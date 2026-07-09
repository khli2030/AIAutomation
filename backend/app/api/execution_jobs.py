"""Execution job endpoints — Phase 5 approve/reject + Phase 6 mock dry-run/run/results + Phase 7 list."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.constants.job_result_type import JobResultType
from app.db.session import get_db
from app.models.execution_job import ExecutionJob
from app.models.job_result import JobResult
from app.schemas.dashboard import ExecutionJobListAllResponse
from app.schemas.plans import (
    ExecutionJobResponse,
    JobExecutionSummaryResponse,
    JobResultResponse,
    JobResultsListResponse,
    JobReviewRequest,
)
from app.services.ansible_execution import (
    AnsibleExecutionError,
    AnsibleExecutionService,
    summary_to_dict,
)
from app.services.job_approval import JobApprovalError, JobApprovalService
from app.services.plan_query import PlanQueryService

router = APIRouter()


def _job_response(db: Session, job: ExecutionJob) -> ExecutionJobResponse:
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


def _summary_response(summary) -> JobExecutionSummaryResponse:
    data = summary_to_dict(summary)
    return JobExecutionSummaryResponse(**data)


@router.get("", response_model=ExecutionJobListAllResponse)
@router.get("/", response_model=ExecutionJobListAllResponse, include_in_schema=False)
def list_execution_jobs(
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    status_filter: str | None = Query(default=None, alias="status"),
    plan_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
) -> ExecutionJobListAllResponse:
    """List execution jobs newest-first (Phase 7 approvals / jobs pages)."""
    filters = []
    if status_filter:
        filters.append(ExecutionJob.status == status_filter)
    if plan_id is not None:
        filters.append(ExecutionJob.plan_id == plan_id)

    count_q = select(func.count()).select_from(ExecutionJob)
    query = select(ExecutionJob)
    if filters:
        count_q = count_q.where(*filters)
        query = query.where(*filters)

    total = db.scalar(count_q) or 0
    jobs = db.scalars(
        query.order_by(ExecutionJob.id.desc()).offset(offset).limit(limit)
    ).all()
    return ExecutionJobListAllResponse(
        total=int(total),
        limit=limit,
        offset=offset,
        items=[_job_response(db, job) for job in jobs],
    )


@router.get("/{job_id}", response_model=ExecutionJobResponse)
def get_execution_job(
    job_id: int,
    db: Session = Depends(get_db),
) -> ExecutionJobResponse:
    job = db.get(ExecutionJob, job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Execution job not found")
    return _job_response(db, job)


@router.post("/{job_id}/dry-run", response_model=JobExecutionSummaryResponse)
def dry_run_job(
    job_id: int,
    db: Session = Depends(get_db),
) -> JobExecutionSummaryResponse:
    """Mock dry-run via AnsibleExecutionService (MOCK_MODE path only for MVP).

    Allowed only when job status=waiting_dry_run. Never uses AI draft playbooks.
    """
    try:
        summary = AnsibleExecutionService(db).dry_run_job(job_id)
    except AnsibleExecutionError as exc:
        detail = str(exc)
        code = (
            status.HTTP_404_NOT_FOUND
            if "not found" in detail.lower()
            else status.HTTP_400_BAD_REQUEST
        )
        raise HTTPException(status_code=code, detail=detail) from exc
    return _summary_response(summary)


@router.post("/{job_id}/approve", response_model=ExecutionJobResponse)
def approve_job(
    job_id: int,
    body: JobReviewRequest | None = None,
    db: Session = Depends(get_db),
) -> ExecutionJobResponse:
    """Approve only when status is dry_run_success. waiting_dry_run → 400."""
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


@router.post("/{job_id}/run", response_model=JobExecutionSummaryResponse)
def run_job(
    job_id: int,
    db: Session = Depends(get_db),
) -> JobExecutionSummaryResponse:
    """Mock apply via AnsibleExecutionService after approval.

    Allowed only when job status=approved. Never uses AI draft playbooks.
    """
    try:
        summary = AnsibleExecutionService(db).run_job(job_id)
    except AnsibleExecutionError as exc:
        detail = str(exc)
        code = (
            status.HTTP_404_NOT_FOUND
            if "not found" in detail.lower()
            else status.HTTP_400_BAD_REQUEST
        )
        raise HTTPException(status_code=code, detail=detail) from exc
    return _summary_response(summary)


@router.get("/{job_id}/results", response_model=JobResultsListResponse)
def get_job_results(
    job_id: int,
    result_type: str | None = Query(
        default=None,
        description="Filter by result_type: dry_run or run. Omit to return both.",
    ),
    db: Session = Depends(get_db),
) -> JobResultsListResponse:
    """GET /execution-jobs/{job_id}/results — per-host mock/real results.

    Use ?result_type=dry_run or ?result_type=run to separate dry-run vs apply results.
    """
    job = db.get(ExecutionJob, job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Execution job not found")

    if result_type is not None:
        allowed = {JobResultType.DRY_RUN.value, JobResultType.RUN.value}
        if result_type not in allowed:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"result_type must be one of: {', '.join(sorted(allowed))}",
            )

    query = select(JobResult).where(JobResult.job_id == job_id)
    if result_type is not None:
        query = query.where(JobResult.result_type == result_type)
    rows = db.scalars(query.order_by(JobResult.id.asc())).all()

    return JobResultsListResponse(
        job_id=job_id,
        job_status=job.status,
        dry_run_status=job.dry_run_status,
        result_type_filter=result_type,
        total=len(rows),
        items=[JobResultResponse.model_validate(row) for row in rows],
    )
