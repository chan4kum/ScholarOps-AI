"""Phase 2 prepare pipeline and API tests (mocked LLM / network)."""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from opportunity_intel.domain.models import EvidenceItem, UserProfile
from opportunity_intel.llm.router import CompletionResult
from opportunity_intel.prepare.papers import PaperHit, search_professor_papers


def test_search_professor_papers_empty_supervisor() -> None:
    assert search_professor_papers("") == []
    assert search_professor_papers("unknown") == []


def test_search_professor_papers_parses_openalex(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeResponse:
        status_code = 200

        def json(self) -> dict:
            return {
                "results": [
                    {
                        "display_name": "Agentic Systems for Energy",
                        "publication_year": 2024,
                        "authorships": [
                            {"author": {"display_name": "Ada Lovelace"}},
                            {"author": {"display_name": "Alan Turing"}},
                        ],
                        "primary_location": {
                            "landing_page_url": "https://example.org/paper",
                            "source": {"display_name": "AI Journal"},
                        },
                        "id": "https://openalex.org/W123",
                    }
                ]
            }

    monkeypatch.setattr(
        "opportunity_intel.prepare.papers.httpx.get",
        lambda *args, **kwargs: FakeResponse(),  # noqa: ARG005
    )
    hits = search_professor_papers("Ada Lovelace", "TU Delft")
    assert len(hits) == 1
    assert hits[0].title == "Agentic Systems for Energy"
    assert hits[0].year == 2024
    assert "Ada Lovelace" in hits[0].authors


def _seed_opp(keyed_app: TestClient, monkeypatch: pytest.MonkeyPatch) -> int:
    from opportunity_intel.discovery.sources import RawListing

    def fake_discover(query: str, settings, model_config):  # noqa: ANN001, ARG001
        return [
            RawListing(
                title="PhD Responsible AI",
                source_url="https://www.tudelft.nl/jobs/phd-prepare-test",
                organization="TU Delft",
                location="Netherlands",
                summary="Fully funded doctoral position",
                source="test",
                funding="fully funded",
                supervisor="Ada Lovelace",
                deadline=None,
            )
        ]

    monkeypatch.setattr("opportunity_intel.discovery.service.discover", fake_discover)
    res = keyed_app.post("/api/discovery/runs", json={"query": "PhD AI"})
    assert res.status_code == 200
    return int(keyed_app.get("/api/opportunities").json()[0]["id"])


def test_prepare_endpoint_builds_packet(
    keyed_app: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    opp_id = _seed_opp(keyed_app, monkeypatch)

    # Seed profile + evidence in DB via session
    from opportunity_intel.db import session_factory

    session = session_factory()()
    try:
        profile = UserProfile(
            full_name="Chandan Kumar",
            highest_degree="MSc Data Science",
            research_interests="Agentic AI",
            profile_summary="Master thesis on agents; no peer-reviewed publications.",
        )
        session.add(profile)
        session.add(
            EvidenceItem(
                category="thesis",
                content="MSc thesis on multi-agent orchestration",
                source_quote="thesis on agents",
            )
        )
        session.commit()
    finally:
        session.close()

    llm_calls: list[str] = []

    def fake_complete(self, role, messages, json_mode=False):  # noqa: ANN001, ARG001
        llm_calls.append(role)
        if role == "extract":
            payload = {
                "requirements": [
                    {"text": "Fully funded doctoral contract", "category": "funding"},
                    {"text": "MSc in CS or related", "category": "degree"},
                ]
            }
        elif role == "reason":
            payload = {
                "items": [
                    {
                        "text": "Fully funded doctoral contract",
                        "status": "met",
                        "evidence_note": "Advert states fully funded",
                    },
                    {
                        "text": "MSc in CS or related",
                        "status": "met",
                        "evidence_note": "EV-1 thesis + MSc profile",
                    },
                ]
            }
        else:
            payload = {
                "cv_tailor": "CV bullet citing EV-1 thesis work.",
                "cover_letter": "Motivated by the group's agent research.",
                "research_proposal": (
                    "Proposal grounded in PI paper Agentic Systems for Energy and EV-1 thesis."
                ),
                "cited_evidence_ids": [1],
                "cited_paper_titles": ["Agentic Systems for Energy"],
            }
        return CompletionResult(text=json.dumps(payload), model="mock", provider="test", role=role)

    monkeypatch.setattr("opportunity_intel.llm.router.LLMRouter.complete", fake_complete)
    monkeypatch.setattr(
        "opportunity_intel.prepare.service.fetch_page",
        lambda url: None,  # noqa: ARG005
    )
    monkeypatch.setattr(
        "opportunity_intel.prepare.service.search_professor_papers",
        lambda supervisor, organization="", **kwargs: [  # noqa: ARG005
            PaperHit(
                title="Agentic Systems for Energy",
                year=2024,
                authors="Ada Lovelace",
                venue="AI Journal",
                url="https://example.org/paper",
            )
        ],
    )

    res = keyed_app.post(f"/api/opportunities/{opp_id}/prepare")
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["status"] == "ready"
    assert len(body["requirements"]) >= 2
    assert body["requirements"][0]["status"] in {"met", "gap", "unknown"}
    assert len(body["papers"]) == 1
    assert body["papers"][0]["title"] == "Agentic Systems for Energy"
    kinds = {d["kind"] for d in body["drafts"]}
    assert kinds == {"cv_tailor", "cover_letter", "research_proposal"}
    proposal = next(d for d in body["drafts"] if d["kind"] == "research_proposal")
    assert "Agentic Systems for Energy" in proposal["body"]
    assert "EV-1" in proposal["body"] or "thesis" in proposal["body"].lower()
    assert "extract" in llm_calls and "reason" in llm_calls and "draft" in llm_calls

    list_res = keyed_app.get("/api/packets")
    assert list_res.status_code == 200
    assert len(list_res.json()) >= 1

    get_res = keyed_app.get(f"/api/packets/{body['id']}")
    assert get_res.status_code == 200
    assert get_res.json()["id"] == body["id"]


def test_prepare_missing_opportunity(keyed_app: TestClient) -> None:
    res = keyed_app.post("/api/opportunities/99999/prepare")
    assert res.status_code == 404


def test_prepare_requires_api_keys(tmp_app: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    opp_id = _seed_opp(tmp_app, monkeypatch)
    res = tmp_app.post(f"/api/opportunities/{opp_id}/prepare")
    assert res.status_code == 503


def _fake_complete_factory():
    def fake_complete(self, role, messages, json_mode=False):  # noqa: ANN001, ARG001
        if role == "extract":
            payload: dict = {
                "requirements": [{"text": "Fully funded doctoral contract", "category": "funding"}]
            }
        elif role == "reason":
            payload = {
                "items": [
                    {
                        "text": "Fully funded doctoral contract",
                        "status": "met",
                        "evidence_note": "Advert",
                    }
                ]
            }
        else:
            payload = {
                "cv_tailor": "CV",
                "cover_letter": "Cover",
                "research_proposal": "Proposal citing Agentic Systems for Energy",
                "cited_evidence_ids": [],
                "cited_paper_titles": ["Agentic Systems for Energy"],
            }
        return CompletionResult(text=json.dumps(payload), model="mock", provider="test", role=role)

    return fake_complete


def test_prepare_allows_concurrent_sqlite_writes_during_llm(
    keyed_app: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Prepare must not hold a SQLite write lock while waiting on the LLM."""
    from opportunity_intel.db import session_factory

    opp_id = _seed_opp(keyed_app, monkeypatch)
    inner = _fake_complete_factory()

    def fake_complete(self, role, messages, json_mode=False):  # noqa: ANN001, ARG001
        db = session_factory()()
        try:
            db.add(
                EvidenceItem(
                    category="lock-probe",
                    content="write while prepare waits on LLM",
                    source_quote="",
                )
            )
            db.commit()
        finally:
            db.close()
        return inner(self, role, messages, json_mode=json_mode)

    monkeypatch.setattr("opportunity_intel.llm.router.LLMRouter.complete", fake_complete)
    monkeypatch.setattr("opportunity_intel.prepare.service.fetch_page", lambda url: None)
    monkeypatch.setattr(
        "opportunity_intel.prepare.service.search_professor_papers",
        lambda supervisor, organization="", **kwargs: [
            PaperHit(
                title="Agentic Systems for Energy",
                year=2024,
                authors="Ada Lovelace",
                venue="AI Journal",
                url="https://example.org/paper",
            )
        ],
    )
    res = keyed_app.post(f"/api/opportunities/{opp_id}/prepare")
    assert res.status_code == 200, res.text
    assert res.json()["status"] == "ready"

    again = keyed_app.post(f"/api/opportunities/{opp_id}/prepare")
    assert again.status_code == 200, again.text
    assert again.json()["status"] == "ready"
    packets = keyed_app.get("/api/packets").json()
    assert len(packets) == 1
