"""Phase 9A tests: Qualys control coverage expansion (classifier + catalog).

Does not modify mock dry-run/run safety behaviour. Never executes Ansible.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.classifiers.qualys_control_map import (
    MANUAL_REVIEW_QUALYS_CONTROL_IDS,
    QUALYS_CONTROL_ID_MAP,
)
from app.classifiers.rules import classify_record
from app.constants.record_status import RecordStatus
from app.constants.task_codes import TaskCode
from app.db.seed_remediation_catalog import MVP_CATALOG, PHASE9A_TASK_CODES
from app.models.execution_job import ExecutionJob
from app.models.execution_job_target import ExecutionJobTarget
from app.models.execution_plan import ExecutionPlan
from app.services.plan_generator import PlanGeneratorService
from app.services.validator import RecordValidationService

READY = RecordStatus.READY_FOR_PLAN.value

# Exact Qualys ID → task_code pairs from the Phase 9A map (all must classify).
PHASE9A_ID_CASES: list[tuple[str, str]] = sorted(QUALYS_CONTROL_ID_MAP.items())

PHASE9A_TEXT_FALLBACK: list[tuple[str, str]] = [
    ("PASS_MIN_DAYS 1", TaskCode.PASSWORD_MIN_AGE.value),
    (
        "net.ipv4.conf.all.secure_redirects = 0",
        TaskCode.SYSCTL_IPV4_SECURE_REDIRECTS_DISABLE.value,
    ),
    (
        "net.ipv6.conf.default.accept_ra = 0",
        TaskCode.SYSCTL_IPV6_ACCEPT_RA_DISABLE.value,
    ),
    ("journald Compress=yes", TaskCode.JOURNALD_COMPRESS_ENABLE.value),
    ("IgnoreRhosts yes", TaskCode.SSH_IGNORE_RHOSTS_ENABLE.value),
    ("LogLevel INFO", TaskCode.SSH_LOG_LEVEL_INFO.value),
    ("MaxAuthTries 4", TaskCode.SSH_MAX_AUTH_TRIES.value),
    ("ClientAliveInterval 300", TaskCode.SSH_CLIENT_ALIVE_INTERVAL.value),
    ("TMOUT=600", TaskCode.SHELL_TMOUT.value),
    ("chmod 600 /etc/crontab", TaskCode.CRONTAB_PERMISSIONS.value),
    ("chmod 700 /etc/cron.daily", TaskCode.CRON_DAILY_PERMISSIONS.value),
    ("chmod 700 /etc/cron.hourly", TaskCode.CRON_HOURLY_PERMISSIONS.value),
    ("chmod 700 /etc/cron.weekly", TaskCode.CRON_WEEKLY_PERMISSIONS.value),
    ("chmod 700 /etc/cron.monthly", TaskCode.CRON_MONTHLY_PERMISSIONS.value),
    ("remove rsync package", TaskCode.RSYNC_REMOVE.value),
    ("remove xorg-x11-server packages", TaskCode.X11_SERVER_REMOVE.value),
    ("install aide package", TaskCode.AIDE_INSTALL.value),
    ("ensure /home has nodev in fstab", TaskCode.HOME_PARTITION_NODEV.value),
]


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


def _record(**kwargs: object) -> SimpleNamespace:
    defaults: dict[str, object] = {
        "id": 1,
        "row_number": 2,
        "device_name": "host-1",
        "overall_status": "Failed",
        "qualys_control_id": "Q1",
        "source_check_id": "S1",
        "config_scan_id": "C1",
        "expected_configuration": "x",
        "control_description": "desc",
        "rationale": "rationale",
        "remediation": "remediation",
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


class ScalarsResult:
    def __init__(self, values):
        self._values = values

    def all(self):
        return self._values


def _run_generate(
    records: list[SimpleNamespace],
    *,
    enabled_codes: set[str],
    all_codes: set[str],
    assets: list[SimpleNamespace] | None = None,
):
    db = MagicMock()
    db.get.return_value = SimpleNamespace(id=10)
    assets = assets or [
        SimpleNamespace(
            device_name="host-1",
            ip_address="10.0.0.1",
            environment="test",
            ansible_group="linux_test",
            is_active=True,
        )
    ]
    db.scalars.side_effect = [
        ScalarsResult(records),
        ScalarsResult(list(enabled_codes)),
        ScalarsResult(list(all_codes)),
        ScalarsResult(assets),
    ]
    plan_id = {"n": 100}
    job_id = {"n": 200}

    def flush() -> None:
        for call in db.add.call_args_list:
            obj = call.args[0]
            if isinstance(obj, ExecutionPlan) and getattr(obj, "id", None) is None:
                obj.id = plan_id["n"]
                plan_id["n"] += 1
            if isinstance(obj, ExecutionJob) and getattr(obj, "id", None) is None:
                obj.id = job_id["n"]
                job_id["n"] += 1

    db.flush.side_effect = flush
    result = PlanGeneratorService(db).generate_plan(10, created_by="tester")
    added = [c.args[0] for c in db.add.call_args_list]
    return result, added


# ---------------------------------------------------------------------------
# Exact Qualys ID mappings
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(("control_id", "expected"), PHASE9A_ID_CASES)
def test_phase9a_exact_qualys_control_id_mapping(
    control_id: str, expected: str
) -> None:
    result = classify_record(_finding(qualys_control_id=control_id))
    assert result.task_code == expected
    assert result.is_recognized is True
    assert result.matched_rule == f"qualys_control_id:{control_id}"


@pytest.mark.parametrize(("control_id", "expected"), PHASE9A_ID_CASES)
def test_phase9a_exact_id_wins_over_unrelated_text(
    control_id: str, expected: str
) -> None:
    """Exact ID must win even when remediation text would not match alone."""
    result = classify_record(
        _finding(
            qualys_control_id=control_id,
            remediation="Install proprietary agent XYZ",
            expected_configuration="n/a",
        )
    )
    assert result.task_code == expected
    assert result.matched_rule == f"qualys_control_id:{control_id}"


# ---------------------------------------------------------------------------
# Conservative text fallback
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(("text", "expected"), PHASE9A_TEXT_FALLBACK)
def test_phase9a_conservative_text_fallback(text: str, expected: str) -> None:
    result = classify_record(_finding(expected_configuration=text))
    assert result.task_code == expected
    assert result.is_recognized is True


# ---------------------------------------------------------------------------
# Holdouts + unknown controls stay NEEDS_REVIEW (not READY_FOR_PLAN)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("control_id", sorted(MANUAL_REVIEW_QUALYS_CONTROL_IDS))
def test_manual_review_qualys_ids_not_auto_mapped(control_id: str) -> None:
    assert control_id not in QUALYS_CONTROL_ID_MAP
    # Use holdout-safe text that must not trip Phase 9A keyword rules.
    if control_id == "6896":
        text = "Review home directory permissions per user carefully"
    else:
        text = "Create dedicated /tmp partition and migrate existing data"
    result = classify_record(
        _finding(
            qualys_control_id=control_id,
            remediation=text,
            expected_configuration=text,
            control_description=text,
        )
    )
    assert result.task_code == TaskCode.NEEDS_REVIEW.value
    assert result.is_recognized is False


@pytest.mark.parametrize("control_id", sorted(MANUAL_REVIEW_QUALYS_CONTROL_IDS))
def test_manual_review_ids_never_ready_for_plan(control_id: str) -> None:
    if control_id == "6896":
        text = "Review home directory permissions per user carefully"
    else:
        text = "Create dedicated /tmp partition and migrate existing data"
    rec = _record(
        qualys_control_id=control_id,
        remediation=text,
        expected_configuration=text,
        control_description=text,
        rationale="manual",
    )
    summary, records = _run_validation([rec], devices={"host-1"})
    assert records[0].validation_status == RecordStatus.NEEDS_REVIEW.value
    assert records[0].task_code == TaskCode.NEEDS_REVIEW.value
    assert records[0].validation_status != READY
    assert summary.needs_review == 1
    assert summary.ready_for_plan == 0


def test_unknown_control_still_needs_review() -> None:
    result = classify_record(
        _finding(
            qualys_control_id="999999",
            remediation="Something completely custom",
            expected_configuration="unknown widget setting",
        )
    )
    assert result.task_code == TaskCode.NEEDS_REVIEW.value
    assert result.is_recognized is False


def test_unknown_control_validation_never_ready_for_plan() -> None:
    rec = _record(
        qualys_control_id="999999",
        remediation="Do something custom and unclear",
        expected_configuration="unknown",
        control_description="misc",
        rationale="misc",
    )
    summary, records = _run_validation([rec], devices={"host-1"})
    assert records[0].validation_status == RecordStatus.NEEDS_REVIEW.value
    assert records[0].validation_status != READY
    assert summary.ready_for_plan == 0


@pytest.mark.parametrize(("control_id", "expected"), PHASE9A_ID_CASES[:3])
def test_mapped_qualys_id_can_reach_ready_for_plan(
    control_id: str, expected: str
) -> None:
    rec = _record(
        qualys_control_id=control_id,
        remediation="see catalog",
        expected_configuration="see catalog",
        control_description="phase9a",
        rationale="phase9a",
    )
    summary, records = _run_validation([rec], devices={"host-1"})
    assert records[0].validation_status == READY
    assert records[0].task_code == expected
    assert summary.ready_for_plan == 1


# ---------------------------------------------------------------------------
# Catalog seed contains Phase 9A task codes (enabled for MVP/mock)
# ---------------------------------------------------------------------------


def test_catalog_seed_contains_phase9a_task_codes() -> None:
    by_code = {str(item["task_code"]): item for item in MVP_CATALOG}
    assert PHASE9A_TASK_CODES == set(QUALYS_CONTROL_ID_MAP.values())
    for code in PHASE9A_TASK_CODES:
        assert code in by_code, f"missing catalog entry for {code}"
        assert by_code[code]["is_enabled"] is True
        playbook = str(by_code[code]["ansible_playbook_path"])
        assert playbook.endswith(".yml")
        path = Path("/workspace/ansible/playbooks") / playbook
        assert path.is_file(), f"missing playbook file {playbook}"


def test_holdout_task_codes_not_in_catalog_as_auto_mapped() -> None:
    """6896/7394 must not gain executable catalog task codes via Phase 9A map."""
    catalog_codes = {str(item["task_code"]) for item in MVP_CATALOG}
    assert "HOME_DIR_PERMISSIONS" not in catalog_codes
    assert "TMP_PARTITION_REQUIRED" not in catalog_codes
    assert "6896" not in QUALYS_CONTROL_ID_MAP
    assert "7394" not in QUALYS_CONTROL_ID_MAP


# ---------------------------------------------------------------------------
# generate-plan: only READY_FOR_PLAN + enabled catalog
# ---------------------------------------------------------------------------


def test_generate_plan_uses_ready_for_plan_with_enabled_phase9a_catalog() -> None:
    enabled = {"PASSWORD_MIN_AGE", "SSH_DISABLE_ROOT_LOGIN"}
    all_codes = enabled | {"SSH_DISABLE_X11_FORWARDING"}
    records = [
        SimpleNamespace(
            id=1,
            batch_id=10,
            row_number=2,
            device_name="host-1",
            validation_status=READY,
            task_code="PASSWORD_MIN_AGE",
            criticality="High",
        ),
        SimpleNamespace(
            id=2,
            batch_id=10,
            row_number=3,
            device_name="host-1",
            validation_status=RecordStatus.NEEDS_REVIEW.value,
            task_code=TaskCode.NEEDS_REVIEW.value,
            criticality="High",
        ),
        SimpleNamespace(
            id=3,
            batch_id=10,
            row_number=4,
            device_name="host-1",
            validation_status=READY,
            task_code="SSH_DISABLE_X11_FORWARDING",  # disabled catalog
            criticality="Medium",
        ),
    ]
    result, added = _run_generate(
        records, enabled_codes=enabled, all_codes=all_codes
    )
    jobs = [o for o in added if isinstance(o, ExecutionJob)]
    targets = [o for o in added if isinstance(o, ExecutionJobTarget)]
    assert result.ready_for_plan_records == 2
    assert result.skipped_excluded_status == 1
    assert result.skipped_disabled_catalog == 1
    assert result.job_count == 1
    assert len(jobs) == 1
    assert jobs[0].task_code == "PASSWORD_MIN_AGE"
    assert len(targets) == 1


def test_generate_plan_skips_needs_review_even_if_task_looks_known() -> None:
    """NEEDS_REVIEW status must never create jobs regardless of task_code field."""
    result, added = _run_generate(
        [
            SimpleNamespace(
                id=1,
                batch_id=10,
                row_number=2,
                device_name="host-1",
                validation_status=RecordStatus.NEEDS_REVIEW.value,
                task_code="PASSWORD_MIN_AGE",
                criticality="High",
            )
        ],
        enabled_codes={"PASSWORD_MIN_AGE"},
        all_codes={"PASSWORD_MIN_AGE"},
    )
    assert result.job_count == 0
    assert result.skipped_excluded_status == 1
    assert not any(isinstance(o, ExecutionJob) for o in added)
