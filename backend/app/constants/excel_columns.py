"""Expected Excel column headers and normalized snake_case names."""

from typing import Final

# Original headers as they appear in the Qualys/MBSS-style export.
EXCEL_REQUIRED_COLUMNS: Final[tuple[str, ...]] = (
    "Sector Name",
    "General Department Name",
    "Department Name",
    "Application Name",
    "Device Name",
    "VM Authentication",
    "VM Integration",
    "Section Manager",
    "Last Scan Date Time",
    "Last Compliance Scan Date Time",
    "Config Scan ID",
    "Overall Status",
    "Criticality",
    "Tracking Method",
    "Evaluation Date",
    "Posture Modified Date",
    "Posture Evidence",
    "MBSS Score",
    "Source Check ID",
    "Control Description",
    "Policy ID",
    "Qualys Control ID",
    "RATIONALE",
    "Remediation",
    "Expected Configuration",
)

# Map original header -> DB / model field name.
EXCEL_COLUMN_MAP: Final[dict[str, str]] = {
    "Sector Name": "sector_name",
    "General Department Name": "general_department_name",
    "Department Name": "department_name",
    "Application Name": "application_name",
    "Device Name": "device_name",
    "VM Authentication": "vm_authentication",
    "VM Integration": "vm_integration",
    "Section Manager": "section_manager",
    "Last Scan Date Time": "last_scan_date_time",
    "Last Compliance Scan Date Time": "last_compliance_scan_date_time",
    "Config Scan ID": "config_scan_id",
    "Overall Status": "overall_status",
    "Criticality": "criticality",
    "Tracking Method": "tracking_method",
    "Evaluation Date": "evaluation_date",
    "Posture Modified Date": "posture_modified_date",
    "Posture Evidence": "posture_evidence",
    "MBSS Score": "mbss_score",
    "Source Check ID": "source_check_id",
    "Control Description": "control_description",
    "Policy ID": "policy_id",
    "Qualys Control ID": "qualys_control_id",
    "RATIONALE": "rationale",
    "Remediation": "remediation",
    "Expected Configuration": "expected_configuration",
}

# Fields used by the rule-based classifier (never executed as commands).
CLASSIFIER_INPUT_FIELDS: Final[tuple[str, ...]] = (
    "qualys_control_id",
    "source_check_id",
    "control_description",
    "rationale",
    "remediation",
    "expected_configuration",
)
