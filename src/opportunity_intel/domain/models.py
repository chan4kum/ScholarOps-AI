from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Date, DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class UserProfile(Base):
    __tablename__ = "user_profiles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    full_name: Mapped[str] = mapped_column(String(200), default="")
    email: Mapped[str] = mapped_column(String(200), default="")
    highest_degree: Mapped[str] = mapped_column(String(200), default="")
    research_interests: Mapped[str] = mapped_column(Text, default="")
    skills: Mapped[str] = mapped_column(Text, default="")
    funding_requirement: Mapped[str] = mapped_column(String(100), default="fully_funded")
    target_countries: Mapped[str] = mapped_column(String(200), default="")
    notes: Mapped[str] = mapped_column(Text, default="")
    profile_summary: Mapped[str] = mapped_column(Text, default="")
    profile_source: Mapped[str] = mapped_column(String(40), default="manual")
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class UploadedDocument(Base):
    __tablename__ = "uploaded_documents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    original_name: Mapped[str] = mapped_column(String(500))
    stored_name: Mapped[str] = mapped_column(String(500), unique=True)
    doc_type: Mapped[str] = mapped_column(String(80), default="other")
    mime_type: Mapped[str] = mapped_column(String(120), default="")
    file_size: Mapped[int] = mapped_column(Integer, default=0)
    extracted_text: Mapped[str] = mapped_column(Text, default="")
    parsed_facts: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(40), default="uploaded")
    source_path: Mapped[str] = mapped_column(String(1000), default="", index=True)
    content_hash: Mapped[str] = mapped_column(String(64), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    evidence_items: Mapped[list[EvidenceItem]] = relationship(back_populates="document")


class EvidenceItem(Base):
    __tablename__ = "evidence_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    document_id: Mapped[int | None] = mapped_column(
        ForeignKey("uploaded_documents.id"), nullable=True
    )
    category: Mapped[str] = mapped_column(String(80), default="general")
    content: Mapped[str] = mapped_column(Text)
    source_quote: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    document: Mapped[UploadedDocument | None] = relationship(back_populates="evidence_items")


class ResearchSuggestion(Base):
    __tablename__ = "research_suggestions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(500))
    summary: Mapped[str] = mapped_column(Text, default="")
    rationale: Mapped[str] = mapped_column(Text, default="")
    next_steps: Mapped[str] = mapped_column(Text, default="")
    priority: Mapped[str] = mapped_column(String(20), default="medium")
    active: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class AdvisorMessage(Base):
    __tablename__ = "advisor_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    role: Mapped[str] = mapped_column(String(20))
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class Opportunity(Base):
    __tablename__ = "opportunities"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    kind: Mapped[str] = mapped_column(String(20), default="phd")
    source: Mapped[str] = mapped_column(String(50), default="")
    title: Mapped[str] = mapped_column(String(500))
    organization: Mapped[str] = mapped_column(String(300), default="")
    country_code: Mapped[str] = mapped_column(String(8), default="")
    location: Mapped[str] = mapped_column(String(300), default="")
    source_url: Mapped[str] = mapped_column(String(1000), unique=True)
    funding: Mapped[str] = mapped_column(String(200), default="")
    deadline: Mapped[date | None] = mapped_column(Date, nullable=True)
    summary: Mapped[str] = mapped_column(Text, default="")
    supervisor: Mapped[str] = mapped_column(String(300), default="")
    rule_fit: Mapped[float] = mapped_column(Float, default=0.0)
    llm_fit: Mapped[float | None] = mapped_column(Float, nullable=True)
    embed_fit: Mapped[float | None] = mapped_column(Float, nullable=True)
    fit_rationale: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(40), default="discovered")
    shortlisted: Mapped[int] = mapped_column(Integer, default=0)
    apply_channel: Mapped[str] = mapped_column(String(40), default="")
    apply_url: Mapped[str] = mapped_column(String(1000), default="")
    apply_email: Mapped[str] = mapped_column(String(300), default="")
    apply_notes: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class DiscoveryRun(Base):
    __tablename__ = "discovery_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    query: Mapped[str] = mapped_column(String(500))
    status: Mapped[str] = mapped_column(String(40), default="running")
    found_count: Mapped[int] = mapped_column(Integer, default=0)
    kept_count: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class AgentRun(Base):
    __tablename__ = "agent_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    agent: Mapped[str] = mapped_column(String(80), index=True)
    action: Mapped[str] = mapped_column(String(80), default="")
    status: Mapped[str] = mapped_column(String(20), default="running", index=True)
    input_summary: Mapped[str] = mapped_column(Text, default="")
    output_summary: Mapped[str] = mapped_column(Text, default="")
    error: Mapped[str] = mapped_column(Text, default="")
    duration_ms: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    spans: Mapped[list[AgentSpan]] = relationship(back_populates="run")


class AgentSpan(Base):
    __tablename__ = "agent_spans"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("agent_runs.id"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    status: Mapped[str] = mapped_column(String(20), default="ok")
    detail: Mapped[str] = mapped_column(Text, default="")
    duration_ms: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    run: Mapped[AgentRun] = relationship(back_populates="spans")


class ApplicationPacket(Base):
    """Phase 2 document packet for one opportunity. Human still submits."""

    __tablename__ = "application_packets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    opportunity_id: Mapped[int] = mapped_column(ForeignKey("opportunities.id"), unique=True)
    status: Mapped[str] = mapped_column(String(40), default="preparing")
    error: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    opportunity: Mapped[Opportunity] = relationship()
    requirements: Mapped[list[RequirementItem]] = relationship(
        back_populates="packet", cascade="all, delete-orphan"
    )
    papers: Mapped[list[ProfessorPaper]] = relationship(
        back_populates="packet", cascade="all, delete-orphan"
    )
    drafts: Mapped[list[DraftDocument]] = relationship(
        back_populates="packet", cascade="all, delete-orphan"
    )


class RequirementItem(Base):
    __tablename__ = "requirement_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    packet_id: Mapped[int] = mapped_column(ForeignKey("application_packets.id"), index=True)
    text: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="unknown")
    evidence_note: Mapped[str] = mapped_column(Text, default="")

    packet: Mapped[ApplicationPacket] = relationship(back_populates="requirements")


class ProfessorPaper(Base):
    __tablename__ = "professor_papers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    packet_id: Mapped[int] = mapped_column(ForeignKey("application_packets.id"), index=True)
    title: Mapped[str] = mapped_column(String(800))
    year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    authors: Mapped[str] = mapped_column(String(500), default="")
    venue: Mapped[str] = mapped_column(String(400), default="")
    url: Mapped[str] = mapped_column(String(1000), default="")

    packet: Mapped[ApplicationPacket] = relationship(back_populates="papers")


class DraftDocument(Base):
    __tablename__ = "draft_documents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    packet_id: Mapped[int] = mapped_column(ForeignKey("application_packets.id"), index=True)
    kind: Mapped[str] = mapped_column(String(40))
    body: Mapped[str] = mapped_column(Text, default="")
    cited_evidence_ids: Mapped[str] = mapped_column(Text, default="[]")
    cited_paper_titles: Mapped[str] = mapped_column(Text, default="[]")

    packet: Mapped[ApplicationPacket] = relationship(back_populates="drafts")


class Application(Base):
    """Phase 3 assisted apply. Submit only after a human approval token."""

    __tablename__ = "applications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    packet_id: Mapped[int] = mapped_column(ForeignKey("application_packets.id"), unique=True)
    adapter: Mapped[str] = mapped_column(String(40), default="manual")
    status: Mapped[str] = mapped_column(String(40), default="previewed")
    payload_json: Mapped[str] = mapped_column(Text, default="{}")
    payload_sha256: Mapped[str] = mapped_column(String(64), default="")
    token_hash: Mapped[str] = mapped_column(String(64), default="")
    token_expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    token_used: Mapped[int] = mapped_column(Integer, default=0)
    receipt: Mapped[str] = mapped_column(String(500), default="")
    error: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    packet: Mapped[ApplicationPacket] = relationship()
    events: Mapped[list[ApplicationEvent]] = relationship(
        back_populates="application", cascade="all, delete-orphan"
    )


class NightlyDigest(Base):
    """One scheduled ops cycle: discovery refresh + notification text."""

    __tablename__ = "nightly_digests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    query: Mapped[str] = mapped_column(String(500), default="")
    new_count: Mapped[int] = mapped_column(Integer, default=0)
    high_fit_new_count: Mapped[int] = mapped_column(Integer, default=0)
    deadline_count: Mapped[int] = mapped_column(Integer, default=0)
    message: Mapped[str] = mapped_column(Text, default="")
    channel: Mapped[str] = mapped_column(String(40), default="log")
    sent: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    channel: Mapped[str] = mapped_column(String(40), default="log")
    body: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(20), default="queued")
    error: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class ApplicationEvent(Base):
    __tablename__ = "application_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    application_id: Mapped[int] = mapped_column(ForeignKey("applications.id"), index=True)
    action: Mapped[str] = mapped_column(String(80))
    detail: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    application: Mapped[Application] = relationship(back_populates="events")


class PipelineCheckpoint(Base):
    __tablename__ = "pipeline_checkpoints"

    thread_id: Mapped[str] = mapped_column(String(80), primary_key=True)
    state_json: Mapped[str] = mapped_column(Text, default="")
    updated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
