"""Find how to apply from the vacancy page. Prefer page facts over LLM guesses."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import urljoin

from opportunity_intel.config import Settings
from opportunity_intel.discovery.extract import extract_main_text
from opportunity_intel.discovery.fetch import fetch_page
from opportunity_intel.domain.models import Opportunity
from opportunity_intel.llm.models_config import AppModelConfig
from opportunity_intel.llm.prompting import APPLY_PATH_PROMPT
from opportunity_intel.llm.router import LLMRouter

_MAILTO = re.compile(r"mailto:([^?\"'\s>]+)", re.I)
_EMAIL = re.compile(r"[A-Z0-9._%+\-]+@[A-Z0-9.\-]+\.[A-Z]{2,}", re.I)
_HREF = re.compile(r"""href\s*=\s*["']([^"']+)["']""", re.I)
_APPLY_WORDS = (
    "apply",
    "application",
    "sollicit",
    "bewerb",
    "postul",
    "candidat",
    "online application",
)


@dataclass
class ApplyPath:
    channel: str
    apply_url: str
    apply_email: str
    notes: str
    recommended_adapter: str


def recommended_adapter(channel: str, apply_email: str, apply_url: str) -> str:
    if channel == "email" or apply_email:
        return "email"
    if channel == "portal" or apply_url:
        return "portal"
    return "email"


def _clean_email(raw: str) -> str:
    value = raw.strip().strip(".,;()[]<>").replace("%20", "")
    if value.lower().startswith("mailto:"):
        value = value.split(":", 1)[1]
    if "@" not in value:
        return ""
    return value[:300]


def extract_path_from_html(html: str, base_url: str) -> ApplyPath:
    emails = [_clean_email(item) for item in _MAILTO.findall(html)]
    emails += [_clean_email(item) for item in _EMAIL.findall(html)]
    emails = [item for item in emails if item]
    apply_email = emails[0] if emails else ""

    apply_url = ""
    for href in _HREF.findall(html):
        lowered = href.lower()
        if not any(word in lowered for word in _APPLY_WORDS):
            continue
        absolute = urljoin(base_url, href)
        if not absolute.startswith("http"):
            continue
        apply_url = absolute[:1000]
        break

    if apply_email:
        channel = "email"
        notes = (
            "Vacancy lists an application email. "
            "Agent will send CV, cover letter, and proposal as you."
        )
    elif apply_url:
        channel = "portal"
        notes = "Vacancy lists an apply link. Agent will fill the public form as you."
    else:
        channel = "unknown"
        notes = (
            "No mailto or apply link found. "
            "Agent can still try the listing URL as a portal if you confirm."
        )
        apply_url = base_url if base_url.startswith("http") else ""
    return ApplyPath(
        channel=channel,
        apply_url=apply_url,
        apply_email=apply_email,
        notes=notes,
        recommended_adapter=recommended_adapter(channel, apply_email, apply_url),
    )


def _merge_llm(path: ApplyPath, payload: dict[str, Any], page_text: str) -> ApplyPath:
    channel = str(payload.get("channel") or path.channel).strip().lower()
    if channel not in {"email", "portal", "unknown"}:
        channel = path.channel
    email = _clean_email(str(payload.get("apply_email") or ""))
    blob = page_text.lower()
    if email and email.lower() not in blob and email != path.apply_email:
        email = ""
    url = str(payload.get("apply_url") or "").strip()
    if url and url not in page_text and url != path.apply_url:
        url = ""
    notes = str(payload.get("notes") or path.notes).strip()[:1000]
    apply_email = email or path.apply_email
    apply_url = url or path.apply_url
    if apply_email:
        channel = "email"
    elif apply_url and channel == "unknown":
        channel = "portal"
    return ApplyPath(
        channel=channel,
        apply_url=apply_url,
        apply_email=apply_email,
        notes=notes or path.notes,
        recommended_adapter=recommended_adapter(channel, apply_email, apply_url),
    )


def discover_apply_path(
    opportunity: Opportunity,
    settings: Settings,
    model_config: AppModelConfig | None = None,
) -> ApplyPath:
    page = fetch_page(opportunity.source_url, use_playwright=settings.use_playwright)
    html = page.html if page else ""
    base = page.url if page else opportunity.source_url
    path = extract_path_from_html(html, base)
    page_text = extract_main_text(html)[:8000] if html else (opportunity.summary or "")
    if model_config and settings.groq_api_key and page_text.strip():
        try:
            router = LLMRouter(settings, model_config)
            result = router.complete(
                "extract",
                [
                    {"role": "system", "content": APPLY_PATH_PROMPT},
                    {
                        "role": "user",
                        "content": (
                            f"Title: {opportunity.title}\nOrg: {opportunity.organization}\n"
                            f"URL: {opportunity.source_url}\n\n{page_text}"
                        ),
                    },
                ],
                json_mode=True,
            )
            payload = json.loads(result.text)
            if isinstance(payload, dict):
                path = _merge_llm(path, payload, page_text)
        except Exception:  # noqa: BLE001 — pathfind must not block apply preview
            pass
    return path


def store_apply_path(opportunity: Opportunity, path: ApplyPath) -> None:
    opportunity.apply_channel = path.channel
    opportunity.apply_url = path.apply_url
    opportunity.apply_email = path.apply_email
    opportunity.apply_notes = path.notes
