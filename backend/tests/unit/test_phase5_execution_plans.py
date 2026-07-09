"""Phase 5 tests: execution plan generation and approval (no Ansible)."""

from __future__ import annotations

import ast
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.constants.job_status import JobStatus
from app.constants.record_status import RecordStatus
from app.models.execution_job import ExecutionJob
from app.models.execution_job_target import ExecutionJobTarget
from app.models.execution_plan import ExecutionPlan
from app.services.job_approval import JobApprovalError, JobApprovalService
from app.services.plan_generator import MAX_TARGETS_PER_JOB, PlanGeneratorService

FORBIDDEN_IMPORT_ROOTS = {
    "ansible_execution",
    "real_ansible_runner",
    "subprocess",
    "ansible_runner",
    "paramiko",
    "openai",
}


def _imported_roots(module_file: str) -> set[str]:
    tree = ast.parse(Path(module_file).read_text(encoding="utf-8"))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imported.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom) and node.module:
            parts = node.module.split(".")
            imported.add(parts[0])
            imported.add(parts[-1])
            if len(parts) >= 2:
                imported.add(".".join(parts[-2:]))
    return imported


class ScalarsResult:
    def __init__(self, values):
        self._values = values

    def all(self):
        return self._values

    def first(self):
        return self._values[0] if self._values else None


def _record(**kwargs: object) -> SimpleNamespace:
    defaults: dict[str, object] = {
        "id": 1,
        "batch_id": 10,
        "row_number": 2,
        "device_name": "host-1",
        "validation_status": RecordStatus.READY_FOR_PLAN.value,
        "task_code": "SSH_DISABLE_ROOT_LOGIN",
        "criticality": "High",
    }
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


def _asset(**kwargs: object) -> SimpleNamespace:
    defaults: dict[str, object] = {
        "device_name": "host-1",
        "ip_address": "10.0.0.1",
        "environment": "prod",
        "ansible_group": "linux_servers",
        "is_active": True,
    }
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


def _run_generate(
    records: list[SimpleNamespace],
    *,
    enabled_codes: set[str] | None = None,
    all_codes: set[str] | None = None,
    assets: list[SimpleNamespace] | None = None,
):
    db = MagicMock()
    db.get.return_value = SimpleNamespace(id=10)
    assets = assets or [_asset()]
    enabled_codes = enabled_codes or {"SSH_DISABLE_ROOT_LOGIN"}
    all_codes = all_codes or {"SSH_DISABLE_ROOT_LOGIN", "SSH_DISABLE_X11_FORWARDING"}

    # Order of scalars calls in generate_plan:
    # 1) records, 2) enabled catalog, 3) all catalog, 4) assets
    db.scalars.side_effect = [
        ScalarsResult(records),
        ScalarsResult(list(enabled_codes)),
        ScalarsResult(list(all_codes)),
        ScalarsResult(assets),
    ]

    # Simulate flush assigning IDs
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

    service = PlanGeneratorService(db)
    result = service.generate_plan(10, created_by="tester")
    added = [c.args[0] for c in db.add.call_args_list]
    return result, added, db


def test_only_ready_for_plan_included() -> None:
    records = [
        _record(id=1, device_name="host-1", validation_status=RecordStatus.READY_FOR_PLAN.value),
        _record(id=2, device_name="host-2", validation_status=RecordStatus.NEEDS_REVIEW.value),
        _record(id=3, device_name="host-3", validation_status=RecordStatus.ASSET_NOT_FOUND.value),
        _record(id=4, device_name="host-4", validation_status=RecordStatus.ALREADY_COMPLIANT.value),
        _record(id=5, device_name="host-5", validation_status=RecordStatus.DUPLICATE.value),
        _record(id=6, device_name="host-6", validation_status=RecordStatus.INVALID_RECORD.value),
        _record(
            id=7,
            device_name="host-7",
            validation_status=RecordStatus.UNSUPPORTED_CONTROL.value,
        ),
    ]
    assets = [
        _asset(device_name="host-1"),
        _asset(device_name="host-2"),
        _asset(device_name="host-3"),
        _asset(device_name="host-4"),
        _asset(device_name="host-5"),
        _asset(device_name="host-6"),
        _asset(device_name="host-7"),
    ]
    result, added, _db = _run_generate(records, assets=assets)
    jobs = [o for o in added if isinstance(o, ExecutionJob)]
    targets = [o for o in added if isinstance(o, ExecutionJobTarget)]
    assert result.ready_for_plan_records == 1
    assert result.skipped_excluded_status == 6
    assert len(jobs) == 1
    assert len(targets) == 1
    assert targets[0].device_name == "host-1"
    assert jobs[0].status == JobStatus.WAITING_DRY_RUN.value


@pytest.mark.parametrize(
    "status",
    [
        RecordStatus.NEEDS_REVIEW.value,
        RecordStatus.ASSET_NOT_FOUND.value,
        RecordStatus.ALREADY_COMPLIANT.value,
        RecordStatus.DUPLICATE.value,
        RecordStatus.INVALID_RECORD.value,
        RecordStatus.UNSUPPORTED_CONTROL.value,
    ],
)
def test_excluded_statuses_produce_no_jobs(status: str) -> None:
    result, added, _db = _run_generate(
        [_record(validation_status=status, device_name="host-1")],
        assets=[_asset(device_name="host-1")],
    )
    assert result.job_count == 0
    assert not any(isinstance(o, ExecutionJob) for o in added)


def test_missing_catalog_task_code_skipped() -> None:
    result, added, _db = _run_generate(
        [_record(task_code="NOT_IN_CATALOG")],
        enabled_codes={"SSH_DISABLE_ROOT_LOGIN"},
        all_codes={"SSH_DISABLE_ROOT_LOGIN"},
    )
    assert result.skipped_missing_catalog == 1
    assert result.job_count == 0
    assert not any(isinstance(o, ExecutionJob) for o in added)


def test_disabled_catalog_task_code_skipped() -> None:
    result, added, _db = _run_generate(
        [_record(task_code="SSH_DISABLE_X11_FORWARDING")],
        enabled_codes={"SSH_DISABLE_ROOT_LOGIN"},
        all_codes={"SSH_DISABLE_ROOT_LOGIN", "SSH_DISABLE_X11_FORWARDING"},
    )
    assert result.skipped_disabled_catalog == 1
    assert result.job_count == 0
    assert not any(isinstance(o, ExecutionJob) for o in added)


def test_jobs_group_by_task_env_crit_group() -> None:
    records = [
        _record(
            id=1,
            device_name="host-a",
            task_code="SSH_DISABLE_ROOT_LOGIN",
            criticality="High",
        ),
        _record(
            id=2,
            device_name="host-b",
            task_code="SSH_DISABLE_ROOT_LOGIN",
            criticality="High",
        ),
        _record(
            id=3,
            device_name="host-c",
            task_code="SSH_DISABLE_ROOT_LOGIN",
            criticality="Low",
        ),
    ]
    assets = [
        _asset(device_name="host-a", environment="prod", ansible_group="g1"),
        _asset(device_name="host-b", environment="prod", ansible_group="g1"),
        _asset(device_name="host-c", environment="prod", ansible_group="g1"),
    ]
    result, added, _db = _run_generate(records, assets=assets)
    jobs = [o for o in added if isinstance(o, ExecutionJob)]
    targets = [o for o in added if isinstance(o, ExecutionJobTarget)]
    assert result.job_count == 2
    assert len(jobs) == 2
    assert len(targets) == 3
    high_job = next(j for j in jobs if j.criticality == "High")
    low_job = next(j for j in jobs if j.criticality == "Low")
    high_targets = [t for t in targets if t.job_id == high_job.id]
    low_targets = [t for t in targets if t.job_id == low_job.id]
    assert len(high_targets) == 2
    assert len(low_targets) == 1


def test_jobs_split_at_100_targets() -> None:
    records = [
        _record(
            id=i,
            device_name=f"host-{i}",
            task_code="SSH_DISABLE_ROOT_LOGIN",
            criticality="High",
            row_number=i,
        )
        for i in range(1, 101 + 25)
    ]
    assets = [
        _asset(device_name=f"host-{i}", environment="prod", ansible_group="g1")
        for i in range(1, 101 + 25)
    ]
    result, added, _db = _run_generate(records, assets=assets)
    jobs = [o for o in added if isinstance(o, ExecutionJob)]
    targets = [o for o in added if isinstance(o, ExecutionJobTarget)]
    assert result.target_count == 125
    assert result.job_count == 2
    assert len(jobs) == 2
    assert MAX_TARGETS_PER_JOB == 100
    counts = {}
    for t in targets:
        counts[t.job_id] = counts.get(t.job_id, 0) + 1
    assert sorted(counts.values()) == [25, 100]


def test_job_status_starts_waiting_dry_run() -> None:
    result, added, _db = _run_generate([_record()])
    jobs = [o for o in added if isinstance(o, ExecutionJob)]
    assert jobs
    assert all(j.status == JobStatus.WAITING_DRY_RUN.value for j in jobs)
    assert result.plan.status in {"generated", "empty"} or result.job_count == 1


def test_approve_blocked_for_waiting_dry_run() -> None:
    job = SimpleNamespace(
        id=1,
        plan_id=9,
        task_code="SSH_DISABLE_ROOT_LOGIN",
        status=JobStatus.WAITING_DRY_RUN.value,
        approved_by=None,
        approved_at=None,
    )
    db = MagicMock()
    db.get.return_value = job
    with pytest.raises(JobApprovalError, match="waiting_dry_run"):
        JobApprovalService(db).approve(1, reviewed_by="alice")
    db.commit.assert_not_called()


def test_approve_blocked_before_dry_run_success() -> None:
    for status in (
        JobStatus.WAITING_DRY_RUN.value,
        JobStatus.DRY_RUN_RUNNING.value,
        JobStatus.DRY_RUN_FAILED.value,
        JobStatus.DRAFT.value,
    ):
        job = SimpleNamespace(
            id=1,
            plan_id=9,
            task_code="SSH_DISABLE_ROOT_LOGIN",
            status=status,
            approved_by=None,
            approved_at=None,
        )
        db = MagicMock()
        db.get.return_value = job
        with pytest.raises(JobApprovalError):
            JobApprovalService(db).approve(1)
        db.commit.assert_not_called()


def test_approve_allowed_after_dry_run_success() -> None:
    """Phase 5 does not run dry-run, but approve path must accept dry_run_success."""
    job = SimpleNamespace(
        id=1,
        plan_id=9,
        task_code="SSH_DISABLE_ROOT_LOGIN",
        status=JobStatus.DRY_RUN_SUCCESS.value,
        approved_by=None,
        approved_at=None,
    )
    db = MagicMock()
    db.get.return_value = job
    out = JobApprovalService(db).approve(1, reviewed_by="alice")
    assert out.status == JobStatus.APPROVED.value
    assert out.approved_by == "alice"
    db.commit.assert_called_once()


def test_reject_works_for_waiting_dry_run() -> None:
    job = SimpleNamespace(
        id=1,
        plan_id=9,
        task_code="SSH_DISABLE_ROOT_LOGIN",
        status=JobStatus.WAITING_DRY_RUN.value,
        approved_by=None,
        approved_at=None,
    )
    db = MagicMock()
    db.get.return_value = job
    out = JobApprovalService(db).reject(1, reviewed_by="bob")
    assert out.status == JobStatus.REJECTED.value
    assert out.approved_by == "bob"
    db.commit.assert_called_once()


@pytest.mark.parametrize(
    "status",
    [
        JobStatus.WAITING_DRY_RUN.value,
        JobStatus.DRY_RUN_FAILED.value,
        JobStatus.WAITING_APPROVAL.value,
    ],
)
def test_reject_works_for_allowed_statuses(status: str) -> None:
    job = SimpleNamespace(
        id=1,
        plan_id=9,
        task_code="SSH_DISABLE_ROOT_LOGIN",
        status=status,
        approved_by=None,
        approved_at=None,
    )
    db = MagicMock()
    db.get.return_value = job
    out = JobApprovalService(db).reject(1)
    assert out.status == JobStatus.REJECTED.value


def test_phase5_never_uses_ai_generated_playbook() -> None:
    src = Path(__file__).resolve().parents[2] / "app" / "services" / "plan_generator.py"
    text = src.read_text(encoding="utf-8")
    assert "generated_playbook" not in text or "used_ai_generated_playbook" in text
    assert "AIRemediationSuggestion" not in text
    assert "ai_remediation" not in text


def test_phase5_modules_no_ansible_mock_subprocess_ssh() -> None:
    import app.api.execution_jobs as jobs_api
    import app.api.execution_plans as plans_api
    import app.api.imports as imports_api
    import app.services.job_approval as approval_mod
    import app.services.plan_generator as generator_mod

    for mod in (generator_mod, approval_mod, plans_api):
        roots = _imported_roots(mod.__file__)
        for forbidden in FORBIDDEN_IMPORT_ROOTS:
            assert forbidden not in roots, f"{mod.__name__} imports {forbidden}"
        src = Path(mod.__file__).read_text(encoding="utf-8")
        assert "AnsibleExecutionService" not in src
        assert "import subprocess" not in src
        assert "from subprocess" not in src

    jobs_roots = _imported_roots(jobs_api.__file__)
    for forbidden in FORBIDDEN_IMPORT_ROOTS:
        assert forbidden not in jobs_roots
    jobs_src = Path(jobs_api.__file__).read_text(encoding="utf-8")
    assert "AnsibleExecutionService" not in jobs_src
    assert "Not implemented yet (Phase 6)" in jobs_src

    # generate-plan handler must not call execution services
    imports_src = Path(imports_api.__file__).read_text(encoding="utf-8")
    tree = ast.parse(imports_src)
    gen_node = next(
        n
        for n in tree.body
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == "generate_plan"
    )
    body = ast.get_source_segment(imports_src, gen_node)
    assert body is not None
    assert "PlanGeneratorService" in body
    assert "AnsibleExecutionService" not in body
    assert "MockAIProvider" not in body
