"""Dashboard summary schemas (Phase 7)."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.imports import ImportBatchResponse
from app.schemas.plans import ExecutionJobResponse


class DashboardSummaryResponse(BaseModel):
    """Aggregated counters for the internal operator dashboard."""

    mock_mode: bool = True
    import_batches_total: int = 0
    import_batches_by_status: dict[str, int] = Field(default_factory=dict)
    records_total: int = 0
    records_by_validation_status: dict[str, int] = Field(default_factory=dict)
    jobs_total: int = 0
    jobs_by_status: dict[str, int] = Field(default_factory=dict)
    plans_total: int = 0
    suggestions_total: int = 0
    suggestions_by_status: dict[str, int] = Field(default_factory=dict)
    latest_imports: list[ImportBatchResponse] = Field(default_factory=list)
    latest_jobs: list[ExecutionJobResponse] = Field(default_factory=list)
    generated_at: datetime


class ImportBatchListResponse(BaseModel):
    total: int
    limit: int
    offset: int
    items: list[ImportBatchResponse]


class ExecutionPlanListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    batch_id: int
    status: str
    created_by: str | None = None
    created_at: datetime
    job_count: int = 0
    target_count: int = 0


class ExecutionPlanListResponse(BaseModel):
    total: int
    limit: int
    offset: int
    items: list[ExecutionPlanListItem]


class ExecutionJobListAllResponse(BaseModel):
    total: int
    limit: int
    offset: int
    items: list[ExecutionJobResponse]
