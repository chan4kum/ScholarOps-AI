"""Deterministic nightly digest. No LLM."""

from __future__ import annotations

from datetime import date, timedelta

from opportunity_intel.domain.models import Opportunity


def effective_fit(row: Opportunity) -> float:
    if row.llm_fit is not None:
        return float(row.llm_fit)
    return float(row.rule_fit or 0.0)


def format_digest_line(
    *,
    high_fit_new: int,
    deadline_count: int,
    threshold: float = 80.0,
    deadline_days: int = 7,
) -> str:
    fit_word = "fit" if high_fit_new == 1 else "fits"
    deadline_word = "deadline" if deadline_count == 1 else "deadlines"
    thresh = int(threshold) if float(threshold).is_integer() else threshold
    return (
        f"{high_fit_new} new >{thresh}% {fit_word}; "
        f"{deadline_count} {deadline_word} in {deadline_days} days."
    )


def deadlines_within(
    rows: list[Opportunity],
    *,
    days: int,
    today: date | None = None,
) -> list[Opportunity]:
    today = today or date.today()
    until = today + timedelta(days=days)
    return [row for row in rows if row.deadline is not None and today <= row.deadline <= until]
