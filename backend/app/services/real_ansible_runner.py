"""Real Ansible Runner adapter — Phase 8B lab/test readiness.

IMPORTANT:
- NEVER imported when MOCK_MODE=true (lazy import from AnsibleExecutionService).
- Real execution requires MOCK_MODE=false, REAL_ANSIBLE_ENABLED=true,
  APP_ENV in {lab, test}, and all targets environment in {lab, test}.
- Production targets and APP_ENV=production remain blocked.
- Only enabled remediation_catalog playbook paths are used — never AI drafts,
  never Excel Remediation text, never arbitrary shell.
- Phase 8B does NOT call ansible_runner.run(); it validates readiness only.
  Live invocation is deferred until per-host result persistence exists.
"""

from __future__ import annotations

import logging
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
    """Validate Phase 8B real-Ansible readiness (no live ansible-runner.run).

    Raises RealAnsibleBlockedError when gated or when readiness-only deferral applies.
    Raises AnsibleRunnerMissingError when ansible-runner is not installed.
    Never falls back to ansible-playbook / subprocess / shell / paramiko.
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

    # 5) ansible-runner must be available — checked via find_spec (no import).
    #    No subprocess/ansible-playbook fallback.
    assert_ansible_runner_available()

    # 6) Phase 8B: dry-run readiness only — never invoke live apply.
    if mode != "dry_run":
        raise RealAnsibleBlockedError(
            "Phase 8B blocks real apply/run. Only dry-run readiness is in scope; "
            "keep MOCK_MODE=true for operator workflows.",
            code="apply_blocked_phase8b",
        )

    limit_hosts = [
        t.device_name
        for t in list(getattr(job, "targets", None) or [])
        if getattr(t, "device_name", None)
    ]

    logger.info(
        "Phase 8B real ansible readiness OK (no live run): job_id=%s mode=%s "
        "playbook=%s inventory=%s limit=%s — ansible-runner available but "
        "ansible_runner.run() is not called until persistence is wired",
        job.id,
        mode,
        playbook_path,
        inventory_path,
        limit_hosts,
    )

    # Intentionally do NOT `import ansible_runner` or call ansible_runner.run()
    # in Phase 8B. Import/call will live only in this guarded function once
    # per-host result persistence is implemented.
    raise RealAnsibleBlockedError(
        "Phase 8B readiness passed: gates OK, playbook/inventory paths OK, "
        "ansible-runner is available. Live ansible-runner invocation is deferred "
        "until per-host result persistence is implemented. "
        f"job_id={job.id} mode={mode} playbook={playbook_path} "
        f"inventory={inventory_path}. Keep MOCK_MODE=true for normal workflows.",
        code="phase8b_readiness_only",
    )
