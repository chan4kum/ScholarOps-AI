"""ChromaDB-powered persistent Vector Database for ScholarOps AI.

Replaces basic FAISS with a full-featured, embedded ChromaDB store supporting:
  - Persistent disk storage under data/chroma/
  - Structured metadata indexing & filtering (doc_type, category, country, tags)
  - Dense cosine similarity matching with BGE-small (384-dim) or Gemini embeddings
  - Exact atomic evidence mapping (EV-<id>)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import chromadb
from chromadb.config import Settings as ChromaSettings
from sqlalchemy.orm import Session

from opportunity_intel.config import Settings
from opportunity_intel.domain.models import (
    EvidenceItem,
    Opportunity,
    ProfessorPaper,
    UploadedDocument,
)

if TYPE_CHECKING:
    from opportunity_intel.llm.router import LLMRouter

logger = logging.getLogger("opportunity_intel.rag.vector_store")


@dataclass
class VectorDocument:
    id: str
    text: str
    metadata: dict[str, Any]
    vector: list[float] | None = None


class ChromaVectorStore:
    """Persistent local vector database using ChromaDB."""

    COLLECTION_DOSSIER = "applicant_dossier"
    COLLECTION_EVIDENCE = "evidence_items"
    COLLECTION_OPPORTUNITIES = "opportunities"
    COLLECTION_PAPERS = "professor_papers"

    def __init__(self, settings: Settings, *, router: LLMRouter | None = None) -> None:
        self.settings = settings
        self.router = router
        self.chroma_dir = settings.chroma_dir
        self.chroma_dir.mkdir(parents=True, exist_ok=True)
        self.client = chromadb.PersistentClient(
            path=str(self.chroma_dir),
            settings=ChromaSettings(anonymized_telemetry=False),
        )

    def _get_collection(self, name: str) -> chromadb.Collection:
        return self.client.get_or_create_collection(
            name=name,
            metadata={"hnsw:space": "cosine"},
        )

    def _embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        if self.router is not None:
            try:
                return self.router.embed(texts)
            except Exception as exc:
                logger.warning("Router embed failed, using fallback: %s", exc)

        # Fallback 384-dim pseudo-embedding if router is absent
        import hashlib
        import math

        results = []
        for t in texts:
            vec = [0.0] * 384
            for token in t.lower().split():
                idx = int(hashlib.md5(token.encode()).hexdigest(), 16) % 384
                vec[idx] += 1.0
            norm = math.sqrt(sum(x * x for x in vec)) or 1.0
            results.append([x / norm for x in vec])
        return results

    def index_documents(self, collection_name: str, docs: list[VectorDocument]) -> int:
        """Batch index documents into the specified collection."""
        if not docs:
            return 0
        collection = self._get_collection(collection_name)
        texts = [d.text for d in docs]
        embeddings = self._embed(texts)

        ids = [d.id for d in docs]
        metadatas = [d.metadata if d.metadata else {"type": "document"} for d in docs]

        collection.upsert(
            ids=ids,
            embeddings=embeddings,
            documents=texts,
            metadatas=metadatas,
        )
        return len(docs)

    def search(
        self,
        collection_name: str,
        query: str,
        *,
        limit: int = 5,
        where: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """Perform dense semantic search in the specified collection."""
        if not query.strip():
            return []
        collection = self._get_collection(collection_name)
        query_vec = self._embed([query])
        if not query_vec:
            return []

        results = collection.query(
            query_embeddings=query_vec,
            n_results=min(limit, max(collection.count(), 1)),
            where=where if where else None,
            include=["documents", "metadatas", "distances"],
        )

        hits: list[dict[str, Any]] = []
        if results and results["ids"] and results["ids"][0]:
            for i, doc_id in enumerate(results["ids"][0]):
                dist = results["distances"][0][i] if results["distances"] else 1.0
                sim = max(0.0, 1.0 - float(dist))
                hits.append(
                    {
                        "id": doc_id,
                        "text": results["documents"][0][i] if results["documents"] else "",
                        "metadata": results["metadatas"][0][i] if results["metadatas"] else {},
                        "similarity": round(sim * 100.0, 1),
                    }
                )
        return hits

    def count(self, collection_name: str) -> int:
        return self._get_collection(collection_name).count()


def sync_all_to_vector_store(
    session: Session,
    settings: Settings,
    *,
    router: LLMRouter | None = None,
) -> dict[str, int]:
    """Indexes all database evidence, documents, opportunities, and PI papers into ChromaDB."""
    store = ChromaVectorStore(settings, router=router)
    stats: dict[str, int] = {}

    # 1. Evidence items
    ev_docs: list[VectorDocument] = []
    for ev in session.query(EvidenceItem).all():
        if ev.content:
            ev_docs.append(
                VectorDocument(
                    id=f"EV-{ev.id}",
                    text=f"{ev.content}\nSource quote: {ev.source_quote}",
                    metadata={
                        "type": "evidence",
                        "category": ev.category or "general",
                        "doc_id": ev.document_id or 0,
                    },
                )
            )
    stats["evidence_items"] = store.index_documents(
        ChromaVectorStore.COLLECTION_EVIDENCE, ev_docs
    )

    # 2. Uploaded documents (structure-aware semantic chunking)
    from opportunity_intel.rag.chunker import StructureAwareChunker

    chunker = StructureAwareChunker(max_chunk_size=800, min_chunk_size=100, overlap_size=150)
    dossier_docs: list[VectorDocument] = []
    for doc in session.query(UploadedDocument).all():
        if doc.extracted_text:
            chunks = chunker.chunk_document(
                doc_id=doc.id,
                text=doc.extracted_text,
                base_metadata={
                    "doc_name": doc.original_name,
                    "doc_type": doc.doc_type,
                },
            )
            for chk in chunks:
                dossier_docs.append(
                    VectorDocument(
                        id=chk.id,
                        text=chk.text,
                        metadata=chk.metadata,
                    )
                )
    stats["dossier_chunks"] = store.index_documents(
        ChromaVectorStore.COLLECTION_DOSSIER, dossier_docs
    )

    # 3. Opportunities
    opp_docs: list[VectorDocument] = []
    for opp in session.query(Opportunity).all():
        blob = (
            f"{opp.title}\n{opp.summary}\n"
            f"Supervisor: {opp.supervisor}\n"
            f"Organization: {opp.organization}\n"
            f"Funding: {opp.funding}"
        )
        opp_docs.append(
            VectorDocument(
                id=f"opp-{opp.id}",
                text=blob,
                metadata={
                    "opp_id": opp.id,
                    "country": opp.country_code or "",
                    "org": opp.organization or "",
                    "funding": opp.funding or "",
                    "rule_fit": float(opp.rule_fit or 0.0),
                },
            )
        )
    stats["opportunities"] = store.index_documents(
        ChromaVectorStore.COLLECTION_OPPORTUNITIES, opp_docs
    )

    # 4. Professor Papers
    paper_docs: list[VectorDocument] = []
    for paper in session.query(ProfessorPaper).all():
        blob = f"{paper.title}\nAuthors: {paper.authors}\nVenue: {paper.venue}\nURL: {paper.url}"
        paper_docs.append(
            VectorDocument(
                id=f"paper-{paper.id}",
                text=blob,
                metadata={
                    "paper_id": paper.id,
                    "venue": paper.venue or "",
                    "authors": paper.authors or "",
                },
            )
        )
    stats["professor_papers"] = store.index_documents(
        ChromaVectorStore.COLLECTION_PAPERS, paper_docs
    )

    logger.info("ChromaDB vector store sync completed: %s", stats)
    return stats
