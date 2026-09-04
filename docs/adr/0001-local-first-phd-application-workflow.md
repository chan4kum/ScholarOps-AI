# ADR 0001: Local-First PhD Application Workflow

## Status

Accepted

## Context

ScholarOps AI is intended to help a candidate discover funded PhD opportunities, compare fit, and prepare application materials. The domain requires strong evidence grounding because application documents can affect real academic and career outcomes.

The project also needs a clear boundary between assistance and action. Drafting and ranking can be automated, but submitting or sending application material should remain under human control.

## Decision

Use a local-first workflow architecture with:

- FastAPI for backend APIs.
- React/Vite for the local user interface.
- LangGraph orchestration for multi-step workflow state.
- Document ingestion and hybrid retrieval for candidate and opportunity evidence.
- Configurable LLM provider routing.
- SQLite/checkpoint-oriented persistence for local workflow state.
- A human-in-the-loop gate before application/browser actions.

## Consequences

Positive consequences:

- The architecture makes workflow stages explicit and reviewable.
- Retrieval and drafting can be evaluated independently.
- Local-first execution reduces accidental data exposure compared with a cloud-only design.
- The human approval gate creates a concrete safety boundary before external actions.

Tradeoffs:

- Local setup requires users to manage dependencies and provider keys.
- Portal discovery reliability still depends on external sites and adapters.
- Draft quality must be measured with labeled examples before making quality claims.
- HITL controls reduce automation speed but are appropriate for application workflows.

## Evidence Boundary

This ADR supports describing ScholarOps AI as an applied AI workflow prototype with retrieval, orchestration, and review controls. It does not support claims of zero hallucinations, guaranteed application success, production deployment, or validated portal coverage without additional evaluation artifacts.
