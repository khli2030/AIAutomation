"""Phase 10C: single-host lab connectivity + real dry-run pilot."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from app.config import Settings, get_settings
from app.models.audit_log import AuditLog
from app.services.lab_ansible_config import build_pilot_readiness
from app.services.real_ansible_pilot import (
    RealAnsiblePilotError,
    RealAnsiblePilotService,
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
        real_ansible_pilot_mode=False,
        real_ansible_max_hosts_per_run=1,
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


def _lab_files(tmp_path: Path):
    inv = tmp_path / "lab.ini"
    inv.write_text("[lab]\nlab-server-01 ansible_host=10.0.0.10\n")
    key = tmp_path / "id_ed25519"
    key.write_text("-----BEGIN OPENSSH PRIVATE KEY-----\nTEST_ONLY\n")
    playbooks = tmp_path / "playbooks"
    playbooks.mkdir()
    (playbooks / "aide_install.yml").write_text("---\n")
    return inv, key, playbooks


def _catalog():
    return SimpleNamespace(
        task_code="AIDE_INSTALL",
        is_enabled=True,
        ansible_playbook_path="aide_install.yml",
    )


def _job(*, hosts: list[str], status: str = "waiting_dry_run"):
    targets = [
        SimpleNamespace(device_name=h, environment="test", status="pending")
        for h in hosts
    ]
    return SimpleNamespace(
        id=1,
        plan_id=9,
        task_code="AIDE_INSTALL",
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


def test_defaults_include_pilot_guards():
    s = Settings()
    assert s.mock_mode is True
    assert s.real_ansible_enabled is False
    assert s.real_ansible_check_mode_only is True
    assert s.real_ansible_pilot_mode is False
    assert s.real_ansible_max_hosts_per_run == 1
    assert s.real_ansible_auth_mode == "explicit"


def test_pilot_readiness_blocked_by_default():
    readiness = build_pilot_readiness(_settings())
    assert readiness.ready is False
    assert readiness.pilot_mode is False
    assert readiness.max_hosts_per_run == 1
    assert any("PILOT_MODE=false" in e for e in readiness.errors)


def test_pilot_readiness_ready_only_when_all_settings_valid(tmp_path):
    inv, key, playbooks = _lab_files(tmp_path)
    settings = _settings(
        mock_mode=False,
        real_ansible_enabled=True,
        real_ansible_check_mode_only=True,
        real_ansible_pilot_mode=True,
        real_ansible_max_hosts_per_run=1,
        real_ansible_allowed_hosts="lab-server-01",
        real_ansible_allowed_task_codes="AIDE_INSTALL",
        real_ansible_inventory_path=str(inv),
        real_ansible_private_key_path=str(key),
        real_ansible_remote_user="labuser",
        ansible_playbooks_dir=str(playbooks),
        app_env="lab",
    )
    readiness = build_pilot_readiness(
        settings, known_task_codes=["AIDE_INSTALL"]
    )
    assert readiness.ready is True
    assert readiness.errors == []
    assert readiness.pilot_mode is True
    assert readiness.max_hosts_per_run == 1


def test_connectivity_blocks_more_than_max_hosts(tmp_path):
    inv, key, playbooks = _lab_files(tmp_path)
    settings = _settings(
        mock_mode=False,
        real_ansible_enabled=True,
        real_ansible_pilot_mode=True,
        real_ansible_max_hosts_per_run=1,
        real_ansible_allowed_hosts="lab-server-01,lab-server-02",
        real_ansible_allowed_task_codes="AIDE_INSTALL",
        real_ansible_inventory_path=str(inv),
        real_ansible_private_key_path=str(key),
        real_ansible_remote_user="labuser",
        ansible_playbooks_dir=str(playbooks),
        app_env="lab",
    )
    db = MagicMock()
    service = RealAnsiblePilotService(db, settings=settings)
    result = service.connectivity_check(
        ["lab-server-01", "lab-server-02"],
        actor="t",
        role="admin",
        known_task_codes=["AIDE_INSTALL"],
    )
    assert result["blocked"] is True
    assert any("MAX_HOSTS_PER_RUN" in r for r in result["reasons"])


def test_real_dry_run_blocks_job_with_more_than_max_hosts(tmp_path):
    inv, key, playbooks = _lab_files(tmp_path)
    settings = _settings(
        mock_mode=False,
        real_ansible_enabled=True,
        real_ansible_pilot_mode=True,
        real_ansible_max_hosts_per_run=1,
        real_ansible_allowed_hosts="lab-server-01,lab-server-02",
        real_ansible_allowed_task_codes="AIDE_INSTALL",
        real_ansible_inventory_path=str(inv),
        real_ansible_private_key_path=str(key),
        real_ansible_remote_user="labuser",
        ansible_playbooks_dir=str(playbooks),
        app_env="lab",
    )
    job = _job(hosts=["lab-server-01", "lab-server-02"])
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
        service.real_dry_run(1, actor="t", role="admin")
    assert "MAX_HOSTS_PER_RUN" in str(exc.value) or "targets" in str(exc.value)


def test_real_dry_run_blocks_non_allowlisted_host(tmp_path):
    inv, key, playbooks = _lab_files(tmp_path)
    settings = _settings(
        mock_mode=False,
        real_ansible_enabled=True,
        real_ansible_pilot_mode=True,
        real_ansible_allowed_hosts="lab-server-01",
        real_ansible_allowed_task_codes="AIDE_INSTALL",
        real_ansible_inventory_path=str(inv),
        real_ansible_private_key_path=str(key),
        real_ansible_remote_user="labuser",
        ansible_playbooks_dir=str(playbooks),
        app_env="lab",
    )
    job = _job(hosts=["evil-host"])
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
        service.real_dry_run(1, actor="t", role="admin")
    assert "not in REAL_ANSIBLE_ALLOWED_HOSTS" in str(exc.value)


def test_real_dry_run_blocks_non_allowlisted_task_code(tmp_path):
    inv, key, playbooks = _lab_files(tmp_path)
    settings = _settings(
        mock_mode=False,
        real_ansible_enabled=True,
        real_ansible_pilot_mode=True,
        real_ansible_allowed_hosts="lab-server-01",
        real_ansible_allowed_task_codes="SSH_MAX_AUTH_TRIES",
        real_ansible_inventory_path=str(inv),
        real_ansible_private_key_path=str(key),
        real_ansible_remote_user="labuser",
        ansible_playbooks_dir=str(playbooks),
        app_env="lab",
    )
    job = _job(hosts=["lab-server-01"])
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
        service.real_dry_run(1, actor="t", role="admin")
    assert "not in REAL_ANSIBLE_ALLOWED_TASK_CODES" in str(exc.value)


def test_real_dry_run_remains_check_mode_only(tmp_path):
    inv, key, playbooks = _lab_files(tmp_path)
    settings = _settings(
        mock_mode=False,
        real_ansible_enabled=True,
        real_ansible_pilot_mode=True,
        real_ansible_check_mode_only=True,
        real_ansible_allowed_hosts="lab-server-01",
        real_ansible_allowed_task_codes="AIDE_INSTALL",
        real_ansible_inventory_path=str(inv),
        real_ansible_private_key_path=str(key),
        real_ansible_remote_user="labuser",
        ansible_playbooks_dir=str(playbooks),
        runner_private_data_dir=str(tmp_path / "runner"),
        app_env="lab",
    )
    job = _job(hosts=["lab-server-01"])
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
                    "device_name": "lab-server-01",
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
        result = service.real_dry_run(1, actor="t", role="admin")
    assert result["check_mode"] is True
    assert result["result_type"] == "real_dry_run"
    assert "--check" in result["cmdline"]


def test_no_apply_endpoint_exists():
    from app.api import execution_jobs

    paths = []
    for route in execution_jobs.router.routes:
        methods = getattr(route, "methods", set()) or set()
        path = getattr(route, "path", "")
        for m in methods:
            paths.append(f"{m} {path}")
    assert not any("/apply" in p for p in paths)
    assert not any(p.endswith("/real-run") for p in paths)
    assert any("POST /{job_id}/real-dry-run" in p for p in paths)


def test_audit_event_created_for_blocked_pilot_action():
    db = MagicMock()
    service = RealAnsiblePilotService(db, settings=_settings())
    result = service.connectivity_check(["h1"], actor="t", role="admin")
    assert result["blocked"] is True
    events = []
    for call in db.add.call_args_list:
        obj = call.args[0] if call.args else None
        if isinstance(obj, AuditLog):
            events.append(json.loads(obj.details or "{}").get("event"))
    assert "real_connectivity_check_started" in events
    assert "real_execution_blocked" in events


def test_audit_event_created_for_connectivity_check():
    db = MagicMock()
    service = RealAnsiblePilotService(db, settings=_settings())
    service.connectivity_check(["h1"], actor="tester", role="operator")
    events = []
    for call in db.add.call_args_list:
        obj = call.args[0] if call.args else None
        if isinstance(obj, AuditLog):
            events.append(json.loads(obj.details or "{}").get("event"))
    assert "real_connectivity_check_started" in events


def test_audit_event_created_for_real_dry_run(tmp_path):
    inv, key, playbooks = _lab_files(tmp_path)
    settings = _settings(
        mock_mode=False,
        real_ansible_enabled=True,
        real_ansible_pilot_mode=True,
        real_ansible_allowed_hosts="lab-server-01",
        real_ansible_allowed_task_codes="AIDE_INSTALL",
        real_ansible_inventory_path=str(inv),
        real_ansible_private_key_path=str(key),
        real_ansible_remote_user="labuser",
        ansible_playbooks_dir=str(playbooks),
        runner_private_data_dir=str(tmp_path / "runner"),
        app_env="lab",
    )
    job = _job(hosts=["lab-server-01"])
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
                    "device_name": "lab-server-01",
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
        service.real_dry_run(1, actor="t", role="admin")
    events = []
    for call in db.add.call_args_list:
        obj = call.args[0] if call.args else None
        if isinstance(obj, AuditLog):
            events.append(json.loads(obj.details or "{}").get("event"))
    assert "real_dry_run_started" in events
    assert "real_dry_run_completed" in events


def test_pilot_mode_required_for_execution(tmp_path):
    inv, key, playbooks = _lab_files(tmp_path)
    settings = _settings(
        mock_mode=False,
        real_ansible_enabled=True,
        real_ansible_pilot_mode=False,
        real_ansible_allowed_hosts="lab-server-01",
        real_ansible_allowed_task_codes="AIDE_INSTALL",
        real_ansible_inventory_path=str(inv),
        real_ansible_private_key_path=str(key),
        real_ansible_remote_user="labuser",
        ansible_playbooks_dir=str(playbooks),
        app_env="lab",
    )
    gate = can_execute_real_ansible(
        settings=settings,
        job=None,
        host="lab-server-01",
        task_code=None,
        mode="connectivity",
        known_task_codes=["AIDE_INSTALL"],
        host_count=1,
    )
    assert gate.allowed is False
    assert any("PILOT_MODE=false" in r for r in gate.reasons)
