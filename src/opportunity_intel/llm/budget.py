"""LLM spend tracking and daily budget enforcement.

Two charging modes:
  1. ``charge_from_usage()`` — preferred; uses actual token counts from the
     API response to compute real USD cost.
  2. ``charge()`` — legacy flat-estimate fallback used when usage data is
     unavailable (e.g. recovered ``failed_generation`` payloads).

Provider pricing (per 1M tokens, input / output):
  deepseek  $0.14 / $0.28   (deepseek-v4-flash, 2025 pricing)
  openai    $0.15 / $0.60   (gpt-5-nano-2025-08-07)
  gemini    $0.075 / $0.30  (gemini-2.5-flash, free quota exists but charges beyond it)
  ollama    $0.00 / $0.00   (local)
  groq      $0.00 / $0.00   (free tier; never counts toward paid ceiling)

Flat fallback estimates per role (used only when token counts are unavailable):
  extract   $0.002   ~14K tokens at Groq — but Groq is free, so only hits paid fallback
  reason    $0.007   ~50K tokens at DeepSeek rates
  draft     $0.014   ~100K tokens at DeepSeek rates
  polish    $0.009   ~30K tokens at Groq — but Groq is free
  fallback  $0.000
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from opportunity_intel.config import ROOT, Settings

# ---------------------------------------------------------------------------
# Provider pricing table: (input_per_1M_USD, output_per_1M_USD)
# ---------------------------------------------------------------------------
PROVIDER_TOKEN_PRICE: dict[str, tuple[float, float]] = {
    "deepseek": (0.14, 0.28),
    "openai": (0.15, 0.60),
    "gemini": (0.075, 0.30),
    "ollama": (0.0, 0.0),
    "groq": (0.0, 0.0),
}

# Flat per-call fallback estimates (used only when usage data is unavailable).
# These are conservative lower bounds so the budget is never under-charged.
# Public alias ``ROLE_COST_USD`` is exported for tests and external callers.
ROLE_COST_USD: dict[str, float] = {
    "extract": 0.002,
    "reason": 0.007,
    "draft": 0.014,
    "polish": 0.009,
    "fallback": 0.0,
}
_ROLE_FLAT_COST_USD = ROLE_COST_USD  # backwards-compat internal alias

# Providers whose calls are entirely free — never counted toward the budget.
# NOTE: gemini is intentionally removed from this set because Gemini charges
# beyond its free quota. Calls from paid Gemini usage must be tracked.
FREE_PROVIDERS = frozenset({"groq", "ollama"})
FREE_ROLES = frozenset({"fallback"})


class BudgetExceeded(PermissionError):
    """Raised when LLM_DAILY_BUDGET_USD would be exceeded."""


def spend_log_path() -> Path:
    path = ROOT / "data" / "logs"
    path.mkdir(parents=True, exist_ok=True)
    return path / "llm-spend.json"


def spent_today(path: Path | None = None) -> float:
    """Return total USD spent today from the spend log."""
    log = path or spend_log_path()
    if not log.exists():
        return 0.0
    payload = json.loads(log.read_text(encoding="utf-8"))
    return float(payload.get(date.today().isoformat(), 0.0))


def _compute_token_cost(
    provider: str,
    prompt_tokens: int,
    completion_tokens: int,
) -> float:
    """Compute exact USD cost from token counts using the provider price table."""
    prices = PROVIDER_TOKEN_PRICE.get(provider.lower(), (0.03, 0.06))
    input_price, output_price = prices
    return (prompt_tokens * input_price + completion_tokens * output_price) / 1_000_000


def _append_cost(log: Path, cost: float, budget: float) -> None:
    """Append ``cost`` to today's total and raise BudgetExceeded if over limit."""
    if cost <= 0:
        return
    today = date.today().isoformat()
    payload: dict[str, float] = {}
    if log.exists():
        payload = json.loads(log.read_text(encoding="utf-8"))
    current = float(payload.get(today, 0.0))
    if current + cost > budget:
        raise BudgetExceeded(
            f"Daily LLM budget ${budget:.4f} exceeded "
            f"(already ${current:.4f}, this call ${cost:.4f})."
        )
    payload[today] = round(current + cost, 6)
    log.write_text(json.dumps(payload), encoding="utf-8")


def charge_from_usage(
    role: str,
    settings: Settings,
    *,
    provider: str,
    prompt_tokens: int,
    completion_tokens: int,
    path: Path | None = None,
) -> None:
    """Charge real USD cost derived from actual API token counts.

    This is the preferred charging method. Call it after a successful
    ``chat.completions.create()`` response using ``response.usage``.

    Free providers (Groq, Ollama) and disabled budgets are short-circuited
    immediately. ``BudgetExceeded`` is raised if the cost would push today's
    spend over ``settings.llm_daily_budget_usd``.
    """
    if role in FREE_ROLES or provider.lower() in FREE_PROVIDERS:
        return
    if settings.llm_daily_budget_usd <= 0:
        return
    cost = _compute_token_cost(provider, prompt_tokens, completion_tokens)
    if cost <= 0:
        return
    _append_cost(path or spend_log_path(), cost, settings.llm_daily_budget_usd)


def charge(
    role: str,
    settings: Settings,
    *,
    path: Path | None = None,
    provider: str | None = None,
) -> None:
    """Flat-estimate fallback charge. Used when token counts are unavailable.

    Prefer ``charge_from_usage()`` for all paths where the API response is
    available (i.e. successful completions). This function is retained for
    the pre-flight guard in ``complete()`` (called before the API round-trip)
    and for recovered ``failed_generation`` payloads.

    Groq and Ollama are free — calls with those providers return immediately.
    ``llm_daily_budget_usd <= 0`` disables the paid ceiling entirely.
    """
    if role in FREE_ROLES or (provider or "").lower() in FREE_PROVIDERS:
        return
    if settings.llm_daily_budget_usd <= 0:
        return
    cost = ROLE_COST_USD.get(role, 0.003)
    if cost <= 0:
        return
    _append_cost(path or spend_log_path(), cost, settings.llm_daily_budget_usd)
