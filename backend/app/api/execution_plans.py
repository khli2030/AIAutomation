"""Execution plan endpoints — Phase 5 + Phase 7 list + Phase 9C audit/summary/CSV."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth import READ_ROLES, AuthContext, require_roles
from app.config import Settings, get_settings
from app.db.session import get_db
from app.models.execution_plan import ExecutionPlan
from app.schemas.dashboard import ExecutionPlanListItem, ExecutionPlanListResponse
from app.schemas.plans import (
    ExecutionJobListResponse,
    ExecutionJobResponse,
    ExecutionPlanResponse,
    PlanAuditEventResponse,
    PlanAuditListResponse,
    PlanExecutionSummaryResponse,
)
from app.services.plan_query import PlanQueryError, PlanQueryService
from app.services.plan_reporting import PlanReportingService

router = APIRouter()


@router.get("", response_model=ExecutionPlanListResponse)
@router.get("/", response_model=ExecutionPlanListResponse, include_in_schema=False)
def list_execution_plans(
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    batch_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
    auth: AuthContext = require_roles(*READ_ROLES),
) -> ExecutionPlanListResponse:
    """List execution plans newest-first (Phase 7)."""
    filters = []
    if batch_id is not None:
        filters.append(ExecutionPlan.batch_id == batch_id)

    count_q = select(func.count()).select_from(ExecutionPlan)
    query = select(ExecutionPlan)
    if filters:
        count_q = count_q.where(*filters)
        query = query.where(*filters)

    total = db.scalar(count_q) or 0
    plans = db.scalars(
        query.order_by(ExecutionPlan.id.desc()).offset(offset).limit(limit)
    ).all()

    service = PlanQueryService(db)
    items: list[ExecutionPlanListItem] = []
    for plan in plans:
        items.append(
            ExecutionPlanListItem(
                id=plan.id,
                batch_id=plan.batch_id,
                status=plan.status,
                created_by=plan.created_by,
                created_at=plan.created_at,
                job_count=service.count_jobs(plan.id),
                target_count=service.count_targets(plan.id),
            )
        )
    return ExecutionPlanListResponse(
        total=int(total), limit=limit, offset=offset, items=items
    )


@router.get("/{plan_id}", response_model=ExecutionPlanResponse)
def get_execution_plan(
    plan_id: int,
    db: Session = Depends(get_db),
    auth: AuthContext = require_roles(*READ_ROLES),
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
    auth: AuthContext = require_roles(*READ_ROLES),
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


@router.get("/{plan_id}/audit", response_model=PlanAuditListResponse)
def list_plan_audit(
    plan_id: int,
    db: Session = Depends(get_db),
    auth: AuthContext = require_roles(*READ_ROLES),
    settings: Settings = Depends(get_settings),
) -> PlanAuditListResponse:
    """GET /execution-plans/{plan_id}/audit — newest-first execution audit timeline."""
    _ = auth
    service = PlanReportingService(db, settings=settings)
    try:
        events = service.list_audit_events(plan_id)
    except PlanQueryError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return PlanAuditListResponse(
        plan_id=plan_id,
        total=len(events),
        items=[
            PlanAuditEventResponse(
                id=e.id,
                created_at=e.created_at,
                actor=e.actor,
                role=e.role,
                action=e.action,
                event=e.event,
                plan_id=e.plan_id,
                job_id=e.job_id,
                batch_id=e.batch_id,
                task_code=e.task_code,
                old_status=e.old_status,
                new_status=e.new_status,
                mock_mode=e.mock_mode,
                real_ansible_enabled=e.real_ansible_enabled,
                hosts_total=e.hosts_total,
                hosts_success=e.hosts_success,
                hosts_failed=e.hosts_failed,
                hosts_skipped=e.hosts_skipped,
                hosts_changed=e.hosts_changed,
            )
            for e in events
        ],
    )


@router.get("/{plan_id}/summary", response_model=PlanExecutionSummaryResponse)
def get_plan_summary(
    plan_id: int,
    db: Session = Depends(get_db),
    auth: AuthContext = require_roles(*READ_ROLES),
    settings: Settings = Depends(get_settings),
) -> PlanExecutionSummaryResponse:
    """GET /execution-plans/{plan_id}/summary — job/result counters for operators."""
    _ = auth
    service = PlanReportingService(db, settings=settings)
    try:
        summary = service.build_summary(plan_id)
    except PlanQueryError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return PlanExecutionSummaryResponse(
        plan_id=summary.plan_id,
        batch_id=summary.batch_id,
        total_jobs=summary.total_jobs,
        jobs_by_status=summary.jobs_by_status,
        total_targets=summary.total_targets,
        dry_run_results_by_status=summary.dry_run_results_by_status,
        run_results_by_status=summary.run_results_by_status,
        failed_task_codes=summary.failed_task_codes,
        skipped_task_codes=summary.skipped_task_codes,
        mock_mode=summary.mock_mode,
        real_ansible_enabled=summary.real_ansible_enabled,
    )


@router.get("/{plan_id}/results.csv")
def export_plan_results_csv(
    plan_id: int,
    db: Session = Depends(get_db),
    auth: AuthContext = require_roles(*READ_ROLES),
    settings: Settings = Depends(get_settings),
) -> Response:
    """GET /execution-plans/{plan_id}/results.csv — per-host results export."""
    _ = auth
    service = PlanReportingService(db, settings=settings)
    try:
        csv_text = service.results_csv(plan_id)
    except PlanQueryError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return Response(
        content=csv_text,
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="plan-{plan_id}-results.csv"'
        },
    )
