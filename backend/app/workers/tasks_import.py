"""Celery tasks for Excel import — implemented in Phase 2."""

from app.workers.celery_app import celery_app


@celery_app.task(name="imports.parse_excel_batch")
def parse_excel_batch(batch_id: int) -> dict[str, int]:
    """Parse uploaded Excel in chunks (openpyxl read_only) — Phase 2."""
    return {"batch_id": batch_id, "status": "not_implemented"}
