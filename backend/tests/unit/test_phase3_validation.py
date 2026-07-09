"""Phase 3 tests: validation statuses and rule-based classifier."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.classifiers.rules import classify_record
from app.constants.record_status import RecordStatus
from app.constants.task_codes import TaskCode
from app.services.record_hash import compute_record_hash
from app.services.validator import RecordValidationService, _is_already_compliant


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

    # First scalars call loads records; second (inside _load_active_device_names) loads devices.
    # RecordValidationService calls: write_audit, select records, select assets, write_audit.
    # We monkeypatch helpers instead for clarity.
    service = RecordValidationService(db)
    from app.services import validator as validator_mod

    original_load = validator_mod._load_active_device_names
    validator_mod._load_active_device_names = lambda _db: devices
    try:
        db.scalars.side_effect = [
            ScalarsResult(records),  # records query
        ]
        # validate_batch also calls db.scalars once for records only after patching assets loader
        summary = service.validate_batch(10)
    finally:
        validator_mod._load_active_device_names = original_load
    return summary, records


def test_missing_device_name_invalid() -> None:
    rec = _record(device_name="")
    summary, records = _run_validation([rec], devices={"host-1"})
    assert records[0].validation_status == RecordStatus.INVALID_RECORD.value
    assert summary.invalid_record == 1


def test_compliant_status_already_compliant() -> None:
    rec = _record(overall_status="Passed")
    summary, records = _run_validation([rec], devices={"host-1"})
    assert records[0].validation_status == RecordStatus.ALREADY_COMPLIANT.value
    assert summary.already_compliant == 1


def test_asset_not_found() -> None:
    rec = _record(device_name="unknown-host")
    summary, records = _run_validation([rec], devices={"host-1"})
    assert records[0].validation_status == RecordStatus.ASSET_NOT_FOUND.value
    assert summary.asset_not_found == 1


def test_duplicate_detection() -> None:
    r1 = _record(id=1, row_number=2)
    r2 = _record(id=2, row_number=3)
    summary, records = _run_validation([r1, r2], devices={"host-1"})
    assert records[0].validation_status == RecordStatus.READY_FOR_PLAN.value
    assert records[1].validation_status == RecordStatus.DUPLICATE.value
    assert summary.duplicate == 1
    assert summary.ready_for_plan == 1


def test_valid_non_compliant_known_ready_for_plan() -> None:
    rec = _record(
        device_name="host-1",
        overall_status="Failed",
        remediation="Set PermitRootLogin no in sshd_config",
    )
    summary, records = _run_validation([rec], devices={"host-1"})
    assert records[0].validation_status == RecordStatus.READY_FOR_PLAN.value
    assert records[0].task_code == TaskCode.SSH_DISABLE_ROOT_LOGIN.value
    assert summary.ready_for_plan == 1


def test_unknown_goes_needs_review() -> None:
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
    assert summary.needs_review == 1


def test_validate_batch_not_found() -> None:
    db = MagicMock()
    db.get.return_value = None
    with pytest.raises(ValueError):
        RecordValidationService(db).validate_batch(999)


def test_no_ansible_imports_in_validator_module() -> None:
    import ast
    from pathlib import Path

    import app.services.validator as mod

    tree = ast.parse(Path(mod.__file__).read_text(encoding="utf-8"))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imported.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
    assert "ansible_execution" not in imported
    assert "real_ansible_runner" not in imported
    assert "subprocess" not in imported
