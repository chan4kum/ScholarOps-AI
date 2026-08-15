"""Tests for Advanced RAG: ChromaDB, BM25, Reranker, Knowledge Graph, and LangGraph."""

from __future__ import annotations

from pathlib import Path

from opportunity_intel.config import ROOT, Settings
from opportunity_intel.domain.models import EvidenceItem, Opportunity, UserProfile
from opportunity_intel.llm.models_config import load_model_config
from opportunity_intel.llm.router import LLMRouter
from opportunity_intel.rag.hybrid_search import HybridSearchEngine
from opportunity_intel.rag.knowledge_graph import AcademicKnowledgeGraph
from opportunity_intel.rag.query_enhancer import QueryEnhancer
from opportunity_intel.rag.vector_store import (
    ChromaVectorStore,
    VectorDocument,
)


def test_chroma_vector_store_crud(tmp_path: Path) -> None:
    settings = Settings(chroma_dir=tmp_path / "chroma")
    store = ChromaVectorStore(settings)

    docs = [
        VectorDocument(
            id="EV-1",
            text="Published research in NeurIPS on distributed reinforcement learning and safety.",
            metadata={"category": "publication", "type": "evidence"},
        ),
        VectorDocument(
            id="EV-2",
            text="Developed industrial IoT telemetry pipelines for Boeing aerospace engines.",
            metadata={"category": "industry", "type": "evidence"},
        ),
    ]

    indexed = store.index_documents(ChromaVectorStore.COLLECTION_EVIDENCE, docs)
    assert indexed == 2
    assert store.count(ChromaVectorStore.COLLECTION_EVIDENCE) == 2

    hits = store.search(
        ChromaVectorStore.COLLECTION_EVIDENCE, "reinforcement learning safety", limit=1
    )
    assert len(hits) == 1
    assert hits[0]["id"] == "EV-1"
    assert hits[0]["similarity"] > 0


def test_hybrid_search_rrf(tmp_path: Path) -> None:
    settings = Settings(chroma_dir=tmp_path / "chroma")
    store = ChromaVectorStore(settings)

    docs = [
        VectorDocument(
            id="doc-1", text="Machine learning with PyTorch and neural networks.", metadata={}
        ),
        VectorDocument(id="doc-2", text="Quantum computing simulation using Qiskit.", metadata={}),
    ]
    store.index_documents(ChromaVectorStore.COLLECTION_DOSSIER, docs)

    engine = HybridSearchEngine(settings)
    results = engine.hybrid_search(
        ChromaVectorStore.COLLECTION_DOSSIER, "PyTorch machine learning", limit=2
    )
    assert len(results) > 0
    assert results[0].id == "doc-1"
    assert results[0].rrf_score > 0


def test_academic_knowledge_graph(tmp_path: Path) -> None:
    db_path = tmp_path / "test.db"
    settings = Settings(
        database_url=f"sqlite:///{db_path}",
        kg_path=tmp_path / "academic_kg.json",
        chroma_dir=tmp_path / "chroma",
    )
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session

    from opportunity_intel.domain.models import Base

    engine = create_engine(f"sqlite:///{db_path}")
    Base.metadata.create_all(engine)
    session = Session(engine)

    profile = UserProfile(
        full_name="Chandan Kumar",
        highest_degree="MSc Data Science",
        research_interests="Trustworthy AI, Agentic Systems",
        skills="PyTorch, LangGraph, Airflow",
    )
    ev = EvidenceItem(content="Authored MSc Thesis on AI Safety", category="thesis")
    opp = Opportunity(
        title="PhD in Agentic AI",
        organization="TU Delft",
        supervisor="Prof. Smith",
        funding="fully funded",
        source_url=f"https://tudelft.nl/phd/agentic-ai-{tmp_path.name}",
    )
    session.add_all([profile, ev, opp])
    session.commit()

    kg = AcademicKnowledgeGraph(settings)
    stats = kg.build_from_database(session)
    assert stats["nodes"] > 0
    assert stats["edges"] > 0
    assert kg.graph.has_node("candidate:me")

    context = kg.get_related_subgraph_context(opp.id)
    assert len(context) > 0


def test_query_enhancer_fallback(tmp_path: Path) -> None:
    settings = Settings(chroma_dir=tmp_path / "chroma")
    cfg = load_model_config(ROOT / "config" / "models.yaml")
    router = LLMRouter(settings, cfg)

    enhancer = QueryEnhancer(settings, router)
    enhanced = enhancer.enhance("Autonomous Agent Verification")
    assert enhanced.original_query == "Autonomous Agent Verification"
    assert len(enhanced.expanded_keywords) > 0
