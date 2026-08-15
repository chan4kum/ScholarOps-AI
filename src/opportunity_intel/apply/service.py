"""Phase 3 apply pipeline: fill → validate → token → human approve → adapter submit."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session, selectinload

from opportunity_intel.apply.adapters import (
    ADAPTERS,
    HttpFormAdapter,
    ManualAdapter,
    SandboxAdapter,
    SubmitResult,
)
from opportunity_intel.apply.email_send import EmailAdapter
from opportunity_intel.apply.mapping import (
    fill_form,
    has_blocking_errors,
    payload_sha256,
    validate_payload,
)
from opportunity_intel.apply.pathfind import (
    discover_apply_path,
    extract_path_from_html,
    recommended_adapter,
    store_apply_path,
)
from opportunity_intel.apply.portal import PortalAdapter
from opportunity_intel.apply.secrets import resolve_signing_secret
from opportunity_intel.apply.tokens import hash_token, issue_token, parse_and_verify
from opportunity_intel.config import Settings
from opportunity_intel.domain.models import (
    Application,
    ApplicationEvent,
    ApplicationPacket,
    EvidenceItem,
    Opportunity,
    UserProfile,
)
from opportunity_intel.llm.models_config import AppModelConfig
from opportunity_intel.observability.trace import agent_run


def _load_packet(session: Session, packet_id: int) -> ApplicationPacket:
    packet = (
        session.query(ApplicationPacket)
        .options(
            selectinload(ApplicationPacket.requirements),
            selectinload(ApplicationPacket.papers),
            selectinload(ApplicationPacket.drafts),
            selectinload(ApplicationPacket.opportunity),
        )
        .filter_by(id=packet_id)
        .one_or_none()
    )
    if packet is None:
        raise ValueError("Packet not found")
    return packet


def preview_application(
    session: Session,
    packet_id: int,
    settings: Settings | None = None,
    model_config: AppModelConfig | None = None,
) -> dict[str, Any]:
    packet = _load_packet(session, packet_id)
    opp = packet.opportunity
    if opp is None:
        opp = session.get(Opportunity, packet.opportunity_id)
    if opp is None:
        raise ValueError("Opportunity not found")
    if settings is not None:
        if settings.apply_pathfind:
            path = discover_apply_path(opp, settings, model_config)
        else:
            path = extract_path_from_html(opp.summary or "", opp.source_url)
            if opp.apply_email:
                path.apply_email = opp.apply_email
                path.channel = "email"
                path.recommended_adapter = "email"
            if opp.apply_url:
                path.apply_url = opp.apply_url
        store_apply_path(opp, path)
        session.flush()
    profile = session.query(UserProfile).order_by(UserProfile.id).first()
    evidence = session.query(EvidenceItem).order_by(EvidenceItem.id).all()
    payload = fill_form(profile=profile, opportunity=opp, packet=packet, evidence=evidence)
    issues = validate_payload(payload)
    rec = recommended_adapter(
        str(payload.get("apply_channel") or ""),
        str(payload.get("apply_email") or ""),
        str(payload.get("apply_url") or payload.get("source_url") or ""),
    )
    return {
        "packet_id": packet_id,
        "opportunity_id": opp.id,
        "adapter_options": list(ADAPTERS),
        "recommended_adapter": rec,
        "apply_as_me": bool(settings.apply_as_me) if settings else False,
        "fields": payload,
        "issues": issues,
        "can_request_approval": not has_blocking_errors(issues),
        "payload_sha256": payload_sha256(payload),
    }


def _add_event(session: Session, application_id: int, action: str, detail: str) -> None:
    session.add(
        ApplicationEvent(application_id=application_id, action=action, detail=detail[:4000])
    )


def request_approval(
    session: Session,
    packet_id: int,
    settings: Settings,
    *,
    adapter: str = "",
    inbox: list[dict[str, Any]] | None = None,
    model_config: AppModelConfig | None = None,
) -> tuple[Application, str]:
    preview = preview_application(session, packet_id, settings, model_config)
    chosen = (adapter or preview["recommended_adapter"] or "email").strip()
    if chosen not in ADAPTERS:
        raise ValueError(f"Unknown adapter. Use one of: {', '.join(ADAPTERS)}")
    if not preview["can_request_approval"]:
        raise PermissionError("Fix validation errors before requesting approval.")
    fields = preview["fields"]
    if chosen == "email" and not fields.get("apply_email"):
        raise PermissionError(
            "No application email on the vacancy. Use portal if an apply URL exists."
        )
    if chosen == "portal" and not (fields.get("apply_url") or fields.get("source_url")):
        raise PermissionError("No apply URL on the vacancy.")

    with agent_run("application", "request_approval", f"packet {packet_id} adapter={chosen}"):
        row = session.query(Application).filter_by(packet_id=packet_id).one_or_none()
        if row is None:
            row = Application(packet_id=packet_id)
            session.add(row)
            session.flush()
        if row.status == "submitted":
            raise PermissionError("This packet was already submitted.")
        payload = fields
        checksum = preview["payload_sha256"]
        issued = issue_token(
            secret=resolve_signing_secret(settings),
            application_id=row.id,
            payload_sha256=checksum,
            ttl_seconds=settings.apply_token_ttl_seconds,
        )
        row.adapter = chosen
        row.status = "pending_approval"
        row.payload_json = json.dumps(payload, ensure_ascii=True)
        row.payload_sha256 = checksum
        row.token_hash = issued.token_hash
        row.token_expires_at = datetime.fromtimestamp(issued.expires_at_unix, tz=UTC).replace(
            tzinfo=None
        )
        row.token_used = 0
        row.receipt = ""
        row.error = ""
        _add_event(
            session,
            row.id,
            "request_approval",
            f"adapter={chosen} sha256={checksum[:12]}… ttl={settings.apply_token_ttl_seconds}s",
        )
        session.commit()
        session.refresh(row)
        return row, issued.token


def reject_application(session: Session, application_id: int, reason: str = "") -> Application:
    row = session.get(Application, application_id)
    if row is None:
        raise ValueError("Application not found")
    if row.status == "submitted":
        raise PermissionError("Cannot reject a submitted application.")
    row.status = "rejected"
    row.token_hash = ""
    row.token_used = 1
    row.error = (reason or "Rejected by human").strip()[:2000]
    _add_event(session, row.id, "reject", row.error)
    session.commit()
    session.refresh(row)
    return row


def approve_and_submit(
    session: Session,
    application_id: int,
    token: str,
    settings: Settings,
    *,
    inbox: list[dict[str, Any]] | None = None,
    http_target: str = "",
) -> Application:
    row = session.get(Application, application_id)
    if row is None:
        raise ValueError("Application not found")
    if row.status == "submitted":
        raise PermissionError("Already submitted.")
    if row.status != "pending_approval":
        raise PermissionError("Request approval before submitting.")
    if row.token_used:
        raise PermissionError("Approval token already used.")
    secret = resolve_signing_secret(settings)
    try:
        parse_and_verify(
            secret=secret,
            token=token,
            application_id=row.id,
            payload_sha256=row.payload_sha256,
        )
    except ValueError as exc:
        _add_event(session, row.id, "approve_denied", str(exc))
        session.commit()
        raise PermissionError(str(exc)) from exc
    if hash_token(token) != row.token_hash:
        raise PermissionError("Approval token does not match the issued token.")

    payload = json.loads(row.payload_json)
    if payload_sha256(payload) != row.payload_sha256:
        raise PermissionError("Payload checksum mismatch; request a new approval.")
    packet = None
    packet_id = payload.get("packet_id") or row.packet_id
    if packet_id:
        packet = (
            session.query(ApplicationPacket)
            .options(selectinload(ApplicationPacket.drafts))
            .filter_by(id=packet_id)
            .one_or_none()
        )

    with agent_run("application", "submit", f"application {row.id} adapter={row.adapter}"):
        result = _run_adapter(
            row.adapter,
            payload,
            settings,
            inbox=inbox,
            http_target=http_target,
            packet=packet,
        )
        row.token_used = 1
        row.token_hash = ""
        if result.ok:
            row.status = "submitted"
            row.receipt = result.receipt
            row.submitted_at = datetime.now(UTC).replace(tzinfo=None)
            row.error = ""
            opp = session.get(Opportunity, payload.get("opportunity_id"))
            if opp is not None:
                opp.status = "submitted"
            _add_event(session, row.id, "submitted", result.sent_summary)
        else:
            row.status = "failed"
            row.error = result.error
            _add_event(session, row.id, "submit_failed", result.error)
        session.commit()
        session.refresh(row)
    if not result.ok:
        raise RuntimeError(result.error)
    return row


def _run_adapter(
    name: str,
    payload: dict[str, Any],
    settings: Settings,
    *,
    inbox: list[dict[str, Any]] | None,
    http_target: str,
    packet: ApplicationPacket | None = None,
) -> SubmitResult:
    if name == "manual":
        return ManualAdapter().submit(payload)
    if name == "sandbox":
        return SandboxAdapter(inbox if inbox is not None else []).submit(payload)
    if name == "email":
        return EmailAdapter(settings, packet=packet).submit(payload)
    if name == "portal":
        return PortalAdapter(settings).submit(payload)
    if name == "http_form":
        return HttpFormAdapter(http_target, live_submit=settings.apply_live_submit).submit(payload)
    return SubmitResult(ok=False, receipt="", sent_summary="", error=f"Unknown adapter {name}")
