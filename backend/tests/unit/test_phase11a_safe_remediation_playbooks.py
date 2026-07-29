"""Phase 11A: real safe SSH playbooks + stub blocking."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from app.config import Settings, get_settings
from app.db.seed_remediation_catalog import (
    PHASE11A_IMPLEMENTED_TASK_CODES,
    _with_capability_defaults,
)
from app.services.ansible_safety import RealAnsibleBlockedError
from app.services.playbook_quality import (
    PHASE11A_HIGH_RISK_BLOCKED_TASK_CODES,
    assert_playbook_allowed_for_real_execution,
    catalog_capability_flags,
    is_stub_playbook,
    playbook_has_backup,
    playbook_has_validate,
    playbook_text_is_stub,
)
from app.services.real_ansible_pilot import (
    RealAnsiblePilotError,
    RealAnsiblePilotService,
    can_execute_real_ansible,
)

REPO_PLAYBOOKS = Path("/workspace/ansible/playbooks")

IMPLEMENTED = {
    "SSH_MAX_AUTH_TRIES": "ssh_max_auth_tries.yml",
    "SSH_LOG_LEVEL_INFO": "ssh_log_level_info.yml",
    "SSH_CLIENT_ALIVE_INTERVAL": "ssh_client_alive_interval.yml",
    "SSH_IGNORE_RHOSTS_ENABLE": "ssh_ignore_rhosts_enable.yml",
}

STUB_SAMPLES = [
    "aide_install.yml",
    "rsync_remove.yml",
    "x11_server_remove.yml",
    "set_tmp_nodev.yml",
    "home_partition_nodev.yml",
    "set_selinux_mode.yml",
]


@pytest.fixture(autouse=True)
def _clear_settings_cache():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _settings(**overrides) -> Settings:
    defaults = dict(
        mock_mode=False,
        real_ansible_enabled=True,
        real_ansible_check_mode_only=True,
        real_ansible_pilot_mode=True,
        real_ansible_max_hosts_per_run=1,
        real_ansible_auth_mode="explicit",
        real_ansible_allowed_hosts="lab-server-01",
        real_ansible_allowed_task_codes=",".join(IMPLEMENTED),
        real_ansible_inventory_path=None,
        real_ansible_private_key_path=None,
        real_ansible_remote_user="labuser",
        ansible_playbooks_dir=str(REPO_PLAYBOOKS),
        ansible_inventories_dir="/tmp/inventories-missing",
        runner_private_data_dir="/tmp/runner-private",
        app_env="lab",
    )
    defaults.update(overrides)
    return Settings(**defaults)  # type: ignore[arg-type]


def test_implemented_ssh_playbooks_are_not_stubs():
    for rel in IMPLEMENTED.values():
        path = REPO_PLAYBOOKS / rel
        assert path.is_file(), rel
        text = path.read_text(encoding="utf-8")
        assert not playbook_text_is_stub(text), rel
        assert not is_stub_playbook(path), rel


def test_implemented_playbooks_contain_backup_and_validate():
    for code, rel in IMPLEMENTED.items():
        text = (REPO_PLAYBOOKS / rel).read_text(encoding="utf-8")
        assert playbook_has_backup(text), code
        assert playbook_has_validate(text), code
        assert "sshd -t -f %s" in text, code
        assert "/etc/ssh/sshd_config" in text, code
        assert "serial: 1" in text, code
        assert "ansible.builtin.lineinfile" in text, code
        assert "ansible.builtin.shell" not in text, code
        assert "generated_playbook" not in text
        # Comments may mention Excel/AI only as forbidden sources.
        assert "Never generated from Excel Remediation text or AI drafts" in text
        assert "ansible.builtin.command" in text  # validation only (sshd -t)


def test_expected_ssh_values_present():
    assert "MaxAuthTries {{ ssh_max_auth_tries }}" in (
        REPO_PLAYBOOKS / "ssh_max_auth_tries.yml"
    ).read_text()
    assert "ssh_max_auth_tries: 4" in (
        REPO_PLAYBOOKS / "ssh_max_auth_tries.yml"
    ).read_text()
    assert "LogLevel {{ ssh_log_level }}" in (
        REPO_PLAYBOOKS / "ssh_log_level_info.yml"
    ).read_text()
    assert "ssh_log_level: INFO" in (
        REPO_PLAYBOOKS / "ssh_log_level_info.yml"
    ).read_text()
    assert "ClientAliveInterval {{ ssh_client_alive_interval }}" in (
        REPO_PLAYBOOKS / "ssh_client_alive_interval.yml"
    ).read_text()
    assert "ssh_client_alive_interval: 300" in (
        REPO_PLAYBOOKS / "ssh_client_alive_interval.yml"
    ).read_text()
    assert "IgnoreRhosts {{ ssh_ignore_rhosts }}" in (
        REPO_PLAYBOOKS / "ssh_ignore_rhosts_enable.yml"
    ).read_text()
    assert 'ssh_ignore_rhosts: "yes"' in (
        REPO_PLAYBOOKS / "ssh_ignore_rhosts_enable.yml"
    ).read_text()


def test_stub_playbooks_still_marked_as_stubs():
    for rel in STUB_SAMPLES:
        path = REPO_PLAYBOOKS / rel
        assert path.is_file(), rel
        assert is_stub_playbook(path), rel


def test_stub_playbooks_blocked_from_real_execution():
    settings = _settings()
    with pytest.raises(RealAnsibleBlockedError) as exc:
        assert_playbook_allowed_for_real_execution(
            settings,
            catalog_relative_path="aide_install.yml",
            task_code="AIDE_INSTALL",
        )
    assert exc.value.code == "stub_playbook"
    assert "stub" in exc.value.reason.lower()


def test_high_risk_task_codes_blocked_from_real_execution(tmp_path):
    # Even a non-stub file must not allow high-risk codes in Phase 11A.
    pb = tmp_path / "playbooks"
    pb.mkdir()
    (pb / "rsync_remove.yml").write_text(
        "---\n- hosts: all\n  tasks:\n    - ansible.builtin.debug:\n        msg: fake\n"
    )
    settings = _settings(ansible_playbooks_dir=str(pb))
    with pytest.raises(RealAnsibleBlockedError) as exc:
        assert_playbook_allowed_for_real_execution(
            settings,
            catalog_relative_path="rsync_remove.yml",
            task_code="RSYNC_REMOVE",
        )
    assert exc.value.code == "high_risk_blocked"
    assert "RSYNC_REMOVE" in PHASE11A_HIGH_RISK_BLOCKED_TASK_CODES


def test_implemented_playbooks_allowed_for_real_execution(tmp_path):
    inv = tmp_path / "lab.ini"
    inv.write_text("[lab]\nlab-server-01\n")
    key = tmp_path / "key"
    key.write_text("fake-key\n")
    settings = _settings(
        real_ansible_inventory_path=str(inv),
        real_ansible_private_key_path=str(key),
        real_ansible_allowed_hosts="lab-server-01",
        real_ansible_allowed_task_codes="SSH_MAX_AUTH_TRIES",
    )
    path = assert_playbook_allowed_for_real_execution(
        settings,
        catalog_relative_path="ssh_max_auth_tries.yml",
        task_code="SSH_MAX_AUTH_TRIES",
    )
    assert path.name == "ssh_max_auth_tries.yml"


def test_can_execute_blocks_stub_catalog_playbook():
    settings = _settings(
        real_ansible_allowed_task_codes="AIDE_INSTALL",
        real_ansible_allowed_hosts="lab-server-01",
    )
    catalog = SimpleNamespace(
        task_code="AIDE_INSTALL",
        is_enabled=True,
        ansible_playbook_path="aide_install.yml",
    )
    gate = can_execute_real_ansible(
        settings=settings,
        job=None,
        host="lab-server-01",
        task_code="AIDE_INSTALL",
        mode="dry_run",
        catalog=catalog,
        host_count=1,
    )
    assert gate.allowed is False
    assert any("stub" in r.lower() for r in gate.reasons)


def test_real_dry_run_refuses_stub_playbook(tmp_path):
    inv = tmp_path / "lab.ini"
    inv.write_text("[lab]\nlab-server-01\n")
    key = tmp_path / "key"
    key.write_text("fake\n")
    settings = _settings(
        real_ansible_inventory_path=str(inv),
        real_ansible_private_key_path=str(key),
        real_ansible_allowed_hosts="lab-server-01",
        real_ansible_allowed_task_codes="AIDE_INSTALL",
    )
    catalog = SimpleNamespace(
        task_code="AIDE_INSTALL",
        is_enabled=True,
        ansible_playbook_path="aide_install.yml",
    )
    job = SimpleNamespace(
        id=9,
        plan_id=1,
        task_code="AIDE_INSTALL",
        status="waiting_dry_run",
        environment="lab",
        targets=[SimpleNamespace(device_name="lab-server-01")],
        started_at=None,
        dry_run_status=None,
    )

    def _scalars(stmt):  # noqa: ARG001
        result = MagicMock()
        # First call: job; subsequent catalog / results lookups
        if not hasattr(_scalars, "n"):
            _scalars.n = 0  # type: ignore[attr-defined]
        _scalars.n += 1  # type: ignore[attr-defined]
        if _scalars.n == 1:  # type: ignore[attr-defined]
            result.first.return_value = job
            result.all.return_value = []
        elif _scalars.n == 2:  # type: ignore[attr-defined]
            result.first.return_value = catalog
            result.all.return_value = []
        else:
            result.first.return_value = None
            result.all.return_value = []
        return result

    db = MagicMock()
    db.scalars.side_effect = _scalars

    service = RealAnsiblePilotService(db, settings=settings)
    with pytest.raises(RealAnsiblePilotError) as exc:
        service.real_dry_run(9, actor="t", role="admin")
    msg = str(exc.value).lower()
    assert "stub" in msg or getattr(exc.value, "code", "") == "stub_playbook"


def test_catalog_capability_flags_for_implemented():
    path = REPO_PLAYBOOKS / "ssh_max_auth_tries.yml"
    flags = catalog_capability_flags(
        task_code="SSH_MAX_AUTH_TRIES", playbook_path=path
    )
    assert flags["is_stub"] is False
    assert flags["phase11a_implemented"] is True
    assert flags["supports_backup"] is True
    assert flags["supports_validation"] is True
    assert flags["supports_rollback"] == "manual"


def test_catalog_capability_flags_for_stub():
    path = REPO_PLAYBOOKS / "aide_install.yml"
    flags = catalog_capability_flags(task_code="AIDE_INSTALL", playbook_path=path)
    assert flags["is_stub"] is True
    assert flags["phase11a_implemented"] is False
    assert flags["supports_backup"] is False
    assert flags["supports_rollback"] == "none"


def test_seed_capability_defaults_for_phase11a():
    assert PHASE11A_IMPLEMENTED_TASK_CODES == set(IMPLEMENTED)
    item = _with_capability_defaults(
        {
            "task_code": "SSH_MAX_AUTH_TRIES",
            "title": "x",
            "ansible_playbook_path": "ssh_max_auth_tries.yml",
            "is_enabled": True,
        }
    )
    assert item["supports_backup"] is True
    assert item["supports_validation"] is True
    assert item["supports_rollback"] == "manual"


def test_no_excel_or_ai_execution_in_playbook_quality_module():
    src = Path("/workspace/backend/app/services/playbook_quality.py").read_text()
    assert "Excel" in src or "remediation" in src.lower()
    # Module must not execute remediation/AI content
    assert "subprocess" not in src
    assert "ansible_runner" not in src


def test_safety_defaults_unchanged():
    s = Settings()
    assert s.mock_mode is True
    assert s.real_ansible_enabled is False
    assert s.real_ansible_check_mode_only is True
    assert s.real_ansible_pilot_mode is False


def test_no_real_apply_endpoint_registered():
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
