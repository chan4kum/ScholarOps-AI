from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import NullPool

from opportunity_intel.config import Settings
from opportunity_intel.domain.models import Base

_engine: Engine | None = None
_SessionLocal: sessionmaker[Session] | None = None

# Wait this long for another writer (Prepare used to hold the lock during LLM calls).
_SQLITE_BUSY_MS = 30_000


def get_engine(settings: Settings) -> Engine:
    global _engine
    if _engine is None:
        connect_args: dict[str, object] = {}
        engine_kwargs: dict[str, object] = {}
        if settings.database_url.startswith("sqlite"):
            Path("data").mkdir(exist_ok=True)
            connect_args = {
                "check_same_thread": False,
                "timeout": _SQLITE_BUSY_MS / 1000,
            }
            engine_kwargs["poolclass"] = NullPool
        _engine = create_engine(
            settings.database_url,
            connect_args=connect_args,
            **engine_kwargs,
        )
        if settings.database_url.startswith("sqlite"):

            @event.listens_for(_engine, "connect")
            def _sqlite_pragmas(dbapi_conn, _connection_record) -> None:  # noqa: ANN001
                cursor = dbapi_conn.cursor()
                cursor.execute("PRAGMA journal_mode=WAL")
                cursor.execute(f"PRAGMA busy_timeout={_SQLITE_BUSY_MS}")
                cursor.execute("PRAGMA foreign_keys=ON")
                cursor.close()

    return _engine


def init_db(settings: Settings) -> None:
    Path("data").mkdir(exist_ok=True)
    settings.uploads_dir.mkdir(parents=True, exist_ok=True)
    engine = get_engine(settings)
    Base.metadata.create_all(engine)
    _migrate_sqlite(engine)
    global _SessionLocal
    _SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def _migrate_sqlite(engine: Engine) -> None:
    if not str(engine.url).startswith("sqlite"):
        return
    from sqlalchemy import inspect, text

    insp = inspect(engine)
    if "user_profiles" not in insp.get_table_names():
        return
    cols = {c["name"] for c in insp.get_columns("user_profiles")}
    with engine.begin() as conn:
        if "profile_summary" not in cols:
            conn.execute(
                text("ALTER TABLE user_profiles ADD COLUMN profile_summary TEXT DEFAULT ''")
            )
        if "profile_source" not in cols:
            conn.execute(
                text(
                    "ALTER TABLE user_profiles ADD COLUMN profile_source "
                    "VARCHAR(40) DEFAULT 'manual'"
                )
            )

    if "uploaded_documents" in insp.get_table_names():
        doc_cols = {c["name"] for c in insp.get_columns("uploaded_documents")}
        with engine.begin() as conn:
            if "source_path" not in doc_cols:
                conn.execute(
                    text(
                        "ALTER TABLE uploaded_documents ADD COLUMN source_path "
                        "VARCHAR(1000) DEFAULT ''"
                    )
                )
            if "content_hash" not in doc_cols:
                conn.execute(
                    text(
                        "ALTER TABLE uploaded_documents ADD COLUMN content_hash "
                        "VARCHAR(64) DEFAULT ''"
                    )
                )

    if "opportunities" in insp.get_table_names():
        opp_cols = {c["name"] for c in insp.get_columns("opportunities")}
        with engine.begin() as conn:
            if "shortlisted" not in opp_cols:
                conn.execute(
                    text("ALTER TABLE opportunities ADD COLUMN shortlisted INTEGER DEFAULT 0")
                )
            if "apply_channel" not in opp_cols:
                conn.execute(
                    text(
                        "ALTER TABLE opportunities ADD COLUMN apply_channel VARCHAR(40) DEFAULT ''"
                    )
                )
            if "apply_url" not in opp_cols:
                conn.execute(
                    text("ALTER TABLE opportunities ADD COLUMN apply_url VARCHAR(1000) DEFAULT ''")
                )
            if "apply_email" not in opp_cols:
                conn.execute(
                    text("ALTER TABLE opportunities ADD COLUMN apply_email VARCHAR(300) DEFAULT ''")
                )
            if "apply_notes" not in opp_cols:
                conn.execute(
                    text("ALTER TABLE opportunities ADD COLUMN apply_notes TEXT DEFAULT ''")
                )
            if "embed_fit" not in opp_cols:
                conn.execute(
                    text("ALTER TABLE opportunities ADD COLUMN embed_fit FLOAT DEFAULT NULL")
                )


def session_factory() -> sessionmaker[Session]:
    if _SessionLocal is None:
        raise RuntimeError("Database not initialised")
    return _SessionLocal


def reset_engine() -> None:
    """Dispose the process-wide engine so tests can use a temp database."""
    global _engine, _SessionLocal
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _SessionLocal = None
