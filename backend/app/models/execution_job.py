"""Execution job — one task_code / environment / criticality / ansible_group batch."""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class ExecutionJob(Base):
    __tablename__ = "execution_jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    plan_id: Mapped[int] = mapped_column(
        ForeignKey("execution_plans.id", ondelete="CASCADE"), nullable=False, index=True
    )
    task_code: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    environment: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    criticality: Mapped[str | None] = mapped_column(String(64), nullable=True)
    ansible_group: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(64), nullable=False, default="draft", index=True)
    dry_run_status: Mapped[str | None] = mapped_column(String(64), nullable=True)
    approved_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    plan = relationship("ExecutionPlan", back_populates="jobs")
    targets = relationship("ExecutionJobTarget", back_populates="job")
    results = relationship("JobResult", back_populates="job")
