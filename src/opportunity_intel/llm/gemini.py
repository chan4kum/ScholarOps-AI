"""Gemini Flash wrapper using raw httpx REST — no google.genai SDK import.

Discovery and orchestrator call this module. Agents must never import it directly.
The spec explicitly forbids importing the google.genai SDK here; all network calls
go through httpx so the package is not required at runtime.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from typing import Any

import httpx

from opportunity_intel.discovery.web_search import SearchHit

# Type alias kept for the test-injection hook (signature unchanged).
GenerateFn = Callable[..., Any]

_URL = re.compile(r"https?://[^\s)\]>\"']+")
DEFAULT_MODEL = "gemini-2.5-flash"

# REST endpoint template — key is passed as a query param, never in a header,
# because the Gemini generateContent endpoint authenticates via ?key=.
_GEMINI_REST_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"


# ---------------------------------------------------------------------------
# Chunk / response helpers (handle both object-style SDK responses from the
# test-injection hook AND dict-style REST responses from httpx).
# ---------------------------------------------------------------------------


def _chunk_uri(chunk: Any) -> str:
    # Dict-style (REST response)
    if isinstance(chunk, dict):
        web = chunk.get("web") or {}
        return str(web.get("uri") or web.get("url") or "")
    # Object-style (test-injection hook)
    web = getattr(chunk, "web", None)
    if web is None:
        return ""
    uri = getattr(web, "uri", None) or getattr(web, "url", None)
    if uri:
        return str(uri)
    if isinstance(web, dict):
        return str(web.get("uri") or web.get("url") or "")
    return ""


def _chunk_title(chunk: Any) -> str:
    # Dict-style (REST response)
    if isinstance(chunk, dict):
        web = chunk.get("web") or {}
        return str(web.get("title") or "")
    # Object-style (test-injection hook)
    web = getattr(chunk, "web", None)
    if web is None:
        return ""
    title = getattr(web, "title", None)
    if title:
        return str(title)
    if isinstance(web, dict):
        return str(web.get("title") or "")
    return ""


def _grounding_chunks_from_dict(response_dict: dict) -> list[Any]:
    """Extract grounding chunks from a raw REST JSON response dict."""
    candidates = response_dict.get("candidates") or []
    for candidate in candidates:
        meta = candidate.get("groundingMetadata") or {}
        chunks = meta.get("groundingChunks") or []
        if chunks:
            return chunks
    return []


def _text_from_dict(response_dict: dict) -> str:
    """Extract text content from a raw REST JSON response dict."""
    candidates = response_dict.get("candidates") or []
    for candidate in candidates:
        content = candidate.get("content") or {}
        parts = content.get("parts") or []
        texts = [str(p.get("text") or "") for p in parts if p.get("text")]
        if texts:
            return " ".join(texts)
    return ""


def hits_from_response(response: Any, *, limit: int) -> list[SearchHit]:
    """Parse hits from either an object-style (test hook) or dict-style (REST) response."""
    hits: list[SearchHit] = []
    seen: set[str] = set()

    # --- Dict-style REST response path ---
    if isinstance(response, dict):
        chunks = _grounding_chunks_from_dict(response)
        for chunk in chunks:
            url = _chunk_uri(chunk)
            if not url.startswith("http") or url in seen:
                continue
            seen.add(url)
            hits.append(
                SearchHit(
                    title=_chunk_title(chunk) or url,
                    url=url,
                    snippet="",
                    provider="gemini",
                )
            )
            if len(hits) >= limit:
                return hits
        text = _text_from_dict(response)
    else:
        # --- Object-style path (test-injection hook only) ---
        candidates = getattr(response, "candidates", None) or []
        for candidate in candidates:
            meta = getattr(candidate, "grounding_metadata", None)
            chunks = getattr(meta, "grounding_chunks", None) if meta is not None else None
            if not chunks and isinstance(meta, dict):
                chunks = meta.get("grounding_chunks") or []
            for chunk in chunks or []:
                url = _chunk_uri(chunk)
                if not url.startswith("http") or url in seen:
                    continue
                seen.add(url)
                hits.append(
                    SearchHit(
                        title=_chunk_title(chunk) or url,
                        url=url,
                        snippet="",
                        provider="gemini",
                    )
                )
                if len(hits) >= limit:
                    return hits
        text = getattr(response, "text", None) or ""
        if not text and candidates:
            content = getattr(candidates[0], "content", None)
            parts = getattr(content, "parts", None) or []
            text = " ".join(str(getattr(part, "text", "") or "") for part in parts)

    # Fallback: scrape URLs from the text body
    for url in _URL.findall(str(text)):
        clean = url.rstrip(".,;")
        if clean in seen or not clean.startswith("http"):
            continue
        seen.add(clean)
        hits.append(SearchHit(title=clean, url=clean, snippet=str(text)[:400], provider="gemini"))
        if len(hits) >= limit:
            break
    return hits


def generate_grounded(
    query: str,
    *,
    api_key: str,
    model: str = DEFAULT_MODEL,
    generate: GenerateFn | None = None,
) -> Any:
    """Call Gemini generateContent with Google Search grounding.

    Uses raw httpx REST — no google.genai SDK import.
    Inject ``generate`` in tests to avoid real network calls.
    """
    if generate is not None:
        # Test-injection hook: caller supplies a fake generate function.
        # Signature kept identical to the original for backwards compatibility.
        return generate(
            model=model or DEFAULT_MODEL,
            contents=query,
            config={"tools": [{"google_search": {}}]},
        )

    url = _GEMINI_REST_URL.format(model=model or DEFAULT_MODEL)
    payload = {
        "contents": [{"parts": [{"text": query}]}],
        "tools": [{"google_search": {}}],
    }
    response = httpx.post(
        url,
        params={"key": api_key},
        json=payload,
        timeout=30.0,
        headers={"Content-Type": "application/json"},
    )
    response.raise_for_status()
    # Return the parsed JSON dict — hits_from_response handles dict-style responses.
    return response.json()


def search_gemini_grounded(
    query: str,
    *,
    api_key: str,
    model: str = DEFAULT_MODEL,
    limit: int = 8,
    generate: GenerateFn | None = None,
) -> list[SearchHit]:
    """Search for PhD vacancies using Gemini grounded generation.

    Falls back to an empty list on any error so discovery continues with
    other providers (DuckDuckGo, Brave, Tavily).
    """
    if not api_key:
        return []
    prompt = (
        "Find current funded PhD / doctoral vacancy pages matching this query. "
        "Return official job URLs, not guides.\n\n"
        f"{query}"
    )
    try:
        response = generate_grounded(prompt, api_key=api_key, model=model, generate=generate)
    except Exception:  # noqa: BLE001 — discovery must fall back gracefully
        return []
    return hits_from_response(response, limit=limit)
