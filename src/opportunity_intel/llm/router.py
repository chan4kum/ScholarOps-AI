from __future__ import annotations

import hashlib
import time
import warnings
from dataclasses import dataclass

import httpx
from openai import OpenAI

from opportunity_intel.config import Settings
from opportunity_intel.llm.budget import charge
from opportunity_intel.llm.models_config import AppModelConfig, RoleConfig
from opportunity_intel.observability.trace import record_llm_call

# HuggingFace Inference API endpoint for sentence-transformer models.
# Returns list[list[float]] for a batch of input strings.
_HF_INFERENCE_URL = "https://api-inference.huggingface.co/models/{model}"

# Fallback embedding dimension when the hash-trick is used (no HF token).
_HASH_DIM = 256


@dataclass
class CompletionResult:
    text: str
    model: str
    provider: str
    role: str


class LLMRouter:
    """OpenAI-compatible router. Agents pass a role, never a vendor."""

    def __init__(self, settings: Settings, model_config: AppModelConfig) -> None:
        self.settings = settings
        self.model_config = model_config
        self._clients: dict[str, OpenAI] = {}
        # In-process embedding cache: sha256(text[:2000]) -> vector
        self._embed_cache: dict[str, list[float]] = {}

    def _client_for(self, provider: str) -> OpenAI:
        if provider in self._clients:
            return self._clients[provider]
        if provider == "deepseek":
            client = OpenAI(
                api_key=self.settings.deepseek_api_key,
                base_url=self.settings.deepseek_base_url,
            )
        elif provider == "groq":
            client = OpenAI(
                api_key=self.settings.groq_api_key,
                base_url=self.settings.groq_base_url,
            )
        elif provider == "openai":
            if not self.settings.openai_api_key:
                raise ValueError("OPENAI_API_KEY is not set")
            client = OpenAI(
                api_key=self.settings.openai_api_key,
                base_url=self.settings.openai_base_url,
            )
        elif provider == "ollama":
            client = OpenAI(
                api_key=self.settings.ollama_api_key,
                base_url=self.settings.ollama_base_url,
            )
        elif provider == "gemini":
            if not self.settings.gemini_api_key:
                raise ValueError("GEMINI_API_KEY is not set")
            client = OpenAI(
                api_key=self.settings.gemini_api_key,
                base_url=self.settings.gemini_base_url,
            )
        else:
            raise ValueError(f"Unsupported chat provider: {provider}")
        self._clients[provider] = client
        return client

    def resolve(self, role: str) -> RoleConfig:
        if role not in self.model_config.roles:
            raise KeyError(f"Unknown LLM role: {role}")
        return self.model_config.roles[role]

    # ------------------------------------------------------------------
    # Embedding — real BGE-small via HF Inference API, hash-trick fallback
    # ------------------------------------------------------------------

    def embed(self, texts: list[str]) -> list[list[float]]:
        """Return one embedding vector per input text.

        When ``HF_TOKEN`` is configured, calls the HuggingFace Inference API
        for ``BAAI/bge-small-en-v1.5`` (384-dim, normalised).

        When the token is absent or the API call fails, silently falls back to
        a local 256-dim hash-trick embedding so the system remains functional
        offline. A ``UserWarning`` is emitted on fallback so the caller can
        choose to surface it.

        Results are cached in-process keyed by ``sha256(text[:2000])`` so
        repeated calls for the same text within a session are free.
        """
        if not texts:
            return []

        results: list[list[float]] = [[] for _ in texts]
        uncached_indices: list[int] = []
        uncached_texts: list[str] = []

        for i, text in enumerate(texts):
            key = hashlib.sha256(text[:2000].encode()).hexdigest()
            if key in self._embed_cache:
                results[i] = self._embed_cache[key]
            else:
                uncached_indices.append(i)
                uncached_texts.append(text)

        if not uncached_texts:
            return results

        if self.settings.hf_token:
            try:
                vectors = self._embed_via_hf(uncached_texts)
                for idx, vec in zip(uncached_indices, vectors):
                    key = hashlib.sha256(texts[idx][:2000].encode()).hexdigest()
                    self._embed_cache[key] = vec
                    results[idx] = vec
                return results
            except Exception as exc:  # noqa: BLE001
                warnings.warn(
                    f"HF Inference API failed, using hash-trick fallback: {exc}",
                    UserWarning,
                    stacklevel=2,
                )

        # Hash-trick fallback (no HF token or API failure)
        for idx, text in zip(uncached_indices, uncached_texts):
            vec = _hash_embed(text)
            key = hashlib.sha256(text[:2000].encode()).hexdigest()
            self._embed_cache[key] = vec
            results[idx] = vec
        return results

    def _embed_via_hf(self, texts: list[str]) -> list[list[float]]:
        """Call HF Inference API for BAAI/bge-small-en-v1.5.

        Returns list[list[float]] — one 384-dim vector per text, already
        normalised by the model.
        """
        spec = self.resolve("embed")
        url = _HF_INFERENCE_URL.format(model=spec.model)
        response = httpx.post(
            url,
            headers={
                "Authorization": f"Bearer {self.settings.hf_token}",
                "Content-Type": "application/json",
            },
            json={"inputs": texts},
            timeout=30.0,
        )
        response.raise_for_status()
        data = response.json()
        # HF returns list[list[float]] for batch inputs
        if isinstance(data, list) and data and isinstance(data[0], list):
            return [list(map(float, vec)) for vec in data]
        # Single-input response: list[float]
        if isinstance(data, list) and data and isinstance(data[0], (int, float)):
            return [[float(v) for v in data]]
        raise ValueError(f"Unexpected HF embedding response shape: {type(data)}")

    # ------------------------------------------------------------------
    # Chat completion
    # ------------------------------------------------------------------

    def complete(
        self,
        role: str,
        messages: list[dict[str, str]],
        *,
        json_mode: bool = False,
    ) -> CompletionResult:
        spec = self.resolve(role)
        if spec.provider == "huggingface":
            raise ValueError("Hugging Face is configured for embeddings, not chat")
        if role == "polish" and not self.settings.groq_polish_enabled:
            raise PermissionError("Polish is disabled. Set GROQ_POLISH_ENABLED=true to use it.")
        if (
            spec.provider == "deepseek"
            and not self.settings.deepseek_api_key
            and not self.settings.offline
        ):
            if self.settings.gemini_api_key:
                spec = RoleConfig(
                    name=spec.name,
                    provider="gemini",
                    model=self.settings.gemini_model,
                    thinking="disabled",
                )
            elif self.settings.openai_api_key:
                spec = RoleConfig(
                    name=spec.name,
                    provider="openai",
                    model=self.settings.openai_model,
                    thinking="disabled",
                )
        if self.settings.offline:
            spec = self.resolve("fallback")
            charge("fallback", self.settings, provider=spec.provider)
        else:
            charge(role, self.settings, provider=spec.provider)

        extra_body: dict[str, object] = {}
        kwargs: dict[str, object] = {
            "model": spec.model,
            "messages": messages,
        }
        if spec.provider == "deepseek":
            extra_body["thinking"] = {
                "type": "enabled" if spec.thinking == "enabled" else "disabled"
            }
            if spec.thinking == "enabled" and spec.reasoning_effort:
                kwargs["reasoning_effort"] = spec.reasoning_effort
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}
        if extra_body:
            kwargs["extra_body"] = extra_body

        started = time.perf_counter()
        try:
            response = self._client_for(spec.provider).chat.completions.create(**kwargs)
            text = response.choices[0].message.content or ""
            record_llm_call(
                role=role,
                provider=spec.provider,
                model=spec.model,
                ok=True,
                duration_ms=int((time.perf_counter() - started) * 1000),
                preview=text[:200],
            )
        except Exception as exc:
            recovered = _failed_generation(exc)
            if recovered:
                record_llm_call(
                    role=role,
                    provider=spec.provider,
                    model=spec.model,
                    ok=True,
                    duration_ms=int((time.perf_counter() - started) * 1000),
                    preview=recovered[:200],
                )
                return CompletionResult(
                    text=recovered,
                    model=spec.model,
                    provider=spec.provider,
                    role=role,
                )
            record_llm_call(
                role=role,
                provider=spec.provider,
                model=spec.model,
                ok=False,
                duration_ms=int((time.perf_counter() - started) * 1000),
                error=str(exc),
            )
            raise
        return CompletionResult(
            text=text,
            model=spec.model,
            provider=spec.provider,
            role=role,
        )


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------


def _hash_embed(text: str) -> list[float]:
    """256-dim bag-of-tokens hash embedding. Deterministic, offline, no network."""
    import math
    import re

    token_re = re.compile(r"[a-z0-9]{3,}")
    vec = [0.0] * _HASH_DIM
    for token in token_re.findall(text.lower()):
        vec[hash(token) % _HASH_DIM] += 1.0
    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / norm for v in vec]


def _failed_generation(exc: BaseException) -> str | None:
    """Groq json_mode often returns usable JSON in failed_generation."""
    body = getattr(exc, "body", None)
    if isinstance(body, dict):
        error = body.get("error") if isinstance(body.get("error"), dict) else body
        raw = error.get("failed_generation") if isinstance(error, dict) else None
        if isinstance(raw, str) and raw.strip().startswith(("{", "[")):
            return raw.strip()
    return None
