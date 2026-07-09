"""Ansible execution facade.

MOCK_MODE=true  → fake realistic per-host results; never runs ansible-runner/shell/SSH.
MOCK_MODE=false → Phase 8C lab-only real dry-run (ansible-runner --check), gated by:
  REAL_ANSIBLE_ENABLED=true, APP_ENV in {lab,test}, targets environment in {lab,test}.
  Real apply/run remains blocked.

Hard guarantee when MOCK_MODE=true:
- No import of ansible_runner / paramiko
- No subprocess / os.system / shell
- No ansible-playbook invocation
- Real adapter module is not imported
"""

from __future__ import annotations

import logging
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.config import Settings, get_settings
from app.constants.job_result_type import JobResultType
from app.constants.job_status import JobStatus
from app.models.execution_job import ExecutionJob
from app.models.execution_job_target import ExecutionJobTarget
from app.models.job_result import JobResult
from app.models.remediation_catalog import RemediationCatalog
from app.services.audit import write_audit_log

logger = logging.getLogger(__name__)

ExecutionMode = Literal["dry_run", "apply"]


def _result_type_for_mode(mode: ExecutionMode) -> str:
    """Map execution mode to persisted job_results.result_type."""
    return JobResultType.DRY_RUN.value if mode == "dry_run" else JobResultType.RUN.value

# Modules that must never be loaded/used while MOCK_MODE=true.
_FORBIDDEN_MODULES_WHEN_MOCK: frozenset[str] = frozenset(
    {
        "ansible_runner",
        "ansible.executor",
        "ansible.cli",
        "paramiko",
        "fabric",
        "invoke",
    }
)


class AnsibleExecutionError(Exception):
    """Raised when a job cannot be executed (missing job, policy, etc.)."""


class MockModeViolationError(AnsibleExecutionError):
    """Raised if a real-execution code path is entered while MOCK_MODE=true."""


@dataclass(frozen=True)
class HostMockOutcome:
    status: str
    changed: bool
    skipped: bool
    stdout: str
    stderr: str
    return_code: int


@dataclass
class JobExecutionSummary:
    job_id: int
    mode: ExecutionMode
    mock_mode: bool
    job_status: str
    dry_run_status: str | None
    hosts_total: int
    hosts_success: int
    hosts_failed: int
    hosts_changed: int
    hosts_skipped: int


class AnsibleExecutionService:
    """Entry point used by Celery tasks for dry-run and real apply."""

    def __init__(self, db: Session, settings: Settings | None = None) -> None:
        self.db = db
        self.settings = settings or get_settings()

    def dry_run_job(
        self,
        job_id: int,
        *,
        actor: str = "system",
        role: str | None = None,
    ) -> JobExecutionSummary:
        """Run check-mode (or mock equivalent) for an execution job.

        Allowed only when job status is waiting_dry_run.
        """
        return self._execute(
            job_id=job_id, mode="dry_run", actor=actor, role=role
        )

    def run_job(
        self,
        job_id: int,
        *,
        actor: str = "system",
        role: str | None = None,
    ) -> JobExecutionSummary:
        """Run apply-mode (or mock equivalent) for an approved execution job.

        Allowed only when job status is approved.
        """
        return self._execute(
            job_id=job_id, mode="apply", actor=actor, role=role
        )

    def _execute(
        self,
        *,
        job_id: int,
        mode: ExecutionMode,
        actor: str = "system",
        role: str | None = None,
    ) -> JobExecutionSummary:
        job = self._load_job(job_id)
        self._assert_job_status_allows(job=job, mode=mode)
        catalog = self._assert_catalog_allows(job.task_code)

        # Branch FIRST on MOCK_MODE so the real adapter is never imported/called.
        if self.settings.mock_mode:
            self._assert_mock_mode_safe()
            return self._execute_mock(
                job=job, mode=mode, catalog=catalog, actor=actor, role=role
            )

        return self._execute_real(
            job=job, mode=mode, actor=actor, role=role, catalog=catalog
        )

    def _assert_job_status_allows(self, *, job: ExecutionJob, mode: ExecutionMode) -> None:
        if mode == "dry_run":
            # First dry-run: waiting_dry_run. Retry after failure: dry_run_failed
            # (replaces previous dry_run result_type rows only).
            allowed = {
                JobStatus.WAITING_DRY_RUN.value,
                JobStatus.DRY_RUN_FAILED.value,
            }
            if job.status not in allowed:
                raise AnsibleExecutionError(
                    "Dry-run allowed only when job status is waiting_dry_run "
                    f"or dry_run_failed (current status={job.status})"
                )
            return
        if job.status != JobStatus.APPROVED.value:
            raise AnsibleExecutionError(
                "Run allowed only when job status=approved "
                f"(current status={job.status})"
            )

    def _assert_mock_mode_safe(self) -> None:
        """Defense-in-depth: refuse if MOCK_MODE is inconsistent or forbidden libs loaded."""
        if not self.settings.mock_mode:
            raise MockModeViolationError(
                "Internal error: mock path entered while MOCK_MODE=false"
            )
        loaded = sorted(
            name for name in _FORBIDDEN_MODULES_WHEN_MOCK if name in sys.modules
        )
        if loaded:
            raise MockModeViolationError(
                "MOCK_MODE=true but forbidden execution modules are already imported: "
                + ", ".join(loaded)
            )
        # Real adapter must not be imported in mock mode.
        if "app.services.real_ansible_runner" in sys.modules:
            raise MockModeViolationError(
                "MOCK_MODE=true but real_ansible_runner is imported — refusing to continue"
            )

    def _load_job(self, job_id: int) -> ExecutionJob:
        job = self.db.scalars(
            select(ExecutionJob)
            .where(ExecutionJob.id == job_id)
            .options(selectinload(ExecutionJob.targets))
        ).first()
        if job is None:
            raise AnsibleExecutionError(f"Execution job {job_id} not found")
        return job

    def _assert_catalog_allows(self, task_code: str) -> RemediationCatalog:
        catalog = self.db.scalars(
            select(RemediationCatalog).where(RemediationCatalog.task_code == task_code)
        ).first()
        if catalog is None:
            raise AnsibleExecutionError(
                f"task_code {task_code} is not in remediation_catalog"
            )
        if not catalog.is_enabled:
            raise AnsibleExecutionError(
                f"task_code {task_code} is disabled in remediation_catalog"
            )
        # Never use AI generated_playbook — only catalog playbook paths.
        playbook_path = (catalog.ansible_playbook_path or "").strip()
        if not playbook_path:
            raise AnsibleExecutionError(
                f"task_code {task_code} has empty ansible_playbook_path in catalog"
            )
        return catalog

    # ------------------------------------------------------------------
    # MOCK path — no ansible-runner, no shell, no SSH
    # ------------------------------------------------------------------

    def _execute_mock(
        self,
        *,
        job: ExecutionJob,
        mode: ExecutionMode,
        catalog: RemediationCatalog,
        actor: str = "system",
        role: str | None = None,
    ) -> JobExecutionSummary:
        # Re-check at entry so this method is never a backdoor into real execution.
        if not self.settings.mock_mode:
            raise MockModeViolationError(
                "Refusing _execute_mock while MOCK_MODE=false"
            )
        self._assert_mock_mode_safe()

        playbook_path = (catalog.ansible_playbook_path or "").strip()

        now = datetime.now(UTC)
        running_status = (
            JobStatus.DRY_RUN_RUNNING.value
            if mode == "dry_run"
            else JobStatus.RUNNING.value
        )
        job.status = running_status
        if mode == "dry_run":
            job.dry_run_status = JobStatus.DRY_RUN_RUNNING.value
        job.started_at = job.started_at or now
        self.db.flush()

        write_audit_log(
            self.db,
            actor=actor,
            action="dry_run" if mode == "dry_run" else "run",
            entity_type="execution_job",
            entity_id=job.id,
            role=role,
            details={
                "event": "started",
                "mock_mode": True,
                "mode": mode,
                "result_type": _result_type_for_mode(mode),
                "task_code": job.task_code,
                "ansible_playbook_path": playbook_path,
                "used_ai_generated_playbook": False,
                "execution_backend": "mock",
            },
        )

        # Replace previous results for THIS mode only — never wipe the other type.
        # Dry-run re-run (if status allows) replaces dry_run rows; run never deletes dry_run.
        result_type = _result_type_for_mode(mode)
        existing = self.db.scalars(
            select(JobResult).where(
                JobResult.job_id == job.id,
                JobResult.result_type == result_type,
            )
        ).all()
        for row in existing:
            self.db.delete(row)
        self.db.flush()

        targets = list(job.targets)
        if not targets:
            summary = self._finalize_job(
                job=job,
                mode=mode,
                outcomes=[],
                mock_mode=True,
                actor=actor,
                role=role,
            )
            self.db.commit()
            return summary

        outcomes: list[tuple[ExecutionJobTarget, HostMockOutcome]] = []
        for index, target in enumerate(targets):
            outcome = self._mock_host_outcome(
                job=job,
                target=target,
                mode=mode,
                index=index,
                playbook_path=playbook_path,
            )
            outcomes.append((target, outcome))
            target.status = outcome.status
            self.db.add(
                JobResult(
                    job_id=job.id,
                    result_type=result_type,
                    device_name=target.device_name,
                    status=outcome.status,
                    changed=outcome.changed,
                    skipped=outcome.skipped,
                    stdout=outcome.stdout,
                    stderr=outcome.stderr,
                    return_code=outcome.return_code,
                )
            )

        summary = self._finalize_job(
            job=job,
            mode=mode,
            outcomes=outcomes,
            mock_mode=True,
            actor=actor,
            role=role,
        )
        self.db.commit()
        # Final safety check after mock work — still no forbidden modules.
        self._assert_mock_mode_safe()
        logger.info(
            "MOCK %s completed for job_id=%s status=%s hosts=%s (no ansible/shell/SSH)",
            mode,
            job.id,
            summary.job_status,
            summary.hosts_total,
        )
        return summary

    def _mock_host_outcome(
        self,
        *,
        job: ExecutionJob,
        target: ExecutionJobTarget,
        mode: ExecutionMode,
        index: int,
        playbook_path: str = "",
    ) -> HostMockOutcome:
        """Generate fake but realistic Ansible-like output per host.

        Pure string generation — no network, no subprocess, no SSH.
        Deterministic pattern (no randomness) so tests are stable:
        - every 7th host → failed
        - every 5th host (not failed) → skipped / already compliant
        - otherwise success (dry-run: ok preview; apply: changed)

        playbook_path must come from enabled remediation_catalog — never AI drafts.
        """
        host = target.device_name
        ip = target.ip_address or "0.0.0.0"
        task = job.task_code
        playbook = playbook_path or f"{task.lower()}.yml"

        if index % 7 == 6:
            return HostMockOutcome(
                status="failed",
                changed=False,
                skipped=False,
                stdout=(
                    f"PLAY [MOCK {mode}] *********************************************************\n"
                    f"TASK [Apply {task}] *******************************************************\n"
                    f"fatal: [{host}]: FAILED! => "
                    f'{{"msg": "MOCK simulated failure on {host} ({ip})"}}\n'
                    f"PLAY RECAP *********************************************************************\n"
                    f"{host} : ok=0 changed=0 unreachable=0 failed=1 skipped=0 rescued=0 ignored=0\n"
                ),
                stderr=f"MOCK: simulated ansible failure for {host} playbook={playbook}\n",
                return_code=2,
            )

        if index % 5 == 4:
            return HostMockOutcome(
                status="skipped",
                changed=False,
                skipped=True,
                stdout=(
                    f"PLAY [MOCK {mode}] *********************************************************\n"
                    f"TASK [Apply {task}] *******************************************************\n"
                    f"skipping: [{host}] => {{\"msg\": \"MOCK already compliant\"}}\n"
                    f"PLAY RECAP *********************************************************************\n"
                    f"{host} : ok=1 changed=0 unreachable=0 failed=0 skipped=1 rescued=0 ignored=0\n"
                ),
                stderr="",
                return_code=0,
            )

        if mode == "dry_run":
            return HostMockOutcome(
                status="success",
                changed=False,
                skipped=False,
                stdout=(
                    f"PLAY [MOCK dry_run / check mode] *******************************************\n"
                    f"TASK [Apply {task} via {playbook}] *****************************************\n"
                    f"ok: [{host}] => {{"
                    f"\"changed\": false, "
                    f"\"msg\": \"MOCK check mode: would change {task} on {host} ({ip})\", "
                    f"\"diff\": {{\"before\": \"...\", \"after\": \"...\"}}"
                    f"}}\n"
                    f"PLAY RECAP *********************************************************************\n"
                    f"{host} : ok=1 changed=0 unreachable=0 failed=0 skipped=0 rescued=0 ignored=0\n"
                ),
                stderr="",
                return_code=0,
            )

        return HostMockOutcome(
            status="success",
            changed=True,
            skipped=False,
            stdout=(
                f"PLAY [MOCK apply] **********************************************************\n"
                f"TASK [Apply {task} via {playbook}] *****************************************\n"
                f"changed: [{host}] => {{"
                f"\"changed\": true, "
                f"\"msg\": \"MOCK applied {task} on {host} ({ip})\""
                f"}}\n"
                f"PLAY RECAP *********************************************************************\n"
                f"{host} : ok=1 changed=1 unreachable=0 failed=0 skipped=0 rescued=0 ignored=0\n"
            ),
            stderr="",
            return_code=0,
        )

    def _finalize_job(
        self,
        *,
        job: ExecutionJob,
        mode: ExecutionMode,
        outcomes: list[tuple[ExecutionJobTarget, HostMockOutcome]],
        mock_mode: bool,
        actor: str = "system",
        role: str | None = None,
        write_completion_audit: bool = True,
    ) -> JobExecutionSummary:
        now = datetime.now(UTC)
        hosts_total = len(outcomes)
        hosts_failed = sum(
            1 for _, o in outcomes if o.status in {"failed", "unreachable"}
        )
        hosts_skipped = sum(1 for _, o in outcomes if o.skipped)
        hosts_changed = sum(1 for _, o in outcomes if o.changed)
        hosts_success = hosts_total - hosts_failed

        if hosts_total == 0 or hosts_failed == 0:
            final_status = (
                JobStatus.DRY_RUN_SUCCESS.value
                if mode == "dry_run"
                else JobStatus.SUCCESS.value
            )
        elif hosts_failed == hosts_total:
            final_status = (
                JobStatus.DRY_RUN_FAILED.value
                if mode == "dry_run"
                else JobStatus.FAILED.value
            )
        else:
            final_status = (
                JobStatus.DRY_RUN_FAILED.value
                if mode == "dry_run"
                else JobStatus.PARTIALLY_FAILED.value
            )

        job.status = final_status
        job.finished_at = now
        if mode == "dry_run":
            # Keep job.status = dry_run_success so approve gate (Phase 5/6) can proceed.
            # Do NOT auto-advance to waiting_approval — human approve is required.
            job.dry_run_status = final_status

        if write_completion_audit:
            write_audit_log(
                self.db,
                actor=actor,
                action="dry_run" if mode == "dry_run" else "run",
                entity_type="execution_job",
                entity_id=job.id,
                role=role,
                details={
                    "event": "completed",
                    "mock_mode": mock_mode,
                    "mode": mode,
                    "result_type": _result_type_for_mode(mode),
                    "execution_backend": "mock" if mock_mode else "real",
                    "job_status": job.status,
                    "dry_run_status": job.dry_run_status,
                    "hosts_total": hosts_total,
                    "hosts_success": hosts_success,
                    "hosts_failed": hosts_failed,
                    "hosts_changed": hosts_changed,
                    "hosts_skipped": hosts_skipped,
                },
            )

        return JobExecutionSummary(
            job_id=job.id,
            mode=mode,
            mock_mode=mock_mode,
            job_status=job.status,
            dry_run_status=job.dry_run_status,
            hosts_total=hosts_total,
            hosts_success=hosts_success,
            hosts_failed=hosts_failed,
            hosts_changed=hosts_changed,
            hosts_skipped=hosts_skipped,
        )

    # ------------------------------------------------------------------
    # REAL path — only reachable when MOCK_MODE=false
    # ------------------------------------------------------------------

    def _execute_real(
        self,
        *,
        job: ExecutionJob,
        mode: ExecutionMode,
        actor: str = "system",
        role: str | None = None,
        catalog: RemediationCatalog | None = None,
    ) -> JobExecutionSummary:
        """Phase 8C lab-only real dry-run. Hard-blocked while MOCK_MODE=true."""
        if self.settings.mock_mode:
            raise MockModeViolationError(
                "Refusing real Ansible execution while MOCK_MODE=true. "
                "No ansible-runner, ansible-playbook, subprocess, shell, or SSH is allowed."
            )

        # Lazy import ONLY when mock_mode is False — keeps mock path free of Runner code.
        from app.services.ansible_safety import (  # noqa: PLC0415
            RealAnsibleBlockedError as SafetyBlocked,
            assert_settings_allow_real_ansible,
        )
        from app.services.real_ansible_runner import (  # noqa: PLC0415
            AnsibleRunnerMissingError,
            RealAnsibleBlockedError,
            RealAnsibleNotImplementedError,
            run_with_ansible_runner,
        )

        def _audit_blocked(reason: str, code: str = "blocked") -> None:
            write_audit_log(
                self.db,
                actor=actor,
                action="dry_run" if mode == "dry_run" else "execute",
                entity_type="execution_job",
                entity_id=job.id,
                role=role,
                details={
                    "event": (
                        "real_dry_run_blocked" if mode == "dry_run" else "blocked"
                    ),
                    "mock_mode": False,
                    "real_ansible_enabled": bool(self.settings.real_ansible_enabled),
                    "app_env": self.settings.app_env,
                    "job_environment": getattr(job, "environment", None),
                    "mode": mode,
                    "reason": reason,
                    "block_code": code,
                    "used_ai_generated_playbook": False,
                    "used_remediation_text": False,
                },
                commit=False,
            )
            self.db.commit()

        # Phase 8C: real apply/run stays blocked at the service layer too.
        if mode != "dry_run":
            reason = (
                "Phase 8C blocks real apply/run. Only ansible-runner check-mode "
                "dry-run is allowed."
            )
            _audit_blocked(reason, "apply_blocked_phase8c")
            raise AnsibleExecutionError(reason)

        # Settings + target gates BEFORE started audit / running status.
        try:
            assert_settings_allow_real_ansible(self.settings)
        except SafetyBlocked as exc:
            _audit_blocked(exc.reason, getattr(exc, "code", "blocked"))
            raise AnsibleExecutionError(exc.reason) from exc

        from app.services.ansible_safety import (  # noqa: PLC0415
            assert_job_targets_allow_real_ansible,
        )

        try:
            assert_job_targets_allow_real_ansible(
                job_environment=getattr(job, "environment", None),
                target_environments=[getattr(job, "environment", None)],
            )
        except SafetyBlocked as exc:
            _audit_blocked(exc.reason, getattr(exc, "code", "blocked"))
            raise AnsibleExecutionError(exc.reason) from exc

        if not list(getattr(job, "targets", None) or []):
            reason = (
                "Real dry-run blocked: job has no targets. Refusing unbounded "
                "inventory check-mode run."
            )
            _audit_blocked(reason, "missing_targets")
            raise AnsibleExecutionError(reason)

        catalog_entry = catalog or self._assert_catalog_allows(job.task_code)
        playbook_path = (catalog_entry.ansible_playbook_path or "").strip()

        now = datetime.now(UTC)
        job.status = JobStatus.DRY_RUN_RUNNING.value
        job.dry_run_status = JobStatus.DRY_RUN_RUNNING.value
        job.started_at = job.started_at or now
        self.db.flush()

        write_audit_log(
            self.db,
            actor=actor,
            action="dry_run",
            entity_type="execution_job",
            entity_id=job.id,
            role=role,
            details={
                "event": "real_dry_run_started",
                "mock_mode": False,
                "mode": "dry_run",
                "result_type": JobResultType.DRY_RUN.value,
                "task_code": job.task_code,
                "ansible_playbook_path": playbook_path,
                "job_environment": getattr(job, "environment", None),
                "used_ai_generated_playbook": False,
                "used_remediation_text": False,
                "execution_backend": "ansible-runner",
                "check_mode": True,
            },
            commit=False,
        )
        self.db.flush()

        # Replace previous dry_run results only.
        result_type = JobResultType.DRY_RUN.value
        existing = self.db.scalars(
            select(JobResult).where(
                JobResult.job_id == job.id,
                JobResult.result_type == result_type,
            )
        ).all()
        for row in existing:
            self.db.delete(row)
        self.db.flush()

        try:
            result = run_with_ansible_runner(
                job=job,
                mode="dry_run",
                catalog=catalog_entry,
                settings=self.settings,
            )
        except (RealAnsibleBlockedError, AnsibleRunnerMissingError, RealAnsibleNotImplementedError) as exc:
            reason = str(exc)
            code = getattr(exc, "code", "blocked")
            # Safety-gate refusals are "blocked"; runner/parse problems are "failed".
            gate_codes = {
                "mock_mode",
                "real_ansible_disabled",
                "app_env_blocked",
                "production_target",
                "target_env_blocked",
                "missing_environment",
                "missing_targets",
                "catalog_required",
                "catalog_disabled",
                "path_traversal",
                "playbook_missing",
                "inventory_missing",
                "inventory_env_blocked",
                "preflight_failed",
                "apply_blocked_phase8c",
                "empty_playbook_path",
                "absolute_playbook_path",
                "empty_inventory_path",
                "absolute_inventory_path",
            }
            event = (
                "real_dry_run_blocked"
                if isinstance(exc, RealAnsibleBlockedError) and code in gate_codes
                else "real_dry_run_failed"
            )
            job.status = JobStatus.DRY_RUN_FAILED.value
            job.dry_run_status = JobStatus.DRY_RUN_FAILED.value
            job.finished_at = datetime.now(UTC)
            write_audit_log(
                self.db,
                actor=actor,
                action="dry_run",
                entity_type="execution_job",
                entity_id=job.id,
                role=role,
                details={
                    "event": event,
                    "mock_mode": False,
                    "mode": "dry_run",
                    "reason": reason,
                    "block_code": code,
                    "used_ai_generated_playbook": False,
                    "used_remediation_text": False,
                    "execution_backend": "ansible-runner",
                },
                commit=False,
            )
            self.db.commit()
            raise AnsibleExecutionError(reason) from exc
        except Exception as exc:  # noqa: BLE001 — fail safely; never leave job running
            reason = f"Real dry-run failed unexpectedly: {exc}"
            job.status = JobStatus.DRY_RUN_FAILED.value
            job.dry_run_status = JobStatus.DRY_RUN_FAILED.value
            job.finished_at = datetime.now(UTC)
            write_audit_log(
                self.db,
                actor=actor,
                action="dry_run",
                entity_type="execution_job",
                entity_id=job.id,
                role=role,
                details={
                    "event": "real_dry_run_failed",
                    "mock_mode": False,
                    "mode": "dry_run",
                    "reason": reason,
                    "block_code": "runner_error",
                    "used_ai_generated_playbook": False,
                    "used_remediation_text": False,
                    "execution_backend": "ansible-runner",
                },
                commit=False,
            )
            self.db.commit()
            raise AnsibleExecutionError(reason) from exc

        # Honor runner-level failure even if host events look clean.
        if not result.get("ok", False):
            reason = (
                "Real dry-run failed: ansible-runner reported "
                f"status={result.get('status')!r} rc={result.get('rc')!r}."
            )
            job.status = JobStatus.DRY_RUN_FAILED.value
            job.dry_run_status = JobStatus.DRY_RUN_FAILED.value
            job.finished_at = datetime.now(UTC)
            write_audit_log(
                self.db,
                actor=actor,
                action="dry_run",
                entity_type="execution_job",
                entity_id=job.id,
                role=role,
                details={
                    "event": "real_dry_run_failed",
                    "mock_mode": False,
                    "mode": "dry_run",
                    "reason": reason,
                    "block_code": "runner_status_failed",
                    "runner_status": result.get("status"),
                    "runner_rc": result.get("rc"),
                    "used_ai_generated_playbook": False,
                    "used_remediation_text": False,
                    "execution_backend": "ansible-runner",
                },
                commit=False,
            )
            self.db.commit()
            raise AnsibleExecutionError(reason)

        # Map runner host outcomes onto job targets; persist result_type=dry_run.
        targets_by_name = {
            t.device_name: t for t in list(job.targets or []) if t.device_name
        }
        outcomes: list[tuple[ExecutionJobTarget, HostMockOutcome]] = []
        for host in result.get("hosts") or []:
            name = str(host.get("device_name") or "").strip()
            if not name:
                continue
            target = targets_by_name.get(name)
            if target is None:
                # Persist orphan host from runner events as a synthetic target row status.
                target = ExecutionJobTarget(
                    job_id=job.id,
                    device_name=name,
                    ip_address=None,
                    ansible_group=getattr(job, "ansible_group", None),
                    status=str(host.get("status") or "success"),
                )
                self.db.add(target)
                self.db.flush()
            outcome = HostMockOutcome(
                status=str(host.get("status") or "success"),
                changed=bool(host.get("changed")),
                skipped=bool(host.get("skipped")),
                stdout=str(host.get("stdout") or ""),
                stderr=str(host.get("stderr") or ""),
                return_code=int(host.get("return_code") or 0),
            )
            outcomes.append((target, outcome))
            target.status = outcome.status
            self.db.add(
                JobResult(
                    job_id=job.id,
                    result_type=result_type,
                    device_name=name,
                    status=outcome.status,
                    changed=outcome.changed,
                    skipped=outcome.skipped,
                    stdout=outcome.stdout,
                    stderr=outcome.stderr,
                    return_code=outcome.return_code,
                )
            )

        summary = self._finalize_job(
            job=job,
            mode="dry_run",
            outcomes=outcomes,
            mock_mode=False,
            actor=actor,
            role=role,
            write_completion_audit=False,
        )
        write_audit_log(
            self.db,
            actor=actor,
            action="dry_run",
            entity_type="execution_job",
            entity_id=job.id,
            role=role,
            details={
                "event": "real_dry_run_completed",
                "mock_mode": False,
                "mode": "dry_run",
                "result_type": result_type,
                "execution_backend": "ansible-runner",
                "check_mode": True,
                "cmdline": result.get("cmdline"),
                "playbook": result.get("playbook"),
                "inventory": result.get("inventory"),
                "runner_status": result.get("status"),
                "runner_rc": result.get("rc"),
                "job_status": summary.job_status,
                "hosts_total": summary.hosts_total,
                "hosts_success": summary.hosts_success,
                "hosts_failed": summary.hosts_failed,
                "used_ai_generated_playbook": False,
                "used_remediation_text": False,
            },
            commit=False,
        )
        self.db.commit()
        return summary


def summary_to_dict(summary: JobExecutionSummary) -> dict[str, Any]:
    return {
        "job_id": summary.job_id,
        "mode": summary.mode,
        "mock_mode": summary.mock_mode,
        "status": summary.job_status,
        "dry_run_status": summary.dry_run_status,
        "hosts_total": summary.hosts_total,
        "hosts_success": summary.hosts_success,
        "hosts_failed": summary.hosts_failed,
        "hosts_changed": summary.hosts_changed,
        "hosts_skipped": summary.hosts_skipped,
    }
