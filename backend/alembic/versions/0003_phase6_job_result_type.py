"""Phase 6: distinguish dry_run vs run job_results.

Revision ID: 0003_phase6_job_result_type
Revises: 0002_phase2_import
Create Date: 2026-07-09
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003_phase6_job_result_type"
down_revision: str | None = "0002_phase2_import"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "job_results",
        sa.Column(
            "result_type",
            sa.String(length=32),
            nullable=False,
            server_default="dry_run",
        ),
    )
    op.create_index(
        "ix_job_results_result_type",
        "job_results",
        ["result_type"],
        unique=False,
    )
    op.create_index(
        "ix_job_results_job_id_result_type",
        "job_results",
        ["job_id", "result_type"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_job_results_job_id_result_type", table_name="job_results")
    op.drop_index("ix_job_results_result_type", table_name="job_results")
    op.drop_column("job_results", "result_type")
