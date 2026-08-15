"""Semantic Caching Layer for ScholarOps AI RAG System.

Caches query embeddings and generation responses. When semantically equivalent
queries are submitted (cosine similarity >= threshold), returns cached results
to eliminate redundant LLM calls and reduce latency from seconds to <50ms.
"""

from __future__ import annotations

import logging
import math
import time
from dataclasses import dataclass, field
from typing import Any

from opportunity_intel.config import Settings
from opportunity_intel.llm.router import LLMRouter

logger = logging.getLogger("opportunity_intel.rag.semantic_cache")


@dataclass
class CacheEntry:
    query: str
    embedding: list[float]
    response_text: str
    metadata: dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)
    hit_count: int = 0


@dataclass
class CacheLookupResult:
    hit: bool
    query: str
    response_text: str = ""
    similarity: float = 0.0
    matched_cached_query: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    latency_ms: float = 0.0


def _cosine_similarity(vec_a: list[float], vec_b: list[float]) -> float:
    """Computes cosine similarity between two float vectors."""
    if not vec_a or not vec_b or len(vec_a) != len(vec_b):
        return 0.0
    dot = sum(a * b for a, b in zip(vec_a, vec_b, strict=False))
    norm_a = math.sqrt(sum(a * a for a in vec_a))
    norm_b = math.sqrt(sum(b * b for b in vec_b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return max(0.0, min(1.0, dot / (norm_a * norm_b)))


class SemanticCache:
    """In-memory & vector-based semantic cache with configurable similarity threshold."""

    def __init__(
        self,
        settings: Settings,
        router: LLMRouter | None = None,
        *,
        similarity_threshold: float = 0.90,
        max_entries: int = 500,
    ) -> None:
        self.settings = settings
        self.router = router
        self.similarity_threshold = similarity_threshold
        self.max_entries = max_entries
        self._entries: list[CacheEntry] = []

    def get(self, query: str) -> CacheLookupResult:
        """Looks up semantically matching query in the cache."""
        start_time = time.perf_counter()
        if not query.strip() or not self._entries:
            return CacheLookupResult(hit=False, query=query, latency_ms=0.0)

        query_emb = self._embed_query(query)
        if not query_emb:
            return CacheLookupResult(hit=False, query=query, latency_ms=0.0)

        best_score = -1.0
        best_entry: CacheEntry | None = None

        for entry in self._entries:
            sim = _cosine_similarity(query_emb, entry.embedding)
            if sim > best_score:
                best_score = sim
                best_entry = entry

        latency_ms = (time.perf_counter() - start_time) * 1000.0

        if best_entry and best_score >= self.similarity_threshold:
            best_entry.hit_count += 1
            logger.info(
                "Semantic Cache HIT: '%.40s' matches '%.40s' (sim=%.3f)",
                query,
                best_entry.query,
                best_score,
            )
            return CacheLookupResult(
                hit=True,
                query=query,
                response_text=best_entry.response_text,
                similarity=round(best_score, 4),
                matched_cached_query=best_entry.query,
                metadata=best_entry.metadata,
                latency_ms=round(latency_ms, 2),
            )

        return CacheLookupResult(
            hit=False,
            query=query,
            similarity=round(max(0.0, best_score), 4),
            latency_ms=round(latency_ms, 2),
        )

    def put(
        self,
        query: str,
        response_text: str,
        *,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Stores a new query-response pair into the semantic cache."""
        if not query.strip() or not response_text.strip():
            return

        query_emb = self._embed_query(query)
        if not query_emb:
            return

        # Evict oldest entry if exceeding max_entries
        if len(self._entries) >= self.max_entries:
            self._entries.pop(0)

        entry = CacheEntry(
            query=query.strip(),
            embedding=query_emb,
            response_text=response_text.strip(),
            metadata=dict(metadata or {}),
        )
        self._entries.append(entry)
        logger.debug("Stored query in semantic cache: '%.40s'", query)

    def stats(self) -> dict[str, Any]:
        """Returns statistics about the semantic cache state."""
        total_hits = sum(e.hit_count for e in self._entries)
        return {
            "total_entries": len(self._entries),
            "max_entries": self.max_entries,
            "similarity_threshold": self.similarity_threshold,
            "total_hits": total_hits,
        }

    def clear(self) -> None:
        """Clears all cached entries."""
        self._entries.clear()

    def _embed_query(self, query: str) -> list[float]:
        """Embeds single query string into a normalized float vector."""
        if self.router:
            vectors = self.router.embed([query])
            if vectors and len(vectors) > 0:
                return vectors[0]

        # Fallback deterministic hash-trick vector
        dim = 256
        vec = [0.0] * dim
        for i, word in enumerate(query.lower().split()):
            h = hash(word) % dim
            vec[h] += 1.0 / (i + 1.0)
        norm = math.sqrt(sum(x * x for x in vec)) or 1.0
        return [x / norm for x in vec]
