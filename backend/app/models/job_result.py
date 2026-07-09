"""Per-host Ansible execution results."""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class JobResult(Base):
    __tablename__ = "job_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_id: Mapped[int] = mapped_column(
        ForeignKey("execution_jobs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # dry_run | run — keeps mock dry-run and apply results distinguishable.
    result_type: Mapped[str] = mapped_column(
        String(32), nullable=False, default="dry_run", index=True
    )
    device_name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    # success | failed | unreachable | skipped | changed (normalized later)
    status: Mapped[str] = mapped_column(String(64), nullable=False)
    changed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    skipped: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    stdout: Mapped[str | None] = mapped_column(Text, nullable=True)
    stderr: Mapped[str | None] = mapped_column(Text, nullable=True)
    return_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    job = relationship("ExecutionJob", back_populates="results")
