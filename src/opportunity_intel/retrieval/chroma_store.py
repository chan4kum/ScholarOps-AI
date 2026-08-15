"""Deprecated: RAG lives in opportunity_intel.rag.faiss_store (local, no cloud)."""

from opportunity_intel.rag.faiss_store import query_similar, upsert_corpus

upsert_evidence = upsert_corpus

__all__ = ["query_similar", "upsert_corpus", "upsert_evidence"]
