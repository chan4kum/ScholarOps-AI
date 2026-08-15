"""Professor paper lookup via OpenAlex. No LLM."""

from __future__ import annotations

from dataclasses import dataclass

import httpx

from opportunity_intel.discovery.fetch import USER_AGENT, is_fetchable_url

OPENALEX = "https://api.openalex.org/works"


@dataclass
class PaperHit:
    title: str
    year: int | None
    authors: str
    venue: str
    url: str


def search_professor_papers(
    supervisor: str,
    organization: str = "",
    *,
    timeout: float = 15.0,
    client: httpx.Client | None = None,
) -> list[PaperHit]:
    name = (supervisor or "").strip()
    if not name or name.lower() in {"unknown", "n/a", "-"}:
        return []
    query = " ".join(part for part in (name, organization) if part).strip()
    params = {"search": query, "per_page": 5, "sort": "cited_by_count:desc"}
    headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    try:
        if client is not None:
            response = client.get(OPENALEX, params=params, headers=headers, timeout=timeout)
        else:
            response = httpx.get(OPENALEX, params=params, headers=headers, timeout=timeout)
        if response.status_code >= 400:
            return []
        payload = response.json()
    except (httpx.HTTPError, ValueError):
        return []
    results = payload.get("results") if isinstance(payload, dict) else None
    if not isinstance(results, list):
        return []
    hits: list[PaperHit] = []
    for item in results[:5]:
        if not isinstance(item, dict):
            continue
        title = str(item.get("display_name") or "").strip()
        if not title:
            continue
        year_raw = item.get("publication_year")
        year = int(year_raw) if isinstance(year_raw, int) else None
        authors = _author_line(item)
        venue = ""
        loc = item.get("primary_location") or {}
        if isinstance(loc, dict):
            source = loc.get("source") or {}
            if isinstance(source, dict):
                venue = str(source.get("display_name") or "")[:400]
        url = str(item.get("id") or "")
        landing = ""
        if isinstance(loc, dict):
            landing = str(loc.get("landing_page_url") or "")
        chosen = landing or url
        if (
            chosen
            and not is_fetchable_url(chosen)
            and not chosen.startswith("https://openalex.org")
        ):
            chosen = url if str(url).startswith("https://") else ""
        hits.append(
            PaperHit(
                title=title[:800],
                year=year,
                authors=authors[:500],
                venue=venue,
                url=chosen[:1000],
            )
        )
    return hits


def _author_line(item: dict) -> str:
    authorships = item.get("authorships") or []
    names: list[str] = []
    if isinstance(authorships, list):
        for row in authorships[:4]:
            if not isinstance(row, dict):
                continue
            author = row.get("author") or {}
            if isinstance(author, dict):
                display = str(author.get("display_name") or "").strip()
                if display:
                    names.append(display)
    return ", ".join(names)
