"""Read helpers for execution plans and jobs (Phase 5)."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.execution_job import ExecutionJob
from app.models.execution_job_target import ExecutionJobTarget
from app.models.execution_plan import ExecutionPlan


class PlanQueryError(ValueError):
    """Plan/job not found."""


class PlanQueryService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_plan(self, plan_id: int) -> ExecutionPlan:
        plan = self.db.get(ExecutionPlan, plan_id)
        if plan is None:
            raise PlanQueryError(f"Execution plan {plan_id} not found")
        return plan

    def count_jobs(self, plan_id: int) -> int:
        return int(
            self.db.scalar(
                select(func.count()).select_from(ExecutionJob).where(
                    ExecutionJob.plan_id == plan_id
                )
            )
            or 0
        )

    def count_targets(self, plan_id: int) -> int:
        return int(
            self.db.scalar(
                select(func.count())
                .select_from(ExecutionJobTarget)
                .join(ExecutionJob, ExecutionJobTarget.job_id == ExecutionJob.id)
                .where(ExecutionJob.plan_id == plan_id)
            )
            or 0
        )

    def list_jobs(self, plan_id: int) -> list[ExecutionJob]:
        self.get_plan(plan_id)
        return list(
            self.db.scalars(
                select(ExecutionJob)
                .where(ExecutionJob.plan_id == plan_id)
                .order_by(ExecutionJob.id.asc())
            ).all()
        )

    def count_job_targets(self, job_id: int) -> int:
        return int(
            self.db.scalar(
                select(func.count()).select_from(ExecutionJobTarget).where(
                    ExecutionJobTarget.job_id == job_id
                )
            )
            or 0
        )
