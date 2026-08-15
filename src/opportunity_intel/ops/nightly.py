"""Nightly ops cycle: refresh listings, then notify. n8n must not duplicate this."""

from __future__ import annotations

from sqlalchemy.orm import Session

from opportunity_intel.config import Settings
from opportunity_intel.discovery.service import run_discovery
from opportunity_intel.domain.models import (
    NightlyDigest,
    Notification,
    Opportunity,
    UserProfile,
)
from opportunity_intel.llm.models_config import AppModelConfig
from opportunity_intel.observability.trace import agent_run
from opportunity_intel.ops.digest import deadlines_within, effective_fit, format_digest_line
from opportunity_intel.ops.notify import dispatch


def discovery_query(profile: UserProfile | None, settings: Settings) -> str:
    interests = (profile.research_interests if profile else "") or ""
    blob = interests.strip()
    if len(blob) >= 3:
        return f"funded PhD {blob}"[:500]
    return settings.ops_discovery_query[:500]


def run_nightly_cycle(
    session: Session,
    settings: Settings,
    model_config: AppModelConfig,
    *,
    query: str | None = None,
    run_search: bool = True,
) -> NightlyDigest:
    profile = session.query(UserProfile).order_by(UserProfile.id).first()
    q = (query or discovery_query(profile, settings)).strip()
    before_ids = {row_id for (row_id,) in session.query(Opportunity.id).all()}

    digest = NightlyDigest(query=q, channel="log", sent=0)
    session.add(digest)
    session.flush()

    with agent_run("notification", "nightly", q):
        if run_search:
            run_discovery(session, q, model_config, settings)
        rows = session.query(Opportunity).order_by(Opportunity.id.desc()).all()
        new_rows = [row for row in rows if row.id not in before_ids]
        high_new = [row for row in new_rows if effective_fit(row) > settings.ops_high_fit_threshold]
        deadlines = deadlines_within(rows, days=settings.ops_deadline_days)
        message = format_digest_line(
            high_fit_new=len(high_new),
            deadline_count=len(deadlines),
            threshold=settings.ops_high_fit_threshold,
            deadline_days=settings.ops_deadline_days,
        )
        digest.query = q
        digest.new_count = len(new_rows)
        digest.high_fit_new_count = len(high_new)
        digest.deadline_count = len(deadlines)
        digest.message = message

        titles = [row.title for row in high_new[:8]]
        deadline_titles = [f"{row.title} ({row.deadline})" for row in deadlines[:8]]
        long_body = message
        if titles:
            long_body += "\nHigh fit: " + "; ".join(titles)
        if deadline_titles:
            long_body += "\nDeadlines: " + "; ".join(deadline_titles)

        results = dispatch(long_body, settings)
        sent_any = False
        errors: list[str] = []
        channels: list[str] = []
        for result in results:
            channels.append(result.channel)
            skipped = result.error.startswith("skipped")
            status = "skipped" if skipped else ("sent" if result.ok else "failed")
            if result.ok and not skipped:
                sent_any = True
            if result.error:
                errors.append(f"{result.channel}: {result.error}")
            session.add(
                Notification(
                    channel=result.channel,
                    body=long_body[:4000],
                    status=status,
                    error=result.error,
                )
            )
        digest.channel = ",".join(channels) or "log"
        digest.sent = 1 if sent_any else 0
        digest.error = "; ".join(errors)
        session.commit()
        session.refresh(digest)
        return digest
