"""Phase 11B: SSH-delegated Ansible execution mode."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.config import Settings, get_settings
from app.services.ansible_safety import RealAnsibleBlockedError
from app.services.lab_ansible_config import build_lab_config_preview
from app.services.playbook_quality import assert_playbook_allowed_for_real_execution
from app.services.real_ansible_pilot import build_safety_status
from app.services.ssh_delegate_ansible import (
    build_remote_ping_argv,
    build_remote_playbook_check_argv,
    build_remote_shell_command,
    build_ssh_argv,
    delegate_blocking_reasons,
    redact_for_log,
    resolve_execution_mode,
    run_ssh_delegate,
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
        real_ansible_execution_mode="local",
        real_ansible_allowed_hosts="",
        real_ansible_allowed_task_codes="",
        real_ansible_inventory_path=None,
        real_ansible_private_key_path=None,
        real_ansible_remote_user=None,
        real_ansible_control_node_host=None,
        real_ansible_control_node_user=None,
        real_ansible_control_node_workdir=None,
        real_ansible_control_node_timeout_seconds=120,
        real_ansible_timeout_seconds=120,
        app_env="development",
        ansible_playbooks_dir="/workspace/ansible/playbooks",
        ansible_inventories_dir="/tmp/inventories-missing",
        runner_private_data_dir="/tmp/runner-private",
    )
    defaults.update(overrides)
    return Settings(**defaults)  # type: ignore[arg-type]


def test_execution_mode_defaults_to_local():
    s = Settings()
    assert s.real_ansible_execution_mode == "local"
    assert resolve_execution_mode(s) == "local"


def test_local_mode_still_requires_local_inventory_file(tmp_path):
    settings = _settings(
        mock_mode=False,
        real_ansible_enabled=True,
        real_ansible_pilot_mode=True,
        real_ansible_execution_mode="local",
        real_ansible_allowed_hosts="lab-server-01",
        real_ansible_allowed_task_codes="SSH_MAX_AUTH_TRIES",
        real_ansible_inventory_path=str(tmp_path / "missing.ini"),
        real_ansible_private_key_path=str(tmp_path / "missing_key"),
        real_ansible_remote_user="labuser",
    )
    preview = build_lab_config_preview(
        settings, known_task_codes=["SSH_MAX_AUTH_TRIES"]
    )
    assert preview.execution_mode == "local"
    assert preview.inventory_path_configured is False
    assert preview.delegate_available is False


def test_ssh_delegate_refuses_when_host_or_workdir_missing():
    settings = _settings(
        real_ansible_execution_mode="ssh_delegate",
        real_ansible_control_node_host=None,
        real_ansible_control_node_workdir=None,
    )
    reasons = delegate_blocking_reasons(settings)
    assert any("CONTROL_NODE_HOST missing" in r for r in reasons)
    assert any("CONTROL_NODE_WORKDIR missing" in r for r in reasons)

    settings2 = _settings(
        mock_mode=False,
        real_ansible_enabled=True,
        real_ansible_pilot_mode=True,
        real_ansible_execution_mode="ssh_delegate",
        real_ansible_auth_mode="ssh_config",
        real_ansible_allowed_hosts="lab-server-01",
        real_ansible_allowed_task_codes="SSH_MAX_AUTH_TRIES",
        real_ansible_inventory_path="/opt/compliance/lab.ini",
        real_ansible_control_node_host=None,
        real_ansible_control_node_workdir="/opt/compliance",
    )
    preview = build_lab_config_preview(
        settings2, known_task_codes=["SSH_MAX_AUTH_TRIES"]
    )
    assert preview.execution_mode == "ssh_delegate"
    assert preview.control_node_configured is False
    assert preview.delegate_available is False
    assert any("CONTROL_NODE_HOST missing" in e for e in preview.validation_errors)


def test_ssh_delegate_builds_remote_command_safely():
    settings = _settings(
        real_ansible_execution_mode="ssh_delegate",
        real_ansible_control_node_host="infra-ops.example",
        real_ansible_control_node_user="ansible",
        real_ansible_control_node_workdir="/opt/compliance",
        real_ansible_auth_mode="ssh_config",
    )
    ping_parts = build_remote_ping_argv(
        settings,
        hosts=["lab-server-01"],
        inventory_path="/opt/compliance/lab.ini",
    )
    assert ping_parts[0] == "ansible"
    assert "-m" in ping_parts and "ping" in ping_parts
    assert "--private-key" not in ping_parts

    pb_parts = build_remote_playbook_check_argv(
        settings,
        playbook_rel="ssh_max_auth_tries.yml",
        inventory_path="/opt/compliance/lab.ini",
        limit_hosts=["lab-server-01"],
    )
    assert pb_parts[0] == "ansible-playbook"
    assert "--check" in pb_parts
    assert "--limit" in pb_parts
    assert "lab-server-01" in pb_parts

    remote = build_remote_shell_command("/opt/compliance", pb_parts)
    assert remote.startswith("cd '/opt/compliance' &&") or remote.startswith(
        'cd /opt/compliance &&'
    ) or "cd " in remote
    assert "--check" in remote

    ssh_argv = build_ssh_argv(settings, remote_command=remote)
    assert ssh_argv[0] == "ssh"
    assert "BatchMode=yes" in ssh_argv
    assert "ansible@infra-ops.example" in ssh_argv


def test_ssh_delegate_redacts_private_key_in_logs():
    argv = ["ansible-playbook", "--private-key", "/secret/id_ed25519", "--check"]
    redacted = redact_for_log(argv)
    assert "<redacted>" in redacted
    assert "/secret/id_ed25519" not in redacted


def test_ssh_delegate_run_uses_subprocess_not_local_ansible():
    settings = _settings(
        real_ansible_execution_mode="ssh_delegate",
        real_ansible_control_node_host="infra-ops.example",
        real_ansible_control_node_workdir="/opt/compliance",
        real_ansible_auth_mode="ssh_config",
    )
    completed = MagicMock(returncode=0, stdout="pong", stderr="")
    with patch("app.services.ssh_delegate_ansible.subprocess.run", return_value=completed) as run:
        result = run_ssh_delegate(
            settings,
            remote_argv_parts=["ansible", "-i", "/opt/lab.ini", "h1", "-m", "ping"],
        )
    assert result.ok is True
    assert result.execution_backend == "ssh_delegate"
    assert run.called
    argv = run.call_args.args[0]
    assert argv[0] == "ssh"
    assert "BatchMode=yes" in argv
    # No local ansible-runner invocation
    assert "ansible-runner" not in str(argv)


def test_safety_status_shows_execution_mode_fields():
    settings = _settings(real_ansible_execution_mode="ssh_delegate")
    with patch(
        "app.services.ssh_delegate_ansible.ssh_client_available",
        return_value=(True, "ok"),
    ):
        status = build_safety_status(settings)
    assert status.execution_mode == "ssh_delegate"
    assert status.control_node_configured is False
    assert status.delegate_available is False
    payload = status.to_dict()
    assert "execution_mode" in payload
    assert "BEGIN OPENSSH" not in str(payload)
    assert "private_key_path" not in payload
    assert "real_ansible_private_key_path" not in payload


def test_stub_playbooks_still_blocked_in_ssh_delegate_mode():
    settings = _settings(
        real_ansible_execution_mode="ssh_delegate",
        real_ansible_control_node_host="infra-ops",
        real_ansible_control_node_workdir="/opt/compliance",
        ansible_playbooks_dir="/workspace/ansible/playbooks",
    )
    with pytest.raises(RealAnsibleBlockedError) as exc:
        assert_playbook_allowed_for_real_execution(
            settings,
            catalog_relative_path="aide_install.yml",
            task_code="AIDE_INSTALL",
        )
    assert exc.value.code == "stub_playbook"


def test_high_risk_still_blocked_in_ssh_delegate_mode(tmp_path):
    pb = tmp_path / "playbooks"
    pb.mkdir()
    (pb / "rsync_remove.yml").write_text("---\n- hosts: all\n  tasks: []\n")
    settings = _settings(
        real_ansible_execution_mode="ssh_delegate",
        real_ansible_control_node_host="infra-ops",
        real_ansible_control_node_workdir="/opt/compliance",
        ansible_playbooks_dir=str(pb),
    )
    with pytest.raises(RealAnsibleBlockedError) as exc:
        assert_playbook_allowed_for_real_execution(
            settings,
            catalog_relative_path="rsync_remove.yml",
            task_code="RSYNC_REMOVE",
        )
    assert exc.value.code == "high_risk_blocked"


def test_no_real_apply_endpoint_added():
    from app.api import execution_jobs

    paths = []
    for route in execution_jobs.router.routes:
        methods = getattr(route, "methods", set()) or set()
        path = getattr(route, "path", "")
        for m in methods:
            paths.append(f"{m} {path}")
    assert not any("/apply" in p for p in paths)
    assert any("POST /{job_id}/real-dry-run" in p for p in paths)


def test_safety_defaults_unchanged():
    s = Settings()
    assert s.mock_mode is True
    assert s.real_ansible_enabled is False
    assert s.real_ansible_check_mode_only is True
    assert s.real_ansible_pilot_mode is False
    assert s.real_ansible_execution_mode == "local"
