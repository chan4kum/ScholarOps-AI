"""Complete live UI E2E coverage against Vite + API. Skip if servers are down.

Browser is the source of truth: these tests drive Chromium against the running app.
"""

from __future__ import annotations

import json
import os
import re
import uuid
from pathlib import Path

import httpx
import pytest

UI = os.environ.get("UI_BASE", "http://127.0.0.1:5173")
API = os.environ.get("API_BASE", "http://127.0.0.1:8000")
SUPERVISOR_SEED = "Ada Lovelace"


def _servers_up() -> bool:
    try:
        httpx.get(f"{API}/health", timeout=2.0).raise_for_status()
        httpx.get(UI, timeout=2.0).raise_for_status()
        return True
    except httpx.HTTPError:
        return False


pytestmark = pytest.mark.skipif(not _servers_up(), reason="API or Vite not running")


@pytest.fixture()
def page():
    pytest.importorskip("playwright")
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1280, "height": 900})
        page = context.new_page()
        page.goto(UI, wait_until="networkidle")
        yield page
        browser.close()


def _ensure_supervised_opportunity() -> dict:
    """Return an opportunity with a supervisor name (seed via SQLite if needed)."""
    import sqlite3
    import time

    opps = httpx.get(f"{API}/api/opportunities", timeout=10.0).json()
    if not opps:
        pytest.skip("No opportunities in DB — run Discover first")
    for row in opps:
        if (row.get("supervisor") or "").strip():
            return row
    target = opps[0]
    db_path = Path("data/opportunity.db")
    if not db_path.exists():
        pytest.skip("Local SQLite DB not found for supervisor seed")
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "UPDATE opportunities SET supervisor = ? WHERE id = ?",
            (SUPERVISOR_SEED, target["id"]),
        )
        conn.commit()
    for _ in range(20):
        refreshed = httpx.get(f"{API}/api/opportunities", timeout=10.0).json()
        seeded = next(row for row in refreshed if row["id"] == target["id"])
        if (seeded.get("supervisor") or "").strip():
            return seeded
        time.sleep(0.25)
    pytest.skip("Live API did not reflect supervisor seed — restart API or check DB path")


def test_landing_brand_pills_and_documents_inventory(page) -> None:  # noqa: ANN001
    from playwright.sync_api import expect

    expect = expect
    expect(page.get_by_role("heading", name="ScholarOps AI")).to_be_visible()
    expect(page.get_by_text("DeepSeek ready")).to_be_visible()
    expect(page.get_by_text("Groq ready")).to_be_visible()
    expect(page.get_by_role("button", name="Documents", exact=True)).to_be_visible()
    expect(page.get_by_role("button", name="Advisor", exact=True)).to_be_visible()
    expect(page.get_by_role("button", name="Opportunities", exact=True)).to_be_visible()
    expect(page.get_by_role("button", name="Prepare", exact=True)).to_be_visible()
    expect(page.get_by_role("button", name="Apply", exact=True)).to_be_visible()
    expect(page.get_by_role("button", name="Ops", exact=True)).to_be_visible()
    expect(page.get_by_role("button", name="Monitor", exact=True)).to_be_visible()

    expect(page.get_by_role("heading", name="Import from your PHD folder")).to_be_visible()
    expect(page.get_by_role("button", name="Import all documents")).to_be_enabled()
    expect(page.get_by_role("heading", name=re.compile(r"Your files"))).to_be_visible()
    expect(page.get_by_role("button", name="Build profile and get suggestions")).to_be_enabled()
    expect(page.get_by_role("combobox")).to_be_visible()
    expect(page.locator('input[type="file"]')).to_be_attached()


def test_tab_navigation_and_active_content(page) -> None:  # noqa: ANN001
    from playwright.sync_api import expect

    page.get_by_role("button", name="Advisor").click()
    expect(page.get_by_role("heading", name="Research suggestions")).to_be_visible()
    expect(page.get_by_placeholder("Ask about a suggestion")).to_be_enabled()

    page.get_by_role("button", name="Opportunities").click()
    expect(page.get_by_role("button", name="Discover")).to_be_enabled()
    expect(page.get_by_role("columnheader", name="Fit")).to_be_visible()
    expect(page.get_by_role("columnheader", name="Funding")).to_be_visible()
    expect(page.get_by_role("columnheader", name="Supervisor")).to_be_visible()
    expect(page.get_by_role("columnheader", name="Deadline")).to_be_visible()
    expect(
        page.locator("nav.tabs").get_by_role("button", name="Prepare", exact=True)
    ).to_be_visible()

    page.locator("nav.tabs").get_by_role("button", name="Prepare", exact=True).click()
    expect(page.get_by_role("heading", name="Application packet")).to_be_visible()
    expect(page.get_by_text("the agent finds how to apply")).to_be_visible()

    page.locator("nav.tabs").get_by_role("button", name="Apply", exact=True).click()
    expect(page.get_by_role("heading", name="Apply as me")).to_be_visible()
    expect(page.get_by_text("single-use token")).to_be_visible()

    page.get_by_role("button", name="Monitor").click()
    expect(page.get_by_role("heading", name="Agent traces")).to_be_visible()
    expect(page.get_by_role("columnheader", name="Status")).to_be_visible()

    page.get_by_role("button", name="Ops").click()
    expect(page.get_by_role("heading", name="Nightly digest")).to_be_visible()
    expect(page.get_by_role("button", name="Run nightly now")).to_be_enabled()
    expect(page.get_by_role("heading", name="Application tracking")).to_be_visible()

    page.get_by_role("button", name="Documents").click()
    expect(page.get_by_text("Import from your PHD folder")).to_be_visible()


def test_ops_tab_digest_tracker_and_notifications(page) -> None:  # noqa: ANN001
    from playwright.sync_api import expect

    page.get_by_role("button", name="Ops").click()
    expect(page.get_by_role("heading", name="Nightly digest")).to_be_visible()
    expect(page.get_by_role("heading", name="Deadlines")).to_be_visible()
    expect(page.get_by_role("heading", name="Application tracking")).to_be_visible()
    expect(page.get_by_role("heading", name="Notifications")).to_be_visible()
    expect(page.get_by_role("button", name="Run nightly now")).to_be_enabled()


def test_import_idempotent_banner(page) -> None:  # noqa: ANN001
    from playwright.sync_api import expect

    page.get_by_role("button", name="Import all documents").click()
    expect(page.get_by_role("button", name="Importing...")).to_be_visible()
    expect(page.get_by_text(re.compile(r"Imported .*Skipped"))).to_be_visible(timeout=60_000)
    expect(page.get_by_role("button", name="Import all documents")).to_be_enabled()


def test_document_type_select_and_upload_valid_markdown(page, tmp_path: Path) -> None:  # noqa: ANN001
    from playwright.sync_api import expect

    page.get_by_role("combobox").select_option("other")
    expect(page.get_by_role("combobox")).to_have_value("other")

    sample = tmp_path / "ui_e2e_note.md"
    sample.write_text("# UI E2E note\nagentic AI governance", encoding="utf-8")
    before = httpx.get(f"{API}/api/documents", timeout=10.0).json()
    page.locator('input[type="file"]').set_input_files(str(sample))
    page.get_by_role("button", name="Upload").click()
    expect(page.get_by_text("Documents uploaded.")).to_be_visible(timeout=30_000)
    expect(page.get_by_text("ui_e2e_note.md")).to_be_visible()
    after = httpx.get(f"{API}/api/documents", timeout=10.0).json()
    assert len(after) == len(before) + 1

    # cleanup uploaded test file via UI Remove on that row
    row = page.locator("li.file-row").filter(has_text="ui_e2e_note.md")
    row.get_by_role("button", name="Remove").click()
    expect(page.get_by_text("ui_e2e_note.md")).to_have_count(0, timeout=15_000)


def test_upload_without_file_does_not_crash(page) -> None:  # noqa: ANN001
    from playwright.sync_api import expect

    page.get_by_role("button", name="Upload").click()
    # form handler returns early when no files selected
    expect(page.get_by_role("heading", name="ScholarOps AI")).to_be_visible()
    expect(page.locator("body")).not_to_contain_text("undefined")


def test_advisor_suggestions_and_empty_send_disabled(page) -> None:  # noqa: ANN001
    from playwright.sync_api import expect

    page.get_by_role("button", name="Advisor").click()
    suggestions = page.locator("article.suggestion")
    expect(suggestions.first).to_be_visible()
    assert suggestions.count() >= 1
    expect(suggestions.first.get_by_text("Why you:")).to_be_visible()
    expect(suggestions.first.get_by_text("Start here:")).to_be_visible()

    box = page.get_by_placeholder("Ask about a suggestion")
    expect(box).to_be_enabled()
    expect(page.get_by_role("button", name="Send")).to_be_disabled()
    box.fill("   ")
    expect(page.get_by_role("button", name="Send")).to_be_disabled()


def test_advisor_send_gets_reply(page) -> None:  # noqa: ANN001
    from playwright.sync_api import expect

    page.get_by_role("button", name="Advisor").click()
    box = page.get_by_placeholder("Ask about a suggestion")
    marker = f"ui-complete-chat-{uuid.uuid4().hex[:10]}"
    box.fill(f"In one short sentence, name one priority research track. {marker}")
    page.get_by_role("button", name="Send").click()
    expect(page.get_by_role("button", name="Thinking...")).to_be_visible()
    user_bubble = page.locator(".bubble.user").filter(has_text=marker)
    expect(user_bubble.last).to_be_visible(timeout=120_000)
    expect(page.locator(".chat-log .bubble").nth(-1)).not_to_have_class("user", timeout=120_000)
    expect(box).to_be_enabled()
    expect(box).to_have_value("")


def test_advisor_enter_sends_message(page) -> None:  # noqa: ANN001
    from playwright.sync_api import expect

    page.get_by_role("button", name="Advisor").click()
    box = page.get_by_placeholder("Ask about a suggestion")
    marker = f"ui-complete-enter-{uuid.uuid4().hex[:10]}"
    box.fill(f"Reply with OK only. {marker}")
    box.press("Enter")
    expect(page.locator(".bubble.user").filter(has_text=marker).last).to_be_visible(timeout=120_000)


def test_opportunities_table_and_shortlist_star(page) -> None:  # noqa: ANN001
    from playwright.sync_api import expect

    page.get_by_role("button", name="Opportunities").click()
    rows = page.locator("table.data-table tbody tr")
    if rows.count() == 0:
        pytest.skip("No opportunities in DB yet — discover separately")
    expect(rows.first).to_be_visible()
    expect(page.get_by_role("columnheader", name="Fit")).to_be_visible()
    star = rows.first.get_by_role("button", name=re.compile(r"Shortlist|Remove shortlist"))
    expect(star).to_be_visible()
    before = star.get_attribute("aria-label")
    star.click()
    page.wait_for_timeout(500)
    after = (
        page.locator("table.data-table tbody tr")
        .first.get_by_role("button", name=re.compile(r"Shortlist|Remove shortlist"))
        .get_attribute("aria-label")
    )
    assert before != after


def test_discover_search_updates_banner(page) -> None:  # noqa: ANN001
    from playwright.sync_api import expect

    page.get_by_role("button", name="Opportunities").click()
    query = page.locator("form.search-row input.control")
    expect(query).to_be_visible()
    query.fill("PhD Responsible AI Agentic AI governance")
    page.get_by_role("button", name="Discover").click()
    expect(page.get_by_role("button", name="Searching...")).to_be_visible()
    expect(page.get_by_text(re.compile(r"Run (completed|failed): found"))).to_be_visible(
        timeout=180_000
    )


def test_opportunity_source_links_have_href(page) -> None:  # noqa: ANN001
    from playwright.sync_api import expect

    page.get_by_role("button", name="Opportunities").click()
    links = page.locator("table.data-table tbody a[href^='http']")
    if links.count() == 0:
        pytest.skip("No opportunity links present")
    href = links.first.get_attribute("href")
    assert href and href.startswith("http")
    expect(links.first).to_be_visible()


def test_monitor_traces_table(page) -> None:  # noqa: ANN001
    from playwright.sync_api import expect

    page.get_by_role("button", name="Monitor").click()
    expect(page.get_by_role("heading", name="Agent traces")).to_be_visible()
    expect(page.get_by_text("agent-runs.jsonl")).to_be_visible()
    rows = page.locator("table.data-table tbody tr")
    # After prior actions there should be at least one run
    expect(rows.first).to_be_visible(timeout=10_000)


def test_refresh_preserves_documents_tab(page) -> None:  # noqa: ANN001
    from playwright.sync_api import expect

    page.reload(wait_until="networkidle")
    expect(page.get_by_role("heading", name="ScholarOps AI")).to_be_visible()
    expect(page.get_by_role("button", name="Import all documents")).to_be_visible()


def test_mobile_viewport_tabs_usable(page) -> None:  # noqa: ANN001
    from playwright.sync_api import expect

    page.set_viewport_size({"width": 390, "height": 844})
    page.reload(wait_until="networkidle")
    expect(page.get_by_role("heading", name="ScholarOps AI")).to_be_visible()
    page.get_by_role("button", name="Advisor").click()
    expect(page.get_by_placeholder("Ask about a suggestion")).to_be_visible()
    page.get_by_role("button", name="Opportunities").click()
    expect(page.get_by_role("button", name="Discover")).to_be_visible()


def test_no_critical_console_errors_on_load(page) -> None:  # noqa: ANN001
    errors: list[str] = []
    page.on("pageerror", lambda err: errors.append(str(err)))
    page.reload(wait_until="networkidle")
    page.get_by_role("button", name="Advisor").click()
    page.get_by_role("button", name="Opportunities").click()
    page.get_by_role("button", name="Monitor").click()
    critical = [e for e in errors if "ResizeObserver" not in e]
    assert critical == [], f"pageerrors: {critical}"


def test_build_profile_completes_with_mocked_analyze(page) -> None:  # noqa: ANN001
    from playwright.sync_api import expect

    mock_body = {
        "profile": {
            "id": 1,
            "full_name": "Chandan Kumar",
            "email": "",
            "highest_degree": "MSc Data Science",
            "research_interests": "Agentic AI",
            "skills": "Python, LangGraph",
            "funding_requirement": "fully_funded",
            "target_countries": "NL,DE",
            "notes": "",
            "profile_summary": "Mock profile for UI test.",
            "profile_source": "documents",
            "updated_at": "2026-08-15T00:00:00",
        },
        "suggestions": [
            {
                "id": 9001,
                "title": "Mock research track",
                "summary": "Responsible agentic systems.",
                "rationale": "Matches thesis and industry work.",
                "next_steps": "Read two recent papers.",
                "priority": "high",
            }
        ],
        "message": "Profile ready (mocked UI test).",
        "parsed_count": 1,
        "failed_count": 0,
    }

    def fulfill_analyze(route) -> None:  # noqa: ANN001
        route.fulfill(status=200, content_type="application/json", body=json.dumps(mock_body))

    page.route("**/api/profile/analyze", fulfill_analyze)
    page.reload(wait_until="networkidle")
    page.get_by_role("button", name="Build profile and get suggestions").click()
    expect(page.get_by_text("Profile ready (mocked UI test).")).to_be_visible(timeout=15_000)
    expect(page.get_by_role("heading", name="Research suggestions")).to_be_visible()
    page.locator("nav.tabs").get_by_role("button", name="Documents").click()
    expect(page.get_by_role("button", name="Build profile and get suggestions")).to_be_enabled()


def test_upload_rejects_unsupported_file_in_ui(page, tmp_path: Path) -> None:  # noqa: ANN001
    from playwright.sync_api import expect

    bad = tmp_path / "payload.exe"
    bad.write_bytes(b"MZ")
    before = len(httpx.get(f"{API}/api/documents", timeout=10.0).json())
    page.locator('input[type="file"]').set_input_files(str(bad))
    page.get_by_role("button", name="Upload").click()
    expect(page.locator(".banner.error")).to_contain_text("Unsupported", timeout=15_000)
    after = len(httpx.get(f"{API}/api/documents", timeout=10.0).json())
    assert after == before


def test_upload_rejects_empty_file_in_ui(page, tmp_path: Path) -> None:  # noqa: ANN001
    from playwright.sync_api import expect

    empty = tmp_path / "empty.md"
    empty.write_bytes(b"")
    before = len(httpx.get(f"{API}/api/documents", timeout=10.0).json())
    page.locator('input[type="file"]').set_input_files(str(empty))
    page.get_by_role("button", name="Upload").click()
    expect(page.locator(".banner.error")).to_contain_text("Empty", timeout=15_000)
    after = len(httpx.get(f"{API}/api/documents", timeout=10.0).json())
    assert after == before


def test_upload_rejects_oversized_file_in_ui(page, tmp_path: Path) -> None:  # noqa: ANN001
    from playwright.sync_api import expect

    huge = tmp_path / "too_big.md"
    with huge.open("wb") as handle:
        handle.write(b"x" * (15 * 1024 * 1024 + 1))
    before = len(httpx.get(f"{API}/api/documents", timeout=10.0).json())
    page.locator('input[type="file"]').set_input_files(str(huge))
    page.get_by_role("button", name="Upload").click()
    expect(page.locator(".banner.error")).to_contain_text("too large", timeout=30_000)
    after = len(httpx.get(f"{API}/api/documents", timeout=10.0).json())
    assert after == before


def test_prepare_with_supervisor_shows_pi_papers(page) -> None:  # noqa: ANN001
    from playwright.sync_api import expect

    opp = _ensure_supervised_opportunity()
    mock_paper = {
        "id": 1,
        "title": "Agentic Systems for Energy",
        "year": 2024,
        "authors": "Ada Lovelace",
        "venue": "AI Journal",
        "url": "https://example.org/paper",
    }
    mock_packet = {
        "id": 88001,
        "opportunity_id": opp["id"],
        "status": "ready",
        "error": "",
        "requirements": [
            {
                "id": 1,
                "text": "MSc in CS or related",
                "status": "met",
                "evidence_note": "EV-1 thesis",
            }
        ],
        "papers": [mock_paper],
        "drafts": [
            {
                "id": 1,
                "kind": "research_proposal",
                "body": "Proposal citing Agentic Systems for Energy and EV-1 thesis work.",
                "cited_evidence_ids": "[1]",
                "cited_paper_titles": '["Agentic Systems for Energy"]',
            }
        ],
    }

    def fulfill_prepare(route) -> None:  # noqa: ANN001
        route.fulfill(status=200, content_type="application/json", body=json.dumps(mock_packet))

    def fulfill_packets(route) -> None:  # noqa: ANN001
        route.fulfill(status=200, content_type="application/json", body=json.dumps([mock_packet]))

    page.route(f"**/api/opportunities/{opp['id']}/prepare", fulfill_prepare)
    page.route("**/api/packets", fulfill_packets)
    page.reload(wait_until="networkidle")
    page.locator("nav.tabs").get_by_role("button", name="Opportunities").click()
    row = page.locator("table.data-table tbody tr").filter(
        has=page.locator(f"a[href='{opp['source_url']}']")
    )
    expect(row).to_be_visible()
    row.get_by_role("button", name="Prepare").click()
    expect(page.get_by_text(re.compile(r"Packet ready:|Prepare failed"))).to_be_visible(
        timeout=15_000
    )
    page.locator("nav.tabs").get_by_role("button", name="Prepare", exact=True).click()
    expect(
        page.locator(".paper-list li").filter(has_text="Agentic Systems for Energy")
    ).to_be_visible()


def test_prepare_live_openalex_papers_for_supervisor() -> None:
    """API integration: real prepare returns PI papers when supervisor is set."""
    opp = _ensure_supervised_opportunity()
    res = httpx.post(f"{API}/api/opportunities/{opp['id']}/prepare", timeout=180.0)
    assert res.status_code == 200, res.text
    packet = res.json()
    assert packet["status"] == "ready", packet.get("error")
    if not packet.get("papers"):
        pytest.skip("OpenAlex returned no papers (network or name match)")
    assert packet["papers"][0].get("title")
