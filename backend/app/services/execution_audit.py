"""Phase 9C execution audit helpers — structured details for audit_logs.

Safety defaults are never changed here. Structured fields live in details JSON.
"""

from __future__ import annotations

from typing import Any

from app.config import Settings
from app.models.execution_job import ExecutionJob


def build_execution_audit_details(
    *,
    event: str,
    job: ExecutionJob,
    settings: Settings,
    old_status: str | None = None,
    new_status: str | None = None,
    batch_id: int | None = None,
    hosts_total: int | None = None,
    hosts_success: int | None = None,
    hosts_failed: int | None = None,
    hosts_skipped: int | None = None,
    hosts_changed: int | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a consistent Phase 9C audit details payload."""
    details: dict[str, Any] = {
        "event": event,
        "plan_id": getattr(job, "plan_id", None),
        "job_id": getattr(job, "id", None),
        "batch_id": batch_id,
        "task_code": getattr(job, "task_code", None),
        "old_status": old_status,
        "new_status": new_status,
        "mock_mode": bool(settings.mock_mode),
        "real_ansible_enabled": bool(settings.real_ansible_enabled),
    }
    if hosts_total is not None:
        details["hosts_total"] = hosts_total
    if hosts_success is not None:
        details["hosts_success"] = hosts_success
    if hosts_failed is not None:
        details["hosts_failed"] = hosts_failed
    if hosts_skipped is not None:
        details["hosts_skipped"] = hosts_skipped
    if hosts_changed is not None:
        details["hosts_changed"] = hosts_changed
    if extra:
        details.update(extra)
    return details


def start_event_for_dry_run(*, old_status: str) -> str:
    """First dry-run vs retry after dry_run_failed."""
    if old_status == "dry_run_failed":
        return "dry_run_retry_started"
    return "dry_run_started"


def completion_event_for_mode(*, mode: str, final_status: str) -> str:
    """Map final job status to Phase 9C completed/failed event names."""
    if mode == "dry_run":
        if final_status == "dry_run_success":
            return "dry_run_completed"
        return "dry_run_failed"
    # apply / run
    if final_status == "success":
        return "run_completed"
    return "run_failed"
