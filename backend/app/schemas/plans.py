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
