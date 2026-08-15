"""Daily LLM spend budget enforcement."""

from __future__ import annotations

from pathlib import Path

import pytest

from opportunity_intel.config import Settings
from opportunity_intel.llm.budget import ROLE_COST_USD, BudgetExceeded, charge, spent_today


def test_charge_accumulates_and_blocks(tmp_path: Path) -> None:
    log = tmp_path / "llm-spend.json"
    # Budget sits between extract-only ($0.002) and extract+reason ($0.009).
    settings = Settings(llm_daily_budget_usd=0.008)
    charge("extract", settings, path=log)
    assert spent_today(log) == pytest.approx(ROLE_COST_USD["extract"])
    with pytest.raises(BudgetExceeded):
        charge("reason", settings, path=log)


def test_fallback_is_free(tmp_path: Path) -> None:
    log = tmp_path / "llm-spend.json"
    settings = Settings(llm_daily_budget_usd=0.01)
    charge("fallback", settings, path=log)
    assert spent_today(log) == 0.0


def test_groq_and_ollama_never_consume_budget(tmp_path: Path) -> None:
    log = tmp_path / "llm-spend.json"
    settings = Settings(llm_daily_budget_usd=0.01)
    charge("extract", settings, path=log, provider="groq")
    charge("extract", settings, path=log, provider="ollama")
    charge("reason", settings, path=log, provider="groq")
    assert spent_today(log) == 0.0


def test_zero_budget_disables_paid_cap(tmp_path: Path) -> None:
    log = tmp_path / "llm-spend.json"
    settings = Settings(llm_daily_budget_usd=0)
    charge("draft", settings, path=log, provider="deepseek")
    assert spent_today(log) == 0.0
