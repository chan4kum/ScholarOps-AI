"""Submit adapters. Live university portals are refused unless explicitly allowed."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol
from urllib.parse import urlparse

import httpx

from opportunity_intel.discovery.fetch import USER_AGENT


@dataclass
class SubmitResult:
    ok: bool
    receipt: str
    sent_summary: str
    error: str = ""


class Adapter(Protocol):
    name: str

    def submit(self, payload: dict[str, Any]) -> SubmitResult: ...


class ManualAdapter:
    """Log-only. Human copies the packet to the real portal."""

    name = "manual"

    def submit(self, payload: dict[str, Any]) -> SubmitResult:
        summary = _sent_summary(payload)
        receipt = f"manual:{payload.get('packet_id')}:{payload.get('opportunity_id')}"
        return SubmitResult(ok=True, receipt=receipt, sent_summary=summary)


class SandboxAdapter:
    """Local fake portal. Never leaves the machine."""

    name = "sandbox"

    def __init__(self, inbox: list[dict[str, Any]]) -> None:
        self.inbox = inbox

    def submit(self, payload: dict[str, Any]) -> SubmitResult:
        receipt = f"sandbox:{len(self.inbox) + 1}"
        self.inbox.append({"receipt": receipt, "payload": payload})
        return SubmitResult(ok=True, receipt=receipt, sent_summary=_sent_summary(payload))


class HttpFormAdapter:
    """POST JSON to a loopback URL only. Real university hosts are refused."""

    name = "http_form"

    def __init__(self, target_url: str, *, live_submit: bool) -> None:
        self.target_url = target_url
        self.live_submit = live_submit

    def submit(self, payload: dict[str, Any]) -> SubmitResult:
        if not self.live_submit:
            return SubmitResult(
                ok=False,
                receipt="",
                sent_summary="",
                error="Live HTTP submit is disabled. Use manual or sandbox.",
            )
        parsed = urlparse(self.target_url)
        host = (parsed.hostname or "").lower()
        if parsed.scheme not in {"http", "https"} or host not in {"127.0.0.1", "localhost"}:
            return SubmitResult(
                ok=False,
                receipt="",
                sent_summary="",
                error="HTTP adapter may only POST to localhost / 127.0.0.1.",
            )
        try:
            response = httpx.post(
                self.target_url,
                json=payload,
                timeout=10.0,
                headers={"User-Agent": USER_AGENT, "Content-Type": "application/json"},
            )
        except httpx.HTTPError as exc:
            return SubmitResult(ok=False, receipt="", sent_summary="", error=str(exc))
        if response.status_code >= 400:
            return SubmitResult(
                ok=False,
                receipt="",
                sent_summary="",
                error=f"Portal returned HTTP {response.status_code}",
            )
        return SubmitResult(
            ok=True,
            receipt=f"http:{response.status_code}",
            sent_summary=_sent_summary(payload),
        )


ADAPTERS = ("email", "portal", "sandbox", "manual")


def _sent_summary(payload: dict[str, Any]) -> str:
    email = str(payload.get("applicant_email") or "")
    redacted = _redact_email(email)
    return (
        f"{payload.get('applicant_name')} <{redacted}> → "
        f"{payload.get('position_title')} @ {payload.get('organization')} "
        f"(packet {payload.get('packet_id')})"
    )


def _redact_email(email: str) -> str:
    if "@" not in email:
        return ""
    local, domain = email.split("@", 1)
    if not local:
        return f"*@{domain}"
    return f"{local[0]}***@{domain}"
