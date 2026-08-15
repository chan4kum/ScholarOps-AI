from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from sqlalchemy.orm import Session, joinedload, selectinload

from opportunity_intel.agents.advisor import build_profile_from_documents, chat_with_advisor
from opportunity_intel.api.deps import get_db
from opportunity_intel.api.schemas import (
    AdvisorMessageOut,
    AgentRunOut,
    AnalyzeResultOut,
    ApplicationOut,
    ApplyPreviewOut,
    ApprovalIssuedOut,
    ApprovalRequest,
    ApproveRequest,
    ChatRequest,
    ChatResponse,
    DiscoveryRequest,
    DiscoveryRunOut,
    DocumentOut,
    EvidenceOut,
    FolderImportInfoOut,
    FolderImportResultOut,
    LlmStatusOut,
    MonitorHealthOut,
    NightlyDigestOut,
    NightlyRequest,
    NotificationOut,
    OpportunityOut,
    OpsToolOut,
    OpsToolRequest,
    OpsToolsListOut,
    PacketOut,
    PipelineOut,
    PipelineRequest,
    ProfileOut,
    RejectRequest,
    ResearchSuggestionOut,
    ShortlistRequest,
)
from opportunity_intel.apply.service import (
    approve_and_submit,
    preview_application,
    reject_application,
    request_approval,
)
from opportunity_intel.discovery.service import run_discovery
from opportunity_intel.documents.extract import extract_text
from opportunity_intel.documents.import_folder import (
    import_documents_from_folder,
    iter_importable_files,
    resolve_import_dir,
)
from opportunity_intel.documents.storage import delete_stored_file, save_upload
from opportunity_intel.domain.models import (
    AdvisorMessage,
    AgentRun,
    Application,
    ApplicationPacket,
    EvidenceItem,
    NightlyDigest,
    Notification,
    ResearchSuggestion,
    UploadedDocument,
    UserProfile,
)
from opportunity_intel.llm.budget import BudgetExceeded
from opportunity_intel.observability.trace import jsonl_path
from opportunity_intel.ops.nightly import run_nightly_cycle
from opportunity_intel.ops.tools import ToolError, invoke_tool, list_tools
from opportunity_intel.ops.tracker import build_tracker
from opportunity_intel.prepare.service import prepare_packet

router = APIRouter()

ALLOWED_DOC_TYPES = {
    "academic_cv",
    "research_cv",
    "research_proposal",
    "publication",
    "transcript",
    "cover_letter",
    "other",
}


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/api/llm/status", response_model=LlmStatusOut)
def llm_status(request: Request) -> LlmStatusOut:
    settings = request.app.state.settings
    cfg = request.app.state.model_config
    return LlmStatusOut(
        deepseek_configured=bool(settings.deepseek_api_key),
        groq_configured=bool(settings.groq_api_key),
        huggingface_configured=bool(settings.hf_token),
        tavily_configured=bool(settings.tavily_api_key),
        brave_configured=bool(settings.brave_api_key),
        gemini_configured=bool(settings.gemini_api_key),
        gemini_model=settings.gemini_model,
        openai_configured=bool(settings.openai_api_key),
        openai_model=settings.openai_model,
        offline=settings.offline,
        polish_enabled=settings.groq_polish_enabled,
        reason_model=cfg.roles["reason"].model,
        extract_model=cfg.roles["extract"].model,
        draft_model=cfg.roles["draft"].model,
        target_countries=list(cfg.target_countries),
        excluded_countries=list(cfg.excluded_countries),
    )


@router.get("/api/profile", response_model=ProfileOut | None)
def get_profile(db: Session = Depends(get_db)) -> UserProfile | None:
    return db.query(UserProfile).order_by(UserProfile.id).first()


@router.get("/api/documents", response_model=list[DocumentOut])
def list_documents(db: Session = Depends(get_db)) -> list[UploadedDocument]:
    return db.query(UploadedDocument).order_by(UploadedDocument.id.desc()).all()


@router.get("/api/documents/import-folder/info", response_model=FolderImportInfoOut)
def import_folder_info(request: Request) -> FolderImportInfoOut:
    root = resolve_import_dir(request.app.state.settings)
    files = iter_importable_files(root) if root.is_dir() else []
    return FolderImportInfoOut(folder=str(root), exists=root.is_dir(), file_count=len(files))


@router.post("/api/documents/import-folder", response_model=FolderImportResultOut)
def import_folder(request: Request, db: Session = Depends(get_db)) -> FolderImportResultOut:
    result = import_documents_from_folder(db, request.app.state.settings)
    if result.errors and result.scanned == 0 and result.imported == 0:
        raise HTTPException(status_code=400, detail="; ".join(result.errors))
    message = (
        f"Imported {result.imported} file(s) from {result.folder}. "
        f"Skipped {result.skipped} unchanged."
    )
    if result.errors:
        message += f" {len(result.errors)} error(s)."
    return FolderImportResultOut(
        folder=result.folder,
        scanned=result.scanned,
        imported=result.imported,
        skipped=result.skipped,
        errors=result.errors,
        message=message,
    )


@router.post("/api/documents/upload", response_model=DocumentOut)
async def upload_document(
    request: Request,
    file: UploadFile = File(...),
    doc_type: str = Form("other"),
    db: Session = Depends(get_db),
) -> UploadedDocument:
    if doc_type not in ALLOWED_DOC_TYPES:
        allowed = ", ".join(sorted(ALLOWED_DOC_TYPES))
        raise HTTPException(status_code=400, detail=f"Invalid doc_type. Use one of: {allowed}")

    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="Empty file")
    if len(data) > 15 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="File too large (max 15MB)")

    settings = request.app.state.settings
    stored_name, path = save_upload(settings, file.filename or "document.bin", data)
    try:
        text = extract_text(path, file.content_type or "")
    except ValueError as exc:
        delete_stored_file(settings, stored_name)
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        delete_stored_file(settings, stored_name)
        raise HTTPException(status_code=400, detail=f"Could not read file: {exc}") from exc

    row = UploadedDocument(
        original_name=file.filename or stored_name,
        stored_name=stored_name,
        doc_type=doc_type,
        mime_type=file.content_type or "",
        file_size=len(data),
        extracted_text=text,
        status="uploaded",
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


@router.delete("/api/documents/{document_id}")
def delete_document(
    document_id: int,
    request: Request,
    db: Session = Depends(get_db),
) -> dict[str, str]:
    row = db.query(UploadedDocument).filter_by(id=document_id).one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Document not found")
    delete_stored_file(request.app.state.settings, row.stored_name)
    db.delete(row)
    db.commit()
    return {"status": "deleted"}


@router.post("/api/profile/analyze", response_model=AnalyzeResultOut)
def analyze_documents(request: Request, db: Session = Depends(get_db)) -> AnalyzeResultOut:
    settings = request.app.state.settings
    if not settings.deepseek_api_key or not settings.groq_api_key:
        raise HTTPException(
            status_code=503,
            detail="DeepSeek and Groq API keys required for document analysis.",
        )
    try:
        profile, suggestions, _ = build_profile_from_documents(
            db, settings, request.app.state.model_config
        )
    except BudgetExceeded as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    parsed_count = db.query(UploadedDocument).filter_by(status="parsed").count()
    failed_count = db.query(UploadedDocument).filter_by(status="failed").count()
    message = (
        f"Profile built from your documents "
        f"({parsed_count} parsed, {failed_count} failed). "
        "See Advisor tab for suggestions and chat."
    )
    return AnalyzeResultOut(
        profile=ProfileOut.model_validate(profile, from_attributes=True),
        suggestions=[
            ResearchSuggestionOut.model_validate(s, from_attributes=True) for s in suggestions
        ],
        message=message,
        parsed_count=parsed_count,
        failed_count=failed_count,
    )


@router.get("/api/advisor/suggestions", response_model=list[ResearchSuggestionOut])
def list_suggestions(db: Session = Depends(get_db)) -> list[ResearchSuggestion]:
    return db.query(ResearchSuggestion).filter_by(active=1).order_by(ResearchSuggestion.id).all()


@router.get("/api/advisor/messages", response_model=list[AdvisorMessageOut])
def list_messages(db: Session = Depends(get_db)) -> list[AdvisorMessage]:
    return db.query(AdvisorMessage).order_by(AdvisorMessage.id).all()


@router.post("/api/advisor/chat", response_model=ChatResponse)
def advisor_chat(
    payload: ChatRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> ChatResponse:
    settings = request.app.state.settings
    if not settings.deepseek_api_key:
        raise HTTPException(status_code=503, detail="DeepSeek API key required for advisor chat.")
    try:
        reply = chat_with_advisor(db, settings, request.app.state.model_config, payload.message)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return ChatResponse(reply=AdvisorMessageOut.model_validate(reply, from_attributes=True))


@router.get("/api/opportunities", response_model=list[OpportunityOut])
def list_opportunities(db: Session = Depends(get_db)) -> list:
    from opportunity_intel.domain.models import Opportunity

    return (
        db.query(Opportunity)
        .order_by(
            Opportunity.shortlisted.desc(),
            Opportunity.llm_fit.desc().nulls_last(),
            Opportunity.embed_fit.desc().nulls_last(),
            Opportunity.rule_fit.desc(),
            Opportunity.id.desc(),
        )
        .limit(200)
        .all()
    )


@router.post("/api/opportunities/{opportunity_id}/shortlist", response_model=OpportunityOut)
def shortlist_opportunity(
    opportunity_id: int,
    payload: ShortlistRequest,
    db: Session = Depends(get_db),
) -> OpportunityOut:
    from opportunity_intel.domain.models import Opportunity

    row = db.query(Opportunity).filter_by(id=opportunity_id).one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Opportunity not found")
    row.shortlisted = 1 if payload.shortlisted else 0
    db.commit()
    db.refresh(row)
    return OpportunityOut.model_validate(row, from_attributes=True)


@router.get("/api/evidence", response_model=list[EvidenceOut])
def list_evidence(db: Session = Depends(get_db)) -> list[EvidenceItem]:
    return db.query(EvidenceItem).order_by(EvidenceItem.id).limit(400).all()


@router.post("/api/opportunities/{opportunity_id}/prepare", response_model=PacketOut)
def prepare_opportunity(
    opportunity_id: int,
    request: Request,
    db: Session = Depends(get_db),
) -> ApplicationPacket:
    settings = request.app.state.settings
    try:
        packet = prepare_packet(db, opportunity_id, settings, request.app.state.model_config)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except BudgetExceeded as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    loaded = (
        db.query(ApplicationPacket)
        .options(
            selectinload(ApplicationPacket.requirements),
            selectinload(ApplicationPacket.papers),
            selectinload(ApplicationPacket.drafts),
        )
        .filter_by(id=packet.id)
        .one()
    )
    return loaded


@router.get("/api/packets", response_model=list[PacketOut])
def list_packets(db: Session = Depends(get_db)) -> list[ApplicationPacket]:
    return (
        db.query(ApplicationPacket)
        .options(
            selectinload(ApplicationPacket.requirements),
            selectinload(ApplicationPacket.papers),
            selectinload(ApplicationPacket.drafts),
        )
        .order_by(ApplicationPacket.id.desc())
        .limit(50)
        .all()
    )


@router.get("/api/packets/{packet_id}", response_model=PacketOut)
def get_packet(packet_id: int, db: Session = Depends(get_db)) -> ApplicationPacket:
    row = (
        db.query(ApplicationPacket)
        .options(
            selectinload(ApplicationPacket.requirements),
            selectinload(ApplicationPacket.papers),
            selectinload(ApplicationPacket.drafts),
        )
        .filter_by(id=packet_id)
        .one_or_none()
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Packet not found")
    return row


@router.get("/api/packets/{packet_id}/download/{kind}")
def download_packet_document(
    packet_id: int,
    kind: str,
    db: Session = Depends(get_db),
) -> Response:
    from opportunity_intel.domain.models import Opportunity
    from fastapi import Response

    packet = (
        db.query(ApplicationPacket)
        .options(
            selectinload(ApplicationPacket.requirements),
            selectinload(ApplicationPacket.papers),
            selectinload(ApplicationPacket.drafts),
        )
        .filter_by(id=packet_id)
        .one_or_none()
    )
    if packet is None:
        raise HTTPException(status_code=404, detail="Packet not found")

    opp = db.query(Opportunity).filter_by(id=packet.opportunity_id).one_or_none()
    opp_title = (opp.title if opp else f"Opportunity_{packet.opportunity_id}").replace(" ", "_")[:40]

    if kind == "dossier" or kind == "all":
        parts = [f"# Application Dossier: {opp.title if opp else 'PhD Application'}\n\n"]
        if opp:
            parts.append(
                f"**Institution:** {opp.organization} ({opp.country_code})\n"
                f"**Funding:** {opp.funding} | **Supervisor:** {opp.supervisor or 'N/A'}\n"
                f"**Source:** {opp.source_url}\n\n---\n\n"
            )
        for draft in packet.drafts:
            title = draft.kind.replace("_", " ").title()
            parts.append(f"## {title}\n\n{draft.body}\n\n---\n\n")
        content = "".join(parts)
        filename = f"Application_Dossier_{opp_title}.md"
    else:
        draft = next((d for d in packet.drafts if d.kind == kind), None)
        if draft is None:
            raise HTTPException(status_code=404, detail=f"Draft document of kind '{kind}' not found")
        content = draft.body
        filename = f"{kind.replace('_', '-')}_{opp_title}.md"

    return Response(
        content=content,
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def _load_application(db: Session, application_id: int) -> Application:
    row = (
        db.query(Application)
        .options(selectinload(Application.events))
        .filter_by(id=application_id)
        .one_or_none()
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Application not found")
    return row


@router.get("/api/packets/{packet_id}/apply/preview", response_model=ApplyPreviewOut)
def apply_preview(
    packet_id: int, request: Request, db: Session = Depends(get_db)
) -> ApplyPreviewOut:
    try:
        preview = preview_application(
            db,
            packet_id,
            request.app.state.settings,
            request.app.state.model_config,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return ApplyPreviewOut.model_validate(preview)


@router.post("/api/packets/{packet_id}/apply/request-approval", response_model=ApprovalIssuedOut)
def apply_request_approval(
    packet_id: int,
    payload: ApprovalRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> ApprovalIssuedOut:
    try:
        row, token = request_approval(
            db,
            packet_id,
            request.app.state.settings,
            adapter=payload.adapter,
            inbox=request.app.state.sandbox_inbox,
            model_config=request.app.state.model_config,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    loaded = _load_application(db, row.id)
    return ApprovalIssuedOut(
        **ApplicationOut.model_validate(loaded, from_attributes=True).model_dump(),
        token=token,
        token_expires_at=loaded.token_expires_at,
        message="Review the filled fields, then Approve. Token is single-use and expires.",
    )


@router.get("/api/applications", response_model=list[ApplicationOut])
def list_applications(db: Session = Depends(get_db)) -> list[Application]:
    return (
        db.query(Application)
        .options(selectinload(Application.events))
        .order_by(Application.id.desc())
        .limit(50)
        .all()
    )


@router.get("/api/applications/{application_id}", response_model=ApplicationOut)
def get_application(application_id: int, db: Session = Depends(get_db)) -> Application:
    return _load_application(db, application_id)


@router.post("/api/applications/{application_id}/approve", response_model=ApplicationOut)
def approve_application(
    application_id: int,
    payload: ApproveRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> Application:
    try:
        approve_and_submit(
            db,
            application_id,
            payload.token,
            request.app.state.settings,
            inbox=request.app.state.sandbox_inbox,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return _load_application(db, application_id)


@router.post("/api/applications/{application_id}/reject", response_model=ApplicationOut)
def reject_application_route(
    application_id: int,
    payload: RejectRequest,
    db: Session = Depends(get_db),
) -> Application:
    try:
        reject_application(db, application_id, payload.reason)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _load_application(db, application_id)


@router.post("/api/discovery/runs", response_model=DiscoveryRunOut)
def start_discovery(
    payload: DiscoveryRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> DiscoveryRunOut:
    run = run_discovery(
        db,
        payload.query,
        request.app.state.model_config,
        request.app.state.settings,
    )
    return DiscoveryRunOut.model_validate(run, from_attributes=True)


@router.get("/api/monitor/health", response_model=MonitorHealthOut)
def monitor_health(db: Session = Depends(get_db)) -> MonitorHealthOut:
    failures = (
        db.query(AgentRun)
        .filter(AgentRun.status == "error")
        .order_by(AgentRun.created_at.desc())
        .limit(10)
        .all()
    )
    return MonitorHealthOut(
        ok=len(failures) == 0,
        failed_runs=db.query(AgentRun).filter(AgentRun.status == "error").count(),
        log_file=str(jsonl_path()),
        last_failures=[AgentRunOut.model_validate(row, from_attributes=True) for row in failures],
    )


@router.get("/api/monitor/runs", response_model=list[AgentRunOut])
def list_agent_runs(db: Session = Depends(get_db)) -> list[AgentRun]:
    return (
        db.query(AgentRun)
        .options(joinedload(AgentRun.spans))
        .order_by(AgentRun.created_at.desc())
        .limit(50)
        .all()
    )


def _require_ops_secret(request: Request) -> None:
    expected = (request.app.state.settings.ops_webhook_secret or "").strip()
    if not expected:
        return
    got = request.headers.get("x-ops-secret", "")
    if got != expected:
        raise HTTPException(status_code=401, detail="Invalid ops webhook secret")


@router.post("/api/ops/nightly", response_model=NightlyDigestOut)
def ops_run_nightly(
    payload: NightlyRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> NightlyDigest:
    _require_ops_secret(request)
    digest = run_nightly_cycle(
        db,
        request.app.state.settings,
        request.app.state.model_config,
        query=payload.query,
        run_search=payload.run_search,
    )
    return digest


@router.get("/api/ops/digest", response_model=NightlyDigestOut | None)
def ops_last_digest(db: Session = Depends(get_db)) -> NightlyDigest | None:
    return db.query(NightlyDigest).order_by(NightlyDigest.id.desc()).first()


@router.get("/api/ops/tracker")
def ops_tracker(request: Request, db: Session = Depends(get_db)) -> dict:
    return build_tracker(db, request.app.state.settings)


@router.get("/api/notifications", response_model=list[NotificationOut])
def list_notifications_route(db: Session = Depends(get_db)) -> list[Notification]:
    return db.query(Notification).order_by(Notification.id.desc()).limit(50).all()


@router.get("/api/ops/tools", response_model=OpsToolsListOut)
def ops_list_tools() -> OpsToolsListOut:
    return OpsToolsListOut(tools=list_tools())


@router.post("/api/ops/tools", response_model=OpsToolOut)
def ops_invoke_tool(
    payload: OpsToolRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> OpsToolOut:
    try:
        result = invoke_tool(
            payload.name,
            payload.arguments,
            session=db,
            settings=request.app.state.settings,
        )
    except ToolError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return OpsToolOut(name=payload.name, result=result)


@router.post("/api/ops/pipeline", response_model=PipelineOut)
def ops_pipeline(
    payload: PipelineRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> PipelineOut:
    from opportunity_intel.orchestrator.graph import start_or_resume
    from opportunity_intel.orchestrator.nodes import PipelineContext

    ctx = PipelineContext(
        db,
        request.app.state.settings,
        request.app.state.model_config,
        inbox=request.app.state.sandbox_inbox,
    )
    state = start_or_resume(
        db,
        ctx,
        research_query=payload.research_query,
        thread_id=payload.thread_id,
        human_approved=payload.human_approved,
        reject=payload.reject,
        approval_token=payload.approval_token,
    )
    return PipelineOut(
        thread_id=str(state.get("thread_id") or ""),
        node=str(state.get("node") or ""),
        application_status=str(state.get("application_status") or ""),
        error=str(state.get("error") or ""),
        human_approved=bool(state.get("human_approved")),
        discovered_labs=list(state.get("discovered_labs") or []),
        matched_pis=list(state.get("matched_pis") or []),
        drafted_documents=dict(state.get("drafted_documents") or {}),
        opportunity_id=state.get("opportunity_id"),
        packet_id=state.get("packet_id"),
        application_id=state.get("application_id"),
        approval_token=str(state.get("approval_token") or ""),
        adapter=str(state.get("adapter") or ""),
    )


@router.post("/api/ops/google-workflow")
def ops_google_workflow(
    payload: PipelineRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> dict:
    """Executes the Google GenAI Search + LangGraph doctoral discovery & application workflow."""
    from opportunity_intel.orchestrator.google_workflow import run_google_phd_workflow

    result = run_google_phd_workflow(
        db,
        request.app.state.settings,
        request.app.state.model_config,
        research_query=payload.research_query or "",
        human_approved=payload.human_approved,
        selected_opportunity_id=payload.selected_opportunity_id
        if hasattr(payload, "selected_opportunity_id")
        else None,
        approval_token=payload.approval_token or "",
    )
    return {
        "node": result.get("node"),
        "application_status": result.get("application_status"),
        "human_approved": result.get("human_approved"),
        "opportunity_id": result.get("opportunity_id"),
        "application_id": result.get("application_id"),
        "approval_token": result.get("approval_token"),
        "discovered_vacancies": result.get("discovered_vacancies", []),
        "ranked_matches": result.get("ranked_matches", []),
        "drafted_documents": result.get("drafted_documents", {}),
        "critic_issues": result.get("critic_issues", []),
        "submission_receipt": result.get("submission_receipt", {}),
        "error": result.get("error", ""),
    }


@router.post("/api/rag/search")
def rag_hybrid_search(
    request: Request,
    query: str,
    collection: str = "evidence_items",
    limit: int = 5,
    use_reranker: bool = True,
    db: Session = Depends(get_db),
) -> dict:
    """Performs BM25 + ChromaDB dense hybrid search with RRF and LLM reranking."""
    from opportunity_intel.llm.router import LLMRouter
    from opportunity_intel.rag.hybrid_search import HybridSearchEngine
    from opportunity_intel.rag.reranker import LLMReranker

    settings = request.app.state.settings
    cfg = request.app.state.model_config
    router_inst = LLMRouter(settings, cfg)

    hybrid = HybridSearchEngine(settings, router=router_inst)
    candidates = hybrid.hybrid_search(collection, query, limit=limit)

    if use_reranker and candidates:
        reranker = LLMReranker(settings, router_inst)
        reranked = reranker.rerank(query, candidates, top_n=limit)
        return {
            "query": query,
            "collection": collection,
            "results": [
                {
                    "id": r.id,
                    "text": r.text,
                    "rerank_score": r.rerank_score,
                    "rationale": r.relevance_rationale,
                    "metadata": r.metadata,
                }
                for r in reranked
            ],
        }

    return {
        "query": query,
        "collection": collection,
        "results": [
            {
                "id": r.id,
                "text": r.text,
                "rrf_score": r.rrf_score,
                "bm25_score": r.bm25_score,
                "dense_score": r.dense_score,
                "metadata": r.metadata,
            }
            for r in candidates
        ],
    }


@router.post("/api/rag/generate")
def rag_generate_and_refine(
    request: Request,
    query: str,
    opportunity_id: int | None = None,
    max_iterations: int = 2,
    db: Session = Depends(get_db),
) -> dict:
    """Generates evidence-grounded application text and self-corrects using LLM-as-a-Judge."""
    from opportunity_intel.llm.router import LLMRouter
    from opportunity_intel.rag.self_improving_rag import SelfImprovingRAGEngine

    settings = request.app.state.settings
    cfg = request.app.state.model_config
    router_inst = LLMRouter(settings, cfg)

    engine = SelfImprovingRAGEngine(settings, router_inst)
    res = engine.generate_and_refine(
        query,
        opportunity_id=opportunity_id,
        max_iterations=max_iterations,
    )
    return {
        "query": res.query,
        "final_text": res.final_text,
        "iterations_run": res.iterations_run,
        "grounding_evidence_ids": res.grounding_evidence_ids,
        "evaluation": {
            "passed": res.evaluation.passed,
            "hallucination_score": res.evaluation.hallucination_score,
            "relevance_score": res.evaluation.relevance_score,
            "coverage_score": res.evaluation.coverage_score,
            "critique": res.evaluation.critique,
            "suggested_edits": res.evaluation.suggested_edits,
        },
    }
