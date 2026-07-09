"""Phase 5 execution plan generator.

Rules:
- Only READY_FOR_PLAN records are included.
- Only task_codes present in remediation_catalog with is_enabled=true.
- Never uses AI generated_playbook.
- Never calls Ansible / MOCK execution / subprocess / SSH.
- Creates jobs with status=waiting_dry_run; does not dry-run or run.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from itertools import islice
from typing import Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.constants.job_status import JobStatus
from app.constants.plan_status import PlanStatus
from app.constants.record_status import RecordStatus
from app.models.asset import Asset
from app.models.execution_job import ExecutionJob
from app.models.execution_job_target import ExecutionJobTarget
from app.models.execution_plan import ExecutionPlan
from app.models.import_batch import ImportBatch
from app.models.raw_import_record import RawImportRecord
from app.models.remediation_catalog import RemediationCatalog
from app.services.audit import write_audit_log

# Max devices per execution job (requirement: split at 100).
MAX_TARGETS_PER_JOB = 100

EXCLUDED_FROM_PLAN: frozenset[str] = frozenset(
    {
        RecordStatus.NEEDS_REVIEW.value,
        RecordStatus.ASSET_NOT_FOUND.value,
        RecordStatus.ALREADY_COMPLIANT.value,
        RecordStatus.DUPLICATE.value,
        RecordStatus.INVALID_RECORD.value,
        RecordStatus.UNSUPPORTED_CONTROL.value,
    }
)


@dataclass(frozen=True)
class GroupKey:
    task_code: str
    environment: str | None
    criticality: str | None
    ansible_group: str | None


@dataclass
class TargetCandidate:
    device_name: str
    ip_address: str | None
    ansible_group: str | None


@dataclass
class PlanGenerationResult:
    plan: ExecutionPlan
    job_count: int = 0
    target_count: int = 0
    ready_for_plan_records: int = 0
    skipped_records: int = 0
    skipped_missing_catalog: int = 0
    skipped_disabled_catalog: int = 0
    skipped_missing_asset: int = 0
    skipped_excluded_status: int = 0


def _chunks(items: list[TargetCandidate], size: int) -> Iterable[list[TargetCandidate]]:
    it = iter(items)
    while True:
        chunk = list(islice(it, size))
        if not chunk:
            return
        yield chunk


class PlanGeneratorService:
    """Build execution_plans / jobs / targets from READY_FOR_PLAN records only."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def generate_plan(
        self,
        batch_id: int,
        *,
        created_by: str | None = None,
    ) -> PlanGenerationResult:
        batch = self.db.get(ImportBatch, batch_id)
        if batch is None:
            raise ValueError(f"Import batch {batch_id} not found")

        records = self.db.scalars(
            select(RawImportRecord)
            .where(RawImportRecord.batch_id == batch_id)
            .order_by(RawImportRecord.row_number.asc(), RawImportRecord.id.asc())
        ).all()

        enabled_catalog = self._load_enabled_catalog_codes()
        all_catalog = self._load_all_catalog_codes()
        assets_by_device = self._load_active_assets()

        plan = ExecutionPlan(
            batch_id=batch_id,
            status=PlanStatus.DRAFT.value,
            created_by=created_by or "system",
        )
        self.db.add(plan)
        self.db.flush()

        write_audit_log(
            self.db,
            actor=plan.created_by or "system",
            action="generate_plan",
            entity_type="execution_plan",
            entity_id=plan.id,
            details={
                "event": "generate_plan_started",
                "batch_id": batch_id,
                "record_count": len(records),
            },
        )

        groups: dict[GroupKey, list[TargetCandidate]] = defaultdict(list)
        seen_devices_in_group: dict[GroupKey, set[str]] = defaultdict(set)

        result = PlanGenerationResult(plan=plan)
        for record in records:
            status = (record.validation_status or "").strip()
            if status != RecordStatus.READY_FOR_PLAN.value:
                result.skipped_excluded_status += 1
                result.skipped_records += 1
                continue

            result.ready_for_plan_records += 1
            task_code = (record.task_code or "").strip()
            if not task_code or task_code not in all_catalog:
                result.skipped_missing_catalog += 1
                result.skipped_records += 1
                continue
            if task_code not in enabled_catalog:
                result.skipped_disabled_catalog += 1
                result.skipped_records += 1
                continue

            device = (record.device_name or "").strip()
            if not device:
                result.skipped_missing_asset += 1
                result.skipped_records += 1
                continue

            asset = assets_by_device.get(device.lower())
            if asset is None:
                # READY_FOR_PLAN implies asset existed at validate time; still guard.
                result.skipped_missing_asset += 1
                result.skipped_records += 1
                continue

            key = GroupKey(
                task_code=task_code,
                environment=asset.environment,
                criticality=record.criticality,
                ansible_group=asset.ansible_group,
            )
            device_key = device.lower()
            if device_key in seen_devices_in_group[key]:
                # Same device already queued for this group — skip duplicate target.
                continue
            seen_devices_in_group[key].add(device_key)
            groups[key].append(
                TargetCandidate(
                    device_name=device,
                    ip_address=asset.ip_address,
                    ansible_group=asset.ansible_group,
                )
            )

        job_count = 0
        target_count = 0
        for key in sorted(
            groups.keys(),
            key=lambda k: (
                k.task_code,
                k.environment or "",
                k.criticality or "",
                k.ansible_group or "",
            ),
        ):
            targets = groups[key]
            for chunk in _chunks(targets, MAX_TARGETS_PER_JOB):
                job = ExecutionJob(
                    plan_id=plan.id,
                    task_code=key.task_code,
                    environment=key.environment,
                    criticality=key.criticality,
                    ansible_group=key.ansible_group,
                    status=JobStatus.WAITING_DRY_RUN.value,
                )
                self.db.add(job)
                self.db.flush()
                for target in chunk:
                    self.db.add(
                        ExecutionJobTarget(
                            job_id=job.id,
                            device_name=target.device_name,
                            ip_address=target.ip_address,
                            ansible_group=target.ansible_group,
                            status="pending",
                        )
                    )
                job_count += 1
                target_count += len(chunk)

        plan.status = (
            PlanStatus.GENERATED.value if job_count > 0 else PlanStatus.EMPTY.value
        )
        result.job_count = job_count
        result.target_count = target_count

        write_audit_log(
            self.db,
            actor=plan.created_by or "system",
            action="generate_plan",
            entity_type="execution_plan",
            entity_id=plan.id,
            details={
                "event": "generate_plan_completed",
                "batch_id": batch_id,
                "status": plan.status,
                "job_count": job_count,
                "target_count": target_count,
                "ready_for_plan_records": result.ready_for_plan_records,
                "skipped_records": result.skipped_records,
                "skipped_missing_catalog": result.skipped_missing_catalog,
                "skipped_disabled_catalog": result.skipped_disabled_catalog,
                "used_ai_generated_playbook": False,
            },
        )
        self.db.commit()
        self.db.refresh(plan)
        return result

    def _load_enabled_catalog_codes(self) -> set[str]:
        rows = self.db.scalars(
            select(RemediationCatalog.task_code).where(
                RemediationCatalog.is_enabled.is_(True)
            )
        ).all()
        return {code for code in rows if code}

    def _load_all_catalog_codes(self) -> set[str]:
        rows = self.db.scalars(select(RemediationCatalog.task_code)).all()
        return {code for code in rows if code}

    def _load_active_assets(self) -> dict[str, Asset]:
        rows = self.db.scalars(select(Asset).where(Asset.is_active.is_(True))).all()
        return {(a.device_name or "").strip().lower(): a for a in rows if a.device_name}
