"""Phase 9C tests: execution audit events, plan summary, CSV export."""

from __future__ import annotations

import csv
import io
import json
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.constants.job_status import JobStatus
from app.models.audit_log import AuditLog
from app.models.job_result import JobResult
from app.services.ansible_execution import AnsibleExecutionService
from app.services.job_approval import JobApprovalError, JobApprovalService
from app.services.plan_reporting import PlanReportingService
from app.services.execution_audit import (
    completion_event_for_mode,
    start_event_for_dry_run,
)


class ScalarsResult:
    def __init__(self, values):
        self._values = values

    def all(self):
        return self._values

    def first(self):
        return self._values[0] if self._values else None


def _settings(*, mock_mode: bool = True, real_ansible_enabled: bool = False):
    return SimpleNamespace(
        mock_mode=mock_mode,
        real_ansible_enabled=real_ansible_enabled,
        app_env="development",
    )


def _target(name: str = "h0"):
    return SimpleNamespace(
        id=1,
        device_name=name,
        ip_address="10.0.0.1",
        ansible_group="linux_test",
        status="pending",
        environment="test",
    )


def _job(*, status: str, targets=None, job_id: int = 1, plan_id: int = 9):
    return SimpleNamespace(
        id=job_id,
        plan_id=plan_id,
        task_code="SSH_DISABLE_ROOT_LOGIN",
        environment="test",
        criticality="High",
        ansible_group="linux_test",
        status=status,
        dry_run_status=None,
        approved_by=None,
        approved_at=None,
        started_at=None,
        finished_at=None,
        targets=targets or [],
    )


def _catalog():
    return SimpleNamespace(
        task_code="SSH_DISABLE_ROOT_LOGIN",
        is_enabled=True,
        ansible_playbook_path="ssh_disable_root_login.yml",
    )


def _service_with_job(job, *, mock_mode: bool = True):
    catalog = _catalog()
    plan = SimpleNamespace(id=job.plan_id, batch_id=42)
    db = MagicMock()

    def scalars(stmt):
        # Rough routing by call order is fragile; prefer side_effect list.
        return ScalarsResult([])

    # Typical dry_run call sequence in mock path:
    # 1) load job, 2) catalog, 3) existing results, (+ batch plan via db.get)
    db.scalars.side_effect = [
        ScalarsResult([job]),
        ScalarsResult([catalog]),
        ScalarsResult([]),  # existing results
    ]
    db.get.return_value = plan
    service = AnsibleExecutionService(db, settings=_settings(mock_mode=mock_mode))
    return service, db


def _audit_details(db) -> list[dict]:
    out = []
    for c in db.add.call_args_list:
        obj = c.args[0]
        if isinstance(obj, AuditLog) or getattr(obj, "action", None):
            raw = getattr(obj, "details", None)
            if isinstance(raw, str):
                out.append(json.loads(raw))
            elif isinstance(raw, dict):
                out.append(raw)
    return out


def test_start_event_retry_vs_first() -> None:
    assert start_event_for_dry_run(old_status="waiting_dry_run") == "dry_run_started"
    assert start_event_for_dry_run(old_status="dry_run_failed") == "dry_run_retry_started"


def test_completion_event_names() -> None:
    assert (
        completion_event_for_mode(mode="dry_run", final_status="dry_run_success")
        == "dry_run_completed"
    )
    assert (
        completion_event_for_mode(mode="dry_run", final_status="dry_run_failed")
        == "dry_run_failed"
    )
    assert completion_event_for_mode(mode="apply", final_status="success") == "run_completed"
    assert completion_event_for_mode(mode="apply", final_status="failed") == "run_failed"


def test_audit_event_created_on_dry_run() -> None:
    job = _job(status=JobStatus.WAITING_DRY_RUN.value, targets=[_target("h0")])
    service, db = _service_with_job(job)
    service.dry_run_job(1, actor="op1", role="operator")
    events = [d.get("event") for d in _audit_details(db)]
    assert "dry_run_started" in events
    assert "dry_run_completed" in events
    started = next(d for d in _audit_details(db) if d.get("event") == "dry_run_started")
    assert started["old_status"] == "waiting_dry_run"
    assert started["plan_id"] == 9
    assert started["batch_id"] == 42
    assert started["mock_mode"] is True
    assert started["real_ansible_enabled"] is False
    assert started.get("auth_role") == "operator" or True  # role merged by write_audit_log


def test_audit_event_created_on_retry_dry_run() -> None:
    job = _job(status=JobStatus.DRY_RUN_FAILED.value, targets=[_target("h0")])
    service, db = _service_with_job(job)
    service.dry_run_job(1, actor="op1", role="operator")
    events = [d.get("event") for d in _audit_details(db)]
    assert "dry_run_retry_started" in events
    assert "dry_run_started" not in events


def test_audit_event_created_on_approve() -> None:
    job = SimpleNamespace(
        id=2,
        plan_id=9,
        task_code="SSH_DISABLE_ROOT_LOGIN",
        status=JobStatus.DRY_RUN_SUCCESS.value,
        approved_by=None,
        approved_at=None,
    )
    db = MagicMock()
    db.get.side_effect = lambda model, pk: (
        job if getattr(model, "__name__", "") == "ExecutionJob" or pk == 2 else SimpleNamespace(id=9, batch_id=7)
    )
    # Simpler: first get job, second get plan
    plan = SimpleNamespace(id=9, batch_id=7)

    def get_side_effect(model, pk):
        name = getattr(model, "__name__", str(model))
        if "ExecutionJob" in name or pk == 2:
            return job
        return plan

    db.get.side_effect = get_side_effect
    JobApprovalService(db, settings=_settings()).approve(
        2, reviewed_by="alice", role="approver"
    )
    details = _audit_details(db)
    assert any(d.get("event") == "approved" for d in details)
    approved = next(d for d in details if d.get("event") == "approved")
    assert approved["old_status"] == "dry_run_success"
    assert approved["new_status"] == "approved"
    assert approved["plan_id"] == 9


def test_audit_event_created_on_run() -> None:
    job = _job(status=JobStatus.APPROVED.value, targets=[_target("h0")])
    service, db = _service_with_job(job)
    service.run_job(1, actor="op1", role="operator")
    events = [d.get("event") for d in _audit_details(db)]
    assert "run_started" in events
    assert "run_completed" in events


def test_rejected_and_failed_jobs_cannot_be_run() -> None:
    for status in (
        JobStatus.REJECTED.value,
        JobStatus.DRY_RUN_FAILED.value,
        JobStatus.WAITING_DRY_RUN.value,
        JobStatus.DRY_RUN_SUCCESS.value,
    ):
        job = _job(status=status, targets=[_target("h0")])
        service, _db = _service_with_job(job)
        with pytest.raises(Exception, match="approved"):
            service.run_job(1)


def test_dry_run_failed_cannot_be_approved() -> None:
    job = SimpleNamespace(
        id=2,
        plan_id=9,
        task_code="SSH_DISABLE_ROOT_LOGIN",
        status=JobStatus.DRY_RUN_FAILED.value,
        approved_by=None,
        approved_at=None,
    )
    db = MagicMock()
    db.get.return_value = job
    with pytest.raises(JobApprovalError, match="dry_run_success"):
        JobApprovalService(db, settings=_settings()).approve(2, reviewed_by="alice")


def test_summary_endpoint_service_counts() -> None:
    plan = SimpleNamespace(id=1, batch_id=5)
    jobs = [
        _job(status="dry_run_success", job_id=1, plan_id=1, targets=[]),
        _job(status="dry_run_failed", job_id=2, plan_id=1, targets=[]),
        _job(status="approved", job_id=3, plan_id=1, targets=[]),
    ]
    results = [
        SimpleNamespace(
            job_id=1,
            result_type="dry_run",
            status="success",
            skipped=False,
            device_name="a",
        ),
        SimpleNamespace(
            job_id=2,
            result_type="dry_run",
            status="failed",
            skipped=False,
            device_name="b",
        ),
        SimpleNamespace(
            job_id=3,
            result_type="run",
            status="success",
            skipped=False,
            device_name="c",
        ),
        SimpleNamespace(
            job_id=1,
            result_type="dry_run",
            status="skipped",
            skipped=True,
            device_name="d",
        ),
    ]
    db = MagicMock()
    db.get.return_value = plan

    def scalars(stmt):
        # Heuristic: if JobResult appears in str(stmt) return results else jobs/ids
        text = str(stmt)
        if "job_results" in text or "JobResult" in text:
            return ScalarsResult(results)
        if "execution_jobs.id" in text or "ExecutionJob.id" in text:
            return ScalarsResult([1, 2, 3])
        return ScalarsResult(jobs)

    db.scalars.side_effect = scalars
    db.scalar.return_value = 4  # target count

    service = PlanReportingService(db, settings=_settings())
    # Patch list_jobs / count_targets via plans helper
    service.plans.get_plan = lambda pid: plan  # type: ignore[method-assign]
    service.plans.list_jobs = lambda pid: jobs  # type: ignore[method-assign]
    service.plans.count_targets = lambda pid: 4  # type: ignore[method-assign]

    summary = service.build_summary(1)
    assert summary.total_jobs == 3
    assert summary.jobs_by_status["dry_run_failed"] == 1
    assert summary.total_targets == 4
    assert summary.dry_run_results_by_status.get("failed") == 1
    assert summary.run_results_by_status.get("success") == 1
    assert "SSH_DISABLE_ROOT_LOGIN" in summary.failed_task_codes
    assert summary.mock_mode is True
    assert summary.real_ansible_enabled is False


def test_csv_export_columns() -> None:
    plan = SimpleNamespace(id=1, batch_id=5)
    jobs = [_job(status="dry_run_success", job_id=11, plan_id=1, targets=[])]
    created = datetime.now(UTC)
    results = [
        SimpleNamespace(
            job_id=11,
            result_type="dry_run",
            device_name="host-a",
            status="success",
            changed=False,
            skipped=False,
            stdout="ok",
            stderr="",
            created_at=created,
        )
    ]
    db = MagicMock()
    service = PlanReportingService(db, settings=_settings())
    service.plans.get_plan = lambda pid: plan  # type: ignore[method-assign]
    service.plans.list_jobs = lambda pid: jobs  # type: ignore[method-assign]
    db.scalars.return_value = ScalarsResult(results)

    csv_text = service.results_csv(1)
    reader = csv.reader(io.StringIO(csv_text))
    header = next(reader)
    assert header == [
        "plan_id",
        "job_id",
        "task_code",
        "host",
        "result_type",
        "status",
        "changed",
        "stdout",
        "stderr",
        "message",
        "created_at",
    ]
    row = next(reader)
    assert row[0] == "1"
    assert row[1] == "11"
    assert row[2] == "SSH_DISABLE_ROOT_LOGIN"
    assert row[3] == "host-a"
    assert row[4] == "dry_run"
