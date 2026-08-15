import { FormEvent, KeyboardEvent, useEffect, useRef, useState } from "react";
import { RagStudio } from "./components/RagStudio";

type Tab =
  | "documents"
  | "advisor"
  | "opportunities"
  | "prepare"
  | "apply"
  | "ops"
  | "monitor"
  | "rag";

type Profile = {
  full_name: string;
  email: string;
  highest_degree: string;
  research_interests: string;
  skills: string;
  funding_requirement: string;
  target_countries: string;
  notes: string;
  profile_summary?: string;
  profile_source?: string;
};

type DocumentRow = {
  id: number;
  original_name: string;
  doc_type: string;
  file_size: number;
  status: string;
};

type FolderInfo = {
  folder: string;
  exists: boolean;
  file_count: number;
};

type Suggestion = {
  id: number;
  title: string;
  summary: string;
  rationale: string;
  next_steps: string;
  priority: string;
};

type ChatMessage = {
  id: number;
  role: string;
  content: string;
};

type Opportunity = {
  id: number;
  title: string;
  organization: string;
  country_code: string;
  source: string;
  source_url: string;
  funding: string;
  supervisor: string;
  deadline: string | null;
  rule_fit: number;
  llm_fit: number | null;
  embed_fit: number | null;
  shortlisted: number;
};

type AgentRun = {
  id: string;
  agent: string;
  action: string;
  status: string;
  input_summary: string;
  error: string;
  duration_ms: number;
};

type Requirement = {
  id: number;
  text: string;
  status: string;
  evidence_note: string;
};

type Paper = {
  id: number;
  title: string;
  year: number | null;
  authors: string;
  venue: string;
  url: string;
};

type Draft = {
  id: number;
  kind: string;
  body: string;
  cited_evidence_ids: string;
  cited_paper_titles: string;
};

type Packet = {
  id: number;
  opportunity_id: number;
  status: string;
  error: string;
  requirements: Requirement[];
  papers: Paper[];
  drafts: Draft[];
};

type ApplyIssue = { level: string; code: string; message: string };

type ApplyPreview = {
  packet_id: number;
  opportunity_id: number;
  adapter_options: string[];
  recommended_adapter?: string;
  apply_as_me?: boolean;
  fields: Record<string, unknown>;
  issues: ApplyIssue[];
  can_request_approval: boolean;
  payload_sha256: string;
};

type ApplyEvent = {
  id: number;
  action: string;
  detail: string;
};

type ApplicationRow = {
  id: number;
  packet_id: number;
  adapter: string;
  status: string;
  payload_sha256: string;
  receipt: string;
  error: string;
  token?: string;
  message?: string;
  events: ApplyEvent[];
};

type TrackerDeadline = {
  id: number;
  title: string;
  deadline: string | null;
  fit: number;
  days_left: number | null;
};

type TrackerPacket = {
  id: number;
  opportunity_id: number;
  title: string;
  status: string;
};

type TrackerApp = {
  id: number;
  packet_id: number;
  status: string;
  adapter: string;
  receipt: string;
};

type DigestRow = {
  id: number;
  message: string;
  query: string;
  new_count: number;
  high_fit_new_count: number;
  deadline_count: number;
  channel: string;
  sent: number;
  error: string;
};

type Tracker = {
  deadline_days: number;
  high_fit_threshold: number;
  packets_ready: number;
  applications_submitted: number;
  deadlines: TrackerDeadline[];
  packets: TrackerPacket[];
  applications: TrackerApp[];
  last_digest: DigestRow | null;
};

type Notice = {
  id: number;
  channel: string;
  body: string;
  status: string;
  error: string;
};

type LlmStatus = {
  deepseek_configured: boolean;
  groq_configured: boolean;
  huggingface_configured?: boolean;
  tavily_configured: boolean;
  brave_configured: boolean;
  gemini_configured?: boolean;
  gemini_model?: string;
  reason_model: string;
  extract_model: string;
};

const DOC_TYPES = [
  { value: "academic_cv", label: "Academic CV" },
  { value: "research_cv", label: "Research CV" },
  { value: "research_proposal", label: "Research proposal" },
  { value: "publication", label: "Publication / paper" },
  { value: "transcript", label: "Transcript" },
  { value: "cover_letter", label: "Cover / motivation letter" },
  { value: "other", label: "Other" },
];

const TABS: { id: Tab; label: string }[] = [
  { id: "documents", label: "Documents" },
  { id: "advisor", label: "Advisor" },
  { id: "opportunities", label: "Opportunities" },
  { id: "prepare", label: "Prepare" },
  { id: "apply", label: "Apply" },
  { id: "ops", label: "Ops" },
  { id: "monitor", label: "Monitor" },
  { id: "rag", label: "RAG & KG Studio" },
];

function errorDetail(body: unknown, fallback: string): string {
  if (body && typeof body === "object" && "detail" in body) {
    const detail = (body as { detail: unknown }).detail;
    if (typeof detail === "string") return detail;
  }
  return fallback;
}

export default function App() {
  const [tab, setTab] = useState<Tab>("documents");
  const [runs, setRuns] = useState<AgentRun[]>([]);
  const [profile, setProfile] = useState<Profile | null>(null);
  const [documents, setDocuments] = useState<DocumentRow[]>([]);
  const [folderInfo, setFolderInfo] = useState<FolderInfo | null>(null);
  const [suggestions, setSuggestions] = useState<Suggestion[]>([]);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [opps, setOpps] = useState<Opportunity[]>([]);
  const [status, setStatus] = useState<LlmStatus | null>(null);
  const [docType, setDocType] = useState("academic_cv");
  const [query, setQuery] = useState(
    "PhD Responsible AI Agentic AI governance autonomous agents",
  );
  const [chatInput, setChatInput] = useState("");
  const [banner, setBanner] = useState("");
  const [bannerError, setBannerError] = useState(false);
  const [importing, setImporting] = useState(false);
  const [analyzing, setAnalyzing] = useState(false);
  const [chatting, setChatting] = useState(false);
  const [discovering, setDiscovering] = useState(false);
  const [preparing, setPreparing] = useState(false);
  const [packets, setPackets] = useState<Packet[]>([]);
  const [activePacketId, setActivePacketId] = useState<number | null>(null);
  const [applyPreview, setApplyPreview] = useState<ApplyPreview | null>(null);
  const [application, setApplication] = useState<ApplicationRow | null>(null);
  const [approvalToken, setApprovalToken] = useState("");
  const [applyAdapter, setApplyAdapter] = useState("email");
  const [applyBusy, setApplyBusy] = useState(false);
  const [tracker, setTracker] = useState<Tracker | null>(null);
  const [notices, setNotices] = useState<Notice[]>([]);
  const [opsBusy, setOpsBusy] = useState(false);
  const chatLogRef = useRef<HTMLDivElement>(null);
  const chatInputRef = useRef<HTMLTextAreaElement>(null);

  async function refresh() {
    try {
      const [p, d, fi, s, m, o, llm, r, pk, apps, tr, notes] = await Promise.all([
        fetch("/api/profile").then((res) => res.json()),
        fetch("/api/documents").then((res) => res.json()),
        fetch("/api/documents/import-folder/info").then((res) => res.json()),
        fetch("/api/advisor/suggestions").then((res) => res.json()),
        fetch("/api/advisor/messages").then((res) => res.json()),
        fetch("/api/opportunities").then((res) => res.json()),
        fetch("/api/llm/status").then((res) => res.json()),
        fetch("/api/monitor/runs").then((res) => res.json()),
        fetch("/api/packets").then((res) => res.json()),
        fetch("/api/applications").then((res) => res.json()),
        fetch("/api/ops/tracker").then((res) => res.json()),
        fetch("/api/notifications").then((res) => res.json()),
      ]);
      if (p) setProfile(p);
        setDocuments(Array.isArray(d) ? d : documents);
        if (fi && typeof fi === "object" && !("detail" in fi)) setFolderInfo(fi as FolderInfo);
        if (Array.isArray(s)) setSuggestions(s);
        if (Array.isArray(m)) setMessages(m);
        if (Array.isArray(o)) setOpps(o);
        if (llm && typeof llm === "object" && !("detail" in llm)) setStatus(llm as LlmStatus);
        if (Array.isArray(r)) setRuns(r);
        if (Array.isArray(pk)) {
          setPackets(pk);
          setActivePacketId((cur) =>
            cur && pk.some((item: Packet) => item.id === cur) ? cur : pk[0]?.id ?? null,
          );
        }
        if (Array.isArray(apps) && apps.length) {
          setApplication(apps[0] as ApplicationRow);
        }
        if (tr && typeof tr === "object" && !("detail" in tr)) setTracker(tr as Tracker);
        if (Array.isArray(notes)) setNotices(notes);
    } catch (err) {
      setBannerError(true);
      setBanner(err instanceof Error ? err.message : "Could not load API");
    }
  }

  useEffect(() => {
    void refresh();
  }, []);

  useEffect(() => {
    const node = chatLogRef.current;
    if (node) node.scrollTop = node.scrollHeight;
  }, [messages, tab]);

  useEffect(() => {
    if (tab === "advisor") {
      chatInputRef.current?.focus();
    }
  }, [tab]);

  useEffect(() => {
    if (tab === "apply" && activePacketId) {
      void loadApplyPreview(activePacketId);
    }
  }, [tab, activePacketId]);

  function note(text: string, isError = false) {
    setBannerError(isError);
    setBanner(text);
  }

  async function importFromFolder() {
    setImporting(true);
    note("Scanning your PHD folder...");
    const res = await fetch("/api/documents/import-folder", { method: "POST" });
    const body = await res.json();
    note(res.ok ? body.message : errorDetail(body, "Import failed"), !res.ok);
    await refresh();
    setImporting(false);
  }

  async function uploadFiles(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const fileInput = form.elements.namedItem("files") as HTMLInputElement;
    if (!fileInput.files?.length) return;
    note("Uploading...");
    for (const file of Array.from(fileInput.files)) {
      const body = new FormData();
      body.append("file", file);
      body.append("doc_type", docType);
      const res = await fetch("/api/documents/upload", { method: "POST", body });
      if (!res.ok) {
        note(errorDetail(await res.json(), "Upload failed"), true);
        return;
      }
    }
    fileInput.value = "";
    note("Documents uploaded.");
    await refresh();
  }

  async function analyzeDocuments() {
    setAnalyzing(true);
    note("Reading documents and building your profile. You can open Advisor while this runs.");
    const res = await fetch("/api/profile/analyze", { method: "POST" });
    const body = await res.json();
    if (!res.ok) {
      note(errorDetail(body, "Analysis failed"), true);
      setAnalyzing(false);
      return;
    }
    note(body.message || "Profile ready.");
    setTab("advisor");
    await refresh();
    setAnalyzing(false);
  }

  async function toggleShortlist(row: Opportunity) {
    const next = !(row.shortlisted === 1);
    const res = await fetch(`/api/opportunities/${row.id}/shortlist`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ shortlisted: next }),
    });
    if (!res.ok) {
      note(errorDetail(await res.json(), "Shortlist update failed"), true);
      return;
    }
    await refresh();
  }

  async function prepareOpportunity(row: Opportunity) {
    setPreparing(true);
    setTab("prepare");
    note(`Preparing packet for ${row.title}…`);
    const res = await fetch(`/api/opportunities/${row.id}/prepare`, { method: "POST" });
    const body = await res.json();
    if (!res.ok) {
      note(errorDetail(body, "Prepare failed"), true);
      setPreparing(false);
      return;
    }
    note("Packet ready: checklist, PI papers, and drafts. You still submit yourself.");
    if (body.id) setActivePacketId(body.id);
    await refresh();
    setPreparing(false);
  }

  async function runNightlyNow() {
    setOpsBusy(true);
    note("Running nightly refresh...");
    const res = await fetch("/api/ops/nightly", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ query, run_search: true }),
    });
    const body = await res.json();
    if (!res.ok) {
      note(errorDetail(body, "Nightly run failed"), true);
      setOpsBusy(false);
      return;
    }
    note(typeof body.message === "string" ? body.message : "Nightly digest ready.");
    await refresh();
    setOpsBusy(false);
  }

  async function loadApplyPreview(packetId: number) {
    const res = await fetch(`/api/packets/${packetId}/apply/preview`);
    const body = await res.json();
    if (!res.ok) {
      note(errorDetail(body, "Apply preview failed"), true);
      setApplyPreview(null);
      return;
    }
    setApplyPreview(body as ApplyPreview);
    if (typeof body.recommended_adapter === "string" && body.recommended_adapter) {
      setApplyAdapter(body.recommended_adapter);
    }
  }

  async function requestApproval() {
    if (!activePacket) return;
    setApplyBusy(true);
    const res = await fetch(`/api/packets/${activePacket.id}/apply/request-approval`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ adapter: applyAdapter }),
    });
    const body = await res.json();
    if (!res.ok) {
      note(errorDetail(body, "Could not issue approval token"), true);
      setApplyBusy(false);
      return;
    }
    setApplication(body as ApplicationRow);
    setApprovalToken(typeof body.token === "string" ? body.token : "");
    note(body.message || "Approval token issued. Review fields, then Approve.");
    setApplyBusy(false);
  }

  async function approveApplication() {
    if (!application || !approvalToken) return;
    setApplyBusy(true);
    const res = await fetch(`/api/applications/${application.id}/approve`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ token: approvalToken }),
    });
    const body = await res.json();
    if (!res.ok) {
      note(errorDetail(body, "Approve failed"), true);
      setApplyBusy(false);
      return;
    }
    setApplication(body as ApplicationRow);
    setApprovalToken("");
    note(
      `Recorded as ${body.status}. Receipt: ${body.receipt || "—"}. ` +
        (body.adapter === "manual"
          ? "Manual adapter only logged the packet."
          : "The agent applied as you on the discovered channel."),
    );
    await refresh();
    setApplyBusy(false);
  }

  async function rejectApplication() {
    if (!application) return;
    setApplyBusy(true);
    const res = await fetch(`/api/applications/${application.id}/reject`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ reason: "Rejected from dashboard" }),
    });
    const body = await res.json();
    if (!res.ok) {
      note(errorDetail(body, "Reject failed"), true);
      setApplyBusy(false);
      return;
    }
    setApplication(body as ApplicationRow);
    setApprovalToken("");
    note("Application rejected. Token invalidated.");
    setApplyBusy(false);
  }

  async function deleteDocument(id: number) {
    await fetch(`/api/documents/${id}`, { method: "DELETE" });
    await refresh();
  }

  async function sendChat() {
    const text = chatInput.trim();
    if (!text || chatting) return;
    setChatting(true);
    try {
      const res = await fetch("/api/advisor/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: text }),
      });
      const raw = await res.text();
      let body: { detail?: string } = {};
      try {
        body = raw ? (JSON.parse(raw) as { detail?: string }) : {};
      } catch {
        note(raw.slice(0, 240) || "Chat failed", true);
        return;
      }
      if (!res.ok) {
        note(errorDetail(body, "Chat failed"), true);
        return;
      }
      setChatInput("");
      await refresh();
    } catch (err) {
      note(err instanceof Error ? err.message : "Chat failed", true);
    } finally {
      setChatting(false);
      chatInputRef.current?.focus();
    }
  }

  function onChatKey(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      void sendChat();
    }
  }

  async function runDiscovery(event: FormEvent) {
    event.preventDefault();
    setDiscovering(true);
    note("Searching EURAXESS, AcademicTransfer, FindAPhD...");
    const res = await fetch("/api/discovery/runs", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ query }),
    });
    const body = await res.json();
    note(
      `Run ${body.status}: found ${body.found_count}, kept ${body.kept_count}${
        body.error ? ` — ${body.error}` : ""
      }`,
      Boolean(body.error),
    );
    await refresh();
    setDiscovering(false);
  }

  const activePacket = packets.find((p) => p.id === activePacketId) ?? packets[0] ?? null;
  const proposalDraft = activePacket?.drafts.find((d) => d.kind === "research_proposal");
  const cvDraft = activePacket?.drafts.find((d) => d.kind === "cv_tailor");
  const coverDraft = activePacket?.drafts.find((d) => d.kind === "cover_letter");
  const outreachDraft = activePacket?.drafts.find((d) => d.kind === "outreach_email");

  const downloadDoc = (kind: string) => {
    if (!activePacket) return;
    window.location.href = `/api/packets/${activePacket.id}/download/${kind}`;
  };

  const copyDraftText = (text?: string, label = "Document") => {
    if (!text) return;
    void navigator.clipboard.writeText(text);
    note(`Copied ${label} to clipboard!`);
  };

  return (
    <div className="app">
      <header className="topbar">
        <h1>ScholarOps AI</h1>
        <p className="lede">
          Multi-agent pipeline for funded PhDs worldwide: Discover, Prepare, then Apply as me.
          One HMAC confirmation pauses before send. You still handle login, CAPTCHA, and fees.
        </p>
        {status && (
          <div className="pills">
            <span className={`pill ${status.deepseek_configured ? "ok" : ""}`}>
              DeepSeek {status.deepseek_configured ? "ready" : "missing"}
            </span>
            <span className={`pill ${status.groq_configured ? "ok" : ""}`}>
              Groq {status.groq_configured ? "ready" : "missing"}
            </span>
            <span className="pill">Reason {status.reason_model}</span>
            <span className="pill">Extract {status.extract_model}</span>
          </div>
        )}
        <nav className="tabs">
          {TABS.map((item) => (
            <button
              key={item.id}
              type="button"
              className={tab === item.id ? "active" : ""}
              onClick={() => setTab(item.id)}
            >
              {item.label}
            </button>
          ))}
        </nav>
      </header>

      {banner && <div className={`banner ${bannerError ? "error" : ""}`}>{banner}</div>}
      {analyzing && (
        <div className="banner">Profile build is running. Advisor tab stays usable.</div>
      )}

      {tab === "documents" && (
        <div className="stack">
          <section className="card">
            <h2>Import from your PHD folder</h2>
            <p className="muted">
              Reads PDF, DOCX, and Markdown from the local folder. Skill files under{" "}
              <code>.agents/</code> are skipped.
            </p>
            {folderInfo && (
              <p className="muted">
                <code>{folderInfo.folder}</code>
                {folderInfo.exists
                  ? ` — ${folderInfo.file_count} file(s)`
                  : " — folder not found"}
              </p>
            )}
            <button
              type="button"
              className="btn primary"
              disabled={importing || !folderInfo?.exists}
              onClick={() => void importFromFolder()}
            >
              {importing ? "Importing..." : "Import all documents"}
            </button>
          </section>

          <section className="card">
            <h3>Optional extra upload</h3>
            <form onSubmit={uploadFiles} className="stack" style={{ gap: 10 }}>
              <label className="field">
                Document type
                <select
                  className="control"
                  value={docType}
                  onChange={(e) => setDocType(e.target.value)}
                >
                  {DOC_TYPES.map((t) => (
                    <option key={t.value} value={t.value}>
                      {t.label}
                    </option>
                  ))}
                </select>
              </label>
              <input type="file" name="files" multiple accept=".pdf,.docx,.txt,.md" />
              <button type="submit" className="btn">
                Upload
              </button>
            </form>
          </section>

          <section className="card">
            <h3>Your files ({documents.length})</h3>
            {documents.length === 0 ? (
              <p className="muted">Import the folder first, then build a profile.</p>
            ) : (
              <ul className="file-list">
                {documents.map((doc) => (
                  <li key={doc.id} className="file-row">
                    <span>
                      <strong>{doc.original_name}</strong> — {doc.doc_type} ({doc.status})
                    </span>
                    <button type="button" className="btn" onClick={() => deleteDocument(doc.id)}>
                      Remove
                    </button>
                  </li>
                ))}
              </ul>
            )}
            <button
              type="button"
              className="btn primary"
              disabled={analyzing || documents.length === 0}
              onClick={() => void analyzeDocuments()}
              style={{ marginTop: 12 }}
            >
              {analyzing ? "Building profile..." : "Build profile and get suggestions"}
            </button>
          </section>

          {profile?.profile_source === "documents" && (
            <section className="card">
              <h3>Generated profile</h3>
              {profile.profile_summary && <p>{profile.profile_summary}</p>}
              <dl className="profile-grid">
                <dt>Name</dt>
                <dd>{profile.full_name || "—"}</dd>
                <dt>Degree</dt>
                <dd>{profile.highest_degree || "—"}</dd>
                <dt>Interests</dt>
                <dd>{profile.research_interests || "—"}</dd>
                <dt>Skills</dt>
                <dd>{profile.skills || "—"}</dd>
              </dl>
            </section>
          )}
        </div>
      )}

      {tab === "advisor" && (
        <div className="advisor">
          <div className="suggestions">
            <section className="card">
              <h2>Research suggestions</h2>
              {suggestions.length === 0 && (
                <p className="muted">
                  Import documents and click Build profile. You can still type in the
                  advisor box on the right.
                </p>
              )}
            </section>
            {suggestions.map((s) => (
              <article key={s.id} className="card suggestion">
                <div className="file-row">
                  <h3>{s.title}</h3>
                  <span className={`priority ${s.priority}`}>{s.priority}</span>
                </div>
                <p>{s.summary}</p>
                <p className="muted">
                  <strong>Why you:</strong> {s.rationale}
                </p>
                <p>
                  <strong>Start here:</strong> {s.next_steps}
                </p>
              </article>
            ))}
          </div>

          <section className="card chat-card">
            <h3>Talk to your advisor</h3>
            <div className="chat-log" ref={chatLogRef}>
              {messages.length === 0 && (
                <p className="muted">Ask how to narrow a topic, what to read, or which group to contact.</p>
              )}
              {messages.map((m) => (
                <div key={m.id} className={`bubble ${m.role === "user" ? "user" : ""}`}>
                  <strong>{m.role === "user" ? "You" : "Advisor"}</strong>
                  <div>{m.content}</div>
                </div>
              ))}
            </div>
            <form
              className="composer"
              onSubmit={(event) => {
                event.preventDefault();
                void sendChat();
              }}
            >
              <textarea
                ref={chatInputRef}
                className="control"
                value={chatInput}
                onChange={(e) => setChatInput(e.target.value)}
                onKeyDown={onChatKey}
                placeholder="Ask about a suggestion, papers to read, or how to narrow the topic..."
                disabled={chatting}
              />
              <div className="composer-row">
                <span className="muted">Enter to send, Shift+Enter for a new line</span>
                <button type="submit" className="btn primary" disabled={chatting || !chatInput.trim()}>
                  {chatting ? "Thinking..." : "Send"}
                </button>
              </div>
            </form>
          </section>
        </div>
      )}

      {tab === "prepare" && (
        <div className="stack">
          <section className="card stack">
            <h2>Application packet</h2>
            <p className="muted">
              Requirements checklist, PI papers (OpenAlex), and evidence-bound drafts. Then Apply —
              the agent finds how to apply and sends as you after one confirmation.
            </p>
            {packets.length === 0 ? (
              <p className="muted">Shortlist a PhD on Opportunities and click Prepare.</p>
            ) : (
              <>
                <label className="field">
                  <span>Packet</span>
                  <select
                    className="control"
                    value={activePacket?.id ?? ""}
                    onChange={(e) => setActivePacketId(Number(e.target.value))}
                  >
                    {packets.map((p) => (
                      <option key={p.id} value={p.id}>
                        #{p.id} · opp {p.opportunity_id} · {p.status}
                      </option>
                    ))}
                  </select>
                </label>
                {activePacket && (
                  <>
                    {activePacket.error && (
                      <p className="muted" style={{ color: "var(--danger)" }}>
                        {activePacket.error}
                      </p>
                    )}
                    <h3>Checklist</h3>
                    <table className="data-table">
                      <thead>
                        <tr>
                          <th>Status</th>
                          <th>Requirement</th>
                          <th>Evidence</th>
                        </tr>
                      </thead>
                      <tbody>
                        {activePacket.requirements.map((req) => (
                          <tr key={req.id}>
                            <td className={`status-${req.status}`}>{req.status}</td>
                            <td>{req.text}</td>
                            <td>{req.evidence_note || "—"}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                    <h3>Professor papers</h3>
                    {activePacket.papers.length === 0 ? (
                      <p className="muted">No papers found (supervisor missing or OpenAlex empty).</p>
                    ) : (
                      <ul className="paper-list">
                        {activePacket.papers.map((paper) => (
                          <li key={paper.id}>
                            <strong>{paper.title}</strong>
                            {paper.year ? ` (${paper.year})` : ""}
                            {paper.authors ? ` — ${paper.authors}` : ""}
                            {paper.url ? (
                              <>
                                {" "}
                                <a href={paper.url} target="_blank" rel="noreferrer">
                                  link
                                </a>
                              </>
                            ) : null}
                          </li>
                        ))}
                      </ul>
                    )}
                    <div className="dossier-banner-row" style={{ marginTop: "16px" }}>
                      <div>
                        <strong>📦 Complete Application Dossier Bundle</strong>
                        <div className="muted" style={{ fontSize: "12px" }}>
                          Includes Cover Letter, Research Proposal, Tailored CV, and Supervisor Email
                        </div>
                      </div>
                      <button
                        type="button"
                        className="btn-sm primary"
                        onClick={() => downloadDoc("dossier")}
                      >
                        📥 Download Full Dossier (.md)
                      </button>
                    </div>

                    <div className="draft-header">
                      <h3>1. Formal Academic Cover Letter</h3>
                      <div className="draft-actions">
                        <button
                          type="button"
                          className="btn-sm"
                          onClick={() => copyDraftText(coverDraft?.body, "Cover Letter")}
                        >
                          📋 Copy
                        </button>
                        <button
                          type="button"
                          className="btn-sm primary"
                          onClick={() => downloadDoc("cover_letter")}
                        >
                          📥 Download (.md)
                        </button>
                      </div>
                    </div>
                    <pre className="draft">{coverDraft?.body || "—"}</pre>

                    <div className="draft-header">
                      <h3>2. PhD Research Proposal / Statement of Purpose</h3>
                      <div className="draft-actions">
                        <button
                          type="button"
                          className="btn-sm"
                          onClick={() => copyDraftText(proposalDraft?.body, "Research Proposal")}
                        >
                          📋 Copy
                        </button>
                        <button
                          type="button"
                          className="btn-sm primary"
                          onClick={() => downloadDoc("research_proposal")}
                        >
                          📥 Download (.md)
                        </button>
                      </div>
                    </div>
                    <pre className="draft">{proposalDraft?.body || "—"}</pre>
                    {proposalDraft?.cited_paper_titles && (
                      <p className="muted" style={{ marginTop: "-4px", marginBottom: "12px", fontSize: "12px" }}>
                        Cited PI papers: {proposalDraft.cited_paper_titles}
                      </p>
                    )}

                    <div className="draft-header">
                      <h3>3. Tailored Academic CV Highlights</h3>
                      <div className="draft-actions">
                        <button
                          type="button"
                          className="btn-sm"
                          onClick={() => copyDraftText(cvDraft?.body, "CV Highlights")}
                        >
                          📋 Copy
                        </button>
                        <button
                          type="button"
                          className="btn-sm primary"
                          onClick={() => downloadDoc("cv_tailor")}
                        >
                          📥 Download (.md)
                        </button>
                      </div>
                    </div>
                    <pre className="draft">{cvDraft?.body || "—"}</pre>

                    <div className="draft-header">
                      <h3>4. Prospective Supervisor Outreach Email</h3>
                      <div className="draft-actions">
                        <button
                          type="button"
                          className="btn-sm"
                          onClick={() => copyDraftText(outreachDraft?.body, "Supervisor Email")}
                        >
                          📋 Copy
                        </button>
                        <button
                          type="button"
                          className="btn-sm primary"
                          onClick={() => downloadDoc("outreach_email")}
                        >
                          📥 Download (.md)
                        </button>
                      </div>
                    </div>
                    <pre className="draft">{outreachDraft?.body || "—"}</pre>

                    {activePacket.status === "ready" && (
                      <div style={{ marginTop: "24px" }}>
                        <button
                          type="button"
                          className="btn primary"
                          onClick={() => setTab("apply")}
                        >
                          Review filled form and proceed to Apply as me →
                        </button>
                      </div>
                    )}
                  </>
                )}
              </>
            )}
          </section>
        </div>
      )}

      {tab === "apply" && (
        <div className="stack">
          <section className="card stack">
            <h2>Apply as me</h2>
            <p className="muted">
              Select a prepared packet. The agent finds the vacancy email or public form. You
              confirm once with a single-use token. Then it sends as you — not a copy-paste into
              a university portal. Login/SSO, CAPTCHA, and payment pages stop for you. Set
              APPLY_AS_ME=true and SMTP (email) or Playwright (portal) in .env.
            </p>
            {packets.length === 0 ? (
              <p className="muted">Prepare a packet first.</p>
            ) : (
              <>
                <label className="field">
                  <span>Packet</span>
                  <select
                    className="control"
                    value={activePacket?.id ?? ""}
                    onChange={(e) => setActivePacketId(Number(e.target.value))}
                  >
                    {packets.map((p) => (
                      <option key={p.id} value={p.id}>
                        #{p.id} · opp {p.opportunity_id} · {p.status}
                      </option>
                    ))}
                  </select>
                </label>
                <label className="field">
                  <span>How the agent applies</span>
                  <select
                    className="control"
                    value={applyAdapter}
                    onChange={(e) => setApplyAdapter(e.target.value)}
                  >
                    <option value="email">email — send CV, letter, and proposal as you</option>
                    <option value="portal">portal — fill the public form as you</option>
                    <option value="sandbox">sandbox — local fake portal (test)</option>
                    <option value="manual">manual — log only, do not send</option>
                  </select>
                </label>
                {applyPreview && (
                  <>
                    <p>
                      Discovered path:{" "}
                      <strong>{String(applyPreview.fields.apply_channel || "unknown")}</strong>
                      {applyPreview.fields.apply_email
                        ? ` · ${String(applyPreview.fields.apply_email)}`
                        : ""}
                      {applyPreview.fields.apply_url
                        ? ` · ${String(applyPreview.fields.apply_url)}`
                        : ""}
                    </p>
                    {applyPreview.fields.apply_notes ? (
                      <p className="muted">{String(applyPreview.fields.apply_notes)}</p>
                    ) : null}
                    {applyPreview.apply_as_me === false && (
                      <p className="muted">
                        APPLY_AS_ME is off. Approval will fail on email/portal until you enable it
                        and configure SMTP or Playwright.
                      </p>
                    )}
                    <h3>Filled fields</h3>
                    <table className="data-table">
                      <thead>
                        <tr>
                          <th>Field</th>
                          <th>Value</th>
                        </tr>
                      </thead>
                      <tbody>
                        {Object.entries(applyPreview.fields)
                          .filter(([key]) => key !== "known_evidence_ids")
                          .map(([key, value]) => (
                            <tr key={key}>
                              <td>{key}</td>
                              <td>{typeof value === "string" ? value || "—" : JSON.stringify(value)}</td>
                            </tr>
                          ))}
                      </tbody>
                    </table>
                    <h3>Validation</h3>
                    {applyPreview.issues.length === 0 ? (
                      <p className="muted">No issues. You may request approval.</p>
                    ) : (
                      <ul className="paper-list">
                        {applyPreview.issues.map((issue) => (
                          <li key={issue.code} className={`status-${issue.level === "error" ? "gap" : "unknown"}`}>
                            {issue.level}: {issue.message}
                          </li>
                        ))}
                      </ul>
                    )}
                    <div className="composer-row">
                      <button
                        type="button"
                        className="btn primary"
                        disabled={applyBusy || !applyPreview.can_request_approval}
                        onClick={() => void requestApproval()}
                      >
                        Request approval token
                      </button>
                      <button
                        type="button"
                        className="btn"
                        disabled={applyBusy || !application || !approvalToken}
                        onClick={() => void approveApplication()}
                      >
                        Approve and apply as me
                      </button>
                      <button
                        type="button"
                        className="btn"
                        disabled={applyBusy || !application}
                        onClick={() => void rejectApplication()}
                      >
                        Reject
                      </button>
                    </div>
                    {application && (
                      <p className="muted">
                        Application #{application.id} · {application.status}
                        {application.receipt ? ` · receipt ${application.receipt}` : ""}
                      </p>
                    )}
                    {application?.events?.length ? (
                      <>
                        <h3>Audit log</h3>
                        <table className="data-table">
                          <thead>
                            <tr>
                              <th>Action</th>
                              <th>Detail</th>
                            </tr>
                          </thead>
                          <tbody>
                            {application.events.map((ev) => (
                              <tr key={ev.id}>
                                <td>{ev.action}</td>
                                <td>{ev.detail}</td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </>
                    ) : null}
                  </>
                )}
              </>
            )}
          </section>
        </div>
      )}

      {tab === "ops" && (
        <div className="stack">
          <section className="card stack">
            <h2>Nightly digest</h2>
            <p className="muted">
              Refreshes listings, then notifies. Telegram is optional. n8n should only POST this
              API on a cron — scoring stays in Python.
            </p>
            {tracker?.last_digest ? (
              <p>
                <strong>{tracker.last_digest.message}</strong>
              </p>
            ) : (
              <p className="muted">No nightly run yet.</p>
            )}
            <button
              type="button"
              className="btn primary"
              disabled={opsBusy}
              onClick={() => void runNightlyNow()}
            >
              {opsBusy ? "Running nightly..." : "Run nightly now"}
            </button>
            <p className="muted">
              Packets ready: {tracker?.packets_ready ?? 0} · Submitted:{" "}
              {tracker?.applications_submitted ?? 0}
            </p>
          </section>
          <section className="card stack">
            <h2>Deadlines</h2>
            {!tracker?.deadlines?.length ? (
              <p className="muted">No deadlines in the next {tracker?.deadline_days ?? 7} days.</p>
            ) : (
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Title</th>
                    <th>Deadline</th>
                    <th>Days</th>
                    <th>Fit</th>
                  </tr>
                </thead>
                <tbody>
                  {tracker.deadlines.map((row) => (
                    <tr key={row.id}>
                      <td>{row.title}</td>
                      <td>{row.deadline || "—"}</td>
                      <td>{row.days_left ?? "—"}</td>
                      <td>{row.fit}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </section>
          <section className="card stack">
            <h2>Application tracking</h2>
            {!tracker?.applications?.length && !tracker?.packets?.length ? (
              <p className="muted">Prepare a packet, then Apply, to track status here.</p>
            ) : (
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Kind</th>
                    <th>Id</th>
                    <th>Status</th>
                    <th>Detail</th>
                  </tr>
                </thead>
                <tbody>
                  {(tracker?.packets ?? []).map((row) => (
                    <tr key={`p-${row.id}`}>
                      <td>Packet</td>
                      <td>{row.id}</td>
                      <td>{row.status}</td>
                      <td>{row.title}</td>
                    </tr>
                  ))}
                  {(tracker?.applications ?? []).map((row) => (
                    <tr key={`a-${row.id}`}>
                      <td>Application</td>
                      <td>{row.id}</td>
                      <td>{row.status}</td>
                      <td>
                        {row.adapter}
                        {row.receipt ? ` · ${row.receipt}` : ""}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </section>
          <section className="card stack">
            <h2>Notifications</h2>
            {notices.length === 0 ? (
              <p className="muted">No notifications yet.</p>
            ) : (
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Channel</th>
                    <th>Status</th>
                    <th>Body</th>
                  </tr>
                </thead>
                <tbody>
                  {notices.map((row) => (
                    <tr key={row.id}>
                      <td>{row.channel}</td>
                      <td>{row.status}</td>
                      <td>{row.body}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </section>
        </div>
      )}

      {tab === "monitor" && (
        <section className="card stack">
          <h2>Agent traces</h2>
          <p className="muted">Failures are also in data/logs/agent-runs.jsonl.</p>
          {runs.length === 0 ? (
            <p className="muted">No agent runs yet.</p>
          ) : (
            <table className="data-table">
              <thead>
                <tr>
                  <th>Status</th>
                  <th>Agent</th>
                  <th>Action</th>
                  <th>ms</th>
                  <th>Detail</th>
                </tr>
              </thead>
              <tbody>
                {runs.map((run) => (
                  <tr key={run.id}>
                    <td style={{ color: run.status === "error" ? "var(--danger)" : "var(--ok)" }}>
                      {run.status}
                    </td>
                    <td>{run.agent}</td>
                    <td>{run.action}</td>
                    <td>{run.duration_ms}</td>
                    <td>{run.error || run.input_summary || "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </section>
      )}

      {tab === "opportunities" && (
        <div className="stack">
          <form className="search-row" onSubmit={runDiscovery}>
            <input
              className="control"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
            />
            <button type="submit" className="btn primary" disabled={discovering}>
              {discovering ? "Searching..." : "Discover"}
            </button>
          </form>
          <section className="card">
            <table className="data-table">
              <thead>
                <tr>
                  <th></th>
                  <th>Fit</th>
                  <th>Semantic</th>
                  <th>Title</th>
                  <th>Country</th>
                  <th>Funding</th>
                  <th>Supervisor</th>
                  <th>Source</th>
                  <th>Deadline</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {opps.map((row) => (
                  <tr key={row.id} className={row.shortlisted ? "shortlisted" : ""}>
                    <td>
                      <button
                        type="button"
                        className={`star-btn ${row.shortlisted ? "on" : ""}`}
                        aria-label={row.shortlisted ? "Remove shortlist" : "Shortlist"}
                        title={row.shortlisted ? "Remove shortlist" : "Shortlist"}
                        onClick={() => void toggleShortlist(row)}
                      >
                        {row.shortlisted ? "★" : "☆"}
                      </button>
                    </td>
                    <td>{Math.round(row.llm_fit ?? row.rule_fit)}</td>
                    <td>{row.embed_fit != null ? Math.round(row.embed_fit) : "—"}</td>
                    <td>
                      <a href={row.source_url} target="_blank" rel="noreferrer">
                        {row.title}
                      </a>
                    </td>
                    <td>{row.country_code || "—"}</td>
                    <td>{row.funding || "—"}</td>
                    <td>{row.supervisor || "—"}</td>
                    <td>{row.source}</td>
                    <td>{row.deadline || "—"}</td>
                    <td>
                      <button
                        type="button"
                        className="btn"
                        disabled={preparing}
                        onClick={() => void prepareOpportunity(row)}
                      >
                        Prepare
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            {opps.length === 0 && (
              <p className="muted">Build a profile, then discover funded PhDs.</p>
            )}
          </section>
        </div>
      )}

      {tab === "rag" && <RagStudio />}
    </div>
  );
}
