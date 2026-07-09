"""Celery tasks for AI analyzer — Phase 4 (mock provider by default).

Optional async wrapper; primary path is synchronous
POST /imports/{batch_id}/ai-analyze-needs-review.
Never executes remediations.
"""

from __future__ import annotations

from app.db.session import SessionLocal
from app.models.raw_import_record import RawImportRecord
from app.services.ai_analyzer import AIAnalyzerService
from app.workers.celery_app import celery_app


@celery_app.task(name="ai.analyze_record")
def analyze_record(raw_record_id: int) -> dict[str, int | str]:
    """Analyze a single NEEDS_REVIEW record into a draft suggestion — never execute."""
    db = SessionLocal()
    try:
        record = db.get(RawImportRecord, raw_record_id)
        if record is None:
            return {"raw_record_id": raw_record_id, "status": "not_found"}
        if record.batch_id is None:
            return {"raw_record_id": raw_record_id, "status": "missing_batch"}

        service = AIAnalyzerService(db)
        suggestion = service.analyze_record(record)
        if suggestion is None:
            return {
                "raw_record_id": raw_record_id,
                "status": "skipped_non_needs_review",
            }
        db.commit()
        return {
            "raw_record_id": raw_record_id,
            "suggestion_id": suggestion.id,
            "status": suggestion.status,
        }
    finally:
        db.close()
