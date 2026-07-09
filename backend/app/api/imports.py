"""Import endpoints — Phase 2 upload / batch / records."""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.db.session import get_db
from app.models.import_batch import ImportBatch
from app.models.raw_import_record import RawImportRecord
from app.schemas.ai_suggestions import AIAnalyzeSummaryResponse
from app.schemas.dashboard import ImportBatchListResponse
from app.schemas.imports import (
    ImportBatchResponse,
    ImportUploadResponse,
    RawImportRecordListResponse,
    RawImportRecordResponse,
    ValidationSummaryResponse,
)
from app.schemas.plans import ExecutionPlanResponse, GeneratePlanResponse
from app.services.ai_analyzer import AIAnalyzerService
from app.services.import_service import (
    ImportUploadError,
    create_import_batch_record,
    finalize_upload_audit,
    save_upload_for_batch,
)
from app.services.plan_generator import PlanGeneratorService
from app.services.validator import RecordValidationService
from app.workers.tasks_import import parse_excel_batch

router = APIRouter()


@router.get("", response_model=ImportBatchListResponse)
@router.get("/", response_model=ImportBatchListResponse, include_in_schema=False)
def list_import_batches(
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> ImportBatchListResponse:
    """List import batches newest-first (Phase 7 dashboard / imports index)."""
    total = db.scalar(select(func.count()).select_from(ImportBatch)) or 0
    rows = db.scalars(
        select(ImportBatch)
        .order_by(ImportBatch.id.desc())
        .offset(offset)
        .limit(limit)
    ).all()
    return ImportBatchListResponse(
        total=int(total),
        limit=limit,
        offset=offset,
        items=[ImportBatchResponse.model_validate(row) for row in rows],
    )


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
    """Accept .xlsx upload, store under uploads/{batch_id}/, queue Celery parse.

    Does not classify remediation or generate execution plans.
    Does not execute any Remediation text.
    """
    try:
        original = file.filename or "upload.xlsx"
        batch = create_import_batch_record(
            db,
            original_filename=original,
            uploaded_by=uploaded_by,
        )
        save_upload_for_batch(file, batch=batch, settings=settings)
        batch = finalize_upload_audit(db, batch)
    except ImportUploadError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except OSError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to store upload: {exc}",
        ) from exc

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
    validation_status: str | None = Query(default=None),
    task_code: str | None = Query(default=None),
    device_name: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> RawImportRecordListResponse:
    batch = db.get(ImportBatch, batch_id)
    if batch is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Import batch not found")

    filters = [RawImportRecord.batch_id == batch_id]
    if validation_status:
        filters.append(RawImportRecord.validation_status == validation_status)
    if task_code:
        filters.append(RawImportRecord.task_code == task_code)
    if device_name:
        filters.append(RawImportRecord.device_name.ilike(f"%{device_name.strip()}%"))

    total = db.scalar(
        select(func.count()).select_from(RawImportRecord).where(*filters)
    ) or 0

    rows = db.scalars(
        select(RawImportRecord)
        .where(*filters)
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


@router.post(
    "/{batch_id}/validate",
    response_model=ValidationSummaryResponse,
    status_code=status.HTTP_200_OK,
)
def validate_import_batch(
    batch_id: int,
    db: Session = Depends(get_db),
) -> ValidationSummaryResponse:
    """Validate + rule-based classify raw_import_records for a batch (Phase 3).

    Does not generate execution plans, call AI, or invoke Ansible/MOCK execution.
    """
    batch = db.get(ImportBatch, batch_id)
    if batch is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Import batch not found")

    try:
        summary = RecordValidationService(db).validate_batch(batch_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    return ValidationSummaryResponse(**summary.to_dict())


@router.post(
    "/{batch_id}/ai-analyze-needs-review",
    response_model=AIAnalyzeSummaryResponse,
    status_code=status.HTTP_200_OK,
)
def ai_analyze_needs_review(
    batch_id: int,
    db: Session = Depends(get_db),
) -> AIAnalyzeSummaryResponse:
    """Analyze NEEDS_REVIEW records only; persist draft AI suggestions (Phase 4).

    Does not execute playbooks, call Ansible/MOCK, or write remediation_catalog.
    """
    batch = db.get(ImportBatch, batch_id)
    if batch is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Import batch not found")

    try:
        summary = AIAnalyzerService(db).analyze_batch_needs_review(batch_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    return AIAnalyzeSummaryResponse(**summary.to_dict())


@router.post(
    "/{batch_id}/generate-plan",
    response_model=GeneratePlanResponse,
    status_code=status.HTTP_200_OK,
)
def generate_plan(
    batch_id: int,
    created_by: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> GeneratePlanResponse:
    """Generate execution plan from READY_FOR_PLAN records only (Phase 5).

    Creates jobs with status=waiting_dry_run. Does not dry-run, run, or call Ansible/MOCK.
    Never uses AI generated_playbook.
    """
    batch = db.get(ImportBatch, batch_id)
    if batch is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Import batch not found")

    try:
        result = PlanGeneratorService(db).generate_plan(batch_id, created_by=created_by)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    plan = result.plan
    return GeneratePlanResponse(
        plan=ExecutionPlanResponse(
            id=plan.id,
            batch_id=plan.batch_id,
            status=plan.status,
            created_by=plan.created_by,
            created_at=plan.created_at,
            job_count=result.job_count,
            target_count=result.target_count,
            skipped_records=result.skipped_records,
            ready_for_plan_records=result.ready_for_plan_records,
            skipped_missing_catalog=result.skipped_missing_catalog,
            skipped_disabled_catalog=result.skipped_disabled_catalog,
            skipped_missing_asset=result.skipped_missing_asset,
            skipped_missing_asset_metadata=result.skipped_missing_asset_metadata,
            skipped_excluded_status=result.skipped_excluded_status,
        )
    )
