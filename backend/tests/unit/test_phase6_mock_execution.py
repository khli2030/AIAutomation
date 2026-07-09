"""Phase 6 tests: mock dry-run / run / results safety."""

from __future__ import annotations

import ast
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.config import Settings
from app.constants.job_status import JobStatus
from app.models.job_result import JobResult
from app.services.ansible_execution import (
    AnsibleExecutionError,
    AnsibleExecutionService,
)
from app.services.job_approval import JobApprovalError, JobApprovalService

FORBIDDEN = {
    "ansible_runner",
    "subprocess",
    "paramiko",
    "fabric",
    "invoke",
}


@pytest.fixture(autouse=True)
def _clear_real_adapter_import() -> None:
    """Keep MOCK_MODE path free of leftover real_ansible_runner imports from other tests."""
    sys.modules.pop("app.services.real_ansible_runner", None)
    yield
    sys.modules.pop("app.services.real_ansible_runner", None)


def _settings(*, mock_mode: bool = True) -> Settings:
    return Settings(
        mock_mode=mock_mode,
        admin_token="test",
        database_url="postgresql+psycopg://x:x@localhost/x",
    )


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
    return imported


class ScalarsResult:
    def __init__(self, values):
        self._values = values

    def all(self):
        return self._values

    def first(self):
        return self._values[0] if self._values else None


def _catalog(**kwargs: object) -> SimpleNamespace:
    defaults = {
        "task_code": "SSH_DISABLE_ROOT_LOGIN",
        "is_enabled": True,
        "ansible_playbook_path": "ssh_disable_root_login.yml",
    }
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


def _target(name: str, *, ip: str = "10.0.0.1") -> SimpleNamespace:
    return SimpleNamespace(
        device_name=name,
        ip_address=ip,
        ansible_group="linux",
        status="pending",
    )


def _job(
    *,
    status: str = JobStatus.WAITING_DRY_RUN.value,
    targets: list[SimpleNamespace] | None = None,
    task_code: str = "SSH_DISABLE_ROOT_LOGIN",
) -> SimpleNamespace:
    return SimpleNamespace(
        id=1,
        plan_id=9,
        task_code=task_code,
        status=status,
        dry_run_status=None,
        approved_by=None,
        approved_at=None,
        started_at=None,
        finished_at=None,
        targets=targets or [_target("host-a"), _target("host-b")],
    )


def _service_with_job(
    job: SimpleNamespace,
    *,
    catalog: SimpleNamespace | None = None,
    mock_mode: bool = True,
) -> tuple[AnsibleExecutionService, MagicMock]:
    db = MagicMock()
    # scalars used for: load job (with options), catalog, delete existing results
    cat = catalog or _catalog()

    def scalars(query):  # noqa: ANN001
        # Heuristic: if selectinload path / job load — return job once then catalog/results
        return ScalarsResult([job])

    # More precise side_effect sequence for dry_run:
    # 1) _load_job -> job
    # 2) _assert_catalog_allows -> catalog
    # 3) existing JobResult delete query -> []
    db.scalars.side_effect = [
        ScalarsResult([job]),
        ScalarsResult([cat]),
        ScalarsResult([]),
    ]
    service = AnsibleExecutionService(db, settings=_settings(mock_mode=mock_mode))
    return service, db


def test_dry_run_blocked_unless_waiting_dry_run_or_failed() -> None:
    for status in (
        JobStatus.DRY_RUN_SUCCESS.value,
        JobStatus.APPROVED.value,
        JobStatus.RUNNING.value,
        JobStatus.DRAFT.value,
    ):
        job = _job(status=status)
        service, _db = _service_with_job(job)
        with pytest.raises(AnsibleExecutionError, match="waiting_dry_run"):
            service.dry_run_job(1)


def test_dry_run_retry_allowed_after_dry_run_failed() -> None:
    job = _job(status=JobStatus.DRY_RUN_FAILED.value, targets=[_target("h0")])
    service, db = _service_with_job(job)
    summary = service.dry_run_job(1)
    assert summary.mock_mode is True
    results = [c.args[0] for c in db.add.call_args_list if isinstance(c.args[0], JobResult)]
    assert results
    assert all(r.result_type == "dry_run" for r in results)


def test_dry_run_creates_per_host_mock_results() -> None:
    targets = [_target("host-a"), _target("host-b"), _target("host-c")]
    job = _job(status=JobStatus.WAITING_DRY_RUN.value, targets=targets)
    service, db = _service_with_job(job)

    summary = service.dry_run_job(1)
    assert summary.mock_mode is True
    assert summary.hosts_total == 3
    results = [c.args[0] for c in db.add.call_args_list if isinstance(c.args[0], JobResult)]
    assert len(results) == 3
    assert {r.device_name for r in results} == {"host-a", "host-b", "host-c"}
    assert all(isinstance(r.stdout, str) and r.stdout for r in results)
    assert all(r.result_type == "dry_run" for r in results)


def test_dry_run_updates_job_status_success() -> None:
    # indices 0,1 — neither %7==6 nor %5==4 → all success
    job = _job(
        status=JobStatus.WAITING_DRY_RUN.value,
        targets=[_target("h0"), _target("h1")],
    )
    service, _db = _service_with_job(job)
    summary = service.dry_run_job(1)
    assert summary.job_status == JobStatus.DRY_RUN_SUCCESS.value
    assert job.status == JobStatus.DRY_RUN_SUCCESS.value
    assert job.dry_run_status == JobStatus.DRY_RUN_SUCCESS.value


def test_dry_run_mixed_results_failed() -> None:
    # index 6 → failed; index 0 → success → mixed → dry_run_failed
    targets = [_target(f"h{i}") for i in range(7)]
    job = _job(status=JobStatus.WAITING_DRY_RUN.value, targets=targets)
    service, _db = _service_with_job(job)
    summary = service.dry_run_job(1)
    assert summary.hosts_failed >= 1
    assert summary.hosts_success >= 1
    assert summary.job_status == JobStatus.DRY_RUN_FAILED.value
    assert job.status == JobStatus.DRY_RUN_FAILED.value


def test_approve_blocked_before_dry_run_success() -> None:
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
    with pytest.raises(JobApprovalError):
        JobApprovalService(db).approve(1)


def test_approve_works_after_dry_run_success() -> None:
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
    assert out.approved_at is not None


def test_run_blocked_before_approved() -> None:
    for status in (
        JobStatus.WAITING_DRY_RUN.value,
        JobStatus.DRY_RUN_SUCCESS.value,
        JobStatus.DRY_RUN_FAILED.value,
        JobStatus.WAITING_APPROVAL.value,
    ):
        job = _job(status=status)
        service, _db = _service_with_job(job)
        with pytest.raises(AnsibleExecutionError, match="approved"):
            service.run_job(1)


def test_run_creates_per_host_mock_results() -> None:
    targets = [_target("host-a"), _target("host-b")]
    job = _job(status=JobStatus.APPROVED.value, targets=targets)
    service, db = _service_with_job(job)
    summary = service.run_job(1)
    assert summary.mock_mode is True
    assert summary.hosts_total == 2
    results = [c.args[0] for c in db.add.call_args_list if isinstance(c.args[0], JobResult)]
    assert len(results) == 2
    assert all(r.result_type == "run" for r in results)


def test_run_does_not_delete_dry_run_results() -> None:
    """Run must only replace result_type=run rows, never dry_run rows."""
    from app.constants.job_result_type import JobResultType

    targets = [_target("host-a")]
    job = _job(status=JobStatus.APPROVED.value, targets=targets)
    dry_run_row = SimpleNamespace(
        id=99,
        job_id=1,
        result_type=JobResultType.DRY_RUN.value,
        device_name="host-a",
    )
    db = MagicMock()
    catalog = _catalog()
    # load job, catalog, existing run-type results (empty)
    db.scalars.side_effect = [
        ScalarsResult([job]),
        ScalarsResult([catalog]),
        ScalarsResult([]),  # existing run results to replace
    ]
    service = AnsibleExecutionService(db, settings=_settings(mock_mode=True))
    service.run_job(1)

    # Ensure delete was never called on the dry_run row object
    deleted = [c.args[0] for c in db.delete.call_args_list]
    assert dry_run_row not in deleted
    results = [c.args[0] for c in db.add.call_args_list if isinstance(c.args[0], JobResult)]
    assert results
    assert all(r.result_type == JobResultType.RUN.value for r in results)


def test_dry_run_replaces_only_dry_run_results() -> None:
    from app.constants.job_result_type import JobResultType

    job = _job(status=JobStatus.DRY_RUN_FAILED.value, targets=[_target("host-a")])
    old_dry = SimpleNamespace(id=1, result_type=JobResultType.DRY_RUN.value)
    db = MagicMock()
    catalog = _catalog()
    db.scalars.side_effect = [
        ScalarsResult([job]),
        ScalarsResult([catalog]),
        ScalarsResult([old_dry]),  # previous dry_run rows replaced
    ]
    service = AnsibleExecutionService(db, settings=_settings(mock_mode=True))
    service.dry_run_job(1)
    deleted = [c.args[0] for c in db.delete.call_args_list]
    assert old_dry in deleted
    results = [c.args[0] for c in db.add.call_args_list if isinstance(c.args[0], JobResult)]
    assert all(r.result_type == JobResultType.DRY_RUN.value for r in results)


def test_run_final_status_success() -> None:
    job = _job(
        status=JobStatus.APPROVED.value,
        targets=[_target("h0"), _target("h1")],
    )
    service, _db = _service_with_job(job)
    summary = service.run_job(1)
    assert summary.job_status == JobStatus.SUCCESS.value
    assert job.status == JobStatus.SUCCESS.value


def test_run_final_status_failed() -> None:
    # Only failed hosts: indices 6,13 → both %7==6
    job = _job(
        status=JobStatus.APPROVED.value,
        targets=[_target("h6"), _target("h13")],
    )
    # Force indices by ordering: first target index 0 won't fail — use monkeypatch outcomes
    # Instead build 7 targets and check all-failed by using only failing indices via custom list
    # Simpler: patch _mock_host_outcome to always fail
    service, _db = _service_with_job(job)

    def always_fail(**kwargs):  # noqa: ANN003
        from app.services.ansible_execution import HostMockOutcome

        return HostMockOutcome(
            status="failed",
            changed=False,
            skipped=False,
            stdout="fail",
            stderr="err",
            return_code=2,
        )

    service._mock_host_outcome = always_fail  # type: ignore[method-assign]
    summary = service.run_job(1)
    assert summary.job_status == JobStatus.FAILED.value


def test_run_final_status_partially_failed() -> None:
    targets = [_target(f"h{i}") for i in range(7)]  # includes one failure at index 6
    job = _job(status=JobStatus.APPROVED.value, targets=targets)
    service, _db = _service_with_job(job)
    summary = service.run_job(1)
    assert summary.hosts_failed >= 1
    assert summary.hosts_success >= 1
    assert summary.job_status == JobStatus.PARTIALLY_FAILED.value


def test_disabled_catalog_never_executed() -> None:
    job = _job(status=JobStatus.WAITING_DRY_RUN.value)
    catalog = _catalog(is_enabled=False)
    service, _db = _service_with_job(job, catalog=catalog)
    with pytest.raises(AnsibleExecutionError, match="disabled"):
        service.dry_run_job(1)


def test_missing_catalog_never_executed() -> None:
    job = _job(status=JobStatus.WAITING_DRY_RUN.value)
    db = MagicMock()
    db.scalars.side_effect = [
        ScalarsResult([job]),
        ScalarsResult([]),  # catalog missing
    ]
    service = AnsibleExecutionService(db, settings=_settings(mock_mode=True))
    with pytest.raises(AnsibleExecutionError, match="not in remediation_catalog"):
        service.dry_run_job(1)


def test_generated_playbook_from_ai_never_used() -> None:
    import app.api.execution_jobs as jobs_api
    import app.services.ansible_execution as ae_mod

    for mod in (ae_mod, jobs_api):
        roots = _imported_roots(mod.__file__)
        assert "ai_suggestions" not in roots
        assert "ai_analyzer" not in roots
        assert "ai_remediation_suggestion" not in roots
        src = Path(mod.__file__).read_text(encoding="utf-8")
        assert "AIRemediationSuggestion" not in src

    # Execution service must only reference catalog playbook paths, never AI drafts as input.
    ae_src = Path(ae_mod.__file__).read_text(encoding="utf-8")
    assert "used_ai_generated_playbook" in ae_src
    assert "ansible_playbook_path" in ae_src
    assert "from app.models.ai_remediation_suggestion" not in ae_src


def test_phase6_no_ansible_runner_playbook_subprocess_ssh() -> None:
    import app.api.execution_jobs as jobs_api
    import app.services.ansible_execution as ae_mod

    roots = _imported_roots(ae_mod.__file__)
    for forbidden in FORBIDDEN:
        assert forbidden not in roots, f"ansible_execution imports {forbidden}"

    mock_src = Path(ae_mod.__file__).read_text(encoding="utf-8")
    tree = ast.parse(mock_src)
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == "AnsibleExecutionService":
            for item in node.body:
                if isinstance(item, ast.FunctionDef) and item.name == "_execute_mock":
                    body = ast.get_source_segment(mock_src, item)
                    assert body is not None
                    assert "ansible_runner" not in body
                    assert "subprocess" not in body
                    assert "paramiko" not in body
                    assert "ansible-playbook" not in body
                    assert "run_with_ansible_runner" not in body

    jobs_src = Path(jobs_api.__file__).read_text(encoding="utf-8")
    assert "AnsibleExecutionService" in jobs_src
    assert "import subprocess" not in jobs_src
    assert "ansible_runner" not in jobs_src
    assert "paramiko" not in jobs_src


def test_mock_uses_catalog_playbook_path_not_ai() -> None:
    job = _job(status=JobStatus.WAITING_DRY_RUN.value, targets=[_target("host-a")])
    catalog = _catalog(ansible_playbook_path="from_catalog.yml")
    service, db = _service_with_job(job, catalog=catalog)
    service.dry_run_job(1)
    results = [c.args[0] for c in db.add.call_args_list if isinstance(c.args[0], JobResult)]
    assert results
    assert "from_catalog.yml" in (results[0].stdout or "")


def test_get_results_filters_by_result_type() -> None:
    from datetime import UTC, datetime

    from app.api.execution_jobs import get_job_results
    from app.constants.job_result_type import JobResultType

    now = datetime.now(UTC)
    job = SimpleNamespace(
        id=1,
        status=JobStatus.SUCCESS.value,
        dry_run_status=JobStatus.DRY_RUN_SUCCESS.value,
    )
    dry = SimpleNamespace(
        id=1,
        job_id=1,
        result_type=JobResultType.DRY_RUN.value,
        device_name="h1",
        status="success",
        changed=False,
        skipped=False,
        stdout="dry",
        stderr="",
        return_code=0,
        created_at=now,
    )
    run = SimpleNamespace(
        id=2,
        job_id=1,
        result_type=JobResultType.RUN.value,
        device_name="h1",
        status="success",
        changed=True,
        skipped=False,
        stdout="run",
        stderr="",
        return_code=0,
        created_at=now,
    )
    db = MagicMock()
    db.get.return_value = job
    db.scalars.return_value = ScalarsResult([dry])

    out = get_job_results(1, result_type="dry_run", db=db)
    assert out.result_type_filter == "dry_run"
    assert out.total == 1
    assert out.items[0].result_type == "dry_run"

    db.scalars.return_value = ScalarsResult([run])
    out_run = get_job_results(1, result_type="run", db=db)
    assert out_run.result_type_filter == "run"
    assert out_run.items[0].result_type == "run"


def test_mock_mode_false_blocked_without_real_flag() -> None:
    job = _job(status=JobStatus.WAITING_DRY_RUN.value, targets=[_target("h0")])
    catalog = _catalog()
    db = MagicMock()
    db.scalars.side_effect = [
        ScalarsResult([job]),
        ScalarsResult([catalog]),
    ]
    service = AnsibleExecutionService(db, settings=_settings(mock_mode=False))
    with pytest.raises(AnsibleExecutionError, match="REAL_ANSIBLE_ENABLED=false"):
        service.dry_run_job(1)


def test_audit_logs_for_dry_run_approve_reject_run() -> None:
    # dry-run audits
    job = _job(status=JobStatus.WAITING_DRY_RUN.value, targets=[_target("h0")])
    service, db = _service_with_job(job)
    service.dry_run_job(1)
    audit_actions = []
    for c in db.add.call_args_list:
        obj = c.args[0]
        action = getattr(obj, "action", None)
        if action:
            audit_actions.append(action)
    assert "dry_run" in audit_actions

    # approve audit
    approve_job = SimpleNamespace(
        id=2,
        plan_id=9,
        task_code="SSH_DISABLE_ROOT_LOGIN",
        status=JobStatus.DRY_RUN_SUCCESS.value,
        approved_by=None,
        approved_at=None,
    )
    db2 = MagicMock()
    db2.get.return_value = approve_job
    JobApprovalService(db2).approve(2, reviewed_by="alice")
    approve_actions = [
        getattr(c.args[0], "action", None) for c in db2.add.call_args_list
    ]
    assert "approve" in approve_actions

    # reject audit
    reject_job = SimpleNamespace(
        id=3,
        plan_id=9,
        task_code="SSH_DISABLE_ROOT_LOGIN",
        status=JobStatus.WAITING_DRY_RUN.value,
        approved_by=None,
        approved_at=None,
    )
    db3 = MagicMock()
    db3.get.return_value = reject_job
    JobApprovalService(db3).reject(3, reviewed_by="bob")
    reject_actions = [
        getattr(c.args[0], "action", None) for c in db3.add.call_args_list
    ]
    assert "reject" in reject_actions

    # run audit
    run_job_obj = _job(status=JobStatus.APPROVED.value, targets=[_target("h0")])
    service4, db4 = _service_with_job(run_job_obj)
    service4.run_job(1)
    run_actions = [
        getattr(c.args[0], "action", None) for c in db4.add.call_args_list
    ]
    assert "run" in run_actions
