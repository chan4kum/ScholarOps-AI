"""Query Enhancer, HyDE Generator, and Multi-Perspective Query Expander for ScholarOps AI.

Transforms raw user queries or vacancy summaries into rich multi-facet search queries
and hypothetical document embeddings (HyDE) for maximized retrieval recall.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from opportunity_intel.config import Settings
from opportunity_intel.llm.json_repair import parse_llm_json
from opportunity_intel.llm.router import LLMRouter

logger = logging.getLogger("opportunity_intel.rag.query_enhancer")


@dataclass
class EnhancedQuery:
    original_query: str
    expanded_keywords: list[str] = field(default_factory=list)
    sub_queries: list[str] = field(default_factory=list)
    hyde_passage: str = ""
    domain_tags: list[str] = field(default_factory=list)


class QueryEnhancer:
    """Uses LLM to perform query expansion, HyDE generation, and sub-query decomposition."""

    def __init__(self, settings: Settings, router: LLMRouter) -> None:
        self.settings = settings
        self.router = router

    def enhance(self, query: str) -> EnhancedQuery:
        """Expand and enhance the user query into multi-facet search representations."""
        if not query.strip():
            return EnhancedQuery(original_query=query)

        prompt = (
            "You are a doctoral research search optimizer. "
            f"Analyze the following PhD research query:\n\n"
            f"QUERY: {query}\n\n"
            "Generate:\n"
            "1. 'expanded_keywords': list of 4-6 technical and methodology keywords.\n"
            "2. 'sub_queries': list of 3 distinct search variations.\n"
            "3. 'hyde_passage': A hypothetical paragraph matching an ideal PhD profile.\n"
            "4. 'domain_tags': 2-4 broad academic field tags.\n\n"
            "Respond strictly in valid JSON format:\n"
            "{\n"
            '  "expanded_keywords": ["..."],\n'
            '  "sub_queries": ["..."],\n'
            '  "hyde_passage": "...",\n'
            '  "domain_tags": ["..."]\n'
            "}"
        )

        messages = [
            {
                "role": "system",
                "content": "You are a specialized query enhancement assistant. Output JSON.",
            },
            {"role": "user", "content": prompt},
        ]

        try:
            res = self.router.complete("reason", messages, json_mode=True)
            data = parse_llm_json(res.text)
            if isinstance(data, dict):
                return EnhancedQuery(
                    original_query=query,
                    expanded_keywords=list(data.get("expanded_keywords") or []),
                    sub_queries=list(data.get("sub_queries") or []),
                    hyde_passage=str(data.get("hyde_passage") or ""),
                    domain_tags=list(data.get("domain_tags") or []),
                )
        except Exception as exc:
            logger.warning("Query enhancement failed, using raw query: %s", exc)

        return EnhancedQuery(
            original_query=query,
            expanded_keywords=query.split()[:6],
            sub_queries=[query],
            hyde_passage="",
            domain_tags=[],
        )
