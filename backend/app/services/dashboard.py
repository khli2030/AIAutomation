"""Dashboard aggregation — read-only counters for Phase 7 UI.

Never calls Ansible / MOCK execution / subprocess / SSH.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.models.ai_remediation_suggestion import AIRemediationSuggestion
from app.models.execution_job import ExecutionJob
from app.models.execution_plan import ExecutionPlan
from app.models.import_batch import ImportBatch
from app.models.raw_import_record import RawImportRecord
from app.schemas.dashboard import DashboardSummaryResponse
from app.schemas.imports import ImportBatchResponse
from app.schemas.plans import ExecutionJobResponse
from app.services.plan_query import PlanQueryService


def _count_by(db: Session, column) -> dict[str, int]:
    rows = db.execute(select(column, func.count()).group_by(column)).all()
    return {str(key or "unknown"): int(count) for key, count in rows}


class DashboardService:
    def __init__(self, db: Session, settings: Settings | None = None) -> None:
        self.db = db
        self.settings = settings or get_settings()

    def summary(self, *, latest_limit: int = 10) -> DashboardSummaryResponse:
        pq = PlanQueryService(self.db)

        imports_total = int(
            self.db.scalar(select(func.count()).select_from(ImportBatch)) or 0
        )
        records_total = int(
            self.db.scalar(select(func.count()).select_from(RawImportRecord)) or 0
        )
        jobs_total = int(
            self.db.scalar(select(func.count()).select_from(ExecutionJob)) or 0
        )
        plans_total = int(
            self.db.scalar(select(func.count()).select_from(ExecutionPlan)) or 0
        )
        suggestions_total = int(
            self.db.scalar(select(func.count()).select_from(AIRemediationSuggestion))
            or 0
        )

        latest_batches = list(
            self.db.scalars(
                select(ImportBatch).order_by(ImportBatch.id.desc()).limit(latest_limit)
            ).all()
        )
        latest_job_rows = list(
            self.db.scalars(
                select(ExecutionJob).order_by(ExecutionJob.id.desc()).limit(latest_limit)
            ).all()
        )

        latest_jobs: list[ExecutionJobResponse] = []
        for job in latest_job_rows:
            latest_jobs.append(
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
                    target_count=pq.count_job_targets(job.id),
                )
            )

        return DashboardSummaryResponse(
            mock_mode=bool(self.settings.mock_mode),
            import_batches_total=imports_total,
            import_batches_by_status=_count_by(self.db, ImportBatch.status),
            records_total=records_total,
            records_by_validation_status=_count_by(
                self.db, RawImportRecord.validation_status
            ),
            jobs_total=jobs_total,
            jobs_by_status=_count_by(self.db, ExecutionJob.status),
            plans_total=plans_total,
            suggestions_total=suggestions_total,
            suggestions_by_status=_count_by(
                self.db, AIRemediationSuggestion.status
            ),
            latest_imports=[ImportBatchResponse.model_validate(b) for b in latest_batches],
            latest_jobs=latest_jobs,
            generated_at=datetime.now(UTC),
        )
