"""Pathfind, email send, and public-portal apply-as-me (no live network)."""

from __future__ import annotations

from opportunity_intel.apply.adapters import SubmitResult
from opportunity_intel.apply.email_send import EmailAdapter
from opportunity_intel.apply.pathfind import extract_path_from_html
from opportunity_intel.apply.portal import (
    PortalAdapter,
    _human_gate,
    _looks_like_captcha,
    _looks_like_login,
)
from opportunity_intel.config import Settings


def test_pathfind_prefers_mailto_over_listing() -> None:
    html = (
        '<p>Apply: <a href="mailto:apply@tudelft.nl">email</a> '
        'or <a href="/online-application">Apply now</a></p>'
    )
    path = extract_path_from_html(html, "https://www.tudelft.nl/vacancy/123")
    assert path.apply_email == "apply@tudelft.nl"
    assert path.channel == "email"
    assert path.recommended_adapter == "email"
    assert "online-application" in path.apply_url or path.apply_url == ""


def test_pathfind_keeps_uk_email_and_host() -> None:
    html = (
        '<a href="mailto:jobs@cam.ac.uk">apply</a> '
        '<a href="https://www.ox.ac.uk/apply-now">Apply</a>'
    )
    path = extract_path_from_html(html, "https://www.cam.ac.uk/job")
    assert path.apply_email == "jobs@cam.ac.uk"
    assert "ox.ac.uk" in path.apply_url
    assert path.recommended_adapter == "email"


def test_email_adapter_sends_when_apply_as_me() -> None:
    sent: list[object] = []
    settings = Settings(
        apply_as_me=True,
        smtp_host="smtp.test.local",
        smtp_from="chandan@example.com",
        apply_pathfind=False,
    )
    payload = {
        "apply_email": "pi@cam.ac.uk",
        "applicant_name": "Chandan Kumar",
        "applicant_email": "chandan@example.com",
        "position_title": "PhD Agentic AI",
        "organization": "Cambridge",
        "packet_id": 1,
        "opportunity_id": 1,
    }
    result = EmailAdapter(settings, smtp_send=sent.append).submit(payload)
    assert result.ok is True
    assert result.receipt.startswith("email:")
    assert sent


def test_email_adapter_fails_fast_when_apply_as_me_off() -> None:
    settings = Settings(
        apply_as_me=False,
        smtp_host="smtp.test.local",
        smtp_from="chandan@example.com",
        apply_pathfind=False,
    )
    blocked = EmailAdapter(settings).submit(
        {
            "apply_email": "pi@tudelft.nl",
            "applicant_name": "A",
            "applicant_email": "a@b.com",
            "position_title": "PhD",
        }
    )
    assert blocked.ok is False
    assert "APPLY_AS_ME" in blocked.error


def test_portal_human_gates_and_apply_as_me_off() -> None:
    html = '<form><input type="password" name="pw"><p>Sign in with SSO</p></form>'
    assert _looks_like_login(html) is True
    assert _looks_like_captcha('<div class="g-recaptcha"></div>') is True
    assert "CAPTCHA" in _human_gate('<div class="h-captcha"></div>')
    assert "payment" in _human_gate("Application fee via Stripe.com").lower()

    off = PortalAdapter(Settings(apply_as_me=False, apply_pathfind=False)).submit(
        {"apply_url": "https://www.cam.ac.uk/apply"}
    )
    assert off.ok is False
    assert "APPLY_AS_ME" in off.error

    def factory(_url: str, _payload: dict) -> SubmitResult:
        return SubmitResult(
            ok=False,
            receipt="",
            sent_summary="",
            error="Portal requires a login (password field).",
        )

    wall = PortalAdapter(
        Settings(apply_as_me=True, apply_pathfind=False),
        page_factory=factory,
    ).submit({"apply_url": "https://www.cam.ac.uk/apply"})
    assert wall.ok is False
    assert "login" in wall.error.lower()
