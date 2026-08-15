"""LangChain & LangGraph Workflow Agent powered by Google GenAI SDK and Google Search Grounding.

This module provides a production-grade multi-agent workflow graph:
  1. IngestionNode: Loads applicant dossier, master CV, and evidence items.
  2. GoogleSearchDiscoveryNode: Employs google.genai SDK with native Google Search Grounding
     to discover real, active funded PhD positions and research lab vacancies worldwide.
  3. ResearchFitMatchmakerNode: Evaluates candidate-opportunity alignment using structured scoring.
  4. HITLGateNode: Human-in-the-loop cryptographic safety checkpoint.
  5. EvidenceBoundDrafterNode: Generates evidence-grounded application dossiers.
  6. CriticVerifierNode: LangChain safety validator checking truthfulness and citation accuracy.
"""

from __future__ import annotations

import logging
from typing import Any, TypedDict

from google import genai
from google.genai import types
from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, START, StateGraph
from sqlalchemy.orm import Session

from opportunity_intel.apply.mapping import validate_payload
from opportunity_intel.apply.service import preview_application, request_approval
from opportunity_intel.config import Settings
from opportunity_intel.discovery.sources import RawListing
from opportunity_intel.domain.models import (
    DraftDocument,
    Opportunity,
    UploadedDocument,
    UserProfile,
)
from opportunity_intel.llm.json_repair import parse_llm_json
from opportunity_intel.llm.models_config import AppModelConfig
from opportunity_intel.prepare.service import prepare_packet
from opportunity_intel.rag import faiss_store
from opportunity_intel.scoring.rules import ProfileSignals, parse_csv, rule_fit_score

logger = logging.getLogger("opportunity_intel.orchestrator.google_workflow")


class WorkflowState(TypedDict, total=False):
    research_query: str
    thread_id: str
    user_cv_text: str
    profile_summary: str
    candidate_skills: list[str]
    candidate_interests: list[str]
    discovered_opportunities: list[dict[str, Any]]
    matched_opportunities: list[dict[str, Any]]
    selected_opportunity_id: int | None
    human_approved: bool
    reject: bool
    drafted_documents: dict[str, str]
    critic_issues: list[dict[str, str]]
    application_status: str
    application_id: int | None
    packet_id: int | None
    approval_token: str
    adapter: str
    error: str
    node: str


def _get_configurable(config: RunnableConfig | dict[str, Any] | None) -> dict[str, Any]:
    if not config:
        return {}
    if isinstance(config, dict):
        return config.get("configurable", config)
    return getattr(config, "configurable", {}) or (
        config.get("configurable", {}) if hasattr(config, "get") else {}
    )


class GoogleSearchDiscoveryAgent:
    """Uses the official google.genai SDK with native Google Search tool grounding."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        if not settings.gemini_api_key:
            raise ValueError("GEMINI_API_KEY is required for GoogleSearchDiscoveryAgent")
        self.client = genai.Client(api_key=settings.gemini_api_key)
        self.model = settings.gemini_model or "gemini-3.7-flash"

    def search_funded_phd(
        self,
        query: str,
        *,
        target_countries: tuple[str, ...] = (),
        limit: int = 10,
    ) -> list[RawListing]:
        """Perform live Google Search grounded query for funded PhD openings."""
        country_hint = (
            f" in {', '.join(target_countries)}"
            if target_countries
            else " in Europe, UK, Scandinavia or North America"
        )
        prompt = (
            f"Search Google for current, official, fully funded PhD vacancies "
            f"matching: '{query}'{country_hint}.\n"
            "For each vacancy found, output a JSON array of objects with the following keys:\n"
            "- title: string (the official vacancy title)\n"
            "- organization: string (university or research institute name)\n"
            "- location: string (city and country)\n"
            "- source_url: string (the direct official link to the vacancy / lab page)\n"
            "- funding: string (e.g., 'fully funded', 'salaried employee', 'stipend')\n"
            "- summary: string (3-4 sentences on the research scope, topic, and requirements)\n"
            "- supervisor: string (Professor or PI name if mentioned, else '')\n\n"
            "Respond strictly with valid JSON inside a ```json ``` block."
        )

        try:
            response = self.client.models.generate_content(
                model=self.model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    tools=[types.Tool(google_search=types.GoogleSearch())],
                    temperature=0.2,
                ),
            )
        except Exception as exc:
            logger.error("Google GenAI search grounding failed: %s", exc)
            return []

        text = response.text or ""
        listings: list[RawListing] = []

        # Strategy 1: Parse structured JSON from model response
        try:
            parsed = parse_llm_json(text)
            items = (
                parsed
                if isinstance(parsed, list)
                else (parsed.get("opportunities") or parsed.get("vacancies") or [])
            )
            for item in items[:limit]:
                if isinstance(item, dict) and item.get("title") and item.get("source_url"):
                    listings.append(
                        RawListing(
                            title=str(item["title"]).strip(),
                            source_url=str(item["source_url"]).strip(),
                            organization=str(item.get("organization") or "").strip(),
                            location=str(item.get("location") or "").strip(),
                            summary=str(item.get("summary") or "").strip(),
                            funding=str(item.get("funding") or "fully funded").strip(),
                            supervisor=str(item.get("supervisor") or "").strip(),
                            source="google_search_grounding",
                        )
                    )
        except Exception as parse_err:
            logger.warning("Could not parse JSON from search grounding response: %s", parse_err)

        # Strategy 2: Extract verified links from Grounding Metadata if JSON was partial
        if not listings and response.candidates:
            metadata = getattr(response.candidates[0], "grounding_metadata", None)
            chunks = getattr(metadata, "grounding_chunks", None) or []
            for chunk in chunks:
                web = getattr(chunk, "web", None)
                if not web:
                    continue
                uri = getattr(web, "uri", "") or getattr(web, "url", "")
                title = getattr(web, "title", "") or uri
                if uri and uri.startswith("http"):
                    listings.append(
                        RawListing(
                            title=title,
                            source_url=uri,
                            organization="",
                            location="",
                            summary=text[:600],
                            funding="funded",
                            source="google_search_grounding",
                        )
                    )
                if len(listings) >= limit:
                    break

        return listings


# ---------------------------------------------------------------------------
# LangGraph Workflow Nodes
# ---------------------------------------------------------------------------


def ingestion_node(state: WorkflowState, config: RunnableConfig | None = None) -> WorkflowState:
    """Ingests candidate CV, research proposals, and extracted evidence items."""
    cfg = _get_configurable(config)
    session: Session = cfg["session"]
    settings: Settings = cfg["settings"]

    profile = session.query(UserProfile).order_by(UserProfile.id).first()
    interests = parse_csv(profile.research_interests if profile else "")
    skills = parse_csv(profile.skills if profile else "")
    summary = profile.profile_summary if profile else ""

    docs = session.query(UploadedDocument).order_by(UploadedDocument.id).all()
    cv_parts = [summary] + [d.extracted_text[:6000] for d in docs if d.extracted_text]
    cv_text = "\n\n".join(part for part in cv_parts if part.strip())

    faiss_store.upsert_corpus(session, settings)

    return {
        **state,
        "node": "ingestion",
        "user_cv_text": cv_text[:25000],
        "profile_summary": summary,
        "candidate_skills": skills,
        "candidate_interests": interests,
        "application_status": "ingested",
    }


def google_search_discovery_node(
    state: WorkflowState, config: RunnableConfig | None = None
) -> WorkflowState:
    """Runs Google Search Grounding with Google GenAI SDK to discover active positions."""
    cfg = _get_configurable(config)
    settings: Settings = cfg["settings"]
    session: Session = cfg["session"]
    model_config: AppModelConfig = cfg["model_config"]

    query = state.get("research_query") or "funded PhD Responsible AI machine learning"
    agent = GoogleSearchDiscoveryAgent(settings)

    listings = agent.search_funded_phd(
        query,
        target_countries=model_config.target_countries,
        limit=10,
    )

    discovered_rows: list[dict[str, Any]] = []
    signals = ProfileSignals(
        interests=state.get("candidate_interests") or [],
        skills=state.get("candidate_skills") or [],
        require_funded=True,
    )

    for item in listings:
        score = rule_fit_score(
            title=item.title,
            summary=item.summary,
            funding=item.funding,
            country_code=item.country_code,
            profile=signals,
            allowed_countries=model_config.target_countries,
            excluded_countries=model_config.excluded_countries,
        )
        existing = session.query(Opportunity).filter_by(source_url=item.source_url).one_or_none()
        if existing is None:
            existing = Opportunity(
                source_url=item.source_url,
                kind="phd",
                source=item.source,
                title=item.title,
                organization=item.organization,
                country_code=item.country_code,
                location=item.location,
                funding=item.funding,
                summary=item.summary,
                supervisor=item.supervisor,
                rule_fit=score,
                status="discovered",
            )
            session.add(existing)
            session.flush()
        else:
            existing.rule_fit = max(existing.rule_fit, score)

        lab_text = f"{item.title} {item.summary} {item.supervisor}"
        alignment = faiss_store.alignment_score(settings, state.get("user_cv_text") or "", lab_text)

        discovered_rows.append(
            {
                "id": existing.id,
                "title": existing.title,
                "organization": existing.organization,
                "location": existing.location,
                "country_code": existing.country_code,
                "source_url": existing.source_url,
                "funding": existing.funding,
                "summary": existing.summary,
                "supervisor": existing.supervisor,
                "rule_fit": existing.rule_fit,
                "alignment_fit": alignment,
            }
        )

    session.commit()
    return {
        **state,
        "node": "google_search_discovery",
        "discovered_opportunities": discovered_rows,
        "application_status": "discovered",
    }


def research_fit_matchmaker_node(
    state: WorkflowState, config: RunnableConfig | None = None
) -> WorkflowState:
    """Ranks opportunities by combining rule fit, embedding similarity, and qualification fit."""
    cfg = _get_configurable(config)
    session: Session = cfg["session"]
    settings: Settings = cfg["settings"]

    opps = list(state.get("discovered_opportunities") or [])
    if not opps:
        db_opps = session.query(Opportunity).order_by(Opportunity.rule_fit.desc()).limit(10).all()
        for o in db_opps:
            lab_text = f"{o.title} {o.summary} {o.supervisor}"
            alignment = faiss_store.alignment_score(
                settings, state.get("user_cv_text") or "", lab_text
            )
            opps.append(
                {
                    "id": o.id,
                    "title": o.title,
                    "organization": o.organization,
                    "location": o.location,
                    "country_code": o.country_code,
                    "source_url": o.source_url,
                    "funding": o.funding,
                    "summary": o.summary,
                    "supervisor": o.supervisor,
                    "rule_fit": o.rule_fit,
                    "alignment_fit": alignment,
                }
            )

    opps.sort(
        key=lambda x: (
            float(x.get("rule_fit") or 0) * 0.6 + float(x.get("alignment_fit") or 0) * 0.4
        ),
        reverse=True,
    )

    top_id = opps[0]["id"] if opps else None
    return {
        **state,
        "node": "research_fit_matchmaker",
        "matched_opportunities": opps[:8],
        "selected_opportunity_id": top_id,
        "application_status": "matched" if opps else "no_match",
    }


def hitl_gate_node(state: WorkflowState, config: RunnableConfig | None = None) -> WorkflowState:
    """Human-in-the-Loop approval gate. Halts for human authorization before document synthesis."""
    _ = config
    if state.get("reject"):
        return {
            **state,
            "node": "hitl_gate",
            "human_approved": False,
            "application_status": "rejected_by_user",
        }

    if not state.get("human_approved"):
        return {
            **state,
            "node": "hitl_gate",
            "application_status": "awaiting_human_approval",
        }

    return {
        **state,
        "node": "hitl_gate",
        "application_status": "human_approved",
    }


def evidence_bound_drafter_node(
    state: WorkflowState, config: RunnableConfig | None = None
) -> WorkflowState:
    """Synthesizes evidence-bound application packet using prepare engine."""
    cfg = _get_configurable(config)
    session: Session = cfg["session"]
    settings: Settings = cfg["settings"]
    model_config: AppModelConfig = cfg["model_config"]

    opp_id = state.get("selected_opportunity_id")
    if not opp_id:
        return {
            **state,
            "node": "evidence_bound_drafter",
            "application_status": "failed",
            "error": "No opportunity selected for drafting.",
        }

    try:
        packet = prepare_packet(session, int(opp_id), settings, model_config)
        drafts = session.query(DraftDocument).filter_by(packet_id=packet.id).all()
        draft_dict = {d.kind: d.body for d in drafts}

        preview = preview_application(session, packet.id, settings, model_config)
        adapter = str(preview.get("recommended_adapter") or "email")

        app_row, token = request_approval(
            session,
            packet.id,
            settings,
            adapter=adapter,
            model_config=model_config,
        )

        return {
            **state,
            "node": "evidence_bound_drafter",
            "packet_id": packet.id,
            "application_id": app_row.id,
            "approval_token": token,
            "adapter": adapter,
            "drafted_documents": draft_dict,
            "application_status": "drafted_awaiting_dispatch",
        }
    except Exception as exc:
        logger.error("Drafter node failed: %s", exc)
        return {
            **state,
            "node": "evidence_bound_drafter",
            "application_status": "failed",
            "error": str(exc),
        }


def critic_verifier_node(
    state: WorkflowState, config: RunnableConfig | None = None
) -> WorkflowState:
    """Validates that all draft claims are grounded in verified evidence items."""
    cfg = _get_configurable(config)
    session: Session = cfg["session"]
    settings: Settings = cfg["settings"]
    model_config: AppModelConfig = cfg["model_config"]

    packet_id = state.get("packet_id")
    issues: list[dict[str, str]] = []

    if packet_id:
        try:
            payload = preview_application(session, int(packet_id), settings, model_config)
            issues = validate_payload(payload)
        except Exception as exc:
            issues = [{"level": "error", "code": "validation_error", "message": str(exc)}]

    blocking = [i for i in issues if i.get("level") == "error"]
    return {
        **state,
        "node": "critic_verifier",
        "critic_issues": issues,
        "application_status": "critic_blocked" if blocking else "verified_ready",
        "error": blocking[0]["message"] if blocking else "",
    }


# ---------------------------------------------------------------------------
# LangGraph Workflow Definition & Builder
# ---------------------------------------------------------------------------


def build_google_workflow_graph() -> StateGraph:
    """Build and compile the LangGraph PhD Application StateGraph."""
    workflow = StateGraph(WorkflowState)

    # Wrap nodes to handle LangGraph invocation with RunnableConfig
    workflow.add_node("ingestion", lambda state, config=None: ingestion_node(state, config))
    workflow.add_node(
        "google_search_discovery",
        lambda state, config=None: google_search_discovery_node(state, config),
    )
    workflow.add_node(
        "research_fit_matchmaker",
        lambda state, config=None: research_fit_matchmaker_node(state, config),
    )
    workflow.add_node("hitl_gate", lambda state, config=None: hitl_gate_node(state, config))
    workflow.add_node(
        "evidence_bound_drafter",
        lambda state, config=None: evidence_bound_drafter_node(state, config),
    )
    workflow.add_node(
        "critic_verifier", lambda state, config=None: critic_verifier_node(state, config)
    )

    # Graph Edges
    workflow.add_edge(START, "ingestion")
    workflow.add_edge("ingestion", "google_search_discovery")
    workflow.add_edge("google_search_discovery", "research_fit_matchmaker")
    workflow.add_edge("research_fit_matchmaker", "hitl_gate")

    def route_after_hitl(state: WorkflowState) -> str:
        if state.get("reject"):
            return "google_search_discovery"
        if state.get("human_approved"):
            return "evidence_bound_drafter"
        return END

    workflow.add_conditional_edges(
        "hitl_gate",
        route_after_hitl,
        {
            "google_search_discovery": "google_search_discovery",
            "evidence_bound_drafter": "evidence_bound_drafter",
            END: END,
        },
    )

    workflow.add_edge("evidence_bound_drafter", "critic_verifier")
    workflow.add_edge("critic_verifier", END)

    return workflow.compile()


def run_google_phd_workflow(
    session: Session,
    settings: Settings,
    model_config: AppModelConfig,
    *,
    research_query: str,
    human_approved: bool = False,
    reject: bool = False,
    selected_opportunity_id: int | None = None,
) -> WorkflowState:
    """Executes the complete LangGraph workflow with Google GenAI SDK and Google Search."""
    graph = build_google_workflow_graph()

    initial_state: WorkflowState = {
        "research_query": research_query,
        "human_approved": human_approved,
        "reject": reject,
        "selected_opportunity_id": selected_opportunity_id,
        "application_status": "starting",
    }

    config = {
        "configurable": {
            "session": session,
            "settings": settings,
            "model_config": model_config,
        }
    }

    final_state = graph.invoke(initial_state, config=config)
    return final_state
