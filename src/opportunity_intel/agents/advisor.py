"""Profile builder and research advisor agents."""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy.orm import Session

from opportunity_intel.config import Settings
from opportunity_intel.documents.extract import truncate
from opportunity_intel.domain.models import (
    AdvisorMessage,
    EvidenceItem,
    ResearchSuggestion,
    UploadedDocument,
    UserProfile,
)
from opportunity_intel.llm.json_repair import parse_llm_json
from opportunity_intel.llm.models_config import AppModelConfig
from opportunity_intel.llm.prompting import (
    ADVISOR_SYSTEM,
    DOC_EXTRACT_PROMPT,
    PROFILE_SYNTHESIS_PROMPT,
)
from opportunity_intel.llm.router import LLMRouter
from opportunity_intel.observability.trace import agent_run


def usable_parsed_facts(raw: str | None) -> dict[str, Any] | None:
    """Reuse Groq extracts that already succeeded; skip error payloads."""
    if not raw or not raw.strip():
        return None
    try:
        facts = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if isinstance(facts, dict) and "error" not in facts:
        return facts
    return None


def extract_document_facts(
    router: LLMRouter,
    doc: UploadedDocument,
) -> dict[str, Any]:
    if not doc.extracted_text.strip():
        return {"evidence": [], "note": "no text extracted"}
    messages = [
        {"role": "system", "content": DOC_EXTRACT_PROMPT},
        {
            "role": "user",
            "content": f"Document type label: {doc.doc_type}\n\n{truncate(doc.extracted_text)}",
        },
    ]
    result = router.complete("extract", messages, json_mode=True)
    return parse_llm_json(result.text)


def build_profile_from_documents(
    session: Session,
    settings: Settings,
    model_config: AppModelConfig,
) -> tuple[UserProfile, list[ResearchSuggestion], list[EvidenceItem]]:
    docs = session.query(UploadedDocument).order_by(UploadedDocument.id).all()
    if not docs:
        raise ValueError("Upload at least one document first.")

    with agent_run("profile_builder", "analyze", f"{len(docs)} documents"):
        return _build_profile(session, settings, model_config, docs)


def _build_profile(
    session: Session,
    settings: Settings,
    model_config: AppModelConfig,
    docs: list[UploadedDocument],
) -> tuple[UserProfile, list[ResearchSuggestion], list[EvidenceItem]]:
    router = LLMRouter(settings, model_config)
    fact_blocks: list[str] = []

    for doc in docs:
        reused = usable_parsed_facts(doc.parsed_facts) if doc.status == "parsed" else None
        if reused is not None:
            fact_blocks.append(
                f"=== {doc.doc_type}: {doc.original_name} ===\n{json.dumps(reused, indent=2)}"
            )
            continue
        if not (doc.extracted_text or "").strip():
            doc.status = "failed"
            doc.parsed_facts = json.dumps({"error": "no text extracted"})
            session.commit()
            continue
        doc.status = "processing"
        session.commit()
        try:
            facts = extract_document_facts(router, doc)
            doc.parsed_facts = json.dumps(facts)
            doc.status = "parsed"
            fact_blocks.append(
                f"=== {doc.doc_type}: {doc.original_name} ===\n{json.dumps(facts, indent=2)}"
            )
        except Exception as exc:  # noqa: BLE001
            doc.status = "failed"
            doc.parsed_facts = json.dumps({"error": str(exc)})
            session.commit()
            continue

    if not fact_blocks:
        raise ValueError("No documents could be parsed. Check Monitor traces.")

    session.commit()

    messages = [
        {"role": "system", "content": PROFILE_SYNTHESIS_PROMPT},
        {"role": "user", "content": "\n\n".join(fact_blocks)},
    ]
    synthesis = parse_llm_json(router.complete("reason", messages, json_mode=True).text)

    profile_data = synthesis.get("profile") or {}
    row = session.query(UserProfile).order_by(UserProfile.id).first()
    if row is None:
        row = UserProfile()
        session.add(row)

    row.full_name = profile_data.get("full_name") or row.full_name
    row.email = profile_data.get("email") or row.email
    row.highest_degree = profile_data.get("highest_degree") or row.highest_degree
    row.research_interests = profile_data.get("research_interests") or row.research_interests
    row.skills = profile_data.get("skills") or row.skills
    row.funding_requirement = profile_data.get("funding_requirement") or row.funding_requirement
    row.target_countries = profile_data.get("target_countries") or row.target_countries
    row.profile_summary = profile_data.get("profile_summary") or ""
    row.notes = profile_data.get("notes") or ""
    row.profile_source = "documents"

    session.query(ResearchSuggestion).update({"active": 0})
    session.query(EvidenceItem).delete()

    suggestions: list[ResearchSuggestion] = []
    for item in synthesis.get("research_suggestions") or []:
        suggestion = ResearchSuggestion(
            title=item.get("title") or "Research direction",
            summary=item.get("summary") or "",
            rationale=item.get("rationale") or "",
            next_steps=item.get("next_steps") or "",
            priority=item.get("priority") or "medium",
            active=1,
        )
        session.add(suggestion)
        suggestions.append(suggestion)

    evidence_items: list[EvidenceItem] = []
    for doc in docs:
        if not doc.parsed_facts:
            continue
        facts = json.loads(doc.parsed_facts)
        for ev in facts.get("evidence") or []:
            item = EvidenceItem(
                document_id=doc.id,
                category=ev.get("category") or "general",
                content=ev.get("content") or "",
                source_quote=ev.get("quote") or "",
            )
            session.add(item)
            evidence_items.append(item)

    welcome = (
        "I've reviewed your uploaded documents and created your profile. "
        "Here are research directions I'd explore first:\n\n"
        + "\n".join(
            f"- **{s.title}** ({s.priority}): {s.summary[:200]}..."
            if len(s.summary) > 200
            else f"- **{s.title}** ({s.priority}): {s.summary}"
            for s in suggestions
        )
        + "\n\nAsk me about any suggestion — why it fits, what to read first, or how to narrow it."
    )
    session.query(AdvisorMessage).delete()
    session.add(AdvisorMessage(role="assistant", content=welcome))

    session.commit()
    session.refresh(row)
    for s in suggestions:
        session.refresh(s)
    return row, suggestions, evidence_items


def chat_with_advisor(
    session: Session,
    settings: Settings,
    model_config: AppModelConfig,
    user_message: str,
) -> AdvisorMessage:
    router = LLMRouter(settings, model_config)
    with agent_run("advisor", "chat", user_message[:200]):
        return _chat(session, router, user_message)


def _chat(session: Session, router: LLMRouter, user_message: str) -> AdvisorMessage:
    profile = session.query(UserProfile).order_by(UserProfile.id).first()
    suggestions = (
        session.query(ResearchSuggestion).filter_by(active=1).order_by(ResearchSuggestion.id).all()
    )
    history = session.query(AdvisorMessage).order_by(AdvisorMessage.id.desc()).limit(20).all()
    history.reverse()

    context_parts = []
    if profile:
        context_parts.append(
            f"Profile: {profile.full_name}; degree: {profile.highest_degree}; "
            f"interests: {profile.research_interests}; skills: {profile.skills}; "
            f"summary: {profile.profile_summary}"
        )
    if suggestions:
        context_parts.append(
            "Active suggestions:\n"
            + "\n".join(
                f"- {s.title} [{s.priority}]: {s.rationale}\n  Next: {s.next_steps}"
                for s in suggestions
            )
        )

    messages: list[dict[str, str]] = [
        {"role": "system", "content": ADVISOR_SYSTEM + "\n\n" + "\n\n".join(context_parts)},
    ]
    for msg in history:
        messages.append({"role": msg.role, "content": msg.content})
    messages.append({"role": "user", "content": user_message})

    session.add(AdvisorMessage(role="user", content=user_message))
    reply_text = router.complete("reason", messages).text
    reply = AdvisorMessage(role="assistant", content=reply_text)
    session.add(reply)
    session.commit()
    session.refresh(reply)
    return reply
