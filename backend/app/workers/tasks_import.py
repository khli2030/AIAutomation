"""Celery tasks for Excel import (Phase 2).

Uses openpyxl read_only streaming and inserts rows in chunks.
Never executes Remediation text.
"""

from __future__ import annotations

import logging
from pathlib import Path

from sqlalchemy.orm import Session

from app.config import get_settings
from app.constants.import_status import ImportBatchStatus
from app.db.session import SessionLocal
from app.models.import_batch import ImportBatch
from app.services.audit import write_audit_log
from app.services.excel_parser import ExcelColumnError, iter_excel_rows
from app.services.import_persist import insert_parsed_chunk
from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(name="imports.parse_excel_batch", bind=True, max_retries=0)
def parse_excel_batch(self, batch_id: int) -> dict[str, int | str | None]:
    """Parse uploaded Excel in chunks and persist raw_import_records."""
    settings = get_settings()
    db = SessionLocal()
    processed_rows = 0
    total_rows = 0

    try:
        batch = db.get(ImportBatch, batch_id)
        if batch is None:
            return {
                "batch_id": batch_id,
                "status": "not_found",
                "total_rows": 0,
                "processed_rows": 0,
                "error_message": "Import batch not found",
            }

        batch.status = ImportBatchStatus.PARSING.value
        batch.error_message = None
        write_audit_log(
            db,
            actor="system",
            action="parse",
            entity_type="import_batch",
            entity_id=batch.id,
            details={"event": "parse_started", "path": batch.stored_path},
        )
        db.commit()

        file_path = Path(batch.stored_path)
        if not file_path.is_file():
            raise FileNotFoundError(f"Stored Excel file missing: {file_path}")

        for chunk in iter_excel_rows(
            file_path,
            chunk_size=settings.excel_chunk_size,
        ):
            inserted = insert_parsed_chunk(db, batch_id=batch.id, chunk=chunk)
            processed_rows += inserted
            total_rows = processed_rows
            batch.processed_rows = processed_rows
            batch.total_rows = total_rows
            db.commit()

        batch.status = ImportBatchStatus.PARSED.value
        batch.total_rows = total_rows
        batch.processed_rows = processed_rows
        batch.error_message = None
        write_audit_log(
            db,
            actor="system",
            action="parse",
            entity_type="import_batch",
            entity_id=batch.id,
            details={
                "event": "parse_completed",
                "total_rows": total_rows,
                "processed_rows": processed_rows,
            },
        )
        db.commit()

        return {
            "batch_id": batch.id,
            "status": ImportBatchStatus.PARSED.value,
            "total_rows": total_rows,
            "processed_rows": processed_rows,
            "error_message": None,
        }

    except ExcelColumnError as exc:
        logger.exception("Excel column validation failed for batch_id=%s", batch_id)
        _mark_batch_failed(
            db,
            batch_id=batch_id,
            status=ImportBatchStatus.COLUMNS_INVALID.value,
            error_message=str(exc),
        )
        return {
            "batch_id": batch_id,
            "status": ImportBatchStatus.COLUMNS_INVALID.value,
            "total_rows": total_rows,
            "processed_rows": processed_rows,
            "error_message": str(exc),
        }
    except Exception as exc:  # noqa: BLE001 — persist failure state for operators
        logger.exception("Parse failed for batch_id=%s", batch_id)
        _mark_batch_failed(
            db,
            batch_id=batch_id,
            status=ImportBatchStatus.PARSE_FAILED.value,
            error_message=str(exc),
        )
        return {
            "batch_id": batch_id,
            "status": ImportBatchStatus.PARSE_FAILED.value,
            "total_rows": total_rows,
            "processed_rows": processed_rows,
            "error_message": str(exc),
        }
    finally:
        db.close()


def _mark_batch_failed(
    db: Session,
    *,
    batch_id: int,
    status: str,
    error_message: str,
) -> None:
    try:
        db.rollback()
    except Exception:  # noqa: BLE001
        pass
    batch = db.get(ImportBatch, batch_id)
    if batch is None:
        return
    batch.status = status
    batch.error_message = error_message[:4000]
    write_audit_log(
        db,
        actor="system",
        action="parse",
        entity_type="import_batch",
        entity_id=batch.id,
        details={"event": "parse_failed", "status": status, "error": error_message},
    )
    db.commit()
