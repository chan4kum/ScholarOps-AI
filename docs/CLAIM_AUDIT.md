# Claim Audit

This audit keeps the public project description credible for recruiters and reviewers. It maps portfolio claims to repository evidence and identifies language that should be avoided until there is reproducible proof.

## Supported Claims

| Recruiter-facing claim | Evidence in repository | Notes |
| --- | --- | --- |
| ScholarOps AI is a local-first PhD opportunity workflow assistant. | FastAPI backend, React/Vite frontend, SQLite-oriented workflow state, and local run instructions. | Supported as a prototype/local workflow system. |
| The system uses LangGraph-style orchestration for multi-step workflows. | `src/opportunity_intel/orchestrator/graph.py`. | Supported. |
| The workflow includes ingestion, discovery, matching, human review, drafting, critique, and browser/action stages. | Orchestrator graph nodes and routing in `src/opportunity_intel/orchestrator/graph.py`. | Supported as implemented workflow structure. |
| The retrieval layer combines lexical and vector search. | `src/opportunity_intel/rag/hybrid_search.py`. | Supported. |
| The project includes LLM provider routing and fallback-oriented plumbing. | `src/opportunity_intel/llm/router.py`. | Supported as provider-routing architecture. |
| Human approval is part of the application-action path. | HITL node in the orchestrator flow. | Supported; describe as an approval gate, not as a guarantee against all misuse. |
| The frontend exposes application workflow and retrieval-inspection views. | `frontend/src/App.tsx`, `frontend/src/components/RagStudio.tsx`. | Supported. |

## Claims To Soften Or Remove

| Previous wording | Issue | Replacement |
| --- | --- | --- |
| Zero hallucinations | No public reproducible hallucination benchmark was found. | Evidence-grounded drafting with a planned source-grounding evaluation. |
| Publication-grade application dossiers | Quality is subjective and not benchmarked. | Draft application materials for human review. |
| Semantic cache under 50 ms | No benchmark artifact was found. | Semantic caching layer for repeated queries. |
| 18-portal discovery coverage | Portal adapters and discovery code exist, but live coverage and reliability are not validated here. | Multi-source opportunity discovery adapters. |
| Production RAG subsystem | Production readiness requires operational evidence, monitoring, and benchmark results. | Retrieval subsystem with hybrid search and evaluation plan. |
| DesignGurus-compliant | External compliance is not evidenced in the repository. | Architecture inspired by common RAG design patterns. |
| Fully autonomous application submission | The repository contains HITL gating and browser/action concepts. | Human-approved application-action workflow. |

## Recruiter-Facing Rule

Use claims that describe implemented architecture and observable code paths. Do not claim production use, latency, ranking quality, hallucination rate, portal reliability, or application outcomes until those results are measured and published with methodology.
