"""Initial schema for compliance remediation platform.

Revision ID: 0001_initial
Revises:
Create Date: 2026-07-09
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001_initial"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "import_batches",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("original_filename", sa.String(length=512), nullable=False),
        sa.Column("stored_path", sa.String(length=1024), nullable=False),
        sa.Column("status", sa.String(length=64), nullable=False),
        sa.Column("total_rows", sa.Integer(), nullable=True),
        sa.Column("processed_rows", sa.Integer(), nullable=False),
        sa.Column("uploaded_by", sa.String(length=255), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "assets",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("device_name", sa.String(length=255), nullable=False),
        sa.Column("ip_address", sa.String(length=64), nullable=True),
        sa.Column("os_type", sa.String(length=64), nullable=True),
        sa.Column("environment", sa.String(length=64), nullable=True),
        sa.Column("ansible_group", sa.String(length=255), nullable=True),
        sa.Column("ssh_user", sa.String(length=128), nullable=True),
        sa.Column("credential_group", sa.String(length=128), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("device_name"),
    )
    op.create_index("ix_assets_device_name", "assets", ["device_name"])
    op.create_index("ix_assets_environment", "assets", ["environment"])
    op.create_index("ix_assets_ansible_group", "assets", ["ansible_group"])

    op.create_table(
        "remediation_catalog",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("task_code", sa.String(length=128), nullable=False),
        sa.Column("title", sa.String(length=512), nullable=False),
        sa.Column("supported_os", sa.String(length=128), nullable=True),
        sa.Column("ansible_playbook_path", sa.String(length=512), nullable=False),
        sa.Column("risk_level", sa.String(length=32), nullable=False),
        sa.Column("requires_approval", sa.Boolean(), nullable=False),
        sa.Column("requires_dry_run", sa.Boolean(), nullable=False),
        sa.Column("requires_backup", sa.Boolean(), nullable=False),
        sa.Column("requires_validation", sa.Boolean(), nullable=False),
        sa.Column("validation_command", sa.Text(), nullable=True),
        sa.Column("service_reload", sa.String(length=128), nullable=True),
        sa.Column("is_enabled", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("task_code"),
    )
    op.create_index("ix_remediation_catalog_task_code", "remediation_catalog", ["task_code"])

    op.create_table(
        "audit_logs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("actor", sa.String(length=255), nullable=False),
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column("entity_type", sa.String(length=64), nullable=False),
        sa.Column("entity_id", sa.String(length=64), nullable=False),
        sa.Column("details", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_audit_logs_action", "audit_logs", ["action"])
    op.create_index("ix_audit_logs_created_at", "audit_logs", ["created_at"])

    op.create_table(
        "raw_import_records",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("batch_id", sa.Integer(), nullable=False),
        sa.Column("row_number", sa.Integer(), nullable=False),
        sa.Column("sector_name", sa.Text(), nullable=True),
        sa.Column("general_department_name", sa.Text(), nullable=True),
        sa.Column("department_name", sa.Text(), nullable=True),
        sa.Column("application_name", sa.Text(), nullable=True),
        sa.Column("device_name", sa.String(length=255), nullable=True),
        sa.Column("vm_authentication", sa.Text(), nullable=True),
        sa.Column("vm_integration", sa.Text(), nullable=True),
        sa.Column("section_manager", sa.Text(), nullable=True),
        sa.Column("last_scan_date_time", sa.Text(), nullable=True),
        sa.Column("last_compliance_scan_date_time", sa.Text(), nullable=True),
        sa.Column("config_scan_id", sa.String(length=255), nullable=True),
        sa.Column("overall_status", sa.String(length=128), nullable=True),
        sa.Column("criticality", sa.String(length=64), nullable=True),
        sa.Column("tracking_method", sa.Text(), nullable=True),
        sa.Column("evaluation_date", sa.Text(), nullable=True),
        sa.Column("posture_modified_date", sa.Text(), nullable=True),
        sa.Column("posture_evidence", sa.Text(), nullable=True),
        sa.Column("mbss_score", sa.Text(), nullable=True),
        sa.Column("source_check_id", sa.String(length=255), nullable=True),
        sa.Column("control_description", sa.Text(), nullable=True),
        sa.Column("policy_id", sa.String(length=255), nullable=True),
        sa.Column("qualys_control_id", sa.String(length=255), nullable=True),
        sa.Column("rationale", sa.Text(), nullable=True),
        sa.Column("remediation", sa.Text(), nullable=True),
        sa.Column("expected_configuration", sa.Text(), nullable=True),
        sa.Column("normalized_status", sa.String(length=64), nullable=True),
        sa.Column("task_code", sa.String(length=128), nullable=True),
        sa.Column("validation_status", sa.String(length=64), nullable=True),
        sa.Column("validation_error", sa.Text(), nullable=True),
        sa.Column("record_hash", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["batch_id"], ["import_batches.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("batch_id", "record_hash", name="uq_batch_record_hash"),
    )
    op.create_index("ix_raw_import_records_batch_id", "raw_import_records", ["batch_id"])
    op.create_index("ix_raw_import_records_device_name", "raw_import_records", ["device_name"])
    op.create_index("ix_raw_import_records_criticality", "raw_import_records", ["criticality"])
    op.create_index("ix_raw_import_records_source_check_id", "raw_import_records", ["source_check_id"])
    op.create_index("ix_raw_import_records_qualys_control_id", "raw_import_records", ["qualys_control_id"])
    op.create_index("ix_raw_import_records_task_code", "raw_import_records", ["task_code"])
    op.create_index("ix_raw_import_records_validation_status", "raw_import_records", ["validation_status"])
    op.create_index("ix_raw_import_records_record_hash", "raw_import_records", ["record_hash"])

    op.create_table(
        "execution_plans",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("batch_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=64), nullable=False),
        sa.Column("created_by", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["batch_id"], ["import_batches.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_execution_plans_batch_id", "execution_plans", ["batch_id"])

    op.create_table(
        "ai_remediation_suggestions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("raw_record_id", sa.Integer(), nullable=False),
        sa.Column("source_check_id", sa.String(length=255), nullable=True),
        sa.Column("qualys_control_id", sa.String(length=255), nullable=True),
        sa.Column("control_description", sa.Text(), nullable=True),
        sa.Column("rationale", sa.Text(), nullable=True),
        sa.Column("remediation", sa.Text(), nullable=True),
        sa.Column("expected_configuration", sa.Text(), nullable=True),
        sa.Column("suggested_task_code", sa.String(length=128), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("risk_level", sa.String(length=32), nullable=True),
        sa.Column("target_file", sa.String(length=512), nullable=True),
        sa.Column("setting_name", sa.String(length=255), nullable=True),
        sa.Column("expected_value", sa.Text(), nullable=True),
        sa.Column("ansible_module", sa.String(length=128), nullable=True),
        sa.Column("generated_playbook", sa.Text(), nullable=True),
        sa.Column("validation_notes", sa.Text(), nullable=True),
        sa.Column("safety_warnings", sa.Text(), nullable=True),
        sa.Column("rollback_strategy", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=64), nullable=False),
        sa.Column("reviewed_by", sa.String(length=255), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["raw_record_id"], ["raw_import_records.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_ai_remediation_suggestions_raw_record_id",
        "ai_remediation_suggestions",
        ["raw_record_id"],
    )
    op.create_index("ix_ai_remediation_suggestions_status", "ai_remediation_suggestions", ["status"])

    op.create_table(
        "execution_jobs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("plan_id", sa.Integer(), nullable=False),
        sa.Column("task_code", sa.String(length=128), nullable=False),
        sa.Column("environment", sa.String(length=64), nullable=True),
        sa.Column("criticality", sa.String(length=64), nullable=True),
        sa.Column("ansible_group", sa.String(length=255), nullable=True),
        sa.Column("status", sa.String(length=64), nullable=False),
        sa.Column("dry_run_status", sa.String(length=64), nullable=True),
        sa.Column("approved_by", sa.String(length=255), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["plan_id"], ["execution_plans.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_execution_jobs_plan_id", "execution_jobs", ["plan_id"])
    op.create_index("ix_execution_jobs_task_code", "execution_jobs", ["task_code"])
    op.create_index("ix_execution_jobs_environment", "execution_jobs", ["environment"])
    op.create_index("ix_execution_jobs_status", "execution_jobs", ["status"])

    op.create_table(
        "execution_job_targets",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("job_id", sa.Integer(), nullable=False),
        sa.Column("device_name", sa.String(length=255), nullable=False),
        sa.Column("ip_address", sa.String(length=64), nullable=True),
        sa.Column("ansible_group", sa.String(length=255), nullable=True),
        sa.Column("status", sa.String(length=64), nullable=False),
        sa.ForeignKeyConstraint(["job_id"], ["execution_jobs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_execution_job_targets_job_id", "execution_job_targets", ["job_id"])
    op.create_index("ix_execution_job_targets_device_name", "execution_job_targets", ["device_name"])

    op.create_table(
        "job_results",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("job_id", sa.Integer(), nullable=False),
        sa.Column("device_name", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=64), nullable=False),
        sa.Column("changed", sa.Boolean(), nullable=False),
        sa.Column("skipped", sa.Boolean(), nullable=False),
        sa.Column("stdout", sa.Text(), nullable=True),
        sa.Column("stderr", sa.Text(), nullable=True),
        sa.Column("return_code", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["job_id"], ["execution_jobs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_job_results_job_id", "job_results", ["job_id"])
    op.create_index("ix_job_results_device_name", "job_results", ["device_name"])


def downgrade() -> None:
    op.drop_table("job_results")
    op.drop_table("execution_job_targets")
    op.drop_table("execution_jobs")
    op.drop_table("ai_remediation_suggestions")
    op.drop_table("execution_plans")
    op.drop_table("raw_import_records")
    op.drop_table("audit_logs")
    op.drop_table("remediation_catalog")
    op.drop_table("assets")
    op.drop_table("import_batches")
