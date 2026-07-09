"""Pydantic schemas for execution plans and jobs (Phase 5)."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ExecutionPlanResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    batch_id: int
    status: str
    created_by: str | None = None
    created_at: datetime
    job_count: int = 0
    target_count: int = 0
    skipped_records: int = 0
    ready_for_plan_records: int = 0
    skipped_missing_catalog: int = 0
    skipped_disabled_catalog: int = 0
    skipped_missing_asset: int = 0
    skipped_missing_asset_metadata: int = 0
    skipped_excluded_status: int = 0


class GeneratePlanResponse(BaseModel):
    plan: ExecutionPlanResponse
    message: str = (
        "Execution plan generated. Jobs are waiting_dry_run; "
        "no Ansible or mock execution was invoked."
    )


class ExecutionJobResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    plan_id: int
    task_code: str
    environment: str | None = None
    criticality: str | None = None
    ansible_group: str | None = None
    status: str
    dry_run_status: str | None = None
    approved_by: str | None = None
    approved_at: datetime | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    target_count: int = 0


class ExecutionJobListResponse(BaseModel):
    plan_id: int
    total: int
    items: list[ExecutionJobResponse]


class ExecutionJobTargetResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    job_id: int
    device_name: str
    ip_address: str | None = None
    ansible_group: str | None = None
    status: str


class JobReviewRequest(BaseModel):
    reviewed_by: str | None = Field(default=None, max_length=255)


class JobExecutionSummaryResponse(BaseModel):
    job_id: int
    mode: str
    mock_mode: bool
    status: str
    dry_run_status: str | None = None
    hosts_total: int
    hosts_success: int
    hosts_failed: int
    hosts_changed: int
    hosts_skipped: int
    message: str = "Mock execution only — no ansible-runner, subprocess, or SSH."


class JobResultResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    job_id: int
    result_type: str
    device_name: str
    status: str
    changed: bool
    skipped: bool
    stdout: str | None = None
    stderr: str | None = None
    return_code: int | None = None
    created_at: datetime


class JobResultsListResponse(BaseModel):
    job_id: int
    job_status: str
    dry_run_status: str | None = None
    result_type_filter: str | None = None
    total: int
    items: list[JobResultResponse]
