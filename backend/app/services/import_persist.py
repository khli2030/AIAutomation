"""Persist parsed Excel chunks into raw_import_records (Phase 2).

No remediation classification / execution-plan generation in this phase.
Remediation text is stored only — never executed.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.raw_import_record import RawImportRecord
from app.services.excel_parser import ParsedExcelRow
from app.services.record_hash import compute_record_hash


def insert_parsed_chunk(
    db: Session,
    *,
    batch_id: int,
    chunk: list[ParsedExcelRow],
) -> tuple[int, int]:
    """Insert one chunk.

    Returns (valid_count, invalid_count).
    Structural invalid = missing Device Name (still stored for review).
    """
    if not chunk:
        return 0, 0

    valid = 0
    invalid = 0
    records: list[RawImportRecord] = []

    for row in chunk:
        values = row.values
        device_name = values.get("device_name")
        is_valid = bool(device_name and str(device_name).strip())
        if is_valid:
            valid += 1
            validation_status = None
            validation_error = None
        else:
            invalid += 1
            validation_status = "INVALID_RECORD"
            validation_error = "Missing Device Name"

        record_hash = compute_record_hash(
            device_name=device_name,
            qualys_control_id=values.get("qualys_control_id"),
            source_check_id=values.get("source_check_id"),
            config_scan_id=values.get("config_scan_id"),
            expected_configuration=values.get("expected_configuration"),
        )
        records.append(
            RawImportRecord(
                batch_id=batch_id,
                row_number=row.row_number,
                sector_name=values.get("sector_name"),
                general_department_name=values.get("general_department_name"),
                department_name=values.get("department_name"),
                application_name=values.get("application_name"),
                device_name=device_name,
                vm_authentication=values.get("vm_authentication"),
                vm_integration=values.get("vm_integration"),
                section_manager=values.get("section_manager"),
                last_scan_date_time=values.get("last_scan_date_time"),
                last_compliance_scan_date_time=values.get(
                    "last_compliance_scan_date_time"
                ),
                config_scan_id=values.get("config_scan_id"),
                overall_status=values.get("overall_status"),
                criticality=values.get("criticality"),
                tracking_method=values.get("tracking_method"),
                evaluation_date=values.get("evaluation_date"),
                posture_modified_date=values.get("posture_modified_date"),
                posture_evidence=values.get("posture_evidence"),
                mbss_score=values.get("mbss_score"),
                source_check_id=values.get("source_check_id"),
                control_description=values.get("control_description"),
                policy_id=values.get("policy_id"),
                qualys_control_id=values.get("qualys_control_id"),
                rationale=values.get("rationale"),
                remediation=values.get("remediation"),
                expected_configuration=values.get("expected_configuration"),
                # Classification deferred to Phase 3:
                normalized_status=None,
                task_code=None,
                validation_status=validation_status,
                validation_error=validation_error,
                record_hash=record_hash,
            )
        )

    db.add_all(records)
    db.flush()
    return valid, invalid
