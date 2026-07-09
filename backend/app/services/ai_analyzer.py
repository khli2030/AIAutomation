"""Phase 4 AI Analyzer service.

Rules:
- Only analyzes records with validation_status = NEEDS_REVIEW.
- Never executes anything (no Ansible, subprocess, SSH).
- Never writes directly to remediation_catalog.
- Creates draft suggestions in ai_remediation_suggestions only.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.provider import AIProvider, get_ai_provider
from app.constants.record_status import RecordStatus
from app.constants.suggestion_status import SuggestionStatus
from app.models.ai_remediation_suggestion import AIRemediationSuggestion
from app.models.import_batch import ImportBatch
from app.models.raw_import_record import RawImportRecord
from app.services.audit import write_audit_log

# Changes that always require human review regardless of confidence.
ALWAYS_REVIEW_KEYWORDS: frozenset[str] = frozenset(
    {
        "ssh",
        "sshd",
        "selinux",
        "setenforce",
        "fstab",
        "mount",
        "chmod",
        "permission",
        "permissions",
        "/etc/ssh",
        "/etc/selinux",
        "/etc/fstab",
    }
)

HIGH_CONFIDENCE_THRESHOLD = 0.90


@dataclass
class AIAnalyzeSummary:
    batch_id: int
    needs_review_records: int = 0
    analyzed: int = 0
    suggestions_created: int = 0
    skipped_non_needs_review: int = 0

    def to_dict(self) -> dict[str, int]:
        return asdict(self)


def _finding_dict(record: RawImportRecord) -> dict[str, str | None]:
    return {
        "qualys_control_id": record.qualys_control_id,
        "source_check_id": record.source_check_id,
        "control_description": record.control_description,
        "rationale": record.rationale,
        "remediation": record.remediation,
        "expected_configuration": record.expected_configuration,
    }


def _text_blob(*parts: str | None) -> str:
    return " ".join(p for p in parts if p).lower()


def _requires_forced_review(
    *,
    confidence: float | None,
    risk_level: str | None,
    target_file: str | None,
    setting_name: str | None,
    remediation: str | None,
    expected_configuration: str | None,
    control_description: str | None,
    generated_playbook: str | None,
) -> tuple[bool, list[str]]:
    """Even confidence >= 0.90 requires human review; SSH/SELinux/fstab/mount/perms always."""
    warnings: list[str] = [
        "Human review required before any catalog conversion or execution.",
        "AI-generated playbooks are never executable directly.",
    ]
    forced = True  # Always require review for MVP safety.

    if confidence is not None and confidence >= HIGH_CONFIDENCE_THRESHOLD:
        warnings.append(
            f"Confidence {confidence:.2f} >= {HIGH_CONFIDENCE_THRESHOLD:.2f} "
            "still requires human review."
        )

    blob = _text_blob(
        risk_level,
        target_file,
        setting_name,
        remediation,
        expected_configuration,
        control_description,
        generated_playbook,
    )
    matched = sorted(kw for kw in ALWAYS_REVIEW_KEYWORDS if kw in blob)
    if matched:
        warnings.append(
            "Sensitive change area detected (SSH/SELinux/fstab/mount/permissions): "
            + ", ".join(matched)
        )

    if (risk_level or "").lower() in {"high", "critical"}:
        warnings.append(f"Risk level '{risk_level}' requires elevated review.")

    return forced, warnings


def map_provider_result_to_suggestion_fields(
    result: dict,
    *,
    record: RawImportRecord,
) -> dict:
    """Map provider JSON into AIRemediationSuggestion column values (draft-safe)."""
    classification = result.get("classification") or {}
    plan = result.get("remediation_plan") or {}
    safety = result.get("safety") or {}
    draft = result.get("ansible_draft") or {}

    confidence = classification.get("confidence")
    try:
        confidence_f = float(confidence) if confidence is not None else None
    except (TypeError, ValueError):
        confidence_f = None

    suggested_task_code = classification.get("task_code") or "NEEDS_REVIEW"
    risk_level = plan.get("risk_level") or "high"
    target_file = plan.get("target_file") or None
    setting_name = plan.get("setting_name") or None
    expected_value = plan.get("expected_value") or None
    ansible_module = plan.get("ansible_module") or None
    generated_playbook = draft.get("playbook_yaml") or None
    rollback_strategy = safety.get("rollback_strategy") or None

    _forced, warnings = _requires_forced_review(
        confidence=confidence_f,
        risk_level=risk_level,
        target_file=target_file,
        setting_name=setting_name,
        remediation=record.remediation,
        expected_configuration=record.expected_configuration,
        control_description=record.control_description,
        generated_playbook=generated_playbook,
    )

    provider_status = str(classification.get("status") or "NEEDS_REVIEW").upper()
    # Persist as draft/needs_review only — never approved/converted from AI.
    if provider_status == "UNSUPPORTED_CONTROL" or suggested_task_code == "UNSUPPORTED_CONTROL":
        status = SuggestionStatus.UNSUPPORTED_CONTROL.value
    else:
        # Default: draft that still needs human review.
        status = SuggestionStatus.DRAFT.value

    validation_notes = classification.get("reason") or safety.get("possible_impact") or ""
    if safety.get("validation_command"):
        validation_notes = f"{validation_notes}\nValidation: {safety['validation_command']}".strip()

    return {
        "suggested_task_code": suggested_task_code,
        "confidence": confidence_f,
        "risk_level": risk_level,
        "target_file": target_file,
        "setting_name": setting_name,
        "expected_value": expected_value,
        "ansible_module": ansible_module,
        "generated_playbook": generated_playbook,
        "validation_notes": validation_notes or None,
        "safety_warnings": "\n".join(warnings),
        "rollback_strategy": rollback_strategy,
        "status": status,
    }


class AIAnalyzerService:
    """Analyze NEEDS_REVIEW records and persist draft AI suggestions."""

    def __init__(self, db: Session, provider: AIProvider | None = None) -> None:
        self.db = db
        self.provider = provider or get_ai_provider()

    def analyze_batch_needs_review(
        self,
        batch_id: int,
        *,
        actor: str | None = None,
        role: str | None = None,
    ) -> AIAnalyzeSummary:
        batch = self.db.get(ImportBatch, batch_id)
        if batch is None:
            raise ValueError(f"Import batch {batch_id} not found")

        all_records = self.db.scalars(
            select(RawImportRecord)
            .where(RawImportRecord.batch_id == batch_id)
            .order_by(RawImportRecord.row_number.asc(), RawImportRecord.id.asc())
        ).all()

        needs_review = [
            r
            for r in all_records
            if (r.validation_status or "") == RecordStatus.NEEDS_REVIEW.value
        ]
        skipped = len(all_records) - len(needs_review)
        audit_actor = actor or "system"

        write_audit_log(
            self.db,
            actor=audit_actor,
            action="ai_analyze",
            entity_type="import_batch",
            entity_id=batch_id,
            role=role,
            details={
                "event": "ai_analyze_started",
                "needs_review_records": len(needs_review),
                "skipped_non_needs_review": skipped,
            },
        )

        created = 0
        for record in needs_review:
            suggestion = self.analyze_record(record)
            if suggestion is not None:
                created += 1

        summary = AIAnalyzeSummary(
            batch_id=batch_id,
            needs_review_records=len(needs_review),
            analyzed=len(needs_review),
            suggestions_created=created,
            skipped_non_needs_review=skipped,
        )

        write_audit_log(
            self.db,
            actor=audit_actor,
            action="ai_analyze",
            entity_type="import_batch",
            entity_id=batch_id,
            role=role,
            details={"event": "ai_analyze_completed", **summary.to_dict()},
        )
        self.db.commit()
        return summary

    def analyze_record(self, record: RawImportRecord) -> AIRemediationSuggestion | None:
        """Analyze one record if NEEDS_REVIEW; otherwise return None (ignored)."""
        if (record.validation_status or "") != RecordStatus.NEEDS_REVIEW.value:
            return None

        result = self.provider.analyze(_finding_dict(record))
        fields = map_provider_result_to_suggestion_fields(result, record=record)

        # Hard safety: AI path may only create draft/needs_review/unsupported.
        if fields["status"] not in {
            SuggestionStatus.DRAFT.value,
            SuggestionStatus.NEEDS_REVIEW.value,
            SuggestionStatus.UNSUPPORTED_CONTROL.value,
        }:
            fields["status"] = SuggestionStatus.DRAFT.value

        suggestion = AIRemediationSuggestion(
            raw_record_id=record.id,
            source_check_id=record.source_check_id,
            qualys_control_id=record.qualys_control_id,
            control_description=record.control_description,
            rationale=record.rationale,
            remediation=record.remediation,
            expected_configuration=record.expected_configuration,
            **fields,
        )
        self.db.add(suggestion)
        self.db.flush()
        return suggestion
