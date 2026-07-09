"""Pydantic schemas for AI remediation suggestions (Phase 4)."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class AISuggestionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    raw_record_id: int
    source_check_id: str | None = None
    qualys_control_id: str | None = None
    control_description: str | None = None
    rationale: str | None = None
    remediation: str | None = None
    expected_configuration: str | None = None
    suggested_task_code: str | None = None
    confidence: float | None = None
    risk_level: str | None = None
    target_file: str | None = None
    setting_name: str | None = None
    expected_value: str | None = None
    ansible_module: str | None = None
    generated_playbook: str | None = None
    validation_notes: str | None = None
    safety_warnings: str | None = None
    rollback_strategy: str | None = None
    status: str
    reviewed_by: str | None = None
    reviewed_at: datetime | None = None
    created_at: datetime


class AISuggestionListResponse(BaseModel):
    total: int
    limit: int
    offset: int
    items: list[AISuggestionResponse]


class AIAnalyzeSummaryResponse(BaseModel):
    batch_id: int
    needs_review_records: int
    analyzed: int
    suggestions_created: int
    skipped_non_needs_review: int
    message: str = "AI analysis complete; draft suggestions only (never executed)."


class ReviewActionRequest(BaseModel):
    reviewed_by: str | None = Field(default=None, max_length=255)


class ConvertToCatalogRequest(BaseModel):
    reviewed_by: str | None = Field(default=None, max_length=255)
    task_code: str | None = Field(
        default=None,
        max_length=128,
        description="Optional override; defaults to suggested_task_code",
    )
    title: str | None = Field(default=None, max_length=512)
    enable: bool = Field(
        default=False,
        description="Must stay false unless an admin explicitly enables the catalog entry",
    )


class ConvertToCatalogResponse(BaseModel):
    suggestion_id: int
    catalog_id: int
    task_code: str
    is_enabled: bool
    ansible_playbook_path: str
    message: str = "Catalog entry created disabled; AI playbook is not executable."
