"""Send the application packet as the user via SMTP."""

from __future__ import annotations

import smtplib
from email.message import EmailMessage
from typing import Any

from opportunity_intel.apply.adapters import SubmitResult, _redact_email, _sent_summary
from opportunity_intel.config import Settings
from opportunity_intel.domain.models import ApplicationPacket


def _draft_bodies(packet: ApplicationPacket | None) -> dict[str, str]:
    if packet is None:
        return {}
    return {draft.kind: draft.body or "" for draft in packet.drafts}


def build_message(
    payload: dict[str, Any],
    *,
    packet: ApplicationPacket | None,
    from_addr: str,
) -> EmailMessage:
    drafts = _draft_bodies(packet)
    cover = drafts.get("cover_letter") or ""
    cv = drafts.get("cv_tailor") or ""
    proposal = drafts.get("research_proposal") or ""
    to_addr = str(payload.get("apply_email") or "")
    subject = f"Application: {payload.get('position_title')} — {payload.get('applicant_name')}"
    body = (
        f"{cover.strip()}\n\n"
        f"—\nSent as {payload.get('applicant_name')} <{payload.get('applicant_email')}> "
        f"via ScholarOps AI after human confirmation.\n"
    )
    msg = EmailMessage()
    msg["From"] = from_addr
    msg["To"] = to_addr
    msg["Reply-To"] = str(payload.get("applicant_email") or from_addr)
    msg["Subject"] = subject[:200]
    msg.set_content(body)
    if cv.strip():
        msg.add_attachment(
            cv.encode("utf-8"),
            maintype="text",
            subtype="plain",
            filename="cv.txt",
        )
    if proposal.strip():
        msg.add_attachment(
            proposal.encode("utf-8"),
            maintype="text",
            subtype="plain",
            filename="research_proposal.txt",
        )
    return msg


class EmailAdapter:
    name = "email"

    def __init__(
        self,
        settings: Settings,
        *,
        packet: ApplicationPacket | None = None,
        smtp_send=None,  # noqa: ANN001
    ) -> None:
        self.settings = settings
        self.packet = packet
        self._smtp_send = smtp_send

    def submit(self, payload: dict[str, Any]) -> SubmitResult:
        to_addr = str(payload.get("apply_email") or "").strip()
        if not to_addr or "@" not in to_addr:
            return SubmitResult(
                ok=False,
                receipt="",
                sent_summary="",
                error="No application email found on the vacancy. Cannot apply by email.",
            )
        if not self.settings.apply_as_me:
            return SubmitResult(
                ok=False,
                receipt="",
                sent_summary=_sent_summary(payload),
                error=(
                    "APPLY_AS_ME is false. Set APPLY_AS_ME=true to send email as you "
                    f"to {_redact_email(to_addr)}."
                ),
            )
        domain = to_addr.rsplit("@", 1)[-1].lower()
        if not domain:
            return SubmitResult(
                ok=False,
                receipt="",
                sent_summary="",
                error="Application email domain is invalid.",
            )
        from_addr = (self.settings.smtp_from or str(payload.get("applicant_email") or "")).strip()
        if not from_addr:
            return SubmitResult(
                ok=False,
                receipt="",
                sent_summary="",
                error="Profile email is required to send as you.",
            )
        message = build_message(payload, packet=self.packet, from_addr=from_addr)
        if not self.settings.smtp_host:
            return SubmitResult(
                ok=False,
                receipt="",
                sent_summary="",
                error="SMTP_HOST is not set. Configure SMTP to send as you.",
            )
        try:
            if self._smtp_send is not None:
                self._smtp_send(message)
            else:
                _smtp_send(self.settings, message)
        except (OSError, smtplib.SMTPException) as exc:
            return SubmitResult(ok=False, receipt="", sent_summary="", error=str(exc))
        return SubmitResult(
            ok=True,
            receipt=f"email:{_redact_email(to_addr)}",
            sent_summary=_sent_summary(payload) + f" via email to {_redact_email(to_addr)}",
        )


def _smtp_send(settings: Settings, message: EmailMessage) -> None:
    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=20) as smtp:
        smtp.ehlo()
        smtp.starttls()
        if settings.smtp_username:
            smtp.login(settings.smtp_username, settings.smtp_password)
        smtp.send_message(message)
