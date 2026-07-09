"""Celery tasks for execution plan generation — Phase 5."""

from app.workers.celery_app import celery_app


@celery_app.task(name="plans.generate_execution_plan")
def generate_execution_plan(batch_id: int, created_by: str | None = None) -> dict[str, int | str]:
    return {"batch_id": batch_id, "status": "not_implemented"}
