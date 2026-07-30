"""Phase 11C: next safe Linux playbooks + stub/high-risk blocking."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from app.config import Settings, get_settings
from app.db.seed_remediation_catalog import (
    PHASE11C_IMPLEMENTED_TASK_CODES,
    PHASE11_SAFE_IMPLEMENTED_TASK_CODES,
    _with_capability_defaults,
)
from app.services.ansible_safety import RealAnsibleBlockedError
from app.services.playbook_quality import (
    PHASE11A_HIGH_RISK_BLOCKED_TASK_CODES,
    PHASE11A_IMPLEMENTED_TASK_CODES,
    assert_playbook_allowed_for_real_execution,
    catalog_capability_flags,
    is_stub_playbook,
    playbook_has_backup,
    playbook_has_validate,
    playbook_text_is_stub,
)
from app.services.real_ansible_pilot import can_execute_real_ansible

REPO_PLAYBOOKS = Path("/workspace/ansible/playbooks")
ROLLBACK_DOC = Path("/workspace/docs/remediation-rollback.md")

IMPLEMENTED = {
    "JOURNALD_COMPRESS_ENABLE": "journald_compress_enable.yml",
    "SHELL_TMOUT": "shell_tmout.yml",
    "CRONTAB_PERMISSIONS": "crontab_permissions.yml",
    "CRON_DAILY_PERMISSIONS": "cron_daily_permissions.yml",
}

STUB_SAMPLES = [
    "aide_install.yml",
    "rsync_remove.yml",
    "x11_server_remove.yml",
    "set_tmp_nodev.yml",
    "home_partition_nodev.yml",
    "set_selinux_mode.yml",
    "cron_hourly_permissions.yml",
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


def test_phase11c_playbooks_are_not_stubs():
    for rel in IMPLEMENTED.values():
        path = REPO_PLAYBOOKS / rel
        assert path.is_file(), rel
        text = path.read_text(encoding="utf-8")
        assert not playbook_text_is_stub(text), rel
        assert not is_stub_playbook(path), rel
        assert "Playbook stub" not in text
        assert "Placeholder — not implemented" not in text


def test_phase11c_playbooks_check_mode_and_idempotent_friendly():
    for code, rel in IMPLEMENTED.items():
        text = (REPO_PLAYBOOKS / rel).read_text(encoding="utf-8")
        assert "serial: 1" in text, code
        assert "ansible_check_mode" in text, code
        assert playbook_has_backup(text), code
        assert playbook_has_validate(text), code
        assert "generated_playbook" not in text
        assert "Never generated from Excel Remediation text or AI drafts" in text
        # No shell module for mutations
        assert "ansible.builtin.shell" not in text, code


def test_journald_compress_playbook_details():
    text = (REPO_PLAYBOOKS / "journald_compress_enable.yml").read_text()
    assert "Compress=yes" in text
    assert "99-aiautomation.conf" in text
    assert "journald.conf.d" in text
    assert "/etc/systemd/journald.conf" in text
    assert "systemd-journald" in text
    assert ".bak-" in text


def test_shell_tmout_playbook_details():
    text = (REPO_PLAYBOOKS / "shell_tmout.yml").read_text()
    assert "TMOUT" in text
    assert "shell_tmout: 600" in text
    assert "/etc/profile.d/99-aiautomation-tmout.sh" in text
    assert "bash -n" in text
    assert 'mode: "0644"' in text
    assert "owner: root" in text
    assert "group: root" in text


def test_crontab_permissions_playbook_details():
    text = (REPO_PLAYBOOKS / "crontab_permissions.yml").read_text()
    assert "/etc/crontab" in text
    assert 'crontab_desired_mode: "0600"' in text
    assert "previous_owner" in text
    assert "previous_group" in text
    assert "previous_mode" in text
    assert "do not create" in text.lower() or "refusing to create" in text.lower()
    assert "ansible.builtin.file" in text


def test_cron_daily_permissions_playbook_details():
    text = (REPO_PLAYBOOKS / "cron_daily_permissions.yml").read_text()
    assert "/etc/cron.daily" in text
    assert 'cron_daily_desired_mode: "0700"' in text
    assert "previous_owner" in text
    assert "previous_mode" in text
    assert "refusing to create" in text.lower()
    assert "state: directory" in text


def test_rollback_documentation_covers_phase11c():
    assert ROLLBACK_DOC.is_file()
    doc = ROLLBACK_DOC.read_text(encoding="utf-8")
    for code in IMPLEMENTED:
        assert code in doc, code
    assert "99-aiautomation-tmout.sh" in doc
    assert "Compress" in doc
    assert "previous_owner" in doc or "chown" in doc
    assert "manual" in doc.lower()
    assert "no automated rollback" in doc.lower() or "no automated rollback playbook" in doc.lower()


def test_stub_and_high_risk_remain_blocked():
    for rel in STUB_SAMPLES:
        path = REPO_PLAYBOOKS / rel
        assert path.is_file(), rel
        assert is_stub_playbook(path), rel

    settings = _settings()
    with pytest.raises(RealAnsibleBlockedError) as stub_exc:
        assert_playbook_allowed_for_real_execution(
            settings,
            catalog_relative_path="aide_install.yml",
            task_code="AIDE_INSTALL",
        )
    assert stub_exc.value.code == "stub_playbook"

    with pytest.raises(RealAnsibleBlockedError) as risk_exc:
        assert_playbook_allowed_for_real_execution(
            settings,
            catalog_relative_path="rsync_remove.yml",
            task_code="RSYNC_REMOVE",
        )
    assert risk_exc.value.code == "high_risk_blocked"
    assert "RSYNC_REMOVE" in PHASE11A_HIGH_RISK_BLOCKED_TASK_CODES
    assert "SET_SELINUX_MODE" in PHASE11A_HIGH_RISK_BLOCKED_TASK_CODES
    assert "HOME_PARTITION_NODEV" in PHASE11A_HIGH_RISK_BLOCKED_TASK_CODES


def test_phase11c_playbooks_allowed_for_real_execution():
    settings = _settings()
    for code, rel in IMPLEMENTED.items():
        path = assert_playbook_allowed_for_real_execution(
            settings,
            catalog_relative_path=rel,
            task_code=code,
        )
        assert path.name == rel


def test_can_execute_blocks_stub_still():
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


def test_catalog_capability_flags_for_phase11c():
    path = REPO_PLAYBOOKS / "shell_tmout.yml"
    flags = catalog_capability_flags(task_code="SHELL_TMOUT", playbook_path=path)
    assert flags["is_stub"] is False
    assert flags["phase11c_implemented"] is True
    assert flags["phase11a_implemented"] is False
    assert flags["supports_backup"] is True
    assert flags["supports_validation"] is True
    assert flags["supports_rollback"] == "manual"


def test_seed_capability_defaults_for_phase11c():
    assert PHASE11C_IMPLEMENTED_TASK_CODES == set(IMPLEMENTED)
    assert PHASE11A_IMPLEMENTED_TASK_CODES.isdisjoint(PHASE11C_IMPLEMENTED_TASK_CODES)
    assert PHASE11_SAFE_IMPLEMENTED_TASK_CODES == (
        PHASE11A_IMPLEMENTED_TASK_CODES | PHASE11C_IMPLEMENTED_TASK_CODES
    )
    for code in IMPLEMENTED:
        item = _with_capability_defaults(
            {
                "task_code": code,
                "title": "x",
                "ansible_playbook_path": IMPLEMENTED[code],
                "is_enabled": True,
            }
        )
        assert item["supports_backup"] is True
        assert item["supports_validation"] is True
        assert item["supports_rollback"] == "manual"


def test_safety_defaults_and_no_real_apply():
    s = Settings()
    assert s.mock_mode is True
    assert s.real_ansible_enabled is False
    assert s.real_ansible_check_mode_only is True
    assert s.real_ansible_pilot_mode is False

    from app.api import execution_jobs

    paths = []
    for route in execution_jobs.router.routes:
        methods = getattr(route, "methods", set()) or set()
        path = getattr(route, "path", "")
        for m in methods:
            paths.append(f"{m} {path}")
    assert not any("/apply" in p for p in paths)
    assert not any(p.endswith("/real-run") for p in paths)
