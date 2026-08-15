"""Memory layer: SQLite JSON checkpoints for LangGraph HITL resume."""

from __future__ import annotations

import json
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from opportunity_intel.domain.models import PipelineCheckpoint
from opportunity_intel.orchestrator.nodes import PhdApplicationState


def save_checkpoint(session: Session, thread_id: str, state: PhdApplicationState) -> None:
    row = session.get(PipelineCheckpoint, thread_id)
    blob = json.dumps(state, ensure_ascii=True, default=str)
    now = datetime.now(UTC).replace(tzinfo=None)
    if row is None:
        session.add(PipelineCheckpoint(thread_id=thread_id, state_json=blob, updated_at=now))
    else:
        row.state_json = blob
        row.updated_at = now
    session.commit()


def load_checkpoint(session: Session, thread_id: str) -> PhdApplicationState | None:
    row = session.get(PipelineCheckpoint, thread_id)
    if row is None or not row.state_json:
        return None
    return json.loads(row.state_json)
