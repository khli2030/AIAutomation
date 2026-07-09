"""Phase 2: import batch counters + allow duplicate raw rows.

Revision ID: 0002_phase2_import
Revises: 0001_initial
Create Date: 2026-07-09
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002_phase2_import"
down_revision: str | None = "0001_initial"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "import_batches",
        sa.Column("total_records", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "import_batches",
        sa.Column("valid_records", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "import_batches",
        sa.Column("invalid_records", sa.Integer(), nullable=False, server_default="0"),
    )
    # Backfill from legacy columns when present.
    op.execute(
        """
        UPDATE import_batches
        SET total_records = COALESCE(total_rows, 0),
            valid_records = COALESCE(processed_rows, 0)
        """
    )
    # Duplicates are stored in Phase 2; Phase 3 marks DUPLICATE status.
    op.execute(
        "ALTER TABLE raw_import_records DROP CONSTRAINT IF EXISTS uq_batch_record_hash"
    )


def downgrade() -> None:
    op.create_unique_constraint(
        "uq_batch_record_hash",
        "raw_import_records",
        ["batch_id", "record_hash"],
    )
    op.drop_column("import_batches", "invalid_records")
    op.drop_column("import_batches", "valid_records")
    op.drop_column("import_batches", "total_records")
