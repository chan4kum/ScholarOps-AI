"""Deterministic application form fill. No LLM. No invented credentials."""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any

from opportunity_intel.domain.models import (
    ApplicationPacket,
    EvidenceItem,
    Opportunity,
    UserProfile,
)

CANONICAL_FIELDS = (
    "applicant_name",
    "applicant_email",
    "highest_degree",
    "research_interests",
    "skills",
    "target_countries",
    "position_title",
    "organization",
    "country",
    "supervisor",
    "deadline",
    "funding",
    "source_url",
    "cv_present",
    "cover_letter_present",
    "proposal_present",
    "cited_evidence_ids",
    "publications_claimed",
)


def payload_sha256(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(encoded.encode()).hexdigest()


def fill_form(
    *,
    profile: UserProfile | None,
    opportunity: Opportunity,
    packet: ApplicationPacket,
    evidence: list[EvidenceItem],
) -> dict[str, Any]:
    drafts = {d.kind: d for d in packet.drafts}
    cited: list[int] = []
    for draft in packet.drafts:
        try:
            raw = json.loads(draft.cited_evidence_ids or "[]")
        except json.JSONDecodeError:
            raw = []
        if isinstance(raw, list):
            for value in raw:
                try:
                    cited.append(int(value))
                except (TypeError, ValueError):
                    continue
    cited = sorted(set(cited))
    evidence_ids = {item.id for item in evidence}
    pub_categories = {"publication", "paper", "papers"}
    publications_claimed = any(
        item.id in cited and item.category.lower() in pub_categories for item in evidence
    )
    return {
        "packet_id": packet.id,
        "opportunity_id": opportunity.id,
        "applicant_name": (profile.full_name if profile else "").strip(),
        "applicant_email": (profile.email if profile else "").strip(),
        "highest_degree": (profile.highest_degree if profile else "").strip(),
        "research_interests": (profile.research_interests if profile else "").strip(),
        "skills": (profile.skills if profile else "").strip(),
        "target_countries": (profile.target_countries if profile else "").strip(),
        "position_title": opportunity.title,
        "organization": opportunity.organization,
        "country": opportunity.country_code,
        "supervisor": opportunity.supervisor,
        "deadline": opportunity.deadline.isoformat() if opportunity.deadline else "",
        "funding": opportunity.funding,
        "source_url": opportunity.source_url,
        "cv_present": "cv_tailor" in drafts and bool((drafts["cv_tailor"].body or "").strip()),
        "cover_letter_present": "cover_letter" in drafts
        and bool((drafts["cover_letter"].body or "").strip()),
        "proposal_present": "research_proposal" in drafts
        and bool((drafts["research_proposal"].body or "").strip()),
        "cited_evidence_ids": cited,
        "known_evidence_ids": sorted(evidence_ids),
        "publications_claimed": publications_claimed,
        "packet_status": packet.status,
        "apply_channel": opportunity.apply_channel or "",
        "apply_url": opportunity.apply_url or "",
        "apply_email": opportunity.apply_email or "",
        "apply_notes": opportunity.apply_notes or "",
    }


_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def validate_payload(payload: dict[str, Any]) -> list[dict[str, str]]:
    issues: list[dict[str, str]] = []

    def error(code: str, message: str) -> None:
        issues.append({"level": "error", "code": code, "message": message})

    def warn(code: str, message: str) -> None:
        issues.append({"level": "warning", "code": code, "message": message})

    if payload.get("packet_status") != "ready":
        error("packet_not_ready", "Prepare a complete packet before applying.")
    if not payload.get("applicant_name"):
        error("missing_name", "Profile is missing full name.")
    email = str(payload.get("applicant_email") or "")
    if not email:
        error("missing_email", "Profile is missing email.")
    elif not _EMAIL.match(email):
        error("invalid_email", "Profile email is not a valid address.")
    if not payload.get("highest_degree"):
        error("missing_degree", "Profile is missing highest degree.")
    if not payload.get("cv_present"):
        error("missing_cv", "Packet has no tailored CV draft.")
    if not payload.get("cover_letter_present"):
        error("missing_cover", "Packet has no cover letter draft.")
    if not payload.get("proposal_present"):
        error("missing_proposal", "Packet has no research proposal draft.")
    known = set(payload.get("known_evidence_ids") or [])
    cited = payload.get("cited_evidence_ids") or []
    if isinstance(cited, list):
        unknown = [eid for eid in cited if eid not in known]
        if unknown:
            error("unknown_evidence", f"Drafts cite evidence IDs not in the store: {unknown}")
    if payload.get("publications_claimed"):
        warn("publications", "Drafts claim a publication; confirm this is in stored evidence.")
    if not payload.get("supervisor"):
        warn("no_supervisor", "Supervisor is empty; PI paper citations may be missing.")
    channel = str(payload.get("apply_channel") or "")
    if channel == "unknown" and not payload.get("apply_email") and not payload.get("apply_url"):
        warn("no_apply_path", "Could not find how to apply yet. Preview again after pathfind.")
    return issues


def has_blocking_errors(issues: list[dict[str, str]]) -> bool:
    return any(item["level"] == "error" for item in issues)
