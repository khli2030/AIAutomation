"""Rule-based remediation classifier (Phase 3).

Uses Qualys/Source/Description/Rationale/Remediation/Expected Configuration
text only to map findings to approved task_code values.

Never executes Remediation text. Never calls Ansible / AI.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

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


def classify_record(record: ClassifiableRecord) -> ClassificationResult:
    """Map a finding to a task_code using deterministic keyword rules."""
    text = _combined_text(record)

    # Order matters for overlapping filesystem rules (/tmp vs /dev/shm, nodev vs noexec).
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
    ]

    for rule_name, task_code, predicate in rules:
        if predicate(text):
            return ClassificationResult(
                task_code=task_code,
                matched_rule=rule_name,
                is_recognized=task_code not in NON_EXECUTABLE_TASK_CODES,
            )

    return ClassificationResult(
        task_code=TaskCode.NEEDS_REVIEW.value,
        matched_rule=None,
        is_recognized=False,
    )
