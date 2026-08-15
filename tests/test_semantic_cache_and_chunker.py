"""Unit tests for Semantic Caching and Structure-Aware Chunking."""

from __future__ import annotations

from pathlib import Path

from opportunity_intel.config import Settings
from opportunity_intel.rag.chunker import StructureAwareChunker
from opportunity_intel.rag.semantic_cache import SemanticCache


def test_structure_aware_chunker_markdown_sections() -> None:
    doc_text = (
        "# Curriculum Vitae\n\n"
        "Chandan Kumar is an AI Architect and Researcher.\n\n"
        "## Research Interests\n\n"
        "My research focuses on Trustworthy AI and safe agentic workflows.\n"
        "I explore how ensemble models behave under distribution shifts.\n\n"
        "## Industry Experience\n\n"
        "Lead Architect at EY and Deloitte delivering AI pipelines.\n"
        "Software Engineer 3 at Boeing building predictive maintenance telemetry."
    )

    chunker = StructureAwareChunker(max_chunk_size=300, min_chunk_size=50, overlap_size=50)
    chunks = chunker.chunk_document(doc_id="doc-42", text=doc_text)

    assert len(chunks) >= 2
    section_titles = [c.section_title for c in chunks]
    assert any("Research Interests" in t for t in section_titles)
    assert any("Industry Experience" in t for t in section_titles)
    assert all("doc_id" in c.metadata for c in chunks)


def test_semantic_cache_hit_and_eviction(tmp_path: Path) -> None:
    settings = Settings(chroma_dir=tmp_path / "chroma")
    cache = SemanticCache(settings, similarity_threshold=0.85, max_entries=3)

    # 1. Test empty cache
    res = cache.get("What is your research background?")
    assert not res.hit

    # 2. Put query and response
    cache.put(
        "What is your research background?",
        "I specialize in Trustworthy AI and agentic systems at the University of Hertfordshire.",
        metadata={"category": "profile"},
    )

    # 3. Exact query match
    res_exact = cache.get("What is your research background?")
    assert res_exact.hit
    assert "Trustworthy AI" in res_exact.response_text
    assert res_exact.similarity >= 0.99

    # 4. Semantically close query match
    res_similar = cache.get("What is your research background and experience?")
    assert res_similar.hit
    assert res_similar.similarity >= 0.85

    # 5. Completely different query (miss)
    res_diff = cache.get("Quantum chemistry molecular simulations in Gaussian 16")
    assert not res_diff.hit

    # 6. Test statistics
    stats = cache.stats()
    assert stats["total_entries"] == 1
    assert stats["total_hits"] >= 2
