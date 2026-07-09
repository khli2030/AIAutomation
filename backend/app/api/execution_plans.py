"""Execution plan endpoints — Phase 5 (no Ansible execution)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.plans import (
    ExecutionJobListResponse,
    ExecutionJobResponse,
    ExecutionPlanResponse,
)
from app.services.plan_query import PlanQueryError, PlanQueryService

router = APIRouter()


@router.get("/{plan_id}", response_model=ExecutionPlanResponse)
def get_execution_plan(
    plan_id: int,
    db: Session = Depends(get_db),
) -> ExecutionPlanResponse:
    """GET /execution-plans/{plan_id}."""
    service = PlanQueryService(db)
    try:
        plan = service.get_plan(plan_id)
    except PlanQueryError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    return ExecutionPlanResponse(
        id=plan.id,
        batch_id=plan.batch_id,
        status=plan.status,
        created_by=plan.created_by,
        created_at=plan.created_at,
        job_count=service.count_jobs(plan_id),
        target_count=service.count_targets(plan_id),
    )


@router.get("/{plan_id}/jobs", response_model=ExecutionJobListResponse)
def list_plan_jobs(
    plan_id: int,
    db: Session = Depends(get_db),
) -> ExecutionJobListResponse:
    """GET /execution-plans/{plan_id}/jobs."""
    service = PlanQueryService(db)
    try:
        jobs = service.list_jobs(plan_id)
    except PlanQueryError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    items: list[ExecutionJobResponse] = []
    for job in jobs:
        items.append(
            ExecutionJobResponse(
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
                target_count=service.count_job_targets(job.id),
            )
        )
    return ExecutionJobListResponse(plan_id=plan_id, total=len(items), items=items)
