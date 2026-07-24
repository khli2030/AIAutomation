"""Exact Qualys control ID → task_code mappings (Phase 9A).

Exact ID lookup runs before conservative text fallback in classify_record().
Never execute Excel Remediation text; mapping only produces approved task_codes
that must also exist in remediation_catalog for plan/execution.

Intentionally unmapped (remain NEEDS_REVIEW / manual operator review):
  6896 — HOME_DIR_PERMISSIONS (per-user home review; not a safe generic remediation)
  7394 — TMP_PARTITION_REQUIRED (creating/migrating /tmp is not a simple remediation)
"""

from __future__ import annotations

from app.constants.task_codes import TaskCode

# Exact Qualys control IDs → approved task codes (Phase 9A top coverage).
QUALYS_CONTROL_ID_MAP: dict[str, str] = {
    "1072": TaskCode.PASSWORD_MIN_AGE.value,
    "5957": TaskCode.SYSCTL_IPV4_SECURE_REDIRECTS_DISABLE.value,
    "7500": TaskCode.SYSCTL_IPV6_ACCEPT_RA_DISABLE.value,
    "17132": TaskCode.JOURNALD_COMPRESS_ENABLE.value,
    "2236": TaskCode.SSH_IGNORE_RHOSTS_ENABLE.value,
    "3598": TaskCode.SSH_LOG_LEVEL_INFO.value,
    "2234": TaskCode.SSH_MAX_AUTH_TRIES.value,
    "5222": TaskCode.SSH_CLIENT_ALIVE_INTERVAL.value,
    "2678": TaskCode.SHELL_TMOUT.value,
    "5154": TaskCode.CRONTAB_PERMISSIONS.value,
    "7341": TaskCode.CRON_DAILY_PERMISSIONS.value,
    "7343": TaskCode.CRON_HOURLY_PERMISSIONS.value,
    "7345": TaskCode.CRON_WEEKLY_PERMISSIONS.value,
    "7347": TaskCode.CRON_MONTHLY_PERMISSIONS.value,
    "22693": TaskCode.RSYNC_REMOVE.value,
    "21959": TaskCode.X11_SERVER_REMOVE.value,
    "7411": TaskCode.AIDE_INSTALL.value,
    "7403": TaskCode.HOME_PARTITION_NODEV.value,
}

# Documented holdouts — must NOT appear in QUALYS_CONTROL_ID_MAP.
MANUAL_REVIEW_QUALYS_CONTROL_IDS: frozenset[str] = frozenset(
    {
        "6896",  # HOME_DIR_PERMISSIONS
        "7394",  # TMP_PARTITION_REQUIRED
    }
)


def normalize_qualys_control_id(value: str | None) -> str | None:
    """Strip whitespace; return None when empty."""
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def lookup_qualys_control_id(value: str | None) -> str | None:
    """Return mapped task_code for an exact Qualys control ID, else None."""
    key = normalize_qualys_control_id(value)
    if key is None:
        return None
    return QUALYS_CONTROL_ID_MAP.get(key)
