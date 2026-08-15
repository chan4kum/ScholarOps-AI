"""Application settings. Secrets come from the environment, never from code."""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT / ".env", extra="ignore")

    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com"
    groq_api_key: str = ""
    groq_base_url: str = "https://api.groq.com/openai/v1"
    openai_api_key: str = ""
    openai_base_url: str = "https://api.openai.com/v1"
    openai_model: str = "gpt-5-nano-2025-08-07"
    hf_token: str = ""
    ollama_base_url: str = "http://127.0.0.1:11434/v1"
    ollama_api_key: str = "ollama"
    database_url: str = "sqlite+pysqlite:///./data/opportunity.db"
    redis_url: str = "redis://127.0.0.1:6379/0"
    llm_daily_budget_usd: float = 2.0
    groq_polish_enabled: bool = False
    offline: bool = False
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    models_config_path: Path = ROOT / "config" / "models.yaml"
    uploads_dir: Path = ROOT / "data" / "uploads"
    documents_import_dir: Path = Path.home() / "Documents" / "PHD"
    brave_api_key: str = ""
    tavily_api_key: str = ""
    discovery_min_results: int = 8
    discovery_fetch_limit: int = 12
    use_playwright: bool = False
    discovery_config_path: Path = ROOT / "config" / "discovery.yaml"
    enable_llm_enrich: bool = True
    apply_signing_secret: str = ""
    apply_token_ttl_seconds: int = 300  # spec: 5-minute HITL window (was 900)
    apply_live_submit: bool = False
    apply_as_me: bool = False
    apply_pathfind: bool = True
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_from: str = ""
    ops_discovery_query: str = "funded PhD Responsible AI Agentic AI governance"
    ops_high_fit_threshold: float = 80.0
    ops_deadline_days: int = 7
    ops_webhook_secret: str = ""
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""
    github_token: str = ""
    # GEMINI_API_KEY in .env (pydantic-settings env name). Never commit the value.
    gemini_api_key: str = ""
    gemini_model: str = "gemini-3.7-flash"
    gemini_base_url: str = "https://generativelanguage.googleapis.com/v1beta/openai/"
    faiss_dir: Path = ROOT / "data" / "faiss"
    chroma_dir: Path = ROOT / "data" / "chroma"
    kg_path: Path = ROOT / "data" / "knowledge_graph" / "academic_kg.json"

    @property
    def cors_origin_list(self) -> list[str]:
        return [item.strip() for item in self.cors_origins.split(",") if item.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
