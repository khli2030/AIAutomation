"""Celery tasks for Ansible dry-run and execution — Phase 6.

Safety:
- Never execute Excel Remediation text.
- Never execute AI-generated playbooks.
- Only playbook paths from remediation_catalog are allowed.
"""

from app.workers.celery_app import celery_app


@celery_app.task(name="jobs.dry_run")
def dry_run_job(job_id: int) -> dict[str, int | str]:
    return {"job_id": job_id, "status": "not_implemented"}


@celery_app.task(name="jobs.run")
def run_job(job_id: int) -> dict[str, int | str]:
    return {"job_id": job_id, "status": "not_implemented"}
