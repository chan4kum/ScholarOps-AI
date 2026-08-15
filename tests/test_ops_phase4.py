"""Phase 4 ops: digest, nightly, tracker, MCP tools, webhook secret."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import date, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from opportunity_intel.api.app import create_app
from opportunity_intel.config import Settings
from opportunity_intel.db import reset_engine, session_factory
from opportunity_intel.discovery.sources import RawListing
from opportunity_intel.domain.models import Opportunity, UserProfile
from opportunity_intel.ops.digest import format_digest_line


@contextmanager
def _noop_agent_run(*_args, **_kwargs):
    yield "test-run"


def test_digest_line_matches_phase4_gate() -> None:
    assert format_digest_line(high_fit_new=3, deadline_count=1) == (
        "3 new >80% fits; 1 deadline in 7 days."
    )
    assert format_digest_line(high_fit_new=1, deadline_count=0) == (
        "1 new >80% fit; 0 deadlines in 7 days."
    )


def test_ops_empty_contracts(tmp_app: TestClient) -> None:
    assert tmp_app.get("/api/ops/digest").status_code == 200
    assert tmp_app.get("/api/ops/digest").json() is None
    assert tmp_app.get("/api/notifications").json() == []
    tracker = tmp_app.get("/api/ops/tracker")
    assert tracker.status_code == 200
    body = tracker.json()
    assert body["packets_ready"] == 0
    assert body["last_digest"] is None
    tools = tmp_app.get("/api/ops/tools")
    assert tools.status_code == 200
    names = tools.json()["tools"]
    assert "db.list_opportunities" in names
    assert "notify.preview_digest" in names


def test_nightly_refreshes_and_formats_digest(
    keyed_app: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from opportunity_intel.db import session_factory as factory

    session = factory()()
    try:
        session.add(
            UserProfile(
                full_name="Chandan Kumar",
                research_interests="Agentic AI",
                skills="",
                funding_requirement="fully_funded",
            )
        )
        session.commit()
    finally:
        session.close()

    def fake_discover(query: str, settings, model_config):  # noqa: ANN001, ARG001
        return [
            RawListing(
                title="PhD Agentic AI Governance",
                source_url="https://www.tudelft.nl/jobs/phd-nightly",
                organization="TU Delft",
                location="Netherlands",
                summary="Fully funded PhD vacancy on agentic AI",
                source="test",
                funding="fully funded",
                supervisor="Ada Lovelace",
            )
        ]

    monkeypatch.setattr("opportunity_intel.discovery.service.discover", fake_discover)
    monkeypatch.setattr("opportunity_intel.ops.nightly.agent_run", _noop_agent_run)
    monkeypatch.setattr("opportunity_intel.discovery.service.agent_run", _noop_agent_run)

    res = keyed_app.post("/api/ops/nightly", json={"query": "PhD Agentic AI", "run_search": True})
    assert res.status_code == 200, res.text
    body = res.json()
    assert "new >80%" in body["message"]
    assert "in 7 days" in body["message"]
    assert body["high_fit_new_count"] >= 1
    digest = keyed_app.get("/api/ops/digest").json()
    assert digest["id"] == body["id"]
    notices = keyed_app.get("/api/notifications").json()
    assert notices
    assert notices[0]["channel"] == "telegram" or any(n["channel"] == "log" for n in notices)
    tracker = keyed_app.get("/api/ops/tracker").json()
    assert tracker["last_digest"]["message"] == body["message"]


def test_nightly_counts_deadlines_without_search(
    keyed_app: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("opportunity_intel.ops.nightly.agent_run", _noop_agent_run)
    session = session_factory()()
    try:
        session.add(
            Opportunity(
                title="PhD deadline soon",
                organization="TU Delft",
                country_code="NL",
                source_url="https://www.tudelft.nl/jobs/phd-deadline",
                funding="fully funded",
                deadline=date.today() + timedelta(days=3),
                rule_fit=90.0,
            )
        )
        session.commit()
    finally:
        session.close()
    res = keyed_app.post("/api/ops/nightly", json={"run_search": False})
    assert res.status_code == 200, res.text
    assert res.json()["deadline_count"] == 1
    assert "1 deadline in 7 days" in res.json()["message"]
    assert res.json()["high_fit_new_count"] == 0


def test_ops_tools_validation(tmp_app: TestClient) -> None:
    unknown = tmp_app.post("/api/ops/tools", json={"name": "shell.exec", "arguments": {}})
    assert unknown.status_code == 400
    bad_limit = tmp_app.post(
        "/api/ops/tools",
        json={"name": "db.list_opportunities", "arguments": {"limit": 999}},
    )
    assert bad_limit.status_code == 400
    ok = tmp_app.post("/api/ops/tools", json={"name": "notify.preview_digest", "arguments": {}})
    assert ok.status_code == 200
    assert "new >80%" in ok.json()["result"]["message"]
    files = tmp_app.post("/api/ops/tools", json={"name": "files.list_import_dir"})
    assert files.status_code == 200
    assert files.json()["result"]["exists"] is True


def test_ops_webhook_secret_required(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("opportunity_intel.ops.nightly.agent_run", _noop_agent_run)
    reset_engine()
    settings = Settings(
        database_url=f"sqlite+pysqlite:///{tmp_path / 'api.db'}",
        uploads_dir=tmp_path / "uploads",
        documents_import_dir=tmp_path / "phd",
        apply_signing_secret="test-hmac-secret",
        ops_webhook_secret="ops-secret-test",
        cors_origins="http://127.0.0.1:5173",
        enable_llm_enrich=False,
    )
    (tmp_path / "phd").mkdir()
    (tmp_path / "uploads").mkdir()
    app = create_app(settings)
    with TestClient(app) as client:
        denied = client.post("/api/ops/nightly", json={"run_search": False})
        assert denied.status_code == 401
        ok = client.post(
            "/api/ops/nightly",
            json={"run_search": False},
            headers={"X-Ops-Secret": "ops-secret-test"},
        )
        assert ok.status_code == 200, ok.text
    reset_engine()
