"""Import upload helpers — save file, create batch, enqueue parse."""

from __future__ import annotations

import re
import uuid
from pathlib import Path

from fastapi import UploadFile
from sqlalchemy.orm import Session

from app.config import Settings
from app.constants.import_status import ImportBatchStatus
from app.models.import_batch import ImportBatch
from app.services.audit import write_audit_log

ALLOWED_EXTENSIONS = {".xlsx"}
# Reject path traversal / odd characters in original filenames when storing.
_SAFE_NAME_RE = re.compile(r"[^A-Za-z0-9._-]+")


class ImportUploadError(ValueError):
    """Raised for invalid upload payloads."""


def _safe_filename(original: str) -> str:
    name = Path(original).name.strip() or "upload.xlsx"
    name = _SAFE_NAME_RE.sub("_", name)
    if not name.lower().endswith(".xlsx"):
        name = f"{name}.xlsx"
    return name[:200]


def ensure_upload_dir(upload_dir: str | Path) -> Path:
    path = Path(upload_dir)
    path.mkdir(parents=True, exist_ok=True)
    return path


def validate_upload_file(file: UploadFile) -> None:
    filename = file.filename or ""
    suffix = Path(filename).suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise ImportUploadError("Only .xlsx Excel files are supported")
    content_type = (file.content_type or "").lower()
    # Browsers vary; allow common Excel MIME types and octet-stream.
    allowed_types = {
        "",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "application/octet-stream",
        "application/zip",
    }
    if content_type and content_type not in allowed_types:
        # Soft check — extension is authoritative for MVP.
        if "sheet" not in content_type and "excel" not in content_type:
            raise ImportUploadError(f"Unsupported content type: {content_type}")


def save_upload_file(
    file: UploadFile,
    *,
    settings: Settings,
) -> tuple[str, Path]:
    """Persist upload under UPLOAD_DIR. Returns (original_filename, stored_path)."""
    validate_upload_file(file)
    original = file.filename or "upload.xlsx"
    safe = _safe_filename(original)
    upload_root = ensure_upload_dir(settings.upload_dir)
    stored_name = f"{uuid.uuid4().hex}_{safe}"
    stored_path = upload_root / stored_name

    # Stream to disk to avoid loading entire file into memory.
    with stored_path.open("wb") as out:
        while True:
            chunk = file.file.read(1024 * 1024)
            if not chunk:
                break
            out.write(chunk)

    if stored_path.stat().st_size == 0:
        stored_path.unlink(missing_ok=True)
        raise ImportUploadError("Uploaded file is empty")

    return original, stored_path


def create_import_batch(
    db: Session,
    *,
    original_filename: str,
    stored_path: Path,
    uploaded_by: str | None,
) -> ImportBatch:
    batch = ImportBatch(
        original_filename=original_filename,
        stored_path=str(stored_path),
        status=ImportBatchStatus.UPLOADED.value,
        total_rows=None,
        processed_rows=0,
        uploaded_by=uploaded_by,
        error_message=None,
    )
    db.add(batch)
    db.flush()
    write_audit_log(
        db,
        actor=uploaded_by or "anonymous",
        action="upload",
        entity_type="import_batch",
        entity_id=batch.id,
        details={
            "original_filename": original_filename,
            "stored_path": str(stored_path),
        },
    )
    db.commit()
    db.refresh(batch)
    return batch
