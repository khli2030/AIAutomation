"""Rule-based remediation classifier (Phase 3 + Phase 9A).

Uses Qualys/Source/Description/Rationale/Remediation/Expected Configuration
text only to map findings to approved task_code values.

Phase 9A: exact qualys_control_id lookup runs first, then conservative
keyword fallback. Never executes Remediation text. Never calls Ansible / AI.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from app.classifiers.qualys_control_map import lookup_qualys_control_id
from app.constants.task_codes import NON_EXECUTABLE_TASK_CODES, TaskCode


class ClassifiableRecord(Protocol):
    qualys_control_id: str | None
    source_check_id: str | None
    control_description: str | None
    rationale: str | None
    remediation: str | None
    expected_configuration: str | None


@dataclass(frozen=True)
class ClassificationResult:
    task_code: str
    matched_rule: str | None
    is_recognized: bool


def _combined_text(record: ClassifiableRecord) -> str:
    parts = [
        record.qualys_control_id,
        record.source_check_id,
        record.control_description,
        record.rationale,
        record.remediation,
        record.expected_configuration,
    ]
    return " ".join(p for p in parts if p).lower()


def _recognized(task_code: str) -> bool:
    return task_code not in NON_EXECUTABLE_TASK_CODES


def classify_record(record: ClassifiableRecord) -> ClassificationResult:
    """Map a finding to a task_code using exact Qualys ID then keyword rules."""
    # 1) Exact Qualys control ID (Phase 9A) — preferred deterministic path.
    mapped = lookup_qualys_control_id(record.qualys_control_id)
    if mapped is not None:
        control_id = str(record.qualys_control_id or "").strip()
        return ClassificationResult(
            task_code=mapped,
            matched_rule=f"qualys_control_id:{control_id}",
            is_recognized=_recognized(mapped),
        )

    text = _combined_text(record)

    # 2) Conservative text fallback (order matters for overlapping rules).
    rules: list[tuple[str, str, Callable[[str], bool]]] = [
        (
            "PermitRootLogin",
            TaskCode.SSH_DISABLE_ROOT_LOGIN.value,
            lambda t: "permitrootlogin" in t,
        ),
        (
            "X11Forwarding",
            TaskCode.SSH_DISABLE_X11_FORWARDING.value,
            lambda t: "x11forwarding" in t,
        ),
        (
            "MaxSessions",
            TaskCode.SSH_SET_MAX_SESSIONS.value,
            lambda t: "maxsessions" in t,
        ),
        (
            "PASS_MAX_DAYS",
            TaskCode.SET_PASS_MAX_DAYS.value,
            lambda t: "pass_max_days" in t,
        ),
        (
            "PASS_MIN_DAYS",
            TaskCode.PASSWORD_MIN_AGE.value,
            lambda t: "pass_min_days" in t,
        ),
        (
            "/var/log + chmod",
            TaskCode.SET_VAR_LOG_PERMISSIONS.value,
            lambda t: "/var/log" in t and "chmod" in t,
        ),
        (
            "/tmp + noexec",
            TaskCode.SET_TMP_NOEXEC.value,
            lambda t: "/tmp" in t and "noexec" in t,
        ),
        (
            "/tmp + nodev",
            TaskCode.SET_TMP_NODEV.value,
            lambda t: "/tmp" in t and "nodev" in t,
        ),
        (
            "/dev/shm + noexec",
            TaskCode.SET_DEV_SHM_NOEXEC.value,
            lambda t: "/dev/shm" in t and "noexec" in t,
        ),
        (
            "/dev/shm + nodev",
            TaskCode.SET_DEV_SHM_NODEV.value,
            lambda t: "/dev/shm" in t and "nodev" in t,
        ),
        (
            "/home + nodev",
            TaskCode.HOME_PARTITION_NODEV.value,
            lambda t: "/home" in t and "nodev" in t,
        ),
        (
            "SELinux / setenforce",
            TaskCode.SET_SELINUX_MODE.value,
            lambda t: "selinux" in t or "setenforce" in t,
        ),
        (
            "/etc/motd",
            TaskCode.SET_MOTD_BANNER.value,
            lambda t: "/etc/motd" in t,
        ),
        (
            "Banner + sshd_config",
            TaskCode.SET_SSH_LOGIN_BANNER.value,
            lambda t: "banner" in t and "sshd_config" in t,
        ),
        (
            "secure_redirects ipv4",
            TaskCode.SYSCTL_IPV4_SECURE_REDIRECTS_DISABLE.value,
            lambda t: "secure_redirects" in t and "ipv4" in t,
        ),
        (
            "accept_ra ipv6",
            TaskCode.SYSCTL_IPV6_ACCEPT_RA_DISABLE.value,
            lambda t: "accept_ra" in t and "ipv6" in t,
        ),
        (
            "journald Compress",
            TaskCode.JOURNALD_COMPRESS_ENABLE.value,
            lambda t: "journald" in t and "compress" in t,
        ),
        (
            "IgnoreRhosts",
            TaskCode.SSH_IGNORE_RHOSTS_ENABLE.value,
            lambda t: "ignorerhosts" in t,
        ),
        (
            "LogLevel INFO",
            TaskCode.SSH_LOG_LEVEL_INFO.value,
            lambda t: "loglevel" in t and "info" in t,
        ),
        (
            "MaxAuthTries",
            TaskCode.SSH_MAX_AUTH_TRIES.value,
            lambda t: "maxauthtries" in t,
        ),
        (
            "ClientAliveInterval",
            TaskCode.SSH_CLIENT_ALIVE_INTERVAL.value,
            lambda t: "clientaliveinterval" in t,
        ),
        (
            "TMOUT",
            TaskCode.SHELL_TMOUT.value,
            lambda t: "tmout" in t,
        ),
        (
            "/etc/crontab permissions",
            TaskCode.CRONTAB_PERMISSIONS.value,
            lambda t: "/etc/crontab" in t and ("chmod" in t or "600" in t),
        ),
        (
            "/etc/cron.daily permissions",
            TaskCode.CRON_DAILY_PERMISSIONS.value,
            lambda t: "/etc/cron.daily" in t,
        ),
        (
            "/etc/cron.hourly permissions",
            TaskCode.CRON_HOURLY_PERMISSIONS.value,
            lambda t: "/etc/cron.hourly" in t,
        ),
        (
            "/etc/cron.weekly permissions",
            TaskCode.CRON_WEEKLY_PERMISSIONS.value,
            lambda t: "/etc/cron.weekly" in t,
        ),
        (
            "/etc/cron.monthly permissions",
            TaskCode.CRON_MONTHLY_PERMISSIONS.value,
            lambda t: "/etc/cron.monthly" in t,
        ),
        (
            "remove rsync",
            TaskCode.RSYNC_REMOVE.value,
            lambda t: "rsync" in t
            and ("remove" in t or "uninstall" in t or "not installed" in t or "absent" in t),
        ),
        (
            "remove xorg-x11-server",
            TaskCode.X11_SERVER_REMOVE.value,
            lambda t: "xorg-x11-server" in t
            or ("x11 server" in t and ("remove" in t or "uninstall" in t)),
        ),
        (
            "install aide",
            TaskCode.AIDE_INSTALL.value,
            lambda t: "aide" in t and "install" in t,
        ),
    ]

    for rule_name, task_code, predicate in rules:
        if predicate(text):
            return ClassificationResult(
                task_code=task_code,
                matched_rule=rule_name,
                is_recognized=_recognized(task_code),
            )

    return ClassificationResult(
        task_code=TaskCode.NEEDS_REVIEW.value,
        matched_rule=None,
        is_recognized=False,
    )
