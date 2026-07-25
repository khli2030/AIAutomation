"""Phase 5 job approve / reject (no execution).

Rules:
- approve blocked unless status is exactly dry_run_success.
- waiting_dry_run → approve returns error (dry-run not implemented yet).
- reject allowed for waiting_dry_run, dry_run_failed, waiting_approval.
- Never calls Ansible / MOCK / subprocess / SSH.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.constants.job_status import JobStatus
from app.models.execution_job import ExecutionJob
from app.models.execution_plan import ExecutionPlan
from app.services.audit import write_audit_log
from app.services.execution_audit import build_execution_audit_details

# Approve is only allowed when dry-run has succeeded (exact status).
APPROVABLE_STATUSES: frozenset[str] = frozenset(
    {
        JobStatus.DRY_RUN_SUCCESS.value,
    }
)

REJECTABLE_STATUSES: frozenset[str] = frozenset(
    {
        JobStatus.WAITING_DRY_RUN.value,
        JobStatus.DRY_RUN_FAILED.value,
        JobStatus.WAITING_APPROVAL.value,
    }
)


class JobApprovalError(ValueError):
    """Domain error for job approve/reject."""


class JobApprovalService:
    def __init__(self, db: Session, settings: Settings | None = None) -> None:
        self.db = db
        self.settings = settings or get_settings()

    def get_job(self, job_id: int) -> ExecutionJob:
        job = self.db.get(ExecutionJob, job_id)
        if job is None:
            raise JobApprovalError(f"Execution job {job_id} not found")
        return job

    def _batch_id(self, job: ExecutionJob) -> int | None:
        plan = self.db.get(ExecutionPlan, job.plan_id)
        if plan is None:
            return None
        batch_id = getattr(plan, "batch_id", None)
        if batch_id is None:
            return None
        try:
            return int(batch_id)
        except (TypeError, ValueError):
            return None

    def approve(
        self,
        job_id: int,
        *,
        reviewed_by: str | None = None,
        role: str | None = None,
    ) -> ExecutionJob:
        job = self.get_job(job_id)
        old_status = job.status

        if job.status == JobStatus.WAITING_DRY_RUN.value:
            raise JobApprovalError(
                "Approve is blocked until dry-run succeeds "
                "(job status is waiting_dry_run)"
            )
        if job.status not in APPROVABLE_STATUSES:
            raise JobApprovalError(
                f"Approve requires job status=dry_run_success "
                f"(current status={job.status})"
            )

        job.status = JobStatus.APPROVED.value
        job.approved_by = reviewed_by or "admin"
        job.approved_at = datetime.now(UTC)

        write_audit_log(
            self.db,
            actor=job.approved_by,
            action="approve",
            entity_type="execution_job",
            entity_id=job.id,
            role=role,
            details=build_execution_audit_details(
                event="approved",
                job=job,
                settings=self.settings,
                old_status=old_status,
                new_status=job.status,
                batch_id=self._batch_id(job),
            ),
        )
        self.db.commit()
        self.db.refresh(job)
        return job

    def reject(
        self,
        job_id: int,
        *,
        reviewed_by: str | None = None,
        role: str | None = None,
    ) -> ExecutionJob:
        job = self.get_job(job_id)
        old_status = job.status

        if job.status not in REJECTABLE_STATUSES:
            raise JobApprovalError(
                "Reject allowed only for waiting_dry_run, dry_run_failed, "
                f"or waiting_approval (current status={job.status})"
            )

        actor = reviewed_by or "admin"
        job.status = JobStatus.REJECTED.value
        job.approved_by = actor
        job.approved_at = datetime.now(UTC)

        write_audit_log(
            self.db,
            actor=actor,
            action="reject",
            entity_type="execution_job",
            entity_id=job.id,
            role=role,
            details=build_execution_audit_details(
                event="rejected",
                job=job,
                settings=self.settings,
                old_status=old_status,
                new_status=job.status,
                batch_id=self._batch_id(job),
            ),
        )
        self.db.commit()
        self.db.refresh(job)
        return job
