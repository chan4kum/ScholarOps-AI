# Opportunity Intelligence Platform — Master Plan

**Product:** a local-first research and application copilot for funded PhDs and AI jobs.  
**Not:** an unsupervised bot that submits applications.

Two pipelines share one profile, one opportunity database, one document store, and one human-approval gate.

---

## 1. Product thesis

You store your academic/professional profile once. Agents discover opportunities, research people and institutions, score fit, extract requirements, and draft documents from **verified evidence only**. You approve every submission.

The durable asset is the **opportunity graph** (universities, professors, papers, jobs, deadlines, applications), not the chat UI.

---

## 2. Cost principle (non-negotiable)

Most of the system must work **without** a paid LLM.

| Work | Mechanism | LLM? |
| --- | --- | --- |
| Crawl FindAPhD, EURAXESS, university pages | HTTP + parsers + Playwright (read-only) | No |
| Extract deadline, funding, URL, country | CSS/JSON-LD/regex + schema validation | Rarely |
| Deduplicate opportunities | Canonical URL + title/org hash | No |
| Semantic search over papers/JDs | Local embeddings (`nomic-embed-text`) | No |
| Hard eligibility (degree, language, visa, deadline) | Rules against your profile | No |
| Research fit narrative + gap | LLM | Yes |
| Tailored CV evidence selection | LLM constrained to evidence IDs | Yes |
| Research proposal / SOP / cover letter | LLM | Yes |
| Application form fill | Deterministic mapping + optional LLM for leftover fields | Minimal |
| Submit | Human click only | No |

**Rule:** if a field is on the page as structured text, do not spend tokens to “read” it.

---

## 3. Model routing — DeepSeek reason/draft, Groq extract, Ollama fallback

You have **DeepSeek**, **Groq** (`gsk_`, not xAI Grok), and a **Hugging Face** token. Ollama remains the offline box.

### 3.1 Roles (locked 2026-08-15)

| Role | Provider | Model | Used for |
| --- | --- | --- | --- |
| `extract` | Groq | `openai/gpt-oss-20b` | Page → JSON. Llama 3.x Groq IDs deprecate 16 Aug 2026. |
| `embed` | Hugging Face | `BAAI/bge-small-en-v1.5` | Phase 2+ similarity |
| `reason` | DeepSeek | `deepseek-v4-flash` thinking **off** | Fit scores. `deepseek-chat` retired 24 Jul 2026. |
| `draft` | DeepSeek | `deepseek-v4-flash` thinking **on** | Proposals. `deepseek-reasoner` retired. Not `v4-pro`. |
| `polish` | Groq | `qwen/qwen3.6-27b` | Opt-in rewrite |
| `fallback` | Ollama | `qwen2.5:7b` | Offline |

Target geography: **NL, DE, SE, NO, DK, FI, IS, CH**. UK/GB excluded.

Dashboard: **React** (Vite), not HTMX.

### 3.2 Provider abstraction

One interface: `LLMRouter.complete(role, messages, json_schema?)`.

```
OPENAI-compatible clients:
  DEEPSEEK_BASE_URL=https://api.deepseek.com
  GROQ_BASE_URL=https://api.groq.com/openai/v1
  OLLAMA_BASE_URL=http://ollama:11434/v1
```

Switching models is `.env` + a YAML map `config/models.yaml`. Agents never import a vendor SDK directly.

### 3.3 Token budget controls

- Cache extracted page JSON keyed by URL + content hash.
- Summarize professor pages once; reuse across positions.
- Cap `extract` to the cleaned main text (trafilatura), not raw HTML.
- Max 1 `reason` call per opportunity per discovery run unless the source page changed.
- Drafts generated only for opportunities you mark **Prepare** or auto-prepare above a fit threshold you set (default 80%).
- Daily spend ceiling in config; workers stop LLM calls (scraping continues).

### 3.4 Local hardware

| Machine | Practical local stack |
| --- | --- |
| 16 GB RAM, no GPU | `qwen2.5:7b` + `nomic-embed-text`; DeepSeek for reason/draft |
| 16 GB+ Apple Silicon / 8 GB VRAM | add `qwen2.5:14b` as offline `draft` |
| No GPU, APIs down | discovery + rules still work; drafts queue until API or larger local model is available |

---

## 4. Runtime architecture (local Docker)

```
You
 │
 Web dashboard (Phase 1: FastAPI + HTMX or simple React)
 │
 API + LangGraph orchestrator
 │
 Postgres  ← opportunity graph, profile, applications
 Redis     ← queues, rate limits, run locks
 │
 Workers (discovery, research, qualify, documents)
 │
 MCP tool servers (permissions per agent)
 │
 Optional: Ollama | Playwright (read-only) | n8n (Phase 4)
```

**LangGraph** owns agent state, retries, and human interrupts (approve / reject / revise).  
**n8n** (Phase 4 only) owns clocks and external events: cron, Gmail, Telegram. It must not contain business logic.  
**MCP** is the permission boundary: tools are granted per agent, not globally.

Do not put reasoning inside n8n nodes. n8n starts a job; LangGraph runs it.

---

## 5. Shared domain model

Postgres + JSONB. Relational queries you already want (“deadlines in 14 days”, “Germany + Agentic AI + fit > 80”) are first-class SQL, not a vector DB toy.

| Entity | Purpose |
| --- | --- |
| `UserProfile` | Degrees, skills, countries, funding needs, visa, research interests |
| `EvidenceItem` | Atomic true facts from master CV / transcripts (id, type, text, dates). **CV agent may only cite these IDs.** |
| `Document` | Files: CV, transcripts, references, generated drafts (versioned) |
| `University` / `Company` | Org records |
| `Person` | Professor, PI, hiring manager |
| `ResearchGroup` | Group, lab, centre |
| `Paper` | Title, year, authors, URL, abstract, embedding |
| `Opportunity` | `kind = phd \| job`, source URL, deadline, funding, location |
| `Requirement` | Required/optional docs and eligibility rules extracted from the advert |
| `FitScore` | Rule score + embedding score + LLM rationale (stored, not recomputed) |
| `Application` | Status machine: discovered → researched → qualified → docs_ready → pending_approval → submitted / rejected |
| `ApplicationEvent` | Audit log |
| `Contact` | Emails, portal URLs |

Opportunity intelligence queries (all SQL + optional vector filter):

- Funded PhDs in Germany, Agentic AI governance, fit > 80%
- Professors with AI governance + autonomous agents papers in last 3 years
- Applications with deadlines in 14 days
- All applications in `docs_ready` awaiting approval

---

## 6. Agent pool (12 names, 8 built first)

Start with **8**. The extra four are Phase 4 wrappers, not extra brains.

| # | Agent | Tools allowed | Model role | Phase |
| --- | --- | --- | --- | --- |
| 1 | Discovery | web_search, fetch_page, parse_listing, db_write(opportunity) | none / extract | 1 |
| 2 | Opportunity Research | fetch_page, db | extract | 1 |
| 3 | Professor/Company Intelligence | scholar/search, fetch_page, db | extract + reason | 1 |
| 4 | Qualification | profile, db, **no web submit** | reason + rules | 1 |
| 5 | Document/Requirements | fetch_page | extract | 2 |
| 6 | CV | evidence store, **cannot invent** | reason | 2 |
| 7 | Research/Letter | profile + papers + advert | draft (+ optional polish) | 2 |
| 8 | Application | form fill, **submit denied** until approval | mapping | 3 |
| 9 | Verification | checksums, claim-vs-evidence | reason (cheap) | 3 |
| 10 | Compliance/Security | policy, PII redaction logs | rules | 3 |
| 11 | Tracking | portals, Gmail (read) | extract | 4 |
| 12 | Notification | n8n → email/Telegram | none | 4 |

### Permission matrix

| Tool | Discovery | Research | Qualify | CV/Letter | Application |
| --- | --- | --- | --- | --- | --- |
| web_search / fetch | yes | yes | no | no | yes (form only) |
| db read | yes | yes | yes | yes | yes |
| db write opportunities | yes | yes | scores only | docs only | application only |
| email send | no | no | no | no | no |
| application submit | no | no | no | no | **human approval** |

---

## 7. Pipelines

### Use case 1 — PhD

```
Profile
  → Discovery (many sources, not FindAPhD only)
  → Opportunity Research (deadline, funding, eligibility)
  → Professor Intelligence (group, papers, supervision)
  → Qualification (rules + research fit)
  → Requirements checklist
  → Proposal / SOP / CV (evidence-bound)
  → Human approval
  → Submit + track
```

Discovery sources (priority order): EURAXESS, university / department / group pages, official job boards, FindAPhD, DAAD/other funders, Scholar/professor pages. FindAPhD is a feed, not the product.

### Use case 2 — AI jobs

```
Same profile + master CV evidence
  → Job Discovery (company pages, boards; LinkedIn last and ToS-aware)
  → Company / team research
  → Qualification vs JD
  → Tailored CV (reorder/select evidence, never invent)
  → Cover letter
  → Fill form
  → Human approval
  → Submit + track
```

LinkedIn Easy Apply and similar ToS-restricted surfaces stay **manual**: the system prepares the packet; you submit.

---

## 8. Safety: application agent

```
Fill (deterministic profile mapping)
  → Validation (required fields, file types, evidence claims)
  → HUMAN APPROVAL  (dashboard: “27 fields, 3 docs — review”)
       ├─ Reject → revise
       └─ Approve → submit once, log receipt
```

LangGraph `interrupt()` before any mutating HTTP POST to an application portal.  
Playwright is **read-only** until Phase 3, and even then submit is a separate tool with a signed approval token that expires.

CV agent contract: output is a list of `evidence_id`s plus layout. If a bullet is not in `EvidenceItem`, it is dropped.

---

## 9. Phased MVP

### Phase 1 — Intelligence dashboard (build first)

User profile → PhD discovery → position extraction → eligibility rules → professor research → fit score → dashboard.

**Done when:** you can type a research query, get a table of funded roles with deadline, country, funding, professor, fit %, and open the source URL. No auto-writing, no apply.

### Phase 2 — Documents

Requirements extraction → checklist → CV tailor → cover letter → research proposal grounded in professor papers + your evidence.

**Done when:** for one HIGH PRIORITY PhD, the system produces a proposal draft that cites the professor’s recent papers and only your real projects.

### Phase 3 — Assisted apply

Form fill + validation + human approval. Submit is optional and per-site adapters (start with 1–2 university portals, not “the whole internet”).

**Done when:** you review a filled packet and click Approve; the audit log records what was sent.

### Phase 4 — Platform operations

n8n cron + Gmail/Telegram; MCP servers for Gmail, Drive, GitHub, DB; scheduled discovery; application tracking; notifications.

**Done when:** a nightly job refreshes listings and Telegram tells you “3 new >80% fits; 1 deadline in 7 days.”

---

## 10. Recommended local stack

| Layer | Choice | Why |
| --- | --- | --- |
| Language | Python 3.12 | LangGraph, scraping, Pydantic |
| API | FastAPI | Local, typed, easy dashboard |
| Orchestration | LangGraph | HITL interrupts, durable state |
| DB | Postgres 16 + pgvector | Graph queries + embeddings |
| Queue | Redis + a worker process | Cheap, local |
| LLM gateway | Thin OpenAI-compatible router | DeepSeek / Grok / Ollama |
| Extract/clean | trafilatura, selectolax, httpx | Avoid LLM on HTML |
| Browser | Playwright (later) | JS-heavy department sites |
| Dashboard Phase 1 | HTMX + Jinja **or** a small React app | Fastest path to a table you will actually use |
| n8n | Compose service, Phase 4 | Cron and notifications only |
| Secrets | `.env` never committed | DeepSeek, Grok, later Gmail OAuth |

Skip Kubernetes, Terraform, and cloud CD until the local loop is useful for *your* applications.

---

## 11. Repo layout (when we implement)

```
project/
├── AGENT_RULES.md
├── README.md
├── .gitignore
├── .env.example
├── pyproject.toml
├── Dockerfile
├── docker-compose.yml          # api, worker, postgres, redis, ollama profile
├── config/models.yaml          # role → provider/model
├── src/
│   ├── api/
│   ├── orchestrator/           # LangGraph graphs
│   ├── agents/
│   ├── llm/                    # router, budgets
│   ├── tools/                  # MCP-facing tools
│   ├── extractors/             # non-LLM parsers
│   ├── domain/                 # Pydantic + SQLAlchemy models
│   └── scoring/
├── tests/
├── infra/                      # empty until we leave localhost
├── n8n/                        # Phase 4 workflows
└── docs/
```

---

## 12. What we will not do in v1

- Unrestricted browser agents that click Submit.
- Invented publications, grades, or job titles.
- Depending on FindAPhD or LinkedIn as the only source.
- Thirty agents. Eight, then four operational wrappers.
- Sending Grok every page scrape.
- Building n8n before the Postgres opportunity table works.

---

## 13. Open decisions (needed before coding Phase 1)

1. Dashboard: fastest HTMX vs React (recommend **HTMX for Phase 1**).
2. Confirm DeepSeek model IDs on your account (`deepseek-chat` / `deepseek-reasoner`).
3. Confirm Grok model ID on your xAI account.
4. Target countries for the first discovery adapters (recommend **NL, DE, UK, Nordics, CH**).
5. Whether you already have a master CV file to ingest as `EvidenceItem`s.
