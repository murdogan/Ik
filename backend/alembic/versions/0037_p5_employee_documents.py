"""P5 employee document policy, quarantine metadata, and upload grants.

Revision ID: 0037_p5_employee_documents
Revises: 0036_p4f_employee_lifecycle
"""

from __future__ import annotations

from collections.abc import Sequence
from uuid import UUID

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0037_p5_employee_documents"
down_revision = "0036_p4f_employee_lifecycle"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_APP_ROLE = "wealthy_falcon_app"
_PLATFORM_ROLE = "wealthy_falcon_platform"
_AUTH_ROLE = "wealthy_falcon_authentication"
_TABLES = (
    "document_types",
    "employee_documents",
    "employee_document_upload_intents",
)
_JSON = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")

_PERMISSIONS = (
    (
        "d3000000-0000-4000-8000-000000000034",
        "document_type:manage:tenant",
        "document_type",
        "manage",
        "tenant",
        "Manage tenant employee-document types.",
    ),
    (
        "d3000000-0000-4000-8000-000000000035",
        "employee_document:manage:tenant",
        "employee_document",
        "manage",
        "tenant",
        "Manage employee document metadata and private content across the tenant.",
    ),
    (
        "d3000000-0000-4000-8000-000000000036",
        "employee_document:read:own",
        "employee_document",
        "read",
        "own",
        "Read clean employee-visible documents linked to the current membership.",
    ),
)
_ROLE_GRANTS = {
    "d3000000-0000-4000-8000-000000000034": (
        "d2000000-0000-4000-8000-000000000003",
        "d2000000-0000-4000-8000-000000000004",
    ),
    "d3000000-0000-4000-8000-000000000035": (
        "d2000000-0000-4000-8000-000000000003",
        "d2000000-0000-4000-8000-000000000004",
    ),
    "d3000000-0000-4000-8000-000000000036": (
        "d2000000-0000-4000-8000-000000000003",
        "d2000000-0000-4000-8000-000000000004",
        "d2000000-0000-4000-8000-000000000008",
    ),
}


def upgrade() -> None:
    # This revision deliberately performs zero INSERT/UPDATE/DELETE operations on employees and
    # does not backfill employee records. Only new empty tables and immutable RBAC catalog rows are
    # introduced.
    op.create_table(
        "document_types",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("description", sa.String(length=500), nullable=True),
        sa.Column("required", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("employee_visible", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("sensitivity", sa.String(length=32), nullable=False),
        sa.Column("expiry_mode", sa.String(length=16), nullable=False),
        sa.Column("allowed_mime_types", _JSON, nullable=False),
        sa.Column("allowed_extensions", _JSON, nullable=False),
        sa.Column("max_size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("version", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "length(trim(code)) > 0",
            name="ck_document_types_code_not_blank",
        ),
        sa.CheckConstraint(
            "length(trim(name)) > 0",
            name="ck_document_types_name_not_blank",
        ),
        sa.CheckConstraint(
            "sensitivity in ('standard','sensitive','highly_sensitive')",
            name="ck_document_types_sensitivity",
        ),
        sa.CheckConstraint(
            "expiry_mode in ('none','optional','required')",
            name="ck_document_types_expiry_mode",
        ),
        sa.CheckConstraint(
            "max_size_bytes between 1 and 52428800",
            name="ck_document_types_max_size",
        ),
        sa.CheckConstraint("version > 0", name="ck_document_types_version_positive"),
        sa.ForeignKeyConstraint(
            ("tenant_id",),
            ("tenants.id",),
            name="fk_document_types_tenant_id_tenants",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_document_types"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_document_types_tenant_id_id"),
        sa.UniqueConstraint("tenant_id", "code", name="uq_document_types_tenant_code"),
    )
    op.create_index(
        "ix_document_types_tenant_archived",
        "document_types",
        ("tenant_id", "archived_at", "code"),
    )

    op.create_table(
        "employee_documents",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("employee_id", sa.Uuid(), nullable=False),
        sa.Column("document_type_id", sa.Uuid(), nullable=False),
        sa.Column("object_id", sa.Uuid(), nullable=False),
        sa.Column("object_key", sa.Text(), nullable=False),
        sa.Column("display_filename", sa.String(length=255), nullable=False),
        sa.Column("normalized_extension", sa.String(length=8), nullable=False),
        sa.Column("declared_content_type", sa.String(length=100), nullable=False),
        sa.Column("stored_content_type", sa.String(length=100), nullable=True),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=True),
        sa.Column("issued_on", sa.Date(), nullable=True),
        sa.Column("expires_on", sa.Date(), nullable=True),
        sa.Column("employee_visible", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("processing_state", sa.String(length=32), nullable=False),
        sa.Column("finalized_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("scanned_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("scan_result", sa.String(length=16), nullable=True),
        sa.Column("scanner_provider", sa.String(length=32), nullable=True),
        sa.Column("scanner_version", sa.String(length=64), nullable=True),
        sa.Column("scan_error_code", sa.String(length=32), nullable=True),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("version", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "processing_state in "
            "('pending_upload','pending_scan','available','infected','scan_error','rejected')",
            name="ck_employee_documents_processing_state",
        ),
        sa.CheckConstraint(
            "scan_result is null or scan_result in ('clean','infected','error')",
            name="ck_employee_documents_scan_result",
        ),
        sa.CheckConstraint(
            "normalized_extension in ('pdf','jpg','jpeg','png')",
            name="ck_employee_documents_extension",
        ),
        sa.CheckConstraint(
            "size_bytes between 1 and 52428800",
            name="ck_employee_documents_size",
        ),
        sa.CheckConstraint("version > 0", name="ck_employee_documents_version_positive"),
        sa.CheckConstraint(
            "expires_on is null or issued_on is null or expires_on >= issued_on",
            name="ck_employee_documents_date_order",
        ),
        sa.CheckConstraint(
            "(processing_state = 'pending_upload' and finalized_at is null and sha256 is null) "
            "or (processing_state = 'rejected') "
            "or (processing_state in ('pending_scan','available','infected','scan_error') "
            "and finalized_at is not null and sha256 is not null)",
            name="ck_employee_documents_finalization_state",
        ),
        sa.CheckConstraint(
            "(processing_state in ('available','infected','scan_error') and scanned_at is not null "
            "and scan_result is not null) or "
            "(processing_state not in ('available','infected','scan_error') "
            "and scanned_at is null and scan_result is null)",
            name="ck_employee_documents_scan_state",
        ),
        sa.ForeignKeyConstraint(
            ("tenant_id",),
            ("tenants.id",),
            name="fk_employee_documents_tenant_id_tenants",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ("tenant_id", "employee_id"),
            ("employees.tenant_id", "employees.id"),
            name="fk_employee_documents_tenant_employee_employees",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ("tenant_id", "document_type_id"),
            ("document_types.tenant_id", "document_types.id"),
            name="fk_employee_documents_tenant_type_document_types",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_employee_documents"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_employee_documents_tenant_id_id"),
        sa.UniqueConstraint("object_id", name="uq_employee_documents_object_id"),
        sa.UniqueConstraint("object_key", name="uq_employee_documents_object_key"),
    )
    op.create_index(
        "ix_employee_documents_tenant_employee_state",
        "employee_documents",
        ("tenant_id", "employee_id", "processing_state", "archived_at"),
    )
    op.create_index(
        "ix_employee_documents_tenant_employee_type_expiry",
        "employee_documents",
        ("tenant_id", "employee_id", "document_type_id", "expires_on"),
    )
    op.create_index(
        "ix_employee_documents_own_available",
        "employee_documents",
        ("tenant_id", "employee_id", "employee_visible", "processing_state"),
    )

    op.create_table(
        "employee_document_upload_intents",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("initiated_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("initiated_by_membership_id", sa.Uuid(), nullable=False),
        sa.Column("upload_object_key", sa.Text(), nullable=False),
        sa.Column("expected_content_type", sa.String(length=100), nullable=False),
        sa.Column("expected_size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("expected_extension", sa.String(length=8), nullable=False),
        sa.Column("expected_metadata", _JSON, nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finalized_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status in ('active','finalized','rejected','expired')",
            name="ck_employee_document_upload_intents_status",
        ),
        sa.CheckConstraint(
            "expected_size_bytes between 1 and 52428800",
            name="ck_employee_document_upload_intents_size",
        ),
        sa.CheckConstraint(
            "expected_extension in ('pdf','jpg','jpeg','png')",
            name="ck_employee_document_upload_intents_extension",
        ),
        sa.CheckConstraint(
            "(status = 'finalized' and finalized_at is not null) or "
            "(status <> 'finalized' and finalized_at is null)",
            name="ck_employee_document_upload_intents_finalized_state",
        ),
        sa.ForeignKeyConstraint(
            ("tenant_id",),
            ("tenants.id",),
            name="fk_employee_document_upload_intents_tenant_id_tenants",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ("tenant_id", "document_id"),
            ("employee_documents.tenant_id", "employee_documents.id"),
            name="fk_employee_document_upload_intents_tenant_document",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ("tenant_id", "initiated_by_user_id"),
            ("users.tenant_id", "users.id"),
            name="fk_employee_document_upload_intents_tenant_user",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ("tenant_id", "initiated_by_membership_id"),
            ("tenant_memberships.tenant_id", "tenant_memberships.id"),
            name="fk_employee_document_upload_intents_tenant_membership",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_employee_document_upload_intents"),
        sa.UniqueConstraint(
            "tenant_id",
            "id",
            name="uq_employee_document_upload_intents_tenant_id_id",
        ),
        sa.UniqueConstraint(
            "upload_object_key",
            name="uq_employee_document_upload_intents_object_key",
        ),
    )
    op.create_index(
        "ix_employee_document_upload_intents_tenant_document_status",
        "employee_document_upload_intents",
        ("tenant_id", "document_id", "status"),
    )
    op.create_index(
        "ix_employee_document_upload_intents_expiry",
        "employee_document_upload_intents",
        ("tenant_id", "status", "expires_at"),
    )

    _seed_permissions()
    if op.get_bind().dialect.name == "postgresql":
        _configure_postgresql_security()


def downgrade() -> None:
    connection = op.get_bind()
    counts = {
        table: int(connection.execute(sa.text(f"SELECT count(*) FROM {table}")).scalar_one())
        for table in _TABLES
    }
    if any(counts.values()):
        detail = ", ".join(f"{table}={count}" for table, count in counts.items())
        raise RuntimeError(f"P5 employee document data must be retained before downgrade: {detail}")

    _remove_permissions()
    if connection.dialect.name == "postgresql":
        for table in reversed(_TABLES):
            op.execute(f'REVOKE ALL PRIVILEGES ON TABLE "{table}" FROM PUBLIC')
            op.execute(f'REVOKE ALL PRIVILEGES ON TABLE "{table}" FROM {_APP_ROLE}')
            op.execute(f'REVOKE ALL PRIVILEGES ON TABLE "{table}" FROM {_PLATFORM_ROLE}')
            op.execute(f'REVOKE ALL PRIVILEGES ON TABLE "{table}" FROM {_AUTH_ROLE}')
            op.execute(f'DROP POLICY IF EXISTS tenant_isolation_app ON "{table}"')
            op.execute(f'ALTER TABLE "{table}" NO FORCE ROW LEVEL SECURITY')
            op.execute(f'ALTER TABLE "{table}" DISABLE ROW LEVEL SECURITY')

    op.drop_index(
        "ix_employee_document_upload_intents_expiry",
        table_name="employee_document_upload_intents",
    )
    op.drop_index(
        "ix_employee_document_upload_intents_tenant_document_status",
        table_name="employee_document_upload_intents",
    )
    op.drop_table("employee_document_upload_intents")
    op.drop_index("ix_employee_documents_own_available", table_name="employee_documents")
    op.drop_index(
        "ix_employee_documents_tenant_employee_type_expiry",
        table_name="employee_documents",
    )
    op.drop_index(
        "ix_employee_documents_tenant_employee_state",
        table_name="employee_documents",
    )
    op.drop_table("employee_documents")
    op.drop_index("ix_document_types_tenant_archived", table_name="document_types")
    op.drop_table("document_types")


def _seed_permissions() -> None:
    connection = op.get_bind()
    for permission_id, code, resource, action, target, description in _PERMISSIONS:
        rows = connection.execute(
            sa.text(
                "SELECT id, code, resource, action, target, target_type, description "
                "FROM permissions WHERE id = :id OR code = :code"
            ),
            {"id": UUID(permission_id), "code": code},
        ).mappings().all()
        if len(rows) > 1:
            raise RuntimeError(f"Conflicting permission identities exist for {code}")
        if rows:
            row = rows[0]
            expected = {
                "id": permission_id,
                "code": code,
                "resource": resource,
                "action": action,
                "target": target,
                "target_type": "scope",
                "description": description,
            }
            if any(str(row[key]) != str(value) for key, value in expected.items()):
                raise RuntimeError(f"Existing permission contract conflicts with {code}")
        else:
            connection.execute(
                sa.text(
                    "INSERT INTO permissions "
                    "(id, code, resource, action, target, target_type, description) "
                    "VALUES (:id, :code, :resource, :action, :target, 'scope', :description)"
                ),
                {
                    "id": UUID(permission_id),
                    "code": code,
                    "resource": resource,
                    "action": action,
                    "target": target,
                    "description": description,
                },
            )

        expected_roles = set(_ROLE_GRANTS[permission_id])
        actual_roles = {
            str(value)
            for value in connection.execute(
                sa.text(
                    "SELECT role_id FROM role_permissions WHERE permission_id = :permission_id"
                ),
                {"permission_id": UUID(permission_id)},
            ).scalars()
        }
        if not actual_roles <= expected_roles:
            raise RuntimeError(f"Unexpected role grant exists for {code}")
        for role_id in sorted(expected_roles - actual_roles):
            connection.execute(
                sa.text(
                    "INSERT INTO role_permissions (role_id, permission_id) "
                    "VALUES (:role_id, :permission_id)"
                ),
                {"role_id": UUID(role_id), "permission_id": UUID(permission_id)},
            )


def _remove_permissions() -> None:
    connection = op.get_bind()
    for permission_id, code, *_rest in reversed(_PERMISSIONS):
        actual_roles = {
            str(value)
            for value in connection.execute(
                sa.text(
                    "SELECT role_id FROM role_permissions WHERE permission_id = :permission_id"
                ),
                {"permission_id": UUID(permission_id)},
            ).scalars()
        }
        expected_roles = set(_ROLE_GRANTS[permission_id])
        if actual_roles - expected_roles:
            raise RuntimeError(f"Unexpected retained role grant prevents removal of {code}")
        connection.execute(
            sa.text("DELETE FROM role_permissions WHERE permission_id = :permission_id"),
            {"permission_id": UUID(permission_id)},
        )
        connection.execute(
            sa.text("DELETE FROM permissions WHERE id = :permission_id AND code = :code"),
            {"permission_id": UUID(permission_id), "code": code},
        )


def _configure_postgresql_security() -> None:
    update_columns = {
        "document_types": (
            "name",
            "description",
            "required",
            "employee_visible",
            "sensitivity",
            "expiry_mode",
            "allowed_mime_types",
            "allowed_extensions",
            "max_size_bytes",
            "version",
            "archived_at",
            "updated_at",
        ),
        "employee_documents": (
            "display_filename",
            "stored_content_type",
            "sha256",
            "issued_on",
            "expires_on",
            "employee_visible",
            "processing_state",
            "finalized_at",
            "scanned_at",
            "scan_result",
            "scanner_provider",
            "scanner_version",
            "scan_error_code",
            "archived_at",
            "version",
            "updated_at",
        ),
        "employee_document_upload_intents": (
            "status",
            "finalized_at",
            "updated_at",
        ),
    }
    for table in _TABLES:
        op.execute(f'REVOKE ALL PRIVILEGES ON TABLE "{table}" FROM PUBLIC')
        op.execute(f'REVOKE ALL PRIVILEGES ON TABLE "{table}" FROM {_APP_ROLE}')
        op.execute(f'REVOKE ALL PRIVILEGES ON TABLE "{table}" FROM {_PLATFORM_ROLE}')
        op.execute(f'REVOKE ALL PRIVILEGES ON TABLE "{table}" FROM {_AUTH_ROLE}')
        op.execute(f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY')
        op.execute(f'ALTER TABLE "{table}" FORCE ROW LEVEL SECURITY')
        op.execute(
            f'CREATE POLICY tenant_isolation_app ON "{table}" TO {_APP_ROLE} '
            "USING (tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid) "
            "WITH CHECK (tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid)"
        )
        op.execute(f'GRANT SELECT, INSERT ON TABLE "{table}" TO {_APP_ROLE}')
        columns = ", ".join(f'"{column}"' for column in update_columns[table])
        op.execute(f'GRANT UPDATE ({columns}) ON TABLE "{table}" TO {_APP_ROLE}')


__all__ = ["downgrade", "upgrade"]
