"""Phase 3 apply: fill, validate, token, adapters (no live portals)."""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient
from helpers import seed_ready_packet

from opportunity_intel.apply.mapping import fill_form, payload_sha256, validate_payload
from opportunity_intel.apply.tokens import issue_token, parse_and_verify
from opportunity_intel.db import session_factory
from opportunity_intel.domain.models import (
    ApplicationPacket,
    EvidenceItem,
    Opportunity,
    UserProfile,
)

_seed_ready_packet = seed_ready_packet


def test_token_roundtrip_and_expiry() -> None:
    issued = issue_token(
        secret="s",
        application_id=7,
        payload_sha256="abc",
        ttl_seconds=60,
    )
    parse_and_verify(secret="s", token=issued.token, application_id=7, payload_sha256="abc")
    with pytest.raises(ValueError, match="expired"):
        parse_and_verify(
            secret="s",
            token=issued.token,
            application_id=7,
            payload_sha256="abc",
            now=issued.expires_at_unix + 1,
        )
    with pytest.raises(ValueError, match="Invalid"):
        parse_and_verify(secret="other", token=issued.token, application_id=7, payload_sha256="abc")
    with pytest.raises(ValueError, match="does not match"):
        parse_and_verify(secret="s", token=issued.token, application_id=99, payload_sha256="abc")


def test_validate_blocks_unknown_evidence() -> None:
    issues = validate_payload(
        {
            "packet_status": "ready",
            "applicant_name": "A",
            "applicant_email": "a@b.com",
            "highest_degree": "MSc",
            "cv_present": True,
            "cover_letter_present": True,
            "proposal_present": True,
            "country": "GB",
            "cited_evidence_ids": [9],
            "known_evidence_ids": [1],
        }
    )
    codes = {i["code"] for i in issues if i["level"] == "error"}
    assert "excluded_country" not in codes
    assert "unknown_evidence" in codes


def test_fill_form_is_deterministic(tmp_app: TestClient) -> None:
    packet_id = _seed_ready_packet(tmp_app)
    session = session_factory()()
    try:
        packet = session.get(ApplicationPacket, packet_id)
        assert packet is not None
        opp = session.get(Opportunity, packet.opportunity_id)
        profile = session.query(UserProfile).first()
        evidence = session.query(EvidenceItem).all()
        first = fill_form(profile=profile, opportunity=opp, packet=packet, evidence=evidence)
        second = fill_form(profile=profile, opportunity=opp, packet=packet, evidence=evidence)
        assert payload_sha256(first) == payload_sha256(second)
        assert first["applicant_name"] == "Chandan Kumar"
        assert first["publications_claimed"] is False
    finally:
        session.close()


def test_preview_request_approve_sandbox_and_audit(keyed_app: TestClient) -> None:
    packet_id = _seed_ready_packet(keyed_app)
    preview = keyed_app.get(f"/api/packets/{packet_id}/apply/preview")
    assert preview.status_code == 200, preview.text
    body = preview.json()
    assert body["can_request_approval"] is True
    assert "manual" in body["adapter_options"]
    assert "sandbox" in body["adapter_options"]
    assert "email" in body["adapter_options"]
    assert "portal" in body["adapter_options"]
    assert body["recommended_adapter"] == "email"

    denied = keyed_app.post(
        "/api/applications/1/approve",
        json={"token": "1.1.deadbeef." + ("a" * 64)},
    )
    assert denied.status_code in {403, 404}

    issued = keyed_app.post(
        f"/api/packets/{packet_id}/apply/request-approval",
        json={"adapter": "sandbox"},
    )
    assert issued.status_code == 200, issued.text
    token = issued.json()["token"]
    app_id = issued.json()["id"]
    assert issued.json()["status"] == "pending_approval"
    assert "token" not in keyed_app.get(f"/api/applications/{app_id}").json()

    reuse_fail = keyed_app.post(
        f"/api/applications/{app_id}/approve",
        json={"token": "not-a-valid-token-value-here"},
    )
    assert reuse_fail.status_code == 403

    ok = keyed_app.post(f"/api/applications/{app_id}/approve", json={"token": token})
    assert ok.status_code == 200, ok.text
    assert ok.json()["status"] == "submitted"
    assert ok.json()["receipt"].startswith("sandbox:")
    actions = {e["action"] for e in ok.json()["events"]}
    assert "request_approval" in actions
    assert "submitted" in actions
    assert "chandan@example.com" not in json.dumps(ok.json()["events"])

    again = keyed_app.post(f"/api/applications/{app_id}/approve", json={"token": token})
    assert again.status_code == 403

    listed = keyed_app.get("/api/applications").json()
    assert len(listed) == 1
    assert listed[0]["adapter"] == "sandbox"


def test_reject_invalidates_token(keyed_app: TestClient) -> None:
    packet_id = _seed_ready_packet(keyed_app)
    issued = keyed_app.post(
        f"/api/packets/{packet_id}/apply/request-approval",
        json={"adapter": "manual"},
    )
    app_id = issued.json()["id"]
    token = issued.json()["token"]
    rejected = keyed_app.post(
        f"/api/applications/{app_id}/reject",
        json={"reason": "Need to edit CV"},
    )
    assert rejected.status_code == 200
    assert rejected.json()["status"] == "rejected"
    blocked = keyed_app.post(f"/api/applications/{app_id}/approve", json={"token": token})
    assert blocked.status_code == 403


def test_http_form_adapter_refuses_remote_hosts() -> None:
    from opportunity_intel.apply.adapters import HttpFormAdapter

    result = HttpFormAdapter(
        "https://example.com/apply",
        live_submit=True,
    ).submit({"applicant_name": "X"})
    assert result.ok is False
    assert "localhost" in result.error

    disabled = HttpFormAdapter("http://127.0.0.1:9/apply", live_submit=False).submit({})
    assert disabled.ok is False
