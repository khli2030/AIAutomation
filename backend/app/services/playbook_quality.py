"""Phase 11A playbook quality gates — block stubs and high-risk remediations.

Never executes Excel Remediation text or AI suggestions.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from app.services.ansible_safety import RealAnsibleBlockedError, resolve_playbook_path

# Markers that identify unfinished catalog stubs (must never run for real).
STUB_MARKERS: tuple[str, ...] = (
    "Playbook stub",
    "Placeholder — not implemented",
)

# Phase 11A: only these four SSH remediations are implemented as real playbooks.
PHASE11A_IMPLEMENTED_TASK_CODES: frozenset[str] = frozenset(
    {
        "SSH_MAX_AUTH_TRIES",
        "SSH_LOG_LEVEL_INFO",
        "SSH_CLIENT_ALIVE_INTERVAL",
        "SSH_IGNORE_RHOSTS_ENABLE",
    }
)

# High-risk remediations deferred in Phase 11A — blocked from real execution
# even if a stub is accidentally replaced without review.
PHASE11A_HIGH_RISK_BLOCKED_TASK_CODES: frozenset[str] = frozenset(
    {
        "RSYNC_REMOVE",
        "X11_SERVER_REMOVE",
        "SET_SELINUX_MODE",
        "SET_TMP_NODEV",
        "SET_TMP_NOEXEC",
        "SET_DEV_SHM_NODEV",
        "SET_DEV_SHM_NOEXEC",
        "HOME_PARTITION_NODEV",
    }
)


def playbook_text_is_stub(text: str) -> bool:
    """True when playbook content still contains stub / placeholder markers."""
    return any(marker in text for marker in STUB_MARKERS)


def is_stub_playbook(path: Path) -> bool:
    if not path.is_file():
        return False
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False
    return playbook_text_is_stub(text)


def playbook_has_backup(text: str) -> bool:
    lowered = text.lower()
    return (
        "backup sshd_config" in lowered
        or "backup:" in lowered
        or ".bak-" in lowered
    )


def playbook_has_validate(text: str) -> bool:
    return "sshd -t" in text or "validate:" in text.lower()


def assert_playbook_allowed_for_real_execution(
    settings: Any,
    *,
    catalog_relative_path: str,
    task_code: str | None = None,
) -> Path:
    """Resolve playbook and refuse stubs / Phase 11A high-risk codes.

    Returns the resolved path when allowed.
    """
    code = (task_code or "").strip()
    if code and code in PHASE11A_HIGH_RISK_BLOCKED_TASK_CODES:
        raise RealAnsibleBlockedError(
            f"task_code {code!r} is high-risk and blocked from real execution "
            "in Phase 11A",
            code="high_risk_blocked",
        )

    path = resolve_playbook_path(settings, catalog_relative_path)
    if is_stub_playbook(path):
        raise RealAnsibleBlockedError(
            f"Playbook {catalog_relative_path!r} is still a stub "
            f"({STUB_MARKERS[0]!r} / {STUB_MARKERS[1]!r}) — "
            "blocked from real execution",
            code="stub_playbook",
        )
    return path


def catalog_capability_flags(
    *,
    task_code: str,
    playbook_path: Path | None = None,
    playbook_text: str | None = None,
) -> dict[str, Any]:
    """Sanitized capability flags for catalog / readiness (no secrets)."""
    text = playbook_text
    if text is None and playbook_path is not None and playbook_path.is_file():
        try:
            text = playbook_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            text = ""
    text = text or ""
    stub = playbook_text_is_stub(text)
    implemented = task_code in PHASE11A_IMPLEMENTED_TASK_CODES and not stub
    supports_backup = implemented and playbook_has_backup(text)
    supports_validation = implemented and playbook_has_validate(text)
    # Automated rollback is not implemented in Phase 11A.
    supports_rollback = "manual" if implemented else "none"
    return {
        "task_code": task_code,
        "is_stub": stub,
        "phase11a_implemented": implemented,
        "supports_backup": supports_backup,
        "supports_validation": supports_validation,
        "supports_rollback": supports_rollback,
        "high_risk_blocked": task_code in PHASE11A_HIGH_RISK_BLOCKED_TASK_CODES,
    }


__all__ = [
    "PHASE11A_HIGH_RISK_BLOCKED_TASK_CODES",
    "PHASE11A_IMPLEMENTED_TASK_CODES",
    "STUB_MARKERS",
    "assert_playbook_allowed_for_real_execution",
    "catalog_capability_flags",
    "is_stub_playbook",
    "playbook_has_backup",
    "playbook_has_validate",
    "playbook_text_is_stub",
]
