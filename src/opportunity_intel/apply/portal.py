"""Fill a public application form in the browser as the user."""

from __future__ import annotations

from typing import Any

from opportunity_intel.apply.adapters import SubmitResult, _sent_summary
from opportunity_intel.config import Settings

_APPLY_BUTTON = (
    "Apply",
    "Submit",
    "Send",
    "Solliciteer",
    "Solliciteren",
    "Bewerben",
    "Absenden",
    "Postuler",
    "Envoyer",
)


class PortalAdapter:
    name = "portal"

    def __init__(self, settings: Settings, *, page_factory=None) -> None:  # noqa: ANN001
        self.settings = settings
        self._page_factory = page_factory

    def submit(self, payload: dict[str, Any]) -> SubmitResult:
        url = str(payload.get("apply_url") or payload.get("source_url") or "").strip()
        if not url.startswith("http"):
            return SubmitResult(
                ok=False,
                receipt="",
                sent_summary="",
                error="No apply URL found on the vacancy.",
            )
        if not self.settings.apply_as_me:
            return SubmitResult(
                ok=False,
                receipt="",
                sent_summary=_sent_summary(payload),
                error=f"APPLY_AS_ME is false. Enable it to submit the form at {url}.",
            )
        try:
            return self._fill_and_submit(url, payload)
        except Exception as exc:  # noqa: BLE001
            return SubmitResult(ok=False, receipt="", sent_summary="", error=str(exc))

    def _fill_and_submit(self, url: str, payload: dict[str, Any]) -> SubmitResult:
        if self._page_factory is not None:
            return self._page_factory(url, payload)
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            return SubmitResult(
                ok=False,
                receipt="",
                sent_summary="",
                error="Playwright is not installed. pip install -e '.[browser]'",
            )
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(url, wait_until="domcontentloaded", timeout=45000)
            html = page.content()
            wall = _human_gate(html)
            if wall:
                browser.close()
                return SubmitResult(ok=False, receipt="", sent_summary="", error=wall)
            _fill_common_fields(page, payload)
            clicked = _click_apply(page)
            title = page.title()
            final = page.url
            browser.close()
        if not clicked:
            return SubmitResult(
                ok=False,
                receipt="",
                sent_summary=_sent_summary(payload),
                error=f"Opened {url} but no Apply/Submit button was found.",
            )
        return SubmitResult(
            ok=True,
            receipt=f"portal:{final[:200]}",
            sent_summary=_sent_summary(payload) + f" via portal ({title[:80]})",
        )


def _looks_like_login(html: str) -> bool:
    lowered = html.lower()
    has_password = 'type="password"' in lowered or "type='password'" in lowered
    login_words = ("sign in", "log in", "login", "sso", "single sign")
    return has_password and any(word in lowered for word in login_words)


def _looks_like_captcha(html: str) -> bool:
    lowered = html.lower()
    markers = ("g-recaptcha", "h-captcha", "hcaptcha", "cf-turnstile", "captcha")
    return any(marker in lowered for marker in markers)


def _looks_like_payment(html: str) -> bool:
    lowered = html.lower()
    markers = ("application fee", "credit card", "stripe.com", "paypal", "payment required")
    return any(marker in lowered for marker in markers)


def _human_gate(html: str) -> str:
    if _looks_like_login(html):
        return (
            "Portal requires a login (password field). "
            "The agent cannot use your university account. "
            "Use the email path if the vacancy lists a contact."
        )
    if _looks_like_captcha(html):
        return "Portal shows a CAPTCHA. The agent will not solve it. Complete this step yourself."
    if _looks_like_payment(html):
        return "Portal asks for payment. The agent will not pay fees. Complete this step yourself."
    return ""


def _fill_common_fields(page: Any, payload: dict[str, Any]) -> None:
    mapping = {
        "name": str(payload.get("applicant_name") or ""),
        "full name": str(payload.get("applicant_name") or ""),
        "email": str(payload.get("applicant_email") or ""),
        "e-mail": str(payload.get("applicant_email") or ""),
    }
    for label, value in mapping.items():
        if not value:
            continue
        locator = page.get_by_label(label, exact=False)
        try:
            if locator.count() > 0:
                locator.first.fill(value, timeout=2000)
        except Exception:  # noqa: BLE001
            continue
    for selector in ("textarea", "textarea[name*='cover']", "textarea[name*='letter']"):
        try:
            box = page.locator(selector).first
            if box.count() > 0:
                box.fill(str(payload.get("research_interests") or "")[:2000], timeout=2000)
                break
        except Exception:  # noqa: BLE001
            continue


def _click_apply(page: Any) -> bool:
    for name in _APPLY_BUTTON:
        btn = page.get_by_role("button", name=name, exact=False)
        try:
            if btn.count() > 0:
                btn.first.click(timeout=3000)
                return True
        except Exception:  # noqa: BLE001
            continue
        link = page.get_by_role("link", name=name, exact=False)
        try:
            if link.count() > 0:
                link.first.click(timeout=3000)
                return True
        except Exception:  # noqa: BLE001
            continue
    return False
