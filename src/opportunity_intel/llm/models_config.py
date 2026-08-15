from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import yaml

Provider = Literal["deepseek", "groq", "ollama", "huggingface", "openai", "gemini"]
RoleName = Literal["extract", "reason", "draft", "polish", "embed", "fallback"]


@dataclass(frozen=True)
class RoleConfig:
    name: str
    provider: Provider
    model: str
    thinking: str = "disabled"
    reasoning_effort: str | None = None
    enabled_env: str | None = None
    notes: str = ""


@dataclass(frozen=True)
class AppModelConfig:
    roles: dict[str, RoleConfig]
    target_countries: tuple[str, ...]
    excluded_countries: tuple[str, ...]


def load_model_config(path: Path) -> AppModelConfig:
    raw: dict[str, Any] = yaml.safe_load(path.read_text()) or {}
    roles: dict[str, RoleConfig] = {}
    for name, spec in (raw.get("roles") or {}).items():
        roles[name] = RoleConfig(
            name=name,
            provider=spec["provider"],
            model=spec["model"],
            thinking=spec.get("thinking", "disabled"),
            reasoning_effort=spec.get("reasoning_effort"),
            enabled_env=spec.get("enabled_env"),
            notes=spec.get("notes", ""),
        )
    return AppModelConfig(
        roles=roles,
        target_countries=tuple(raw.get("target_countries") or ()),
        excluded_countries=tuple(raw.get("excluded_countries") or ()),
    )
