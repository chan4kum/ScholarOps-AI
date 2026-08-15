from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field


class ProfileIn(BaseModel):
    full_name: str = ""
    email: str = ""
    highest_degree: str = ""
    research_interests: str = ""
    skills: str = ""
    funding_requirement: str = "fully_funded"
    target_countries: str = ""
    notes: str = ""


class ProfileOut(ProfileIn):
    model_config = ConfigDict(from_attributes=True)
    id: int
    profile_summary: str = ""
    profile_source: str = "manual"
    updated_at: datetime | None = None


class DocumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    original_name: str
    doc_type: str
    mime_type: str
    file_size: int
    status: str
    source_path: str = ""
    created_at: datetime | None = None


class FolderImportInfoOut(BaseModel):
    folder: str
    exists: bool
    file_count: int


class FolderImportResultOut(BaseModel):
    folder: str
    scanned: int
    imported: int
    skipped: int
    errors: list[str]
    message: str


class ResearchSuggestionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    title: str
    summary: str
    rationale: str
    next_steps: str
    priority: str


class AdvisorMessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    role: str
    content: str
    created_at: datetime | None = None


class AnalyzeResultOut(BaseModel):
    profile: ProfileOut
    suggestions: list[ResearchSuggestionOut]
    message: str
    parsed_count: int = 0
    failed_count: int = 0


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)


class ShortlistRequest(BaseModel):
    shortlisted: bool = True


class ChatResponse(BaseModel):
    reply: AdvisorMessageOut


class OpportunityOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    kind: str
    source: str
    title: str
    organization: str
    country_code: str
    location: str
    source_url: str
    funding: str
    deadline: date | None
    summary: str
    supervisor: str
    rule_fit: float
    llm_fit: float | None
    embed_fit: float | None = None
    fit_rationale: str
    status: str
    shortlisted: int = 0


class DiscoveryRequest(BaseModel):
    query: str = Field(
        min_length=3,
        examples=["funded PhD Responsible AI Agentic AI governance"],
    )


class DiscoveryRunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    query: str
    status: str
    found_count: int
    kept_count: int
    error: str


class LlmStatusOut(BaseModel):
    deepseek_configured: bool
    groq_configured: bool
    huggingface_configured: bool
    tavily_configured: bool
    brave_configured: bool
    gemini_configured: bool = False
    gemini_model: str = "gemini-2.5-flash"
    openai_configured: bool = False
    openai_model: str = "gpt-5-nano-2025-08-07"
    offline: bool
    polish_enabled: bool
    reason_model: str
    extract_model: str
    draft_model: str
    target_countries: list[str]
    excluded_countries: list[str]


class AgentSpanOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    status: str
    detail: str
    duration_ms: int
    created_at: datetime | None = None


class AgentRunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    agent: str
    action: str
    status: str
    input_summary: str
    output_summary: str
    error: str
    duration_ms: int
    created_at: datetime | None = None
    finished_at: datetime | None = None
    spans: list[AgentSpanOut] = []


class MonitorHealthOut(BaseModel):
    ok: bool
    failed_runs: int
    log_file: str
    last_failures: list[AgentRunOut]


class EvidenceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    category: str
    content: str
    source_quote: str


class RequirementOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    text: str
    status: str
    evidence_note: str


class ProfessorPaperOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    title: str
    year: int | None
    authors: str
    venue: str
    url: str


class DraftDocumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    kind: str
    body: str
    cited_evidence_ids: str
    cited_paper_titles: str


class PacketOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    opportunity_id: int
    status: str
    error: str
    requirements: list[RequirementOut] = []
    papers: list[ProfessorPaperOut] = []
    drafts: list[DraftDocumentOut] = []


class ApplyIssueOut(BaseModel):
    level: str
    code: str
    message: str


class ApplyPreviewOut(BaseModel):
    packet_id: int
    opportunity_id: int
    adapter_options: list[str]
    recommended_adapter: str = "email"
    apply_as_me: bool = False
    fields: dict
    issues: list[ApplyIssueOut]
    can_request_approval: bool
    payload_sha256: str


class ApprovalRequest(BaseModel):
    adapter: str = Field(default="", pattern="^(|manual|sandbox|email|portal)$")


class ApproveRequest(BaseModel):
    token: str = Field(min_length=16, max_length=400)


class RejectRequest(BaseModel):
    reason: str = Field(default="", max_length=2000)


class ApplicationEventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    action: str
    detail: str
    created_at: datetime | None = None


class ApplicationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    packet_id: int
    adapter: str
    status: str
    payload_sha256: str
    receipt: str
    error: str
    created_at: datetime | None = None
    submitted_at: datetime | None = None
    events: list[ApplicationEventOut] = []


class ApprovalIssuedOut(ApplicationOut):
    token: str
    token_expires_at: datetime | None = None
    message: str


class NightlyRequest(BaseModel):
    query: str | None = Field(default=None, max_length=500)
    run_search: bool = True


class NightlyDigestOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    query: str
    new_count: int
    high_fit_new_count: int
    deadline_count: int
    message: str
    channel: str
    sent: int
    error: str
    created_at: datetime | None = None


class NotificationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    channel: str
    body: str
    status: str
    error: str
    created_at: datetime | None = None


class OpsToolRequest(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    arguments: dict = Field(default_factory=dict)


class OpsToolOut(BaseModel):
    name: str
    result: dict


class OpsToolsListOut(BaseModel):
    tools: list[str]


class PipelineRequest(BaseModel):
    research_query: str = Field(default="", max_length=500)
    thread_id: str = Field(default="", max_length=80)
    human_approved: bool = False
    reject: bool = False
    approval_token: str = Field(default="", max_length=400)


class PipelineOut(BaseModel):
    thread_id: str
    node: str = ""
    application_status: str = ""
    error: str = ""
    human_approved: bool = False
    discovered_labs: list[dict] = []
    matched_pis: list[dict] = []
    drafted_documents: dict[str, str] = {}
    opportunity_id: int | None = None
    packet_id: int | None = None
    application_id: int | None = None
    approval_token: str = ""
    adapter: str = ""
