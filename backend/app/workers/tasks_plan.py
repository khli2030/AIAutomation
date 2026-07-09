"""Celery tasks for execution plan generation — Phase 5.

Optional async wrapper; primary path is synchronous
POST /imports/{batch_id}/generate-plan.
Never executes Ansible / MOCK.
"""

from __future__ import annotations

from app.db.session import SessionLocal
from app.services.plan_generator import PlanGeneratorService
from app.workers.celery_app import celery_app


@celery_app.task(name="plans.generate_execution_plan")
def generate_execution_plan(batch_id: int, created_by: str | None = None) -> dict[str, int | str]:
    """Generate plan/jobs/targets for READY_FOR_PLAN records — never execute."""
    db = SessionLocal()
    try:
        result = PlanGeneratorService(db).generate_plan(batch_id, created_by=created_by)
        return {
            "batch_id": batch_id,
            "plan_id": result.plan.id,
            "status": result.plan.status,
            "job_count": result.job_count,
            "target_count": result.target_count,
        }
    except ValueError as exc:
        return {"batch_id": batch_id, "status": "error", "detail": str(exc)}
    finally:
        db.close()
