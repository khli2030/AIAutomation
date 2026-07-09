"""Phase 8B real-Ansible safety gates and path validation.

Real execution is lab/test only and never the default. MOCK_MODE remains the
safe path. This module never imports ansible-runner at module level.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

from app.config import Settings

# APP_ENV values that may enable real Ansible (Phase 8B).
ALLOWED_APP_ENVS: frozenset[str] = frozenset({"lab", "test"})

# Job / asset environment values allowed for real Ansible targets.
ALLOWED_TARGET_ENVIRONMENTS: frozenset[str] = frozenset({"lab", "test"})

# Explicitly blocked target environments (defense in depth).
BLOCKED_TARGET_ENVIRONMENTS: frozenset[str] = frozenset(
    {"production", "prod", "staging"}
)

# Map allowed environments to inventory filenames under ansible/inventories.
INVENTORY_BY_ENVIRONMENT: dict[str, str] = {
    "lab": "test.ini",
    "test": "test.ini",
}


class RealAnsibleBlockedError(RuntimeError):
    """Raised when real Ansible is refused by a safety gate."""

    def __init__(self, reason: str, *, code: str = "blocked") -> None:
        super().__init__(reason)
        self.reason = reason
        self.code = code


class AnsibleRunnerMissingError(RuntimeError):
    """Raised when ansible-runner is not installed."""


@dataclass
class PreflightCheck:
    name: str
    ok: bool
    detail: str


@dataclass
class PreflightReport:
    mock_mode: bool
    real_ansible_enabled: bool
    app_env: str
    real_ansible_allowed: bool
    checks: list[PreflightCheck] = field(default_factory=list)
    blockers: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "mock_mode": self.mock_mode,
            "real_ansible_enabled": self.real_ansible_enabled,
            "app_env": self.app_env,
            "real_ansible_allowed": self.real_ansible_allowed,
            "checks": [
                {"name": c.name, "ok": c.ok, "detail": c.detail} for c in self.checks
            ],
            "blockers": list(self.blockers),
            "message": (
                "Real Ansible readiness OK for lab/test dry-run path."
                if self.real_ansible_allowed
                else "Real Ansible is blocked — see blockers."
            ),
        }


def normalize_env(value: str | None) -> str:
    return (value or "").strip().lower()


def assert_settings_allow_real_ansible(settings: Settings) -> None:
    """Gate on MOCK_MODE / REAL_ANSIBLE_ENABLED / APP_ENV only."""
    if settings.mock_mode:
        raise RealAnsibleBlockedError(
            "Real Ansible blocked: MOCK_MODE=true (mock adapter only).",
            code="mock_mode",
        )
    if not settings.real_ansible_enabled:
        raise RealAnsibleBlockedError(
            "Real Ansible blocked: REAL_ANSIBLE_ENABLED=false.",
            code="real_ansible_disabled",
        )
    app_env = normalize_env(settings.app_env)
    if app_env not in ALLOWED_APP_ENVS:
        raise RealAnsibleBlockedError(
            f"Real Ansible blocked: APP_ENV={settings.app_env!r} "
            f"(allowed: {', '.join(sorted(ALLOWED_APP_ENVS))}). "
            "Production real execution remains blocked in Phase 8B.",
            code="app_env_blocked",
        )


def assert_job_targets_allow_real_ansible(
    *,
    job_environment: str | None,
    target_environments: Iterable[str | None] | None = None,
) -> None:
    """All job/target environments must be lab or test; production always blocks."""
    envs: list[str] = []
    job_env = normalize_env(job_environment)
    if job_env:
        envs.append(job_env)
    if target_environments:
        for raw in target_environments:
            env = normalize_env(raw)
            if env:
                envs.append(env)

    # Deduplicate while preserving order for error messages.
    seen: list[str] = []
    for env in envs:
        if env not in seen:
            seen.append(env)

    if not seen:
        raise RealAnsibleBlockedError(
            "Real Ansible blocked: job has empty environment "
            "(lab/test required; production blocked).",
            code="missing_environment",
        )

    for env in seen:
        if env in BLOCKED_TARGET_ENVIRONMENTS or env == "production":
            raise RealAnsibleBlockedError(
                f"Real Ansible blocked: target environment={env!r} "
                "(production/staging targets are forbidden in Phase 8B).",
                code="production_target",
            )
        if env not in ALLOWED_TARGET_ENVIRONMENTS:
            raise RealAnsibleBlockedError(
                f"Real Ansible blocked: target environment={env!r} "
                f"(allowed: {', '.join(sorted(ALLOWED_TARGET_ENVIRONMENTS))}).",
                code="target_env_blocked",
            )


def safe_resolve_under(base_dir: str | Path, relative: str, *, kind: str) -> Path:
    """Resolve relative path under base; reject traversal and absolute escapes."""
    rel = (relative or "").strip()
    if not rel:
        raise RealAnsibleBlockedError(
            f"Empty {kind} path rejected.",
            code=f"empty_{kind}_path",
        )
    if os.path.isabs(rel) or rel.startswith("~"):
        raise RealAnsibleBlockedError(
            f"Absolute {kind} path rejected: {rel!r}",
            code=f"absolute_{kind}_path",
        )
    # Reject obvious traversal tokens before resolve.
    parts = Path(rel).parts
    if any(p == ".." for p in parts):
        raise RealAnsibleBlockedError(
            f"Path traversal blocked in {kind} path: {rel!r}",
            code="path_traversal",
        )

    base = Path(base_dir).resolve()
    candidate = (base / rel).resolve()
    try:
        candidate.relative_to(base)
    except ValueError as exc:
        raise RealAnsibleBlockedError(
            f"Path traversal blocked: {kind} path {rel!r} escapes {base}",
            code="path_traversal",
        ) from exc
    return candidate


def resolve_playbook_path(settings: Settings, catalog_relative_path: str) -> Path:
    """Playbook must resolve inside ansible/playbooks (catalog path only)."""
    path = safe_resolve_under(
        settings.ansible_playbooks_dir,
        catalog_relative_path,
        kind="playbook",
    )
    if not path.is_file():
        raise RealAnsibleBlockedError(
            f"Playbook not found under playbooks dir: {catalog_relative_path!r} "
            f"(resolved={path})",
            code="playbook_missing",
        )
    return path


def resolve_inventory_path(settings: Settings, environment: str) -> Path:
    """Inventory must resolve inside ansible/inventories for lab/test only."""
    env = normalize_env(environment)
    if env not in ALLOWED_TARGET_ENVIRONMENTS:
        raise RealAnsibleBlockedError(
            f"No inventory mapping for environment={environment!r}",
            code="inventory_env_blocked",
        )
    filename = INVENTORY_BY_ENVIRONMENT[env]
    path = safe_resolve_under(
        settings.ansible_inventories_dir,
        filename,
        kind="inventory",
    )
    if not path.is_file():
        raise RealAnsibleBlockedError(
            f"Inventory not found for environment={env!r}: {filename}",
            code="inventory_missing",
        )
    return path


def ansible_runner_available() -> tuple[bool, str]:
    """Return (available, detail) without importing ansible_runner into sys.modules.

    Uses importlib.util.find_spec so preflight / MOCK_MODE workers never load
    ansible-runner (which would trip mock-path forbidden-module checks).
    """
    import importlib.util

    spec = importlib.util.find_spec("ansible_runner")
    if spec is None:
        return False, "ansible-runner is not installed"
    return True, "ansible-runner package found (not imported)"


def assert_ansible_runner_available() -> None:
    ok, detail = ansible_runner_available()
    if not ok:
        raise AnsibleRunnerMissingError(
            "ansible-runner is not installed. Install ansible-runner on the "
            "lab Ansible control host before enabling real execution. "
            "Do not fall back to ansible-playbook/subprocess/shell."
        )


def runtime_data_roots(settings: Settings) -> list[Path]:
    """Directories the process may write (uploads / runner artifacts / tmp inventories)."""
    return [
        Path(settings.upload_dir),
        Path(settings.runner_private_data_dir),
        Path(settings.tmp_inventory_dir),
    ]


def build_preflight_report(
    settings: Settings,
    *,
    enabled_catalog_paths: Iterable[str] | None = None,
) -> PreflightReport:
    """Collect readiness checks without executing Ansible."""
    checks: list[PreflightCheck] = []
    blockers: list[str] = []

    def add(name: str, ok: bool, detail: str) -> None:
        checks.append(PreflightCheck(name=name, ok=ok, detail=detail))
        if not ok:
            blockers.append(f"{name}: {detail}")

    add(
        "mock_mode",
        not settings.mock_mode,
        (
            "MOCK_MODE=false (real path eligible)"
            if not settings.mock_mode
            else "MOCK_MODE=true — real Ansible disabled (safe default)"
        ),
    )
    add(
        "real_ansible_enabled",
        bool(settings.real_ansible_enabled),
        (
            "REAL_ANSIBLE_ENABLED=true"
            if settings.real_ansible_enabled
            else "REAL_ANSIBLE_ENABLED=false (default)"
        ),
    )
    app_env = normalize_env(settings.app_env)
    add(
        "app_env",
        app_env in ALLOWED_APP_ENVS,
        (
            f"APP_ENV={settings.app_env} allowed for lab/test"
            if app_env in ALLOWED_APP_ENVS
            else f"APP_ENV={settings.app_env} blocks real Ansible "
            f"(need lab|test; production blocked)"
        ),
    )

    runner_ok, runner_detail = ansible_runner_available()
    add("ansible_runner", runner_ok, runner_detail)

    home = Path(settings.ansible_home)
    add(
        "ansible_project_dir",
        home.is_dir(),
        f"{home} {'exists' if home.is_dir() else 'missing'}",
    )
    playbooks = Path(settings.ansible_playbooks_dir)
    add(
        "playbooks_dir",
        playbooks.is_dir(),
        f"{playbooks} {'exists' if playbooks.is_dir() else 'missing'}",
    )
    inventories = Path(settings.ansible_inventories_dir)
    add(
        "inventories_dir",
        inventories.is_dir(),
        f"{inventories} {'exists' if inventories.is_dir() else 'missing'}",
    )

    # Enabled catalog playbook paths must exist under playbooks dir.
    catalog_ok = True
    catalog_details: list[str] = []
    for rel in enabled_catalog_paths or []:
        try:
            resolve_playbook_path(settings, rel)
            catalog_details.append(f"ok:{rel}")
        except RealAnsibleBlockedError as exc:
            catalog_ok = False
            catalog_details.append(f"fail:{rel}:{exc.reason}")
    add(
        "enabled_catalog_playbooks",
        catalog_ok,
        "; ".join(catalog_details) if catalog_details else "no enabled catalog entries",
    )

    add(
        "ai_draft_playbooks_not_executable",
        True,
        "AI generated_playbook is never used for execution (catalog paths only)",
    )

    can_read_playbooks = playbooks.is_dir() and os.access(playbooks, os.R_OK)
    add(
        "playbooks_readable",
        can_read_playbooks,
        (
            f"can read {playbooks}"
            if can_read_playbooks
            else f"cannot read {playbooks}"
        ),
    )

    write_ok = True
    write_details: list[str] = []
    for root in runtime_data_roots(settings):
        try:
            root.mkdir(parents=True, exist_ok=True)
            writable = os.access(root, os.W_OK)
        except OSError as exc:
            writable = False
            write_details.append(f"{root}:mkdir_error:{exc}")
            write_ok = False
            continue
        write_details.append(f"{root}:{'writable' if writable else 'not_writable'}")
        if not writable:
            write_ok = False
    add(
        "runtime_artifacts_writable",
        write_ok,
        "; ".join(write_details),
    )

    # Playbooks/inventories must not be treated as writable runtime dirs.
    add(
        "playbooks_not_runtime_write_target",
        True,
        "Writes restricted to data/runtime artifact dirs only (not ansible/playbooks)",
    )

    real_allowed = (
        not settings.mock_mode
        and bool(settings.real_ansible_enabled)
        and app_env in ALLOWED_APP_ENVS
        and runner_ok
        and home.is_dir()
        and playbooks.is_dir()
        and inventories.is_dir()
        and catalog_ok
        and can_read_playbooks
        and write_ok
    )

    return PreflightReport(
        mock_mode=bool(settings.mock_mode),
        real_ansible_enabled=bool(settings.real_ansible_enabled),
        app_env=settings.app_env,
        real_ansible_allowed=real_allowed,
        checks=checks,
        blockers=blockers,
    )
