"""Advanced RAG layer: ChromaDB Vector Store, BM25 + Dense Hybrid Search,
LLM Cross-Encoder Reranker, Query Enhancer, Academic Knowledge Graph,
and LLM-as-a-Judge Self-Improving RAG.
"""

from opportunity_intel.rag.chunker import SemanticChunk, StructureAwareChunker
from opportunity_intel.rag.hybrid_search import HybridSearchEngine, SearchResult
from opportunity_intel.rag.knowledge_graph import AcademicKnowledgeGraph
from opportunity_intel.rag.query_enhancer import EnhancedQuery, QueryEnhancer
from opportunity_intel.rag.reranker import LLMReranker, RerankedResult
from opportunity_intel.rag.self_improving_rag import (
    JudgeEvaluation,
    SelfImprovingRAGEngine,
    SelfImprovingRAGResult,
)
from opportunity_intel.rag.semantic_cache import CacheLookupResult, SemanticCache
from opportunity_intel.rag.vector_store import ChromaVectorStore, sync_all_to_vector_store

__all__ = [
    "AcademicKnowledgeGraph",
    "CacheLookupResult",
    "ChromaVectorStore",
    "EnhancedQuery",
    "HybridSearchEngine",
    "JudgeEvaluation",
    "LLMReranker",
    "QueryEnhancer",
    "RerankedResult",
    "SearchResult",
    "SemanticCache",
    "SemanticChunk",
    "SelfImprovingRAGEngine",
    "SelfImprovingRAGResult",
    "StructureAwareChunker",
    "sync_all_to_vector_store",
]
