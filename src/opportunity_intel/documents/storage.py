from __future__ import annotations

import uuid
from pathlib import Path

from opportunity_intel.config import Settings


def ensure_upload_dir(settings: Settings) -> Path:
    settings.uploads_dir.mkdir(parents=True, exist_ok=True)
    return settings.uploads_dir


def save_upload(settings: Settings, filename: str, data: bytes) -> tuple[str, Path]:
    ensure_upload_dir(settings)
    ext = Path(filename).suffix.lower()
    stored_name = f"{uuid.uuid4().hex}{ext}"
    path = stored_file_path(settings, stored_name)
    path.write_bytes(data)
    return stored_name, path


def stored_file_path(settings: Settings, stored_name: str) -> Path:
    if not stored_name or Path(stored_name).name != stored_name:
        raise ValueError("Invalid stored file name")
    root = settings.uploads_dir.resolve()
    path = (root / stored_name).resolve()
    if not path.is_relative_to(root):
        raise ValueError("Invalid stored file name")
    return path


def delete_stored_file(settings: Settings, stored_name: str) -> None:
    path = stored_file_path(settings, stored_name)
    if path.exists():
        path.unlink()
