from __future__ import annotations

import json

from opportunity_intel.config import Settings
from opportunity_intel.discovery.extract import extract_main_text
from opportunity_intel.discovery.fetch import fetch_page
from opportunity_intel.domain.models import Opportunity, UserProfile
from opportunity_intel.llm.json_repair import parse_llm_json
from opportunity_intel.llm.models_config import AppModelConfig
from opportunity_intel.llm.prompting import FIT_RATIONALE_PROMPT, PROFESSOR_INTEL_PROMPT
from opportunity_intel.llm.router import LLMRouter


def enrich_opportunity(
    row: Opportunity,
    profile: UserProfile | None,
    settings: Settings,
    model_config: AppModelConfig,
) -> None:
    """Fill supervisor via extract; write llm_fit via reason. Best-effort."""
    if settings.offline:
        return
    router = LLMRouter(settings, model_config)
    if not row.supervisor and settings.groq_api_key:
        _fill_supervisor(row, router)
    if row.llm_fit is None and settings.deepseek_api_key:
        _fill_fit(row, profile, router)


def _fill_supervisor(row: Opportunity, router: LLMRouter) -> None:
    page = fetch_page(row.source_url)
    if page is None or len(page.html) < 80:
        return
    text = extract_main_text(page.html)
    try:
        result = router.complete(
            "extract",
            [
                {"role": "system", "content": PROFESSOR_INTEL_PROMPT},
                {"role": "user", "content": f"URL: {row.source_url}\n\n{text[:6000]}"},
            ],
            json_mode=True,
        )
        payload = parse_llm_json(result.text)
    except (json.JSONDecodeError, Exception):  # noqa: BLE001
        return
    if not isinstance(payload, dict):
        return
    name = str(payload.get("supervisor") or "").strip()
    if name:
        row.supervisor = name[:300]
    themes = payload.get("themes") or []
    if isinstance(themes, list) and themes and not row.fit_rationale:
        row.fit_rationale = "Themes: " + ", ".join(str(t) for t in themes[:5])


def _fill_fit(row: Opportunity, profile: UserProfile | None, router: LLMRouter) -> None:
    profile_blob = ""
    if profile:
        profile_blob = (
            f"{profile.full_name}; {profile.highest_degree}; "
            f"{profile.research_interests}; {profile.skills}; {profile.profile_summary}"
        )
    try:
        result = router.complete(
            "reason",
            [
                {"role": "system", "content": FIT_RATIONALE_PROMPT},
                {
                    "role": "user",
                    "content": (
                        f"Profile: {profile_blob}\n"
                        f"Title: {row.title}\nOrg: {row.organization}\n"
                        f"Country: {row.country_code}\nFunding: {row.funding}\n"
                        f"Supervisor: {row.supervisor}\nSummary: {row.summary[:1500]}"
                    ),
                },
            ],
            json_mode=True,
        )
        payload = parse_llm_json(result.text)
    except (json.JSONDecodeError, Exception):  # noqa: BLE001
        return
    if not isinstance(payload, dict):
        return
    try:
        score = float(payload.get("llm_fit"))
    except (TypeError, ValueError):
        return
    row.llm_fit = max(0.0, min(100.0, score))
    rationale = str(payload.get("fit_rationale") or "").strip()
    if rationale:
        row.fit_rationale = rationale[:4000]
