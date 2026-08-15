"""Tests for llm/json_repair.py and the Groq failed_generation recovery handler."""

from __future__ import annotations

import json

import pytest

from opportunity_intel.llm.json_repair import parse_llm_json
from opportunity_intel.llm.router import _failed_generation

# ---------------------------------------------------------------------------
# Existing test — Groq failed_generation handler
# ---------------------------------------------------------------------------


class _Err:
    def __init__(self, body: dict) -> None:
        self.body = body


def test_recover_groq_failed_generation() -> None:
    payload = {
        "error": {
            "code": "json_validate_failed",
            "failed_generation": '{"full_name": "Chandan Kumar"}',
        }
    }
    assert _failed_generation(_Err(payload)) == '{"full_name": "Chandan Kumar"}'


# ---------------------------------------------------------------------------
# Strategy 1: direct clean JSON
# ---------------------------------------------------------------------------


def test_parse_clean_json_object() -> None:
    result = parse_llm_json('{"requirements": [{"text": "MSc required", "category": "degree"}]}')
    assert isinstance(result, dict)
    assert "requirements" in result
    assert result["requirements"][0]["text"] == "MSc required"


def test_parse_clean_json_array() -> None:
    result = parse_llm_json('[{"id": 1}, {"id": 2}]')
    assert isinstance(result, list)
    assert len(result) == 2


def test_parse_clean_json_with_leading_trailing_whitespace() -> None:
    result = parse_llm_json('   \n  {"key": "value"}  \n  ')
    assert result == {"key": "value"}


# ---------------------------------------------------------------------------
# Strategy 2: markdown fence stripping
# ---------------------------------------------------------------------------


def test_parse_fenced_json_with_language_tag() -> None:
    text = '```json\n{"llm_fit": 82, "fit_rationale": "Good match"}\n```'
    result = parse_llm_json(text)
    assert result["llm_fit"] == 82
    assert result["fit_rationale"] == "Good match"


def test_parse_fenced_json_without_language_tag() -> None:
    text = '```\n{"status": "ok", "issues": []}\n```'
    result = parse_llm_json(text)
    assert result["status"] == "ok"


def test_parse_fenced_json_uppercase_language_tag() -> None:
    text = '```JSON\n{"key": "value"}\n```'
    result = parse_llm_json(text)
    assert result == {"key": "value"}


def test_parse_fenced_json_with_surrounding_text() -> None:
    """Fence is embedded in prose before and after."""
    text = (
        "Here is the extracted data:\n"
        "```json\n"
        '{"full_name": "Chandan Kumar", "degree": "MSc"}\n'
        "```\n"
        "Please verify the above."
    )
    result = parse_llm_json(text)
    assert result["full_name"] == "Chandan Kumar"


# ---------------------------------------------------------------------------
# Strategy 3: balanced block extraction from prose
# ---------------------------------------------------------------------------


def test_parse_json_embedded_in_prose() -> None:
    """JSON object embedded mid-sentence — no fence."""
    text = (
        "After careful analysis, the result is: "
        '{"cv_tailor": "tailored bullets", "cover_letter": "Dear Prof..."} '
        "I hope that helps."
    )
    result = parse_llm_json(text)
    assert result["cv_tailor"] == "tailored bullets"


def test_parse_json_with_trailing_explanation() -> None:
    """Model outputs JSON then writes a plain-text explanation after."""
    text = (
        '{"items": [{"text": "MSc required", "status": "met"}]}\n\n'
        "Note: I matched the requirement based on the uploaded CV."
    )
    result = parse_llm_json(text)
    assert isinstance(result["items"], list)
    assert result["items"][0]["status"] == "met"


def test_parse_json_array_embedded_in_prose() -> None:
    text = 'The requirements are [{"text": "PhD vacancy", "category": "other"}] as listed.'
    result = parse_llm_json(text)
    assert isinstance(result, list)
    assert result[0]["category"] == "other"


def test_parse_nested_json_object() -> None:
    """Deeply nested JSON still parses correctly."""
    data = {
        "profile": {
            "full_name": "Chandan Kumar",
            "degrees": ["MSc Data Science"],
            "research_interests": "agentic AI, governance",
        },
        "research_suggestions": [{"title": "AI Governance", "priority": "high"}],
    }
    result = parse_llm_json(json.dumps(data))
    assert result["profile"]["full_name"] == "Chandan Kumar"
    assert result["research_suggestions"][0]["priority"] == "high"


# ---------------------------------------------------------------------------
# Strategy 4: Groq failed_generation with markdown-wrapped JSON
# ---------------------------------------------------------------------------


def test_parse_groq_failed_generation_with_markdown_fence() -> None:
    """Groq sometimes returns JSON wrapped in a fence inside failed_generation."""
    raw = '```json\n{"full_name": "Chandan Kumar", "email": "test@example.com"}\n```'
    result = parse_llm_json(raw)
    assert result["full_name"] == "Chandan Kumar"
    assert result["email"] == "test@example.com"


def test_parse_groq_failed_generation_with_prose_and_fence() -> None:
    """Groq returns explanation text then fenced JSON."""
    raw = (
        "I could not fully validate the JSON. Here is what I generated:\n"
        "```json\n"
        '{"requirements": [{"text": "Fully funded", "category": "funding"}]}\n'
        "```"
    )
    result = parse_llm_json(raw)
    assert result["requirements"][0]["text"] == "Fully funded"


# ---------------------------------------------------------------------------
# Error path: completely unparseable text raises JSONDecodeError
# ---------------------------------------------------------------------------


def test_parse_completely_unparseable_raises() -> None:
    with pytest.raises(json.JSONDecodeError):
        parse_llm_json("This is just plain prose with no JSON in it at all.")


def test_parse_empty_string_raises() -> None:
    with pytest.raises(json.JSONDecodeError):
        parse_llm_json("")


def test_parse_whitespace_only_raises() -> None:
    with pytest.raises(json.JSONDecodeError):
        parse_llm_json("   \n\t  ")


def test_parse_malformed_json_raises() -> None:
    with pytest.raises(json.JSONDecodeError):
        parse_llm_json('{"key": "value"  missing_bracket')


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


def test_parse_json_with_unicode() -> None:
    text = '{"title": "Promovendi in AI — Universität München", "country": "DE"}'
    result = parse_llm_json(text)
    assert "München" in result["title"]


def test_parse_json_with_boolean_and_null() -> None:
    text = '{"ok": true, "issues": null, "count": 0}'
    result = parse_llm_json(text)
    assert result["ok"] is True
    assert result["issues"] is None
    assert result["count"] == 0


def test_parse_large_packet_draft_shape() -> None:
    """Simulate the shape returned by the PACKET_DRAFT_PROMPT."""
    data = {
        "cv_tailor": "• Led LangGraph pipeline at Deloitte (EV-1)\n• MSc thesis on fairness (EV-3)",
        "cover_letter": "Dear Prof. X, I am writing to express interest...",
        "research_proposal": "1. Motivation\n...\n4. References: [PI Paper Title]",
        "cited_evidence_ids": [1, 3],
        "cited_paper_titles": ["Responsible AI Governance in Agentic Systems"],
    }
    result = parse_llm_json(json.dumps(data))
    assert result["cited_evidence_ids"] == [1, 3]
    assert len(result["cited_paper_titles"]) == 1
