"""Ansible execution facade.

MOCK_MODE=true  → fake realistic per-host results; never runs ansible-runner/shell.
MOCK_MODE=false → real Ansible Runner path (not implemented yet; see Phase 6).

Safety:
- Never executes Excel Remediation text.
- Never executes AI-generated playbooks.
- Only catalog-backed playbooks will be allowed when real mode is implemented.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.config import Settings, get_settings
from app.constants.job_status import JobStatus
from app.models.execution_job import ExecutionJob
from app.models.execution_job_target import ExecutionJobTarget
from app.models.job_result import JobResult
from app.models.remediation_catalog import RemediationCatalog
from app.services.audit import write_audit_log

logger = logging.getLogger(__name__)

ExecutionMode = Literal["dry_run", "apply"]


class AnsibleExecutionError(Exception):
    """Raised when a job cannot be executed (missing job, policy, etc.)."""


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

    def dry_run_job(self, job_id: int) -> JobExecutionSummary:
        """Run check-mode (or mock equivalent) for an execution job."""
        return self._execute(job_id=job_id, mode="dry_run")

    def run_job(self, job_id: int) -> JobExecutionSummary:
        """Run apply-mode (or mock equivalent) for an approved execution job."""
        return self._execute(job_id=job_id, mode="apply")

    def _execute(self, *, job_id: int, mode: ExecutionMode) -> JobExecutionSummary:
        job = self._load_job(job_id)
        self._assert_catalog_allows(job.task_code)

        if self.settings.mock_mode:
            return self._execute_mock(job=job, mode=mode)

        return self._execute_real(job=job, mode=mode)

    def _load_job(self, job_id: int) -> ExecutionJob:
        job = self.db.scalars(
            select(ExecutionJob)
            .where(ExecutionJob.id == job_id)
            .options(selectinload(ExecutionJob.targets))
        ).first()
        if job is None:
            raise AnsibleExecutionError(f"Execution job {job_id} not found")
        return job

    def _assert_catalog_allows(self, task_code: str) -> None:
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

    # ------------------------------------------------------------------
    # MOCK path — no ansible-runner, no shell
    # ------------------------------------------------------------------

    def _execute_mock(
        self, *, job: ExecutionJob, mode: ExecutionMode
    ) -> JobExecutionSummary:
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
            actor="system",
            action="dry_run" if mode == "dry_run" else "execute",
            entity_type="execution_job",
            entity_id=job.id,
            details={
                "event": "started",
                "mock_mode": True,
                "mode": mode,
                "task_code": job.task_code,
            },
        )

        # Clear previous results for this mode re-run (simple MVP behaviour).
        existing = self.db.scalars(
            select(JobResult).where(JobResult.job_id == job.id)
        ).all()
        for row in existing:
            self.db.delete(row)
        self.db.flush()

        targets = list(job.targets)
        if not targets:
            # Still produce a deterministic empty summary.
            summary = self._finalize_job(
                job=job,
                mode=mode,
                outcomes=[],
                mock_mode=True,
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
            )
            outcomes.append((target, outcome))
            target.status = outcome.status
            self.db.add(
                JobResult(
                    job_id=job.id,
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
        )
        self.db.commit()
        logger.info(
            "MOCK %s completed for job_id=%s status=%s hosts=%s",
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
    ) -> HostMockOutcome:
        """Generate fake but realistic Ansible-like output per host.

        Deterministic pattern (no randomness) so tests are stable:
        - every 7th host → failed
        - every 5th host (not failed) → skipped / already compliant
        - otherwise success (dry-run: ok/changed preview; apply: changed)
        """
        host = target.device_name
        ip = target.ip_address or "0.0.0.0"
        task = job.task_code
        playbook = f"{task.lower()}.yml"

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
            # Check mode: report what would change without applying.
            return HostMockOutcome(
                status="success",
                changed=False,
                skipped=False,
                stdout=(
                    f"PLAY [MOCK dry_run / check mode] *******************************************\n"
                    f"TASK [Apply {task}] *******************************************************\n"
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
                f"TASK [Apply {task}] *******************************************************\n"
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
    ) -> JobExecutionSummary:
        now = datetime.now(UTC)
        hosts_total = len(outcomes)
        hosts_failed = sum(1 for _, o in outcomes if o.status == "failed")
        hosts_skipped = sum(1 for _, o in outcomes if o.skipped)
        hosts_changed = sum(1 for _, o in outcomes if o.changed)
        hosts_success = hosts_total - hosts_failed

        if hosts_total == 0:
            final_status = (
                JobStatus.DRY_RUN_SUCCESS.value
                if mode == "dry_run"
                else JobStatus.SUCCESS.value
            )
        elif hosts_failed == 0:
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
            job.dry_run_status = final_status
            # After successful dry-run, waiting_approval is the natural next state.
            if final_status == JobStatus.DRY_RUN_SUCCESS.value:
                job.status = JobStatus.WAITING_APPROVAL.value

        write_audit_log(
            self.db,
            actor="system",
            action="dry_run" if mode == "dry_run" else "execute",
            entity_type="execution_job",
            entity_id=job.id,
            details={
                "event": "completed",
                "mock_mode": mock_mode,
                "mode": mode,
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
    # REAL path — intentionally not implemented yet
    # ------------------------------------------------------------------

    def _execute_real(
        self, *, job: ExecutionJob, mode: ExecutionMode
    ) -> JobExecutionSummary:
        """Placeholder for Ansible Runner integration (Phase 6).

        Refuses to run shell/ansible-runner until explicitly implemented and
        deployed on the internal Ansible control server (see DEPLOYMENT.md).
        """
        write_audit_log(
            self.db,
            actor="system",
            action="dry_run" if mode == "dry_run" else "execute",
            entity_type="execution_job",
            entity_id=job.id,
            details={
                "event": "blocked",
                "mock_mode": False,
                "mode": mode,
                "reason": "Real Ansible Runner is not implemented yet",
            },
            commit=False,
        )
        self.db.commit()
        raise AnsibleExecutionError(
            "MOCK_MODE=false but real Ansible Runner is not implemented yet. "
            "Keep MOCK_MODE=true for local/dev, or deploy to the internal "
            "Ansible control server and complete Phase 6 before enabling real execution. "
            "See DEPLOYMENT.md."
        )


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
