"""Local vector index under data/faiss/index.json.

Uses real BAAI/bge-small-en-v1.5 vectors when an LLMRouter with a
valid HF_TOKEN is passed. Falls back to a local 256-dim hash-trick
embedding so the system works completely offline.

No cloud vector DB. No faiss-cpu dependency required at runtime
(the JSON sidecar approach is used by default).
"""

from __future__ import annotations

import json
import math
import re
from pathlib import Path
from typing import TYPE_CHECKING

from sqlalchemy.orm import Session

from opportunity_intel.config import Settings
from opportunity_intel.domain.models import EvidenceItem, ProfessorPaper, UploadedDocument

if TYPE_CHECKING:
    from opportunity_intel.llm.router import LLMRouter

_TOKEN = re.compile(r"[a-z0-9]{3,}")

# Dimension of the hash-trick fallback (router-provided vectors vary by model).
_HASH_DIM = 256


def _embed(text: str) -> list[float]:
    """256-dim hash-trick embedding. Used when no LLMRouter is available."""
    vec = [0.0] * _HASH_DIM
    for token in _TOKEN.findall(text.lower()):
        vec[hash(token) % _HASH_DIM] += 1.0
    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / norm for v in vec]


def _get_vector(text: str, router: LLMRouter | None) -> list[float]:
    """Return a real embedding from the router, or fall back to hash-trick."""
    if router is not None:
        try:
            vecs = router.embed([text])
            if vecs and vecs[0]:
                return vecs[0]
        except Exception:  # noqa: BLE001
            pass
    return _embed(text)


def cosine(a: list[float], b: list[float]) -> float:
    """Dot-product cosine similarity (works for pre-normalised vectors)."""
    if len(a) != len(b):
        # Dimension mismatch — can happen when mixing real + hash-trick vectors.
        # Return 0 rather than crash; caller will treat it as no match.
        return 0.0
    return float(sum(x * y for x, y in zip(a, b, strict=True)))


def _sidecar(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path / "index.json"


def upsert_corpus(
    session: Session,
    settings: Settings,
    *,
    router: LLMRouter | None = None,
) -> int:
    """Build / rebuild the local vector sidecar.

    Pass ``router`` to use real BAAI/bge-small-en-v1.5 embeddings.
    Omit it (or when HF_TOKEN is unset) to use the hash-trick fallback.

    Returns the number of documents indexed.
    """
    docs: dict[str, str] = {}
    for item in session.query(EvidenceItem).order_by(EvidenceItem.id).all():
        if item.content:
            docs[f"ev-{item.id}"] = item.content[:4000]
    for paper in session.query(ProfessorPaper).order_by(ProfessorPaper.id).all():
        blob = f"{paper.title} {paper.authors} {paper.venue}".strip()
        if blob:
            docs[f"paper-{paper.id}"] = blob[:4000]
    for doc in session.query(UploadedDocument).order_by(UploadedDocument.id).all():
        if doc.extracted_text:
            docs[f"doc-{doc.id}"] = doc.extracted_text[:4000]
    if not docs:
        return 0

    # Batch-embed all texts in one call when a router is available to minimise
    # HF API round-trips; fall back per-item otherwise.
    if router is not None:
        texts = list(docs.values())
        try:
            vectors = router.embed(texts)
        except Exception:  # noqa: BLE001
            vectors = [_embed(t) for t in texts]
        payload = {
            key: {"text": text, "vector": vec} for (key, text), vec in zip(docs.items(), vectors)
        }
    else:
        payload = {key: {"text": text, "vector": _embed(text)} for key, text in docs.items()}

    sidecar = _sidecar(settings.faiss_dir)
    sidecar.write_text(json.dumps(payload), encoding="utf-8")
    return len(payload)


def alignment_score(
    settings: Settings,
    cv_text: str,
    lab_text: str,
    *,
    router: LLMRouter | None = None,
) -> float:
    """Return a 0-100 cosine similarity score between two texts.

    Pass ``router`` to use real BAAI/bge-small-en-v1.5 vectors.
    Without a router, falls back to the hash-trick (still useful for
    rough ranking but less semantically accurate).
    """
    if not cv_text.strip() or not lab_text.strip():
        return 0.0
    cv_vec = _get_vector(cv_text, router)
    lab_vec = _get_vector(lab_text, router)
    return round(max(0.0, cosine(cv_vec, lab_vec)) * 100, 1)


def query_similar(
    settings: Settings,
    text: str,
    *,
    n: int = 5,
    router: LLMRouter | None = None,
) -> list[str]:
    """Return up to ``n`` corpus texts most similar to ``text``."""
    sidecar = _sidecar(settings.faiss_dir)
    if not sidecar.exists() or not text.strip():
        return []
    payload = json.loads(sidecar.read_text(encoding="utf-8"))
    query_vec = _get_vector(text, router)
    ranked = sorted(
        payload.values(),
        key=lambda row: cosine(query_vec, row["vector"]),
        reverse=True,
    )
    return [str(row["text"]) for row in ranked[:n]]
