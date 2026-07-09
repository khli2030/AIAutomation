"""Approved remediation catalog — only these playbooks may execute."""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class RemediationCatalog(Base):
    __tablename__ = "remediation_catalog"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_code: Mapped[str] = mapped_column(String(128), nullable=False, unique=True, index=True)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    supported_os: Mapped[str | None] = mapped_column(String(128), nullable=True)
    # Relative path under ANSIBLE_PLAYBOOKS_DIR — never user-supplied at runtime.
    ansible_playbook_path: Mapped[str] = mapped_column(String(512), nullable=False)
    risk_level: Mapped[str] = mapped_column(String(32), nullable=False, default="medium")
    requires_approval: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    requires_dry_run: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    requires_backup: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    requires_validation: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    validation_command: Mapped[str | None] = mapped_column(Text, nullable=True)
    service_reload: Mapped[str | None] = mapped_column(String(128), nullable=True)
    is_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
