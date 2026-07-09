"""Phase 4 AI suggestion review + convert-to-catalog.

Safety:
- approve/reject change suggestion status only.
- convert-to-catalog requires approved suggestion.
- converted catalog entries are disabled by default.
- AI-generated playbooks are never executed.
- Never calls Ansible / subprocess / SSH.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.constants.suggestion_status import CONVERTIBLE_STATUSES, SuggestionStatus
from app.models.ai_remediation_suggestion import AIRemediationSuggestion
from app.models.remediation_catalog import RemediationCatalog
from app.services.audit import write_audit_log


class AISuggestionError(ValueError):
    """Domain error for suggestion review / conversion."""


class AISuggestionService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def list_suggestions(
        self,
        *,
        status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[AIRemediationSuggestion], int]:
        query = select(AIRemediationSuggestion)
        count_query = select(func.count()).select_from(AIRemediationSuggestion)
        if status:
            query = query.where(AIRemediationSuggestion.status == status)
            count_query = count_query.where(AIRemediationSuggestion.status == status)

        total = self.db.scalar(count_query) or 0
        rows = self.db.scalars(
            query.order_by(AIRemediationSuggestion.id.desc()).offset(offset).limit(limit)
        ).all()
        return list(rows), int(total)

    def get_suggestion(self, suggestion_id: int) -> AIRemediationSuggestion:
        suggestion = self.db.get(AIRemediationSuggestion, suggestion_id)
        if suggestion is None:
            raise AISuggestionError(f"Suggestion {suggestion_id} not found")
        return suggestion

    def approve(
        self,
        suggestion_id: int,
        *,
        reviewed_by: str | None = None,
        role: str | None = None,
    ) -> AIRemediationSuggestion:
        suggestion = self.get_suggestion(suggestion_id)
        if suggestion.status == SuggestionStatus.CONVERTED.value:
            raise AISuggestionError("Converted suggestions cannot be approved again")
        if suggestion.status == SuggestionStatus.REJECTED.value:
            raise AISuggestionError("Rejected suggestions cannot be approved")

        suggestion.status = SuggestionStatus.APPROVED.value
        suggestion.reviewed_by = reviewed_by or "admin"
        suggestion.reviewed_at = datetime.now(UTC)

        write_audit_log(
            self.db,
            actor=suggestion.reviewed_by,
            action="ai_suggestion_approve",
            entity_type="ai_remediation_suggestion",
            entity_id=suggestion.id,
            role=role,
            details={"status": suggestion.status},
        )
        self.db.commit()
        self.db.refresh(suggestion)
        return suggestion

    def reject(
        self,
        suggestion_id: int,
        *,
        reviewed_by: str | None = None,
        role: str | None = None,
    ) -> AIRemediationSuggestion:
        suggestion = self.get_suggestion(suggestion_id)
        if suggestion.status == SuggestionStatus.CONVERTED.value:
            raise AISuggestionError("Converted suggestions cannot be rejected")

        suggestion.status = SuggestionStatus.REJECTED.value
        suggestion.reviewed_by = reviewed_by or "admin"
        suggestion.reviewed_at = datetime.now(UTC)

        write_audit_log(
            self.db,
            actor=suggestion.reviewed_by,
            action="ai_suggestion_reject",
            entity_type="ai_remediation_suggestion",
            entity_id=suggestion.id,
            role=role,
            details={"status": suggestion.status},
        )
        self.db.commit()
        self.db.refresh(suggestion)
        return suggestion

    def convert_to_catalog(
        self,
        suggestion_id: int,
        *,
        reviewed_by: str | None = None,
        task_code: str | None = None,
        title: str | None = None,
        enable: bool = False,
        role: str | None = None,
    ) -> tuple[AIRemediationSuggestion, RemediationCatalog]:
        """Create a disabled catalog entry from an approved suggestion.

        AI playbook text is stored as a draft path reference only — never executed.
        Catalog entry is disabled unless an admin explicitly sets enable=True.
        """
        suggestion = self.get_suggestion(suggestion_id)
        if suggestion.status not in CONVERTIBLE_STATUSES:
            raise AISuggestionError(
                "convert-to-catalog requires an approved suggestion "
                f"(current status={suggestion.status})"
            )

        code = (task_code or suggestion.suggested_task_code or "").strip()
        if not code or code in {"NEEDS_REVIEW", "UNSUPPORTED_CONTROL"}:
            raise AISuggestionError(
                "A concrete task_code is required for catalog conversion "
                "(not NEEDS_REVIEW / UNSUPPORTED_CONTROL)"
            )

        existing = self.db.scalars(
            select(RemediationCatalog).where(RemediationCatalog.task_code == code)
        ).first()
        if existing is not None:
            raise AISuggestionError(f"Catalog task_code already exists: {code}")

        # Draft playbook path under AI drafts namespace — not an executable catalog playbook
        # until an admin enables the entry and places a reviewed playbook file.
        playbook_path = f"ai_drafts/{code.lower()}.yml"
        catalog_title = (title or suggestion.suggested_task_code or code).strip()
        # Safety default: disabled unless admin explicitly enables.
        is_enabled = bool(enable)

        catalog = RemediationCatalog(
            task_code=code,
            title=catalog_title,
            supported_os="linux",
            ansible_playbook_path=playbook_path,
            risk_level=suggestion.risk_level or "high",
            requires_approval=True,
            requires_dry_run=True,
            requires_backup=True,
            requires_validation=True,
            validation_command=None,
            service_reload=None,
            is_enabled=is_enabled,
        )
        self.db.add(catalog)
        self.db.flush()

        suggestion.status = SuggestionStatus.CONVERTED.value
        suggestion.reviewed_by = reviewed_by or suggestion.reviewed_by or "admin"
        suggestion.reviewed_at = datetime.now(UTC)

        write_audit_log(
            self.db,
            actor=suggestion.reviewed_by,
            action="ai_suggestion_convert_to_catalog",
            entity_type="ai_remediation_suggestion",
            entity_id=suggestion.id,
            role=role,
            details={
                "catalog_id": catalog.id,
                "task_code": catalog.task_code,
                "is_enabled": catalog.is_enabled,
                "ansible_playbook_path": catalog.ansible_playbook_path,
                "generated_playbook_executable": False,
            },
        )
        self.db.commit()
        self.db.refresh(suggestion)
        self.db.refresh(catalog)
        return suggestion, catalog
