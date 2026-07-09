"""Seed approved remediation_catalog entries for MVP task codes.

Security: only SSH_DISABLE_ROOT_LOGIN is enabled by default because it has a
real reviewed playbook. All stub playbooks remain is_enabled=False until reviewed.
"""

from sqlalchemy.orm import Session

from app.models.remediation_catalog import RemediationCatalog

# Playbook paths are relative to ANSIBLE_PLAYBOOKS_DIR.
MVP_CATALOG: list[dict[str, object]] = [
    {
        "task_code": "SSH_DISABLE_ROOT_LOGIN",
        "title": "Disable SSH root login (PermitRootLogin no)",
        "supported_os": "linux",
        "ansible_playbook_path": "ssh_disable_root_login.yml",
        "risk_level": "high",
        "requires_approval": True,
        "requires_dry_run": True,
        "requires_backup": True,
        "requires_validation": True,
        "validation_command": "sshd -t",
        "service_reload": "sshd",
        # Only enabled entry — real reviewed playbook.
        "is_enabled": True,
    },
    {
        "task_code": "SSH_DISABLE_X11_FORWARDING",
        "title": "Disable SSH X11 forwarding",
        "supported_os": "linux",
        "ansible_playbook_path": "ssh_disable_x11_forwarding.yml",
        "risk_level": "medium",
        "requires_approval": True,
        "requires_dry_run": True,
        "requires_backup": True,
        "requires_validation": True,
        "validation_command": "sshd -t",
        "service_reload": "sshd",
        "is_enabled": False,  # stub playbook — disabled
    },
    {
        "task_code": "SSH_SET_MAX_SESSIONS",
        "title": "Set SSH MaxSessions",
        "supported_os": "linux",
        "ansible_playbook_path": "ssh_set_max_sessions.yml",
        "risk_level": "medium",
        "requires_approval": True,
        "requires_dry_run": True,
        "requires_backup": True,
        "requires_validation": True,
        "validation_command": "sshd -t",
        "service_reload": "sshd",
        "is_enabled": False,  # stub playbook — disabled
    },
    {
        "task_code": "SET_PASS_MAX_DAYS",
        "title": "Set PASS_MAX_DAYS",
        "supported_os": "linux",
        "ansible_playbook_path": "set_pass_max_days.yml",
        "risk_level": "medium",
        "requires_approval": True,
        "requires_dry_run": True,
        "requires_backup": True,
        "requires_validation": True,
        "validation_command": None,
        "service_reload": None,
        "is_enabled": False,  # stub playbook — disabled
    },
    {
        "task_code": "SET_VAR_LOG_PERMISSIONS",
        "title": "Set /var/log permissions",
        "supported_os": "linux",
        "ansible_playbook_path": "set_var_log_permissions.yml",
        "risk_level": "medium",
        "requires_approval": True,
        "requires_dry_run": True,
        "requires_backup": True,
        "requires_validation": True,
        "validation_command": None,
        "service_reload": None,
        "is_enabled": False,  # stub playbook — disabled
    },
    {
        "task_code": "SET_TMP_NODEV",
        "title": "Mount /tmp with nodev",
        "supported_os": "linux",
        "ansible_playbook_path": "set_tmp_nodev.yml",
        "risk_level": "high",
        "requires_approval": True,
        "requires_dry_run": True,
        "requires_backup": True,
        "requires_validation": True,
        "validation_command": None,
        "service_reload": None,
        "is_enabled": False,  # stub playbook — disabled
    },
    {
        "task_code": "SET_TMP_NOEXEC",
        "title": "Mount /tmp with noexec",
        "supported_os": "linux",
        "ansible_playbook_path": "set_tmp_noexec.yml",
        "risk_level": "high",
        "requires_approval": True,
        "requires_dry_run": True,
        "requires_backup": True,
        "requires_validation": True,
        "validation_command": None,
        "service_reload": None,
        "is_enabled": False,  # stub playbook — disabled
    },
    {
        "task_code": "SET_DEV_SHM_NODEV",
        "title": "Mount /dev/shm with nodev",
        "supported_os": "linux",
        "ansible_playbook_path": "set_dev_shm_nodev.yml",
        "risk_level": "high",
        "requires_approval": True,
        "requires_dry_run": True,
        "requires_backup": True,
        "requires_validation": True,
        "validation_command": None,
        "service_reload": None,
        "is_enabled": False,  # stub playbook — disabled
    },
    {
        "task_code": "SET_DEV_SHM_NOEXEC",
        "title": "Mount /dev/shm with noexec",
        "supported_os": "linux",
        "ansible_playbook_path": "set_dev_shm_noexec.yml",
        "risk_level": "high",
        "requires_approval": True,
        "requires_dry_run": True,
        "requires_backup": True,
        "requires_validation": True,
        "validation_command": None,
        "service_reload": None,
        "is_enabled": False,  # stub playbook — disabled
    },
    {
        "task_code": "SET_SELINUX_MODE",
        "title": "Set SELinux mode",
        "supported_os": "linux",
        "ansible_playbook_path": "set_selinux_mode.yml",
        "risk_level": "critical",
        "requires_approval": True,
        "requires_dry_run": True,
        "requires_backup": True,
        "requires_validation": True,
        "validation_command": None,
        "service_reload": None,
        "is_enabled": False,  # stub playbook — disabled
    },
    {
        "task_code": "SET_MOTD_BANNER",
        "title": "Set /etc/motd banner",
        "supported_os": "linux",
        "ansible_playbook_path": "set_motd_banner.yml",
        "risk_level": "low",
        "requires_approval": True,
        "requires_dry_run": True,
        "requires_backup": True,
        "requires_validation": True,
        "validation_command": None,
        "service_reload": None,
        "is_enabled": False,  # stub playbook — disabled
    },
    {
        "task_code": "SET_SSH_LOGIN_BANNER",
        "title": "Set SSH login banner",
        "supported_os": "linux",
        "ansible_playbook_path": "set_ssh_login_banner.yml",
        "risk_level": "low",
        "requires_approval": True,
        "requires_dry_run": True,
        "requires_backup": True,
        "requires_validation": True,
        "validation_command": "sshd -t",
        "service_reload": "sshd",
        "is_enabled": False,  # stub playbook — disabled
    },
]


def seed_remediation_catalog(db: Session) -> int:
    """Insert missing catalog rows and enforce enabled flags for Phase 1.

    Returns number of inserted or updated rows.
    """
    changed = 0
    for item in MVP_CATALOG:
        existing = (
            db.query(RemediationCatalog)
            .filter(RemediationCatalog.task_code == item["task_code"])
            .first()
        )
        if existing is None:
            db.add(RemediationCatalog(**item))  # type: ignore[arg-type]
            changed += 1
            continue

        # Keep seed authoritative for is_enabled during Phase 1 hardening.
        desired_enabled = bool(item["is_enabled"])
        if existing.is_enabled != desired_enabled:
            existing.is_enabled = desired_enabled
            changed += 1
        if existing.ansible_playbook_path != item["ansible_playbook_path"]:
            existing.ansible_playbook_path = str(item["ansible_playbook_path"])
            changed += 1

    db.commit()
    return changed
