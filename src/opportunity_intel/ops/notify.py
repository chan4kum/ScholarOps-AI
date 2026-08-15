"""Notification adapters. Telegram is optional; log always works. No LLM."""

from __future__ import annotations

from dataclasses import dataclass

import httpx

from opportunity_intel.config import Settings
from opportunity_intel.observability.trace import redact


@dataclass
class NotifyResult:
    channel: str
    ok: bool
    error: str = ""


def send_log(body: str) -> NotifyResult:
    return NotifyResult(channel="log", ok=True)


def send_telegram(body: str, settings: Settings) -> NotifyResult:
    token = (settings.telegram_bot_token or "").strip()
    chat_id = (settings.telegram_chat_id or "").strip()
    if not token or not chat_id:
        return NotifyResult(channel="telegram", ok=True, error="skipped: telegram not configured")
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    try:
        response = httpx.post(
            url,
            json={"chat_id": chat_id, "text": body},
            timeout=15.0,
        )
        if response.status_code >= 400:
            return NotifyResult(
                channel="telegram",
                ok=False,
                error=redact(f"telegram HTTP {response.status_code}"),
            )
        return NotifyResult(channel="telegram", ok=True)
    except httpx.HTTPError as exc:
        return NotifyResult(channel="telegram", ok=False, error=redact(str(exc)))


def dispatch(body: str, settings: Settings) -> list[NotifyResult]:
    return [send_log(body), send_telegram(body, settings)]
