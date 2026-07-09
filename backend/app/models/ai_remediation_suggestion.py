"""AI-assisted remediation suggestions — draft only, never auto-executed."""

from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class AIRemediationSuggestion(Base):
    __tablename__ = "ai_remediation_suggestions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    raw_record_id: Mapped[int] = mapped_column(
        ForeignKey("raw_import_records.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    source_check_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    qualys_control_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    control_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    rationale: Mapped[str | None] = mapped_column(Text, nullable=True)
    remediation: Mapped[str | None] = mapped_column(Text, nullable=True)
    expected_configuration: Mapped[str | None] = mapped_column(Text, nullable=True)

    suggested_task_code: Mapped[str | None] = mapped_column(String(128), nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    risk_level: Mapped[str | None] = mapped_column(String(32), nullable=True)
    target_file: Mapped[str | None] = mapped_column(String(512), nullable=True)
    setting_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    expected_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    ansible_module: Mapped[str | None] = mapped_column(String(128), nullable=True)
    # Draft playbook text only — must never be executed until converted to catalog.
    generated_playbook: Mapped[str | None] = mapped_column(Text, nullable=True)
    validation_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    safety_warnings: Mapped[str | None] = mapped_column(Text, nullable=True)
    rollback_strategy: Mapped[str | None] = mapped_column(Text, nullable=True)

    # draft | needs_review | ready_for_review | unsupported_control | approved | rejected | converted
    status: Mapped[str] = mapped_column(String(64), nullable=False, default="draft", index=True)
    reviewed_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    raw_record = relationship("RawImportRecord", back_populates="ai_suggestions")
