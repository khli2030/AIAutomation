"""Phase 10B: lab inventory + controlled connectivity pilot."""

from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest

from app.config import Settings, get_settings
from app.models.audit_log import AuditLog
from app.services.ansible_env_parse import (
    TIMEOUT_MAX_SECONDS,
    TIMEOUT_MIN_SECONDS,
    clamp_timeout_seconds,
    parse_csv_allowlist,
)
from app.services.lab_ansible_config import build_lab_config_preview
from app.services.real_ansible_pilot import (
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


def _lab_files(tmp_path):
    inv = tmp_path / "lab.ini"
    inv.write_text("[lab]\nlab-server-01 ansible_host=10.0.0.10\n")
    key = tmp_path / "id_ed25519"
    key.write_text("-----BEGIN OPENSSH PRIVATE KEY-----\nTEST_ONLY\n")
    return inv, key


def test_defaults_unchanged():
    s = Settings()
    assert s.mock_mode is True
    assert s.real_ansible_enabled is False
    assert s.real_ansible_check_mode_only is True
    assert s.real_ansible_allowed_hosts_list == []
    assert s.real_ansible_allowed_task_codes_list == []


def test_csv_allowlist_parsing():
    assert parse_csv_allowlist("lab-server-01, 10.10.10.15 ,lab-server-01") == [
        "lab-server-01",
        "10.10.10.15",
    ]
    assert parse_csv_allowlist("AIDE_INSTALL,SSH_MAX_AUTH_TRIES") == [
        "AIDE_INSTALL",
        "SSH_MAX_AUTH_TRIES",
    ]


def test_timeout_bounds_validated():
    n, errs = clamp_timeout_seconds(5)
    assert n == TIMEOUT_MIN_SECONDS
    assert errs
    n, errs = clamp_timeout_seconds(9999)
    assert n == TIMEOUT_MAX_SECONDS
    assert errs
    n, errs = clamp_timeout_seconds(120)
    assert n == 120
    assert errs == []
    s = _settings(real_ansible_timeout_seconds=3)
    assert s.real_ansible_timeout_seconds == TIMEOUT_MIN_SECONDS


def test_lab_config_preview_hides_secrets(tmp_path):
    inv, key = _lab_files(tmp_path)
    settings = _settings(
        mock_mode=False,
        real_ansible_enabled=True,
        real_ansible_pilot_mode=True,
        app_env="lab",
        real_ansible_allowed_hosts="lab-server-01",
        real_ansible_allowed_task_codes="AIDE_INSTALL,SSH_MAX_AUTH_TRIES",
        real_ansible_inventory_path=str(inv),
        real_ansible_private_key_path=str(key),
        real_ansible_remote_user="labuser",
    )
    preview = build_lab_config_preview(
        settings, known_task_codes=["AIDE_INSTALL", "SSH_MAX_AUTH_TRIES"]
    )
    payload = preview.to_dict()
    blob = json.dumps(payload)
    assert "BEGIN OPENSSH" not in blob
    assert "TEST_ONLY" not in blob
    assert str(key) not in blob  # path contents / secret path not returned
    assert "private_key_configured" in payload
    assert payload["private_key_configured"] is True
    assert payload["inventory_path_configured"] is True
    assert payload["remote_user_configured"] is True
    assert "lab-server-01" in payload["allowed_hosts"]
    assert payload["validation_status"] == "ok"
    assert payload["pilot_ready"] is True


def test_empty_allowlists_block_real_execution():
    preview = build_lab_config_preview(_settings())
    assert preview.connectivity_allowed is False
    assert preview.validation_status == "blocked"
    assert any("ALLOWED_HOSTS is empty" in e for e in preview.validation_errors)
    gate = can_execute_real_ansible(
        settings=_settings(),
        job=None,
        host="any",
        task_code="AIDE_INSTALL",
        mode="connectivity",
    )
    assert gate.allowed is False


def test_unknown_task_code_blocks(tmp_path):
    inv, key = _lab_files(tmp_path)
    settings = _settings(
        mock_mode=False,
        real_ansible_enabled=True,
        real_ansible_allowed_hosts="lab-server-01",
        real_ansible_allowed_task_codes="NOT_A_REAL_CODE",
        real_ansible_inventory_path=str(inv),
        real_ansible_private_key_path=str(key),
        real_ansible_remote_user="labuser",
    )
    preview = build_lab_config_preview(
        settings, known_task_codes=["AIDE_INSTALL", "SSH_MAX_AUTH_TRIES"]
    )
    assert preview.connectivity_allowed is False
    assert any("Unknown task_code" in e for e in preview.validation_errors)


def test_non_allowlisted_host_blocks(tmp_path):
    inv, key = _lab_files(tmp_path)
    settings = _settings(
        mock_mode=False,
        real_ansible_enabled=True,
        real_ansible_allowed_hosts="lab-server-01",
        real_ansible_allowed_task_codes="AIDE_INSTALL",
        real_ansible_inventory_path=str(inv),
        real_ansible_private_key_path=str(key),
        real_ansible_remote_user="labuser",
    )
    gate = can_execute_real_ansible(
        settings=settings,
        job=None,
        host="evil-host",
        task_code=None,
        mode="connectivity",
        known_task_codes=["AIDE_INSTALL"],
    )
    assert gate.allowed is False
    assert any("not in REAL_ANSIBLE_ALLOWED_HOSTS" in r for r in gate.reasons)


def test_missing_inventory_blocks_when_enabled(tmp_path):
    key = tmp_path / "key"
    key.write_text("x")
    settings = _settings(
        mock_mode=False,
        real_ansible_enabled=True,
        real_ansible_allowed_hosts="lab-server-01",
        real_ansible_allowed_task_codes="AIDE_INSTALL",
        real_ansible_inventory_path=str(tmp_path / "missing.ini"),
        real_ansible_private_key_path=str(key),
        real_ansible_remote_user="labuser",
    )
    preview = build_lab_config_preview(
        settings, known_task_codes=["AIDE_INSTALL"]
    )
    assert preview.inventory_path_configured is False
    assert any("INVENTORY_PATH missing" in e for e in preview.validation_errors)


def test_missing_remote_user_blocks_when_enabled(tmp_path):
    inv, key = _lab_files(tmp_path)
    settings = _settings(
        mock_mode=False,
        real_ansible_enabled=True,
        real_ansible_allowed_hosts="lab-server-01",
        real_ansible_allowed_task_codes="AIDE_INSTALL",
        real_ansible_inventory_path=str(inv),
        real_ansible_private_key_path=str(key),
        real_ansible_remote_user=None,
    )
    preview = build_lab_config_preview(
        settings, known_task_codes=["AIDE_INSTALL"]
    )
    assert preview.remote_user_configured is False
    assert any("REMOTE_USER missing" in e for e in preview.validation_errors)


def test_connectivity_check_blocked_by_default():
    db = MagicMock()
    service = RealAnsiblePilotService(db, settings=_settings())
    result = service.connectivity_check(["lab-server-01"], actor="t", role="admin")
    assert result["ok"] is False
    assert result["blocked"] is True
    assert any("REAL_ANSIBLE_ENABLED=false" in r for r in result["reasons"])


def test_connectivity_check_blocks_non_allowlisted_host(tmp_path):
    inv, key = _lab_files(tmp_path)
    settings = _settings(
        mock_mode=False,
        real_ansible_enabled=True,
        app_env="lab",
        real_ansible_allowed_hosts="lab-server-01",
        real_ansible_allowed_task_codes="AIDE_INSTALL",
        real_ansible_inventory_path=str(inv),
        real_ansible_private_key_path=str(key),
        real_ansible_remote_user="labuser",
    )
    db = MagicMock()
    service = RealAnsiblePilotService(db, settings=settings)
    result = service.connectivity_check(
        ["not-allowed"],
        actor="t",
        role="admin",
        known_task_codes=["AIDE_INSTALL"],
    )
    assert result["blocked"] is True
    assert "not-allowed" in result.get("blocked_hosts", [])


def test_audit_event_created_for_blocked_connectivity_check():
    db = MagicMock()
    service = RealAnsiblePilotService(db, settings=_settings())
    service.connectivity_check(["h1"], actor="tester", role="operator")
    events = []
    for call in db.add.call_args_list:
        obj = call.args[0] if call.args else None
        if isinstance(obj, AuditLog):
            events.append(json.loads(obj.details or "{}").get("event"))
    assert "real_connectivity_check_started" in events
    assert "real_execution_blocked" in events


def test_safety_status_reflects_lab_preview_defaults():
    status = build_safety_status(_settings())
    assert status.real_execution_available is False
    assert status.inventory_configured is False
    assert status.private_key_configured is False
    assert status.remote_user_configured is False
