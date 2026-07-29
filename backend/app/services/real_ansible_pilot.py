"""Phase 10A real Ansible pilot preparation — safety gates + limited check-mode.

Defaults stay safe:
- MOCK_MODE=true
- REAL_ANSIBLE_ENABLED=false
- REAL_ANSIBLE_CHECK_MODE_ONLY=true
- Empty host/task-code allowlists (nothing allowed)

Never executes Excel Remediation text or AI suggestions.
Never performs real apply/run in Phase 10A.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.config import Settings, get_settings
from app.constants.job_result_type import JobResultType
from app.constants.job_status import JobStatus
from app.models.execution_job import ExecutionJob
from app.models.job_result import JobResult
from app.models.remediation_catalog import RemediationCatalog
from app.services.ansible_safety import (
    RealAnsibleBlockedError,
    ansible_runner_available,
    assert_settings_allow_real_ansible,
    resolve_inventory_path,
    resolve_playbook_path,
)
from app.services.audit import write_audit_log
from app.services.lab_ansible_config import (
    build_lab_config_preview,
    lab_config_blocks_real_execution,
    max_hosts_per_run,
    resolve_auth_mode,
)

logger = logging.getLogger(__name__)

REAL_APPLY_MODES: frozenset[str] = frozenset({"run", "apply"})
CHECK_MODES: frozenset[str] = frozenset({"dry_run", "check", "connectivity"})


@dataclass
class RealAnsibleGateResult:
    allowed: bool
    reasons: list[str] = field(default_factory=list)
    code: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "allowed": self.allowed,
            "reasons": list(self.reasons),
            "code": self.code,
        }


@dataclass
class AnsibleSafetyStatus:
    mock_mode: bool
    real_ansible_enabled: bool
    check_mode_only: bool
    allowed_hosts_count: int
    allowed_task_codes_count: int
    inventory_configured: bool
    private_key_configured: bool
    remote_user_configured: bool
    real_execution_available: bool
    reasons: list[str] = field(default_factory=list)
    allowed_hosts: list[str] = field(default_factory=list)
    allowed_task_codes: list[str] = field(default_factory=list)
    timeout_seconds: int = 120
    # Phase 10C
    pilot_mode: bool = False
    max_hosts_per_run: int = 1
    single_host_pilot_qualified: bool = False
    auth_mode: str = "explicit"
    auth_source: str = "explicit"

    def to_dict(self) -> dict[str, Any]:
        return {
            "mock_mode": self.mock_mode,
            "real_ansible_enabled": self.real_ansible_enabled,
            "check_mode_only": self.check_mode_only,
            "allowed_hosts_count": self.allowed_hosts_count,
            "allowed_task_codes_count": self.allowed_task_codes_count,
            "inventory_configured": self.inventory_configured,
            "private_key_configured": self.private_key_configured,
            "remote_user_configured": self.remote_user_configured,
            "real_execution_available": self.real_execution_available,
            "reasons": list(self.reasons),
            "allowed_hosts": list(self.allowed_hosts),
            "allowed_task_codes": list(self.allowed_task_codes),
            "timeout_seconds": self.timeout_seconds,
            "pilot_mode": self.pilot_mode,
            "max_hosts_per_run": self.max_hosts_per_run,
            "single_host_pilot_qualified": self.single_host_pilot_qualified,
            "auth_mode": self.auth_mode,
            "auth_source": self.auth_source,
        }


def can_execute_real_ansible(
    *,
    settings: Settings,
    job: Any | None,
    host: str | None,
    task_code: str | None,
    mode: str,
    catalog: RemediationCatalog | None = None,
    known_task_codes: list[str] | None = None,
    host_count: int | None = None,
) -> RealAnsibleGateResult:
    """Strict Phase 10A/10B/10C gate — all conditions must pass for allowed=True."""
    reasons: list[str] = []
    code: str | None = None
    mode_norm = (mode or "").strip().lower()

    require_task = mode_norm != "connectivity"
    lab_reasons = lab_config_blocks_real_execution(
        settings,
        known_task_codes=known_task_codes,
        host=host,
        task_code=task_code if require_task else None,
        require_task_code=require_task,
        host_count=host_count,
    )
    # Filter safe-default noise when evaluating a specific host for connectivity:
    # keep concrete blockers (empty allowlist, missing inventory when enabled, etc.).
    for r in lab_reasons:
        if r not in reasons:
            reasons.append(r)
    if settings.mock_mode:
        code = code or "mock_mode"
    if not settings.real_ansible_enabled:
        code = code or "real_ansible_disabled"
    if any("is empty" in r and "HOSTS" in r for r in lab_reasons):
        code = code or "allowed_hosts_empty"
    if any("is empty" in r and "TASK_CODES" in r for r in lab_reasons):
        code = code or "allowed_task_codes_empty"
    if any("not in REAL_ANSIBLE_ALLOWED_HOSTS" in r for r in lab_reasons):
        code = code or "host_not_allowlisted"
    if any("not in REAL_ANSIBLE_ALLOWED_TASK_CODES" in r for r in lab_reasons):
        code = code or "task_code_not_allowlisted"
    if any("INVENTORY_PATH missing" in r for r in lab_reasons):
        code = code or "inventory_missing"
    if any("REMOTE_USER missing" in r for r in lab_reasons):
        code = code or "remote_user_missing"
    if any("PRIVATE_KEY_PATH missing" in r for r in lab_reasons):
        code = code or "private_key_missing"
    if any("Unknown task_code" in r for r in lab_reasons):
        code = code or "unknown_task_code"
    if any("PILOT_MODE=false" in r for r in lab_reasons):
        code = code or "pilot_mode_disabled"
    if any("exceeds REAL_ANSIBLE_MAX_HOSTS_PER_RUN" in r for r in lab_reasons):
        code = code or "max_hosts_exceeded"

    if mode_norm in REAL_APPLY_MODES:
        if settings.real_ansible_check_mode_only:
            reasons.append(
                "REAL_ANSIBLE_CHECK_MODE_ONLY=true — real apply/run is blocked "
                "(check-mode / dry-run only in Phase 10A/10B)"
            )
            code = code or "check_mode_only"
        job_status = getattr(job, "status", None) if job is not None else None
        if job_status != JobStatus.APPROVED.value:
            reasons.append(
                "real run/apply requires job status=approved "
                f"(current={job_status!r})"
            )
            code = code or "approval_required"

    if mode_norm not in CHECK_MODES | REAL_APPLY_MODES:
        reasons.append(f"unsupported real Ansible mode={mode!r}")
        code = code or "unsupported_mode"

    # Catalog mapping for playbook modes — never Excel remediation / AI drafts.
    if mode_norm in {"dry_run", "check", "run", "apply"}:
        if catalog is None:
            reasons.append(
                "catalog playbook required — Excel Remediation text and AI "
                "suggestions are never executable"
            )
            code = code or "catalog_required"
        else:
            if not getattr(catalog, "is_enabled", False):
                reasons.append(
                    f"catalog task_code={catalog.task_code} is disabled"
                )
                code = code or "catalog_disabled"
            playbook = (getattr(catalog, "ansible_playbook_path", None) or "").strip()
            if not playbook:
                reasons.append(
                    "catalog ansible_playbook_path is empty — refusing to use "
                    "Excel Remediation or AI draft content"
                )
                code = code or "empty_playbook_path"
            else:
                try:
                    from app.services.playbook_quality import (  # noqa: PLC0415
                        assert_playbook_allowed_for_real_execution,
                    )

                    assert_playbook_allowed_for_real_execution(
                        settings,
                        catalog_relative_path=playbook,
                        task_code=getattr(catalog, "task_code", task_code),
                    )
                except RealAnsibleBlockedError as exc:
                    reasons.append(exc.reason)
                    code = code or getattr(exc, "code", "playbook_missing")

    # Explicit non-use guarantees surfaced in gate result for audits/UI.
    if reasons:
        if "used_remediation_text=false (never executed)" not in reasons:
            reasons.append("used_remediation_text=false (never executed)")
        if "used_ai_generated_playbook=false (never executed)" not in reasons:
            reasons.append("used_ai_generated_playbook=false (never executed)")

    # Deduplicate
    uniq: list[str] = []
    for r in reasons:
        if r not in uniq:
            uniq.append(r)
    reasons = uniq

    if reasons:
        return RealAnsibleGateResult(allowed=False, reasons=reasons, code=code)
    return RealAnsibleGateResult(allowed=True, reasons=[], code=None)


def build_safety_status(
    settings: Settings,
    *,
    known_task_codes: list[str] | None = None,
) -> AnsibleSafetyStatus:
    """Read-only Phase 10A/10B/10C safety status for operators."""
    preview = build_lab_config_preview(
        settings, known_task_codes=known_task_codes
    )
    runner_ok, runner_detail = ansible_runner_available()
    reasons = list(preview.validation_errors)
    for err in preview.pilot_readiness_errors:
        if err not in reasons:
            reasons.append(err)
    if settings.real_ansible_check_mode_only:
        note = "REAL_ANSIBLE_CHECK_MODE_ONLY=true — apply/run remains blocked"
        if note not in reasons:
            reasons.append(note)
    if not runner_ok:
        reasons.append(runner_detail)

    single_host_qualified = bool(preview.pilot_ready) and runner_ok
    real_execution_available = (
        bool(preview.connectivity_allowed) and runner_ok and bool(preview.pilot_mode)
    )
    if single_host_qualified:
        reasons = [
            "Single-host lab pilot qualifies "
            f"(max_hosts_per_run={preview.max_hosts_per_run}; "
            "check-mode only; apply remains blocked)"
        ]
    elif not preview.pilot_mode:
        if "REAL_ANSIBLE_PILOT_MODE=false (safe default)" not in reasons:
            reasons.append("REAL_ANSIBLE_PILOT_MODE=false (safe default)")

    return AnsibleSafetyStatus(
        mock_mode=bool(settings.mock_mode),
        real_ansible_enabled=bool(settings.real_ansible_enabled),
        check_mode_only=bool(settings.real_ansible_check_mode_only),
        allowed_hosts_count=len(preview.allowed_hosts),
        allowed_task_codes_count=len(preview.allowed_task_codes),
        inventory_configured=bool(preview.inventory_path_configured),
        private_key_configured=bool(preview.private_key_configured),
        remote_user_configured=bool(preview.remote_user_configured),
        real_execution_available=real_execution_available,
        reasons=reasons,
        allowed_hosts=list(preview.allowed_hosts),
        allowed_task_codes=list(preview.allowed_task_codes),
        timeout_seconds=int(preview.timeout_seconds),
        pilot_mode=bool(preview.pilot_mode),
        max_hosts_per_run=int(preview.max_hosts_per_run),
        single_host_pilot_qualified=single_host_qualified,
        auth_mode=preview.auth_mode,
        auth_source=preview.auth_source,
    )


def resolve_pilot_inventory_path(settings: Settings, environment: str | None) -> Path:
    """Prefer REAL_ANSIBLE_INVENTORY_PATH when set; else lab/test inventory mapping."""
    override = (settings.real_ansible_inventory_path or "").strip()
    if override:
        path = Path(override)
        if not path.is_file():
            raise RealAnsibleBlockedError(
                f"REAL_ANSIBLE_INVENTORY_PATH not found: {override!r}",
                code="inventory_missing",
            )
        return path.resolve()
    return resolve_inventory_path(settings, environment or "")


class RealAnsiblePilotError(Exception):
    """Pilot real Ansible refused or failed."""

    def __init__(self, message: str, *, code: str = "blocked") -> None:
        super().__init__(message)
        self.code = code


class RealAnsiblePilotService:
    """Connectivity check + real dry-run (check mode) for Phase 10A."""

    def __init__(self, db: Session, settings: Settings | None = None) -> None:
        self.db = db
        self.settings = settings or get_settings()

    def safety_status(self) -> AnsibleSafetyStatus:
        return build_safety_status(self.settings)

    def connectivity_check(
        self,
        hosts: list[str],
        *,
        actor: str = "system",
        role: str | None = None,
        known_task_codes: list[str] | None = None,
    ) -> dict[str, Any]:
        """Allowlisted ping only — never runs playbooks or apply."""
        requested = [h.strip() for h in hosts if h and str(h).strip()]
        write_audit_log(
            self.db,
            actor=actor,
            action="connectivity_check",
            entity_type="ansible",
            entity_id="connectivity",
            role=role,
            details={
                "event": "real_connectivity_check_started",
                "hosts": requested,
                "mock_mode": bool(self.settings.mock_mode),
                "real_ansible_enabled": bool(self.settings.real_ansible_enabled),
                "check_mode_only": bool(self.settings.real_ansible_check_mode_only),
                "playbook_executed": False,
                "changes_applied": False,
            },
            commit=False,
        )
        self.db.flush()

        if not requested:
            reasons = ["No hosts provided"]
            self._audit_connectivity(
                actor=actor,
                role=role,
                event="real_connectivity_check_failed",
                hosts=requested,
                ok=False,
                reasons=reasons,
                stdout="",
                stderr="No hosts provided",
            )
            return {
                "ok": False,
                "blocked": True,
                "hosts": [],
                "reasons": reasons,
                "stdout": "",
                "stderr": "No hosts provided",
                "mock_mode": bool(self.settings.mock_mode),
                "real_ansible_enabled": bool(self.settings.real_ansible_enabled),
            }

        max_hosts = max_hosts_per_run(self.settings)
        if len(requested) > max_hosts:
            reasons = [
                f"host count {len(requested)} exceeds "
                f"REAL_ANSIBLE_MAX_HOSTS_PER_RUN={max_hosts}"
            ]
            self._audit_connectivity(
                actor=actor,
                role=role,
                event="real_execution_blocked",
                hosts=requested,
                ok=False,
                reasons=reasons,
                stdout="",
                stderr="; ".join(reasons),
                blocked_hosts=requested,
            )
            return {
                "ok": False,
                "blocked": True,
                "hosts": requested,
                "blocked_hosts": requested,
                "reasons": reasons,
                "stdout": "",
                "stderr": "; ".join(reasons),
                "mock_mode": bool(self.settings.mock_mode),
                "real_ansible_enabled": bool(self.settings.real_ansible_enabled),
                "max_hosts_per_run": max_hosts,
            }

        # Gate each host (connectivity mode — task_code N/A; no playbooks).
        blocked_hosts: list[str] = []
        reasons: list[str] = []
        for host in requested:
            gate = can_execute_real_ansible(
                settings=self.settings,
                job=None,
                host=host,
                task_code=None,
                mode="connectivity",
                catalog=None,
                known_task_codes=known_task_codes,
                host_count=len(requested),
            )
            if not gate.allowed:
                blocked_hosts.append(host)
                reasons.extend(gate.reasons)

        if blocked_hosts or reasons:
            uniq: list[str] = []
            for r in reasons:
                if r not in uniq:
                    uniq.append(r)
            event = (
                "real_execution_blocked"
                if not self.settings.real_ansible_enabled or self.settings.mock_mode
                else "real_connectivity_check_failed"
            )
            self._audit_connectivity(
                actor=actor,
                role=role,
                event=event,
                hosts=requested,
                ok=False,
                reasons=uniq,
                stdout="",
                stderr="; ".join(uniq),
                blocked_hosts=blocked_hosts,
            )
            return {
                "ok": False,
                "blocked": True,
                "hosts": requested,
                "blocked_hosts": blocked_hosts,
                "reasons": uniq,
                "stdout": "",
                "stderr": "; ".join(uniq),
                "mock_mode": bool(self.settings.mock_mode),
                "real_ansible_enabled": bool(self.settings.real_ansible_enabled),
            }

        # Settings gates (APP_ENV etc.) before runner.
        try:
            assert_settings_allow_real_ansible(self.settings)
        except RealAnsibleBlockedError as exc:
            self._audit_connectivity(
                actor=actor,
                role=role,
                event="real_execution_blocked",
                hosts=requested,
                ok=False,
                reasons=[exc.reason],
                stdout="",
                stderr=exc.reason,
            )
            return {
                "ok": False,
                "blocked": True,
                "hosts": requested,
                "reasons": [exc.reason],
                "stdout": "",
                "stderr": exc.reason,
                "mock_mode": bool(self.settings.mock_mode),
                "real_ansible_enabled": bool(self.settings.real_ansible_enabled),
            }

        try:
            outcome = self._run_ping(requested)
        except Exception as exc:  # noqa: BLE001
            reason = f"Connectivity check failed: {exc}"
            self._audit_connectivity(
                actor=actor,
                role=role,
                event="real_connectivity_check_failed",
                hosts=requested,
                ok=False,
                reasons=[reason],
                stdout="",
                stderr=reason,
            )
            raise RealAnsiblePilotError(reason, code="connectivity_failed") from exc

        event = (
            "real_connectivity_check_completed"
            if outcome["ok"]
            else "real_connectivity_check_failed"
        )
        self._audit_connectivity(
            actor=actor,
            role=role,
            event=event,
            hosts=requested,
            ok=bool(outcome["ok"]),
            reasons=list(outcome.get("reasons") or []),
            stdout=str(outcome.get("stdout") or ""),
            stderr=str(outcome.get("stderr") or ""),
        )
        return {
            "ok": bool(outcome["ok"]),
            "blocked": False,
            "hosts": requested,
            "reasons": list(outcome.get("reasons") or []),
            "stdout": str(outcome.get("stdout") or ""),
            "stderr": str(outcome.get("stderr") or ""),
            "mock_mode": bool(self.settings.mock_mode),
            "real_ansible_enabled": bool(self.settings.real_ansible_enabled),
            "execution_backend": "ansible-runner",
            "module": "ping",
        }

    def real_dry_run(
        self,
        job_id: int,
        *,
        actor: str = "system",
        role: str | None = None,
    ) -> dict[str, Any]:
        """POST /execution-jobs/{id}/real-dry-run — check-mode only, allowlisted."""
        job = self.db.scalars(
            select(ExecutionJob)
            .where(ExecutionJob.id == job_id)
            .options(selectinload(ExecutionJob.targets))
        ).first()
        if job is None:
            raise RealAnsiblePilotError(
                f"Execution job {job_id} not found", code="not_found"
            )

        allowed_statuses = {
            JobStatus.WAITING_DRY_RUN.value,
            JobStatus.DRY_RUN_FAILED.value,
            JobStatus.DRY_RUN_SUCCESS.value,
        }
        if job.status not in allowed_statuses:
            reason = (
                "Real dry-run allowed only when status is waiting_dry_run, "
                f"dry_run_failed, or dry_run_success (current={job.status})"
            )
            self._audit_job_blocked(
                job=job, actor=actor, role=role, reason=reason, code="status_blocked"
            )
            raise RealAnsiblePilotError(reason, code="status_blocked")

        catalog = self.db.scalars(
            select(RemediationCatalog).where(
                RemediationCatalog.task_code == job.task_code
            )
        ).first()

        targets = list(job.targets or [])
        if not targets:
            reason = "Real dry-run blocked: job has no targets"
            self._audit_job_blocked(
                job=job, actor=actor, role=role, reason=reason, code="missing_targets"
            )
            raise RealAnsiblePilotError(reason, code="missing_targets")

        max_hosts = max_hosts_per_run(self.settings)
        if len(targets) > max_hosts:
            reason = (
                f"Real dry-run blocked: job has {len(targets)} targets; "
                f"REAL_ANSIBLE_MAX_HOSTS_PER_RUN={max_hosts}"
            )
            self._audit_job_blocked(
                job=job,
                actor=actor,
                role=role,
                reason=reason,
                code="max_hosts_exceeded",
            )
            raise RealAnsiblePilotError(reason, code="max_hosts_exceeded")

        # Gate every target host + task_code (check-mode / catalog only).
        reasons: list[str] = []
        code: str | None = None
        for target in targets:
            gate = can_execute_real_ansible(
                settings=self.settings,
                job=job,
                host=target.device_name,
                task_code=job.task_code,
                mode="dry_run",
                catalog=catalog,
                host_count=len(targets),
            )
            if not gate.allowed:
                reasons.extend(gate.reasons)
                code = code or gate.code

        # Phase 10C: endpoint is check-mode only; apply remains blocked.
        if not self.settings.real_ansible_check_mode_only:
            reasons.append(
                "REAL_ANSIBLE_CHECK_MODE_ONLY=false — Phase 10C requires check-mode only"
            )
            code = code or "check_mode_required"

        if reasons:
            uniq: list[str] = []
            for r in reasons:
                if r not in uniq:
                    uniq.append(r)
            reason = "; ".join(uniq)
            self._audit_job_blocked(
                job=job,
                actor=actor,
                role=role,
                reason=reason,
                code=code or "blocked",
            )
            raise RealAnsiblePilotError(reason, code=code or "blocked")

        try:
            assert_settings_allow_real_ansible(self.settings)
        except RealAnsibleBlockedError as exc:
            self._audit_job_blocked(
                job=job,
                actor=actor,
                role=role,
                reason=exc.reason,
                code=getattr(exc, "code", "blocked"),
            )
            raise RealAnsiblePilotError(
                exc.reason, code=getattr(exc, "code", "blocked")
            ) from exc

        assert catalog is not None  # gated above
        playbook_rel = (catalog.ansible_playbook_path or "").strip()

        from app.services.playbook_quality import (  # noqa: PLC0415
            assert_playbook_allowed_for_real_execution,
        )

        try:
            assert_playbook_allowed_for_real_execution(
                self.settings,
                catalog_relative_path=playbook_rel,
                task_code=job.task_code,
            )
        except RealAnsibleBlockedError as exc:
            self._audit_job_blocked(
                job=job,
                actor=actor,
                role=role,
                reason=exc.reason,
                code=getattr(exc, "code", "stub_playbook"),
            )
            raise RealAnsiblePilotError(
                exc.reason, code=getattr(exc, "code", "stub_playbook")
            ) from exc

        old_status = job.status
        now = datetime.now(UTC)
        job.status = JobStatus.DRY_RUN_RUNNING.value
        job.dry_run_status = JobStatus.DRY_RUN_RUNNING.value
        job.started_at = job.started_at or now
        self.db.flush()

        write_audit_log(
            self.db,
            actor=actor,
            action="real_dry_run",
            entity_type="execution_job",
            entity_id=job.id,
            role=role,
            details={
                "event": "real_dry_run_started",
                "plan_id": job.plan_id,
                "job_id": job.id,
                "task_code": job.task_code,
                "old_status": old_status,
                "new_status": job.status,
                "mock_mode": bool(self.settings.mock_mode),
                "real_ansible_enabled": bool(self.settings.real_ansible_enabled),
                "check_mode": True,
                "check_mode_only": bool(self.settings.real_ansible_check_mode_only),
                "result_type": JobResultType.REAL_DRY_RUN.value,
                "ansible_playbook_path": playbook_rel,
                "used_ai_generated_playbook": False,
                "used_remediation_text": False,
                "execution_backend": "ansible-runner",
            },
            commit=False,
        )
        self.db.flush()

        # Replace previous real_dry_run rows only (leave mock dry_run/run intact).
        existing = self.db.scalars(
            select(JobResult).where(
                JobResult.job_id == job.id,
                JobResult.result_type == JobResultType.REAL_DRY_RUN.value,
            )
        ).all()
        for row in existing:
            self.db.delete(row)
        self.db.flush()

        try:
            result = self._run_check_mode_playbook(
                job=job, catalog=catalog, playbook_rel=playbook_rel
            )
        except Exception as exc:  # noqa: BLE001
            reason = str(exc)
            job.status = JobStatus.DRY_RUN_FAILED.value
            job.dry_run_status = JobStatus.DRY_RUN_FAILED.value
            job.finished_at = datetime.now(UTC)
            write_audit_log(
                self.db,
                actor=actor,
                action="real_dry_run",
                entity_type="execution_job",
                entity_id=job.id,
                role=role,
                details={
                    "event": "real_dry_run_failed",
                    "plan_id": job.plan_id,
                    "job_id": job.id,
                    "task_code": job.task_code,
                    "old_status": old_status,
                    "new_status": job.status,
                    "mock_mode": bool(self.settings.mock_mode),
                    "real_ansible_enabled": True,
                    "reason": reason,
                    "used_ai_generated_playbook": False,
                    "used_remediation_text": False,
                    "check_mode": True,
                    "result_type": JobResultType.REAL_DRY_RUN.value,
                },
                commit=False,
            )
            self.db.commit()
            raise RealAnsiblePilotError(reason, code="real_dry_run_failed") from exc

        hosts_success = 0
        hosts_failed = 0
        hosts_skipped = 0
        hosts_changed = 0
        for host in result.get("hosts") or []:
            status = str(host.get("status") or "failed")
            if status in {"failed", "unreachable"}:
                hosts_failed += 1
            elif status == "skipped" or host.get("skipped"):
                hosts_skipped += 1
            else:
                hosts_success += 1
            if host.get("changed"):
                hosts_changed += 1
            self.db.add(
                JobResult(
                    job_id=job.id,
                    result_type=JobResultType.REAL_DRY_RUN.value,
                    device_name=str(host.get("device_name") or ""),
                    status=status,
                    changed=bool(host.get("changed")),
                    skipped=bool(host.get("skipped")),
                    stdout=str(host.get("stdout") or ""),
                    stderr=str(host.get("stderr") or ""),
                    return_code=int(host.get("return_code") or 0),
                )
            )

        ok = bool(result.get("ok")) and hosts_failed == 0
        job.status = (
            JobStatus.DRY_RUN_SUCCESS.value if ok else JobStatus.DRY_RUN_FAILED.value
        )
        job.dry_run_status = job.status
        job.finished_at = datetime.now(UTC)
        self.db.flush()

        write_audit_log(
            self.db,
            actor=actor,
            action="real_dry_run",
            entity_type="execution_job",
            entity_id=job.id,
            role=role,
            details={
                "event": (
                    "real_dry_run_completed" if ok else "real_dry_run_failed"
                ),
                "plan_id": job.plan_id,
                "job_id": job.id,
                "task_code": job.task_code,
                "old_status": old_status,
                "new_status": job.status,
                "mock_mode": False,
                "real_ansible_enabled": True,
                "check_mode": True,
                "cmdline": result.get("cmdline") or "--check",
                "result_type": JobResultType.REAL_DRY_RUN.value,
                "hosts_total": len(result.get("hosts") or []),
                "hosts_success": hosts_success,
                "hosts_failed": hosts_failed,
                "hosts_skipped": hosts_skipped,
                "hosts_changed": hosts_changed,
                "used_ai_generated_playbook": False,
                "used_remediation_text": False,
                "execution_backend": "ansible-runner",
            },
            commit=False,
        )
        self.db.commit()
        self.db.refresh(job)

        return {
            "job_id": job.id,
            "mode": "dry_run",
            "mock_mode": False,
            "status": job.status,
            "dry_run_status": job.dry_run_status,
            "result_type": JobResultType.REAL_DRY_RUN.value,
            "check_mode": True,
            "hosts_total": len(result.get("hosts") or []),
            "hosts_success": hosts_success,
            "hosts_failed": hosts_failed,
            "hosts_changed": hosts_changed,
            "hosts_skipped": hosts_skipped,
            "cmdline": result.get("cmdline") or "--check",
            "message": (
                "Real Ansible check-mode dry-run completed"
                if ok
                else "Real Ansible check-mode dry-run failed"
            ),
        }

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _audit_connectivity(
        self,
        *,
        actor: str,
        role: str | None,
        event: str,
        hosts: list[str],
        ok: bool,
        reasons: list[str],
        stdout: str,
        stderr: str,
        blocked_hosts: list[str] | None = None,
    ) -> None:
        write_audit_log(
            self.db,
            actor=actor,
            action="connectivity_check",
            entity_type="ansible",
            entity_id="connectivity",
            role=role,
            details={
                "event": event,
                "hosts": hosts,
                "blocked_hosts": blocked_hosts or [],
                "ok": ok,
                "reasons": reasons,
                "stdout": (stdout or "")[:4000],
                "stderr": (stderr or "")[:4000],
                "mock_mode": bool(self.settings.mock_mode),
                "real_ansible_enabled": bool(self.settings.real_ansible_enabled),
                "check_mode_only": bool(self.settings.real_ansible_check_mode_only),
            },
            commit=False,
        )
        self.db.commit()

    def _audit_job_blocked(
        self,
        *,
        job: ExecutionJob,
        actor: str,
        role: str | None,
        reason: str,
        code: str,
    ) -> None:
        write_audit_log(
            self.db,
            actor=actor,
            action="real_dry_run",
            entity_type="execution_job",
            entity_id=job.id,
            role=role,
            details={
                "event": "real_execution_blocked",
                "plan_id": job.plan_id,
                "job_id": job.id,
                "task_code": job.task_code,
                "old_status": job.status,
                "new_status": job.status,
                "mock_mode": bool(self.settings.mock_mode),
                "real_ansible_enabled": bool(self.settings.real_ansible_enabled),
                "check_mode_only": bool(self.settings.real_ansible_check_mode_only),
                "reason": reason,
                "block_code": code,
                "used_ai_generated_playbook": False,
                "used_remediation_text": False,
            },
            commit=False,
        )
        self.db.commit()

    def _run_ping(self, hosts: list[str]) -> dict[str, Any]:
        """Safe connectivity check via ansible-runner module=ping (lazy import)."""
        inventory_path = resolve_pilot_inventory_path(
            self.settings, environment="test"
        )
        private_data_dir = (
            Path(self.settings.runner_private_data_dir) / "connectivity-ping"
        )
        private_data_dir.mkdir(parents=True, exist_ok=True)

        import ansible_runner  # noqa: PLC0415

        auth_mode = resolve_auth_mode(self.settings)
        run_kwargs: dict[str, Any] = {
            "private_data_dir": str(private_data_dir),
            "host_pattern": ",".join(hosts),
            "module": "ping",
            "inventory": str(inventory_path),
            "quiet": True,
            "envvars": {
                "ANSIBLE_HOST_KEY_CHECKING": (
                    "True" if self.settings.ansible_host_key_checking else "False"
                ),
            },
        }
        # ssh_config mode: rely on inventory / SSH config / agent — never inject
        # --user or --private-key. Explicit mode injects configured identity.
        if auth_mode == "explicit":
            remote_user = (self.settings.real_ansible_remote_user or "").strip()
            if remote_user:
                run_kwargs["cmdline"] = f"--user {remote_user}"
            private_key = (self.settings.real_ansible_private_key_path or "").strip()
            if private_key:
                extra = f"--private-key {private_key}"
                run_kwargs["cmdline"] = (
                    f"{run_kwargs.get('cmdline', '')} {extra}".strip()
                )
        timeout = int(self.settings.real_ansible_timeout_seconds or 120)
        run_kwargs["timeout"] = timeout

        logger.info(
            "Phase 10C connectivity ping: hosts=%s inventory=%s auth_mode=%s "
            "(no playbook apply)",
            hosts,
            inventory_path,
            auth_mode,
        )
        runner = ansible_runner.run(**run_kwargs)
        status = str(getattr(runner, "status", "unknown") or "unknown")
        stdout = str(getattr(runner, "stdout", "") or "")
        if hasattr(stdout, "read"):
            stdout = str(stdout.read())
        # ansible_runner may expose stdout as a special object
        try:
            stdout_text = getattr(runner, "stdout", None)
            if stdout_text is not None and hasattr(stdout_text, "read"):
                stdout = stdout_text.read()
            elif stdout_text is not None:
                stdout = str(stdout_text)
        except Exception:  # noqa: BLE001
            stdout = ""
        stderr = ""
        try:
            stderr_obj = getattr(runner, "stderr", None)
            if stderr_obj is not None and hasattr(stderr_obj, "read"):
                stderr = stderr_obj.read()
            elif stderr_obj is not None:
                stderr = str(stderr_obj)
        except Exception:  # noqa: BLE001
            stderr = ""

        ok = status == "successful"
        return {
            "ok": ok,
            "status": status,
            "stdout": stdout[:8000],
            "stderr": stderr[:8000],
            "reasons": [] if ok else [f"ansible-runner status={status}"],
        }

    def _run_check_mode_playbook(
        self,
        *,
        job: ExecutionJob,
        catalog: RemediationCatalog,
        playbook_rel: str,
    ) -> dict[str, Any]:
        """Run catalog playbook with --check only (lazy ansible-runner import)."""
        playbook_path = resolve_playbook_path(self.settings, playbook_rel)
        inventory_path = resolve_pilot_inventory_path(
            self.settings, getattr(job, "environment", None)
        )
        limit_hosts = [
            t.device_name
            for t in list(job.targets or [])
            if getattr(t, "device_name", None)
        ]
        # Intersect with allowlist (defense in depth).
        allow = set(self.settings.real_ansible_allowed_hosts_list)
        limit_hosts = [h for h in limit_hosts if h in allow]
        if not limit_hosts:
            raise RealAnsiblePilotError(
                "No allowlisted hosts remain for --limit",
                code="host_not_allowlisted",
            )

        private_data_dir = (
            Path(self.settings.runner_private_data_dir)
            / f"job-{job.id}-real-dry-run"
        )
        private_data_dir.mkdir(parents=True, exist_ok=True)

        import ansible_runner  # noqa: PLC0415

        auth_mode = resolve_auth_mode(self.settings)
        cmdline_parts = ["--check"]
        # ssh_config: do not inject user/key — inventory/SSH config/agent only.
        if auth_mode == "explicit":
            remote_user = (self.settings.real_ansible_remote_user or "").strip()
            if remote_user:
                cmdline_parts.extend(["--user", remote_user])
            private_key = (self.settings.real_ansible_private_key_path or "").strip()
            if private_key:
                cmdline_parts.extend(["--private-key", private_key])
        cmdline = " ".join(cmdline_parts)

        run_kwargs: dict[str, Any] = {
            "private_data_dir": str(private_data_dir),
            "playbook": str(playbook_path),
            "inventory": str(inventory_path),
            "quiet": True,
            "cmdline": cmdline,
            "limit": ",".join(limit_hosts),
            "timeout": int(self.settings.real_ansible_timeout_seconds or 120),
            "envvars": {
                "ANSIBLE_HOST_KEY_CHECKING": (
                    "True" if self.settings.ansible_host_key_checking else "False"
                ),
            },
        }

        logger.info(
            "Phase 10C real dry-run: job_id=%s playbook=%s limit=%s cmdline=%s "
            "auth_mode=%s (check mode; catalog only; no Excel/AI)",
            job.id,
            playbook_path,
            limit_hosts,
            cmdline,
            auth_mode,
        )
        if "--check" not in cmdline:
            raise RealAnsiblePilotError(
                "Internal error: real dry-run missing --check",
                code="check_mode_required",
            )

        runner = ansible_runner.run(**run_kwargs)
        status = str(getattr(runner, "status", "unknown") or "unknown")
        rc = getattr(runner, "rc", None)
        try:
            rc_int = int(rc) if rc is not None else None
        except (TypeError, ValueError):
            rc_int = None

        # Reuse Phase 8C host event parser when available.
        from app.services.real_ansible_runner import (  # noqa: PLC0415
            _parse_host_events,
        )

        host_outcomes = _parse_host_events(runner, expected_hosts=limit_hosts)
        ok = status == "successful" and (rc_int in (0, None)) and not any(
            h.status in {"failed", "unreachable"} for h in host_outcomes
        )
        return {
            "ok": ok,
            "status": status,
            "rc": rc_int,
            "cmdline": cmdline,
            "check_mode": True,
            "playbook": str(playbook_path),
            "inventory": str(inventory_path),
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


__all__ = [
    "AnsibleSafetyStatus",
    "RealAnsibleGateResult",
    "RealAnsiblePilotError",
    "RealAnsiblePilotService",
    "build_safety_status",
    "can_execute_real_ansible",
    "resolve_pilot_inventory_path",
]
