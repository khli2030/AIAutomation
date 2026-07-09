"""Real Ansible Runner adapter — Phase 8B lab/test readiness.

IMPORTANT:
- NEVER imported when MOCK_MODE=true (lazy import from AnsibleExecutionService).
- Real execution requires MOCK_MODE=false, REAL_ANSIBLE_ENABLED=true,
  APP_ENV in {lab, test}, and all targets environment in {lab, test}.
- Production targets and APP_ENV=production remain blocked.
- Only enabled remediation_catalog playbook paths are used — never AI drafts,
  never Excel Remediation text, never arbitrary shell.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any

from app.config import Settings, get_settings
from app.services.ansible_safety import (
    AnsibleRunnerMissingError,
    RealAnsibleBlockedError,
    assert_ansible_runner_available,
    assert_job_targets_allow_real_ansible,
    assert_settings_allow_real_ansible,
    resolve_inventory_path,
    resolve_playbook_path,
)

if TYPE_CHECKING:
    from app.models.execution_job import ExecutionJob
    from app.models.remediation_catalog import RemediationCatalog

logger = logging.getLogger(__name__)

# Re-export for callers / tests.
__all__ = [
    "AnsibleRunnerMissingError",
    "RealAnsibleBlockedError",
    "RealAnsibleNotImplementedError",
    "run_with_ansible_runner",
]


class RealAnsibleNotImplementedError(RuntimeError):
    """Backward-compatible alias — prefer RealAnsibleBlockedError / missing runner."""


def _collect_target_environments(job: ExecutionJob) -> list[str | None]:
    """Collect explicit environments only — blank target attrs are ignored."""
    envs: list[str | None] = []
    job_env = getattr(job, "environment", None)
    if job_env is not None and str(job_env).strip():
        envs.append(job_env)
    targets = list(getattr(job, "targets", None) or [])
    for target in targets:
        # Targets do not store environment today; job.environment is authoritative.
        # Only include an explicit non-blank per-target env if present later.
        t_env = getattr(target, "environment", None)
        if t_env is not None and str(t_env).strip():
            envs.append(t_env)
    return envs


def run_with_ansible_runner(
    *,
    job: ExecutionJob,
    mode: str,
    catalog: RemediationCatalog | None = None,
    settings: Settings | None = None,
) -> dict[str, Any]:
    """Execute via ansible-runner after Phase 8B safety gates.

    Returns a structured result dict. Raises RealAnsibleBlockedError when gated,
    AnsibleRunnerMissingError when ansible-runner is not installed.
    """
    cfg = settings or get_settings()

    # 1) Global gates (mock / flag / app_env).
    assert_settings_allow_real_ansible(cfg)

    # 2) Target environment gates (production always blocked).
    assert_job_targets_allow_real_ansible(
        job_environment=getattr(job, "environment", None),
        target_environments=_collect_target_environments(job),
    )

    # 3) Catalog playbook only — never AI generated_playbook / remediation text.
    if catalog is None:
        raise RealAnsibleBlockedError(
            "Real Ansible blocked: remediation_catalog entry required "
            "(AI generated_playbook is never executable).",
            code="catalog_required",
        )
    if not getattr(catalog, "is_enabled", False):
        raise RealAnsibleBlockedError(
            f"Real Ansible blocked: catalog task_code={catalog.task_code} is disabled.",
            code="catalog_disabled",
        )
    relative_playbook = (catalog.ansible_playbook_path or "").strip()
    playbook_path = resolve_playbook_path(cfg, relative_playbook)

    # 4) Inventory under ansible/inventories for lab/test only.
    inventory_path = resolve_inventory_path(cfg, getattr(job, "environment", None) or "")

    # 5) ansible-runner must be available — no subprocess/ansible-playbook fallback.
    assert_ansible_runner_available()

    # Lazy import only after gates pass.
    import ansible_runner  # noqa: PLC0415

    private_data_dir = Path(cfg.runner_private_data_dir)
    private_data_dir.mkdir(parents=True, exist_ok=True)

    limit_hosts = [
        t.device_name
        for t in list(getattr(job, "targets", None) or [])
        if getattr(t, "device_name", None)
    ]
    cmdline_parts: list[str] = []
    if mode == "dry_run":
        cmdline_parts.append("--check")
    if not cfg.ansible_host_key_checking:
        # Default remains True (safe). Only pass override when explicitly disabled.
        pass

    envvars = {
        "ANSIBLE_HOST_KEY_CHECKING": "True" if cfg.ansible_host_key_checking else "False",
        "ANSIBLE_ROLES_PATH": "",
    }

    logger.info(
        "Phase 8B real ansible-runner: job_id=%s mode=%s playbook=%s inventory=%s "
        "limit=%s (no AI draft, no remediation text, no shell)",
        job.id,
        mode,
        playbook_path,
        inventory_path,
        limit_hosts,
    )

    run_kwargs: dict[str, Any] = {
        "private_data_dir": str(private_data_dir / f"job-{job.id}-{mode}"),
        "playbook": str(playbook_path),
        "inventory": str(inventory_path),
        "quiet": True,
        "envvars": envvars,
    }
    if cmdline_parts:
        run_kwargs["cmdline"] = " ".join(cmdline_parts)
    if limit_hosts:
        run_kwargs["limit"] = ",".join(limit_hosts)

    # ansible-runner writes under private_data_dir only (runtime artifacts).
    runner = ansible_runner.run(**run_kwargs)

    status = getattr(runner, "status", "unknown")
    rc = getattr(runner, "rc", None)
    stdout_text = ""
    stdout_obj = getattr(runner, "stdout", None)
    if stdout_obj is not None:
        try:
            stdout_text = stdout_obj.read() if hasattr(stdout_obj, "read") else str(stdout_obj)
        except Exception:  # noqa: BLE001 — best-effort capture only
            stdout_text = ""

    return {
        "ok": status == "successful" and (rc in (0, None)),
        "status": status,
        "rc": rc,
        "mode": mode,
        "playbook": str(playbook_path),
        "inventory": str(inventory_path),
        "used_ai_generated_playbook": False,
        "used_remediation_text": False,
        "execution_backend": "ansible-runner",
        "limit": limit_hosts,
        "stdout": stdout_text,
    }
