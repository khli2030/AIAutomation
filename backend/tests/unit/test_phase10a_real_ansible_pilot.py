"""Phase 10A: real Ansible pilot preparation — safety gates + blocked defaults."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from app.config import Settings, get_settings
from app.constants.job_status import JobStatus
from app.models.audit_log import AuditLog
from app.services.real_ansible_pilot import (
    RealAnsiblePilotError,
    RealAnsiblePilotService,
    build_safety_status,
    can_execute_real_ansible,
)


@pytest.fixture(autouse=True)
def _clear_settings_cache():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _settings(**overrides) -> Settings:
    defaults = dict(
        mock_mode=True,
        real_ansible_enabled=False,
        real_ansible_check_mode_only=True,
        real_ansible_allowed_hosts="",
        real_ansible_allowed_task_codes="",
        real_ansible_inventory_path=None,
        real_ansible_private_key_path=None,
        real_ansible_remote_user=None,
        real_ansible_timeout_seconds=120,
        app_env="development",
        ansible_playbooks_dir="/tmp/playbooks-missing",
        ansible_inventories_dir="/tmp/inventories-missing",
        runner_private_data_dir="/tmp/runner-private",
    )
    defaults.update(overrides)
    return Settings(**defaults)  # type: ignore[arg-type]


def _catalog(*, enabled: bool = True, path: str = "ssh_disable_root_login.yml"):
    return SimpleNamespace(
        task_code="SSH_DISABLE_ROOT_LOGIN",
        is_enabled=enabled,
        ansible_playbook_path=path,
    )


def _job(*, status: str = "waiting_dry_run", hosts: list[str] | None = None):
    targets = [
        SimpleNamespace(device_name=h, environment="test", status="pending")
        for h in (hosts or ["e2e-linux-01"])
    ]
    return SimpleNamespace(
        id=1,
        plan_id=9,
        task_code="SSH_DISABLE_ROOT_LOGIN",
        environment="test",
        status=status,
        dry_run_status=None,
        started_at=None,
        finished_at=None,
        targets=targets,
    )


class ScalarsResult:
    def __init__(self, values):
        self._values = values

    def all(self):
        return self._values

    def first(self):
        return self._values[0] if self._values else None


def test_defaults_remain_safe():
    s = Settings()
    assert s.mock_mode is True
    assert s.real_ansible_enabled is False
    assert s.real_ansible_check_mode_only is True
    assert s.real_ansible_allowed_hosts_list == []
    assert s.real_ansible_allowed_task_codes_list == []
    assert s.real_ansible_timeout_seconds == 120


def test_safety_status_when_real_ansible_disabled():
    status = build_safety_status(_settings())
    assert status.mock_mode is True
    assert status.real_ansible_enabled is False
    assert status.check_mode_only is True
    assert status.allowed_hosts_count == 0
    assert status.allowed_task_codes_count == 0
    assert status.real_execution_available is False
    assert any("REAL_ANSIBLE_ENABLED=false" in r for r in status.reasons)
    assert any("MOCK_MODE=true" in r for r in status.reasons)


def test_connectivity_check_blocked_when_disabled():
    db = MagicMock()
    db.scalars.return_value = ScalarsResult([])
    service = RealAnsiblePilotService(db, settings=_settings())
    result = service.connectivity_check(
        ["e2e-linux-01"], actor="tester", role="admin"
    )
    assert result["ok"] is False
    assert result["blocked"] is True
    assert any("REAL_ANSIBLE_ENABLED=false" in r for r in result["reasons"])
    audits = [
        c.kwargs.get("details", {}).get("event")
        for c in db.add.call_args_list
        if False
    ]
    # write_audit_log adds AuditLog via db.add
    added_events = []
    for call in db.add.call_args_list:
        obj = call.args[0] if call.args else None
        if isinstance(obj, AuditLog):
            import json

            details = json.loads(obj.details or "{}")
            added_events.append(details.get("event"))
    assert "real_connectivity_check_started" in added_events
    assert (
        "real_execution_blocked" in added_events
        or "real_connectivity_check_failed" in added_events
    )


def test_connectivity_check_blocks_non_allowlisted_hosts(tmp_path):
    playbooks = tmp_path / "playbooks"
    playbooks.mkdir()
    (playbooks / "ssh_disable_root_login.yml").write_text("---\n")
    inventories = tmp_path / "inventories"
    inventories.mkdir()
    (inventories / "test.ini").write_text("e2e-linux-01 ansible_host=10.0.0.1\n")

    settings = _settings(
        mock_mode=False,
        real_ansible_enabled=True,
        app_env="lab",
        real_ansible_allowed_hosts="e2e-linux-01",
        real_ansible_allowed_task_codes="SSH_DISABLE_ROOT_LOGIN",
        ansible_playbooks_dir=str(playbooks),
        ansible_inventories_dir=str(inventories),
        runner_private_data_dir=str(tmp_path / "runner"),
    )
    db = MagicMock()
    service = RealAnsiblePilotService(db, settings=settings)
    result = service.connectivity_check(
        ["evil-host.example"], actor="tester", role="admin"
    )
    assert result["ok"] is False
    assert result["blocked"] is True
    assert "evil-host.example" in result.get("blocked_hosts", [])
    assert any("not in REAL_ANSIBLE_ALLOWED_HOSTS" in r for r in result["reasons"])


def test_real_dry_run_blocked_when_disabled():
    db = MagicMock()
    job = _job()
    catalog = _catalog()

    def scalars(stmt):
        # First load job, then catalog, then existing results
        text = str(stmt)
        if "execution_jobs" in text.lower() or "ExecutionJob" in text:
            return ScalarsResult([job])
        if "remediation" in text.lower() or "RemediationCatalog" in text:
            return ScalarsResult([catalog])
        return ScalarsResult([])

    db.scalars.side_effect = scalars
    service = RealAnsiblePilotService(db, settings=_settings())
    with pytest.raises(RealAnsiblePilotError) as exc:
        service.real_dry_run(1, actor="tester", role="admin")
    assert "REAL_ANSIBLE_ENABLED=false" in str(exc.value) or "MOCK_MODE" in str(
        exc.value
    )


def test_real_dry_run_blocked_for_non_allowlisted_hosts(tmp_path):
    playbooks = tmp_path / "playbooks"
    playbooks.mkdir()
    (playbooks / "ssh_disable_root_login.yml").write_text("---\n")
    inventories = tmp_path / "inventories"
    inventories.mkdir()
    (inventories / "test.ini").write_text("x\n")

    settings = _settings(
        mock_mode=False,
        real_ansible_enabled=True,
        app_env="lab",
        real_ansible_allowed_hosts="allowed-host",
        real_ansible_allowed_task_codes="SSH_DISABLE_ROOT_LOGIN",
        ansible_playbooks_dir=str(playbooks),
        ansible_inventories_dir=str(inventories),
        runner_private_data_dir=str(tmp_path / "runner"),
    )
    job = _job(hosts=["not-allowed"])
    catalog = _catalog()
    db = MagicMock()

    def scalars(stmt):
        return ScalarsResult([job]) if job else ScalarsResult([])

    # Alternate job then catalog
    calls = {"n": 0}

    def scalars2(stmt):
        calls["n"] += 1
        if calls["n"] == 1:
            return ScalarsResult([job])
        if calls["n"] == 2:
            return ScalarsResult([catalog])
        return ScalarsResult([])

    db.scalars.side_effect = scalars2
    service = RealAnsiblePilotService(db, settings=settings)
    with pytest.raises(RealAnsiblePilotError) as exc:
        service.real_dry_run(1, actor="tester", role="admin")
    assert "not in REAL_ANSIBLE_ALLOWED_HOSTS" in str(exc.value)


def test_real_dry_run_blocked_for_non_allowlisted_task_code(tmp_path):
    playbooks = tmp_path / "playbooks"
    playbooks.mkdir()
    (playbooks / "ssh_disable_root_login.yml").write_text("---\n")
    inventories = tmp_path / "inventories"
    inventories.mkdir()
    (inventories / "test.ini").write_text("x\n")

    settings = _settings(
        mock_mode=False,
        real_ansible_enabled=True,
        app_env="lab",
        real_ansible_allowed_hosts="e2e-linux-01",
        real_ansible_allowed_task_codes="OTHER_CODE",
        ansible_playbooks_dir=str(playbooks),
        ansible_inventories_dir=str(inventories),
        runner_private_data_dir=str(tmp_path / "runner"),
    )
    job = _job(hosts=["e2e-linux-01"])
    catalog = _catalog()
    db = MagicMock()
    calls = {"n": 0}

    def scalars2(stmt):
        calls["n"] += 1
        if calls["n"] == 1:
            return ScalarsResult([job])
        if calls["n"] == 2:
            return ScalarsResult([catalog])
        return ScalarsResult([])

    db.scalars.side_effect = scalars2
    service = RealAnsiblePilotService(db, settings=settings)
    with pytest.raises(RealAnsiblePilotError) as exc:
        service.real_dry_run(1, actor="tester", role="admin")
    assert "not in REAL_ANSIBLE_ALLOWED_TASK_CODES" in str(exc.value)


def test_real_dry_run_uses_check_mode_only(tmp_path):
    playbooks = tmp_path / "playbooks"
    playbooks.mkdir()
    (playbooks / "ssh_disable_root_login.yml").write_text("---\n")
    inventories = tmp_path / "inventories"
    inventories.mkdir()
    inv = inventories / "lab.ini"
    inv.write_text("e2e-linux-01 ansible_host=10.0.0.1\n")
    key = tmp_path / "lab_key"
    key.write_text("-----BEGIN OPENSSH PRIVATE KEY-----\nlab-test-only\n")

    settings = _settings(
        mock_mode=False,
        real_ansible_enabled=True,
        real_ansible_pilot_mode=True,
        app_env="lab",
        real_ansible_check_mode_only=True,
        real_ansible_allowed_hosts="e2e-linux-01",
        real_ansible_allowed_task_codes="SSH_DISABLE_ROOT_LOGIN",
        real_ansible_inventory_path=str(inv),
        real_ansible_private_key_path=str(key),
        real_ansible_remote_user="labuser",
        ansible_playbooks_dir=str(playbooks),
        ansible_inventories_dir=str(inventories),
        runner_private_data_dir=str(tmp_path / "runner"),
    )
    job = _job(hosts=["e2e-linux-01"])
    catalog = _catalog()
    db = MagicMock()
    calls = {"n": 0}

    def scalars2(stmt):
        calls["n"] += 1
        if calls["n"] == 1:
            return ScalarsResult([job])
        if calls["n"] == 2:
            return ScalarsResult([catalog])
        return ScalarsResult([])

    db.scalars.side_effect = scalars2

    service = RealAnsiblePilotService(db, settings=settings)
    with patch.object(
        service,
        "_run_check_mode_playbook",
        return_value={
            "ok": True,
            "cmdline": "--check",
            "hosts": [
                {
                    "device_name": "e2e-linux-01",
                    "status": "success",
                    "changed": False,
                    "skipped": False,
                    "stdout": "check ok",
                    "stderr": "",
                    "return_code": 0,
                }
            ],
        },
    ) as check_mock:
        result = service.real_dry_run(1, actor="tester", role="admin")
    assert result["check_mode"] is True
    assert result["result_type"] == "real_dry_run"
    assert check_mock.called
    assert "--check" in result["cmdline"]

    # Direct check: ansible-runner is invoked with --check only (no apply).
    import sys
    import types

    runner_mod = types.ModuleType("ansible_runner")
    runner_mod.run = MagicMock(
        return_value=SimpleNamespace(
            status="successful",
            rc=0,
            events=[
                {
                    "event": "runner_on_ok",
                    "event_data": {
                        "host": "e2e-linux-01",
                        "res": {"changed": False},
                    },
                }
            ],
        )
    )
    with patch.dict(sys.modules, {"ansible_runner": runner_mod}):
        out = service._run_check_mode_playbook(
            job=job, catalog=catalog, playbook_rel="ssh_disable_root_login.yml"
        )
    assert out["check_mode"] is True
    assert "--check" in out["cmdline"]
    assert "--check" in str(runner_mod.run.call_args.kwargs.get("cmdline", ""))
    assert "apply" not in str(runner_mod.run.call_args.kwargs.get("cmdline", "")).lower()


def test_can_execute_never_allows_excel_or_ai_without_catalog(tmp_path):
    playbooks = tmp_path / "playbooks"
    playbooks.mkdir()
    (playbooks / "ssh_disable_root_login.yml").write_text("---\n")
    settings = _settings(
        mock_mode=False,
        real_ansible_enabled=True,
        app_env="lab",
        real_ansible_allowed_hosts="e2e-linux-01",
        real_ansible_allowed_task_codes="SSH_DISABLE_ROOT_LOGIN",
        ansible_playbooks_dir=str(playbooks),
        ansible_inventories_dir=str(tmp_path / "inv"),
    )
    gate = can_execute_real_ansible(
        settings=settings,
        job=_job(),
        host="e2e-linux-01",
        task_code="SSH_DISABLE_ROOT_LOGIN",
        mode="dry_run",
        catalog=None,
    )
    assert gate.allowed is False
    assert any("Excel Remediation" in r or "AI" in r for r in gate.reasons)


def test_raw_excel_remediation_never_used_as_playbook(tmp_path):
    """Catalog empty path rejects — remediation text cannot substitute."""
    settings = _settings(
        mock_mode=False,
        real_ansible_enabled=True,
        app_env="lab",
        real_ansible_allowed_hosts="e2e-linux-01",
        real_ansible_allowed_task_codes="SSH_DISABLE_ROOT_LOGIN",
        ansible_playbooks_dir=str(tmp_path / "playbooks"),
        ansible_inventories_dir=str(tmp_path / "inv"),
    )
    (tmp_path / "playbooks").mkdir()
    catalog = _catalog(path="")
    gate = can_execute_real_ansible(
        settings=settings,
        job=_job(),
        host="e2e-linux-01",
        task_code="SSH_DISABLE_ROOT_LOGIN",
        mode="dry_run",
        catalog=catalog,
    )
    assert gate.allowed is False
    assert any("Remediation" in r or "empty" in r.lower() for r in gate.reasons)


def test_ai_suggestions_never_executed(tmp_path):
    settings = _settings(
        mock_mode=False,
        real_ansible_enabled=True,
        app_env="lab",
        real_ansible_allowed_hosts="e2e-linux-01",
        real_ansible_allowed_task_codes="SSH_DISABLE_ROOT_LOGIN",
        ansible_playbooks_dir=str(tmp_path / "playbooks"),
        ansible_inventories_dir=str(tmp_path / "inv"),
    )
    (tmp_path / "playbooks").mkdir()
    gate = can_execute_real_ansible(
        settings=settings,
        job=_job(),
        host="e2e-linux-01",
        task_code="SSH_DISABLE_ROOT_LOGIN",
        mode="dry_run",
        catalog=None,  # AI draft is never a catalog substitute
    )
    assert gate.allowed is False
    assert any("AI" in r for r in gate.reasons)


def test_apply_blocked_when_check_mode_only(tmp_path):
    playbooks = tmp_path / "playbooks"
    playbooks.mkdir()
    (playbooks / "ssh_disable_root_login.yml").write_text("---\n")
    settings = _settings(
        mock_mode=False,
        real_ansible_enabled=True,
        app_env="lab",
        real_ansible_check_mode_only=True,
        real_ansible_allowed_hosts="e2e-linux-01",
        real_ansible_allowed_task_codes="SSH_DISABLE_ROOT_LOGIN",
        ansible_playbooks_dir=str(playbooks),
        ansible_inventories_dir=str(tmp_path / "inv"),
    )
    job = _job(status=JobStatus.APPROVED.value)
    catalog = _catalog()
    gate = can_execute_real_ansible(
        settings=settings,
        job=job,
        host="e2e-linux-01",
        task_code="SSH_DISABLE_ROOT_LOGIN",
        mode="apply",
        catalog=catalog,
    )
    assert gate.allowed is False
    assert any("CHECK_MODE_ONLY" in r for r in gate.reasons)


def test_audit_event_created_when_blocked():
    db = MagicMock()
    job = _job()
    catalog = _catalog()
    calls = {"n": 0}

    def scalars2(stmt):
        calls["n"] += 1
        if calls["n"] == 1:
            return ScalarsResult([job])
        if calls["n"] == 2:
            return ScalarsResult([catalog])
        return ScalarsResult([])

    db.scalars.side_effect = scalars2
    service = RealAnsiblePilotService(db, settings=_settings())
    with pytest.raises(RealAnsiblePilotError):
        service.real_dry_run(1, actor="tester", role="admin")
    events = []
    import json

    for call in db.add.call_args_list:
        obj = call.args[0] if call.args else None
        if isinstance(obj, AuditLog):
            events.append(json.loads(obj.details or "{}").get("event"))
    assert "real_execution_blocked" in events


def test_audit_event_created_for_connectivity_check():
    db = MagicMock()
    service = RealAnsiblePilotService(db, settings=_settings())
    service.connectivity_check(["h1"], actor="tester", role="operator")
    import json

    events = []
    for call in db.add.call_args_list:
        obj = call.args[0] if call.args else None
        if isinstance(obj, AuditLog):
            events.append(json.loads(obj.details or "{}").get("event"))
    assert "real_connectivity_check_started" in events


def test_audit_event_created_for_real_dry_run_success(tmp_path):
    playbooks = tmp_path / "playbooks"
    playbooks.mkdir()
    (playbooks / "ssh_disable_root_login.yml").write_text("---\n")
    inventories = tmp_path / "inventories"
    inventories.mkdir()
    inv = inventories / "lab.ini"
    inv.write_text("e2e-linux-01 ansible_host=10.0.0.1\n")
    key = tmp_path / "lab_key"
    key.write_text("-----BEGIN OPENSSH PRIVATE KEY-----\nlab-test-only\n")

    settings = _settings(
        mock_mode=False,
        real_ansible_enabled=True,
        real_ansible_pilot_mode=True,
        app_env="lab",
        real_ansible_allowed_hosts="e2e-linux-01",
        real_ansible_allowed_task_codes="SSH_DISABLE_ROOT_LOGIN",
        real_ansible_inventory_path=str(inv),
        real_ansible_private_key_path=str(key),
        real_ansible_remote_user="labuser",
        ansible_playbooks_dir=str(playbooks),
        ansible_inventories_dir=str(inventories),
        runner_private_data_dir=str(tmp_path / "runner"),
    )
    job = _job(hosts=["e2e-linux-01"])
    catalog = _catalog()
    db = MagicMock()
    calls = {"n": 0}

    def scalars2(stmt):
        calls["n"] += 1
        if calls["n"] == 1:
            return ScalarsResult([job])
        if calls["n"] == 2:
            return ScalarsResult([catalog])
        return ScalarsResult([])

    db.scalars.side_effect = scalars2
    service = RealAnsiblePilotService(db, settings=settings)
    with patch.object(
        service,
        "_run_check_mode_playbook",
        return_value={
            "ok": True,
            "cmdline": "--check",
            "hosts": [
                {
                    "device_name": "e2e-linux-01",
                    "status": "success",
                    "changed": False,
                    "skipped": False,
                    "stdout": "ok",
                    "stderr": "",
                    "return_code": 0,
                }
            ],
        },
    ):
        service.real_dry_run(1, actor="tester", role="admin")

    import json

    events = []
    for call in db.add.call_args_list:
        obj = call.args[0] if call.args else None
        if isinstance(obj, AuditLog):
            events.append(json.loads(obj.details or "{}").get("event"))
    assert "real_dry_run_started" in events
    assert "real_dry_run_completed" in events


def test_run_without_approval_blocked_by_gate(tmp_path):
    playbooks = tmp_path / "playbooks"
    playbooks.mkdir()
    (playbooks / "ssh_disable_root_login.yml").write_text("---\n")
    settings = _settings(
        mock_mode=False,
        real_ansible_enabled=True,
        real_ansible_check_mode_only=False,
        app_env="lab",
        real_ansible_allowed_hosts="e2e-linux-01",
        real_ansible_allowed_task_codes="SSH_DISABLE_ROOT_LOGIN",
        ansible_playbooks_dir=str(playbooks),
        ansible_inventories_dir=str(tmp_path / "inv"),
    )
    gate = can_execute_real_ansible(
        settings=settings,
        job=_job(status="dry_run_success"),
        host="e2e-linux-01",
        task_code="SSH_DISABLE_ROOT_LOGIN",
        mode="run",
        catalog=_catalog(),
    )
    assert gate.allowed is False
    assert any("approved" in r for r in gate.reasons)
