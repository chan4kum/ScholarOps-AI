"""Hybrid Search Engine combining Dense Semantic Vectors + BM25 Sparse Lexical Search.

Applies Reciprocal Rank Fusion (RRF) to merge and calibrate retrieval rankings
across both semantic intent and exact academic keyword matches.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from rank_bm25 import BM25Okapi

from opportunity_intel.config import Settings
from opportunity_intel.llm.router import LLMRouter
from opportunity_intel.rag.vector_store import ChromaVectorStore


@dataclass
class SearchResult:
    id: str
    text: str
    metadata: dict[str, Any]
    dense_score: float
    sparse_score: float
    rrf_score: float
    source_collection: str


def _tokenize(text: str) -> list[str]:
    """Tokenize text into lowercase alphanumeric tokens for BM25."""
    return re.findall(r"\b\w+\b", text.lower())


class HybridSearchEngine:
    """Combines ChromaDB dense retrieval with BM25 lexical scoring using RRF."""

    def __init__(self, settings: Settings, *, router: LLMRouter | None = None) -> None:
        self.settings = settings
        self.router = router
        self.vector_store = ChromaVectorStore(settings, router=router)

    def _build_bm25_index(
        self, collection_name: str
    ) -> tuple[BM25Okapi | None, list[dict[str, Any]]]:
        """Fetch all documents from Chroma collection to build in-memory BM25 index."""
        col = self.vector_store._get_collection(collection_name)
        total = col.count()
        if total == 0:
            return None, []

        data = col.get(include=["documents", "metadatas"])
        docs = []
        tokenized_corpus = []
        for doc_id, doc_text, meta in zip(data["ids"], data["documents"], data["metadatas"]):
            docs.append({"id": doc_id, "text": doc_text, "metadata": meta})
            tokenized_corpus.append(_tokenize(doc_text))

        if not tokenized_corpus:
            return None, []

        bm25 = BM25Okapi(tokenized_corpus)
        return bm25, docs

    def hybrid_search(
        self,
        collection_name: str,
        query: str,
        *,
        limit: int = 6,
        dense_weight: float = 0.6,
        sparse_weight: float = 0.4,
        rrf_k: int = 60,
        where: dict[str, Any] | None = None,
    ) -> list[SearchResult]:
        """Execute hybrid search using Reciprocal Rank Fusion."""
        if not query.strip():
            return []

        # 1. Dense Semantic Search via ChromaDB
        dense_hits = self.vector_store.search(collection_name, query, limit=limit * 2, where=where)
        dense_ranks: dict[str, int] = {hit["id"]: idx for idx, hit in enumerate(dense_hits)}
        doc_pool: dict[str, dict[str, Any]] = {
            hit["id"]: {
                "text": hit["text"],
                "metadata": hit["metadata"],
                "dense_sim": hit["similarity"],
            }
            for hit in dense_hits
        }

        # 2. Sparse Lexical Search via BM25
        bm25, corpus = self._build_bm25_index(collection_name)
        sparse_ranks: dict[str, int] = {}
        if bm25 and corpus:
            tokens = _tokenize(query)
            if tokens:
                scores = bm25.get_scores(tokens)
                top_indices = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[
                    : limit * 2
                ]
                for rank, idx in enumerate(top_indices):
                    if scores[idx] > 0:
                        doc = corpus[idx]
                        doc_id = doc["id"]
                        sparse_ranks[doc_id] = rank
                        if doc_id not in doc_pool:
                            doc_pool[doc_id] = {
                                "text": doc["text"],
                                "metadata": doc["metadata"],
                                "dense_sim": 0.0,
                            }

        # 3. Reciprocal Rank Fusion (RRF)
        scored_results: list[SearchResult] = []
        for doc_id, data in doc_pool.items():
            d_rank = dense_ranks.get(doc_id)
            s_rank = sparse_ranks.get(doc_id)

            d_score = dense_weight / (rrf_k + d_rank) if d_rank is not None else 0.0
            s_score = sparse_weight / (rrf_k + s_rank) if s_rank is not None else 0.0
            rrf = d_score + s_score

            scored_results.append(
                SearchResult(
                    id=doc_id,
                    text=data["text"],
                    metadata=data["metadata"],
                    dense_score=data["dense_sim"],
                    sparse_score=float(s_score * 1000),
                    rrf_score=round(rrf * 1000, 3),
                    source_collection=collection_name,
                )
            )

        scored_results.sort(key=lambda x: x.rrf_score, reverse=True)
        return scored_results[:limit]
