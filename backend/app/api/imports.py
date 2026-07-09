"""Import endpoints — Phase 2 upload / batch / records."""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.db.session import get_db
from app.models.import_batch import ImportBatch
from app.models.raw_import_record import RawImportRecord
from app.schemas.imports import (
    ImportBatchResponse,
    ImportUploadResponse,
    RawImportRecordListResponse,
    RawImportRecordResponse,
)
from app.services.import_service import (
    ImportUploadError,
    create_import_batch,
    save_upload_file,
)
from app.workers.tasks_import import parse_excel_batch

router = APIRouter()


@router.post(
    "/upload",
    response_model=ImportUploadResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def upload_excel(
    file: UploadFile = File(..., description="Qualys/MBSS Excel (.xlsx)"),
    uploaded_by: str | None = Form(default=None),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> ImportUploadResponse:
    """Accept Excel upload, create import_batch, enqueue Celery parse job.

    Does not execute any Remediation text from the file.
    """
    try:
        original_filename, stored_path = save_upload_file(file, settings=settings)
    except ImportUploadError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except OSError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to store upload: {exc}",
        ) from exc

    batch = create_import_batch(
        db,
        original_filename=original_filename,
        stored_path=stored_path,
        uploaded_by=uploaded_by,
    )

    # Async parse — worker streams with openpyxl read_only.
    parse_excel_batch.delay(batch.id)

    return ImportUploadResponse(
        batch=ImportBatchResponse.model_validate(batch),
        message="Upload accepted; parse job queued.",
    )


@router.get("/{batch_id}", response_model=ImportBatchResponse)
def get_import_batch(batch_id: int, db: Session = Depends(get_db)) -> ImportBatchResponse:
    batch = db.get(ImportBatch, batch_id)
    if batch is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Import batch not found")
    return ImportBatchResponse.model_validate(batch)


@router.get("/{batch_id}/records", response_model=RawImportRecordListResponse)
def list_import_records(
    batch_id: int,
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> RawImportRecordListResponse:
    batch = db.get(ImportBatch, batch_id)
    if batch is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Import batch not found")

    total = db.scalar(
        select(func.count()).select_from(RawImportRecord).where(
            RawImportRecord.batch_id == batch_id
        )
    ) or 0

    rows = db.scalars(
        select(RawImportRecord)
        .where(RawImportRecord.batch_id == batch_id)
        .order_by(RawImportRecord.row_number.asc())
        .offset(offset)
        .limit(limit)
    ).all()

    return RawImportRecordListResponse(
        batch_id=batch_id,
        total=total,
        limit=limit,
        offset=offset,
        items=[RawImportRecordResponse.model_validate(row) for row in rows],
    )


@router.post("/{batch_id}/generate-plan", status_code=status.HTTP_501_NOT_IMPLEMENTED)
def generate_plan(batch_id: int) -> None:
    """POST /imports/{batch_id}/generate-plan — Phase 5."""
    raise HTTPException(status_code=501, detail="Not implemented yet (Phase 5)")
