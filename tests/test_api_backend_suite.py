"""Expanded backend API suite: contract, validation, security, LLM/discovery failures.

Uses isolated tmp_app / keyed_app fixtures. Mocks LLM and discovery; no live network.
"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from opportunity_intel.discovery.sources import RawListing
from opportunity_intel.llm.budget import BudgetExceeded
from opportunity_intel.llm.router import CompletionResult

OPPORTUNITY_KEYS = {
    "id",
    "kind",
    "source",
    "title",
    "organization",
    "country_code",
    "location",
    "source_url",
    "funding",
    "deadline",
    "summary",
    "supervisor",
    "rule_fit",
    "llm_fit",
    "embed_fit",
    "fit_rationale",
    "status",
    "shortlisted",
}

DOCUMENT_KEYS = {
    "id",
    "original_name",
    "doc_type",
    "mime_type",
    "file_size",
    "status",
    "source_path",
    "created_at",
}


def _nl_listing(url: str = "https://www.tudelft.nl/jobs/phd-api-suite") -> RawListing:
    return RawListing(
        title="PhD Agentic AI Governance",
        source_url=url,
        organization="TU Delft",
        location="Netherlands",
        summary="Fully funded PhD vacancy on responsible agents",
        source="test",
        funding="fully funded",
        supervisor="Ada Lovelace",
        deadline=None,
    )


def _seed_opportunity(client: TestClient, monkeypatch: pytest.MonkeyPatch, url: str) -> int:
    def fake_discover(query: str, settings, model_config):  # noqa: ANN001, ARG001
        return [_nl_listing(url)]

    monkeypatch.setattr("opportunity_intel.discovery.service.discover", fake_discover)
    res = client.post("/api/discovery/runs", json={"query": "PhD agentic AI"})
    assert res.status_code == 200, res.text
    assert res.json()["status"] == "completed"
    assert res.json()["kept_count"] >= 1
    opps = client.get("/api/opportunities").json()
    assert len(opps) >= 1
    return int(opps[0]["id"])


# ---------------------------------------------------------------------------
# Empty-state contracts for every read endpoint
# ---------------------------------------------------------------------------


def test_empty_collections_contract(tmp_app: TestClient) -> None:
    assert tmp_app.get("/api/advisor/suggestions").json() == []
    assert tmp_app.get("/api/advisor/messages").json() == []
    assert tmp_app.get("/api/opportunities").json() == []
    assert tmp_app.get("/api/monitor/runs").json() == []
    health = tmp_app.get("/api/monitor/health").json()
    assert health["ok"] is True
    assert health["failed_runs"] == 0
    assert health["last_failures"] == []


def test_opportunity_response_schema_and_no_secrets(
    keyed_app: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _seed_opportunity(keyed_app, monkeypatch, "https://www.tudelft.nl/jobs/phd-schema")
    row = keyed_app.get("/api/opportunities").json()[0]
    assert set(row.keys()) == OPPORTUNITY_KEYS
    assert isinstance(row["rule_fit"], (int, float))
    assert row["llm_fit"] is None or isinstance(row["llm_fit"], (int, float))
    assert row["shortlisted"] in (0, 1)
    blob = json.dumps(row)
    assert "sk-" not in blob
    assert "api_key" not in blob
    assert "extracted_text" not in blob


def test_document_response_schema_keys(tmp_app: TestClient) -> None:
    res = tmp_app.post(
        "/api/documents/upload",
        data={"doc_type": "other"},
        files={"file": ("note.md", b"hello research", "text/markdown")},
    )
    assert res.status_code == 200
    body = res.json()
    assert set(body.keys()) == DOCUMENT_KEYS
    assert "extracted_text" not in body
    assert "parsed_facts" not in body


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def test_chat_rejects_too_long_and_non_string(keyed_app: TestClient) -> None:
    too_long = keyed_app.post("/api/advisor/chat", json={"message": "x" * 4001})
    assert too_long.status_code == 422
    wrong_type = keyed_app.post("/api/advisor/chat", json={"message": 123})
    assert wrong_type.status_code == 422
    null_msg = keyed_app.post("/api/advisor/chat", json={"message": None})
    assert null_msg.status_code == 422


def test_discovery_rejects_empty_and_non_string(keyed_app: TestClient) -> None:
    assert keyed_app.post("/api/discovery/runs", json={"query": ""}).status_code == 422
    assert keyed_app.post("/api/discovery/runs", json={"query": "ab"}).status_code == 422
    assert keyed_app.post("/api/discovery/runs", json={"query": 12}).status_code == 422
    assert keyed_app.post("/api/discovery/runs", json={}).status_code == 422


def test_shortlist_validation(keyed_app: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    opp_id = _seed_opportunity(keyed_app, monkeypatch, "https://www.tudelft.nl/jobs/phd-sl-val")
    # Pydantic v2 coerces common truthy strings → bool (documented quality finding).
    coerced = keyed_app.post(f"/api/opportunities/{opp_id}/shortlist", json={"shortlisted": "yes"})
    assert coerced.status_code == 200
    assert coerced.json()["shortlisted"] == 1
    bad = keyed_app.post(f"/api/opportunities/{opp_id}/shortlist", json={"shortlisted": ["nope"]})
    assert bad.status_code == 422
    missing_body = keyed_app.post(f"/api/opportunities/{opp_id}/shortlist", json={})
    # default shortlisted=True on schema → should succeed
    assert missing_body.status_code == 200
    assert missing_body.json()["shortlisted"] == 1


def test_upload_rejects_oversized_file(tmp_app: TestClient) -> None:
    huge = b"a" * (15 * 1024 * 1024 + 1)
    res = tmp_app.post(
        "/api/documents/upload",
        data={"doc_type": "other"},
        files={"file": ("big.md", huge, "text/markdown")},
    )
    assert res.status_code == 400
    assert "large" in res.json()["detail"].lower()


def test_path_params_reject_injection_shapes(tmp_app: TestClient) -> None:
    assert tmp_app.delete("/api/documents/1;DROP%20TABLE").status_code == 422
    assert (
        tmp_app.post("/api/opportunities/abc/shortlist", json={"shortlisted": True}).status_code
        == 422
    )
    assert (
        tmp_app.post("/api/opportunities/-1/shortlist", json={"shortlisted": True}).status_code
        == 404
    )


# ---------------------------------------------------------------------------
# CORS / methods / content-type
# ---------------------------------------------------------------------------


def test_cors_preflight_allows_configured_origin(tmp_app: TestClient) -> None:
    res = tmp_app.options(
        "/api/llm/status",
        headers={
            "Origin": "http://127.0.0.1:5173",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert res.status_code in {200, 204}
    assert res.headers.get("access-control-allow-origin") == "http://127.0.0.1:5173"


def test_cors_rejects_unknown_origin_echo(tmp_app: TestClient) -> None:
    res = tmp_app.get("/health", headers={"Origin": "https://evil.example"})
    # Starlette CORS: unknown origins should not be reflected
    assert res.headers.get("access-control-allow-origin") != "https://evil.example"


def test_wrong_methods_return_405(tmp_app: TestClient) -> None:
    assert tmp_app.put("/api/profile").status_code == 405
    assert tmp_app.delete("/api/opportunities").status_code == 405
    assert tmp_app.get("/api/discovery/runs").status_code == 405
    assert tmp_app.patch("/api/documents/1").status_code == 405


# ---------------------------------------------------------------------------
# Auth posture (local-first: intentionally open)
# ---------------------------------------------------------------------------


def test_mutating_endpoints_remain_unauthenticated(
    tmp_app: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Documented local-first posture: no bearer/JWT gate today."""

    def fake_discover(query: str, settings, model_config):  # noqa: ANN001, ARG001
        return []

    monkeypatch.setattr("opportunity_intel.discovery.service.discover", fake_discover)
    for method, path, kwargs in (
        ("post", "/api/documents/import-folder", {}),
        ("post", "/api/advisor/chat", {"json": {"message": "hello there"}}),
        ("post", "/api/discovery/runs", {"json": {"query": "PhD agents"}}),
        ("post", "/api/profile/analyze", {}),
    ):
        res = getattr(tmp_app, method)(path, **kwargs)
        assert res.status_code != 401, path
        assert res.status_code != 403, path


# ---------------------------------------------------------------------------
# Business logic / CRUD lifecycle
# ---------------------------------------------------------------------------


def test_document_upload_list_delete_lifecycle(tmp_app: TestClient) -> None:
    created = tmp_app.post(
        "/api/documents/upload",
        data={"doc_type": "research_proposal"},
        files={"file": ("proposal.md", b"# Proposal\nagent security", "text/markdown")},
    )
    assert created.status_code == 200
    doc_id = created.json()["id"]
    listed = tmp_app.get("/api/documents").json()
    assert any(row["id"] == doc_id for row in listed)
    assert listed[0]["doc_type"] == "research_proposal"
    deleted = tmp_app.delete(f"/api/documents/{doc_id}")
    assert deleted.status_code == 200
    assert all(row["id"] != doc_id for row in tmp_app.get("/api/documents").json())


def test_discovery_upsert_is_idempotent_on_source_url(
    keyed_app: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    url = "https://www.tudelft.nl/jobs/phd-idempotent"

    def fake_discover(query: str, settings, model_config):  # noqa: ANN001, ARG001
        return [_nl_listing(url)]

    monkeypatch.setattr("opportunity_intel.discovery.service.discover", fake_discover)
    first = keyed_app.post("/api/discovery/runs", json={"query": "PhD agents one"})
    second = keyed_app.post("/api/discovery/runs", json={"query": "PhD agents two"})
    assert first.status_code == 200 and second.status_code == 200
    opps = keyed_app.get("/api/opportunities").json()
    matching = [o for o in opps if o["source_url"] == url]
    assert len(matching) == 1


def test_shortlist_sorts_to_top(keyed_app: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_discover(query: str, settings, model_config):  # noqa: ANN001, ARG001
        return [
            _nl_listing("https://www.tudelft.nl/jobs/phd-a"),
            RawListing(
                title="PhD Responsible AI Systems",
                source_url="https://www.ethz.ch/jobs/phd-b",
                organization="ETH Zurich",
                location="Switzerland",
                summary="Fully funded doctoral vacancy",
                source="test",
                funding="fully funded",
            ),
        ]

    monkeypatch.setattr("opportunity_intel.discovery.service.discover", fake_discover)
    keyed_app.post("/api/discovery/runs", json={"query": "PhD responsible AI"})
    opps = keyed_app.get("/api/opportunities").json()
    assert len(opps) == 2
    second_id = opps[1]["id"]
    keyed_app.post(f"/api/opportunities/{second_id}/shortlist", json={"shortlisted": True})
    ordered = keyed_app.get("/api/opportunities").json()
    assert ordered[0]["id"] == second_id
    assert ordered[0]["shortlisted"] == 1


def test_discovery_persists_error_on_pipeline_failure(
    keyed_app: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    def boom(query: str, settings, model_config):  # noqa: ANN001, ARG001
        raise RuntimeError("upstream search failed")

    monkeypatch.setattr("opportunity_intel.discovery.service.discover", boom)
    res = keyed_app.post("/api/discovery/runs", json={"query": "PhD agents fail"})
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "failed"
    assert "upstream search failed" in body["error"]
    assert "Traceback" not in body["error"]


# ---------------------------------------------------------------------------
# LLM / AI failure modes
# ---------------------------------------------------------------------------


def test_analyze_maps_llm_failure_to_500(
    keyed_app: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    keyed_app.post(
        "/api/documents/upload",
        data={"doc_type": "academic_cv"},
        files={"file": ("cv.md", b"Chandan Kumar\nMSc", "text/markdown")},
    )

    def fail_build(*args, **kwargs):  # noqa: ANN002, ANN003
        raise RuntimeError("provider down")

    monkeypatch.setattr(
        "opportunity_intel.api.routes.build_profile_from_documents",
        fail_build,
    )
    res = keyed_app.post("/api/profile/analyze")
    assert res.status_code == 500
    assert "provider down" in res.json()["detail"]


def test_analyze_maps_budget_exceeded_to_503(
    keyed_app: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    keyed_app.post(
        "/api/documents/upload",
        data={"doc_type": "academic_cv"},
        files={"file": ("cv.md", b"Chandan Kumar\nMSc", "text/markdown")},
    )

    def budget_fail(*args, **kwargs):  # noqa: ANN002, ANN003
        raise BudgetExceeded("Daily LLM budget $2.00 exceeded")

    monkeypatch.setattr(
        "opportunity_intel.api.routes.build_profile_from_documents",
        budget_fail,
    )
    res = keyed_app.post("/api/profile/analyze")
    assert res.status_code == 503
    assert "budget" in res.json()["detail"].lower()


def test_analyze_maps_per_document_llm_failure_to_400(
    keyed_app: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Extract failures are absorbed per document; empty parse set → 400."""
    keyed_app.post(
        "/api/documents/upload",
        data={"doc_type": "academic_cv"},
        files={"file": ("cv.md", b"Chandan Kumar\nMSc", "text/markdown")},
    )

    def fail_complete(self, role: str, messages: list, json_mode: bool = False) -> CompletionResult:  # noqa: ARG001
        raise RuntimeError("provider down")

    monkeypatch.setattr("opportunity_intel.agents.advisor.LLMRouter.complete", fail_complete)
    res = keyed_app.post("/api/profile/analyze")
    assert res.status_code == 400
    assert "document" in res.json()["detail"].lower()


def test_chat_maps_llm_failure_to_500(
    keyed_app: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fail_complete(self, role: str, messages: list, json_mode: bool = False) -> CompletionResult:  # noqa: ARG001
        raise TimeoutError("llm timeout")

    monkeypatch.setattr("opportunity_intel.agents.advisor.LLMRouter.complete", fail_complete)
    res = keyed_app.post("/api/advisor/chat", json={"message": "Which topic first?"})
    assert res.status_code == 500
    assert "timeout" in res.json()["detail"].lower()


def test_chat_rejects_malformed_json_body(keyed_app: TestClient) -> None:
    res = keyed_app.post(
        "/api/advisor/chat",
        content="{not-json",
        headers={"Content-Type": "application/json"},
    )
    assert res.status_code == 422


# ---------------------------------------------------------------------------
# Security / mass assignment / excessive exposure
# ---------------------------------------------------------------------------


def test_shortlist_ignores_mass_assignment_fields(
    keyed_app: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    opp_id = _seed_opportunity(keyed_app, monkeypatch, "https://www.tudelft.nl/jobs/phd-mass")
    before = keyed_app.get("/api/opportunities").json()[0]
    res = keyed_app.post(
        f"/api/opportunities/{opp_id}/shortlist",
        json={
            "shortlisted": True,
            "rule_fit": 99.9,
            "title": "Hacked",
            "status": "admin",
            "llm_fit": 100,
        },
    )
    assert res.status_code == 200
    after = res.json()
    assert after["shortlisted"] == 1
    assert after["title"] == before["title"]
    assert after["rule_fit"] == before["rule_fit"]
    assert after["status"] == before["status"]


def test_llm_status_booleans_with_keys_present(keyed_app: TestClient) -> None:
    body = keyed_app.get("/api/llm/status").json()
    assert body["deepseek_configured"] is True
    assert body["groq_configured"] is True
    assert "sk-test" not in json.dumps(body)
    assert "gsk_test" not in json.dumps(body)


def test_monitor_health_after_traced_failure(tmp_app: TestClient) -> None:
    from opportunity_intel.observability.trace import agent_run

    try:
        with agent_run("api_suite", "fail", "probe"):
            raise RuntimeError("probe failure")
    except RuntimeError:
        pass
    health = tmp_app.get("/api/monitor/health").json()
    assert "failed_runs" in health
    assert isinstance(health["last_failures"], list)
    runs = tmp_app.get("/api/monitor/runs").json()
    assert isinstance(runs, list)
