"""Pydantic schemas for import batches and raw records (Phase 2)."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ImportBatchResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    original_filename: str
    stored_path: str
    status: str
    total_records: int = 0
    valid_records: int = 0
    invalid_records: int = 0
    total_rows: int | None = None
    processed_rows: int = 0
    uploaded_by: str | None = None
    error_message: str | None = None
    created_at: datetime
    updated_at: datetime


class ImportUploadResponse(BaseModel):
    batch: ImportBatchResponse
    message: str = "Upload accepted; parse job queued."


class RawImportRecordResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    batch_id: int
    row_number: int
    device_name: str | None = None
    overall_status: str | None = None
    criticality: str | None = None
    qualys_control_id: str | None = None
    source_check_id: str | None = None
    control_description: str | None = None
    remediation: str | None = None
    expected_configuration: str | None = None
    task_code: str | None = None
    validation_status: str | None = None
    validation_error: str | None = None
    record_hash: str | None = None
    created_at: datetime


class RawImportRecordListResponse(BaseModel):
    batch_id: int
    total: int
    limit: int
    offset: int
    items: list[RawImportRecordResponse]


class ValidationSummaryResponse(BaseModel):
    batch_id: int
    total_records: int
    ready_for_plan: int
    needs_review: int
    asset_not_found: int
    already_compliant: int
    duplicate: int
    invalid_record: int
    unsupported_control: int
