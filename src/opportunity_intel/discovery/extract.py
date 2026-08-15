from __future__ import annotations

import json
import re
from datetime import date, datetime
from typing import Any

from selectolax.parser import HTMLParser

from opportunity_intel.discovery.sources import RawListing
from opportunity_intel.llm.prompting import PHD_VACANCY_EXTRACT_PROMPT
from opportunity_intel.llm.router import LLMRouter
from opportunity_intel.scoring.rules import normalize_country

JOB_POSTING_TYPE = "JobPosting"
PHD_HINTS = ("phd", "ph.d", "doctoral", "doctorate", "promovendus", "doktorand")
FUNDING_HINTS = ("fully funded", "funded", "stipend", "salary", "employment")


def _clean(text: str) -> str:
    return " ".join(text.split()).strip()


def extract_main_text(html: str) -> str:
    try:
        import trafilatura

        extracted = trafilatura.extract(html, include_comments=False, include_tables=False)
        if extracted and len(extracted) > 80:
            return extracted[:12000]
    except Exception:  # noqa: BLE001
        pass
    tree = HTMLParser(html)
    for node in tree.css("script, style, nav, footer"):
        node.decompose()
    return _clean(tree.body.text() if tree.body else tree.text())[:12000]


def _json_ld_blocks(html: str) -> list[dict[str, Any]]:
    tree = HTMLParser(html)
    blocks: list[dict[str, Any]] = []
    for script in tree.css('script[type="application/ld+json"]'):
        raw = script.text() or ""
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if isinstance(data, list):
            blocks.extend(item for item in data if isinstance(item, dict))
        elif isinstance(data, dict):
            graph = data.get("@graph")
            if isinstance(graph, list):
                blocks.extend(item for item in graph if isinstance(item, dict))
            else:
                blocks.append(data)
    return blocks


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    text = value.strip()[:40]
    for fmt in ("%Y-%m-%d", "%d %B %Y", "%d %b %Y", "%d/%m/%Y"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    match = re.search(r"(20\d{2}-\d{2}-\d{2})", text)
    if match:
        try:
            return datetime.strptime(match.group(1), "%Y-%m-%d").date()
        except ValueError:
            return None
    return None


def extract_local(url: str, html: str, *, source: str) -> RawListing | None:
    """Structured extract. No LLM."""
    tree = HTMLParser(html)
    title = ""
    organization = ""
    location = ""
    summary = ""
    funding = ""
    deadline: date | None = None
    supervisor = ""

    for block in _json_ld_blocks(html):
        types = block.get("@type")
        type_list = types if isinstance(types, list) else [types]
        if JOB_POSTING_TYPE not in type_list:
            continue
        title = block.get("title") or block.get("name") or title
        org = block.get("hiringOrganization") or {}
        if isinstance(org, dict):
            organization = org.get("name") or organization
        job_loc = block.get("jobLocation") or {}
        if isinstance(job_loc, dict):
            address = job_loc.get("address") or {}
            if isinstance(address, dict):
                location = (
                    address.get("addressCountry") or address.get("addressLocality") or location
                )
        deadline = _parse_date(block.get("validThrough") or block.get("datePosted")) or deadline
        summary = block.get("description") or summary
        if block.get("baseSalary") or block.get("jobBenefits"):
            funding = "salary listed"

    if not title:
        h1 = tree.css_first("h1")
        og = tree.css_first('meta[property="og:title"]')
        title = (h1.text() if h1 else "") or (og.attributes.get("content") if og else "") or ""
    if not summary:
        meta = tree.css_first('meta[name="description"]')
        summary = (meta.attributes.get("content") if meta else "") or extract_main_text(html)[:800]

    blob = f"{title} {summary}".lower()
    if not any(hint in blob for hint in PHD_HINTS):
        return None
    if any(hint in blob for hint in FUNDING_HINTS):
        funding = funding or "funded mentioned"

    title = _clean(title)
    if not title:
        return None
    return RawListing(
        title=title[:500],
        source_url=url,
        organization=_clean(organization)[:300],
        location=_clean(location)[:300],
        summary=_clean(summary)[:1200],
        source=source,
        funding=funding,
        deadline=deadline,
        supervisor=_clean(supervisor)[:300],
    )


def local_extract_is_thin(listing: RawListing | None) -> bool:
    if listing is None:
        return True
    return not listing.deadline and not listing.organization and len(listing.summary) < 120


def extract_with_groq(router: LLMRouter, url: str, html: str, *, source: str) -> RawListing | None:
    """Groq extract role only. Never send raw HTML to Grok/DeepSeek polish."""
    text = extract_main_text(html)
    if len(text) < 80:
        return None
    result = router.complete(
        "extract",
        [
            {"role": "system", "content": PHD_VACANCY_EXTRACT_PROMPT},
            {"role": "user", "content": f"URL: {url}\n\n{text[:8000]}"},
        ],
        json_mode=True,
    )
    try:
        payload = json.loads(result.text)
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict) or not payload.get("is_phd_position"):
        return None
    title = _clean(str(payload.get("title") or ""))
    if not title:
        return None
    location = _clean(str(payload.get("location") or payload.get("country") or ""))
    country = normalize_country(str(payload.get("country") or location))
    return RawListing(
        title=title[:500],
        source_url=url,
        organization=_clean(str(payload.get("organization") or ""))[:300],
        location=location or country,
        summary=_clean(str(payload.get("summary") or ""))[:1200],
        source=source,
        funding=_clean(str(payload.get("funding") or "")),
        deadline=_parse_date(str(payload.get("deadline") or "") or None),
        supervisor=_clean(str(payload.get("supervisor") or "")),
    )
