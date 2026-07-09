"""Phase 8C lab-only real Ansible dry-run (check mode) tests."""

from __future__ import annotations

import json
import sys
import types
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.config import Settings, get_settings
from app.constants.job_result_type import JobResultType
from app.models.audit_log import AuditLog
from app.models.job_result import JobResult
from app.services.ansible_execution import (
    AnsibleExecutionError,
    AnsibleExecutionService,
)
from app.services.ansible_safety import RealAnsibleBlockedError
from app.services.real_ansible_runner import run_with_ansible_runner


@pytest.fixture(autouse=True)
def _clear_settings_cache() -> None:
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()
    sys.modules.pop("app.services.real_ansible_runner", None)


def _settings(**kwargs: object) -> Settings:
    defaults: dict[str, object] = {
        "mock_mode": True,
        "real_ansible_enabled": False,
        "app_env": "development",
        "admin_token": "test",
        "database_url": "postgresql+psycopg://x:x@localhost/x",
        "ansible_home": str(Path("/workspace/ansible")),
        "ansible_playbooks_dir": str(Path("/workspace/ansible/playbooks")),
        "ansible_inventories_dir": str(Path("/workspace/ansible/inventories")),
        "upload_dir": "/tmp/compliance-uploads-8c",
        "runner_private_data_dir": "/tmp/compliance-runner-8c",
        "tmp_inventory_dir": "/tmp/compliance-tmp-inv-8c",
    }
    defaults.update(kwargs)
    return Settings(**defaults)  # type: ignore[arg-type]


def _lab_dirs(tmp_path: Path) -> tuple[Path, Path, Settings]:
    playbooks = tmp_path / "playbooks"
    inventories = tmp_path / "inventories"
    home = tmp_path / "ansible"
    playbooks.mkdir()
    inventories.mkdir()
    home.mkdir()
    (playbooks / "ok.yml").write_text("---\n- hosts: all\n  tasks: []\n")
    (inventories / "test.ini").write_text("[linux_test]\nhost-a\n")
    settings = _settings(
        mock_mode=False,
        real_ansible_enabled=True,
        app_env="lab",
        ansible_home=str(home),
        ansible_playbooks_dir=str(playbooks),
        ansible_inventories_dir=str(inventories),
        upload_dir=str(tmp_path / "uploads"),
        runner_private_data_dir=str(tmp_path / "runner"),
        tmp_inventory_dir=str(tmp_path / "tmpinv"),
    )
    return playbooks, inventories, settings


def _install_fake_runner(monkeypatch: pytest.MonkeyPatch, *, events: list | None = None, status: str = "successful", rc: int = 0):
    calls: list[dict] = []

    class _FakeRunner:
        def __init__(self) -> None:
            self.status = status
            self.rc = rc
            self.events = events or []

    def _run(**kwargs):  # type: ignore[no-untyped-def]
        calls.append(kwargs)
        return _FakeRunner()

    fake = types.ModuleType("ansible_runner")
    fake.run = _run  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "ansible_runner", fake)
    monkeypatch.setattr(
        "app.services.ansible_safety.ansible_runner_available",
        lambda: (True, "ansible-runner package found (not imported)"),
    )
    return calls


def test_defaults_remain_safe() -> None:
    settings = Settings(
        admin_token="t",
        database_url="postgresql+psycopg://x:x@localhost/x",
    )
    assert settings.mock_mode is True
    assert settings.real_ansible_enabled is False


def test_mock_mode_true_uses_mock_only(monkeypatch: pytest.MonkeyPatch) -> None:
    sys.modules.pop("app.services.real_ansible_runner", None)
    db = MagicMock()
    job = SimpleNamespace(
        id=1,
        task_code="SSH_DISABLE_ROOT_LOGIN",
        status="waiting_dry_run",
        dry_run_status=None,
        started_at=None,
        finished_at=None,
        environment="test",
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
    assert "app.services.real_ansible_runner" not in sys.modules


def test_real_ansible_disabled_blocks_real_dry_run() -> None:
    db = MagicMock()
    service = AnsibleExecutionService(
        db,
        settings=_settings(mock_mode=False, real_ansible_enabled=False, app_env="lab"),
    )
    job = SimpleNamespace(id=1, task_code="T", environment="lab", targets=[])
    with pytest.raises(AnsibleExecutionError, match="REAL_ANSIBLE_ENABLED=false"):
        service._execute_real(job=job, mode="dry_run", actor="role:operator", role="operator")
    audit = db.add.call_args[0][0]
    details = json.loads(audit.details)
    assert details["event"] == "real_dry_run_blocked"


def test_app_env_production_blocks_real_dry_run() -> None:
    db = MagicMock()
    service = AnsibleExecutionService(
        db,
        settings=_settings(
            mock_mode=False, real_ansible_enabled=True, app_env="production"
        ),
    )
    job = SimpleNamespace(id=2, task_code="T", environment="lab", targets=[])
    with pytest.raises(AnsibleExecutionError, match="APP_ENV"):
        service._execute_real(job=job, mode="dry_run", actor="role:admin", role="admin")
    details = json.loads(db.add.call_args[0][0].details)
    assert details["event"] == "real_dry_run_blocked"


@pytest.mark.parametrize("env", ["production", "staging"])
def test_production_staging_targets_block_real_dry_run(
    env: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _playbooks, _inv, settings = _lab_dirs(tmp_path)
    _install_fake_runner(monkeypatch)
    db = MagicMock()
    service = AnsibleExecutionService(db, settings=settings)
    job = SimpleNamespace(
        id=3,
        task_code="T",
        environment=env,
        targets=[SimpleNamespace(device_name="h1", environment=None)],
        ansible_group="linux_test",
        status="waiting_dry_run",
        dry_run_status=None,
        started_at=None,
        finished_at=None,
    )
    catalog = SimpleNamespace(task_code="T", is_enabled=True, ansible_playbook_path="ok.yml")
    with pytest.raises(AnsibleExecutionError, match=env):
        service._execute_real(
            job=job, mode="dry_run", catalog=catalog, actor="role:operator", role="operator"
        )
    events = [
        json.loads(c.args[0].details)["event"]
        for c in db.add.call_args_list
        if isinstance(c.args[0], AuditLog)
    ]
    # Target gates run before started audit — blocked only, no started.
    assert "real_dry_run_blocked" in events
    assert "real_dry_run_started" not in events


def test_lab_dry_run_calls_ansible_runner_check_mode(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _p, _i, settings = _lab_dirs(tmp_path)
    events = [
        {
            "event": "runner_on_ok",
            "event_data": {
                "host": "host-a",
                "res": {"changed": False, "msg": "ok", "rc": 0},
            },
        }
    ]
    calls = _install_fake_runner(monkeypatch, events=events)
    job = SimpleNamespace(
        id=10,
        environment="lab",
        targets=[SimpleNamespace(device_name="host-a")],
        ansible_group="linux_test",
    )
    catalog = SimpleNamespace(task_code="T", is_enabled=True, ansible_playbook_path="ok.yml")
    out = run_with_ansible_runner(
        job=job, mode="dry_run", catalog=catalog, settings=settings
    )
    assert calls, "ansible_runner.run must be called"
    assert calls[0]["cmdline"] == "--check"
    assert calls[0]["limit"] == "host-a"
    assert out["check_mode"] is True
    assert out["used_ai_generated_playbook"] is False
    assert out["used_remediation_text"] is False
    assert out["hosts"][0]["device_name"] == "host-a"
    assert out["hosts"][0]["status"] == "success"


def test_empty_targets_block_unbounded_inventory_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _p, _i, settings = _lab_dirs(tmp_path)
    calls = _install_fake_runner(monkeypatch)
    job = SimpleNamespace(id=99, environment="lab", targets=[])
    catalog = SimpleNamespace(task_code="T", is_enabled=True, ansible_playbook_path="ok.yml")
    with pytest.raises(RealAnsibleBlockedError, match="no targets"):
        run_with_ansible_runner(
            job=job, mode="dry_run", catalog=catalog, settings=settings
        )
    assert calls == []


def test_partial_host_parse_fails_safely(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _p, _i, settings = _lab_dirs(tmp_path)
    events = [
        {
            "event": "runner_on_ok",
            "event_data": {"host": "host-a", "res": {"changed": False, "rc": 0}},
        }
    ]
    _install_fake_runner(monkeypatch, events=events)
    job = SimpleNamespace(
        id=100,
        environment="lab",
        targets=[
            SimpleNamespace(device_name="host-a"),
            SimpleNamespace(device_name="host-b"),
        ],
    )
    catalog = SimpleNamespace(task_code="T", is_enabled=True, ansible_playbook_path="ok.yml")
    with pytest.raises(RealAnsibleBlockedError, match="host-b"):
        run_with_ansible_runner(
            job=job, mode="dry_run", catalog=catalog, settings=settings
        )


def test_runner_level_failure_marks_failed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _p, _i, settings = _lab_dirs(tmp_path)
    events = [
        {
            "event": "runner_on_ok",
            "event_data": {"host": "host-a", "res": {"changed": False, "rc": 0}},
        }
    ]
    _install_fake_runner(monkeypatch, events=events, status="failed", rc=2)
    target = SimpleNamespace(
        device_name="host-a",
        ip_address="10.0.0.1",
        ansible_group="linux_test",
        status="pending",
        environment=None,
    )
    job = SimpleNamespace(
        id=101,
        task_code="T",
        environment="lab",
        ansible_group="linux_test",
        status="waiting_dry_run",
        dry_run_status=None,
        started_at=None,
        finished_at=None,
        targets=[target],
    )
    catalog = SimpleNamespace(task_code="T", is_enabled=True, ansible_playbook_path="ok.yml")
    db = MagicMock()
    service = AnsibleExecutionService(db, settings=settings)
    with pytest.raises(AnsibleExecutionError, match="ansible-runner reported"):
        service._execute_real(
            job=job, mode="dry_run", catalog=catalog, actor="role:operator", role="operator"
        )
    assert job.status == "dry_run_failed"
    events_audit = [
        json.loads(c.args[0].details)["event"]
        for c in db.add.call_args_list
        if isinstance(c.args[0], AuditLog)
    ]
    assert "real_dry_run_started" in events_audit
    assert "real_dry_run_failed" in events_audit


def test_apply_still_blocked(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _p, _i, settings = _lab_dirs(tmp_path)
    calls = _install_fake_runner(monkeypatch)
    job = SimpleNamespace(
        id=11,
        environment="lab",
        targets=[SimpleNamespace(device_name="host-a")],
    )
    catalog = SimpleNamespace(task_code="T", is_enabled=True, ansible_playbook_path="ok.yml")
    with pytest.raises(RealAnsibleBlockedError, match="blocks real apply"):
        run_with_ansible_runner(
            job=job, mode="apply", catalog=catalog, settings=settings
        )
    assert calls == []


def test_no_subprocess_shell_or_playbook_fallback() -> None:
    import ast
    from pathlib import Path as P

    import app.services.real_ansible_runner as real_mod

    src = P(real_mod.__file__).read_text(encoding="utf-8")
    assert "ansible-playbook" in src  # mentioned as forbidden
    assert "import subprocess" not in src
    assert "from subprocess" not in src
    assert "shell=True" not in src
    assert "import paramiko" not in src
    assert "from paramiko" not in src
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if isinstance(node.func.value, ast.Name) and node.func.value.id in {
                "os",
                "subprocess",
            }:
                raise AssertionError(f"Forbidden {node.func.value.id}.{node.func.attr}")


def test_ai_and_remediation_never_used(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _p, _i, settings = _lab_dirs(tmp_path)
    events = [
        {
            "event": "runner_on_ok",
            "event_data": {"host": "host-a", "res": {"changed": False, "rc": 0}},
        }
    ]
    _install_fake_runner(monkeypatch, events=events)
    src = Path(__import__("app.services.real_ansible_runner", fromlist=["x"]).__file__).read_text()
    assert "generated_playbook" in src
    assert "remediation text" in src.lower() or "Remediation text" in src
    job = SimpleNamespace(
        id=12,
        environment="test",
        targets=[SimpleNamespace(device_name="host-a")],
    )
    catalog = SimpleNamespace(task_code="T", is_enabled=True, ansible_playbook_path="ok.yml")
    out = run_with_ansible_runner(
        job=job, mode="dry_run", catalog=catalog, settings=settings
    )
    assert out["used_ai_generated_playbook"] is False
    assert out["used_remediation_text"] is False


def test_execute_real_persists_dry_run_results_and_audits(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _p, _i, settings = _lab_dirs(tmp_path)
    events = [
        {
            "event": "runner_on_ok",
            "event_data": {
                "host": "host-a",
                "res": {"changed": False, "msg": "check ok", "rc": 0},
            },
        }
    ]
    _install_fake_runner(monkeypatch, events=events)

    target = SimpleNamespace(
        device_name="host-a",
        ip_address="10.0.0.1",
        ansible_group="linux_test",
        status="pending",
        environment=None,
    )
    job = SimpleNamespace(
        id=20,
        task_code="SSH_DISABLE_ROOT_LOGIN",
        environment="lab",
        ansible_group="linux_test",
        status="waiting_dry_run",
        dry_run_status=None,
        started_at=None,
        finished_at=None,
        targets=[target],
    )
    catalog = SimpleNamespace(
        task_code="SSH_DISABLE_ROOT_LOGIN",
        is_enabled=True,
        ansible_playbook_path="ok.yml",
    )
    db = MagicMock()
    service = AnsibleExecutionService(db, settings=settings)
    summary = service._execute_real(
        job=job,
        mode="dry_run",
        catalog=catalog,
        actor="role:operator",
        role="operator",
    )
    assert summary.mock_mode is False
    assert summary.job_status == "dry_run_success"
    assert job.status == "dry_run_success"

    results = [
        c.args[0]
        for c in db.add.call_args_list
        if isinstance(c.args[0], JobResult)
    ]
    assert len(results) == 1
    assert results[0].result_type == JobResultType.DRY_RUN.value
    assert results[0].device_name == "host-a"

    audit_events = [
        json.loads(c.args[0].details)["event"]
        for c in db.add.call_args_list
        if isinstance(c.args[0], AuditLog)
    ]
    assert "real_dry_run_started" in audit_events
    assert "real_dry_run_completed" in audit_events


def test_incomplete_host_parse_fails_safely(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _p, _i, settings = _lab_dirs(tmp_path)
    # Expected hosts but no host events → fail safely.
    _install_fake_runner(monkeypatch, events=[])
    job = SimpleNamespace(
        id=21,
        environment="lab",
        targets=[SimpleNamespace(device_name="host-a")],
    )
    catalog = SimpleNamespace(task_code="T", is_enabled=True, ansible_playbook_path="ok.yml")
    with pytest.raises(RealAnsibleBlockedError, match="Per-host event parsing incomplete"):
        run_with_ansible_runner(
            job=job, mode="dry_run", catalog=catalog, settings=settings
        )


def test_disabled_catalog_blocked(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _p, _i, settings = _lab_dirs(tmp_path)
    _install_fake_runner(monkeypatch)
    job = SimpleNamespace(
        id=22,
        environment="lab",
        targets=[SimpleNamespace(device_name="host-a")],
    )
    catalog = SimpleNamespace(task_code="T", is_enabled=False, ansible_playbook_path="ok.yml")
    with pytest.raises(RealAnsibleBlockedError, match="disabled"):
        run_with_ansible_runner(
            job=job, mode="dry_run", catalog=catalog, settings=settings
        )


def test_ansible_runner_only_imported_in_guarded_path() -> None:
    import ast
    from pathlib import Path as P

    import app.services.ansible_execution as ae_mod
    import app.services.real_ansible_runner as real_mod

    ae_src = P(ae_mod.__file__).read_text(encoding="utf-8")
    tree = ast.parse(ae_src)
    # No top-level ansible_runner import in execution facade.
    for node in tree.body:
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            mod = getattr(node, "module", None) or ""
            names = [a.name for a in getattr(node, "names", [])]
            assert "ansible_runner" not in mod
            assert "ansible_runner" not in names

    real_src = P(real_mod.__file__).read_text(encoding="utf-8")
    assert "import ansible_runner" in real_src
    assert '"--check"' in real_src or "'--check'" in real_src
