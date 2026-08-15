"""Phase 1 vacancy quality filters."""

from __future__ import annotations

from opportunity_intel.discovery.quality import (
    country_from_host,
    infer_country,
    is_keepable,
    is_phd_vacancy,
)
from opportunity_intel.discovery.sources import RawListing

ALLOWED = (
    "NL",
    "DE",
    "SE",
    "NO",
    "DK",
    "FI",
    "IS",
    "CH",
    "IT",
    "AE",
    "JP",
    "KR",
    "AU",
    "CA",
    "TH",
)
EXCLUDED = ("GB", "UK")


def _listing(**kwargs: object) -> RawListing:
    base = {
        "title": "PhD in Agentic AI",
        "source_url": "https://www.tudelft.nl/jobs/phd-agentic",
        "organization": "TU Delft",
        "location": "Netherlands",
        "summary": "Fully funded PhD vacancy on responsible agents",
        "source": "test",
        "funding": "fully funded",
    }
    base.update(kwargs)
    return RawListing(**base)  # type: ignore[arg-type]


def test_rejects_guides_and_directories() -> None:
    guide = _listing(
        title="A guide to PhD funding in Europe",
        summary="Overview of scholarships worldwide",
        source_url="https://example.com/guide",
    )
    assert is_phd_vacancy(guide) is False
    assert is_keepable(guide, allowed=ALLOWED, excluded=EXCLUDED) is False

    finder = _listing(
        title="PhD Positions",
        source_url="https://www.phdfinder.com/search",
        summary="Search PhD opportunities",
    )
    assert is_phd_vacancy(finder) is False


def test_requires_phd_hint() -> None:
    job = _listing(title="Research Engineer", summary="Industry ML role")
    assert is_phd_vacancy(job) is False


def test_drops_empty_country_when_allowlist_requires_country() -> None:
    orphan = _listing(
        title="PhD in AI Safety",
        organization="Unknown Lab",
        location="",
        source_url="https://example.com/jobs/phd-1",
        summary="Doctoral vacancy",
    )
    assert infer_country(orphan) == ""
    assert is_keepable(orphan, allowed=ALLOWED, excluded=EXCLUDED) is True
    assert is_keepable(orphan, allowed=(), excluded=()) is True


def test_host_tld_infers_country() -> None:
    assert country_from_host("https://www.tudelft.nl/vacancies/phd") == "NL"
    assert country_from_host("https://www.tum.de/jobs/phd") == "DE"
    listing = _listing(
        title="PhD Autonomous Agents",
        organization="University",
        location="",
        source_url="https://www.uu.nl/en/organisation/vacancies/phd",
        summary="Fully funded doctoral position",
    )
    assert infer_country(listing) == "NL"
    assert is_keepable(listing, allowed=ALLOWED, excluded=EXCLUDED) is True


def test_keeps_real_nl_vacancy() -> None:
    row = _listing()
    assert is_phd_vacancy(row) is True
    assert is_keepable(row, allowed=ALLOWED, excluded=EXCLUDED) is True


def test_excludes_uk() -> None:
    uk = _listing(
        title="PhD Responsible AI",
        organization="Oxford",
        location="United Kingdom",
        source_url="https://www.ox.ac.uk/jobs/phd",
        summary="Funded doctoral studentship",
    )
    assert is_keepable(uk, allowed=ALLOWED, excluded=EXCLUDED) is False
    assert is_keepable(uk, allowed=(), excluded=()) is True
