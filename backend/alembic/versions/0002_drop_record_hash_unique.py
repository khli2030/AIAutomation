"""Drop unique constraint on (batch_id, record_hash).

Duplicates must be stored and marked DUPLICATE in Phase 3, not rejected at insert.

Revision ID: 0002_drop_record_hash_uq
Revises: 0001_initial
Create Date: 2026-07-09
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0002_drop_record_hash_uq"
down_revision: str | None = "0001_initial"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # IF EXISTS keeps this safe when 0001 was created without the unique constraint.
    op.execute(
        "ALTER TABLE raw_import_records DROP CONSTRAINT IF EXISTS uq_batch_record_hash"
    )


def downgrade() -> None:
    op.create_unique_constraint(
        "uq_batch_record_hash",
        "raw_import_records",
        ["batch_id", "record_hash"],
    )
