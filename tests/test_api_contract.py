"""Isolated FastAPI contract tests. No live LLM or network discovery."""

from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from opportunity_intel.discovery.sources import RawListing
from opportunity_intel.llm.router import CompletionResult


def test_health_ok(tmp_app: TestClient) -> None:
    res = tmp_app.get("/health")
    assert res.status_code == 200
    assert res.json() == {"status": "ok"}
    assert "application/json" in res.headers["content-type"]


def test_llm_status_contract_and_no_secrets(tmp_app: TestClient) -> None:
    res = tmp_app.get("/api/llm/status")
    assert res.status_code == 200
    body = res.json()
    for key in (
        "deepseek_configured",
        "groq_configured",
        "huggingface_configured",
        "tavily_configured",
        "brave_configured",
        "gemini_configured",
        "gemini_model",
        "openai_configured",
        "openai_model",
        "offline",
        "polish_enabled",
        "reason_model",
        "extract_model",
        "draft_model",
        "target_countries",
        "excluded_countries",
    ):
        assert key in body
    assert body["deepseek_configured"] is False
    assert body["groq_configured"] is False
    assert body["gemini_configured"] is False
    assert body["openai_configured"] is False
    assert body["target_countries"] == []
    assert body["excluded_countries"] == []
    blob = json.dumps(body)
    assert "sk-" not in blob
    assert "gsk_" not in blob
    assert "api_key" not in blob
    assert "AQ." not in blob
    assert "AIza" not in blob


def test_profile_empty(tmp_app: TestClient) -> None:
    res = tmp_app.get("/api/profile")
    assert res.status_code == 200
    assert res.json() is None


def test_documents_empty_list(tmp_app: TestClient) -> None:
    res = tmp_app.get("/api/documents")
    assert res.status_code == 200
    assert res.json() == []


def test_documents_do_not_expose_extracted_text(tmp_app: TestClient) -> None:
    res = tmp_app.post(
        "/api/documents/upload",
        data={"doc_type": "academic_cv"},
        files={"file": ("cv.md", b"# Chandan Kumar\nMSc Data Science", "text/markdown")},
    )
    assert res.status_code == 200
    body = res.json()
    assert "extracted_text" not in body
    assert body["original_name"] == "cv.md"
    assert body["status"] == "uploaded"
    listed = tmp_app.get("/api/documents").json()
    assert listed[0]["id"] == body["id"]
    assert "extracted_text" not in listed[0]


def test_upload_rejects_empty_invalid_type_and_unsupported(tmp_app: TestClient) -> None:
    empty = tmp_app.post(
        "/api/documents/upload",
        data={"doc_type": "academic_cv"},
        files={"file": ("cv.md", b"", "text/markdown")},
    )
    assert empty.status_code == 400
    assert "Empty" in empty.json()["detail"]

    bad_type = tmp_app.post(
        "/api/documents/upload",
        data={"doc_type": "malware"},
        files={"file": ("cv.md", b"ok", "text/markdown")},
    )
    assert bad_type.status_code == 400

    unsupported = tmp_app.post(
        "/api/documents/upload",
        data={"doc_type": "other"},
        files={"file": ("payload.exe", b"MZ", "application/octet-stream")},
    )
    assert unsupported.status_code == 400


def test_upload_sanitizes_path_traversal_filename(tmp_app: TestClient) -> None:
    res = tmp_app.post(
        "/api/documents/upload",
        data={"doc_type": "other"},
        files={"file": ("../../etc/passwd.md", b"not a secret", "text/markdown")},
    )
    assert res.status_code == 200
    stored = Path(tmp_app.app.state.settings.uploads_dir)
    names = [p.name for p in stored.iterdir()]
    assert all(".." not in name for name in names)
    assert all(not name.startswith("passwd") for name in names)


def test_delete_document_404_then_lifecycle(tmp_app: TestClient) -> None:
    missing = tmp_app.delete("/api/documents/999")
    assert missing.status_code == 404
    created = tmp_app.post(
        "/api/documents/upload",
        data={"doc_type": "other"},
        files={"file": ("note.md", b"hello", "text/markdown")},
    )
    doc_id = created.json()["id"]
    deleted = tmp_app.delete(f"/api/documents/{doc_id}")
    assert deleted.status_code == 200
    assert deleted.json() == {"status": "deleted"}
    again = tmp_app.delete(f"/api/documents/{doc_id}")
    assert again.status_code == 404
    assert tmp_app.get("/api/documents").json() == []


def test_delete_rejects_non_integer_id(tmp_app: TestClient) -> None:
    res = tmp_app.delete("/api/documents/abc")
    assert res.status_code == 422


def test_import_folder_missing_and_idempotent(tmp_app: TestClient) -> None:
    missing_dir = Path(tmp_app.app.state.settings.documents_import_dir)
    missing_dir.rmdir()
    res = tmp_app.post("/api/documents/import-folder")
    assert res.status_code == 400

    missing_dir.mkdir()
    (missing_dir / "cv.md").write_text("MSc Data Science", encoding="utf-8")
    first = tmp_app.post("/api/documents/import-folder")
    assert first.status_code == 200
    assert first.json()["imported"] == 1
    second = tmp_app.post("/api/documents/import-folder")
    assert second.status_code == 200
    assert second.json()["imported"] == 0
    assert second.json()["skipped"] == 1


def test_import_folder_info(tmp_app: TestClient) -> None:
    folder = Path(tmp_app.app.state.settings.documents_import_dir)
    (folder / "a.md").write_text("a", encoding="utf-8")
    res = tmp_app.get("/api/documents/import-folder/info")
    assert res.status_code == 200
    body = res.json()
    assert body["exists"] is True
    assert body["file_count"] == 1


def test_analyze_requires_api_keys(tmp_app: TestClient) -> None:
    res = tmp_app.post("/api/profile/analyze")
    assert res.status_code == 503


def test_analyze_requires_documents(keyed_app: TestClient) -> None:
    empty = keyed_app.post("/api/profile/analyze")
    assert empty.status_code == 400
    assert "document" in empty.json()["detail"].lower()


def test_analyze_with_mocked_llm(keyed_app: TestClient, monkeypatch) -> None:  # noqa: ANN001
    keyed_app.post(
        "/api/documents/upload",
        data={"doc_type": "academic_cv"},
        files={"file": ("cv.md", b"Chandan Kumar\nMSc Data Science", "text/markdown")},
    )

    def fake_complete(self, role: str, messages: list, json_mode: bool = False) -> CompletionResult:  # noqa: ARG001
        if role == "extract":
            payload = {
                "document_type_guess": "academic_cv",
                "full_name": "Chandan Kumar",
                "degrees": ["MSc Data Science"],
                "research_interests": ["agentic AI"],
                "skills": ["Python"],
                "evidence": [
                    {"category": "education", "content": "MSc", "quote": "MSc Data Science"}
                ],
            }
        else:
            payload = {
                "profile": {
                    "full_name": "Chandan Kumar",
                    "highest_degree": "MSc Data Science",
                    "research_interests": "agentic AI",
                    "skills": "Python",
                    "funding_requirement": "fully_funded",
                    "target_countries": "NL,DE",
                    "profile_summary": "Industry AI engineer targeting funded PhDs.",
                    "notes": "",
                },
                "research_suggestions": [
                    {
                        "title": "Agent security",
                        "summary": "Secure agentic pipelines.",
                        "rationale": "Matches documented LangGraph work.",
                        "next_steps": "Read ATLAS.",
                        "priority": "high",
                    }
                ],
            }
        return CompletionResult(text=json.dumps(payload), model="mock", provider="mock", role=role)

    monkeypatch.setattr("opportunity_intel.agents.advisor.LLMRouter.complete", fake_complete)
    res = keyed_app.post("/api/profile/analyze")
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["profile"]["full_name"] == "Chandan Kumar"
    assert body["suggestions"][0]["priority"] == "high"
    assert "parsed_count" in body
    assert "failed_count" in body
    profile = keyed_app.get("/api/profile").json()
    assert profile["full_name"] == "Chandan Kumar"
    suggestions = keyed_app.get("/api/advisor/suggestions").json()
    assert len(suggestions) == 1
    messages = keyed_app.get("/api/advisor/messages").json()
    assert messages[0]["role"] == "assistant"


def test_chat_validation_and_mocked_reply(keyed_app: TestClient, monkeypatch) -> None:  # noqa: ANN001
    empty = keyed_app.post("/api/advisor/chat", json={"message": ""})
    assert empty.status_code == 422
    missing = keyed_app.post("/api/advisor/chat", json={})
    assert missing.status_code == 422

    def fake_complete(self, role: str, messages: list, json_mode: bool = False) -> CompletionResult:  # noqa: ARG001
        return CompletionResult(
            text="Pick the agent-security track first.",
            model="mock",
            provider="mock",
            role=role,
        )

    monkeypatch.setattr("opportunity_intel.agents.advisor.LLMRouter.complete", fake_complete)
    res = keyed_app.post("/api/advisor/chat", json={"message": "Which topic first?"})
    assert res.status_code == 200
    assert "agent-security" in res.json()["reply"]["content"]
    history = keyed_app.get("/api/advisor/messages").json()
    roles = [m["role"] for m in history]
    assert "user" in roles
    assert "assistant" in roles


def test_chat_requires_deepseek_key(tmp_app: TestClient) -> None:
    res = tmp_app.post("/api/advisor/chat", json={"message": "hello there"})
    assert res.status_code == 503


def test_discovery_validation_and_country_filter(keyed_app: TestClient, monkeypatch) -> None:  # noqa: ANN001
    short = keyed_app.post("/api/discovery/runs", json={"query": "ab"})
    assert short.status_code == 422

    def fake_discover(query: str, settings, model_config):  # noqa: ANN001, ARG001
        return [
            RawListing(
                title="PhD Agentic AI",
                source_url="https://www.tudelft.nl/jobs/phd-1",
                organization="TU Delft",
                location="Netherlands",
                summary="Fully funded stipend on agents",
                source="test",
                funding="fully funded",
                supervisor="Ada Lovelace",
            ),
            RawListing(
                title="A guide to PhD funding in Europe",
                source_url="https://example.com/phd-funding-guide",
                organization="Blog",
                location="Netherlands",
                summary="An overview of scholarships worldwide",
                source="test",
                funding="",
            ),
            RawListing(
                title="UK PhD",
                source_url="https://www.ox.ac.uk/jobs/phd-uk",
                organization="Oxford",
                location="United Kingdom",
                summary="Funded",
                source="test",
                funding="fully funded",
            ),
        ]

    monkeypatch.setattr("opportunity_intel.discovery.service.discover", fake_discover)
    res = keyed_app.post(
        "/api/discovery/runs",
        json={"query": "PhD agentic AI governance"},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "completed"
    assert body["found_count"] == 3
    assert body["kept_count"] == 2
    opps = keyed_app.get("/api/opportunities").json()
    assert len(opps) == 2
    codes = {row["country_code"] for row in opps}
    assert "NL" in codes
    assert "GB" in codes
    assert all(row["title"] != "A guide to PhD funding in Europe" for row in opps)


def test_shortlist_opportunity(keyed_app: TestClient, monkeypatch) -> None:  # noqa: ANN001
    def fake_discover(query: str, settings, model_config):  # noqa: ANN001, ARG001
        return [
            RawListing(
                title="PhD Responsible Agents",
                source_url="https://www.tudelft.nl/jobs/phd-2",
                organization="TU Delft",
                location="Netherlands",
                summary="Fully funded PhD vacancy",
                source="test",
                funding="fully funded",
            ),
        ]

    monkeypatch.setattr("opportunity_intel.discovery.service.discover", fake_discover)
    keyed_app.post("/api/discovery/runs", json={"query": "PhD agentic AI"})
    opp_id = keyed_app.get("/api/opportunities").json()[0]["id"]
    starred = keyed_app.post(
        f"/api/opportunities/{opp_id}/shortlist",
        json={"shortlisted": True},
    )
    assert starred.status_code == 200
    assert starred.json()["shortlisted"] == 1
    listed = keyed_app.get("/api/opportunities").json()
    assert listed[0]["shortlisted"] == 1
    cleared = keyed_app.post(
        f"/api/opportunities/{opp_id}/shortlist",
        json={"shortlisted": False},
    )
    assert cleared.json()["shortlisted"] == 0
    missing = keyed_app.post("/api/opportunities/9999/shortlist", json={"shortlisted": True})
    assert missing.status_code == 404


def test_analyze_returns_parsed_failed_counts(keyed_app: TestClient, monkeypatch) -> None:  # noqa: ANN001
    keyed_app.post(
        "/api/documents/upload",
        data={"doc_type": "academic_cv"},
        files={"file": ("cv.md", b"Chandan Kumar\nMSc Data Science", "text/markdown")},
    )

    def fake_complete(self, role: str, messages: list, json_mode: bool = False) -> CompletionResult:  # noqa: ARG001
        if role == "extract":
            payload = {
                "document_type_guess": "academic_cv",
                "full_name": "Chandan Kumar",
                "degrees": ["MSc Data Science"],
                "research_interests": ["agentic AI"],
                "skills": ["Python"],
                "evidence": [
                    {"category": "education", "content": "MSc", "quote": "MSc Data Science"}
                ],
            }
        else:
            payload = {
                "profile": {
                    "full_name": "Chandan Kumar",
                    "highest_degree": "MSc Data Science",
                    "research_interests": "agentic AI",
                    "skills": "Python",
                    "funding_requirement": "fully_funded",
                    "target_countries": "NL,DE",
                    "profile_summary": "Industry AI engineer targeting funded PhDs.",
                    "notes": "",
                },
                "research_suggestions": [
                    {
                        "title": "Agent security",
                        "summary": "Secure agentic pipelines.",
                        "rationale": "Matches documented LangGraph work.",
                        "next_steps": "Read ATLAS.",
                        "priority": "high",
                    }
                ],
            }
        return CompletionResult(text=json.dumps(payload), model="mock", provider="mock", role=role)

    monkeypatch.setattr("opportunity_intel.agents.advisor.LLMRouter.complete", fake_complete)
    res = keyed_app.post("/api/profile/analyze")
    assert res.status_code == 200
    body = res.json()
    assert body["parsed_count"] >= 1
    assert body["failed_count"] == 0
    assert "parsed" in body["message"].lower()


def test_monitor_health_and_runs(tmp_app: TestClient) -> None:
    health = tmp_app.get("/api/monitor/health")
    assert health.status_code == 200
    body = health.json()
    assert body["ok"] is True
    assert body["failed_runs"] == 0
    assert "agent-runs.jsonl" in body["log_file"]
    runs = tmp_app.get("/api/monitor/runs")
    assert runs.status_code == 200
    assert runs.json() == []


def test_wrong_method_and_unknown_path(tmp_app: TestClient) -> None:
    assert tmp_app.put("/health").status_code == 405
    assert tmp_app.get("/api/does-not-exist").status_code == 404


def test_mutating_endpoints_have_no_auth_gate(tmp_app: TestClient) -> None:
    """Local-first: no auth today. This must stay documented until a token exists."""
    res = tmp_app.post("/api/documents/import-folder")
    assert res.status_code in {200, 400}
    assert res.status_code != 401
    chat = tmp_app.post("/api/advisor/chat", json={"message": "hello there"})
    assert chat.status_code == 503
    assert chat.status_code != 401
