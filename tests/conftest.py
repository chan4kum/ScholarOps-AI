from __future__ import annotations

from collections.abc import Generator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from opportunity_intel.api.app import create_app
from opportunity_intel.config import Settings
from opportunity_intel.db import reset_engine


def _settings(tmp_path: Path, *, keyed: bool) -> Settings:
    return Settings(
        database_url=f"sqlite+pysqlite:///{tmp_path / 'api.db'}",
        uploads_dir=tmp_path / "uploads",
        documents_import_dir=tmp_path / "phd",
        deepseek_api_key="sk-test-not-real" if keyed else "",
        groq_api_key="gsk_test_not_real" if keyed else "",
        hf_token="",
        tavily_api_key="",
        brave_api_key="",
        offline=False,
        groq_polish_enabled=False,
        enable_llm_enrich=False,
        apply_signing_secret="test-hmac-secret",
        cors_origins="http://127.0.0.1:5173",
        apply_pathfind=False,
        apply_as_me=False,
        smtp_host="",
        openai_api_key="",
        gemini_api_key="",
    )


@pytest.fixture()
def tmp_app(tmp_path: Path) -> Generator[TestClient, None, None]:
    reset_engine()
    (tmp_path / "phd").mkdir()
    (tmp_path / "uploads").mkdir()
    app = create_app(_settings(tmp_path, keyed=False))
    with TestClient(app) as client:
        yield client
    reset_engine()


@pytest.fixture()
def keyed_app(tmp_path: Path) -> Generator[TestClient, None, None]:
    reset_engine()
    (tmp_path / "phd").mkdir()
    (tmp_path / "uploads").mkdir()
    app = create_app(_settings(tmp_path, keyed=True))
    with TestClient(app) as client:
        yield client
    reset_engine()
