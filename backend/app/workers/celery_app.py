"""Celery application configuration.

Workers run on the same internal Ansible control host in MVP mode.
"""

from celery import Celery

from app.config import get_settings

settings = get_settings()

celery_app = Celery(
    "compliance_remediation",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=[
        "app.workers.tasks_import",
        "app.workers.tasks_plan",
        "app.workers.tasks_execute",
        "app.workers.tasks_ai",
    ],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
)
