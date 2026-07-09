"""Approved remediation task codes for MVP.

Execution is allowed only for codes present in remediation_catalog
(except NEEDS_REVIEW / UNSUPPORTED_CONTROL which never execute).
"""

from enum import StrEnum


class TaskCode(StrEnum):
    SSH_DISABLE_ROOT_LOGIN = "SSH_DISABLE_ROOT_LOGIN"
    SSH_DISABLE_X11_FORWARDING = "SSH_DISABLE_X11_FORWARDING"
    SSH_SET_MAX_SESSIONS = "SSH_SET_MAX_SESSIONS"
    SET_PASS_MAX_DAYS = "SET_PASS_MAX_DAYS"
    SET_VAR_LOG_PERMISSIONS = "SET_VAR_LOG_PERMISSIONS"
    SET_TMP_NODEV = "SET_TMP_NODEV"
    SET_TMP_NOEXEC = "SET_TMP_NOEXEC"
    SET_DEV_SHM_NODEV = "SET_DEV_SHM_NODEV"
    SET_DEV_SHM_NOEXEC = "SET_DEV_SHM_NOEXEC"
    SET_SELINUX_MODE = "SET_SELINUX_MODE"
    SET_MOTD_BANNER = "SET_MOTD_BANNER"
    SET_SSH_LOGIN_BANNER = "SET_SSH_LOGIN_BANNER"
    NEEDS_REVIEW = "NEEDS_REVIEW"
    UNSUPPORTED_CONTROL = "UNSUPPORTED_CONTROL"


# Codes that must never be executed by Ansible Runner.
NON_EXECUTABLE_TASK_CODES: frozenset[str] = frozenset(
    {
        TaskCode.NEEDS_REVIEW.value,
        TaskCode.UNSUPPORTED_CONTROL.value,
    }
)
