"""Phase 11A catalog capability flags.

Revision ID: 0004_phase11a
Revises: 0003_phase6
Create Date: 2026-07-29
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004_phase11a"
down_revision: str | None = "0003_phase6_job_result_type"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "remediation_catalog",
        sa.Column(
            "supports_backup",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.add_column(
        "remediation_catalog",
        sa.Column(
            "supports_validation",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.add_column(
        "remediation_catalog",
        sa.Column(
            "supports_rollback",
            sa.String(length=32),
            nullable=False,
            server_default="none",
        ),
    )


def downgrade() -> None:
    op.drop_column("remediation_catalog", "supports_rollback")
    op.drop_column("remediation_catalog", "supports_validation")
    op.drop_column("remediation_catalog", "supports_backup")
