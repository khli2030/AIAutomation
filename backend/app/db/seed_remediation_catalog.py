"""Seed approved remediation_catalog entries for MVP task codes."""

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
        "is_enabled": True,
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
        "is_enabled": True,
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
        "is_enabled": True,
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
        "is_enabled": True,
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
        "is_enabled": True,
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
        "is_enabled": True,
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
        "is_enabled": True,
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
        "is_enabled": True,
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
        "is_enabled": False,  # Disabled until playbook is reviewed in a later phase.
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
        "is_enabled": False,
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
        "is_enabled": False,
    },
]


def seed_remediation_catalog(db: Session) -> int:
    """Insert missing catalog rows. Returns number of inserted rows."""
    inserted = 0
    for item in MVP_CATALOG:
        exists = (
            db.query(RemediationCatalog)
            .filter(RemediationCatalog.task_code == item["task_code"])
            .first()
        )
        if exists:
            continue
        db.add(RemediationCatalog(**item))  # type: ignore[arg-type]
        inserted += 1
    db.commit()
    return inserted
