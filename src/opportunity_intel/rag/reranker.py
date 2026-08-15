"""Cross-Encoder & LLM Reranker for ScholarOps AI.

Scores candidate retrieved chunks using LLM reasoning to evaluate nuanced semantic
and contextual fit for academic applications.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from opportunity_intel.config import Settings
from opportunity_intel.llm.json_repair import parse_llm_json
from opportunity_intel.llm.router import LLMRouter
from opportunity_intel.rag.hybrid_search import SearchResult

logger = logging.getLogger("opportunity_intel.rag.reranker")


@dataclass
class RerankedResult:
    id: str
    text: str
    metadata: dict[str, Any]
    initial_score: float
    rerank_score: float
    relevance_rationale: str
    source_collection: str


class LLMReranker:
    """Uses LLMRouter (Gemini/DeepSeek) to score query-document relevance."""

    def __init__(self, settings: Settings, router: LLMRouter) -> None:
        self.settings = settings
        self.router = router

    def rerank(
        self,
        query: str,
        candidates: list[SearchResult],
        *,
        top_n: int = 5,
    ) -> list[RerankedResult]:
        """Rerank retrieved chunks by passing them through LLM evaluation."""
        if not candidates:
            return []
        if len(candidates) <= 1:
            return [
                RerankedResult(
                    id=c.id,
                    text=c.text,
                    metadata=c.metadata,
                    initial_score=c.rrf_score,
                    rerank_score=100.0,
                    relevance_rationale="Sole candidate",
                    source_collection=c.source_collection,
                )
                for c in candidates
            ]

        doc_blocks = []
        for idx, item in enumerate(candidates):
            preview = item.text[:500].replace("\n", " ")
            doc_blocks.append(f"[{idx}] (ID: {item.id}): {preview}")

        prompt = (
            "You are an expert academic admissions evaluator. "
            "Re-rank the following retrieved context passages for relevance:\n\n"
            f"TARGET QUERY / TOPIC: {query}\n\n"
            f"CANDIDATE PASSAGES:\n" + "\n".join(doc_blocks) + "\n\n"
            "Score each passage from 0 to 100 on how directly it supports the query.\n"
            "Respond strictly in valid JSON with an array of objects:\n"
            "[\n"
            "  {\n"
            '    "index": 0,\n'
            '    "score": 92.5,\n'
            '    "rationale": "Directly explains methodology in distributed PyTorch"\n'
            "  }\n"
            "]"
        )

        messages = [
            {
                "role": "system",
                "content": "You are a precise academic reranker. Output strictly JSON.",
            },
            {"role": "user", "content": prompt},
        ]

        try:
            res = self.router.complete("reason", messages, json_mode=True)
            parsed = parse_llm_json(res.text)
            scores_map: dict[int, tuple[float, str]] = {}
            items = parsed if isinstance(parsed, list) else parsed.get("scores", [])
            for entry in items:
                idx = int(entry.get("index", -1))
                score = float(entry.get("score", 50.0))
                rationale = str(entry.get("rationale", ""))
                if 0 <= idx < len(candidates):
                    scores_map[idx] = (score, rationale)
        except Exception as exc:
            logger.warning("LLM reranking failed, falling back to initial RRF score: %s", exc)
            scores_map = {}

        reranked: list[RerankedResult] = []
        for idx, item in enumerate(candidates):
            if idx in scores_map:
                r_score, r_rationale = scores_map[idx]
            else:
                r_score = min(item.rrf_score * 5.0, 100.0)
                r_rationale = "Initial RRF score"

            reranked.append(
                RerankedResult(
                    id=item.id,
                    text=item.text,
                    metadata=item.metadata,
                    initial_score=item.rrf_score,
                    rerank_score=round(r_score, 1),
                    relevance_rationale=r_rationale,
                    source_collection=item.source_collection,
                )
            )

        reranked.sort(key=lambda x: x.rerank_score, reverse=True)
        return reranked[:top_n]
