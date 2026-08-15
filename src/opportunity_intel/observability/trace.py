from __future__ import annotations

import json
import logging
import re
import time
import uuid
from collections.abc import Generator
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from opportunity_intel.config import ROOT

_LOG = logging.getLogger("opportunity_intel")
_RUN_ID: ContextVar[str | None] = ContextVar("agent_run_id", default=None)
_SECRET = re.compile(
    r"(sk-[A-Za-z0-9_\-]+|gsk_[A-Za-z0-9]+|tvly-[A-Za-z0-9\-]+|hf_[A-Za-z0-9]+|"
    r"AIza[A-Za-z0-9_\-]+|AQ\.[A-Za-z0-9_\-]+)"
)


def redact(text: str) -> str:
    return _SECRET.sub("[redacted]", text)


def clip(text: str, limit: int = 800) -> str:
    text = redact(text.replace("\n", " ").strip())
    if len(text) <= limit:
        return text
    return text[:limit] + "…"


def logs_dir() -> Path:
    path = ROOT / "data" / "logs"
    path.mkdir(parents=True, exist_ok=True)
    return path


def jsonl_path() -> Path:
    return logs_dir() / "agent-runs.jsonl"


def current_run_id() -> str | None:
    return _RUN_ID.get()


def _write_jsonl(event: dict[str, Any]) -> None:
    event["ts"] = datetime.now(UTC).isoformat()
    line = json.dumps(event, ensure_ascii=True, default=str)
    with jsonl_path().open("a", encoding="utf-8") as handle:
        handle.write(line + "\n")
    if event.get("status") == "error" or event.get("event") == "error":
        _LOG.error("%s", line)
    else:
        _LOG.info("%s", line)


def _persist_run_start(run_id: str, agent: str, action: str, input_summary: str) -> None:
    try:
        from opportunity_intel.db import session_factory
        from opportunity_intel.domain.models import AgentRun

        db = session_factory()()
        db.add(
            AgentRun(
                id=run_id,
                agent=agent,
                action=action,
                status="running",
                input_summary=clip(input_summary, 1000),
            )
        )
        db.commit()
        db.close()
    except Exception:  # noqa: BLE001 — tracing must never break agents
        _LOG.debug("Could not persist agent run start", exc_info=True)


def _persist_span(run_id: str, name: str, status: str, detail: str, duration_ms: int) -> None:
    try:
        from opportunity_intel.db import session_factory
        from opportunity_intel.domain.models import AgentSpan

        db = session_factory()()
        db.add(
            AgentSpan(
                run_id=run_id,
                name=name,
                status=status,
                detail=clip(detail, 1500),
                duration_ms=duration_ms,
            )
        )
        db.commit()
        db.close()
    except Exception:  # noqa: BLE001
        _LOG.debug("Could not persist agent span", exc_info=True)


def _persist_run_end(
    run_id: str,
    status: str,
    error: str,
    output_summary: str,
    duration_ms: int,
) -> None:
    try:
        from opportunity_intel.db import session_factory
        from opportunity_intel.domain.models import AgentRun

        db = session_factory()()
        row = db.get(AgentRun, run_id)
        if row is not None:
            row.status = status
            row.error = clip(error, 2000)
            row.output_summary = clip(output_summary, 1500)
            row.duration_ms = duration_ms
            row.finished_at = datetime.now(UTC).replace(tzinfo=None)
            db.commit()
        db.close()
    except Exception:  # noqa: BLE001
        _LOG.debug("Could not persist agent run end", exc_info=True)


@contextmanager
def agent_run(agent: str, action: str, input_summary: str = "") -> Generator[str, None, None]:
    """One traced agent invocation. Writes JSONL + SQLite."""
    run_id = str(uuid.uuid4())
    token = _RUN_ID.set(run_id)
    started = time.perf_counter()
    _write_jsonl(
        {
            "event": "start",
            "run_id": run_id,
            "agent": agent,
            "action": action,
            "input": clip(input_summary),
        }
    )
    _persist_run_start(run_id, agent, action, input_summary)
    error = ""
    status = "ok"
    output = ""
    try:
        yield run_id
    except Exception as exc:
        status = "error"
        error = f"{type(exc).__name__}: {exc}"
        _write_jsonl(
            {
                "event": "error",
                "run_id": run_id,
                "agent": agent,
                "action": action,
                "error": clip(error, 2000),
            }
        )
        raise
    finally:
        duration_ms = int((time.perf_counter() - started) * 1000)
        _write_jsonl(
            {
                "event": "end",
                "run_id": run_id,
                "agent": agent,
                "action": action,
                "status": status,
                "duration_ms": duration_ms,
                "error": clip(error, 2000) if error else "",
            }
        )
        _persist_run_end(run_id, status, error, output, duration_ms)
        _RUN_ID.reset(token)


@contextmanager
def span(name: str, detail: str = "") -> Generator[None, None, None]:
    run_id = current_run_id()
    started = time.perf_counter()
    status = "ok"
    error = ""
    try:
        yield
    except Exception as exc:
        status = "error"
        error = f"{type(exc).__name__}: {exc}"
        raise
    finally:
        duration_ms = int((time.perf_counter() - started) * 1000)
        payload = {
            "event": "span",
            "run_id": run_id,
            "name": name,
            "status": status,
            "duration_ms": duration_ms,
            "detail": clip(detail or error),
        }
        _write_jsonl(payload)
        if run_id:
            _persist_span(run_id, name, status, detail or error, duration_ms)


def record_llm_call(
    *,
    role: str,
    provider: str,
    model: str,
    ok: bool,
    duration_ms: int,
    preview: str = "",
    error: str = "",
) -> None:
    run_id = current_run_id()
    status = "ok" if ok else "error"
    detail = f"{provider}/{model} role={role} {clip(error or preview, 600)}"
    _write_jsonl(
        {
            "event": "llm",
            "run_id": run_id,
            "name": f"llm.{role}",
            "status": status,
            "duration_ms": duration_ms,
            "provider": provider,
            "model": model,
            "detail": clip(detail),
        }
    )
    if run_id:
        _persist_span(run_id, f"llm.{role}", status, detail, duration_ms)


def configure_logging() -> None:
    if _LOG.handlers:
        return
    _LOG.setLevel(logging.INFO)
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
    _LOG.addHandler(handler)
    file_handler = logging.FileHandler(logs_dir() / "app.log", encoding="utf-8")
    file_handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
    _LOG.addHandler(file_handler)
