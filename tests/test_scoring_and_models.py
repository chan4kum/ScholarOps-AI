"""Tests for scoring rules, model config, and embed_fit wiring."""

from __future__ import annotations

from pathlib import Path

from opportunity_intel.llm.models_config import load_model_config
from opportunity_intel.scoring.rules import (
    ProfileSignals,
    is_allowed_country,
    normalize_country,
    rule_fit_score,
)


def test_uk_can_be_excluded_when_listed() -> None:
    assert normalize_country("United Kingdom") == "GB"
    assert normalize_country("UK") == "GB"
    assert not is_allowed_country("GB", ("NL", "DE", "CH"), ("GB", "UK"))
    assert is_allowed_country("GB", (), ())


def test_netherlands_not_confused_with_delft_de_bigram() -> None:
    assert normalize_country("TU Delft, Netherlands") == "NL"
    assert normalize_country("Germany / TU Berlin") == "DE"
    assert normalize_country("PhD Autonomous Agents") == ""
    assert normalize_country("Oslo, NO") == "NO"


def test_target_countries_from_config() -> None:
    from opportunity_intel.config import ROOT

    cfg = load_model_config(ROOT / "config" / "models.yaml")
    assert cfg.target_countries == ()
    assert cfg.excluded_countries == ()


def test_new_country_aliases() -> None:
    assert normalize_country("Italy") == "IT"
    assert normalize_country("United Arab Emirates") == "AE"
    assert normalize_country("Japan") == "JP"
    assert normalize_country("South Korea") == "KR"
    assert normalize_country("Australia") == "AU"
    assert normalize_country("Canada") == "CA"
    assert normalize_country("Thailand") == "TH"


def test_deepseek_roles_use_v4_flash() -> None:
    from opportunity_intel.config import ROOT

    cfg = load_model_config(ROOT / "config" / "models.yaml")
    assert cfg.roles["reason"].model == "deepseek-v4-flash"
    assert cfg.roles["reason"].thinking == "disabled"
    assert cfg.roles["draft"].model == "deepseek-v4-flash"
    assert cfg.roles["draft"].thinking == "enabled"
    assert cfg.roles["extract"].provider == "groq"
    assert cfg.roles["extract"].model == "openai/gpt-oss-20b"


def test_rule_fit_prefers_overlap_and_funding() -> None:
    profile = ProfileSignals(
        interests=["agentic ai", "governance"],
        skills=["genai"],
        require_funded=True,
    )
    high = rule_fit_score(
        title="PhD in Agentic AI governance",
        summary="Fully funded GenAI agents in regulated industries",
        funding="fully funded stipend",
        country_code="NL",
        profile=profile,
        allowed_countries=("NL", "DE"),
        excluded_countries=("GB",),
    )
    low = rule_fit_score(
        title="PhD in marine biology",
        summary="Field work",
        funding="self-funded",
        country_code="NL",
        profile=profile,
        allowed_countries=("NL", "DE"),
        excluded_countries=("GB",),
    )
    zero = rule_fit_score(
        title="PhD in Agentic AI governance",
        summary="Fully funded",
        funding="fully funded",
        country_code="GB",
        profile=profile,
        allowed_countries=("NL", "DE"),
        excluded_countries=("GB",),
    )
    assert high > low
    assert zero == 0.0


# ---------------------------------------------------------------------------
# New tests: embed_fit wired into Opportunity model and discovery service
# ---------------------------------------------------------------------------


def test_opportunity_model_has_embed_fit_column() -> None:
    """embed_fit column exists on the Opportunity ORM model."""
    from opportunity_intel.domain.models import Opportunity

    col_names = {col.key for col in Opportunity.__table__.columns}
    assert "embed_fit" in col_names


def test_embed_fit_column_is_nullable_float() -> None:
    """embed_fit column is nullable Float (not Integer, not required)."""
    from sqlalchemy import Float

    from opportunity_intel.domain.models import Opportunity

    col = Opportunity.__table__.columns["embed_fit"]
    assert isinstance(col.type, Float)
    assert col.nullable is True


def test_embed_fit_in_opportunity_out_schema() -> None:
    """OpportunityOut schema exposes embed_fit as optional float."""
    from opportunity_intel.api.schemas import OpportunityOut

    fields = OpportunityOut.model_fields
    assert "embed_fit" in fields
    # Default is None when not provided

    field = fields["embed_fit"]
    # Field should accept None
    assert field.default is None


def test_embed_fit_computed_in_discovery_run(tmp_path: Path) -> None:
    """run_discovery computes embed_fit for new opportunities when profile exists."""
    from unittest.mock import patch

    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from opportunity_intel.config import ROOT, Settings
    from opportunity_intel.db import init_db, reset_engine
    from opportunity_intel.discovery.service import run_discovery
    from opportunity_intel.domain.models import Opportunity, UserProfile
    from opportunity_intel.llm.models_config import load_model_config

    reset_engine()
    db_path = tmp_path / "test.db"
    settings = Settings(
        database_url=f"sqlite+pysqlite:///{db_path}",
        uploads_dir=tmp_path / "uploads",
        documents_import_dir=tmp_path / "phd",
        groq_api_key="",
        deepseek_api_key="",
        hf_token="",
        offline=False,
        enable_llm_enrich=False,
    )
    init_db(settings)
    model_config = load_model_config(ROOT / "config" / "models.yaml")

    engine = create_engine(f"sqlite+pysqlite:///{db_path}")
    Session = sessionmaker(bind=engine)

    # Insert a profile so embed_fit can be computed
    with Session() as session:
        profile = UserProfile(
            full_name="Chandan Kumar",
            research_interests="agentic AI governance responsible AI",
            skills="LangGraph Python",
            funding_requirement="fully_funded",
        )
        session.add(profile)
        session.commit()

    # Mock discover() to return one controlled listing (no real HTTP calls)
    from opportunity_intel.discovery.sources import RawListing

    fake_listing = RawListing(
        title="PhD in Agentic AI Governance",
        source_url="https://www.tudelft.nl/phd-agentic-ai",
        organization="TU Delft",
        location="Netherlands",
        summary="Fully funded PhD on agentic AI governance frameworks.",
        source="euraxess",
        funding="fully funded stipend",
    )

    with patch(
        "opportunity_intel.discovery.service.discover",
        return_value=[fake_listing],
    ):
        with Session() as session:
            run = run_discovery(session, "agentic AI PhD", model_config, settings)

    assert run.status == "completed"
    assert run.kept_count == 1

    # Verify embed_fit was stored
    with Session() as session:
        opp = (
            session.query(Opportunity)
            .filter_by(source_url="https://www.tudelft.nl/phd-agentic-ai")
            .one_or_none()
        )
        assert opp is not None
        # embed_fit should be computed (non-None) since profile text is present
        assert opp.embed_fit is not None
        # Score should be in [0, 100]
        assert 0.0 <= opp.embed_fit <= 100.0

    reset_engine()


def test_api_sort_order_includes_embed_fit() -> None:
    """list_opportunities query uses embed_fit in ORDER BY."""
    import inspect

    from opportunity_intel.api import routes

    source = inspect.getsource(routes.list_opportunities)
    assert "embed_fit" in source


def test_db_migration_adds_embed_fit_column(tmp_path: Path) -> None:
    """_migrate_sqlite adds embed_fit column to existing databases."""
    from sqlalchemy import create_engine, text
    from sqlalchemy import inspect as sa_inspect

    from opportunity_intel.db import _migrate_sqlite, reset_engine

    reset_engine()
    db_path = tmp_path / "migrate_test.db"
    engine = create_engine(f"sqlite+pysqlite:///{db_path}")

    # Create the opportunities table WITHOUT embed_fit (simulates old DB)
    with engine.begin() as conn:
        conn.execute(
            text("""
            CREATE TABLE opportunities (
                id INTEGER PRIMARY KEY,
                title TEXT,
                source_url TEXT UNIQUE,
                rule_fit FLOAT DEFAULT 0.0,
                llm_fit FLOAT,
                shortlisted INTEGER DEFAULT 0,
                apply_channel VARCHAR(40) DEFAULT '',
                apply_url VARCHAR(1000) DEFAULT '',
                apply_email VARCHAR(300) DEFAULT '',
                apply_notes TEXT DEFAULT '',
                kind VARCHAR(20) DEFAULT 'phd',
                source VARCHAR(50) DEFAULT '',
                organization VARCHAR(300) DEFAULT '',
                country_code VARCHAR(8) DEFAULT '',
                location VARCHAR(300) DEFAULT '',
                funding VARCHAR(200) DEFAULT '',
                deadline DATE,
                summary TEXT DEFAULT '',
                supervisor VARCHAR(300) DEFAULT '',
                fit_rationale TEXT DEFAULT '',
                status VARCHAR(40) DEFAULT 'discovered',
                created_at DATETIME
            )
        """)
        )
        # Also create user_profiles so migration doesn't bail early
        conn.execute(
            text("""
            CREATE TABLE user_profiles (
                id INTEGER PRIMARY KEY,
                full_name VARCHAR(200) DEFAULT '',
                profile_summary TEXT DEFAULT '',
                profile_source VARCHAR(40) DEFAULT 'manual'
            )
        """)
        )

    _migrate_sqlite(engine)

    insp = sa_inspect(engine)
    col_names = {c["name"] for c in insp.get_columns("opportunities")}
    assert "embed_fit" in col_names

    reset_engine()
