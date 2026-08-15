# ScholarOps AI (`opportunity_intel`)

<div align="center">

![ScholarOps AI Banner](https://img.shields.io/badge/ScholarOps%20AI-Doctoral%20Research%20Copilot-blue?style=for-the-badge)
[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg?style=flat-square&logo=python)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688.svg?style=flat-square&logo=fastapi)](https://fastapi.tiangolo.com)
[![React 19](https://img.shields.io/badge/React-19.0-61DAFB.svg?style=flat-square&logo=react)](https://react.dev)
[![Vite](https://img.shields.io/badge/Vite-6.0-646CFF.svg?style=flat-square&logo=vite)](https://vitejs.dev)
[![Playwright](https://img.shields.io/badge/Playwright-E2E%20Automated-2EAD33.svg?style=flat-square&logo=playwright)](https://playwright.dev)
[![ChromaDB](https://img.shields.io/badge/ChromaDB-Vector%20HNSW-orange.svg?style=flat-square)](https://www.trychroma.com)
[![LangGraph](https://img.shields.io/badge/LangGraph-Multi--Agent-purple.svg?style=flat-square)](https://github.com/langchain-ai/langgraph)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg?style=flat-square)](https://opensource.org/licenses/MIT)

**Local-First, Multi-Agent Autonomous Copilot for Discovering Funded PhD Positions Worldwide, Evaluating Research Fit, and Synthesizing Publication-Grade Application Dossiers with Zero Hallucinations.**

[Architecture](#-system-architecture) •
[Key Capabilities](#-key-capabilities) •
[Advanced RAG Subsystem](#-production-rag-subsystem) •
[Quick Start](#-quick-start) •
[Playwright Testing](#-playwright-automated-testing) •
[Security & HITL Gate](#-cryptographic-hitl-security-gate)

</div>

---

## 🌟 Overview

Applying for competitive, fully funded PhD positions across Europe, North America, and globally requires identifying specialized vacancies, matching research backgrounds against professor publications, and synthesizing bespoke, evidence-grounded application materials.

**ScholarOps AI** automates this entire doctoral recruitment lifecycle through an evidence-bound multi-agent system built on the **R-C-T-C-E-O-V** (Role, Context, Task, Constraints, Examples, Output, Validation) framework and a **DesignGurus-compliant Production RAG Subsystem**.

---

## 🏛️ System Architecture

```mermaid
graph TD
    subgraph Frontend ["Frontend Tier (React 19 + Vite)"]
        UI[Dashboard: Documents | Advisor | Opportunities | Prepare | Apply | Monitor | RAG Studio]
    end

    subgraph CoreRAG ["DesignGurus Production RAG Subsystem"]
        SC[Semantic Cache <50ms]
        Chunker[Structure-Aware Semantic Chunker]
        HNSW[(ChromaDB Vector Store)]
        BM25[BM25 Lexical Index]
        RRF[Reciprocal Rank Fusion RRF]
        Reranker[LLM Cross-Encoder Reranker]
        KG[NetworkX Academic Knowledge Graph]
        CRAG[Self-Improving RAG + LLM-as-a-Judge]
    end

    subgraph MultiAgent ["Multi-Agent Orchestration Tier"]
        LangGraph[LangGraph StateGraph Engine]
        GoogleSearch[Google GenAI Grounded Search]
        Discovery[18 Multi-Portal Discovery Aggregator]
        Drafter[R-C-T-C-E-O-V Academic Dossier Drafter]
        HITL[Single-Use HMAC Cryptographic Gate]
    end

    subgraph Persistence ["Persistence & Document Tier"]
        DB[(SQLite / PostgreSQL DB)]
        DocStore[Candidate PhD Document Store]
    end

    UI --> CoreRAG
    UI --> MultiAgent
    MultiAgent --> CoreRAG
    MultiAgent --> Persistence
    CoreRAG --> Persistence
```

---

## 🚀 Key Capabilities

### 1. Multi-Source Opportunity Discovery (18 Portals)
Automated aggregation, scraping, and LLM-based structured extraction across 18 leading academic portals:
* **International Aggregators:** EURAXESS (EU), FindAPhD (Global), AcademicTransfer (NL), PhDportal, AcademicPositions, AcademicKeys, MyScience, Jobs.ac.uk (UK), DAAD (Germany).
* **Direct University Portals:** ETH Zurich, EPFL, Max Planck Institutes, TU Delft, Oxford, Cambridge, Imperial College London, Karolinska Institute, University of Vienna.

### 2. Multi-Agent LangGraph Workflow with Google Search Grounding
* Orchestrates multi-step vacancy discovery using `google.genai` SDK + `types.GoogleSearch()`.
* Automatically ranks live web results against candidate profiles and maps them into the pipeline.

### 3. Rigorous R-C-T-C-E-O-V Application Dossier Synthesis
Generates 4 tailored, publication-grade application artefacts for any selected opportunity:
1. **Formal Academic Cover Letter:** 5-paragraph academic structure connecting master's thesis, technical methods, and supervisor fit.
2. **Doctoral Research Proposal / SOP:** 5 structured sections (Problem Formulation, Relation to PI's Work, Methodology, 3-Year Milestone Plan, Expected Contributions).
3. **Tailored Academic CV Highlights:** Competency matrix mapped directly to vacancy requirements.
4. **Prospective Supervisor Outreach Email:** High-impact, concise initial inquiry (180–250 words).

### 4. One-Click Document & Dossier Exports
* Direct download endpoints and UI buttons for `.md` documents and complete `Application_Dossier_*.md` bundles.

---

## 🧠 Production RAG Subsystem (DesignGurus Compliant)

ScholarOps AI implements a four-phase Advanced RAG architecture:

```
[User Query] ──> [Semantic Cache] ──(Hit >= 0.92)──> Return Response (<50ms)
                        │ (Miss)
                        ▼
                [Query Enhancer (HyDE + Multi-Query)]
                        │
         ┌──────────────┴──────────────┐
         ▼                             ▼
  [BM25 Lexical Search]     [ChromaDB Dense HNSW Vector]
         │                             │
         └──────────────┬──────────────┘
                        ▼
         [Reciprocal Rank Fusion (RRF)]
                        │
                        ▼
         [LLM Cross-Encoder Re-ranker] (0-100 Score + Rationales)
                        │
                        ▼
         [Academic Knowledge Graph (Multi-Hop Traversal)]
                        │
                        ▼
         [Self-Improving RAG (CRAG) + LLM-as-a-Judge] (Hallucination Audit)
```

1. **Structure-Aware Chunker (`chunker.py`):** Splits academic PDFs/DOCX by Markdown headings (`#`, `##`, `###`), section boundaries, and thesis chapters with 150-char sliding window overlap.
2. **Semantic Caching (`semantic_cache.py`):** High-dimensional vector cache storing verified query embeddings. Cached responses return in $<50\text{ms}$.
3. **Hybrid Search (`hybrid_search.py`):** Fuses BM25Okapi exact keyword matching with dense ChromaDB vectors via Reciprocal Rank Fusion:
   $$\text{RRF}(d) = \sum_{m \in \{\text{BM25}, \text{Dense}\}} \frac{1}{60 + \text{rank}_m(d)}$$
4. **Cross-Encoder Reranker (`reranker.py`):** Jointly evaluates `(query, passage)` pairs to output precise 0–100 relevance scores and natural language justifications.
5. **Academic Knowledge Graph (`knowledge_graph.py`):** NetworkX property graph modeling multi-hop relationships (`Candidate` $\leftrightarrow$ `Skills` $\leftrightarrow$ `Evidence` $\leftrightarrow$ `Opportunities` $\leftrightarrow$ `Supervisors` $\leftrightarrow$ `Papers`).
6. **Self-Improving RAG & LLM-as-a-Judge (`self_improving_rag.py`):** Evaluates drafts against ground-truth evidence with an automated self-correction feedback loop.

---

## 🔒 Cryptographic HITL Security Gate

To prevent automated spam or unintended portal submissions, ScholarOps AI enforces a strict **Human-in-the-Loop (HITL)** security gate:

1. **Single-Use HMAC-SHA256 Token:** Prepared applications cannot be dispatched without requesting a cryptographic confirmation token.
2. **Review & Approval Gate:** The user inspects the exact drafted email, attachments, and recipient address before confirming with single-click approval.
3. **Local Loopback Security:** The API binds exclusively to `127.0.0.1:8000` with no external cloud ingestion or telemetry leakage.

---

## 📁 Repository Structure

```
PHD_Job_Research/
├── src/opportunity_intel/           # Core Backend Package
│   ├── api/                         # FastAPI Router, Routes & Pydantic Schemas
│   ├── agents/                      # LLM Agents (Advisor, Profile Builder, Drafter)
│   ├── discovery/                   # 18-Source Scraper & Aggregator Pipeline
│   ├── documents/                   # Text Extraction (PDF, DOCX, MD) & Importer
│   ├── domain/                      # SQLAlchemy ORM Models
│   ├── llm/                         # LLMRouter, Token Economics, JSON Repair, Prompts
│   ├── orchestrator/                # LangGraph StateGraph & Google Grounding Workflow
│   ├── prepare/                     # Checklist Scorer, OpenAlex Papers & Dossier Synthesizer
│   ├── apply/                       # Cryptographic HITL Gate & Playwright Portal Submitter
│   └── rag/                         # Advanced RAG Subsystem
│       ├── chunker.py               # Structure-Aware Semantic Chunker
│       ├── hybrid_search.py         # BM25 + Dense RRF Hybrid Search
│       ├── knowledge_graph.py       # NetworkX Multi-Hop Academic Property Graph
│       ├── query_enhancer.py        # HyDE & Multi-Query Expansion
│       ├── reranker.py              # LLM Cross-Encoder Reranker
│       ├── semantic_cache.py        # Cosine Similarity Vector Cache
│       ├── self_improving_rag.py    # Corrective RAG + LLM-as-a-Judge
│       └── vector_store.py          # Persistent ChromaDB Vector Store
├── frontend/                        # Frontend Application (React 19 + Vite + TypeScript)
│   ├── src/
│   │   ├── components/RagStudio.tsx # Interactive RAG & KG Studio
│   │   ├── App.tsx                  # Main 7-Tab Application View
│   │   └── index.css                # Polished Dark Theme Styling
│   ├── e2e_test.mjs                 # Playwright E2E Test Suite
│   └── e2e_video_record.mjs         # Playwright Live Video Recording Suite
├── tests/                           # Pytest Unit & Integration Test Suite
├── docs/                            # System Design, LLM Routing & Master Plans
├── pyproject.toml                   # Python Dependencies & Tooling Config
└── README.md                        # Documentation
```

---

## ⚡ Quick Start

### 1. Prerequisites
* **Python:** 3.12 or newer
* **Node.js:** 20 or newer
* **API Keys:** DeepSeek, Groq, Google Gemini (optional for search grounding)

### 2. Clone & Configure
```bash
git clone https://github.com/chan4kum/ScholarOps-AI.git
cd ScholarOps-AI

# Create and activate virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install backend dependencies
pip install -e .

# Install frontend dependencies
cd frontend && npm install && cd ..
```

### 3. Set Environment Variables
Create a `.env` file in the root directory:
```env
DEEPSEEK_API_KEY=your_deepseek_api_key
GROQ_API_KEY=your_groq_api_key
GEMINI_API_KEY=your_gemini_api_key
IMPORT_DIR=/path/to/your/documents/PHD
DATABASE_URL=sqlite:///./opportunity.db
APPLY_AS_ME=false
```

### 4. Launch Services

**Start Backend API:**
```bash
python3 -m uvicorn opportunity_intel.api:app --host 127.0.0.1 --port 8000 --reload
```

**Start Frontend UI:**
```bash
cd frontend && npm run dev
```

Open your browser at **`http://127.0.0.1:5173/`**.

---

## 🧪 Playwright Automated Testing

Run the full end-to-end automated UI test suite across all 7 views:

```bash
cd frontend
node e2e_test.mjs
```

**Record Live Browser Automation Session Video:**
```bash
node e2e_video_record.mjs
```
The resulting WebM recording will be saved to `frontend/videos/scholarops_live_automation.webm`.

---

## 📊 Automated Unit Tests

Run backend unit and integration test suites:
```bash
pytest tests/
```

Run code formatting and linting:
```bash
ruff check src/ tests/
```

---

## 📜 License

This project is licensed under the **MIT License** - see the [LICENSE](LICENSE) file for details.
