"""Tests for the RAG/FAISS vector store and LaTeX compilation."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from opportunity_intel.config import ROOT, Settings
from opportunity_intel.execution.latex import compile_latex
from opportunity_intel.llm.models_config import load_model_config
from opportunity_intel.llm.router import LLMRouter, _hash_embed
from opportunity_intel.rag.faiss_store import alignment_score, query_similar, upsert_corpus

# ---------------------------------------------------------------------------
# Existing tests (unchanged behaviour)
# ---------------------------------------------------------------------------


def test_alignment_score_local() -> None:
    """Hash-trick alignment score works without any API token."""
    settings = Settings(openai_api_key="", gemini_api_key="", hf_token="")
    score = alignment_score(settings, "agentic AI governance PhD", "funded PhD agentic AI")
    assert score > 0


def test_upsert_and_query(tmp_path: Path, monkeypatch) -> None:  # noqa: ANN001
    from sqlalchemy.orm import Session

    class _Empty:
        def query(self, _model):  # noqa: ANN001
            class _Q:
                def order_by(self, _col):  # noqa: ANN001
                    return self

                def all(self):
                    return []

            return _Q()

    settings = Settings(faiss_dir=tmp_path / "faiss", openai_api_key="", gemini_api_key="")
    assert upsert_corpus(_Empty(), settings) == 0  # type: ignore[arg-type]
    assert query_similar(settings, "agents") == []
    _ = Session
    _ = monkeypatch


def test_latex_without_tex(tmp_path: Path) -> None:
    ok, msg = compile_latex("", tmp_path)
    assert ok is False
    assert msg == "empty"
    ok, msg = compile_latex("\\documentclass{article}\\begin{document}x\\end{document}", tmp_path)
    assert ok is False
    assert "pdflatex" in msg or "not installed" in msg or msg


# ---------------------------------------------------------------------------
# New tests: LLMRouter.embed() — HF Inference API path
# ---------------------------------------------------------------------------


def _make_router(*, hf_token: str = "") -> LLMRouter:
    cfg = load_model_config(ROOT / "config" / "models.yaml")
    settings = Settings(hf_token=hf_token, openai_api_key="", gemini_api_key="")
    return LLMRouter(settings, cfg)


def test_embed_returns_empty_for_empty_input() -> None:
    router = _make_router(hf_token="")
    result = router.embed([])
    assert result == []


def test_embed_hash_trick_fallback_no_token() -> None:
    """Without HF_TOKEN, embed() falls back to hash-trick (256-dim)."""
    router = _make_router(hf_token="")
    result = router.embed(["agentic AI governance"])
    assert len(result) == 1
    assert len(result[0]) == 256
    # Vectors should be normalised (unit norm ~= 1.0)
    import math

    norm = math.sqrt(sum(v * v for v in result[0]))
    assert abs(norm - 1.0) < 1e-6


def test_embed_hash_trick_fallback_is_deterministic() -> None:
    """Hash-trick embedding is deterministic for the same input."""
    router = _make_router(hf_token="")
    v1 = router.embed(["funded PhD Responsible AI"])[0]
    v2 = router.embed(["funded PhD Responsible AI"])[0]
    assert v1 == v2


def test_embed_hf_api_called_with_correct_shape() -> None:
    """With HF_TOKEN set, embed() POSTs to the HF Inference API correctly."""
    # Mock 384-dim response (BGE-small-en-v1.5 output shape)
    fake_vectors = [[0.1] * 384, [0.2] * 384]

    mock_response = MagicMock()
    mock_response.json.return_value = fake_vectors
    mock_response.raise_for_status = MagicMock()

    router = _make_router(hf_token="hf-test-token-xyz")

    with patch("opportunity_intel.llm.router.httpx.post", return_value=mock_response) as mock_post:
        result = router.embed(["text one", "text two"])

    # Correct endpoint called
    mock_post.assert_called_once()
    call_kwargs = mock_post.call_args
    assert "BAAI/bge-small-en-v1.5" in call_kwargs.args[0]
    # Auth header present
    assert call_kwargs.kwargs["headers"]["Authorization"] == "Bearer hf-test-token-xyz"
    # Inputs passed correctly
    assert call_kwargs.kwargs["json"]["inputs"] == ["text one", "text two"]

    # Results match mock response
    assert len(result) == 2
    assert len(result[0]) == 384
    assert result[0][0] == 0.1
    assert result[1][0] == 0.2


def test_embed_hf_api_result_cached() -> None:
    """Second call with the same text uses the cache, not the API."""
    fake_vectors = [[0.5] * 384]
    mock_response = MagicMock()
    mock_response.json.return_value = fake_vectors
    mock_response.raise_for_status = MagicMock()

    router = _make_router(hf_token="hf-test-token-xyz")

    with patch("opportunity_intel.llm.router.httpx.post", return_value=mock_response) as mock_post:
        first = router.embed(["cached text"])
        second = router.embed(["cached text"])

    # API called only once; second call served from cache
    assert mock_post.call_count == 1
    assert first == second


def test_embed_hf_api_fallback_on_error() -> None:
    """If the HF API raises, embed() falls back to hash-trick without crashing."""
    import warnings

    router = _make_router(hf_token="hf-test-token-xyz")

    with patch(
        "opportunity_intel.llm.router.httpx.post",
        side_effect=Exception("network error"),
    ):
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            result = router.embed(["fallback text"])

    # Should have issued a UserWarning about the fallback
    assert any("hash-trick fallback" in str(w.message) for w in caught)
    # Should still return a valid hash-trick vector (256-dim)
    assert len(result) == 1
    assert len(result[0]) == 256


def test_embed_hf_single_vector_response() -> None:
    """HF may return a flat list[float] for single input instead of list[list[float]]."""
    fake_single = [0.3] * 384  # flat, not nested

    mock_response = MagicMock()
    mock_response.json.return_value = fake_single
    mock_response.raise_for_status = MagicMock()

    router = _make_router(hf_token="hf-test-token-xyz")

    with patch("opportunity_intel.llm.router.httpx.post", return_value=mock_response):
        result = router.embed(["single text"])

    assert len(result) == 1
    assert len(result[0]) == 384
    assert result[0][0] == 0.3


def test_embed_mixed_cached_and_uncached() -> None:
    """Partial cache hit: cached items served from cache, rest from API."""
    router = _make_router(hf_token="hf-test-token-xyz")

    # Pre-populate cache with first text
    import hashlib

    pre_vec = [0.9] * 384
    key = hashlib.sha256(b"already cached").hexdigest()
    router._embed_cache[key] = pre_vec

    # API will be called only for the second text
    api_vec = [0.4] * 384
    mock_response = MagicMock()
    mock_response.json.return_value = [api_vec]
    mock_response.raise_for_status = MagicMock()

    with patch("opportunity_intel.llm.router.httpx.post", return_value=mock_response) as mock_post:
        result = router.embed(["already cached", "new text"])

    # API called only once for the uncached text
    assert mock_post.call_count == 1
    # First result is from cache
    assert result[0] == pre_vec
    # Second result is from API
    assert result[1] == api_vec


# ---------------------------------------------------------------------------
# New tests: faiss_store uses router vectors when provided
# ---------------------------------------------------------------------------


def test_alignment_score_with_router(tmp_path: Path) -> None:
    """alignment_score uses real vectors from router when provided."""
    fake_cv_vec = [1.0, 0.0] + [0.0] * 382
    fake_lab_vec = [1.0, 0.0] + [0.0] * 382  # identical → score = 100

    router = _make_router(hf_token="hf-test-token-xyz")
    call_count = [0]

    def fake_embed(texts: list[str]) -> list[list[float]]:
        call_count[0] += 1
        return [fake_cv_vec if i == 0 else fake_lab_vec for i in range(len(texts))]

    router.embed = fake_embed  # type: ignore[method-assign]

    settings = Settings(
        hf_token="hf-test-token-xyz",
        faiss_dir=tmp_path / "faiss",
        openai_api_key="",
        gemini_api_key="",
    )
    score = alignment_score(settings, "cv text", "lab text", router=router)
    assert score == 100.0
    assert call_count[0] == 2  # one call per text


def test_alignment_score_without_router_uses_hash_trick() -> None:
    """alignment_score with no router stays functional via hash-trick."""
    settings = Settings(hf_token="", openai_api_key="", gemini_api_key="")
    # Different texts should produce a score between 0 and 100
    score = alignment_score(settings, "agentic AI NL funded PhD", "responsible AI governance")
    assert 0.0 <= score <= 100.0


def test_hash_embed_module_level_function() -> None:
    """_hash_embed is importable and returns 256-dim normalised vector."""
    import math

    vec = _hash_embed("test text for hashing")
    assert len(vec) == 256
    norm = math.sqrt(sum(v * v for v in vec))
    assert abs(norm - 1.0) < 1e-6
