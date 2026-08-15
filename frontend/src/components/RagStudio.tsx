import React, { useState } from "react";

type HybridSearchResult = {
  id: string;
  text: string;
  rrf_score?: number;
  bm25_score?: number;
  dense_score?: number;
  rerank_score?: number;
  rationale?: string;
  metadata?: Record<string, unknown>;
};

type JudgeEvaluation = {
  passed: boolean;
  hallucination_score: number;
  relevance_score: number;
  coverage_score: number;
  critique: string;
  suggested_edits: string[];
};

type GenerationResult = {
  query: string;
  final_text: string;
  iterations_run: number;
  grounding_evidence_ids: string[];
  evaluation: JudgeEvaluation;
  cache_hit?: boolean;
  cached_similarity?: number;
};

type GoogleWorkflowResult = {
  node: string;
  application_status: string;
  human_approved: boolean;
  opportunity_id?: number | null;
  application_id?: number | null;
  approval_token?: string | null;
  discovered_vacancies?: Array<{
    title: string;
    organization: string;
    country: string;
    funding: string;
    url: string;
    deadline?: string;
    supervisor?: string;
  }>;
  drafted_documents?: Record<string, string>;
  critic_issues?: Array<{ level: string; code: string; message: string }>;
  error?: string;
};

export function RagStudio(): React.JSX.Element {
  const [activeSubTab, setActiveSubTab] = useState<"search" | "generate" | "workflow">("search");

  // Hybrid Search State
  const [searchQuery, setSearchQuery] = useState("Responsible AI safety and uncertainty quantification");
  const [collection, setCollection] = useState("evidence_items");
  const [useReranker, setUseReranker] = useState(true);
  const [searching, setSearching] = useState(false);
  const [searchResults, setSearchResults] = useState<HybridSearchResult[]>([]);
  const [searchError, setSearchError] = useState("");

  // Self-Improving RAG State
  const [genQuery, setGenQuery] = useState("Draft an evidence-bound statement of fit for a PhD position in Trustworthy AI");
  const [generating, setGenerating] = useState(false);
  const [genResult, setGenResult] = useState<GenerationResult | null>(null);
  const [genError, setGenError] = useState("");

  // Google Workflow State
  const [wfQuery, setWfQuery] = useState("funded PhD in Trustworthy AI and Autonomous Systems Europe");
  const [wfRunning, setWfRunning] = useState(false);
  const [wfResult, setWfResult] = useState<GoogleWorkflowResult | null>(null);
  const [wfError, setWfError] = useState("");
  const [approvalToken, setApprovalToken] = useState("");

  async function handleHybridSearch(e: React.FormEvent) {
    e.preventDefault();
    if (!searchQuery.trim()) return;
    setSearching(true);
    setSearchError("");
    try {
      const url = `/api/rag/search?query=${encodeURIComponent(searchQuery)}&collection=${collection}&limit=5&use_reranker=${useReranker}`;
      const res = await fetch(url, { method: "POST" });
      const data = await res.json();
      if (!res.ok) {
        setSearchError(data.detail || "Search failed");
      } else {
        setSearchResults(data.results || []);
      }
    } catch (err) {
      setSearchError(err instanceof Error ? err.message : "Search error");
    } finally {
      setSearching(false);
    }
  }

  async function handleSelfRAGGenerate(e: React.FormEvent) {
    e.preventDefault();
    if (!genQuery.trim()) return;
    setGenerating(true);
    setGenError("");
    try {
      const url = `/api/rag/generate?query=${encodeURIComponent(genQuery)}&max_iterations=2`;
      const res = await fetch(url, { method: "POST" });
      const data = await res.json();
      if (!res.ok) {
        setGenError(data.detail || "Generation failed");
      } else {
        setGenResult(data);
      }
    } catch (err) {
      setGenError(err instanceof Error ? err.message : "Generation error");
    } finally {
      setGenerating(false);
    }
  }

  async function handleGoogleWorkflow(humanApproved = false) {
    setWfRunning(true);
    setWfError("");
    try {
      const res = await fetch("/api/ops/google-workflow", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          research_query: wfQuery,
          human_approved: humanApproved,
          approval_token: approvalToken || undefined,
        }),
      });
      const data = await res.json();
      if (!res.ok) {
        setWfError(data.detail || "Workflow execution failed");
      } else {
        setWfResult(data);
        if (data.approval_token) {
          setApprovalToken(data.approval_token);
        }
      }
    } catch (err) {
      setWfError(err instanceof Error ? err.message : "Workflow error");
    } finally {
      setWfRunning(false);
    }
  }

  return (
    <div className="stack">
      {/* Studio Header & Architecture Badges */}
      <section className="card">
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", flexWrap: "wrap", gap: "12px" }}>
          <div>
            <h2>Production RAG & Agentic Studio</h2>
            <p className="muted" style={{ margin: "4px 0 0" }}>
              DesignGurus-compliant multi-phase architecture: ChromaDB HNSW Dense + BM25 Lexical RRF, LLM Cross-Encoder Reranker, Semantic Caching, and Corrective RAG (CRAG) with LLM-as-a-Judge.
            </p>
          </div>
          <div className="pills">
            <span className="pill ok">ChromaDB HNSW</span>
            <span className="pill ok">BM25 + RRF</span>
            <span className="pill ok">LLM Cross-Encoder</span>
            <span className="pill ok">Semantic Cache</span>
            <span className="pill ok">LLM-as-a-Judge</span>
          </div>
        </div>

        {/* Sub-Tabs */}
        <div style={{ display: "flex", gap: "8px", marginTop: "16px", borderBottom: "1px solid var(--border-color, #333)", paddingBottom: "8px" }}>
          <button
            type="button"
            className={`btn ${activeSubTab === "search" ? "primary" : ""}`}
            onClick={() => setActiveSubTab("search")}
          >
            1. Hybrid Search & Reranker
          </button>
          <button
            type="button"
            className={`btn ${activeSubTab === "generate" ? "primary" : ""}`}
            onClick={() => setActiveSubTab("generate")}
          >
            2. Self-Improving RAG (Judge)
          </button>
          <button
            type="button"
            className={`btn ${activeSubTab === "workflow" ? "primary" : ""}`}
            onClick={() => setActiveSubTab("workflow")}
          >
            3. Google LangGraph Workflow
          </button>
        </div>
      </section>

      {/* 1. HYBRID SEARCH & RERANKER TAB */}
      {activeSubTab === "search" && (
        <section className="card">
          <h3>BM25 + ChromaDB Dense Hybrid Retrieval & LLM Reranking</h3>
          <form onSubmit={handleHybridSearch} style={{ display: "flex", flexDirection: "column", gap: "12px", marginTop: "12px" }}>
            <div style={{ display: "flex", gap: "8px", flexWrap: "wrap" }}>
              <input
                className="control"
                style={{ flex: "1 1 320px" }}
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="Enter search query or topic..."
              />
              <select
                className="control"
                value={collection}
                onChange={(e) => setCollection(e.target.value)}
                style={{ width: "200px" }}
              >
                <option value="evidence_items">Evidence Items (152 items)</option>
                <option value="applicant_dossier">Dossier Chunks (263 chunks)</option>
                <option value="opportunities">Opportunities (31 vacancies)</option>
                <option value="professor_papers">Professor Papers (7 papers)</option>
              </select>
              <label style={{ display: "flex", alignItems: "center", gap: "6px", fontSize: "14px" }}>
                <input
                  type="checkbox"
                  checked={useReranker}
                  onChange={(e) => setUseReranker(e.target.checked)}
                />
                Cross-Encoder Reranker
              </label>
              <button type="submit" className="btn primary" disabled={searching}>
                {searching ? "Searching & Reranking..." : "Run Hybrid Search"}
              </button>
            </div>
            <div style={{ display: "flex", gap: "8px", fontSize: "12px", color: "var(--text-muted, #888)" }}>
              <span>Examples:</span>
              <button
                type="button"
                className="star-btn"
                onClick={() => setSearchQuery("Responsible AI safety and uncertainty quantification")}
              >
                AI Safety
              </button>
              <button
                type="button"
                className="star-btn"
                onClick={() => setSearchQuery("Ensemble learning diabetes prediction thesis distinction")}
              >
                MSc Thesis
              </button>
              <button
                type="button"
                className="star-btn"
                onClick={() => setSearchQuery("predictive maintenance telemetry Boeing Azure Kubernetes")}
              >
                Boeing Azure
              </button>
            </div>
          </form>

          {searchError && <div className="banner error" style={{ marginTop: "12px" }}>{searchError}</div>}

          {searchResults.length > 0 && (
            <div style={{ marginTop: "16px", display: "flex", flexDirection: "column", gap: "12px" }}>
              <h4>Top Ranked Candidates ({searchResults.length})</h4>
              {searchResults.map((item, idx) => (
                <div
                  key={item.id || idx}
                  style={{
                    border: "1px solid var(--border-color, #333)",
                    borderRadius: "6px",
                    padding: "12px",
                    background: "rgba(255, 255, 255, 0.02)",
                  }}
                >
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "6px" }}>
                    <strong>[{item.id}]</strong>
                    <div style={{ display: "flex", gap: "8px" }}>
                      {item.rerank_score != null && (
                        <span className="pill ok" style={{ fontWeight: "bold" }}>
                          Rerank Score: {item.rerank_score}/100
                        </span>
                      )}
                      {item.rrf_score != null && (
                        <span className="pill">RRF Score: {item.rrf_score.toFixed(2)}</span>
                      )}
                    </div>
                  </div>
                  {item.rationale && (
                    <p style={{ margin: "4px 0 8px", fontStyle: "italic", fontSize: "13px", color: "#a5d6a7" }}>
                      💡 Rationale: {item.rationale}
                    </p>
                  )}
                  <p style={{ whiteSpace: "pre-wrap", fontSize: "14px", margin: "0" }}>{item.text}</p>
                </div>
              ))}
            </div>
          )}
        </section>
      )}

      {/* 2. SELF-IMPROVING RAG TAB */}
      {activeSubTab === "generate" && (
        <section className="card">
          <h3>Self-Improving RAG (CRAG) with LLM-as-a-Judge & Semantic Cache</h3>
          <form onSubmit={handleSelfRAGGenerate} style={{ display: "flex", flexDirection: "column", gap: "12px", marginTop: "12px" }}>
            <div style={{ display: "flex", gap: "8px" }}>
              <input
                className="control"
                style={{ flex: 1 }}
                value={genQuery}
                onChange={(e) => setGenQuery(e.target.value)}
                placeholder="Topic or requirement to synthesize..."
              />
              <button type="submit" className="btn primary" disabled={generating}>
                {generating ? "Generating & Fact-Checking..." : "Generate with CRAG"}
              </button>
            </div>
          </form>

          {genError && <div className="banner error" style={{ marginTop: "12px" }}>{genError}</div>}

          {genResult && (
            <div style={{ marginTop: "16px", display: "flex", flexDirection: "column", gap: "16px" }}>
              {/* Scorecard */}
              <div
                style={{
                  display: "grid",
                  gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))",
                  gap: "12px",
                  padding: "12px",
                  background: "rgba(0, 0, 0, 0.2)",
                  borderRadius: "8px",
                }}
              >
                <div>
                  <div className="muted" style={{ fontSize: "12px" }}>Judge Verdict</div>
                  <strong style={{ color: genResult.evaluation.passed ? "#81c784" : "#e57373", fontSize: "16px" }}>
                    {genResult.evaluation.passed ? "✓ 100% EVIDENCE COMPLIANT" : "⚠ REVISION REQUIRED"}
                  </strong>
                </div>
                <div>
                  <div className="muted" style={{ fontSize: "12px" }}>Hallucination Score</div>
                  <strong style={{ fontSize: "16px", color: "#81c784" }}>
                    {genResult.evaluation.hallucination_score}/100
                  </strong>
                </div>
                <div>
                  <div className="muted" style={{ fontSize: "12px" }}>Coverage Score</div>
                  <strong style={{ fontSize: "16px", color: "#64b5f6" }}>
                    {genResult.evaluation.coverage_score}/100
                  </strong>
                </div>
                <div>
                  <div className="muted" style={{ fontSize: "12px" }}>Semantic Cache</div>
                  <span className={`pill ${genResult.cache_hit ? "ok" : ""}`}>
                    {genResult.cache_hit ? `⚡ HIT (Sim: ${((genResult.cached_similarity || 0.95) * 100).toFixed(0)}%)` : "MISS (Fresh Generation)"}
                  </span>
                </div>
              </div>

              {/* Critique */}
              {genResult.evaluation.critique && (
                <div style={{ padding: "10px 14px", background: "rgba(255, 255, 255, 0.03)", borderRadius: "6px", fontSize: "13px" }}>
                  <strong>Admissions Judge Critique:</strong> {genResult.evaluation.critique}
                </div>
              )}

              {/* Grounding IDs */}
              {genResult.grounding_evidence_ids.length > 0 && (
                <div style={{ display: "flex", gap: "6px", alignItems: "center", flexWrap: "wrap", fontSize: "12px" }}>
                  <span className="muted">Grounding Evidence Items:</span>
                  {genResult.grounding_evidence_ids.map((id) => (
                    <span key={id} className="pill ok">{id}</span>
                  ))}
                </div>
              )}

              {/* Generated Text */}
              <div
                style={{
                  border: "1px solid var(--border-color, #444)",
                  borderRadius: "8px",
                  padding: "16px",
                  background: "rgba(255, 255, 255, 0.02)",
                  whiteSpace: "pre-wrap",
                  fontFamily: "inherit",
                  fontSize: "14px",
                  lineHeight: "1.6",
                }}
              >
                {genResult.final_text}
              </div>
            </div>
          )}
        </section>
      )}

      {/* 3. GOOGLE WORKFLOW TAB */}
      {activeSubTab === "workflow" && (
        <section className="card">
          <h3>Google GenAI Search Grounding & LangGraph Workflow</h3>
          <p className="muted">
            End-to-end multi-agent doctoral recruitment orchestrator: Discover vacancies live on Google Search, rank by candidate fit, pause at Human-in-the-Loop gate, synthesize application dossier, and verify with critic.
          </p>
          <div style={{ display: "flex", gap: "8px", marginTop: "12px" }}>
            <input
              className="control"
              style={{ flex: 1 }}
              value={wfQuery}
              onChange={(e) => setWfQuery(e.target.value)}
              placeholder="Search topic for Google PhD discovery..."
            />
            <button
              type="button"
              className="btn primary"
              disabled={wfRunning}
              onClick={() => void handleGoogleWorkflow(false)}
            >
              {wfRunning ? "Executing Workflow..." : "1. Discover & Match"}
            </button>
          </div>

          {wfError && <div className="banner error" style={{ marginTop: "12px" }}>{wfError}</div>}

          {wfResult && (
            <div style={{ marginTop: "16px", display: "flex", flexDirection: "column", gap: "16px" }}>
              <div style={{ display: "flex", gap: "8px", alignItems: "center", flexWrap: "wrap" }}>
                <span className="pill ok">Active Node: {wfResult.node}</span>
                <span className="pill">Status: {wfResult.application_status}</span>
                {wfResult.approval_token && (
                  <span className="pill" style={{ color: "#ffd54f" }}>
                    🔑 HMAC Token Issued: {wfResult.approval_token.slice(0, 18)}...
                  </span>
                )}
              </div>

              {/* Human-in-the-loop Gate Banner */}
              {wfResult.node === "human_approval_gate" && (
                <div
                  style={{
                    border: "1px solid #ffd54f",
                    borderRadius: "8px",
                    padding: "16px",
                    background: "rgba(255, 213, 79, 0.05)",
                  }}
                >
                  <h4 style={{ color: "#ffd54f", margin: "0 0 8px" }}>🛑 Human-in-the-Loop (HITL) Gate Paused</h4>
                  <p style={{ margin: "0 0 12px", fontSize: "14px" }}>
                    Vacancies discovered and ranked. To authorize the synthesis of your tailored doctoral application dossier (CV, Cover Letter, Research Proposal) and issue a single-use HMAC token, click Approve below:
                  </p>
                  <button
                    type="button"
                    className="btn primary"
                    disabled={wfRunning}
                    onClick={() => void handleGoogleWorkflow(true)}
                  >
                    ✓ Approve & Synthesize Dossier
                  </button>
                </div>
              )}

              {/* Discovered Vacancies */}
              {wfResult.discovered_vacancies && wfResult.discovered_vacancies.length > 0 && (
                <div>
                  <h4>Discovered Opportunities via Google Search ({wfResult.discovered_vacancies.length})</h4>
                  <table className="data-table" style={{ marginTop: "8px" }}>
                    <thead>
                      <tr>
                        <th>Title</th>
                        <th>Organization</th>
                        <th>Country</th>
                        <th>Funding</th>
                        <th>Action</th>
                      </tr>
                    </thead>
                    <tbody>
                      {wfResult.discovered_vacancies.map((v, i) => (
                        <tr key={i}>
                          <td><strong>{v.title}</strong></td>
                          <td>{v.organization}</td>
                          <td>{v.country}</td>
                          <td>{v.funding}</td>
                          <td>
                            <a href={v.url} target="_blank" rel="noreferrer" className="btn" style={{ fontSize: "12px", padding: "4px 8px" }}>
                              View
                            </a>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}

              {/* Drafted Documents */}
              {wfResult.drafted_documents && Object.keys(wfResult.drafted_documents).length > 0 && (
                <div>
                  <h4>Synthesized Application Dossier</h4>
                  {Object.entries(wfResult.drafted_documents).map(([kind, body]) => (
                    <div
                      key={kind}
                      style={{
                        border: "1px solid var(--border-color, #444)",
                        borderRadius: "8px",
                        padding: "12px",
                        marginTop: "8px",
                        background: "rgba(255, 255, 255, 0.02)",
                      }}
                    >
                      <h5 style={{ margin: "0 0 8px", textTransform: "uppercase" }}>{kind.replace("_", " ")}</h5>
                      <p style={{ whiteSpace: "pre-wrap", fontSize: "13px", margin: "0" }}>{body}</p>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
        </section>
      )}
    </div>
  );
}
