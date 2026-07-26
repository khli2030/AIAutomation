"""Phase 10C: REAL_ANSIBLE_AUTH_MODE=ssh_config vs explicit."""

from __future__ import annotations

import sys
import types
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from app.config import Settings, get_settings
from app.services.lab_ansible_config import (
    build_lab_config_preview,
    build_pilot_readiness,
)
from app.services.real_ansible_pilot import (
    RealAnsiblePilotService,
    build_safety_status,
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
        real_ansible_auth_mode="explicit",
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


def _lab_files(tmp_path: Path) -> tuple[Path, Path, Path]:
    inv = tmp_path / "lab.ini"
    inv.write_text("[lab]\nlab-server-01 ansible_host=10.0.0.1\n")
    key = tmp_path / "id_ed25519"
    key.write_text("-----BEGIN OPENSSH PRIVATE KEY-----\nfake\n-----END OPENSSH PRIVATE KEY-----\n")
    playbooks = tmp_path / "playbooks"
    playbooks.mkdir()
    (playbooks / "aide_install.yml").write_text("---\n- hosts: all\n  tasks: []\n")
    return inv, key, playbooks


def test_auth_mode_defaults_to_explicit():
    s = Settings()
    assert s.real_ansible_auth_mode == "explicit"
    assert s.real_ansible_auth_mode_normalized == "explicit"


def test_ssh_config_auth_does_not_require_remote_user(tmp_path):
    inv, _key, playbooks = _lab_files(tmp_path)
    settings = _settings(
        mock_mode=False,
        real_ansible_enabled=True,
        real_ansible_check_mode_only=True,
        real_ansible_pilot_mode=True,
        real_ansible_auth_mode="ssh_config",
        real_ansible_allowed_hosts="lab-server-01",
        real_ansible_allowed_task_codes="AIDE_INSTALL",
        real_ansible_inventory_path=str(inv),
        real_ansible_private_key_path=None,
        real_ansible_remote_user=None,
        ansible_playbooks_dir=str(playbooks),
        app_env="lab",
    )
    preview = build_lab_config_preview(
        settings, known_task_codes=["AIDE_INSTALL"]
    )
    assert preview.auth_mode == "ssh_config"
    assert preview.auth_source == "ssh_config"
    assert preview.remote_user_configured is False
    assert preview.private_key_configured is False
    assert preview.pilot_ready is True
    assert not any("REMOTE_USER" in e for e in preview.validation_errors)
    assert not any("PRIVATE_KEY" in e for e in preview.pilot_readiness_errors)


def test_ssh_config_auth_does_not_require_private_key(tmp_path):
    inv, _key, playbooks = _lab_files(tmp_path)
    settings = _settings(
        mock_mode=False,
        real_ansible_enabled=True,
        real_ansible_check_mode_only=True,
        real_ansible_pilot_mode=True,
        real_ansible_auth_mode="ssh_config",
        real_ansible_allowed_hosts="lab-server-01",
        real_ansible_allowed_task_codes="AIDE_INSTALL",
        real_ansible_inventory_path=str(inv),
        real_ansible_private_key_path=None,
        real_ansible_remote_user=None,
        ansible_playbooks_dir=str(playbooks),
        app_env="lab",
    )
    readiness = build_pilot_readiness(
        settings, known_task_codes=["AIDE_INSTALL"]
    )
    assert readiness.ready is True
    assert readiness.auth_mode == "ssh_config"
    assert readiness.private_key_configured is False


def test_ssh_config_still_blocks_empty_allowlists(tmp_path):
    inv, _key, _playbooks = _lab_files(tmp_path)
    settings = _settings(
        mock_mode=False,
        real_ansible_enabled=True,
        real_ansible_pilot_mode=True,
        real_ansible_auth_mode="ssh_config",
        real_ansible_allowed_hosts="",
        real_ansible_allowed_task_codes="",
        real_ansible_inventory_path=str(inv),
        app_env="lab",
    )
    preview = build_lab_config_preview(settings)
    assert preview.pilot_ready is False
    assert any("ALLOWED_HOSTS is empty" in e for e in preview.validation_errors)
    assert any(
        "ALLOWED_TASK_CODES is empty" in e for e in preview.validation_errors
    )


def test_ssh_config_still_blocks_non_allowlisted_hosts(tmp_path):
    inv, _key, playbooks = _lab_files(tmp_path)
    settings = _settings(
        mock_mode=False,
        real_ansible_enabled=True,
        real_ansible_pilot_mode=True,
        real_ansible_auth_mode="ssh_config",
        real_ansible_allowed_hosts="lab-server-01",
        real_ansible_allowed_task_codes="AIDE_INSTALL",
        real_ansible_inventory_path=str(inv),
        ansible_playbooks_dir=str(playbooks),
        app_env="lab",
    )
    db = MagicMock()
    service = RealAnsiblePilotService(db, settings=settings)
    result = service.connectivity_check(
        ["evil-host"],
        actor="t",
        role="admin",
        known_task_codes=["AIDE_INSTALL"],
    )
    assert result["blocked"] is True
    assert any("not in REAL_ANSIBLE_ALLOWED_HOSTS" in r for r in result["reasons"])


def test_ssh_config_still_enforces_max_hosts(tmp_path):
    inv, _key, playbooks = _lab_files(tmp_path)
    settings = _settings(
        mock_mode=False,
        real_ansible_enabled=True,
        real_ansible_pilot_mode=True,
        real_ansible_auth_mode="ssh_config",
        real_ansible_max_hosts_per_run=1,
        real_ansible_allowed_hosts="lab-server-01,lab-server-02",
        real_ansible_allowed_task_codes="AIDE_INSTALL",
        real_ansible_inventory_path=str(inv),
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


def test_explicit_auth_still_requires_remote_user(tmp_path):
    inv, key, playbooks = _lab_files(tmp_path)
    settings = _settings(
        mock_mode=False,
        real_ansible_enabled=True,
        real_ansible_auth_mode="explicit",
        real_ansible_allowed_hosts="lab-server-01",
        real_ansible_allowed_task_codes="AIDE_INSTALL",
        real_ansible_inventory_path=str(inv),
        real_ansible_private_key_path=str(key),
        real_ansible_remote_user=None,
        ansible_playbooks_dir=str(playbooks),
        app_env="lab",
    )
    preview = build_lab_config_preview(
        settings, known_task_codes=["AIDE_INSTALL"]
    )
    assert preview.auth_mode == "explicit"
    assert preview.remote_user_configured is False
    assert any("REMOTE_USER missing" in e for e in preview.validation_errors)


def test_ssh_config_does_not_inject_user_or_key_on_ping(tmp_path):
    inv, key, playbooks = _lab_files(tmp_path)
    settings = _settings(
        mock_mode=False,
        real_ansible_enabled=True,
        real_ansible_pilot_mode=True,
        real_ansible_auth_mode="ssh_config",
        real_ansible_allowed_hosts="lab-server-01",
        real_ansible_allowed_task_codes="AIDE_INSTALL",
        real_ansible_inventory_path=str(inv),
        # Even if set, ssh_config must not inject them.
        real_ansible_private_key_path=str(key),
        real_ansible_remote_user="labuser",
        ansible_playbooks_dir=str(playbooks),
        runner_private_data_dir=str(tmp_path / "runner"),
        app_env="lab",
    )
    db = MagicMock()
    service = RealAnsiblePilotService(db, settings=settings)
    captured: dict = {}

    class FakeRunner:
        status = "successful"
        stdout = "pong"
        stderr = ""

    def fake_run(**kwargs):
        captured.update(kwargs)
        return FakeRunner()

    runner_mod = types.ModuleType("ansible_runner")
    runner_mod.run = fake_run  # type: ignore[attr-defined]
    with patch.dict(sys.modules, {"ansible_runner": runner_mod}):
        out = service._run_ping(["lab-server-01"])

    assert out["ok"] is True
    cmdline = str(captured.get("cmdline") or "")
    assert "--user" not in cmdline
    assert "--private-key" not in cmdline
    assert "labuser" not in cmdline
    assert str(key) not in cmdline


def test_ssh_config_real_dry_run_cmdline_check_only_no_user_key(tmp_path):
    inv, key, playbooks = _lab_files(tmp_path)
    settings = _settings(
        mock_mode=False,
        real_ansible_enabled=True,
        real_ansible_check_mode_only=True,
        real_ansible_pilot_mode=True,
        real_ansible_auth_mode="ssh_config",
        real_ansible_allowed_hosts="lab-server-01",
        real_ansible_allowed_task_codes="AIDE_INSTALL",
        real_ansible_inventory_path=str(inv),
        real_ansible_private_key_path=str(key),
        real_ansible_remote_user="labuser",
        ansible_playbooks_dir=str(playbooks),
        runner_private_data_dir=str(tmp_path / "runner"),
        app_env="lab",
    )
    catalog = SimpleNamespace(
        task_code="AIDE_INSTALL",
        is_enabled=True,
        ansible_playbook_path="aide_install.yml",
    )
    job = SimpleNamespace(
        id=1,
        plan_id=1,
        task_code="AIDE_INSTALL",
        status="waiting_dry_run",
        environment="lab",
        targets=[SimpleNamespace(device_name="lab-server-01")],
    )
    db = MagicMock()
    service = RealAnsiblePilotService(db, settings=settings)
    captured: dict = {}

    class FakeHost:
        def __init__(self):
            self.device_name = "lab-server-01"
            self.status = "ok"
            self.changed = False
            self.skipped = False
            self.failed = False
            self.unreachable = False
            self.msg = ""
            self.stdout = "ok"
            self.stderr = ""
            self.return_code = 0

    class FakeRunner:
        status = "successful"
        rc = 0
        stdout = "ok"
        stderr = ""
        events = []

    def fake_run(**kwargs):
        captured.update(kwargs)
        return FakeRunner()

    runner_mod = types.ModuleType("ansible_runner")
    runner_mod.run = fake_run  # type: ignore[attr-defined]
    with patch.dict(sys.modules, {"ansible_runner": runner_mod}):
        with patch(
            "app.services.real_ansible_runner._parse_host_events",
            return_value=[FakeHost()],
        ):
            result = service._run_check_mode_playbook(
                job=job,
                catalog=catalog,
                playbook_rel="aide_install.yml",
            )

    assert result["check_mode"] is True
    assert "--check" in result["cmdline"]
    assert "--user" not in result["cmdline"]
    assert "--private-key" not in result["cmdline"]
    assert "labuser" not in result["cmdline"]
    assert str(key) not in result["cmdline"]


def test_no_secrets_in_safety_status_or_lab_config_preview(tmp_path):
    inv, key, playbooks = _lab_files(tmp_path)
    settings = _settings(
        mock_mode=False,
        real_ansible_enabled=True,
        real_ansible_pilot_mode=True,
        real_ansible_auth_mode="explicit",
        real_ansible_allowed_hosts="lab-server-01",
        real_ansible_allowed_task_codes="AIDE_INSTALL",
        real_ansible_inventory_path=str(inv),
        real_ansible_private_key_path=str(key),
        real_ansible_remote_user="labuser",
        ansible_playbooks_dir=str(playbooks),
        app_env="lab",
    )
    with patch(
        "app.services.real_ansible_pilot.ansible_runner_available",
        return_value=(True, "ok"),
    ):
        status = build_safety_status(
            settings, known_task_codes=["AIDE_INSTALL"]
        ).to_dict()
    preview = build_lab_config_preview(
        settings, known_task_codes=["AIDE_INSTALL"]
    ).to_dict()
    readiness = build_pilot_readiness(
        settings, known_task_codes=["AIDE_INSTALL"]
    ).to_dict()

    for payload in (status, preview, readiness):
        blob = str(payload)
        assert "BEGIN OPENSSH" not in blob
        assert "PRIVATE KEY" not in blob
        assert str(key) not in blob
        assert "/var/lib/compliance/keys" not in blob
        assert payload.get("auth_mode") in {"explicit", "ssh_config"}
        assert payload.get("auth_source") in {"explicit", "ssh_config"}
        assert "real_ansible_remote_user" not in payload
        assert "real_ansible_private_key_path" not in payload
        assert "private_key_path" not in payload
        assert "inventory_path" not in payload
