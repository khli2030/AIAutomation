"""Phase 9C plan summary, audit listing, and CSV export."""

from __future__ import annotations

import csv
import io
import json
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.models.audit_log import AuditLog
from app.models.execution_job import ExecutionJob
from app.models.execution_plan import ExecutionPlan
from app.models.job_result import JobResult
from app.services.plan_query import PlanQueryError, PlanQueryService


PHASE9C_EVENTS: frozenset[str] = frozenset(
    {
        "dry_run_started",
        "dry_run_completed",
        "dry_run_failed",
        "dry_run_retry_started",
        "approved",
        "rejected",
        "run_started",
        "run_completed",
        "run_failed",
        # Keep real-path events visible in plan audit timeline.
        "real_dry_run_started",
        "real_dry_run_completed",
        "real_dry_run_failed",
        "real_dry_run_blocked",
    }
)


@dataclass
class PlanAuditEvent:
    id: int
    created_at: datetime
    actor: str
    role: str | None
    action: str
    event: str
    plan_id: int | None
    job_id: int | None
    batch_id: int | None
    task_code: str | None
    old_status: str | None
    new_status: str | None
    mock_mode: bool | None
    real_ansible_enabled: bool | None
    hosts_total: int | None
    hosts_success: int | None
    hosts_failed: int | None
    hosts_skipped: int | None
    hosts_changed: int | None
    details: dict[str, Any]


@dataclass
class PlanExecutionSummary:
    plan_id: int
    batch_id: int
    total_jobs: int
    jobs_by_status: dict[str, int]
    total_targets: int
    dry_run_results_by_status: dict[str, int]
    run_results_by_status: dict[str, int]
    failed_task_codes: list[str]
    skipped_task_codes: list[str]
    mock_mode: bool
    real_ansible_enabled: bool


class PlanReportingService:
    def __init__(self, db: Session, settings: Settings | None = None) -> None:
        self.db = db
        self.settings = settings or get_settings()
        self.plans = PlanQueryService(db)

    def _plan(self, plan_id: int) -> ExecutionPlan:
        return self.plans.get_plan(plan_id)

    def list_audit_events(self, plan_id: int) -> list[PlanAuditEvent]:
        plan = self._plan(plan_id)
        job_ids = list(
            self.db.scalars(
                select(ExecutionJob.id).where(ExecutionJob.plan_id == plan_id)
            ).all()
        )
        job_id_strs = {str(i) for i in job_ids}

        # Load recent audits for execution_job entities in this plan.
        rows = self.db.scalars(
            select(AuditLog)
            .where(AuditLog.entity_type == "execution_job")
            .order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
            .limit(5000)
        ).all()

        events: list[PlanAuditEvent] = []
        for row in rows:
            if row.entity_id not in job_id_strs:
                continue
            details = _parse_details(row.details)
            # Prefer explicit plan_id in details; fall back to this plan.
            detail_plan = details.get("plan_id")
            if detail_plan is not None and int(detail_plan) != plan_id:
                continue
            event_name = str(details.get("event") or row.action or "")
            if event_name and event_name not in PHASE9C_EVENTS and event_name not in {
                "started",
                "completed",
                "approve",
                "reject",
            }:
                # Still include legacy started/completed for visibility.
                pass
            events.append(
                PlanAuditEvent(
                    id=row.id,
                    created_at=row.created_at,
                    actor=row.actor,
                    role=(
                        str(details.get("auth_role"))
                        if details.get("auth_role") is not None
                        else None
                    ),
                    action=row.action,
                    event=event_name or row.action,
                    plan_id=int(detail_plan) if detail_plan is not None else plan_id,
                    job_id=_as_int(details.get("job_id") or row.entity_id),
                    batch_id=_as_int(details.get("batch_id") or plan.batch_id),
                    task_code=(
                        str(details["task_code"])
                        if details.get("task_code") is not None
                        else None
                    ),
                    old_status=_as_str(details.get("old_status")),
                    new_status=_as_str(
                        details.get("new_status") or details.get("status")
                    ),
                    mock_mode=_as_bool(details.get("mock_mode")),
                    real_ansible_enabled=_as_bool(
                        details.get("real_ansible_enabled")
                    ),
                    hosts_total=_as_int(details.get("hosts_total")),
                    hosts_success=_as_int(details.get("hosts_success")),
                    hosts_failed=_as_int(details.get("hosts_failed")),
                    hosts_skipped=_as_int(details.get("hosts_skipped")),
                    hosts_changed=_as_int(details.get("hosts_changed")),
                    details=details,
                )
            )
        return events

    def build_summary(self, plan_id: int) -> PlanExecutionSummary:
        plan = self._plan(plan_id)
        jobs = self.plans.list_jobs(plan_id)
        jobs_by_status = dict(Counter(j.status for j in jobs))
        total_targets = self.plans.count_targets(plan_id)

        job_ids = [j.id for j in jobs]
        dry_counts: Counter[str] = Counter()
        run_counts: Counter[str] = Counter()
        failed_codes: set[str] = set()
        skipped_codes: set[str] = set()

        if job_ids:
            results = self.db.scalars(
                select(JobResult).where(JobResult.job_id.in_(job_ids))
            ).all()
            job_by_id = {j.id: j for j in jobs}
            for r in results:
                bucket = dry_counts if r.result_type == "dry_run" else run_counts
                bucket[r.status] += 1
                job = job_by_id.get(r.job_id)
                if job is None:
                    continue
                st = (r.status or "").lower()
                if "fail" in st or st == "unreachable":
                    failed_codes.add(job.task_code)
                if r.skipped or "skip" in st:
                    skipped_codes.add(job.task_code)

        return PlanExecutionSummary(
            plan_id=plan.id,
            batch_id=plan.batch_id,
            total_jobs=len(jobs),
            jobs_by_status=jobs_by_status,
            total_targets=total_targets,
            dry_run_results_by_status=dict(dry_counts),
            run_results_by_status=dict(run_counts),
            failed_task_codes=sorted(failed_codes),
            skipped_task_codes=sorted(skipped_codes),
            mock_mode=bool(self.settings.mock_mode),
            real_ansible_enabled=bool(self.settings.real_ansible_enabled),
        )

    def results_csv(self, plan_id: int) -> str:
        self._plan(plan_id)
        jobs = self.plans.list_jobs(plan_id)
        job_by_id = {j.id: j for j in jobs}
        job_ids = list(job_by_id)
        rows: list[JobResult] = []
        if job_ids:
            rows = list(
                self.db.scalars(
                    select(JobResult)
                    .where(JobResult.job_id.in_(job_ids))
                    .order_by(JobResult.id.asc())
                ).all()
            )

        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(
            [
                "plan_id",
                "job_id",
                "task_code",
                "host",
                "result_type",
                "status",
                "changed",
                "stdout",
                "stderr",
                "message",
                "created_at",
            ]
        )
        for r in rows:
            job = job_by_id.get(r.job_id)
            message = (r.stderr or r.stdout or "")[:500]
            writer.writerow(
                [
                    plan_id,
                    r.job_id,
                    job.task_code if job else "",
                    r.device_name,
                    r.result_type,
                    r.status,
                    r.changed,
                    r.stdout or "",
                    r.stderr or "",
                    message,
                    r.created_at.isoformat() if r.created_at else "",
                ]
            )
        return buf.getvalue()


def _parse_details(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        data = json.loads(raw)
    except (TypeError, ValueError, json.JSONDecodeError):
        return {"message": raw}
    return data if isinstance(data, dict) else {"message": data}


def _as_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _as_str(value: Any) -> str | None:
    if value is None:
        return None
    return str(value)


def _as_bool(value: Any) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.lower() in {"1", "true", "yes"}
    return bool(value)


__all__ = [
    "PHASE9C_EVENTS",
    "PlanAuditEvent",
    "PlanExecutionSummary",
    "PlanReportingService",
    "PlanQueryError",
]
