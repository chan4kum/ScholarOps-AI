"""Allowlisted ops tools. Validated arguments only. No shell, SQL, or filesystem glob."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from sqlalchemy.orm import Session, selectinload

from opportunity_intel.config import Settings
from opportunity_intel.documents.import_folder import iter_importable_files, resolve_import_dir
from opportunity_intel.domain.models import Application, ApplicationPacket, Opportunity
from opportunity_intel.ops.digest import deadlines_within, effective_fit, format_digest_line


class ToolError(ValueError):
    pass


def _limit(raw: Any, default: int = 20, maximum: int = 50) -> int:
    try:
        value = int(raw if raw is not None else default)
    except (TypeError, ValueError) as exc:
        raise ToolError("limit must be an integer") from exc
    if value < 1 or value > maximum:
        raise ToolError(f"limit must be between 1 and {maximum}")
    return value


def tool_db_list_opportunities(
    session: Session, arguments: dict[str, Any], settings: Settings
) -> dict[str, Any]:
    del settings
    limit = _limit(arguments.get("limit"), 20)
    rows = (
        session.query(Opportunity)
        .order_by(Opportunity.shortlisted.desc(), Opportunity.rule_fit.desc())
        .limit(limit)
        .all()
    )
    return {
        "items": [
            {
                "id": row.id,
                "title": row.title,
                "organization": row.organization,
                "country_code": row.country_code,
                "deadline": row.deadline.isoformat() if row.deadline else None,
                "fit": effective_fit(row),
                "shortlisted": row.shortlisted,
            }
            for row in rows
        ]
    }


def tool_db_list_applications(
    session: Session, arguments: dict[str, Any], settings: Settings
) -> dict[str, Any]:
    del settings
    limit = _limit(arguments.get("limit"), 20)
    rows = (
        session.query(Application)
        .options(selectinload(Application.events))
        .order_by(Application.id.desc())
        .limit(limit)
        .all()
    )
    return {
        "items": [
            {
                "id": row.id,
                "packet_id": row.packet_id,
                "status": row.status,
                "adapter": row.adapter,
                "receipt": row.receipt,
            }
            for row in rows
        ]
    }


def tool_db_deadlines(
    session: Session, arguments: dict[str, Any], settings: Settings
) -> dict[str, Any]:
    days = arguments.get("days", settings.ops_deadline_days)
    try:
        days_i = int(days)
    except (TypeError, ValueError) as exc:
        raise ToolError("days must be an integer") from exc
    if days_i < 1 or days_i > 90:
        raise ToolError("days must be between 1 and 90")
    rows = deadlines_within(
        session.query(Opportunity).filter(Opportunity.deadline.is_not(None)).all(),
        days=days_i,
    )
    rows = sorted(rows, key=lambda row: row.deadline or row.id)[:50]
    return {
        "days": days_i,
        "items": [
            {
                "id": row.id,
                "title": row.title,
                "deadline": row.deadline.isoformat() if row.deadline else None,
                "fit": effective_fit(row),
            }
            for row in rows
        ],
    }


def tool_files_list_import_dir(
    session: Session, arguments: dict[str, Any], settings: Settings
) -> dict[str, Any]:
    del session, arguments
    root = resolve_import_dir(settings)
    files = iter_importable_files(root) if root.is_dir() else []
    return {
        "folder": str(root),
        "exists": root.is_dir(),
        "names": [path.name for path in files[:50]],
        "count": len(files),
    }


def tool_notify_preview_digest(
    session: Session, arguments: dict[str, Any], settings: Settings
) -> dict[str, Any]:
    del arguments
    opps = session.query(Opportunity).all()
    high = [row for row in opps if effective_fit(row) > settings.ops_high_fit_threshold]
    deadlines = deadlines_within(opps, days=settings.ops_deadline_days)
    packets_ready = (
        session.query(ApplicationPacket).filter(ApplicationPacket.status == "ready").count()
    )
    return {
        "message": format_digest_line(
            high_fit_new=len(high),
            deadline_count=len(deadlines),
            threshold=settings.ops_high_fit_threshold,
            deadline_days=settings.ops_deadline_days,
        ),
        "packets_ready": packets_ready,
        "gmail_configured": False,
        "github_configured": bool(settings.github_token),
        "telegram_configured": bool(settings.telegram_bot_token and settings.telegram_chat_id),
    }


TOOL_HANDLERS: dict[str, Callable[[Session, dict[str, Any], Settings], dict[str, Any]]] = {
    "db.list_opportunities": tool_db_list_opportunities,
    "db.list_applications": tool_db_list_applications,
    "db.deadlines": tool_db_deadlines,
    "files.list_import_dir": tool_files_list_import_dir,
    "notify.preview_digest": tool_notify_preview_digest,
}


def list_tools() -> list[str]:
    return sorted(TOOL_HANDLERS)


def invoke_tool(
    name: str,
    arguments: dict[str, Any] | None,
    *,
    session: Session,
    settings: Settings,
) -> dict[str, Any]:
    if name not in TOOL_HANDLERS:
        raise ToolError(f"Unknown tool. Allowed: {', '.join(list_tools())}")
    args = arguments or {}
    if not isinstance(args, dict):
        raise ToolError("arguments must be an object")
    return TOOL_HANDLERS[name](session, args, settings)
