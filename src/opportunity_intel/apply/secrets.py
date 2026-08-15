"""Local HMAC secret for approval tokens. Never log the raw secret."""

from __future__ import annotations

import secrets
from pathlib import Path

from opportunity_intel.config import ROOT, Settings

_SECRET_FILE = ROOT / "data" / "apply_signing_secret"


def resolve_signing_secret(settings: Settings) -> str:
    configured = (settings.apply_signing_secret or "").strip()
    if configured:
        return configured
    _SECRET_FILE.parent.mkdir(parents=True, exist_ok=True)
    if _SECRET_FILE.exists():
        stored = _SECRET_FILE.read_text(encoding="utf-8").strip()
        if stored:
            return stored
    generated = secrets.token_hex(32)
    _SECRET_FILE.write_text(generated, encoding="utf-8")
    try:
        _SECRET_FILE.chmod(0o600)
    except OSError:
        pass
    return generated


def secret_file_path() -> Path:
    return _SECRET_FILE
