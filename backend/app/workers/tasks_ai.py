"""Celery tasks for AI analyzer — Phase 4 (mock provider by default)."""

from app.workers.celery_app import celery_app


@celery_app.task(name="ai.analyze_record")
def analyze_record(raw_record_id: int) -> dict[str, int | str]:
    """Analyze unknown remediation; store draft suggestion only — never execute."""
    return {"raw_record_id": raw_record_id, "status": "not_implemented"}
