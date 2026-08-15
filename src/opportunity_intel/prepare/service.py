"""Phase 2 prepare pipeline: requirements → checklist → PI papers → drafts."""

from __future__ import annotations

import json
import time
from typing import Any, Protocol

from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from opportunity_intel.config import Settings
from opportunity_intel.discovery.extract import extract_main_text
from opportunity_intel.discovery.fetch import fetch_page
from opportunity_intel.domain.models import (
    ApplicationPacket,
    DraftDocument,
    EvidenceItem,
    Opportunity,
    ProfessorPaper,
    RequirementItem,
    UserProfile,
)
from opportunity_intel.llm.budget import BudgetExceeded
from opportunity_intel.llm.json_repair import parse_llm_json
from opportunity_intel.llm.models_config import AppModelConfig
from opportunity_intel.llm.prompting import (
    CHECKLIST_PROMPT,
    PACKET_DRAFT_PROMPT,
    REQUIREMENTS_EXTRACT_PROMPT,
)
from opportunity_intel.llm.router import LLMRouter
from opportunity_intel.observability.trace import agent_run
from opportunity_intel.prepare.papers import PaperHit, search_professor_papers

_LOCK_RETRIES = 6
_LOCK_SLEEP_S = 0.4


class _PaperLike(Protocol):
    title: str
    year: int | None
    authors: str
    url: str


def _vacancy_blob(opp: Opportunity) -> str:
    page = fetch_page(opp.source_url)
    page_text = ""
    if page is not None and len(page.html) > 80:
        page_text = extract_main_text(page.html)[:8000]
    return (
        f"Title: {opp.title}\nOrg: {opp.organization}\nCountry: {opp.country_code}\n"
        f"Location: {opp.location}\nFunding: {opp.funding}\nDeadline: {opp.deadline}\n"
        f"Supervisor: {opp.supervisor}\nURL: {opp.source_url}\nSummary: {opp.summary}\n"
        f"Page text:\n{page_text}"
    )


def _evidence_block(items: list[EvidenceItem]) -> str:
    if not items:
        return "No stored evidence items. Do not invent projects or papers."
    lines = []
    for item in items:
        lines.append(
            f"EV-{item.id} [{item.category}] {item.content}\n  quote: {item.source_quote[:400]}"
        )
    return "\n".join(lines)


def _profile_block(profile: UserProfile | None) -> str:
    if profile is None:
        return "No profile yet."
    return (
        f"Name: {profile.full_name}\nDegree: {profile.highest_degree}\n"
        f"Interests: {profile.research_interests}\nSkills: {profile.skills}\n"
        f"Funding: {profile.funding_requirement}\nCountries: {profile.target_countries}\n"
        f"Summary: {profile.profile_summary}\nNotes: {profile.notes}"
    )


def _heuristic_requirements(opp: Opportunity) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    if opp.funding:
        rows.append({"text": f"Funding: {opp.funding}", "category": "funding"})
    rows.append({"text": "Doctoral / PhD vacancy", "category": "other"})
    if opp.country_code:
        rows.append({"text": f"Location in {opp.country_code}", "category": "other"})
    if opp.deadline:
        rows.append({"text": f"Deadline {opp.deadline}", "category": "other"})
    return rows


def _extract_requirements(router: LLMRouter, blob: str, opp: Opportunity) -> list[dict[str, str]]:
    try:
        result = router.complete(
            "extract",
            [
                {"role": "system", "content": REQUIREMENTS_EXTRACT_PROMPT},
                {"role": "user", "content": blob[:12000]},
            ],
            json_mode=True,
        )
        payload = parse_llm_json(result.text)
        raw = payload.get("requirements") or []
        items: list[dict[str, str]] = []
        if isinstance(raw, list):
            for row in raw:
                if isinstance(row, dict) and str(row.get("text") or "").strip():
                    items.append(
                        {
                            "text": str(row.get("text")).strip()[:800],
                            "category": str(row.get("category") or "other")[:40],
                        }
                    )
        return items or _heuristic_requirements(opp)
    except BudgetExceeded:
        raise
    except Exception:  # noqa: BLE001
        return _heuristic_requirements(opp)


def _score_checklist(
    router: LLMRouter,
    requirements: list[dict[str, str]],
    profile: UserProfile | None,
    evidence: list[EvidenceItem],
) -> list[dict[str, str]]:
    if not requirements:
        return []
    try:
        result = router.complete(
            "reason",
            [
                {"role": "system", "content": CHECKLIST_PROMPT},
                {
                    "role": "user",
                    "content": (
                        f"Profile:\n{_profile_block(profile)}\n\n"
                        f"Evidence:\n{_evidence_block(evidence)}\n\n"
                        f"Requirements JSON:\n{json.dumps(requirements)}"
                    ),
                },
            ],
            json_mode=True,
        )
        payload = parse_llm_json(result.text)
        raw = payload.get("items") or []
        scored: list[dict[str, str]] = []
        if isinstance(raw, list):
            for row in raw:
                if not isinstance(row, dict):
                    continue
                status = str(row.get("status") or "unknown").lower()
                if status not in {"met", "gap", "unknown"}:
                    status = "unknown"
                text = str(row.get("text") or "").strip()
                if not text:
                    continue
                scored.append(
                    {
                        "text": text[:800],
                        "status": status,
                        "evidence_note": str(row.get("evidence_note") or "")[:1000],
                    }
                )
        if scored:
            return scored
    except BudgetExceeded:
        raise
    except Exception:  # noqa: BLE001
        pass
    return [
        {"text": row["text"], "status": "unknown", "evidence_note": "Checklist LLM unavailable"}
        for row in requirements
    ]


def _write_drafts(
    router: LLMRouter,
    *,
    opp: Opportunity,
    profile: UserProfile | None,
    evidence: list[EvidenceItem],
    papers: list[_PaperLike],
) -> dict[str, Any]:
    paper_lines = [
        f"- {p.title} ({p.year or 'n.d.'}) {p.authors} {p.url}".strip() for p in papers
    ] or ["(no PI papers found — do not invent titles)"]
    allowed_ids = {item.id for item in evidence}
    result = router.complete(
        "draft",
        [
            {"role": "system", "content": PACKET_DRAFT_PROMPT},
            {
                "role": "user",
                "content": (
                    f"Vacancy:\n{_vacancy_blob(opp)[:6000]}\n\n"
                    f"Profile:\n{_profile_block(profile)}\n\n"
                    f"Evidence:\n{_evidence_block(evidence)}\n\n"
                    f"PI papers (cite only these titles):\n" + "\n".join(paper_lines)
                ),
            },
        ],
        json_mode=True,
    )
    payload = parse_llm_json(result.text)
    raw_ids = payload.get("cited_evidence_ids") or []
    cited_ids: list[int] = []
    if isinstance(raw_ids, list):
        for value in raw_ids:
            try:
                eid = int(value)
            except (TypeError, ValueError):
                continue
            if eid in allowed_ids:
                cited_ids.append(eid)
    allowed_titles = {p.title.lower() for p in papers}
    raw_titles = payload.get("cited_paper_titles") or []
    cited_titles: list[str] = []
    if isinstance(raw_titles, list):
        for title in raw_titles:
            text = str(title).strip()
            if text and text.lower() in allowed_titles:
                cited_titles.append(text)
    outreach = str(payload.get("outreach_email") or "").strip()
    if not outreach:
        outreach = (
            f"Subject: Prospective PhD Inquiry: {opp.title} — {profile.full_name if profile else 'Chandan Kumar'}\n\n"
            f"Dear Professor {opp.supervisor or 'Hiring Committee'},\n\n"
            f"I am writing to inquire about the funded doctoral vacancy on '{opp.title}' at {opp.organization}.\n"
            f"Holding an MSc in Data Science with Distinction, my research and technical background in machine learning "
            f"align closely with this position.\n\n"
            f"Please find my attached tailored CV and research proposal for your review. I would welcome the opportunity "
            f"to discuss how my background fits your team's objectives.\n\n"
            f"Sincerely,\n{profile.full_name if profile else 'Chandan Kumar'}"
        )
    return {
        "cv_tailor": str(payload.get("cv_tailor") or "").strip(),
        "cover_letter": str(payload.get("cover_letter") or "").strip(),
        "research_proposal": str(payload.get("research_proposal") or "").strip(),
        "outreach_email": outreach,
        "cited_evidence_ids": cited_ids,
        "cited_paper_titles": cited_titles,
    }


def _commit_with_lock_retry(session: Session) -> None:
    """Commit; if SQLite is briefly busy, wait and retry the same pending work.

    Do not rollback between retries — that would drop unflushed changes.
    """
    last: OperationalError | None = None
    for attempt in range(_LOCK_RETRIES):
        try:
            session.commit()
            return
        except OperationalError as exc:
            last = exc
            if "database is locked" not in str(exc).lower():
                raise
            time.sleep(_LOCK_SLEEP_S * (attempt + 1))
    assert last is not None
    raise last


def _mark_packet_preparing(session: Session, opportunity_id: int) -> int:
    packet = session.query(ApplicationPacket).filter_by(opportunity_id=opportunity_id).one_or_none()
    if packet is None:
        packet = ApplicationPacket(opportunity_id=opportunity_id, status="preparing", error="")
        session.add(packet)
    else:
        packet.status = "preparing"
        packet.error = ""
    _commit_with_lock_retry(session)
    session.refresh(packet)
    return packet.id


def _mark_packet_failed(session: Session, packet_id: int, error: str) -> None:
    packet = session.get(ApplicationPacket, packet_id)
    if packet is None:
        return
    packet.status = "failed"
    packet.error = error[:4000]
    _commit_with_lock_retry(session)


def _persist_packet_results(
    session: Session,
    *,
    packet_id: int,
    opportunity_id: int,
    scored: list[dict[str, str]],
    hits: list[PaperHit],
    drafts: dict[str, Any],
) -> ApplicationPacket:
    packet = session.get(ApplicationPacket, packet_id)
    opp = session.get(Opportunity, opportunity_id)
    if packet is None or opp is None:
        raise ValueError("Opportunity not found")
    session.query(RequirementItem).filter_by(packet_id=packet_id).delete()
    session.query(ProfessorPaper).filter_by(packet_id=packet_id).delete()
    session.query(DraftDocument).filter_by(packet_id=packet_id).delete()
    for row in scored:
        session.add(
            RequirementItem(
                packet_id=packet_id,
                text=row["text"],
                status=row["status"],
                evidence_note=row.get("evidence_note") or "",
            )
        )
    for hit in hits:
        session.add(
            ProfessorPaper(
                packet_id=packet_id,
                title=hit.title,
                year=hit.year,
                authors=hit.authors,
                venue=hit.venue,
                url=hit.url,
            )
        )
    cited_ids = json.dumps(drafts["cited_evidence_ids"])
    cited_titles = json.dumps(drafts["cited_paper_titles"])
    for kind, body in (
        ("cv_tailor", drafts["cv_tailor"]),
        ("cover_letter", drafts["cover_letter"]),
        ("research_proposal", drafts["research_proposal"]),
        ("outreach_email", drafts.get("outreach_email", "")),
    ):
        if body:
            session.add(
                DraftDocument(
                    packet_id=packet_id,
                    kind=kind,
                    body=body,
                    cited_evidence_ids=cited_ids,
                    cited_paper_titles=cited_titles if kind == "research_proposal" else "[]",
                )
            )
    packet.status = "ready"
    packet.error = ""
    opp.status = "prepared"
    _commit_with_lock_retry(session)
    session.refresh(packet)
    return packet


def prepare_packet(
    session: Session,
    opportunity_id: int,
    settings: Settings,
    model_config: AppModelConfig,
) -> ApplicationPacket:
    opp = session.query(Opportunity).filter_by(id=opportunity_id).one_or_none()
    if opp is None:
        raise ValueError("Opportunity not found")
    if not settings.deepseek_api_key or not settings.groq_api_key:
        raise PermissionError("DeepSeek and Groq API keys required to prepare a packet.")

    session.expire_on_commit = False

    profile = session.query(UserProfile).order_by(UserProfile.id).first()
    evidence = session.query(EvidenceItem).order_by(EvidenceItem.id).all()
    # Touch attributes so they survive expunge (no lazy loads during LLM I/O).
    _ = (
        opp.title,
        opp.organization,
        opp.country_code,
        opp.location,
        opp.funding,
        opp.deadline,
        opp.supervisor,
        opp.source_url,
        opp.summary,
    )
    if profile is not None:
        _ = (
            profile.full_name,
            profile.highest_degree,
            profile.research_interests,
            profile.skills,
            profile.funding_requirement,
            profile.target_countries,
            profile.profile_summary,
            profile.notes,
        )
    for item in evidence:
        _ = (item.id, item.category, item.content, item.source_quote)

    packet_id = _mark_packet_preparing(session, opportunity_id)
    session.expunge_all()

    try:
        with agent_run("prepare", "packet", f"opportunity {opportunity_id}"):
            router = LLMRouter(settings, model_config)
            blob = _vacancy_blob(opp)
            reqs = _extract_requirements(router, blob, opp)
            scored = _score_checklist(router, reqs, profile, evidence)
            hits = search_professor_papers(opp.supervisor, opp.organization)
            drafts = _write_drafts(router, opp=opp, profile=profile, evidence=evidence, papers=hits)
    except BudgetExceeded as exc:
        _mark_packet_failed(session, packet_id, str(exc))
        raise
    except Exception as exc:  # noqa: BLE001
        _mark_packet_failed(session, packet_id, str(exc))
        raise

    return _persist_packet_results(
        session,
        packet_id=packet_id,
        opportunity_id=opportunity_id,
        scored=scored,
        hits=hits,
        drafts=drafts,
    )
