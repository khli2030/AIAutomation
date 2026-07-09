"""Real Ansible Runner adapter — Phase 8C lab-only dry-run.

IMPORTANT:
- NEVER imported when MOCK_MODE=true (lazy import from AnsibleExecutionService).
- Real dry-run requires MOCK_MODE=false, REAL_ANSIBLE_ENABLED=true,
  APP_ENV in {lab, test}, and all targets environment in {lab, test}.
- Production / staging targets and APP_ENV=production remain blocked.
- Only enabled remediation_catalog playbook paths — never AI drafts,
  never Excel Remediation text, never arbitrary shell.
- Phase 8C calls ansible-runner Python API with --check only.
- Real apply/run remains blocked.
- No ansible-playbook / subprocess / shell / paramiko fallback.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from app.config import Settings, get_settings
from app.services.ansible_safety import (
    AnsibleRunnerMissingError,
    RealAnsibleBlockedError,
    assert_ansible_runner_available,
    assert_job_targets_allow_real_ansible,
    assert_settings_allow_real_ansible,
    build_preflight_report,
    resolve_inventory_path,
    resolve_playbook_path,
)

if TYPE_CHECKING:
    from app.models.execution_job import ExecutionJob
    from app.models.remediation_catalog import RemediationCatalog

logger = logging.getLogger(__name__)

__all__ = [
    "AnsibleRunnerMissingError",
    "HostDryRunOutcome",
    "RealAnsibleBlockedError",
    "RealAnsibleNotImplementedError",
    "run_with_ansible_runner",
]


class RealAnsibleNotImplementedError(RuntimeError):
    """Backward-compatible alias — prefer RealAnsibleBlockedError / missing runner."""


@dataclass(frozen=True)
class HostDryRunOutcome:
    device_name: str
    status: str
    changed: bool
    skipped: bool
    stdout: str
    stderr: str
    return_code: int


def _collect_target_environments(job: ExecutionJob) -> list[str | None]:
    """Collect explicit environments only — blank target attrs are ignored."""
    envs: list[str | None] = []
    job_env = getattr(job, "environment", None)
    if job_env is not None and str(job_env).strip():
        envs.append(job_env)
    targets = list(getattr(job, "targets", None) or [])
    for target in targets:
        t_env = getattr(target, "environment", None)
        if t_env is not None and str(t_env).strip():
            envs.append(t_env)
    return envs


def _assert_preflight_allows_dry_run(
    settings: Settings, *, catalog_relative_path: str
) -> None:
    """Requirement: preflight must pass before real dry-run."""
    report = build_preflight_report(
        settings, enabled_catalog_paths=[catalog_relative_path]
    )
    if not report.real_ansible_allowed:
        blockers = "; ".join(report.blockers) or "unknown preflight failure"
        raise RealAnsibleBlockedError(
            f"Real dry-run blocked: preflight failed — {blockers}",
            code="preflight_failed",
        )


def _event_host(event: dict[str, Any]) -> str | None:
    data = event.get("event_data") or {}
    host = data.get("host") or data.get("remote_addr") or event.get("host")
    if host is None:
        return None
    name = str(host).strip()
    return name or None


def _parse_host_events(
    runner: Any,
    *,
    expected_hosts: list[str],
) -> list[HostDryRunOutcome]:
    """Parse ansible-runner host events into per-host dry-run outcomes.

    If expected hosts exist but no usable host events are found, raise so the
    caller fails safely (Phase 8C limitation — do not invent success).
    """
    by_host: dict[str, HostDryRunOutcome] = {}
    events = getattr(runner, "events", None) or []

    for raw in events:
        if not isinstance(raw, dict):
            continue
        event_name = str(raw.get("event") or "")
        host = _event_host(raw)
        if not host:
            continue
        data = raw.get("event_data") or {}
        res = data.get("res") if isinstance(data.get("res"), dict) else {}
        stdout = ""
        stderr = ""
        if isinstance(res, dict):
            stdout = str(res.get("stdout") or res.get("msg") or "")
            stderr = str(res.get("stderr") or "")
        # Keep a compact event trace when stdout empty.
        if not stdout:
            try:
                stdout = json.dumps(
                    {"event": event_name, "res": res},
                    ensure_ascii=False,
                    default=str,
                )[:4000]
            except TypeError:
                stdout = event_name

        if event_name in {"runner_on_failed", "runner_item_on_failed"}:
            by_host[host] = HostDryRunOutcome(
                device_name=host,
                status="failed",
                changed=False,
                skipped=False,
                stdout=stdout,
                stderr=stderr or stdout,
                return_code=int(res.get("rc") or 2) if isinstance(res, dict) else 2,
            )
        elif event_name in {"runner_on_unreachable"}:
            by_host[host] = HostDryRunOutcome(
                device_name=host,
                status="unreachable",
                changed=False,
                skipped=False,
                stdout=stdout,
                stderr=stderr or "unreachable",
                return_code=int(res.get("rc") or 4) if isinstance(res, dict) else 4,
            )
        elif event_name in {"runner_on_skipped", "runner_item_on_skipped"}:
            # Do not overwrite a prior failure for the same host.
            prev = by_host.get(host)
            if prev and prev.status in {"failed", "unreachable"}:
                continue
            by_host[host] = HostDryRunOutcome(
                device_name=host,
                status="skipped",
                changed=False,
                skipped=True,
                stdout=stdout,
                stderr=stderr,
                return_code=0,
            )
        elif event_name in {"runner_on_ok", "runner_item_on_ok", "runner_on_changed"}:
            prev = by_host.get(host)
            if prev and prev.status in {"failed", "unreachable"}:
                continue
            changed = bool(res.get("changed")) if isinstance(res, dict) else False
            if event_name == "runner_on_changed":
                changed = True
            by_host[host] = HostDryRunOutcome(
                device_name=host,
                status="success",
                changed=changed,
                skipped=False,
                stdout=stdout,
                stderr=stderr,
                return_code=int(res.get("rc") or 0) if isinstance(res, dict) else 0,
            )

    outcomes = list(by_host.values())
    if expected_hosts:
        expected = {h.strip() for h in expected_hosts if h and str(h).strip()}
        seen = {h.device_name for h in outcomes}
        missing = sorted(expected - seen)
        if missing:
            raise RealAnsibleBlockedError(
                "Per-host event parsing incomplete: ansible-runner returned no "
                f"usable host events for expected targets {missing}. "
                "Failing safely without inventing success. Limitation: Phase 8C "
                "requires runner host events for every --limit host "
                "(runner_on_ok/failed/skipped/unreachable).",
                code="host_parse_incomplete",
            )
    return outcomes


def run_with_ansible_runner(
    *,
    job: ExecutionJob,
    mode: str,
    catalog: RemediationCatalog | None = None,
    settings: Settings | None = None,
) -> dict[str, Any]:
    """Run lab-only real dry-run via ansible-runner check mode (Phase 8C).

    Raises RealAnsibleBlockedError when gated.
    Raises AnsibleRunnerMissingError when ansible-runner is not installed.
    Never falls back to ansible-playbook / subprocess / shell / paramiko.
    Never performs real apply/run.
    """
    cfg = settings or get_settings()

    # 1) Global gates (mock / flag / app_env).
    assert_settings_allow_real_ansible(cfg)

    # 2) Target environment gates (production/staging always blocked).
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

    # 5) ansible-runner package must be present (find_spec; import only below).
    assert_ansible_runner_available()

    # 6) Phase 8C: dry-run only — never invoke live apply.
    if mode != "dry_run":
        raise RealAnsibleBlockedError(
            "Phase 8C blocks real apply/run. Only ansible-runner check-mode "
            "dry-run is allowed; keep MOCK_MODE=true for operator workflows.",
            code="apply_blocked_phase8c",
        )

    # 7) Preflight must pass before real dry-run.
    _assert_preflight_allows_dry_run(cfg, catalog_relative_path=relative_playbook)

    limit_hosts = [
        t.device_name
        for t in list(getattr(job, "targets", None) or [])
        if getattr(t, "device_name", None)
    ]
    # Never run check-mode against the full inventory without an explicit limit.
    if not limit_hosts:
        raise RealAnsibleBlockedError(
            "Real dry-run blocked: job has no targets. Refusing unbounded "
            "inventory check-mode run.",
            code="missing_targets",
        )

    private_data_dir = Path(cfg.runner_private_data_dir) / f"job-{job.id}-dry-run"
    private_data_dir.mkdir(parents=True, exist_ok=True)

    # Lazy import ONLY after gates + preflight — guarded real dry-run path.
    import ansible_runner  # noqa: PLC0415

    run_kwargs: dict[str, Any] = {
        "private_data_dir": str(private_data_dir),
        "playbook": str(playbook_path),
        "inventory": str(inventory_path),
        "quiet": True,
        "cmdline": "--check",
        "envvars": {
            "ANSIBLE_HOST_KEY_CHECKING": (
                "True" if cfg.ansible_host_key_checking else "False"
            ),
        },
    }
    run_kwargs["limit"] = ",".join(limit_hosts)

    logger.info(
        "Phase 8C real dry-run: job_id=%s playbook=%s inventory=%s limit=%s "
        "(check mode only; no AI draft; no remediation text; no shell)",
        job.id,
        playbook_path,
        inventory_path,
        limit_hosts,
    )

    runner = ansible_runner.run(**run_kwargs)
    status = str(getattr(runner, "status", "unknown") or "unknown")
    rc = getattr(runner, "rc", None)
    try:
        rc_int = int(rc) if rc is not None else None
    except (TypeError, ValueError):
        rc_int = None

    host_outcomes = _parse_host_events(runner, expected_hosts=limit_hosts)
    ok = status == "successful" and (rc_int in (0, None)) and not any(
        h.status in {"failed", "unreachable"} for h in host_outcomes
    )

    return {
        "ok": ok,
        "status": status,
        "rc": rc_int,
        "mode": "dry_run",
        "check_mode": True,
        "cmdline": "--check",
        "playbook": str(playbook_path),
        "inventory": str(inventory_path),
        "used_ai_generated_playbook": False,
        "used_remediation_text": False,
        "execution_backend": "ansible-runner",
        "limit": limit_hosts,
        "hosts": [
            {
                "device_name": h.device_name,
                "status": h.status,
                "changed": h.changed,
                "skipped": h.skipped,
                "stdout": h.stdout,
                "stderr": h.stderr,
                "return_code": h.return_code,
            }
            for h in host_outcomes
        ],
    }
