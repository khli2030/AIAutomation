"""Phase 3 tests: validation statuses and rule-based classifier."""

from __future__ import annotations

import ast
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.classifiers.rules import classify_record
from app.constants.record_status import RecordStatus
from app.constants.task_codes import TaskCode
from app.services.record_hash import compute_record_hash
from app.services.validator import RecordValidationService, _is_already_compliant

READY = RecordStatus.READY_FOR_PLAN.value
FORBIDDEN_IMPORT_ROOTS = {
    "ansible_execution",
    "real_ansible_runner",
    "subprocess",
    "ansible_runner",
    "openai",
}


def _finding(**kwargs: str | None) -> SimpleNamespace:
    base = {
        "qualys_control_id": None,
        "source_check_id": None,
        "control_description": None,
        "rationale": None,
        "remediation": None,
        "expected_configuration": None,
    }
    base.update(kwargs)
    return SimpleNamespace(**base)


def _imported_roots(module_file: str) -> set[str]:
    tree = ast.parse(Path(module_file).read_text(encoding="utf-8"))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imported.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
            # Also capture dotted app.* service modules for safety checks.
            parts = node.module.split(".")
            if len(parts) >= 2:
                imported.add(parts[-1])
                imported.add(".".join(parts[-2:]))
    return imported


@pytest.mark.parametrize(
    ("text_field", "expected"),
    [
        ("PermitRootLogin no", TaskCode.SSH_DISABLE_ROOT_LOGIN.value),
        ("Disable X11Forwarding", TaskCode.SSH_DISABLE_X11_FORWARDING.value),
        ("Set MaxSessions 4", TaskCode.SSH_SET_MAX_SESSIONS.value),
        ("PASS_MAX_DAYS 90", TaskCode.SET_PASS_MAX_DAYS.value),
        ("chmod 750 /var/log", TaskCode.SET_VAR_LOG_PERMISSIONS.value),
        ("mount /tmp with nodev", TaskCode.SET_TMP_NODEV.value),
        ("mount /tmp with noexec", TaskCode.SET_TMP_NOEXEC.value),
        ("mount /dev/shm nodev", TaskCode.SET_DEV_SHM_NODEV.value),
        ("mount /dev/shm noexec", TaskCode.SET_DEV_SHM_NOEXEC.value),
        ("Ensure SELinux enforcing", TaskCode.SET_SELINUX_MODE.value),
        ("setenforce 1", TaskCode.SET_SELINUX_MODE.value),
        ("Update /etc/motd banner", TaskCode.SET_MOTD_BANNER.value),
        ("Banner /etc/issue.net in sshd_config", TaskCode.SET_SSH_LOGIN_BANNER.value),
    ],
)
def test_every_classifier_rule(text_field: str, expected: str) -> None:
    result = classify_record(_finding(remediation=text_field))
    assert result.task_code == expected
    assert result.is_recognized is True


@pytest.mark.parametrize(
    "field_name",
    [
        "qualys_control_id",
        "source_check_id",
        "control_description",
        "rationale",
        "remediation",
        "expected_configuration",
    ],
)
def test_classifier_uses_each_text_field(field_name: str) -> None:
    """Keyword in any of the six classifier fields must match (not only remediation)."""
    result = classify_record(_finding(**{field_name: "PermitRootLogin no"}))
    assert result.task_code == TaskCode.SSH_DISABLE_ROOT_LOGIN.value
    assert result.is_recognized is True


def test_unknown_remediation_needs_review() -> None:
    result = classify_record(_finding(remediation="Install proprietary agent XYZ"))
    assert result.task_code == TaskCode.NEEDS_REVIEW.value
    assert result.is_recognized is False


def test_compliant_status_detection() -> None:
    assert _is_already_compliant("Passed")
    assert _is_already_compliant("Compliant")
    assert _is_already_compliant("Success")
    assert _is_already_compliant("Not Applicable")
    assert not _is_already_compliant("Failed")
    assert not _is_already_compliant(None)


def test_record_hash_stable() -> None:
    h1 = compute_record_hash(
        device_name="HostA",
        qualys_control_id="1",
        source_check_id="S",
        config_scan_id="C",
        expected_configuration="x",
    )
    h2 = compute_record_hash(
        device_name="hosta",
        qualys_control_id="1",
        source_check_id="S",
        config_scan_id="C",
        expected_configuration="x",
    )
    assert h1 == h2


def _record(**kwargs: object) -> SimpleNamespace:
    defaults: dict[str, object] = {
        "id": 1,
        "row_number": 2,
        "device_name": "host-1",
        "overall_status": "Failed",
        "qualys_control_id": "Q1",
        "source_check_id": "S1",
        "config_scan_id": "C1",
        "expected_configuration": "PermitRootLogin no",
        "control_description": "Disable root login",
        "rationale": "security",
        "remediation": "Set PermitRootLogin no",
        "validation_status": None,
        "normalized_status": None,
        "task_code": None,
        "validation_error": None,
        "record_hash": None,
    }
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


def _run_validation(records: list[SimpleNamespace], devices: set[str]):
    db = MagicMock()
    batch = SimpleNamespace(id=10)
    db.get.return_value = batch

    class ScalarsResult:
        def __init__(self, values):
            self._values = values

        def all(self):
            return self._values

    service = RecordValidationService(db)
    from app.services import validator as validator_mod

    original_load = validator_mod._load_active_device_names
    validator_mod._load_active_device_names = lambda _db: devices
    try:
        db.scalars.side_effect = [ScalarsResult(records)]
        summary = service.validate_batch(10)
    finally:
        validator_mod._load_active_device_names = original_load
    return summary, records


def test_missing_device_name_invalid() -> None:
    rec = _record(device_name="")
    summary, records = _run_validation([rec], devices={"host-1"})
    assert records[0].validation_status == RecordStatus.INVALID_RECORD.value
    assert records[0].validation_status != READY
    assert summary.invalid_record == 1
    assert summary.ready_for_plan == 0


def test_compliant_status_already_compliant() -> None:
    # Known remediation must still not become READY_FOR_PLAN when already compliant.
    rec = _record(overall_status="Passed", remediation="Set PermitRootLogin no")
    summary, records = _run_validation([rec], devices={"host-1"})
    assert records[0].validation_status == RecordStatus.ALREADY_COMPLIANT.value
    assert records[0].validation_status != READY
    assert summary.already_compliant == 1
    assert summary.ready_for_plan == 0


def test_asset_not_found() -> None:
    # Known remediation + missing asset must never become READY_FOR_PLAN.
    rec = _record(device_name="unknown-host", remediation="Set PermitRootLogin no")
    summary, records = _run_validation([rec], devices={"host-1"})
    assert records[0].validation_status == RecordStatus.ASSET_NOT_FOUND.value
    assert records[0].validation_status != READY
    assert summary.asset_not_found == 1
    assert summary.ready_for_plan == 0


def test_duplicate_detection() -> None:
    r1 = _record(id=1, row_number=2)
    r2 = _record(id=2, row_number=3)
    summary, records = _run_validation([r1, r2], devices={"host-1"})
    assert records[0].validation_status == READY
    assert records[1].validation_status == RecordStatus.DUPLICATE.value
    assert records[1].validation_status != READY
    assert summary.duplicate == 1
    assert summary.ready_for_plan == 1


def test_valid_non_compliant_known_ready_for_plan() -> None:
    rec = _record(
        device_name="host-1",
        overall_status="Failed",
        remediation="Set PermitRootLogin no in sshd_config",
    )
    summary, records = _run_validation([rec], devices={"host-1"})
    assert records[0].validation_status == READY
    assert records[0].task_code == TaskCode.SSH_DISABLE_ROOT_LOGIN.value
    assert summary.ready_for_plan == 1


def test_unknown_goes_needs_review_never_ready_for_plan() -> None:
    rec = _record(
        device_name="host-1",
        overall_status="Failed",
        remediation="Do something custom and unclear",
        expected_configuration="unknown",
        control_description="misc",
        rationale="misc",
        qualys_control_id="X",
        source_check_id="Y",
    )
    summary, records = _run_validation([rec], devices={"host-1"})
    assert records[0].validation_status == RecordStatus.NEEDS_REVIEW.value
    assert records[0].task_code == TaskCode.NEEDS_REVIEW.value
    assert records[0].validation_status != READY
    assert summary.needs_review == 1
    assert summary.ready_for_plan == 0


def test_validate_batch_not_found() -> None:
    db = MagicMock()
    db.get.return_value = None
    with pytest.raises(ValueError):
        RecordValidationService(db).validate_batch(999)


def test_phase3_modules_do_not_call_ansible_ai_or_plans() -> None:
    """Phase 3 validate/classify path must not import execution, AI, or plan modules."""
    import app.api.imports as imports_api
    import app.classifiers.rules as rules_mod
    import app.services.validator as validator_mod

    for mod in (validator_mod, rules_mod, imports_api):
        roots = _imported_roots(mod.__file__)
        for forbidden in FORBIDDEN_IMPORT_ROOTS:
            assert forbidden not in roots, f"{mod.__name__} imports {forbidden}"
        assert "ai_suggestions" not in roots
        assert "ai_remediation_suggestion" not in roots
        # generate-plan endpoint remains stubbed; validate path must not call plan services.
        assert "execution_plan" not in roots
        assert "plan_service" not in roots

    source = Path(imports_api.__file__).read_text(encoding="utf-8")
    assert "RecordValidationService" in source
    assert "AnsibleExecutionService" not in source
    assert "dry_run_job" not in source
    assert "run_job" not in source
