from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import parse_qs, unquote, urlparse

import httpx
from selectolax.parser import HTMLParser

from opportunity_intel.discovery.fetch import USER_AGENT


@dataclass(frozen=True)
class SearchHit:
    title: str
    url: str
    snippet: str
    provider: str


SKIP_HOST_FRAGMENTS = (
    "linkedin.com",
    "facebook.com",
    "twitter.com",
    "x.com",
    "youtube.com",
    "pinterest.com",
    "instagram.com",
)


def unwrap_url(url: str) -> str:
    if "duckduckgo.com/l/?" in url:
        query = parse_qs(urlparse(url).query)
        uddg = query.get("uddg", [""])[0]
        if uddg:
            return unquote(uddg)
    return url


def is_skipped_url(url: str, extra_hosts: tuple[str, ...] = ()) -> bool:
    host = (urlparse(url).hostname or "").lower()
    return any(fragment in host for fragment in SKIP_HOST_FRAGMENTS + extra_hosts)


def search_duckduckgo(query: str, *, limit: int = 10) -> list[SearchHit]:
    """Free HTML search. No API key."""
    try:
        response = httpx.post(
            "https://html.duckduckgo.com/html/",
            data={"q": query},
            timeout=20.0,
            headers={"User-Agent": USER_AGENT},
            follow_redirects=True,
        )
        response.raise_for_status()
    except httpx.HTTPError:
        return []

    tree = HTMLParser(response.text)
    hits: list[SearchHit] = []
    for result in tree.css("div.result, div.web-result"):
        link = result.css_first("a.result__a")
        if link is None:
            continue
        href = unwrap_url((link.attributes.get("href") or "").strip())
        title = (link.text() or "").strip()
        snippet_el = result.css_first("a.result__snippet, div.result__snippet")
        snippet = (snippet_el.text() if snippet_el else "") or ""
        if not href.startswith("http") or is_skipped_url(href):
            continue
        hits.append(
            SearchHit(
                title=title,
                url=href,
                snippet=snippet.strip(),
                provider="duckduckgo",
            )
        )
        if len(hits) >= limit:
            break
    return hits


def search_brave(query: str, api_key: str, *, limit: int = 10) -> list[SearchHit]:
    if not api_key:
        return []
    try:
        response = httpx.get(
            "https://api.search.brave.com/res/v1/web/search",
            params={"q": query, "count": min(limit, 20)},
            headers={
                "Accept": "application/json",
                "X-Subscription-Token": api_key,
            },
            timeout=20.0,
        )
        response.raise_for_status()
    except httpx.HTTPError:
        return []
    data = response.json()
    hits: list[SearchHit] = []
    for item in (data.get("web") or {}).get("results") or []:
        url = (item.get("url") or "").strip()
        if not url or is_skipped_url(url):
            continue
        hits.append(
            SearchHit(
                title=item.get("title") or "",
                url=url,
                snippet=item.get("description") or "",
                provider="brave",
            )
        )
        if len(hits) >= limit:
            break
    return hits


def search_tavily(query: str, api_key: str, *, limit: int = 8) -> list[SearchHit]:
    """Paid last resort. Only called when RSS + free search are thin."""
    if not api_key:
        return []
    try:
        response = httpx.post(
            "https://api.tavily.com/search",
            json={
                "api_key": api_key,
                "query": query,
                "search_depth": "basic",
                "max_results": min(limit, 10),
                "include_answer": False,
            },
            timeout=25.0,
        )
        response.raise_for_status()
    except httpx.HTTPError:
        return []
    hits: list[SearchHit] = []
    for item in response.json().get("results") or []:
        url = (item.get("url") or "").strip()
        if not url or is_skipped_url(url):
            continue
        hits.append(
            SearchHit(
                title=item.get("title") or "",
                url=url,
                snippet=item.get("content") or "",
                provider="tavily",
            )
        )
        if len(hits) >= limit:
            break
    return hits
