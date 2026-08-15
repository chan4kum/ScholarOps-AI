"""Application tracking snapshot for the Ops tab."""

from __future__ import annotations

from datetime import date

from sqlalchemy.orm import Session, selectinload

from opportunity_intel.config import Settings
from opportunity_intel.domain.models import (
    Application,
    ApplicationPacket,
    NightlyDigest,
    Notification,
    Opportunity,
)
from opportunity_intel.ops.digest import deadlines_within, effective_fit


def build_tracker(session: Session, settings: Settings) -> dict:
    opps = session.query(Opportunity).all()
    deadlines = deadlines_within(opps, days=settings.ops_deadline_days)
    packets = (
        session.query(ApplicationPacket)
        .options(selectinload(ApplicationPacket.opportunity))
        .order_by(ApplicationPacket.id.desc())
        .limit(50)
        .all()
    )
    apps = session.query(Application).order_by(Application.id.desc()).limit(50).all()
    last = session.query(NightlyDigest).order_by(NightlyDigest.id.desc()).first()
    return {
        "deadline_days": settings.ops_deadline_days,
        "high_fit_threshold": settings.ops_high_fit_threshold,
        "packets_ready": sum(1 for p in packets if p.status == "ready"),
        "applications_submitted": sum(1 for a in apps if a.status == "submitted"),
        "deadlines": [
            {
                "id": row.id,
                "title": row.title,
                "deadline": row.deadline.isoformat() if row.deadline else None,
                "fit": effective_fit(row),
                "days_left": (row.deadline - date.today()).days if row.deadline else None,
            }
            for row in deadlines
        ],
        "packets": [
            {
                "id": p.id,
                "opportunity_id": p.opportunity_id,
                "title": p.opportunity.title if p.opportunity else "",
                "status": p.status,
            }
            for p in packets
        ],
        "applications": [
            {
                "id": a.id,
                "packet_id": a.packet_id,
                "status": a.status,
                "adapter": a.adapter,
                "receipt": a.receipt,
            }
            for a in apps
        ],
        "last_digest": (
            {
                "id": last.id,
                "message": last.message,
                "query": last.query,
                "new_count": last.new_count,
                "high_fit_new_count": last.high_fit_new_count,
                "deadline_count": last.deadline_count,
                "channel": last.channel,
                "sent": last.sent,
                "error": last.error,
                "created_at": last.created_at,
            }
            if last
            else None
        ),
    }


def list_notifications(session: Session, limit: int = 50) -> list[Notification]:
    return session.query(Notification).order_by(Notification.id.desc()).limit(limit).all()
