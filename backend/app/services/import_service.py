"""Import upload helpers — save under ./data/uploads/{batch_id}/."""

from __future__ import annotations

import re
import shutil
from pathlib import Path

from fastapi import UploadFile
from sqlalchemy.orm import Session

from app.config import Settings
from app.constants.import_status import ImportBatchStatus
from app.models.import_batch import ImportBatch
from app.services.audit import write_audit_log

ALLOWED_EXTENSIONS = {".xlsx"}
_SAFE_NAME_RE = re.compile(r"[^A-Za-z0-9._-]+")


class ImportUploadError(ValueError):
    """Raised for invalid upload payloads."""


def _safe_filename(original: str) -> str:
    """Basename-only sanitized name — never use raw client paths on disk."""
    # Path(...).name strips directories / traversal segments (e.g. ../../etc/passwd.xlsx).
    name = Path(original).name.strip() or "upload.xlsx"
    name = name.replace("\\", "_").replace("/", "_")
    name = _SAFE_NAME_RE.sub("_", name)
    if name in {".", ".."} or not name:
        name = "upload.xlsx"
    if not name.lower().endswith(".xlsx"):
        name = f"{name}.xlsx"
    return name[:200]


def validate_upload_file(file: UploadFile) -> None:
    filename = file.filename or ""
    suffix = Path(filename).suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise ImportUploadError("Only .xlsx Excel files are supported")


def create_import_batch_record(
    db: Session,
    *,
    original_filename: str,
    uploaded_by: str | None,
) -> ImportBatch:
    """Create batch first so we can store files under uploads/{batch_id}/."""
    batch = ImportBatch(
        original_filename=original_filename,
        stored_path="",  # filled after directory is known
        status=ImportBatchStatus.UPLOADED.value,
        total_records=0,
        valid_records=0,
        invalid_records=0,
        total_rows=0,
        processed_rows=0,
        uploaded_by=uploaded_by,
        error_message=None,
    )
    db.add(batch)
    db.flush()
    return batch


def save_upload_for_batch(
    file: UploadFile,
    *,
    batch: ImportBatch,
    settings: Settings,
) -> Path:
    """Save upload to UPLOAD_DIR/{batch_id}/{safe_filename}."""
    validate_upload_file(file)
    upload_root = Path(settings.upload_dir)
    batch_dir = upload_root / str(batch.id)
    batch_dir.mkdir(parents=True, exist_ok=True)

    safe = _safe_filename(file.filename or batch.original_filename)
    stored_path = (batch_dir / safe).resolve()
    # Defense-in-depth: refuse if resolved path escapes the batch directory.
    if not stored_path.is_relative_to(batch_dir.resolve()):
        raise ImportUploadError("Invalid upload path")

    with stored_path.open("wb") as out:
        shutil.copyfileobj(file.file, out, length=1024 * 1024)

    if stored_path.stat().st_size == 0:
        stored_path.unlink(missing_ok=True)
        raise ImportUploadError("Uploaded file is empty")

    batch.stored_path = str(stored_path)
    return stored_path


def finalize_upload_audit(db: Session, batch: ImportBatch) -> ImportBatch:
    write_audit_log(
        db,
        actor=batch.uploaded_by or "anonymous",
        action="upload",
        entity_type="import_batch",
        entity_id=batch.id,
        details={
            "original_filename": batch.original_filename,
            "stored_path": batch.stored_path,
        },
    )
    db.commit()
    db.refresh(batch)
    return batch
