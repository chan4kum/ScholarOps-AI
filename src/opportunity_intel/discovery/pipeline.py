from __future__ import annotations

from urllib.parse import quote_plus

import yaml

from opportunity_intel.config import Settings
from opportunity_intel.discovery.extract import (
    extract_local,
    extract_with_groq,
    local_extract_is_thin,
)
from opportunity_intel.discovery.fetch import fetch_page
from opportunity_intel.discovery.quality import is_keepable
from opportunity_intel.discovery.sources import (
    RawListing,
    search_findaphd,
)
from opportunity_intel.discovery.web_search import (
    SearchHit,
    is_skipped_url,
    search_brave,
    search_duckduckgo,
    search_tavily,
)
from opportunity_intel.llm.models_config import AppModelConfig
from opportunity_intel.llm.router import LLMRouter


def _load_discovery_config(settings: Settings) -> dict:
    path = settings.discovery_config_path
    if not path.exists():
        return {}
    return yaml.safe_load(path.read_text()) or {}


def _search_rss(query: str, cfg: dict) -> list[RawListing]:
    """Collect from all 18 structured sources before falling back to web search.

    FindAPhD is excluded here and added separately in discover() to keep the
    original call visible. All other sources run unconditionally.
    Extra RSS feeds from discovery.yaml are appended last.
    """
    import opportunity_intel.discovery.sources as _sources

    listings: list[RawListing] = []
    seen: set[str] = set()

    def _add(items: list[RawListing]) -> None:
        for item in items:
            if item.source_url not in seen:
                listings.append(item)
                seen.add(item.source_url)

    # Iterate ALL_SOURCE_FUNCTIONS via the module reference so tests can patch individual
    # source functions and have those patches take effect here.
    for fn in _sources.ALL_SOURCE_FUNCTIONS:
        if fn.__name__ == "search_findaphd":
            continue  # added explicitly in discover() to preserve existing behaviour
        _add(getattr(_sources, fn.__name__)(query))

    # Extra RSS feeds from discovery.yaml not already covered by ALL_SOURCE_FUNCTIONS
    known_names = {fn.__name__.replace("search_", "") for fn in _sources.ALL_SOURCE_FUNCTIONS}
    for feed in cfg.get("rss_feeds") or []:
        name = feed.get("name") or "rss"
        if name in known_names:
            continue
        url = (feed.get("url") or "").replace("{query}", quote_plus(query))
        if not url:
            continue
        _add(_rss_generic(url, source=name))

    return listings


def _rss_generic(url: str, *, source: str) -> list[RawListing]:
    import feedparser

    from opportunity_intel.discovery.fetch import USER_AGENT
    from opportunity_intel.discovery.sources import _parse_deadline

    parsed = feedparser.parse(url, agent=USER_AGENT, request_headers={"User-Agent": USER_AGENT})
    listings: list[RawListing] = []
    for entry in parsed.entries[:30]:
        title = getattr(entry, "title", "").strip()
        link = getattr(entry, "link", "").strip()
        if not title or not link:
            continue
        listings.append(
            RawListing(
                title=title,
                source_url=link,
                organization=getattr(entry, "author", "") or "",
                location="",
                summary=getattr(entry, "summary", "") or "",
                source=source,
                deadline=_parse_deadline(getattr(entry, "published", None)),
            )
        )
    return listings


def _web_query(user_query: str, cfg: dict) -> str:
    extra = " ".join(cfg.get("web_search", {}).get("extra_terms") or [])
    hints = cfg.get("web_search", {}).get("site_hints") or []
    hint_q = " OR ".join(str(item) for item in hints[:8] if item)
    parts = [user_query, extra, f"({hint_q})" if hint_q else ""]
    return " ".join(part for part in parts if part).strip()


def _dedupe_hits(hits: list[SearchHit]) -> list[SearchHit]:
    seen: set[str] = set()
    unique: list[SearchHit] = []
    for hit in hits:
        key = hit.url.split("?")[0]
        if key in seen:
            continue
        seen.add(key)
        unique.append(hit)
    return unique


def _collect_search_hits(
    query: str,
    settings: Settings,
    cfg: dict,
    *,
    need: int,
) -> list[SearchHit]:
    web_q = _web_query(query, cfg)
    hits = search_duckduckgo(web_q, limit=need)
    if len(hits) < need and settings.brave_api_key:
        hits.extend(search_brave(web_q, settings.brave_api_key, limit=need))
    if len(hits) < need and settings.tavily_api_key:
        hits.extend(search_tavily(web_q, settings.tavily_api_key, limit=min(need, 8)))
    if len(hits) < need and settings.gemini_api_key and not settings.offline:
        from opportunity_intel.llm.gemini import search_gemini_grounded

        hits.extend(
            search_gemini_grounded(
                web_q,
                api_key=settings.gemini_api_key,
                model=settings.gemini_model,
                limit=min(need, 8),
            )
        )
    extra_hosts = tuple(str(item) for item in (cfg.get("skip_domains") or []) if item)
    filtered = [hit for hit in hits if not is_skipped_url(hit.url, extra_hosts=extra_hosts)]
    return _dedupe_hits(filtered)[: settings.discovery_fetch_limit]


def _listing_from_hit(
    hit: SearchHit,
    settings: Settings,
    router: LLMRouter | None,
) -> RawListing | None:
    page = fetch_page(hit.url, use_playwright=settings.use_playwright)
    html = page.html if page else ""
    url = page.url if page else hit.url
    listing = extract_local(url, html, source=hit.provider) if html else None
    if listing is None:
        blob = f"{hit.title} {hit.snippet}".lower()
        if "phd" not in blob and "doctoral" not in blob:
            return None
        listing = RawListing(
            title=hit.title or url,
            source_url=url,
            organization="",
            location="",
            summary=hit.snippet[:800],
            source=hit.provider,
        )
    if local_extract_is_thin(listing) and router is not None and html:
        groq_listing = extract_with_groq(router, url, html, source=hit.provider)
        if groq_listing is not None:
            return groq_listing
    return listing


def discover(
    query: str,
    settings: Settings,
    model_config: AppModelConfig,
) -> list[RawListing]:
    """RSS first, then cheap search, fetch, local extract, Groq only if thin."""
    cfg = _load_discovery_config(settings)
    combined: list[RawListing] = []
    seen: set[str] = set()

    # All six structured sources + FindAPhD HTML
    rss = _search_rss(query, cfg) + search_findaphd(query)
    for listing in rss:
        if listing.source_url in seen:
            continue
        if not is_keepable(
            listing,
            allowed=model_config.target_countries,
            excluded=model_config.excluded_countries,
        ):
            continue
        seen.add(listing.source_url)
        combined.append(listing)

    if len(combined) >= settings.discovery_min_results:
        return combined

    router = None
    if settings.groq_api_key and not settings.offline:
        router = LLMRouter(settings, model_config)

    need = max(settings.discovery_min_results - len(combined), 4)
    for hit in _collect_search_hits(query, settings, cfg, need=need):
        if hit.url in seen:
            continue
        listing = _listing_from_hit(hit, settings, router)
        if listing is None or listing.source_url in seen:
            continue
        if not is_keepable(
            listing,
            allowed=model_config.target_countries,
            excluded=model_config.excluded_countries,
        ):
            continue
        seen.add(listing.source_url)
        combined.append(listing)
    return combined
