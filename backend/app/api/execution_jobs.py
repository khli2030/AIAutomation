"""Execution job endpoints — Phase 5 approve/reject; dry-run/run remain Phase 6."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.plans import ExecutionJobResponse, JobReviewRequest
from app.services.job_approval import JobApprovalError, JobApprovalService
from app.services.plan_query import PlanQueryService

router = APIRouter()


def _job_response(db: Session, job) -> ExecutionJobResponse:
    target_count = PlanQueryService(db).count_job_targets(job.id)
    return ExecutionJobResponse(
        id=job.id,
        plan_id=job.plan_id,
        task_code=job.task_code,
        environment=job.environment,
        criticality=job.criticality,
        ansible_group=job.ansible_group,
        status=job.status,
        dry_run_status=job.dry_run_status,
        approved_by=job.approved_by,
        approved_at=job.approved_at,
        started_at=job.started_at,
        finished_at=job.finished_at,
        target_count=target_count,
    )


@router.post("/{job_id}/dry-run", status_code=status.HTTP_501_NOT_IMPLEMENTED)
def dry_run_job(job_id: int) -> None:
    raise HTTPException(status_code=501, detail="Not implemented yet (Phase 6)")


@router.post("/{job_id}/approve", response_model=ExecutionJobResponse)
def approve_job(
    job_id: int,
    body: JobReviewRequest | None = None,
    db: Session = Depends(get_db),
) -> ExecutionJobResponse:
    """Approve only after dry_run_success. waiting_dry_run → 400 in Phase 5."""
    payload = body or JobReviewRequest()
    try:
        job = JobApprovalService(db).approve(job_id, reviewed_by=payload.reviewed_by)
    except JobApprovalError as exc:
        detail = str(exc)
        code = (
            status.HTTP_404_NOT_FOUND
            if "not found" in detail.lower()
            else status.HTTP_400_BAD_REQUEST
        )
        raise HTTPException(status_code=code, detail=detail) from exc
    return _job_response(db, job)


@router.post("/{job_id}/reject", response_model=ExecutionJobResponse)
def reject_job(
    job_id: int,
    body: JobReviewRequest | None = None,
    db: Session = Depends(get_db),
) -> ExecutionJobResponse:
    """Reject waiting_dry_run / dry_run_failed / waiting_approval jobs. No execution."""
    payload = body or JobReviewRequest()
    try:
        job = JobApprovalService(db).reject(job_id, reviewed_by=payload.reviewed_by)
    except JobApprovalError as exc:
        detail = str(exc)
        code = (
            status.HTTP_404_NOT_FOUND
            if "not found" in detail.lower()
            else status.HTTP_400_BAD_REQUEST
        )
        raise HTTPException(status_code=code, detail=detail) from exc
    return _job_response(db, job)


@router.post("/{job_id}/run", status_code=status.HTTP_501_NOT_IMPLEMENTED)
def run_job(job_id: int) -> None:
    """Real execution — only after dry-run success + approval (Phase 6)."""
    raise HTTPException(status_code=501, detail="Not implemented yet (Phase 6)")


@router.get("/{job_id}/results", status_code=status.HTTP_501_NOT_IMPLEMENTED)
def get_job_results(job_id: int) -> None:
    raise HTTPException(status_code=501, detail="Not implemented yet (Phase 6)")
