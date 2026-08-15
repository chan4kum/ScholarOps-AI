"""Live UI smoke against the running Vite + API. Skip if servers are down."""

from __future__ import annotations

import os
import uuid

import httpx
import pytest

UI = os.environ.get("UI_BASE", "http://127.0.0.1:5173")
API = os.environ.get("API_BASE", "http://127.0.0.1:8000")


def _servers_up() -> bool:
    try:
        httpx.get(f"{API}/health", timeout=2.0).raise_for_status()
        httpx.get(UI, timeout=2.0).raise_for_status()
        return True
    except httpx.HTTPError:
        return False


pytestmark = pytest.mark.skipif(not _servers_up(), reason="API or Vite not running")


def test_tabs_advisor_input_and_tables() -> None:
    pytest.importorskip("playwright")
    from playwright.sync_api import expect, sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(UI, wait_until="domcontentloaded")
        expect(page.get_by_role("heading", name="ScholarOps AI")).to_be_visible()
        expect(page.get_by_role("button", name="Import all documents")).to_be_visible()

        page.get_by_role("button", name="Advisor").click()
        box = page.get_by_placeholder("Ask about a suggestion")
        expect(box).to_be_visible()
        expect(box).to_be_enabled()
        box.fill("Which suggestion should I pick first and why?")
        expect(box).to_have_value("Which suggestion should I pick first and why?")

        page.get_by_role("button", name="Monitor").click()
        expect(page.get_by_role("heading", name="Agent traces")).to_be_visible()

        page.get_by_role("button", name="Opportunities").click()
        expect(page.get_by_role("button", name="Discover")).to_be_enabled()
        expect(page.get_by_role("columnheader", name="Funding")).to_be_visible()
        expect(page.get_by_role("columnheader", name="Supervisor")).to_be_visible()
        expect(page.get_by_role("columnheader", name="Fit")).to_be_visible()

        page.get_by_role("button", name="Documents").click()
        expect(page.get_by_text("Your files")).to_be_visible()
        browser.close()


def test_advisor_send_gets_reply() -> None:
    pytest.importorskip("playwright")
    from playwright.sync_api import expect, sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(UI, wait_until="domcontentloaded")
        page.get_by_role("button", name="Advisor").click()
        box = page.get_by_placeholder("Ask about a suggestion")
        marker = f"live-ui-{uuid.uuid4().hex[:10]}"
        box.fill(f"In one sentence, what is my strongest PhD bet? {marker}")
        page.get_by_role("button", name="Send").click()
        expect(page.locator(".bubble.user").filter(has_text=marker).last).to_be_visible(
            timeout=120_000
        )
        expect(page.locator(".chat-log .bubble").nth(-1)).not_to_have_class("user")
        browser.close()
