"""Guarantee MOCK_MODE=true never reaches ansible-runner / shell / SSH."""

from __future__ import annotations

import ast
import inspect
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.config import Settings
from app.services import ansible_execution as ae_mod
from app.services.ansible_execution import (
    AnsibleExecutionError,
    AnsibleExecutionService,
    MockModeViolationError,
)


def _settings(*, mock_mode: bool) -> Settings:
    return Settings(
        mock_mode=mock_mode,
        admin_token="test",
        database_url="postgresql+psycopg://x:x@localhost/x",
    )


FORBIDDEN_IMPORT_NAMES = {
    "ansible_runner",
    "subprocess",
    "paramiko",
    "fabric",
    "invoke",
    "pexpect",
}


def test_ansible_execution_module_has_no_forbidden_top_level_imports() -> None:
    """Static check: ansible_execution.py must not import runner/shell/SSH libs."""
    source = Path(ae_mod.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imported.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom) and node.module:
            # Allow lazy import only inside function bodies (checked separately).
            imported.add(node.module.split(".")[0])
            if "real_ansible_runner" in node.module:
                # Must be nested inside a function (lazy), not module scope.
                assert any(
                    isinstance(parent, ast.FunctionDef)
                    for parent in ast.walk(tree)
                    if any(
                        child is node
                        for child in ast.walk(parent)
                    )
                )
    bad = imported & FORBIDDEN_IMPORT_NAMES
    assert not bad, f"Forbidden imports in ansible_execution.py: {bad}"

    # Ensure the only ImportFrom of real_ansible_runner is inside _execute_real.
    real_imports: list[ast.AST] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module and "real_ansible_runner" in node.module:
            real_imports.append(node)
    assert len(real_imports) == 1

    # Find containing function
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == "AnsibleExecutionService":
            for item in node.body:
                if isinstance(item, ast.FunctionDef) and item.name == "_execute_real":
                    assert any(
                        isinstance(n, ast.ImportFrom)
                        and n.module
                        and "real_ansible_runner" in n.module
                        for n in ast.walk(item)
                    )
                    return
    raise AssertionError("_execute_real not found")



def test_mock_path_source_has_no_subprocess_or_runner_calls() -> None:
    source = inspect.getsource(AnsibleExecutionService._execute_mock)
    for needle in (
        "ansible_runner",
        "subprocess",
        "Popen",
        "os.system",
        "shell=True",
        "paramiko",
        "ansible-playbook",
        "run_with_ansible_runner",
    ):
        assert needle not in source, f"Found forbidden token in _execute_mock: {needle}"


def test_mock_mode_does_not_import_real_adapter(monkeypatch: pytest.MonkeyPatch) -> None:
    # Ensure clean slate
    sys.modules.pop("app.services.real_ansible_runner", None)

    db = MagicMock()
    job = SimpleNamespace(
        id=1,
        task_code="SSH_DISABLE_ROOT_LOGIN",
        status="waiting_dry_run",
        dry_run_status=None,
        started_at=None,
        finished_at=None,
        targets=[],
    )
    catalog = SimpleNamespace(
        task_code="SSH_DISABLE_ROOT_LOGIN",
        is_enabled=True,
        ansible_playbook_path="ssh_disable_root_login.yml",
    )
    service = AnsibleExecutionService(db, settings=_settings(mock_mode=True))
    monkeypatch.setattr(service, "_load_job", lambda _id: job)
    monkeypatch.setattr(service, "_assert_catalog_allows", lambda _code: catalog)

    summary = service.dry_run_job(1)
    assert summary.mock_mode is True
    assert summary.job_status == "dry_run_success"
    assert "app.services.real_ansible_runner" not in sys.modules
    for name in ("ansible_runner", "paramiko"):
        assert name not in sys.modules


def test_execute_real_blocked_when_mock_mode_true() -> None:
    db = MagicMock()
    service = AnsibleExecutionService(db, settings=_settings(mock_mode=True))
    job = SimpleNamespace(id=9, task_code="SSH_DISABLE_ROOT_LOGIN")
    with pytest.raises(MockModeViolationError) as exc:
        service._execute_real(job=job, mode="apply")
    assert "MOCK_MODE=true" in str(exc.value)
    assert "ansible-runner" in str(exc.value)


def test_mock_mode_rejects_if_real_adapter_already_imported(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import app.services.real_ansible_runner as real_mod  # noqa: F401

    db = MagicMock()
    service = AnsibleExecutionService(db, settings=_settings(mock_mode=True))
    with pytest.raises(MockModeViolationError):
        service._assert_mock_mode_safe()
    # cleanup for other tests
    sys.modules.pop("app.services.real_ansible_runner", None)


def test_real_path_lazy_import_still_not_implemented() -> None:
    db = MagicMock()
    service = AnsibleExecutionService(db, settings=_settings(mock_mode=False))
    job = SimpleNamespace(id=1, task_code="SSH_DISABLE_ROOT_LOGIN")
    with pytest.raises(AnsibleExecutionError) as exc:
        service._execute_real(job=job, mode="dry_run")
    assert "not implemented yet" in str(exc.value)


def test_mock_host_outcome_is_pure_strings() -> None:
    db = MagicMock()
    service = AnsibleExecutionService(db, settings=_settings(mock_mode=True))
    job = SimpleNamespace(task_code="SSH_DISABLE_ROOT_LOGIN")
    target = SimpleNamespace(device_name="host-a", ip_address="10.0.0.1")
    out = service._mock_host_outcome(job=job, target=target, mode="dry_run", index=0)
    assert out.stdout.startswith("PLAY [MOCK")
    assert out.return_code == 0
