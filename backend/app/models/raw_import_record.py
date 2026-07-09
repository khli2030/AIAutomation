"""Raw Excel rows preserved without data loss.

Remediation text is stored for classification only — never executed.
"""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class RawImportRecord(Base):
    __tablename__ = "raw_import_records"
    # Note: record_hash is indexed but not unique so duplicate findings are
    # preserved and marked DUPLICATE during Phase 3 validation.

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    batch_id: Mapped[int] = mapped_column(
        ForeignKey("import_batches.id", ondelete="CASCADE"), nullable=False, index=True
    )
    row_number: Mapped[int] = mapped_column(Integer, nullable=False)

    sector_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    general_department_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    department_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    application_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    device_name: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    vm_authentication: Mapped[str | None] = mapped_column(Text, nullable=True)
    vm_integration: Mapped[str | None] = mapped_column(Text, nullable=True)
    section_manager: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_scan_date_time: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_compliance_scan_date_time: Mapped[str | None] = mapped_column(Text, nullable=True)
    config_scan_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    overall_status: Mapped[str | None] = mapped_column(String(128), nullable=True)
    criticality: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    tracking_method: Mapped[str | None] = mapped_column(Text, nullable=True)
    evaluation_date: Mapped[str | None] = mapped_column(Text, nullable=True)
    posture_modified_date: Mapped[str | None] = mapped_column(Text, nullable=True)
    posture_evidence: Mapped[str | None] = mapped_column(Text, nullable=True)
    mbss_score: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_check_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    control_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    policy_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    qualys_control_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    rationale: Mapped[str | None] = mapped_column(Text, nullable=True)
    remediation: Mapped[str | None] = mapped_column(Text, nullable=True)
    expected_configuration: Mapped[str | None] = mapped_column(Text, nullable=True)

    normalized_status: Mapped[str | None] = mapped_column(String(64), nullable=True)
    task_code: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    validation_status: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    validation_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    record_hash: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    batch = relationship("ImportBatch", back_populates="records")
    ai_suggestions = relationship("AIRemediationSuggestion", back_populates="raw_record")
