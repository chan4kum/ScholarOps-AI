from __future__ import annotations

from sqlalchemy.orm import Session

from opportunity_intel.config import Settings
from opportunity_intel.discovery.enrich import enrich_opportunity
from opportunity_intel.discovery.pipeline import discover
from opportunity_intel.discovery.quality import infer_country, is_keepable
from opportunity_intel.discovery.sources import RawListing
from opportunity_intel.domain.models import DiscoveryRun, Opportunity, UserProfile
from opportunity_intel.llm.budget import BudgetExceeded
from opportunity_intel.llm.models_config import AppModelConfig
from opportunity_intel.observability.trace import agent_run
from opportunity_intel.rag.faiss_store import alignment_score
from opportunity_intel.scoring.rules import (
    ProfileSignals,
    is_allowed_country,
    parse_csv,
    rule_fit_score,
)


def _profile_signals(profile: UserProfile | None) -> ProfileSignals:
    if profile is None:
        return ProfileSignals(interests=[], skills=[], require_funded=True)
    return ProfileSignals(
        interests=parse_csv(profile.research_interests),
        skills=parse_csv(profile.skills),
        require_funded="fund" in (profile.funding_requirement or "").lower(),
    )


def _profile_embed_text(profile: UserProfile | None) -> str:
    """Build a single text blob representing the profile for embedding comparison."""
    if profile is None:
        return ""
    parts = [
        profile.research_interests or "",
        profile.skills or "",
        profile.profile_summary or "",
    ]
    return " ".join(p for p in parts if p.strip())


def upsert_listing(
    session: Session,
    listing: RawListing,
    *,
    profile: UserProfile | None,
    model_config: AppModelConfig,
    settings: Settings | None = None,
) -> Opportunity | None:
    if not is_keepable(
        listing,
        allowed=model_config.target_countries,
        excluded=model_config.excluded_countries,
    ):
        return None
    country = infer_country(listing)
    if not is_allowed_country(
        country, model_config.target_countries, model_config.excluded_countries
    ):
        return None

    signals = _profile_signals(profile)
    score = rule_fit_score(
        title=listing.title,
        summary=listing.summary,
        funding=listing.funding,
        country_code=country,
        profile=signals,
        allowed_countries=model_config.target_countries,
        excluded_countries=model_config.excluded_countries,
    )
    existing = session.query(Opportunity).filter_by(source_url=listing.source_url).one_or_none()
    if existing is None:
        existing = Opportunity(source_url=listing.source_url)
        session.add(existing)
    existing.kind = "phd"
    existing.source = listing.source
    existing.title = listing.title
    existing.organization = listing.organization
    existing.country_code = country
    existing.location = listing.location
    existing.funding = listing.funding
    existing.deadline = listing.deadline
    existing.summary = listing.summary
    existing.supervisor = listing.supervisor
    existing.rule_fit = score
    existing.status = "discovered"
    if settings is not None and score > 0 and settings.enable_llm_enrich:
        try:
            enrich_opportunity(existing, profile, settings, model_config)
        except BudgetExceeded:
            raise
        except Exception:  # noqa: BLE001
            pass
    return existing


def run_discovery(
    session: Session,
    query: str,
    model_config: AppModelConfig,
    settings: Settings,
) -> DiscoveryRun:
    run = DiscoveryRun(query=query, status="running")
    session.add(run)
    session.flush()
    profile = session.query(UserProfile).order_by(UserProfile.id).first()
    profile_text = _profile_embed_text(profile)

    # Build a router for embed_fit if HF token or fallback is available.
    # Import here to avoid circular imports at module load time.
    from opportunity_intel.llm.router import LLMRouter

    router = LLMRouter(settings, model_config) if profile_text else None

    try:
        with agent_run("discovery", "search", query):
            listings = discover(query, settings, model_config)
            run.found_count = len(listings)
            kept = 0
            new_rows: list[Opportunity] = []
            for listing in listings:
                try:
                    row = upsert_listing(
                        session,
                        listing,
                        profile=profile,
                        model_config=model_config,
                        settings=settings,
                    )
                except BudgetExceeded as exc:
                    run.error = str(exc)
                    break
                if row is not None:
                    kept += 1
                    # Track newly inserted rows (embed_fit not yet computed).
                    if row.embed_fit is None:
                        new_rows.append(row)

            # Compute embed_fit for all new rows in one pass.
            # Uses real vectors when HF_TOKEN is set, hash-trick otherwise.
            if profile_text and new_rows and router is not None:
                for row in new_rows:
                    opp_text = f"{row.title} {row.summary}".strip()
                    if opp_text:
                        try:
                            row.embed_fit = alignment_score(
                                settings, profile_text, opp_text, router=router
                            )
                        except Exception:  # noqa: BLE001
                            pass  # Non-critical — leave embed_fit as None

            run.kept_count = kept
            run.status = "completed"
    except Exception as exc:  # noqa: BLE001 — persist failure for the dashboard
        run.status = "failed"
        run.error = str(exc)
    session.commit()
    session.refresh(run)
    return run
