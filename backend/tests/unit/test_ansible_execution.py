"""Unit tests for AnsibleExecutionService MOCK_MODE design."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.config import Settings
from app.services.ansible_execution import (
    AnsibleExecutionError,
    AnsibleExecutionService,
)


def _settings(*, mock_mode: bool) -> Settings:
    return Settings(
        mock_mode=mock_mode,
        admin_token="test",
        database_url="postgresql+psycopg://x:x@localhost/x",
    )


def test_mock_host_outcome_patterns() -> None:
    db = MagicMock()
    service = AnsibleExecutionService(db, settings=_settings(mock_mode=True))
    job = SimpleNamespace(task_code="SSH_DISABLE_ROOT_LOGIN")
    target = SimpleNamespace(device_name="host-a", ip_address="10.0.0.1")

    dry = service._mock_host_outcome(job=job, target=target, mode="dry_run", index=0)
    assert dry.status == "success"
    assert dry.changed is False
    assert "check mode" in dry.stdout
    assert dry.return_code == 0

    apply = service._mock_host_outcome(job=job, target=target, mode="apply", index=0)
    assert apply.status == "success"
    assert apply.changed is True
    assert "MOCK applied" in apply.stdout

    skipped = service._mock_host_outcome(job=job, target=target, mode="apply", index=4)
    assert skipped.skipped is True
    assert skipped.status == "skipped"

    failed = service._mock_host_outcome(job=job, target=target, mode="apply", index=6)
    assert failed.status == "failed"
    assert failed.return_code == 2
    assert "simulated failure" in failed.stdout


def test_real_path_refuses_when_real_ansible_disabled() -> None:
    db = MagicMock()
    # write_audit_log will call db.add; commit is fine on MagicMock
    service = AnsibleExecutionService(db, settings=_settings(mock_mode=False))
    job = SimpleNamespace(id=1, task_code="SSH_DISABLE_ROOT_LOGIN", environment="test")

    with pytest.raises(AnsibleExecutionError) as exc:
        service._execute_real(job=job, mode="dry_run")
    assert "REAL_ANSIBLE_ENABLED=false" in str(exc.value)


def test_mock_mode_true_cannot_enter_real_path() -> None:
    from app.services.ansible_execution import MockModeViolationError

    db = MagicMock()
    service = AnsibleExecutionService(db, settings=_settings(mock_mode=True))
    job = SimpleNamespace(id=1, task_code="SSH_DISABLE_ROOT_LOGIN")
    with pytest.raises(MockModeViolationError):
        service._execute_real(job=job, mode="dry_run")


def test_mock_mode_default_true() -> None:
    settings = Settings(
        admin_token="t",
        database_url="postgresql+psycopg://x:x@localhost/x",
    )
    assert settings.mock_mode is True


def test_service_exposes_dry_run_and_run_methods() -> None:
    service = AnsibleExecutionService(MagicMock(), settings=_settings(mock_mode=True))
    assert callable(service.dry_run_job)
    assert callable(service.run_job)
