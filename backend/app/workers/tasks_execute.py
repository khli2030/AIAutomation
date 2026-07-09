"""Celery tasks for Ansible dry-run and execution.

Delegates to AnsibleExecutionService.
When MOCK_MODE=true, no ansible-runner or shell commands are used.
"""

from __future__ import annotations

import logging

from app.db.session import SessionLocal
from app.services.ansible_execution import (
    AnsibleExecutionError,
    AnsibleExecutionService,
    summary_to_dict,
)
from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(name="jobs.dry_run")
def dry_run_job(job_id: int) -> dict[str, object]:
    db = SessionLocal()
    try:
        service = AnsibleExecutionService(db)
        summary = service.dry_run_job(job_id)
        return summary_to_dict(summary)
    except AnsibleExecutionError as exc:
        logger.warning("dry_run_job failed job_id=%s: %s", job_id, exc)
        return {"job_id": job_id, "status": "error", "error": str(exc), "mock_mode": True}
    except Exception as exc:  # noqa: BLE001
        logger.exception("dry_run_job unexpected error job_id=%s", job_id)
        db.rollback()
        return {"job_id": job_id, "status": "error", "error": str(exc)}
    finally:
        db.close()


@celery_app.task(name="jobs.run")
def run_job(job_id: int) -> dict[str, object]:
    db = SessionLocal()
    try:
        service = AnsibleExecutionService(db)
        summary = service.run_job(job_id)
        return summary_to_dict(summary)
    except AnsibleExecutionError as exc:
        logger.warning("run_job failed job_id=%s: %s", job_id, exc)
        return {"job_id": job_id, "status": "error", "error": str(exc)}
    except Exception as exc:  # noqa: BLE001
        logger.exception("run_job unexpected error job_id=%s", job_id)
        db.rollback()
        return {"job_id": job_id, "status": "error", "error": str(exc)}
    finally:
        db.close()
