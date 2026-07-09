"""Phase 3 validation + rule-based classification for raw_import_records.

Does NOT:
- call Ansible / MOCK execution
- generate execution plans
- invoke AI Analyzer
"""

from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.classifiers.rules import classify_record
from app.constants.record_status import RecordStatus
from app.constants.task_codes import NON_EXECUTABLE_TASK_CODES, TaskCode
from app.models.asset import Asset
from app.models.import_batch import ImportBatch
from app.models.raw_import_record import RawImportRecord
from app.services.audit import write_audit_log
from app.services.record_hash import compute_record_hash

COMPLIANT_STATUS_TOKENS: frozenset[str] = frozenset(
    {
        "passed",
        "pass",
        "compliant",
        "success",
        "successful",
        "not applicable",
        "not_applicable",
        "n/a",
        "na",
    }
)


@dataclass
class ValidationSummary:
    batch_id: int
    total_records: int = 0
    ready_for_plan: int = 0
    needs_review: int = 0
    asset_not_found: int = 0
    already_compliant: int = 0
    duplicate: int = 0
    invalid_record: int = 0
    unsupported_control: int = 0

    def to_dict(self) -> dict[str, int]:
        return asdict(self)


def _normalize_overall_status(value: str | None) -> str:
    return " ".join((value or "").strip().lower().split())


def _is_already_compliant(overall_status: str | None) -> bool:
    normalized = _normalize_overall_status(overall_status)
    if not normalized:
        return False
    if normalized in COMPLIANT_STATUS_TOKENS:
        return True
    for token in ("passed", "compliant", "success", "not applicable"):
        if token in normalized:
            return True
    return False


def _load_active_device_names(db: Session) -> set[str]:
    rows = db.scalars(select(Asset.device_name).where(Asset.is_active.is_(True))).all()
    return {(name or "").strip().lower() for name in rows if name}


class RecordValidationService:
    """Validate and classify all raw_import_records for a batch."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def validate_batch(
        self,
        batch_id: int,
        *,
        actor: str = "system",
        role: str | None = None,
    ) -> ValidationSummary:
        batch = self.db.get(ImportBatch, batch_id)
        if batch is None:
            raise ValueError(f"Import batch {batch_id} not found")

        records = self.db.scalars(
            select(RawImportRecord)
            .where(RawImportRecord.batch_id == batch_id)
            .order_by(RawImportRecord.row_number.asc(), RawImportRecord.id.asc())
        ).all()

        active_devices = _load_active_device_names(self.db)
        seen_hashes: set[str] = set()
        counts: Counter[str] = Counter()

        write_audit_log(
            self.db,
            actor=actor,
            action="classify",
            entity_type="import_batch",
            entity_id=batch_id,
            role=role,
            details={"event": "validate_started", "record_count": len(records)},
        )

        for record in records:
            status, task_code, error = self._validate_one(
                record=record,
                active_devices=active_devices,
                seen_hashes=seen_hashes,
            )
            record.validation_status = status
            record.normalized_status = status
            record.task_code = task_code
            record.validation_error = error
            record.record_hash = compute_record_hash(
                device_name=record.device_name,
                qualys_control_id=record.qualys_control_id,
                source_check_id=record.source_check_id,
                config_scan_id=record.config_scan_id,
                expected_configuration=record.expected_configuration,
            )
            counts[status] += 1

        summary = ValidationSummary(
            batch_id=batch_id,
            total_records=len(records),
            ready_for_plan=counts[RecordStatus.READY_FOR_PLAN.value],
            needs_review=counts[RecordStatus.NEEDS_REVIEW.value],
            asset_not_found=counts[RecordStatus.ASSET_NOT_FOUND.value],
            already_compliant=counts[RecordStatus.ALREADY_COMPLIANT.value],
            duplicate=counts[RecordStatus.DUPLICATE.value],
            invalid_record=counts[RecordStatus.INVALID_RECORD.value],
            unsupported_control=counts[RecordStatus.UNSUPPORTED_CONTROL.value],
        )

        write_audit_log(
            self.db,
            actor=actor,
            action="classify",
            entity_type="import_batch",
            entity_id=batch_id,
            role=role,
            details={"event": "validate_completed", **summary.to_dict()},
        )
        self.db.commit()
        return summary

    def _validate_one(
        self,
        *,
        record: RawImportRecord,
        active_devices: set[str],
        seen_hashes: set[str],
    ) -> tuple[str, str | None, str | None]:
        device = (record.device_name or "").strip()
        if not device:
            return RecordStatus.INVALID_RECORD.value, None, "Missing Device Name"

        record_hash = compute_record_hash(
            device_name=record.device_name,
            qualys_control_id=record.qualys_control_id,
            source_check_id=record.source_check_id,
            config_scan_id=record.config_scan_id,
            expected_configuration=record.expected_configuration,
        )
        classification = classify_record(record)
        task_code = classification.task_code

        # Duplicate detection after hash generation (within batch, first wins).
        if record_hash in seen_hashes:
            return (
                RecordStatus.DUPLICATE.value,
                task_code,
                "Duplicate record_hash within batch",
            )
        seen_hashes.add(record_hash)

        if _is_already_compliant(record.overall_status):
            return RecordStatus.ALREADY_COMPLIANT.value, task_code, None

        if device.lower() not in active_devices:
            return (
                RecordStatus.ASSET_NOT_FOUND.value,
                task_code,
                f"Device Name not found in assets: {device}",
            )

        if task_code == TaskCode.UNSUPPORTED_CONTROL.value:
            return (
                RecordStatus.UNSUPPORTED_CONTROL.value,
                task_code,
                "Control cannot be safely automated",
            )

        if (
            not classification.is_recognized
            or task_code in NON_EXECUTABLE_TASK_CODES
            or task_code == TaskCode.NEEDS_REVIEW.value
        ):
            return (
                RecordStatus.NEEDS_REVIEW.value,
                TaskCode.NEEDS_REVIEW.value,
                "Unknown or unrecognized remediation control",
            )

        # Recognized task_code + asset exists + non-compliant → ready for plan.
        return RecordStatus.READY_FOR_PLAN.value, task_code, None
