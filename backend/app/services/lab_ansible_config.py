"""Phase 10B/10C lab inventory + single-host pilot config validation.

Sanitized previews only — never expose private key contents or secrets.
Defaults remain safe (MOCK_MODE=true, REAL_ANSIBLE_ENABLED=false, PILOT_MODE=false).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

from app.config import Settings
from app.services.ansible_env_parse import (
    TIMEOUT_DEFAULT_SECONDS,
    TIMEOUT_MAX_SECONDS,
    TIMEOUT_MIN_SECONDS,
    clamp_timeout_seconds,
    parse_allowed_hosts,
    parse_allowed_task_codes,
    parse_csv_allowlist,
)


def inventory_is_configured(settings: Settings) -> bool:
    """True when inventory path is set.

    local mode: path must exist as a local file.
    ssh_delegate: path is interpreted on the control node (existence not checked locally).
    """
    override = (settings.real_ansible_inventory_path or "").strip()
    if not override:
        return False
    from app.services.ssh_delegate_ansible import resolve_execution_mode  # noqa: PLC0415

    if resolve_execution_mode(settings) == "ssh_delegate":
        return True
    return Path(override).is_file()


def private_key_is_configured(settings: Settings) -> bool:
    path = (settings.real_ansible_private_key_path or "").strip()
    if not path:
        return False
    from app.services.ssh_delegate_ansible import resolve_execution_mode  # noqa: PLC0415

    if resolve_execution_mode(settings) == "ssh_delegate":
        # Path refers to the control node filesystem.
        return True
    return Path(path).is_file()


def remote_user_is_configured(settings: Settings) -> bool:
    return bool((settings.real_ansible_remote_user or "").strip())


def max_hosts_per_run(settings: Settings) -> int:
    try:
        n = int(getattr(settings, "real_ansible_max_hosts_per_run", 1) or 1)
    except (TypeError, ValueError):
        return 1
    return max(1, min(5, n))


def resolve_auth_mode(settings: Settings) -> str:
    """Return normalized auth mode: explicit | ssh_config (default explicit)."""
    if hasattr(settings, "real_ansible_auth_mode_normalized"):
        return settings.real_ansible_auth_mode_normalized
    mode = str(getattr(settings, "real_ansible_auth_mode", "explicit") or "explicit")
    mode = mode.strip().lower()
    return mode if mode in {"explicit", "ssh_config"} else "explicit"


def uses_explicit_auth(settings: Settings) -> bool:
    return resolve_auth_mode(settings) == "explicit"


@dataclass
class LabConfigPreview:
    """Sanitized lab pilot config — no secrets / key contents."""

    allowed_hosts: list[str] = field(default_factory=list)
    allowed_task_codes: list[str] = field(default_factory=list)
    inventory_path_configured: bool = False
    private_key_configured: bool = False
    remote_user_configured: bool = False
    timeout_seconds: int = TIMEOUT_DEFAULT_SECONDS
    validation_status: str = "blocked"  # ok | invalid | blocked
    validation_errors: list[str] = field(default_factory=list)
    mock_mode: bool = True
    real_ansible_enabled: bool = False
    check_mode_only: bool = True
    connectivity_allowed: bool = False
    # Phase 10C
    pilot_mode: bool = False
    max_hosts_per_run: int = 1
    pilot_ready: bool = False
    pilot_readiness_errors: list[str] = field(default_factory=list)
    auth_mode: str = "explicit"
    auth_source: str = "explicit"
    execution_mode: str = "local"
    control_node_configured: bool = False
    control_node_workdir: str | None = None
    delegate_available: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "allowed_hosts": list(self.allowed_hosts),
            "allowed_task_codes": list(self.allowed_task_codes),
            "inventory_path_configured": self.inventory_path_configured,
            "private_key_configured": self.private_key_configured,
            "remote_user_configured": self.remote_user_configured,
            "timeout_seconds": self.timeout_seconds,
            "validation_status": self.validation_status,
            "validation_errors": list(self.validation_errors),
            "mock_mode": self.mock_mode,
            "real_ansible_enabled": self.real_ansible_enabled,
            "check_mode_only": self.check_mode_only,
            "connectivity_allowed": self.connectivity_allowed,
            "pilot_mode": self.pilot_mode,
            "max_hosts_per_run": self.max_hosts_per_run,
            "pilot_ready": self.pilot_ready,
            "pilot_readiness_errors": list(self.pilot_readiness_errors),
            "auth_mode": self.auth_mode,
            "auth_source": self.auth_source,
            "execution_mode": self.execution_mode,
            "control_node_configured": self.control_node_configured,
            "control_node_workdir": self.control_node_workdir,
            "delegate_available": self.delegate_available,
        }


@dataclass
class PilotReadiness:
    ready: bool
    mock_mode: bool
    real_ansible_enabled: bool
    check_mode_only: bool
    pilot_mode: bool
    max_hosts_per_run: int
    allowed_hosts: list[str] = field(default_factory=list)
    allowed_task_codes: list[str] = field(default_factory=list)
    inventory_configured: bool = False
    remote_user_configured: bool = False
    private_key_configured: bool = False
    auth_mode: str = "explicit"
    auth_source: str = "explicit"
    execution_mode: str = "local"
    control_node_configured: bool = False
    control_node_workdir: str | None = None
    delegate_available: bool = False
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ready": self.ready,
            "mock_mode": self.mock_mode,
            "real_ansible_enabled": self.real_ansible_enabled,
            "check_mode_only": self.check_mode_only,
            "pilot_mode": self.pilot_mode,
            "max_hosts_per_run": self.max_hosts_per_run,
            "allowed_hosts": list(self.allowed_hosts),
            "allowed_task_codes": list(self.allowed_task_codes),
            "inventory_configured": self.inventory_configured,
            "remote_user_configured": self.remote_user_configured,
            "private_key_configured": self.private_key_configured,
            "auth_mode": self.auth_mode,
            "auth_source": self.auth_source,
            "execution_mode": self.execution_mode,
            "control_node_configured": self.control_node_configured,
            "control_node_workdir": self.control_node_workdir,
            "delegate_available": self.delegate_available,
            "errors": list(self.errors),
            "warnings": list(self.warnings),
        }


def build_lab_config_preview(
    settings: Settings,
    *,
    known_task_codes: Iterable[str] | None = None,
) -> LabConfigPreview:
    """Validate lab pilot settings and return a sanitized preview.

    Never includes private key path contents, key material, or secrets.
    """
    errors: list[str] = []
    hosts, host_errs = parse_allowed_hosts(settings.real_ansible_allowed_hosts)
    codes, code_errs = parse_allowed_task_codes(
        settings.real_ansible_allowed_task_codes
    )
    errors.extend(host_errs)
    errors.extend(code_errs)

    timeout, _timeout_errs = clamp_timeout_seconds(
        getattr(settings, "real_ansible_timeout_seconds", None)
    )
    max_hosts = max_hosts_per_run(settings)
    pilot_mode = bool(getattr(settings, "real_ansible_pilot_mode", False))
    auth_mode = resolve_auth_mode(settings)
    explicit_auth = auth_mode == "explicit"

    from app.services.ssh_delegate_ansible import (  # noqa: PLC0415
        control_node_configured as cn_configured,
        control_node_workdir as cn_workdir,
        delegate_available as cn_delegate_available,
        delegate_blocking_reasons,
        resolve_execution_mode,
    )

    execution_mode = resolve_execution_mode(settings)
    control_configured = cn_configured(settings)
    workdir_value = cn_workdir(settings) or None
    # Never expose secrets; workdir is a non-secret path on the control node.
    delegate_ok = cn_delegate_available(settings)

    inv_configured = inventory_is_configured(settings)
    key_configured = private_key_is_configured(settings)
    user_configured = remote_user_is_configured(settings)

    if not hosts:
        errors.append("REAL_ANSIBLE_ALLOWED_HOSTS is empty (no hosts allowlisted)")
    if not codes:
        errors.append(
            "REAL_ANSIBLE_ALLOWED_TASK_CODES is empty (no task codes allowlisted)"
        )

    known = {c.strip() for c in (known_task_codes or []) if c and str(c).strip()}
    if known:
        for code in codes:
            if code not in known:
                errors.append(
                    f"Unknown task_code {code!r} — not in remediation_catalog "
                    "(never use Excel Remediation or AI drafts)"
                )

    if timeout < TIMEOUT_MIN_SECONDS or timeout > TIMEOUT_MAX_SECONDS:
        errors.append(
            f"REAL_ANSIBLE_TIMEOUT_SECONDS={timeout} out of bounds "
            f"[{TIMEOUT_MIN_SECONDS}, {TIMEOUT_MAX_SECONDS}]"
        )

    if settings.real_ansible_enabled:
        if not inv_configured:
            errors.append(
                "REAL_ANSIBLE_INVENTORY_PATH missing or file not found "
                "(required when REAL_ANSIBLE_ENABLED=true)"
            )
        if explicit_auth:
            if not user_configured:
                errors.append(
                    "REAL_ANSIBLE_REMOTE_USER missing "
                    "(required when REAL_ANSIBLE_AUTH_MODE=explicit)"
                )
            if not key_configured:
                errors.append(
                    "REAL_ANSIBLE_PRIVATE_KEY_PATH missing or file not found "
                    "(required when REAL_ANSIBLE_AUTH_MODE=explicit)"
                )
        if execution_mode == "ssh_delegate":
            for reason in delegate_blocking_reasons(settings):
                if reason not in errors:
                    errors.append(reason)
        if settings.mock_mode:
            errors.append(
                "MOCK_MODE=true — real connectivity remains blocked "
                "(set MOCK_MODE=false only on the lab control host)"
            )
    else:
        errors.append("REAL_ANSIBLE_ENABLED=false (safe default)")
        if settings.mock_mode:
            errors.append("MOCK_MODE=true (safe default)")

    hard_failures = [
        e
        for e in errors
        if e.startswith("Invalid ")
        or e.startswith("Unknown task_code")
        or "out of bounds" in e
        or "INVENTORY_PATH missing" in e
        or (explicit_auth and "REMOTE_USER missing" in e)
        or (explicit_auth and "PRIVATE_KEY_PATH missing" in e)
        or "CONTROL_NODE_HOST missing" in e
        or "CONTROL_NODE_WORKDIR missing" in e
        or "is empty" in e
        or ("MOCK_MODE=true" in e and settings.real_ansible_enabled)
    ]

    auth_ok = (not explicit_auth) or (user_configured and key_configured)
    delegate_ok_for_run = execution_mode != "ssh_delegate" or delegate_ok
    base_connectivity_ok = (
        (not settings.mock_mode)
        and bool(settings.real_ansible_enabled)
        and bool(hosts)
        and bool(codes)
        and inv_configured
        and auth_ok
        and delegate_ok_for_run
        and not hard_failures
    )

    # Phase 10C: connectivity / real dry-run also require pilot_mode.
    connectivity_allowed = base_connectivity_ok and pilot_mode

    pilot_errors: list[str] = []
    if not pilot_mode:
        pilot_errors.append("REAL_ANSIBLE_PILOT_MODE=false (safe default)")
    if not settings.real_ansible_check_mode_only:
        pilot_errors.append(
            "REAL_ANSIBLE_CHECK_MODE_ONLY=false — Phase 10C requires check-mode only"
        )
    if max_hosts < 1:
        pilot_errors.append("REAL_ANSIBLE_MAX_HOSTS_PER_RUN must be >= 1")
    if len(hosts) > max_hosts:
        # Allowlist may list multiple labs, but each run is capped.
        # This is a warning-style readiness note, not a hard block by itself.
        pass
    if not base_connectivity_ok:
        pilot_errors.extend(
            e
            for e in errors
            if e not in pilot_errors
            and e
            not in {
                "REAL_ANSIBLE_ENABLED=false (safe default)",
                "MOCK_MODE=true (safe default)",
            }
        )
        if settings.mock_mode:
            msg = "MOCK_MODE=true — pilot not ready"
            if msg not in pilot_errors:
                pilot_errors.append(msg)
        if not settings.real_ansible_enabled:
            msg = "REAL_ANSIBLE_ENABLED=false — pilot not ready"
            if msg not in pilot_errors:
                pilot_errors.append(msg)
        if not hosts:
            msg = "No allowlisted hosts — pilot not ready"
            if msg not in pilot_errors:
                pilot_errors.append(msg)
        if not codes:
            msg = "No allowlisted task codes — pilot not ready"
            if msg not in pilot_errors:
                pilot_errors.append(msg)
        if not inv_configured:
            msg = "Inventory not configured — pilot not ready"
            if msg not in pilot_errors:
                pilot_errors.append(msg)
        if explicit_auth and not user_configured:
            msg = "Remote user not configured — pilot not ready"
            if msg not in pilot_errors:
                pilot_errors.append(msg)
        if explicit_auth and not key_configured:
            msg = "Private key not configured — pilot not ready"
            if msg not in pilot_errors:
                pilot_errors.append(msg)
        if execution_mode == "ssh_delegate" and not delegate_ok:
            for reason in delegate_blocking_reasons(settings):
                if reason not in pilot_errors:
                    pilot_errors.append(reason)

    pilot_ready = (
        base_connectivity_ok
        and pilot_mode
        and bool(settings.real_ansible_check_mode_only)
        and max_hosts >= 1
        and not any(e.startswith("Unknown task_code") for e in errors)
        and not any(e.startswith("Invalid ") for e in errors)
    )
    if pilot_ready:
        pilot_errors = []

    if connectivity_allowed and pilot_ready:
        status = "ok"
        # Keep validation_errors empty when fully ready.
        errors = []
    elif not settings.real_ansible_enabled or not pilot_mode:
        status = "blocked"
    elif settings.mock_mode and not hard_failures:
        status = "blocked"
    else:
        status = "invalid" if hard_failures else "blocked"

    return LabConfigPreview(
        allowed_hosts=hosts,
        allowed_task_codes=codes,
        inventory_path_configured=inv_configured,
        private_key_configured=key_configured,
        remote_user_configured=user_configured,
        timeout_seconds=timeout,
        validation_status=status,
        validation_errors=errors,
        mock_mode=bool(settings.mock_mode),
        real_ansible_enabled=bool(settings.real_ansible_enabled),
        check_mode_only=bool(settings.real_ansible_check_mode_only),
        connectivity_allowed=connectivity_allowed,
        pilot_mode=pilot_mode,
        max_hosts_per_run=max_hosts,
        pilot_ready=pilot_ready,
        pilot_readiness_errors=pilot_errors,
        auth_mode=auth_mode,
        auth_source=auth_mode,
        execution_mode=execution_mode,
        control_node_configured=control_configured,
        control_node_workdir=workdir_value,
        delegate_available=delegate_ok if execution_mode == "ssh_delegate" else False,
    )


def build_pilot_readiness(
    settings: Settings,
    *,
    known_task_codes: Iterable[str] | None = None,
) -> PilotReadiness:
    """Phase 10C single-host pilot readiness (sanitized)."""
    preview = build_lab_config_preview(
        settings, known_task_codes=known_task_codes
    )
    warnings: list[str] = []
    if preview.max_hosts_per_run == 1:
        warnings.append(
            "Single-host pilot: REAL_ANSIBLE_MAX_HOSTS_PER_RUN=1 "
            "(jobs with more targets cannot use real dry-run)"
        )
    if preview.check_mode_only:
        warnings.append(
            "Check-mode only — real apply/run remains blocked in Phase 10C"
        )
    if preview.auth_mode == "ssh_config":
        warnings.append(
            "Auth mode ssh_config — using system SSH config / inventory / agent "
            "(user/key CLI args are not injected)"
        )
    if preview.execution_mode == "ssh_delegate":
        warnings.append(
            "Execution mode ssh_delegate — Local app / Remote Ansible Control Node "
            "(ansible runs on INFRA-OPS via SSH BatchMode)"
        )
        if not preview.delegate_available:
            warnings.append(
                "ssh_delegate is not fully configured — see control node errors"
            )
    if len(preview.allowed_hosts) > preview.max_hosts_per_run:
        warnings.append(
            f"Allowlist has {len(preview.allowed_hosts)} hosts but each run is "
            f"capped at {preview.max_hosts_per_run}"
        )
    warnings.append(
        "Never use production or critical hosts for the lab pilot"
    )

    errors = list(preview.pilot_readiness_errors)
    if not preview.pilot_ready and not errors:
        errors = list(preview.validation_errors) or [
            "Pilot not ready — see safety-status reasons"
        ]

    return PilotReadiness(
        ready=bool(preview.pilot_ready),
        mock_mode=bool(preview.mock_mode),
        real_ansible_enabled=bool(preview.real_ansible_enabled),
        check_mode_only=bool(preview.check_mode_only),
        pilot_mode=bool(preview.pilot_mode),
        max_hosts_per_run=int(preview.max_hosts_per_run),
        allowed_hosts=list(preview.allowed_hosts),
        allowed_task_codes=list(preview.allowed_task_codes),
        inventory_configured=bool(preview.inventory_path_configured),
        remote_user_configured=bool(preview.remote_user_configured),
        private_key_configured=bool(preview.private_key_configured),
        auth_mode=preview.auth_mode,
        auth_source=preview.auth_source,
        execution_mode=preview.execution_mode,
        control_node_configured=bool(preview.control_node_configured),
        control_node_workdir=preview.control_node_workdir,
        delegate_available=bool(preview.delegate_available),
        errors=errors,
        warnings=warnings,
    )


def lab_config_blocks_real_execution(
    settings: Settings,
    *,
    known_task_codes: Iterable[str] | None = None,
    host: str | None = None,
    task_code: str | None = None,
    require_task_code: bool = True,
    host_count: int | None = None,
) -> list[str]:
    """Return human-readable block reasons for real execution / connectivity."""
    preview = build_lab_config_preview(
        settings, known_task_codes=known_task_codes
    )
    reasons = list(preview.validation_errors)

    if not preview.pilot_mode:
        msg = "REAL_ANSIBLE_PILOT_MODE=false — single-host lab pilot disabled"
        if msg not in reasons:
            reasons.append(msg)

    if host is not None:
        host_key = host.strip()
        if host_key not in set(preview.allowed_hosts):
            reasons.append(
                f"host {host_key!r} is not in REAL_ANSIBLE_ALLOWED_HOSTS"
            )

    if require_task_code and task_code is not None:
        tc = task_code.strip()
        if tc not in set(preview.allowed_task_codes):
            reasons.append(
                f"task_code {tc!r} is not in REAL_ANSIBLE_ALLOWED_TASK_CODES"
            )

    if host_count is not None and host_count > preview.max_hosts_per_run:
        reasons.append(
            f"host count {host_count} exceeds REAL_ANSIBLE_MAX_HOSTS_PER_RUN="
            f"{preview.max_hosts_per_run}"
        )

    uniq: list[str] = []
    for r in reasons:
        if r not in uniq:
            uniq.append(r)
    return uniq


__all__ = [
    "TIMEOUT_DEFAULT_SECONDS",
    "TIMEOUT_MAX_SECONDS",
    "TIMEOUT_MIN_SECONDS",
    "LabConfigPreview",
    "PilotReadiness",
    "build_lab_config_preview",
    "build_pilot_readiness",
    "clamp_timeout_seconds",
    "inventory_is_configured",
    "lab_config_blocks_real_execution",
    "max_hosts_per_run",
    "parse_allowed_hosts",
    "parse_allowed_task_codes",
    "parse_csv_allowlist",
    "private_key_is_configured",
    "remote_user_is_configured",
    "resolve_auth_mode",
    "uses_explicit_auth",
]
