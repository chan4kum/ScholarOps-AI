# ScholarOps AI (`opportunity_intel`) — Implementation & Verification Task List

**Version:** 1.0.0  
**Status:** Scaffolding Complete / Verified / Operational  

---

## Phase 1: Architectural Artifacts & Design Specifications

- [x] **Task 1.1: System Design Specification**
  - [x] Define multi-tier architecture diagram (React Frontend, FastAPI Backend, Multi-Agent Engines, SQLite persistence).
  - [x] Document comprehensive file tree and submodule responsibilities.
  - [x] Specify complete SQLAlchemy database schema (16 tables, constraints, relationships, indexes).
  - [x] Document RESTful API contracts (request/response schemas, HTTP methods, status codes).
  - [x] Document locked LLM model routing matrix and R-C-T-C-E-O-V prompt standards.
  - [x] Document HMAC-SHA256 cryptographic approval gate and dispatch adapter safety.
  - [x] Created `docs/design.md`.

- [x] **Task 1.2: Implementation Checklist & Roadmap**
  - [x] Create comprehensive task breakdown across backend, frontend, and verification pipelines.
  - [x] Created `docs/tasks.md`.

---

## Phase 2: Backend Scaffolding & Configuration

- [x] **Task 2.1: Python Packaging & Dependencies (`pyproject.toml`)**
  - [x] Configure Python `>=3.12` requirement with Hatchling build backend.
  - [x] Add core runtime dependencies: `fastapi`, `uvicorn`, `pydantic`, `pydantic-settings`, `sqlalchemy`, `openai`, `httpx`, `feedparser`, `selectolax`, `trafilatura`, `pypdf`, `python-docx`.
  - [x] Configure optional dependency groups: `dev` (`pytest`, `ruff`), `postgres` (`psycopg[binary]`), `browser` (`playwright`), `local` (`google-genai`, `langgraph`, `faiss-cpu`).
  - [x] Configure Pytest paths and Ruff linting rules (`E`, `F`, `I`, `UP`).

- [x] **Task 2.2: Settings & Environment Configuration (`config.py` & `config/`)**
  - [x] Implement `Settings` using `pydantic-settings` to safely read environment variables without hardcoded secrets.
  - [x] Create `config/models.yaml` with locked model roles: `extract` (Groq), `reason` (DeepSeek), `draft` (DeepSeek), `polish` (Groq), `embed` (Hugging Face), `fallback` (Ollama).
  - [x] Create `config/discovery.yaml` with RSS feed URLs and search site hints.
  - [x] Implement YAML loaders and dynamic model configuration validators (`models_config.py`).

- [x] **Task 2.3: Centralized LLM Router (`llm/router.py`)**
  - [x] Implement provider-agnostic `LLMRouter` mapping roles to OpenAI-compatible endpoints.
  - [x] Add DeepSeek thinking parameter toggling (`thinking: enabled` vs `thinking: disabled`).
  - [x] Add Groq `failed_generation` recovery handler for reliable JSON extraction.
  - [x] Implement automatic fallback to OpenAI `gpt-5-nano-2025-08-07` when DeepSeek key is missing.
  - [x] Implement raw REST Gemini search grounding in `llm/gemini.py` without vendor SDK imports.
  - [x] Enforce token budget tracking and daily spend limits in `llm/budget.py`.

- [x] **Task 2.4: Database & Domain Models (`domain/models.py`, `db.py`)**
  - [x] Implement SQLAlchemy 2.0 ORM models: `UserProfile`, `UploadedDocument`, `EvidenceItem`, `Opportunity`, `ApplicationPacket`, `RequirementItem`, `ProfessorPaper`, `DraftDocument`, `Application`, `ApplicationEvent`, `AgentRun`, `AgentSpan`, `NightlyDigest`, `Notification`, `PipelineCheckpoint`.
  - [x] Configure connection pools, SQLite lock retries, and schema initialization.

---

## Phase 3: Core Multi-Agent Pipelines & API

- [x] **Task 3.1: Discovery Engine (`discovery/`)**
  - [x] Implement RSS feed parsers for EURAXESS and AcademicTransfer (`sources.py`).
  - [x] Implement FindAPhD HTML scraper (`sources.py`).
  - [x] Implement multi-engine web search fallback (DuckDuckGo, Brave, Tavily, Gemini) (`web_search.py`).
  - [x] Implement non-LLM HTML main-text extractors (`selectolax`, `trafilatura`) (`extract.py`).
  - [x] Implement Groq extraction fallback when local extraction is thin (`extract.py`).
  - [x] Implement qualification filters dropping non-PhD listings and duplicate URLs (`quality.py`).
  - [x] Implement supervisor and location heuristic enrichment (`enrich.py`).

- [x] **Task 3.2: Matching, Evidence & Preparation Engine (`prepare/`, `agents/advisor.py`)**
  - [x] Implement document parsers for PDF, DOCX, Markdown, and Text (`documents/extract.py`).
  - [x] Implement drop-folder batch scanner (`documents/import_folder.py`).
  - [x] Implement Advisor agent to extract atomic evidence items (`EV-<id>`) and build profile (`agents/advisor.py`).
  - [x] Implement Semantic Scholar / OpenAlex PI publication search (`prepare/papers.py`).
  - [x] Implement R-C-T-C-E-O-V prompts for requirement extraction, checklist scoring, and draft synthesis (`llm/prompting.py`).
  - [x] Enforce evidence-binding: drop any CV claim not backed by an `EvidenceItem` and restrict proposal citations to retrieved PI papers (`prepare/service.py`).
  - [x] Implement LaTeX & Jinja2 compilation module (`execution/latex.py`).

- [x] **Task 3.3: Application & Dispatch Engine (`apply/`)**
  - [x] Implement apply pathfinder classifying vacancy channel as `email` vs `portal` (`pathfind.py`).
  - [x] Implement deterministic profile-to-form field mapper and SHA-256 payload checksum calculator (`mapping.py`).
  - [x] Implement single-use expiring HMAC-SHA256 token issuer and validator (`tokens.py`, `secrets.py`).
  - [x] Implement execution adapters: `sandbox`, `manual`, `email` (SMTP), and `portal` (Playwright) (`adapters.py`, `email_send.py`, `portal.py`).
  - [x] Enforce `APPLY_AS_ME=true` requirement before transmitting live emails or filling live forms.
  - [x] Implement Playwright HITL breakpoints (halt on CAPTCHA, login, payment).

- [x] **Task 3.4: Operations & Observability (`ops/`, `observability/`, `orchestrator/`)**
  - [x] Implement telemetry context managers recording agent runs, spans, and latencies (`observability/trace.py`).
  - [x] Implement scheduled nightly discovery cycle, digest formatter, and Telegram dispatcher (`ops/nightly.py`, `ops/digest.py`, `ops/notify.py`).
  - [x] Implement allowlisted ops management tools (`ops/tools.py`).
  - [x] Implement LangGraph state machine graph with human interruption checkpoints (`orchestrator/graph.py`, `orchestrator/nodes.py`).

- [x] **Task 3.5: FastAPI Web API (`api/`)**
  - [x] Implement complete RESTful routes across documents, advisor, opportunities, packets, applications, monitor, and ops (`api/routes.py`).
  - [x] Enforce `127.0.0.1` loopback binding and security headers (`api/app.py`).

---

## Phase 4: Frontend Dashboard & Automated Testing

- [x] **Task 4.1: React 18 / Vite Dashboard (`frontend/`)**
  - [x] Build multi-tab interface:
    - *Documents*: Master CV/document upload, folder scan, extracted evidence viewer.
    - *Advisor*: Document-driven profile builder, research suggestions, contextual chat.
    - *Opportunities*: Multi-source search, fit scoring (rules + LLM), shortlisting.
    - *Prepare*: Requirements checklist (met/gap), PI paper citations, evidence-bound drafts.
    - *Apply*: Form preview, validation checks, HMAC approval modal, adapter selection.
    - *Ops*: Nightly digest history, application tracker, notification triggers.
    - *Monitor*: Telemetry dashboard, agent run logs, span duration graphs.
  - [x] Verify clean Vite production build without TypeScript errors.

- [x] **Task 4.2: Automated Verification Suite (`tests/`)**
  - [x] `test_api_backend_complete.py` — API routes, error mapping, security contracts.
  - [x] `test_api_backend_suite.py` — Extended contract, validation, and failure tests.
  - [x] `test_api_contract.py` — OpenAPI schema and response structure validation.
  - [x] `test_api_llm_status.py` — Model configuration and country rules status.
  - [x] `test_apply.py` & `test_apply_as_me.py` — HMAC tokens, single-use burning, SMTP/adapter safety.
  - [x] `test_discovery_extract.py` & `test_discovery_quality.py` — Extraction, deduplication, and quality filters.
  - [x] `test_documents.py` & `test_import_folder.py` — Document parsing and folder sync.
  - [x] `test_llm_router.py`, `test_llm_budget.py`, `test_llm_json_recover.py` — Model routing and budget ceilings.
  - [x] `test_openai_gemini_router.py` — Fallback and REST search grounding.
  - [x] `test_prompts_rctceov.py` — Prompt structure and anti-hallucination constraints.
  - [x] `test_rag_and_latex.py` — RAG vector store and LaTeX compilation.
  - [x] `test_security_local_bind.py` & `test_storage_safety.py` — Network isolation and storage safety.
  - [x] Run `pytest` and verify 100% pass rate.
  - [x] Run `ruff check` and verify 0 lint errors.

---

## Phase 5: Ongoing Maintenance & Extension Playbook

- [ ] **Task 5.1:** Add new country-specific academic board adapters (e.g., DAAD Germany, Jobs.ac.uk).
- [ ] **Task 5.2:** Add multi-user SQLite partitioning / PostgreSQL migration scripts if scaling beyond local developer workstation.
- [ ] **Task 5.3:** Extend Playwright adapters with visual snapshot recording for portal audits.

---

## Phase 6: Architectural Hardening (Audit-Driven Fixes)

*Applied post-scaffold based on forensic audit of 12 structural/quality gaps.*

- [x] **Task 6.1: Gemini SDK → httpx REST (Task 1)**
  - [x] Replaced `google.genai` SDK import in `llm/gemini.py` with raw `httpx` REST call.
  - [x] `generate_grounded()` now calls `POST /v1beta/models/{model}:generateContent?key=` directly.
  - [x] Test hook preserved: inject `generate=` kwarg to avoid real network calls in tests.

- [x] **Task 6.2: Centralised JSON Repair (`llm/json_repair.py`) (Task 2)**
  - [x] Created `llm/json_repair.py` with single `parse_llm_json()` utility.
  - [x] Handles: direct JSON, markdown-fenced JSON, JSON embedded in prose, balanced-block extraction.
  - [x] Deleted duplicated `_parse_json` functions from `agents/advisor.py` and `agents/prepare.py`.
  - [x] All agents import exclusively from `llm.json_repair`.

- [x] **Task 6.3: Real BGE Embeddings via HF Inference API (Task 3)**
  - [x] Added `embed()` method to `LLMRouter` using HuggingFace Inference API (`BAAI/bge-small-en-v1.5`, 384-dim).
  - [x] In-process cache keyed by `sha256(text[:2000])` eliminates duplicate API calls within a session.
  - [x] Graceful fallback to 256-dim hash-trick with `UserWarning` when HF_TOKEN is absent or call fails.
  - [x] `embed` role added to `config/models.yaml` (`provider: huggingface`).

- [x] **Task 6.4: `embed_fit` Wired into Discovery Pipeline (Task 4)**
  - [x] `Opportunity.embed_fit` column exists in `domain/models.py`.
  - [x] `rag/faiss_store.py` routes embedding through `LLMRouter.embed()` or falls back to hash-trick.
  - [x] `discovery/service.py → run_discovery()` computes `embed_fit` for all new rows in one batch.
  - [x] `embed_fit` field included in API opportunity response for frontend ranking.

- [x] **Task 6.5: All 18 Discovery Sources Implemented (Task 5)**
  - [x] `discovery/sources.py` implements all 18 sources: EURAXESS, FindAPhD, AcademicTransfer, PhDportal, AcademicPositions, AcademicKeys, MyScience, Jobs.ac.uk, DAAD, Jobbnorge, WorkInDenmark, ScholarshipDb, Nature Careers, Science Careers, HigherEdJobs, ProFellow, ResearchTweet, FellowshipBard.
  - [x] RSS sources use `_parse_rss_feed()` generic helper; HTML scrapers use `selectolax`.
  - [x] `ALL_SOURCE_FUNCTIONS` list ensures `pipeline.py` runs all sources without code duplication.
  - [x] `discover()` convenience entry-point for testing sources in isolation.

- [x] **Task 6.6: Token-Based Budget Charging (`budget.py`) (Task 6)**
  - [x] Added `charge_from_usage()` — charges real USD from actual API `response.usage` token counts.
  - [x] Added `PROVIDER_TOKEN_PRICE` table with per-1M-token input/output costs for all providers.
  - [x] `_ROLE_FLAT_COST_USD` retained as fallback for pre-flight guard and recovered payloads.
  - [x] Exported `ROLE_COST_USD` public alias so tests can reference flat costs without `_`-prefix access.
  - [x] Removed `gemini` from `FREE_PROVIDERS` (it charges beyond free quota).

- [x] **Task 6.7: TTL Fix + Groq JSON Recovery Hardening (Task 7)**
  - [x] `config.py`: fixed `apply_token_ttl_seconds` default from `900` → `300` (5-minute HITL window per spec).
  - [x] `llm/router.py → _failed_generation()`: extracts Groq `failed_generation` JSON from exception body.
  - [x] `_failed_generation()` validated by `test_llm_json_recover.py::test_recover_groq_failed_generation`.

- [x] **Task 6.8: Documentation Refresh (Task 8)**
  - [x] `docs/design.md`: updated to reflect BGE embeddings, 18-source inventory, httpx-only Gemini, real token pricing.
  - [x] `docs/tasks.md`: this file — added Phase 6 hardening record.

