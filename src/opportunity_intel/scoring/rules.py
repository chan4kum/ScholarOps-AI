from __future__ import annotations

import re
from dataclasses import dataclass

COUNTRY_ALIASES: dict[str, str] = {
    "netherlands": "NL",
    "holland": "NL",
    "germany": "DE",
    "deutschland": "DE",
    "sweden": "SE",
    "norway": "NO",
    "denmark": "DK",
    "finland": "FI",
    "iceland": "IS",
    "switzerland": "CH",
    "swiss": "CH",
    "italy": "IT",
    "italia": "IT",
    "united arab emirates": "AE",
    "u.a.e": "AE",
    "uae": "AE",
    "dubai": "AE",
    "abu dhabi": "AE",
    "japan": "JP",
    "south korea": "KR",
    "republic of korea": "KR",
    "korea": "KR",
    "australia": "AU",
    "canada": "CA",
    "thailand": "TH",
    "united kingdom": "GB",
    "uk": "GB",
    "england": "GB",
    "scotland": "GB",
    "wales": "GB",
    "ireland": "IE",
}


KNOWN_ISO = frozenset(
    {
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
        "GB",
        "UK",
        "IE",
    }
)


def normalize_country(text: str) -> str:
    blob = text.strip().upper()
    if len(blob) == 2 and blob.isalpha():
        return "GB" if blob == "UK" else blob
    lowered = text.strip().lower()
    for name, code in COUNTRY_ALIASES.items():
        if name in lowered:
            return code
    for token in re.findall(r"\b[A-Z]{2}\b", blob):
        if token in KNOWN_ISO:
            return "GB" if token == "UK" else token
    return ""


def is_allowed_country(code: str, allowed: tuple[str, ...], excluded: tuple[str, ...]) -> bool:
    """Empty allowlist means worldwide. Empty exclude list means nothing is blocked."""
    normalized = "GB" if code.upper() == "UK" else code
    if normalized and normalized in excluded:
        return False
    if not allowed:
        return True
    if not normalized:
        return True
    return normalized in allowed


@dataclass
class ProfileSignals:
    interests: list[str]
    skills: list[str]
    require_funded: bool


def parse_csv(value: str) -> list[str]:
    return [part.strip().lower() for part in re.split(r"[,;/]", value) if part.strip()]


def rule_fit_score(
    *,
    title: str,
    summary: str,
    funding: str,
    country_code: str,
    profile: ProfileSignals,
    allowed_countries: tuple[str, ...],
    excluded_countries: tuple[str, ...],
) -> float:
    if not is_allowed_country(country_code, allowed_countries, excluded_countries):
        return 0.0
    haystack = f"{title} {summary}".lower()
    terms = [t for t in profile.interests + profile.skills if len(t) > 2]
    if not terms:
        overlap = 0.4
    else:
        hits = sum(1 for term in terms if term in haystack)
        overlap = hits / max(len(terms), 1)
    funded = any(token in funding.lower() for token in ("fund", "stipend", "salary", "fully"))
    if profile.require_funded and not funded:
        overlap *= 0.45
    elif funded:
        overlap = min(1.0, overlap + 0.15)
    return round(min(1.0, overlap) * 100, 1)
