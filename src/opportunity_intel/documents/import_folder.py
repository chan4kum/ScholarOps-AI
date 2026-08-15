from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy.orm import Session

from opportunity_intel.config import Settings
from opportunity_intel.documents.extract import extract_text
from opportunity_intel.documents.storage import save_upload
from opportunity_intel.domain.models import UploadedDocument
from opportunity_intel.observability.trace import agent_run

SUPPORTED_SUFFIXES = {".pdf", ".docx", ".doc", ".txt", ".md", ".markdown"}
SKIP_DIR_NAMES = {".agents", ".git", "node_modules", "__pycache__"}
SKIP_FILE_NAMES = {"AGENTS.md"}


@dataclass
class FolderImportResult:
    folder: str
    scanned: int
    imported: int
    skipped: int
    errors: list[str]


def resolve_import_dir(settings: Settings) -> Path:
    raw = settings.documents_import_dir
    path = Path(raw).expanduser()
    if not path.is_absolute():
        path = settings.models_config_path.parent.parent / path
    return path.resolve()


def guess_doc_type(filename: str) -> str:
    name = filename.lower()
    if "transcript" in name:
        return "transcript"
    if "publication" in name or "paper" in name:
        return "publication"
    if "cover" in name or "motivation" in name or "outreach" in name:
        return "cover_letter"
    if any(
        token in name
        for token in ("proposal", "statement", "research_strategy", "realization", "background")
    ):
        return "research_proposal"
    if "cv" in name or "resume" in name:
        return "research_cv" if "research" in name else "academic_cv"
    return "other"


def iter_importable_files(root: Path) -> list[Path]:
    if not root.is_dir():
        return []
    files: list[Path] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        if path.name in SKIP_FILE_NAMES:
            continue
        if path.suffix.lower() not in SUPPORTED_SUFFIXES:
            continue
        if any(part in SKIP_DIR_NAMES for part in path.parts):
            continue
        files.append(path)
    return files


def file_hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def import_documents_from_folder(session: Session, settings: Settings) -> FolderImportResult:
    root = resolve_import_dir(settings)
    if not root.is_dir():
        return FolderImportResult(
            folder=str(root),
            scanned=0,
            imported=0,
            skipped=0,
            errors=[f"Folder not found: {root}"],
        )

    files = iter_importable_files(root)
    with agent_run("importer", "folder", str(root)):
        return _import_files(session, settings, root, files)


def _import_files(
    session: Session,
    settings: Settings,
    root: Path,
    files: list[Path],
) -> FolderImportResult:
    imported = 0
    skipped = 0
    errors: list[str] = []

    for path in files:
        source = str(path)
        try:
            data = path.read_bytes()
            digest = file_hash(data)
        except OSError as exc:
            errors.append(f"{path.name}: {exc}")
            continue

        existing = session.query(UploadedDocument).filter_by(source_path=source).one_or_none()
        if existing and existing.content_hash == digest:
            skipped += 1
            continue

        try:
            stored_name, dest = save_upload(settings, path.name, data)
            text = extract_text(dest, "")
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{path.name}: {exc}")
            continue

        if existing:
            existing.stored_name = stored_name
            existing.original_name = path.name
            existing.doc_type = guess_doc_type(path.name)
            existing.file_size = len(data)
            existing.extracted_text = text
            existing.content_hash = digest
            existing.status = "uploaded"
            existing.parsed_facts = ""
        else:
            session.add(
                UploadedDocument(
                    original_name=path.name,
                    stored_name=stored_name,
                    doc_type=guess_doc_type(path.name),
                    mime_type="",
                    file_size=len(data),
                    extracted_text=text,
                    source_path=source,
                    content_hash=digest,
                    status="uploaded",
                )
            )
        imported += 1

    session.commit()
    return FolderImportResult(
        folder=str(root),
        scanned=len(files),
        imported=imported,
        skipped=skipped,
        errors=errors,
    )
