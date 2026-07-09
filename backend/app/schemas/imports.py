"""Pydantic schemas for import batches and raw records."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ImportBatchResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    original_filename: str
    stored_path: str
    status: str
    total_rows: int | None = None
    processed_rows: int
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
    sector_name: str | None = None
    general_department_name: str | None = None
    department_name: str | None = None
    application_name: str | None = None
    device_name: str | None = None
    vm_authentication: str | None = None
    vm_integration: str | None = None
    section_manager: str | None = None
    last_scan_date_time: str | None = None
    last_compliance_scan_date_time: str | None = None
    config_scan_id: str | None = None
    overall_status: str | None = None
    criticality: str | None = None
    tracking_method: str | None = None
    evaluation_date: str | None = None
    posture_modified_date: str | None = None
    posture_evidence: str | None = None
    mbss_score: str | None = None
    source_check_id: str | None = None
    control_description: str | None = None
    policy_id: str | None = None
    qualys_control_id: str | None = None
    rationale: str | None = None
    remediation: str | None = None
    expected_configuration: str | None = None
    normalized_status: str | None = None
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


class ParseJobResult(BaseModel):
    batch_id: int
    status: str
    total_rows: int = 0
    processed_rows: int = 0
    skipped_empty_rows: int = 0
    error_message: str | None = None
