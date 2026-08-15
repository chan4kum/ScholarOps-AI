from __future__ import annotations

from urllib.parse import urlparse

from opportunity_intel.discovery.sources import RawListing
from opportunity_intel.scoring.rules import normalize_country

PHD_HINTS = ("phd", "ph.d", "doctoral", "doctorate", "promovendus", "doktorand")

GUIDE_HINTS = (
    "a guide",
    "guide for",
    "an overview",
    "overview -",
    "how to apply",
    "how to find",
    "phd funding in",
    "scholarships -",
    "opportunities worldwide",
    "search phd",
    "what is a phd",
)

HOST_COUNTRY = {
    ".nl": "NL",
    ".de": "DE",
    ".se": "SE",
    ".no": "NO",
    ".dk": "DK",
    ".fi": "FI",
    ".is": "IS",
    ".ch": "CH",
    ".it": "IT",
    ".ae": "AE",
    ".jp": "JP",
    ".kr": "KR",
    ".au": "AU",
    ".ca": "CA",
    ".th": "TH",
    ".uk": "GB",
    ".ac.uk": "GB",
}


def country_from_host(url: str) -> str:
    host = (urlparse(url).hostname or "").lower()
    for suffix, code in HOST_COUNTRY.items():
        if host.endswith(suffix):
            return code
    return ""


def infer_country(listing: RawListing) -> str:
    return (
        listing.country_code
        or normalize_country(f"{listing.location} {listing.organization} {listing.title}")
        or country_from_host(listing.source_url)
    )


def is_phd_vacancy(listing: RawListing) -> bool:
    blob = f"{listing.title} {listing.summary}".lower()
    host = (urlparse(listing.source_url).hostname or "").lower()
    if "phdfinder.com" in host:
        return False
    if any(hint in blob for hint in GUIDE_HINTS):
        return False
    return any(hint in blob for hint in PHD_HINTS)


def is_keepable(
    listing: RawListing,
    *,
    allowed: tuple[str, ...],
    excluded: tuple[str, ...],
) -> bool:
    if not is_phd_vacancy(listing):
        return False
    country = infer_country(listing)
    if country and country in excluded:
        return False
    if allowed and country and country not in allowed:
        return False
    return True
