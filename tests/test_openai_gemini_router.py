"""Tests for OpenAI client construction and Gemini REST search grounding."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from opportunity_intel.config import ROOT, Settings
from opportunity_intel.llm.gemini import (
    hits_from_response,
    search_gemini_grounded,
)
from opportunity_intel.llm.models_config import load_model_config
from opportunity_intel.llm.router import LLMRouter
from opportunity_intel.observability.trace import redact


def test_openai_client_requires_key() -> None:
    cfg = load_model_config(ROOT / "config" / "models.yaml")
    router = LLMRouter(Settings(openai_api_key=""), cfg)
    try:
        router._client_for("openai")
        raise AssertionError("expected ValueError")
    except ValueError as exc:
        assert "OPENAI_API_KEY" in str(exc)


def test_openai_client_constructs_without_network() -> None:
    cfg = load_model_config(ROOT / "config" / "models.yaml")
    settings = Settings(openai_api_key="test-openai-placeholder")
    router = LLMRouter(settings, cfg)
    client = router._client_for("openai")
    assert client.api_key == "test-openai-placeholder"


def test_gemini_skips_without_key() -> None:
    hits = search_gemini_grounded("PhD agents", api_key="")
    assert hits == []


def test_gemini_uses_injected_generate() -> None:
    """Existing test: object-style response from the test-injection hook."""

    class _Web:
        uri = "https://www.tudelft.nl/jobs/phd-agents"
        title = "PhD Agents"

    class _Chunk:
        web = _Web()

    class _Meta:
        grounding_chunks = [_Chunk()]

    class _Candidate:
        grounding_metadata = _Meta()

    class _Resp:
        candidates = [_Candidate()]
        text = ""

    def fake_generate(**kwargs):  # noqa: ANN003
        assert kwargs["config"]["tools"] == [{"google_search": {}}]
        return _Resp()

    hits = search_gemini_grounded(
        "PhD agents",
        api_key="test-gemini-placeholder",
        generate=fake_generate,
    )
    assert len(hits) == 1
    assert hits[0].url.startswith("https://www.tudelft.nl")


def test_gemini_rest_dict_response_parsed() -> None:
    """New test: dict-style REST response (httpx path) is parsed correctly."""
    rest_response = {
        "candidates": [
            {
                "content": {"parts": [{"text": "Some PhD vacancy found."}]},
                "groundingMetadata": {
                    "groundingChunks": [
                        {
                            "web": {
                                "uri": "https://www.rug.nl/phd-agentic-ai",
                                "title": "PhD Agentic AI - University of Groningen",
                            }
                        },
                        {
                            "web": {
                                "uri": "https://www.tudelft.nl/phd-governance",
                                "title": "PhD AI Governance - TU Delft",
                            }
                        },
                    ]
                },
            }
        ]
    }
    hits = hits_from_response(rest_response, limit=10)
    assert len(hits) == 2
    assert hits[0].url == "https://www.rug.nl/phd-agentic-ai"
    assert hits[0].title == "PhD Agentic AI - University of Groningen"
    assert hits[0].provider == "gemini"
    assert hits[1].url == "https://www.tudelft.nl/phd-governance"


def test_gemini_rest_dict_respects_limit() -> None:
    """REST dict response respects the limit parameter."""
    rest_response = {
        "candidates": [
            {
                "content": {"parts": [{"text": ""}]},
                "groundingMetadata": {
                    "groundingChunks": [
                        {"web": {"uri": f"https://example.com/phd-{i}", "title": f"PhD {i}"}}
                        for i in range(10)
                    ]
                },
            }
        ]
    }
    hits = hits_from_response(rest_response, limit=3)
    assert len(hits) == 3


def test_gemini_rest_no_import_needed() -> None:
    """generate_grounded uses httpx, not the google.genai SDK.

    Mock httpx.post to simulate a real REST call without network access.
    Confirms no ImportError is raised even if google-genai is not installed.
    """
    rest_payload = {
        "candidates": [
            {
                "content": {"parts": [{"text": ""}]},
                "groundingMetadata": {
                    "groundingChunks": [
                        {
                            "web": {
                                "uri": "https://www.leiden.nl/phd-ai-governance",
                                "title": "PhD AI Governance - Leiden",
                            }
                        }
                    ]
                },
            }
        ]
    }
    mock_response = MagicMock()
    mock_response.json.return_value = rest_payload
    mock_response.raise_for_status = MagicMock()

    with patch("opportunity_intel.llm.gemini.httpx.post", return_value=mock_response) as mock_post:
        hits = search_gemini_grounded("funded PhD AI governance NL", api_key="test-key-xyz")

    mock_post.assert_called_once()
    call_kwargs = mock_post.call_args
    # Confirm the key is passed as a query param, not in Authorization header
    assert call_kwargs.kwargs["params"]["key"] == "test-key-xyz"
    # Confirm google_search tool is requested
    assert call_kwargs.kwargs["json"]["tools"] == [{"google_search": {}}]
    assert len(hits) == 1
    assert hits[0].url == "https://www.leiden.nl/phd-ai-governance"
    assert hits[0].provider == "gemini"


def test_gemini_rest_falls_back_on_http_error() -> None:
    """Network error during REST call returns empty list, not an exception."""
    import httpx as _httpx

    with patch(
        "opportunity_intel.llm.gemini.httpx.post",
        side_effect=_httpx.ConnectError("unreachable"),
    ):
        hits = search_gemini_grounded("funded PhD NL", api_key="test-key-xyz")
    assert hits == []


def test_redact_gemini_style_tokens() -> None:
    sample = "prefix AQ.TESTGEMINITOKEN suffix AIzaSyTESTTOKEN"
    cleaned = redact(sample)
    assert "AQ." not in cleaned
    assert "AIza" not in cleaned
    assert "[redacted]" in cleaned
