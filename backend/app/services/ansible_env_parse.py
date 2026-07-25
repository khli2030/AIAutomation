"""Pure env parsing helpers for real Ansible pilot settings (no Settings import)."""

from __future__ import annotations

import re

TIMEOUT_MIN_SECONDS = 10
TIMEOUT_MAX_SECONDS = 600
TIMEOUT_DEFAULT_SECONDS = 120

_HOST_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,253}$")
_TASK_CODE_RE = re.compile(r"^[A-Z][A-Z0-9_]{1,127}$")


def parse_csv_allowlist(raw: str | None) -> list[str]:
    """Parse comma-separated allowlist; strip, drop empties, dedupe (stable order)."""
    if not raw:
        return []
    seen: set[str] = set()
    out: list[str] = []
    for part in str(raw).split(","):
        item = part.strip()
        if not item or item in seen:
            continue
        seen.add(item)
        out.append(item)
    return out


def parse_allowed_hosts(raw: str | None) -> tuple[list[str], list[str]]:
    items = parse_csv_allowlist(raw)
    valid: list[str] = []
    errors: list[str] = []
    for h in items:
        if not _HOST_RE.match(h):
            errors.append(f"Invalid host allowlist entry: {h!r}")
            continue
        valid.append(h)
    return valid, errors


def parse_allowed_task_codes(raw: str | None) -> tuple[list[str], list[str]]:
    items = parse_csv_allowlist(raw)
    valid: list[str] = []
    errors: list[str] = []
    for code in items:
        if not _TASK_CODE_RE.match(code):
            errors.append(f"Invalid task_code allowlist entry: {code!r}")
            continue
        valid.append(code)
    return valid, errors


def clamp_timeout_seconds(value: object) -> tuple[int, list[str]]:
    errors: list[str] = []
    if value is None:
        return TIMEOUT_DEFAULT_SECONDS, ["REAL_ANSIBLE_TIMEOUT_SECONDS missing"]
    try:
        n = int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return TIMEOUT_DEFAULT_SECONDS, [
            f"REAL_ANSIBLE_TIMEOUT_SECONDS invalid: {value!r}"
        ]
    if n < TIMEOUT_MIN_SECONDS or n > TIMEOUT_MAX_SECONDS:
        errors.append(
            f"REAL_ANSIBLE_TIMEOUT_SECONDS={n} out of bounds "
            f"[{TIMEOUT_MIN_SECONDS}, {TIMEOUT_MAX_SECONDS}]"
        )
        n = max(TIMEOUT_MIN_SECONDS, min(TIMEOUT_MAX_SECONDS, n))
    return n, errors
