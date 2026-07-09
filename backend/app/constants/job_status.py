"""Execution job lifecycle statuses."""

from enum import StrEnum


class JobStatus(StrEnum):
    DRAFT = "draft"
    WAITING_DRY_RUN = "waiting_dry_run"
    DRY_RUN_RUNNING = "dry_run_running"
    DRY_RUN_SUCCESS = "dry_run_success"
    DRY_RUN_FAILED = "dry_run_failed"
    WAITING_APPROVAL = "waiting_approval"
    APPROVED = "approved"
    REJECTED = "rejected"
    QUEUED = "queued"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    PARTIALLY_FAILED = "partially_failed"
