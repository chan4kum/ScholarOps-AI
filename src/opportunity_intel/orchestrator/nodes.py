"""ScholarOps pipeline nodes. Wrap existing discovery/prepare/apply — no second stack."""

from __future__ import annotations

from typing import Any, TypedDict

from sqlalchemy.orm import Session

from opportunity_intel.apply.mapping import validate_payload
from opportunity_intel.apply.service import (
    approve_and_submit,
    preview_application,
    request_approval,
)
from opportunity_intel.config import Settings
from opportunity_intel.discovery.service import run_discovery
from opportunity_intel.domain.models import (
    DraftDocument,
    EvidenceItem,
    Opportunity,
    UploadedDocument,
    UserProfile,
)
from opportunity_intel.llm.models_config import AppModelConfig
from opportunity_intel.prepare.service import prepare_packet
from opportunity_intel.rag import faiss_store
from opportunity_intel.scoring.rules import ProfileSignals, parse_csv, rule_fit_score


class PhdApplicationState(TypedDict, total=False):
    research_query: str
    user_cv_text: str
    discovered_labs: list[dict[str, Any]]
    matched_pis: list[dict[str, Any]]
    human_approved: bool
    drafted_documents: dict[str, str]
    application_status: str
    thread_id: str
    opportunity_id: int | None
    packet_id: int | None
    application_id: int | None
    approval_token: str
    adapter: str
    error: str
    node: str
    reject: bool
    critic_issues: list[dict[str, str]]


class PipelineContext:
    def __init__(
        self,
        session: Session,
        settings: Settings,
        model_config: AppModelConfig,
        *,
        inbox: list[dict[str, Any]] | None = None,
    ) -> None:
        self.session = session
        self.settings = settings
        self.model_config = model_config
        self.inbox = inbox if inbox is not None else []


def empty_state(query: str = "", thread_id: str = "") -> PhdApplicationState:
    return {
        "research_query": query,
        "user_cv_text": "",
        "discovered_labs": [],
        "matched_pis": [],
        "human_approved": False,
        "drafted_documents": {},
        "application_status": "idle",
        "thread_id": thread_id,
        "opportunity_id": None,
        "packet_id": None,
        "application_id": None,
        "approval_token": "",
        "adapter": "",
        "error": "",
        "node": "",
        "reject": False,
        "critic_issues": [],
    }


def _lab_dict(opp: Opportunity) -> dict[str, Any]:
    return {
        "id": opp.id,
        "title": opp.title,
        "organization": opp.organization,
        "country_code": opp.country_code,
        "source_url": opp.source_url,
        "supervisor": opp.supervisor,
        "funding": opp.funding,
        "summary": opp.summary,
        "rule_fit": opp.rule_fit,
    }


def ingestion_node(state: PhdApplicationState, ctx: PipelineContext) -> PhdApplicationState:
    """Load local CV/docs/evidence. Do not call Gemini here."""
    parts: list[str] = []
    profile = ctx.session.query(UserProfile).order_by(UserProfile.id).first()
    if profile is not None:
        parts.append(profile.profile_summary or "")
        parts.append(profile.research_interests or "")
        parts.append(profile.skills or "")
    for doc in ctx.session.query(UploadedDocument).order_by(UploadedDocument.id).all():
        if doc.extracted_text:
            parts.append(doc.extracted_text[:8000])
    for item in ctx.session.query(EvidenceItem).order_by(EvidenceItem.id).all():
        if item.content:
            parts.append(item.content)
    faiss_store.upsert_corpus(ctx.session, ctx.settings)
    text = "\n".join(part.strip() for part in parts if part and part.strip())
    return {
        **state,
        "node": "ingestion",
        "user_cv_text": text[:20000],
        "application_status": "ingested",
        "error": "",
    }


def discovery_node(state: PhdApplicationState, ctx: PipelineContext) -> PhdApplicationState:
    """RSS + DDG, Gemini Search grounding if GEMINI_API_KEY. Forward structured labs."""
    query = (state.get("research_query") or "").strip()
    if len(query) < 3:
        return {
            **state,
            "node": "discovery",
            "application_status": "failed",
            "error": "research_query too short",
        }
    run = run_discovery(ctx.session, query, ctx.model_config, ctx.settings)
    labs = [_lab_dict(row) for row in ctx.session.query(Opportunity).order_by(Opportunity.id).all()]
    return {
        **state,
        "node": "discovery",
        "discovered_labs": labs,
        "application_status": run.status,
        "error": run.error,
        "reject": False,
    }


def matchmaker_node(state: PhdApplicationState, ctx: PipelineContext) -> PhdApplicationState:
    """Existing rule fit (+ stored llm_fit). Do not re-summarize lab facts."""
    profile = ctx.session.query(UserProfile).order_by(UserProfile.id).first()
    signals = ProfileSignals(
        interests=parse_csv(profile.research_interests if profile else ""),
        skills=parse_csv(profile.skills if profile else ""),
        require_funded=True,
    )
    matched: list[dict[str, Any]] = []
    for lab in state.get("discovered_labs") or []:
        score = float(lab.get("rule_fit") or 0)
        if score <= 0:
            score = rule_fit_score(
                title=str(lab.get("title") or ""),
                summary=str(lab.get("summary") or ""),
                funding=str(lab.get("funding") or ""),
                country_code=str(lab.get("country_code") or ""),
                profile=signals,
                allowed_countries=ctx.model_config.target_countries,
                excluded_countries=ctx.model_config.excluded_countries,
            )
        if score <= 0:
            continue
        item = dict(lab)
        item["rule_fit"] = score
        lab_text = (
            f"{lab.get('title') or ''} {lab.get('summary') or ''} {lab.get('supervisor') or ''}"
        )
        item["alignment"] = faiss_store.alignment_score(
            ctx.settings, state.get("user_cv_text") or "", lab_text
        )
        matched.append(item)
    matched.sort(key=lambda row: float(row.get("rule_fit") or 0), reverse=True)
    top = matched[0] if matched else None
    return {
        **state,
        "node": "matchmaker",
        "matched_pis": matched[:12],
        "opportunity_id": int(top["id"]) if top and top.get("id") else state.get("opportunity_id"),
        "application_status": "matched" if matched else "no_match",
        "human_approved": False,
        "error": "" if matched else "No PI/lab matched the CV signals.",
    }


def hitl_node(state: PhdApplicationState, ctx: PipelineContext) -> PhdApplicationState:
    """Dashboard HMAC / human_approved flag. Never terminal input. Never submit."""
    _ = ctx
    if state.get("reject"):
        return {
            **state,
            "node": "hitl",
            "human_approved": False,
            "matched_pis": [],
            "application_status": "rejected_to_discovery",
            "error": "",
        }
    if not state.get("human_approved"):
        return {
            **state,
            "node": "hitl",
            "application_status": "awaiting_hitl",
            "error": "",
        }
    return {
        **state,
        "node": "hitl",
        "application_status": "hitl_approved",
        "error": "",
    }


def drafter_node(state: PhdApplicationState, ctx: PipelineContext) -> PhdApplicationState:
    """Evidence-bound prepare_packet. Does not invent publications."""
    opp_id = state.get("opportunity_id")
    if not opp_id:
        return {
            **state,
            "node": "drafter",
            "application_status": "failed",
            "error": "No matched opportunity to draft",
        }
    try:
        packet = prepare_packet(ctx.session, opp_id, ctx.settings, ctx.model_config)
        drafts = ctx.session.query(DraftDocument).filter_by(packet_id=packet.id).all()
        bodies = {draft.kind: draft.body for draft in drafts}
        preview = preview_application(ctx.session, packet.id, ctx.settings, ctx.model_config)
        adapter = str(preview.get("recommended_adapter") or "email")
        row, token = request_approval(
            ctx.session,
            packet.id,
            ctx.settings,
            adapter=adapter,
            inbox=ctx.inbox,
            model_config=ctx.model_config,
        )
    except (ValueError, PermissionError) as exc:
        return {
            **state,
            "node": "drafter",
            "application_status": "failed",
            "error": str(exc),
        }
    return {
        **state,
        "node": "drafter",
        "packet_id": packet.id,
        "application_id": row.id,
        "approval_token": token,
        "adapter": adapter,
        "drafted_documents": bodies,
        "application_status": "drafted_awaiting_hmac",
        "error": "",
    }


def critic_node(state: PhdApplicationState, ctx: PipelineContext) -> PhdApplicationState:
    """Local draft checks. Does not invent citations; does not submit."""
    packet_id = state.get("packet_id")
    issues: list[dict[str, str]] = []
    if packet_id:
        try:
            payload = preview_application(
                ctx.session, int(packet_id), ctx.settings, ctx.model_config
            )
            issues = validate_payload(payload)
        except (ValueError, PermissionError) as exc:
            issues = [{"level": "error", "code": "preview_failed", "message": str(exc)}]
    bodies = " ".join((state.get("drafted_documents") or {}).values()).lower()
    if "i have published" in bodies and "evidence" not in bodies:
        issues.append(
            {
                "level": "warning",
                "code": "unverified_publication",
                "message": "Draft claims publications; confirm they exist in stored evidence.",
            }
        )
    blocking = [item for item in issues if item.get("level") == "error"]
    return {
        **state,
        "node": "critic",
        "critic_issues": issues,
        "application_status": "critic_blocked" if blocking else "drafted_awaiting_hmac",
        "error": blocking[0]["message"] if blocking else "",
    }


def browser_node(state: PhdApplicationState, ctx: PipelineContext) -> PhdApplicationState:
    """Stage apply via existing adapters. HMAC + APPLY_AS_ME. Login/CAPTCHA/payment fail."""
    app_id = state.get("application_id")
    token = state.get("approval_token") or ""
    if not app_id or not token:
        return {
            **state,
            "node": "browser",
            "application_status": "awaiting_hmac",
            "error": "HMAC approval required before email/portal send.",
        }
    try:
        row = approve_and_submit(
            ctx.session,
            app_id,
            token,
            ctx.settings,
            inbox=ctx.inbox,
        )
    except (ValueError, PermissionError, RuntimeError) as exc:
        return {
            **state,
            "node": "browser",
            "application_status": "failed",
            "error": str(exc),
        }
    return {
        **state,
        "node": "browser",
        "application_status": row.status,
        "approval_token": "",
        "error": row.error,
    }


def run_pipeline(state: PhdApplicationState, ctx: PipelineContext) -> PhdApplicationState:
    """Supervisor: ingest → discover → match → HITL stop → (approve) draft. Browser needs HMAC."""
    if state.get("application_id") and (state.get("approval_token") or "").strip():
        return browser_node(state, ctx)

    current = dict(state)
    if current.get("reject"):
        current["reject"] = False
        current["discovered_labs"] = []
        current["matched_pis"] = []
        current["human_approved"] = False

    current = ingestion_node(current, ctx)
    if not current.get("discovered_labs"):
        current = discovery_node(current, ctx)
        if current.get("application_status") == "failed":
            return current
        current = matchmaker_node(current, ctx)

    if not current.get("human_approved"):
        return hitl_node(current, ctx)

    current = hitl_node(current, ctx)
    current = drafter_node(current, ctx)
    if current.get("application_status") == "failed":
        return current
    return critic_node(current, ctx)
