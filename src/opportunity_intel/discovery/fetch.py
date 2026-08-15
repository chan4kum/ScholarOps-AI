from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlparse

import httpx

USER_AGENT = "OpportunityIntel/0.1 (personal research; local-first)"

_BLOCKED_HOSTS = {"localhost", "127.0.0.1", "::1", "0.0.0.0"}


def is_fetchable_url(url: str) -> bool:
    """Discovery may only fetch public http(s) pages, not local or file URLs."""
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        return False
    host = (parsed.hostname or "").lower()
    if not host or host in _BLOCKED_HOSTS:
        return False
    return True


@dataclass
class FetchedPage:
    url: str
    html: str
    status_code: int
    via: str


def fetch_httpx(url: str, *, timeout: float = 20.0) -> FetchedPage | None:
    if not is_fetchable_url(url):
        return None
    try:
        response = httpx.get(
            url,
            timeout=timeout,
            headers={"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml"},
            follow_redirects=True,
        )
        if response.status_code >= 400:
            return None
        content_type = response.headers.get("content-type", "")
        if "html" not in content_type and "xml" not in content_type and "text" not in content_type:
            return None
        return FetchedPage(
            url=str(response.url),
            html=response.text,
            status_code=response.status_code,
            via="httpx",
        )
    except httpx.HTTPError:
        return None


def fetch_playwright(url: str, *, timeout_ms: int = 20000) -> FetchedPage | None:
    if not is_fetchable_url(url):
        return None
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return None
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(user_agent=USER_AGENT)
            page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
            html = page.content()
            final_url = page.url
            browser.close()
        return FetchedPage(url=final_url, html=html, status_code=200, via="playwright")
    except Exception:  # noqa: BLE001
        return None


def fetch_page(url: str, *, use_playwright: bool = False) -> FetchedPage | None:
    page = fetch_httpx(url)
    if page and len(page.html) > 400:
        return page
    if use_playwright:
        return fetch_playwright(url)
    return page
