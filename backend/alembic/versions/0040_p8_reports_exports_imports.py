"""Phase 8 bounded reports, private exports, and employee imports.

Revision ID: 0040_p8_reports_exports_imports
Revises: 0039_p7_self_service_notifications
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from app.platform.db.rls_migration import (
    create_tenant_isolation_policy,
    disable_forced_row_security,
    drop_policy,
    enable_forced_row_security,
    grant_table_privileges,
    revoke_table_privileges,
)
from sqlalchemy.dialects import postgresql

revision: str = "0040_p8_reports_exports_imports"
down_revision: str | Sequence[str] | None = "0039_p7_self_service_notifications"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_APPLICATION_ROLE = "wealthy_falcon_app"
_TENANT_TABLES = (
    "report_export_jobs",
    "report_export_download_intents",
    "employee_imports",
    "employee_import_rows",
    "employee_import_issues",
)
_POLICIES = {
    table_name: f"{table_name}_tenant_isolation" for table_name in _TENANT_TABLES
}
_TABLE_PRIVILEGES = {
    "report_export_jobs": ("SELECT", "INSERT", "UPDATE"),
    "report_export_download_intents": ("SELECT", "INSERT"),
    "employee_imports": ("SELECT", "INSERT", "UPDATE"),
    "employee_import_rows": ("SELECT", "INSERT", "DELETE"),
    "employee_import_issues": ("SELECT", "INSERT", "DELETE"),
}


def _bump_affected_permission_versions() -> None:
    op.execute(
        sa.text(
            """
            WITH affected_users AS (
                SELECT DISTINCT user_roles.tenant_id, user_roles.user_id
                FROM user_roles
                WHERE user_roles.active
                  AND user_roles.role_id IN (
                      'd2000000-0000-4000-8000-000000000002',
                      'd2000000-0000-4000-8000-000000000003',
                      'd2000000-0000-4000-8000-000000000004',
                      'd2000000-0000-4000-8000-000000000007'
                  )
            ),
            bumped_users AS (
                UPDATE users
                SET permission_version = users.permission_version + 1,
                    updated_at = now()
                FROM affected_users
                WHERE users.tenant_id = affected_users.tenant_id
                  AND users.id = affected_users.user_id
                RETURNING users.tenant_id, users.id, users.permission_version
            )
            UPDATE tenant_memberships
            SET permission_version = bumped_users.permission_version,
                updated_at = now()
            FROM bumped_users
            WHERE tenant_memberships.tenant_id = bumped_users.tenant_id
              AND tenant_memberships.legacy_user_id = bumped_users.id
            """
        )
    )


def upgrade() -> None:
    op.create_table(
        "report_export_jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("requested_by_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("report_type", sa.String(length=32), nullable=False),
        sa.Column("format", sa.String(length=8), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("request_scope", sa.String(length=16), nullable=False),
        sa.Column("request_scope_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("fields_snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("filters_snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("generated_scope", sa.String(length=16), nullable=True),
        sa.Column("generated_scope_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("generated_fields", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("field_classifications", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("artifact_object_key", sa.String(length=500), nullable=True),
        sa.Column("artifact_sha256", sa.String(length=64), nullable=True),
        sa.Column("artifact_content_type", sa.String(length=128), nullable=True),
        sa.Column("size_bytes", sa.BigInteger(), nullable=True),
        sa.Column("row_count", sa.Integer(), nullable=True),
        sa.Column("attempt_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("failure_code", sa.String(length=64), nullable=True),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancel_requested_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("available_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "report_type in ('employees','leaves','missing_documents')",
            name="ck_report_export_jobs_report_type",
        ),
        sa.CheckConstraint("format in ('csv','xlsx')", name="ck_report_export_jobs_format"),
        sa.CheckConstraint(
            "status in ('queued','running','retry','succeeded','failed','cancelled','expired')",
            name="ck_report_export_jobs_status",
        ),
        sa.CheckConstraint(
            "failure_code is null or failure_code in "
            "('authorization_revoked','file_too_large','row_limit_exceeded',"
            "'storage_unavailable','worker_failure')",
            name="ck_report_export_jobs_failure_code",
        ),
        sa.CheckConstraint(
            "request_scope in ('tenant','team') and "
            "((request_scope = 'team' and request_scope_user_id is not null) or "
            "(request_scope = 'tenant' and request_scope_user_id is null))",
            name="ck_report_export_jobs_request_scope",
        ),
        sa.CheckConstraint(
            "request_scope_user_id is null or request_scope_user_id = requested_by_user_id",
            name="ck_report_export_jobs_request_scope_owner",
        ),
        sa.CheckConstraint(
            "generated_scope is null or generated_scope in ('tenant','team')",
            name="ck_report_export_jobs_generated_scope",
        ),
        sa.CheckConstraint(
            "generated_scope is null or "
            "((generated_scope = 'team' and generated_scope_user_id is not null) or "
            "(generated_scope = 'tenant' and generated_scope_user_id is null))",
            name="ck_report_export_jobs_generated_scope_user",
        ),
        sa.CheckConstraint(
            "generated_scope_user_id is null or generated_scope_user_id = requested_by_user_id",
            name="ck_report_export_jobs_generated_scope_owner",
        ),
        sa.CheckConstraint(
            "attempt_count >= 0 and attempt_count <= 10",
            name="ck_report_export_jobs_attempt_count",
        ),
        sa.CheckConstraint(
            "row_count is null or (row_count >= 0 and row_count <= 10000)",
            name="ck_report_export_jobs_row_count",
        ),
        sa.CheckConstraint(
            "size_bytes is null or size_bytes > 0",
            name="ck_report_export_jobs_size_bytes",
        ),
        sa.CheckConstraint(
            "artifact_sha256 is null or length(artifact_sha256) = 64",
            name="ck_report_export_jobs_sha256",
        ),
        sa.CheckConstraint(
            "jsonb_typeof(fields_snapshot) = 'array' and "
            "jsonb_typeof(filters_snapshot) = 'object' and "
            "(generated_fields is null or jsonb_typeof(generated_fields) = 'array') and "
            "(field_classifications is null or "
            "jsonb_typeof(field_classifications) = 'array')",
            name="ck_report_export_jobs_json_shapes",
        ),
        sa.CheckConstraint(
            "(status in ('succeeded','expired') and artifact_object_key is not null and "
            "artifact_sha256 is not null and artifact_content_type is not null and "
            "size_bytes is not null and row_count is not null and available_at is not null and "
            "expires_at is not null and expires_at > available_at and generated_scope is not null "
            "and generated_fields is not null and field_classifications is not null and "
            "failure_code is null) or "
            "(status not in ('succeeded','expired') and artifact_object_key is null and "
            "artifact_sha256 is null and artifact_content_type is null and size_bytes is null and "
            "row_count is null and available_at is null and expires_at is null and "
            "generated_scope is null and generated_scope_user_id is null and "
            "generated_fields is null and field_classifications is null)",
            name="ck_report_export_jobs_artifact_state",
        ),
        sa.CheckConstraint(
            "generated_scope is null or request_scope = 'tenant' or generated_scope = 'team'",
            name="ck_report_export_jobs_scope_reduction",
        ),
        sa.CheckConstraint(
            "(status in ('retry','failed') and failure_code is not null) or "
            "(status not in ('retry','failed') and failure_code is null)",
            name="ck_report_export_jobs_failure_state",
        ),
        sa.CheckConstraint(
            "(status = 'running' and lease_expires_at is not null) or "
            "(status <> 'running' and lease_expires_at is null)",
            name="ck_report_export_jobs_lease_state",
        ),
        sa.CheckConstraint(
            "(status in ('queued','retry') and next_attempt_at is not null) or "
            "(status not in ('queued','retry') and next_attempt_at is null)",
            name="ck_report_export_jobs_schedule_state",
        ),
        sa.CheckConstraint(
            "(status = 'cancelled' and cancel_requested_at is not null) or "
            "(status <> 'cancelled' and cancel_requested_at is null)",
            name="ck_report_export_jobs_cancellation_state",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name="fk_report_export_jobs_tenant",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "requested_by_user_id"],
            ["users.tenant_id", "users.id"],
            name="fk_report_export_jobs_tenant_requester",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_report_export_jobs_tenant_id_id"),
    )
    op.create_index(
        "ix_report_export_jobs_tenant_requester_created",
        "report_export_jobs",
        ["tenant_id", "requested_by_user_id", "status", "created_at", "id"],
        unique=False,
    )
    op.create_index(
        "ix_report_export_jobs_tenant_expiry",
        "report_export_jobs",
        ["tenant_id", "status", "expires_at", "id"],
        unique=False,
    )
    op.create_index(
        "ix_report_export_jobs_tenant_claim",
        "report_export_jobs",
        ["tenant_id", "status", "next_attempt_at", "created_at", "id"],
        unique=False,
    )

    op.create_table(
        "report_export_download_intents",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("export_job_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("issued_to_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "expires_at > created_at",
            name="ck_report_export_download_intents_expiry",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name="fk_report_export_download_intents_tenant",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "export_job_id"],
            ["report_export_jobs.tenant_id", "report_export_jobs.id"],
            name="fk_report_export_download_intents_job",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "issued_to_user_id"],
            ["users.tenant_id", "users.id"],
            name="fk_report_export_download_intents_user",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id", "id", name="uq_report_export_download_intents_tenant_id_id"
        ),
    )
    op.create_index(
        "ix_report_export_download_intents_job_created",
        "report_export_download_intents",
        ["tenant_id", "export_job_id", "created_at", "id"],
        unique=False,
    )

    op.create_table(
        "employee_imports",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("requested_by_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("template_version", sa.String(length=16), nullable=False),
        sa.Column("file_format", sa.String(length=8), nullable=False),
        sa.Column("content_type", sa.String(length=128), nullable=False),
        sa.Column("object_key", sa.String(length=500), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("source_sha256", sa.String(length=64), nullable=False),
        sa.Column("scan_result", sa.String(length=16), nullable=False),
        sa.Column("scanner_provider", sa.String(length=64), nullable=True),
        sa.Column("validation_fingerprint", sa.String(length=64), nullable=True),
        sa.Column("row_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("error_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("warning_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("committed_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("attempt_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("failure_code", sa.String(length=64), nullable=True),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("validated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("committed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("source_deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status in "
            "('queued','processing','retry','ready','invalid','succeeded','failed','expired')",
            name="ck_employee_imports_status",
        ),
        sa.CheckConstraint("file_format in ('csv','xlsx')", name="ck_employee_imports_format"),
        sa.CheckConstraint(
            "template_version = '1'",
            name="ck_employee_imports_template_version",
        ),
        sa.CheckConstraint(
            "scan_result in ('pending','clean','infected','error')",
            name="ck_employee_imports_scan_result",
        ),
        sa.CheckConstraint(
            "failure_code is null or failure_code in "
            "('infected_file','invalid_file','row_limit_exceeded','scanner_unavailable',"
            "'storage_unavailable','worker_failure')",
            name="ck_employee_imports_failure_code",
        ),
        sa.CheckConstraint(
            "size_bytes > 0 and size_bytes <= 10485760",
            name="ck_employee_imports_size",
        ),
        sa.CheckConstraint("length(source_sha256) = 64", name="ck_employee_imports_sha256"),
        sa.CheckConstraint(
            "row_count >= 0 and row_count <= 10000 and error_count >= 0 and "
            "warning_count >= 0 and committed_count >= 0 and committed_count <= 10000",
            name="ck_employee_imports_counts",
        ),
        sa.CheckConstraint(
            "attempt_count >= 0 and attempt_count <= 10",
            name="ck_employee_imports_attempt_count",
        ),
        sa.CheckConstraint(
            "validation_fingerprint is null or length(validation_fingerprint) = 64",
            name="ck_employee_imports_validation_fingerprint",
        ),
        sa.CheckConstraint(
            "(status = 'ready' and scan_result = 'clean' and error_count = 0 and "
            "validation_fingerprint is not null) or status <> 'ready'",
            name="ck_employee_imports_ready",
        ),
        sa.CheckConstraint(
            "(status = 'succeeded' and committed_at is not null and "
            "committed_count = row_count) or "
            "(status <> 'succeeded' and committed_at is null and committed_count = 0)",
            name="ck_employee_imports_commit",
        ),
        sa.CheckConstraint(
            "(status = 'processing' and lease_expires_at is not null) or "
            "(status <> 'processing' and lease_expires_at is null)",
            name="ck_employee_imports_lease_state",
        ),
        sa.CheckConstraint(
            "(status in ('queued','retry') and next_attempt_at is not null) or "
            "(status not in ('queued','retry') and next_attempt_at is null)",
            name="ck_employee_imports_schedule_state",
        ),
        sa.CheckConstraint(
            "(status in ('retry','failed') and failure_code is not null) or "
            "(status in ('queued','processing','ready','succeeded') and failure_code is null) or "
            "status in ('invalid','expired')",
            name="ck_employee_imports_failure_state",
        ),
        sa.CheckConstraint(
            "status not in ('ready','succeeded') or "
            "(scan_result = 'clean' and row_count > 0 and error_count = 0 and "
            "validated_at is not null and validation_fingerprint is not null)",
            name="ck_employee_imports_validated_state",
        ),
        sa.CheckConstraint(
            "expires_at > created_at and "
            "(source_deleted_at is null or source_deleted_at >= expires_at)",
            name="ck_employee_imports_expiry",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name="fk_employee_imports_tenant",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "requested_by_user_id"],
            ["users.tenant_id", "users.id"],
            name="fk_employee_imports_tenant_requester",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_employee_imports_tenant_id_id"),
    )
    op.create_index(
        "ix_employee_imports_tenant_requester_created",
        "employee_imports",
        ["tenant_id", "requested_by_user_id", "created_at", "id"],
        unique=False,
    )
    op.create_index(
        "ix_employee_imports_tenant_claim",
        "employee_imports",
        ["tenant_id", "status", "next_attempt_at", "created_at", "id"],
        unique=False,
    )
    op.create_index(
        "ix_employee_imports_tenant_source_expiry",
        "employee_imports",
        ["tenant_id", "expires_at", "id"],
        unique=False,
        postgresql_where=sa.text("source_deleted_at IS NULL"),
    )

    op.create_table(
        "employee_import_rows",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("import_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("row_number", sa.Integer(), nullable=False),
        sa.Column("employee_number", sa.String(length=64), nullable=False),
        sa.Column("employee_number_normalized", sa.String(length=64), nullable=False),
        sa.Column("first_name", sa.Text(), nullable=False),
        sa.Column("last_name", sa.Text(), nullable=False),
        sa.Column("work_email", sa.String(length=320), nullable=True),
        sa.Column("work_email_normalized", sa.String(length=320), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("employment_start_date", sa.Date(), nullable=False),
        sa.Column("employment_end_date", sa.Date(), nullable=True),
        sa.Column("legal_entity_code", sa.String(length=32), nullable=False),
        sa.Column("branch_code", sa.String(length=32), nullable=False),
        sa.Column("department_code", sa.String(length=32), nullable=False),
        sa.Column("position_code", sa.String(length=32), nullable=False),
        sa.Column("legal_entity_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("branch_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("department_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("position_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.CheckConstraint(
            "row_number >= 2 and row_number <= 10001",
            name="ck_import_rows_number",
        ),
        sa.CheckConstraint(
            "status in ('active','on_leave')",
            name="ck_import_rows_status",
        ),
        sa.CheckConstraint(
            "employment_end_date is null",
            name="ck_import_rows_end_date",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name="fk_employee_import_rows_tenant",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "import_id"],
            ["employee_imports.tenant_id", "employee_imports.id"],
            name="fk_employee_import_rows_import",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "legal_entity_id"],
            ["legal_entities.tenant_id", "legal_entities.id"],
            name="fk_employee_import_rows_legal_entity",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "branch_id"],
            ["branches.tenant_id", "branches.id"],
            name="fk_employee_import_rows_branch",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "department_id"],
            ["departments.tenant_id", "departments.id"],
            name="fk_employee_import_rows_department",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "position_id"],
            ["positions.tenant_id", "positions.id"],
            name="fk_employee_import_rows_position",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id", "import_id", "row_number", name="uq_import_rows_number"
        ),
    )
    op.create_table(
        "employee_import_issues",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("import_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("row_number", sa.Integer(), nullable=False),
        sa.Column("severity", sa.String(length=16), nullable=False),
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("field", sa.String(length=64), nullable=True),
        sa.Column("message", sa.String(length=240), nullable=False),
        sa.CheckConstraint(
            "row_number >= 1 and row_number <= 10001",
            name="ck_import_issues_row",
        ),
        sa.CheckConstraint(
            "severity in ('error','warning')",
            name="ck_import_issues_severity",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name="fk_employee_import_issues_tenant",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "import_id"],
            ["employee_imports.tenant_id", "employee_imports.id"],
            name="fk_employee_import_issues_import",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id",
            "import_id",
            "row_number",
            "code",
            "field",
            name="uq_employee_import_issues_deterministic",
        ),
    )
    op.create_index(
        "ix_employee_import_issues_import_cursor",
        "employee_import_issues",
        ["tenant_id", "import_id", "row_number", "id"],
        unique=False,
    )

    for table_name in _TENANT_TABLES:
        enable_forced_row_security(op, table_name=table_name)
        create_tenant_isolation_policy(
            op,
            table_name=table_name,
            policy_name=_POLICIES[table_name],
            role_name=_APPLICATION_ROLE,
        )
        grant_table_privileges(
            op,
            table_name=table_name,
            role_name=_APPLICATION_ROLE,
            privileges=_TABLE_PRIVILEGES[table_name],
        )

    op.execute(
        sa.text(
            """
            CREATE FUNCTION p8_guard_export_artifact_metadata()
            RETURNS trigger
            LANGUAGE plpgsql
            AS $p8_guard_export_artifact_metadata$
            BEGIN
                IF NEW.id IS DISTINCT FROM OLD.id OR
                   NEW.tenant_id IS DISTINCT FROM OLD.tenant_id OR
                   NEW.requested_by_user_id IS DISTINCT FROM OLD.requested_by_user_id OR
                   NEW.report_type IS DISTINCT FROM OLD.report_type OR
                   NEW.format IS DISTINCT FROM OLD.format OR
                   NEW.request_scope IS DISTINCT FROM OLD.request_scope OR
                   NEW.request_scope_user_id IS DISTINCT FROM OLD.request_scope_user_id OR
                   NEW.fields_snapshot IS DISTINCT FROM OLD.fields_snapshot OR
                   NEW.filters_snapshot IS DISTINCT FROM OLD.filters_snapshot OR
                   NEW.created_at IS DISTINCT FROM OLD.created_at THEN
                    RAISE EXCEPTION 'Report export request snapshot is immutable'
                        USING ERRCODE = 'integrity_constraint_violation';
                END IF;
                IF NEW.status IS DISTINCT FROM OLD.status AND NOT (
                    (OLD.status = 'queued' AND NEW.status IN ('running', 'cancelled')) OR
                    (OLD.status = 'running' AND
                     NEW.status IN ('retry', 'succeeded', 'failed', 'cancelled')) OR
                    (OLD.status = 'retry' AND NEW.status IN ('running', 'cancelled')) OR
                    (OLD.status = 'succeeded' AND NEW.status = 'expired')
                ) THEN
                    RAISE EXCEPTION 'Report export status transition is invalid'
                        USING ERRCODE = 'integrity_constraint_violation';
                END IF;
                IF (
                    OLD.artifact_object_key IS NOT NULL OR
                    OLD.artifact_sha256 IS NOT NULL OR
                    OLD.artifact_content_type IS NOT NULL OR
                    OLD.size_bytes IS NOT NULL OR
                    OLD.row_count IS NOT NULL OR
                    OLD.available_at IS NOT NULL OR
                    OLD.expires_at IS NOT NULL OR
                    OLD.generated_scope IS NOT NULL OR
                    OLD.generated_scope_user_id IS NOT NULL OR
                    OLD.generated_fields IS NOT NULL OR
                    OLD.field_classifications IS NOT NULL
                ) AND (
                    NEW.artifact_object_key IS DISTINCT FROM OLD.artifact_object_key OR
                    NEW.artifact_sha256 IS DISTINCT FROM OLD.artifact_sha256 OR
                    NEW.artifact_content_type IS DISTINCT FROM OLD.artifact_content_type OR
                    NEW.size_bytes IS DISTINCT FROM OLD.size_bytes OR
                    NEW.row_count IS DISTINCT FROM OLD.row_count OR
                    NEW.available_at IS DISTINCT FROM OLD.available_at OR
                    NEW.expires_at IS DISTINCT FROM OLD.expires_at OR
                    NEW.generated_scope IS DISTINCT FROM OLD.generated_scope OR
                    NEW.generated_scope_user_id IS DISTINCT FROM OLD.generated_scope_user_id OR
                    NEW.generated_fields IS DISTINCT FROM OLD.generated_fields OR
                    NEW.field_classifications IS DISTINCT FROM OLD.field_classifications
                ) THEN
                    RAISE EXCEPTION 'Generated report artifact metadata is immutable'
                        USING ERRCODE = 'integrity_constraint_violation';
                END IF;
                RETURN NEW;
            END
            $p8_guard_export_artifact_metadata$
            """
        )
    )
    op.execute(
        sa.text(
            """
            CREATE TRIGGER trg_p8_guard_export_artifact_metadata
            BEFORE UPDATE ON report_export_jobs
            FOR EACH ROW EXECUTE FUNCTION p8_guard_export_artifact_metadata()
            """
        )
    )
    op.execute(
        sa.text(
            """
            CREATE FUNCTION p8_guard_import_source_metadata()
            RETURNS trigger
            LANGUAGE plpgsql
            AS $p8_guard_import_source_metadata$
            BEGIN
                IF NEW.id IS DISTINCT FROM OLD.id OR
                   NEW.tenant_id IS DISTINCT FROM OLD.tenant_id OR
                   NEW.requested_by_user_id IS DISTINCT FROM OLD.requested_by_user_id OR
                   NEW.template_version IS DISTINCT FROM OLD.template_version OR
                   NEW.file_format IS DISTINCT FROM OLD.file_format OR
                   NEW.content_type IS DISTINCT FROM OLD.content_type OR
                   NEW.object_key IS DISTINCT FROM OLD.object_key OR
                   NEW.size_bytes IS DISTINCT FROM OLD.size_bytes OR
                   NEW.source_sha256 IS DISTINCT FROM OLD.source_sha256 OR
                   NEW.expires_at IS DISTINCT FROM OLD.expires_at OR
                   NEW.created_at IS DISTINCT FROM OLD.created_at THEN
                    RAISE EXCEPTION 'Employee import source metadata is immutable'
                        USING ERRCODE = 'integrity_constraint_violation';
                END IF;
                IF NEW.status IS DISTINCT FROM OLD.status AND NOT (
                    (OLD.status = 'queued' AND NEW.status IN ('processing', 'expired')) OR
                    (OLD.status = 'processing' AND
                     NEW.status IN ('retry', 'ready', 'invalid', 'failed', 'expired')) OR
                    (OLD.status = 'retry' AND NEW.status IN ('processing', 'expired')) OR
                    (OLD.status = 'ready' AND NEW.status IN ('succeeded', 'expired')) OR
                    (OLD.status IN ('invalid', 'failed') AND NEW.status = 'expired')
                ) THEN
                    RAISE EXCEPTION 'Employee import status transition is invalid'
                        USING ERRCODE = 'integrity_constraint_violation';
                END IF;
                IF OLD.status IN ('ready', 'invalid', 'succeeded', 'expired') AND (
                    NEW.scan_result IS DISTINCT FROM OLD.scan_result OR
                    NEW.scanner_provider IS DISTINCT FROM OLD.scanner_provider OR
                    NEW.validation_fingerprint IS DISTINCT FROM OLD.validation_fingerprint OR
                    NEW.row_count IS DISTINCT FROM OLD.row_count OR
                    NEW.error_count IS DISTINCT FROM OLD.error_count OR
                    NEW.warning_count IS DISTINCT FROM OLD.warning_count OR
                    NEW.validated_at IS DISTINCT FROM OLD.validated_at
                ) THEN
                    RAISE EXCEPTION 'Validated employee import snapshot is immutable'
                        USING ERRCODE = 'integrity_constraint_violation';
                END IF;
                IF OLD.status IN ('succeeded', 'expired') AND (
                    NEW.committed_count IS DISTINCT FROM OLD.committed_count OR
                    NEW.committed_at IS DISTINCT FROM OLD.committed_at
                ) THEN
                    RAISE EXCEPTION 'Employee import commit metadata is immutable'
                        USING ERRCODE = 'integrity_constraint_violation';
                END IF;
                IF OLD.source_deleted_at IS NOT NULL AND
                   NEW.source_deleted_at IS DISTINCT FROM OLD.source_deleted_at THEN
                    RAISE EXCEPTION 'Employee import source expiry is immutable'
                        USING ERRCODE = 'integrity_constraint_violation';
                END IF;
                RETURN NEW;
            END
            $p8_guard_import_source_metadata$
            """
        )
    )
    op.execute(
        sa.text(
            """
            CREATE TRIGGER trg_p8_guard_import_source_metadata
            BEFORE UPDATE ON employee_imports
            FOR EACH ROW EXECUTE FUNCTION p8_guard_import_source_metadata()
            """
        )
    )
    op.execute(
        sa.text(
            """
            CREATE FUNCTION p8_reject_immutable_detail_update()
            RETURNS trigger
            LANGUAGE plpgsql
            AS $p8_reject_immutable_detail_update$
            BEGIN
                RAISE EXCEPTION 'Validated report/import detail rows are immutable'
                    USING ERRCODE = 'integrity_constraint_violation';
            END
            $p8_reject_immutable_detail_update$
            """
        )
    )
    for table_name in (
        "report_export_download_intents",
        "employee_import_rows",
        "employee_import_issues",
    ):
        op.execute(
            sa.text(
                f"CREATE TRIGGER trg_p8_reject_{table_name}_update "
                f"BEFORE UPDATE ON {table_name} FOR EACH ROW "
                "EXECUTE FUNCTION p8_reject_immutable_detail_update()"
            )
        )
    op.execute(
        sa.text(
            """
            CREATE FUNCTION p8_guard_import_detail_insert()
            RETURNS trigger
            LANGUAGE plpgsql
            AS $p8_guard_import_detail_insert$
            BEGIN
                IF EXISTS (
                    SELECT 1
                    FROM inserted_import_details AS detail
                    JOIN employee_imports AS parent
                      ON parent.tenant_id = detail.tenant_id
                     AND parent.id = detail.import_id
                    WHERE parent.status <> 'processing'
                ) THEN
                    RAISE EXCEPTION 'Employee import details require a processing parent'
                        USING ERRCODE = 'integrity_constraint_violation';
                END IF;
                RETURN NULL;
            END
            $p8_guard_import_detail_insert$
            """
        )
    )
    for table_name in ("employee_import_rows", "employee_import_issues"):
        op.execute(
            sa.text(
                f"CREATE TRIGGER trg_p8_guard_{table_name}_insert "
                f"AFTER INSERT ON {table_name} "
                "REFERENCING NEW TABLE AS inserted_import_details FOR EACH STATEMENT "
                "EXECUTE FUNCTION p8_guard_import_detail_insert()"
            )
        )
    op.execute(
        sa.text(
            """
            CREATE FUNCTION p8_guard_import_detail_delete()
            RETURNS trigger
            LANGUAGE plpgsql
            AS $p8_guard_import_detail_delete$
            BEGIN
                IF EXISTS (
                    SELECT 1
                    FROM deleted_import_details AS detail
                    JOIN employee_imports AS parent
                      ON parent.tenant_id = detail.tenant_id
                     AND parent.id = detail.import_id
                    WHERE parent.status <> 'processing'
                      AND parent.expires_at > statement_timestamp()
                ) THEN
                    RAISE EXCEPTION 'Validated employee import detail rows are immutable'
                        USING ERRCODE = 'integrity_constraint_violation';
                END IF;
                RETURN NULL;
            END
            $p8_guard_import_detail_delete$
            """
        )
    )
    for table_name in ("employee_import_rows", "employee_import_issues"):
        op.execute(
            sa.text(
                f"CREATE TRIGGER trg_p8_guard_{table_name}_delete "
                f"AFTER DELETE ON {table_name} "
                "REFERENCING OLD TABLE AS deleted_import_details FOR EACH STATEMENT "
                "EXECUTE FUNCTION p8_guard_import_detail_delete()"
            )
        )

    op.execute(
        sa.text(
            """
            INSERT INTO permissions
                (id, code, resource, action, target, target_type,
                 description, created_at, updated_at)
            VALUES
                ('d3000000-0000-4000-8000-000000000051', 'dashboard:read:team',
                 'dashboard', 'read', 'team', 'scope',
                 'Read current direct-team dashboard metrics.', now(), now()),
                ('d3000000-0000-4000-8000-000000000052', 'report:read:tenant',
                 'report', 'read', 'tenant', 'scope',
                 'Read allowlisted HR reports across the tenant.', now(), now()),
                ('d3000000-0000-4000-8000-000000000053', 'report:read:team',
                 'report', 'read', 'team', 'scope',
                 'Read allowlisted reports for the current direct team.', now(), now()),
                ('d3000000-0000-4000-8000-000000000054', 'report:export:tenant',
                 'report', 'export', 'tenant', 'scope',
                 'Create tenant-scoped allowlisted report exports.', now(), now()),
                ('d3000000-0000-4000-8000-000000000055', 'report:export:team',
                 'report', 'export', 'team', 'scope',
                 'Create direct-team allowlisted report exports.', now(), now()),
                ('d3000000-0000-4000-8000-000000000056', 'report_field:read:work_email',
                 'report_field', 'read', 'work_email', 'field',
                 'Include work email in an otherwise authorized report projection.', now(), now()),
                ('d3000000-0000-4000-8000-000000000057', 'employee_import:manage:tenant',
                 'employee_import', 'manage', 'tenant', 'scope',
                 'Validate and commit employee imports.', now(), now())
            ON CONFLICT (id) DO UPDATE SET
                code = EXCLUDED.code,
                resource = EXCLUDED.resource,
                action = EXCLUDED.action,
                target = EXCLUDED.target,
                target_type = EXCLUDED.target_type,
                description = EXCLUDED.description,
                updated_at = now()
            """
        )
    )
    op.execute(
        sa.text(
            """
            DELETE FROM role_permissions
            WHERE role_id = 'd2000000-0000-4000-8000-000000000002'
              AND permission_id = 'd3000000-0000-4000-8000-000000000003'
            """
        )
    )
    op.execute(
        sa.text(
            """
            INSERT INTO role_permissions (role_id, permission_id)
            VALUES
                ('d2000000-0000-4000-8000-000000000003',
                 'd3000000-0000-4000-8000-000000000052'),
                ('d2000000-0000-4000-8000-000000000003',
                 'd3000000-0000-4000-8000-000000000054'),
                ('d2000000-0000-4000-8000-000000000003',
                 'd3000000-0000-4000-8000-000000000056'),
                ('d2000000-0000-4000-8000-000000000003',
                 'd3000000-0000-4000-8000-000000000057'),
                ('d2000000-0000-4000-8000-000000000004',
                 'd3000000-0000-4000-8000-000000000052'),
                ('d2000000-0000-4000-8000-000000000004',
                 'd3000000-0000-4000-8000-000000000054'),
                ('d2000000-0000-4000-8000-000000000004',
                 'd3000000-0000-4000-8000-000000000056'),
                ('d2000000-0000-4000-8000-000000000004',
                 'd3000000-0000-4000-8000-000000000057'),
                ('d2000000-0000-4000-8000-000000000007',
                 'd3000000-0000-4000-8000-000000000051'),
                ('d2000000-0000-4000-8000-000000000007',
                 'd3000000-0000-4000-8000-000000000053'),
                ('d2000000-0000-4000-8000-000000000007',
                 'd3000000-0000-4000-8000-000000000055'),
                ('d2000000-0000-4000-8000-000000000007',
                 'd3000000-0000-4000-8000-000000000056')
            ON CONFLICT (role_id, permission_id) DO NOTHING
            """
        )
    )
    _bump_affected_permission_versions()


def downgrade() -> None:
    op.execute(
        sa.text(
            """
            INSERT INTO role_permissions (role_id, permission_id)
            VALUES ('d2000000-0000-4000-8000-000000000002',
                    'd3000000-0000-4000-8000-000000000003')
            ON CONFLICT (role_id, permission_id) DO NOTHING
            """
        )
    )
    op.execute(
        sa.text(
            """
            DELETE FROM role_permissions
            WHERE permission_id IN (
                'd3000000-0000-4000-8000-000000000051',
                'd3000000-0000-4000-8000-000000000052',
                'd3000000-0000-4000-8000-000000000053',
                'd3000000-0000-4000-8000-000000000054',
                'd3000000-0000-4000-8000-000000000055',
                'd3000000-0000-4000-8000-000000000056',
                'd3000000-0000-4000-8000-000000000057'
            )
            """
        )
    )
    op.execute(
        sa.text(
            """
            DELETE FROM permissions
            WHERE id IN (
                'd3000000-0000-4000-8000-000000000051',
                'd3000000-0000-4000-8000-000000000052',
                'd3000000-0000-4000-8000-000000000053',
                'd3000000-0000-4000-8000-000000000054',
                'd3000000-0000-4000-8000-000000000055',
                'd3000000-0000-4000-8000-000000000056',
                'd3000000-0000-4000-8000-000000000057'
            )
            """
        )
    )
    _bump_affected_permission_versions()

    for table_name in ("employee_import_rows", "employee_import_issues"):
        op.execute(
            sa.text(f"DROP TRIGGER IF EXISTS trg_p8_guard_{table_name}_delete ON {table_name}")
        )
        op.execute(
            sa.text(f"DROP TRIGGER IF EXISTS trg_p8_guard_{table_name}_insert ON {table_name}")
        )
    for table_name in (
        "report_export_download_intents",
        "employee_import_rows",
        "employee_import_issues",
    ):
        op.execute(
            sa.text(
                f"DROP TRIGGER IF EXISTS trg_p8_reject_{table_name}_update "
                f"ON {table_name}"
            )
        )
    op.execute(
        sa.text(
            "DROP TRIGGER IF EXISTS trg_p8_guard_import_source_metadata ON employee_imports"
        )
    )
    op.execute(
        sa.text(
            "DROP TRIGGER IF EXISTS trg_p8_guard_export_artifact_metadata ON report_export_jobs"
        )
    )
    op.execute(sa.text("DROP FUNCTION IF EXISTS p8_reject_immutable_detail_update()"))
    op.execute(sa.text("DROP FUNCTION IF EXISTS p8_guard_import_detail_delete()"))
    op.execute(sa.text("DROP FUNCTION IF EXISTS p8_guard_import_detail_insert()"))
    op.execute(sa.text("DROP FUNCTION IF EXISTS p8_guard_import_source_metadata()"))
    op.execute(sa.text("DROP FUNCTION IF EXISTS p8_guard_export_artifact_metadata()"))

    for table_name in reversed(_TENANT_TABLES):
        revoke_table_privileges(
            op,
            table_name=table_name,
            role_name=_APPLICATION_ROLE,
            privileges=_TABLE_PRIVILEGES[table_name],
        )
        drop_policy(op, table_name=table_name, policy_name=_POLICIES[table_name])
        disable_forced_row_security(op, table_name=table_name)

    op.drop_index(
        "ix_employee_import_issues_import_cursor",
        table_name="employee_import_issues",
    )
    op.drop_table("employee_import_issues")
    op.drop_table("employee_import_rows")
    op.drop_index("ix_employee_imports_tenant_claim", table_name="employee_imports")
    op.drop_index(
        "ix_employee_imports_tenant_source_expiry",
        table_name="employee_imports",
    )
    op.drop_index("ix_employee_imports_tenant_requester_created", table_name="employee_imports")
    op.drop_table("employee_imports")
    op.drop_index(
        "ix_report_export_download_intents_job_created",
        table_name="report_export_download_intents",
    )
    op.drop_table("report_export_download_intents")
    op.drop_index("ix_report_export_jobs_tenant_claim", table_name="report_export_jobs")
    op.drop_index("ix_report_export_jobs_tenant_expiry", table_name="report_export_jobs")
    op.drop_index(
        "ix_report_export_jobs_tenant_requester_created",
        table_name="report_export_jobs",
    )
    op.drop_table("report_export_jobs")
