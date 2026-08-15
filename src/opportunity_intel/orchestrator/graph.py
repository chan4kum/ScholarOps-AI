"""LangGraph compile + SQLite JSON checkpoints. HITL is HMAC/dashboard, not input()."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.orm import Session

from opportunity_intel.memory.checkpoint import load_checkpoint, save_checkpoint
from opportunity_intel.orchestrator.nodes import (
    PhdApplicationState,
    PipelineContext,
    browser_node,
    critic_node,
    discovery_node,
    drafter_node,
    empty_state,
    hitl_node,
    ingestion_node,
    matchmaker_node,
    run_pipeline,
)


def build_graph() -> Any | None:
    try:
        from langgraph.graph import END, START, StateGraph
    except ImportError:
        return None

    graph = StateGraph(dict)

    def wrap(fn):  # noqa: ANN001
        def _inner(state: dict, config: dict | None = None) -> dict:
            ctx: PipelineContext = (config or {}).get("configurable", {}).get("ctx")
            if ctx is None:
                raise RuntimeError("PipelineContext missing from LangGraph config")
            return fn(state, ctx)

        return _inner

    graph.add_node("ingestion", wrap(ingestion_node))
    graph.add_node("discovery", wrap(discovery_node))
    graph.add_node("matchmaker", wrap(matchmaker_node))
    graph.add_node("hitl", wrap(hitl_node))
    graph.add_node("drafter", wrap(drafter_node))
    graph.add_node("critic", wrap(critic_node))
    graph.add_node("browser", wrap(browser_node))
    graph.add_edge(START, "ingestion")
    graph.add_edge("ingestion", "discovery")
    graph.add_edge("discovery", "matchmaker")
    graph.add_edge("matchmaker", "hitl")

    def after_hitl(state: dict) -> str:
        if state.get("reject"):
            return "discovery"
        if state.get("human_approved"):
            return "drafter"
        return "wait"

    graph.add_conditional_edges(
        "hitl",
        after_hitl,
        {"discovery": "discovery", "drafter": "drafter", "wait": END},
    )
    graph.add_edge("drafter", "critic")
    graph.add_edge("critic", END)
    graph.add_edge("browser", END)
    return graph.compile(interrupt_before=["browser"])


def start_or_resume(
    session: Session,
    ctx: PipelineContext,
    *,
    research_query: str = "",
    thread_id: str = "",
    human_approved: bool = False,
    reject: bool = False,
    approval_token: str = "",
) -> PhdApplicationState:
    tid = thread_id.strip() or str(uuid.uuid4())
    state = load_checkpoint(session, tid) or empty_state(research_query, tid)
    state["thread_id"] = tid
    if research_query.strip():
        state["research_query"] = research_query.strip()
    if reject:
        state["reject"] = True
        state["human_approved"] = False
        state["matched_pis"] = []
        state["application_status"] = "rejected_to_discovery"
    if human_approved:
        state["human_approved"] = True
        state["reject"] = False
    if approval_token.strip():
        state["approval_token"] = approval_token.strip()
        state["human_approved"] = True
        result = browser_node(state, ctx)
        save_checkpoint(session, tid, result)
        return result
    result = run_pipeline(state, ctx)
    save_checkpoint(session, tid, {**result, "approval_token": result.get("approval_token") or ""})
    return result
