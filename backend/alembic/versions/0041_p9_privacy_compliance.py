"""Phase 9 privacy notices, optional consent, and retention metadata.

Revision ID: 0041_p9_privacy_compliance
Revises: 0040_p8_reports_exports_imports
"""

from __future__ import annotations

from uuid import UUID

import sqlalchemy as sa
from alembic import op
from app.platform.db.rls_migration import (
    create_tenant_isolation_policy,
    create_unrestricted_insert_policy,
    disable_forced_row_security,
    drop_policy,
    enable_forced_row_security,
    grant_table_privileges,
    revoke_all_table_privileges,
)
from sqlalchemy.dialects import postgresql

revision: str = "0041_p9_privacy_compliance"
down_revision: str | None = "0040_p8_reports_exports_imports"
branch_labels: str | tuple[str, ...] | None = None
depends_on: str | tuple[str, ...] | None = None

_TENANT_ROLE = "wealthy_falcon_app"
_PLATFORM_ROLE = "wealthy_falcon_platform"

_TABLES = (
    "privacy_notices",
    "privacy_notice_acknowledgements",
    "privacy_consent_purposes",
    "privacy_consent_states",
    "privacy_consent_events",
    "retention_policies",
)

_TENANT_PRIVILEGES: dict[str, tuple[str, ...]] = {
    "privacy_notices": ("SELECT", "INSERT", "UPDATE"),
    "privacy_notice_acknowledgements": ("SELECT", "INSERT"),
    "privacy_consent_purposes": ("SELECT",),
    "privacy_consent_states": ("SELECT", "INSERT", "UPDATE"),
    "privacy_consent_events": ("SELECT", "INSERT"),
    "retention_policies": ("SELECT", "INSERT", "UPDATE"),
}

_ROLE_IDS = {
    "tenant_admin": UUID("d2000000-0000-4000-8000-000000000002"),
    "hr_director": UUID("d2000000-0000-4000-8000-000000000003"),
    "hr_specialist": UUID("d2000000-0000-4000-8000-000000000004"),
    "it_admin": UUID("d2000000-0000-4000-8000-000000000005"),
    "auditor": UUID("d2000000-0000-4000-8000-000000000006"),
    "manager": UUID("d2000000-0000-4000-8000-000000000007"),
    "employee": UUID("d2000000-0000-4000-8000-000000000008"),
}

_PERMISSIONS = (
    (
        UUID("d3000000-0000-4000-8000-000000000058"),
        "privacy_notice:read:own",
        "privacy_notice",
        "read",
        "own",
        "Read the current employee privacy notice.",
    ),
    (
        UUID("d3000000-0000-4000-8000-000000000059"),
        "privacy_notice:acknowledge:own",
        "privacy_notice",
        "acknowledge",
        "own",
        "Acknowledge the current employee privacy notice.",
    ),
    (
        UUID("d3000000-0000-4000-8000-000000000060"),
        "privacy_consent:manage:own",
        "privacy_consent",
        "manage",
        "own",
        "Read and change the current employee's optional consent state.",
    ),
    (
        UUID("d3000000-0000-4000-8000-000000000061"),
        "privacy_compliance:read:tenant",
        "privacy_compliance",
        "read",
        "tenant",
        "Read bounded tenant privacy-compliance summaries.",
    ),
    (
        UUID("d3000000-0000-4000-8000-000000000062"),
        "privacy_notice:manage:tenant",
        "privacy_notice",
        "manage",
        "tenant",
        "Create, edit, and publish tenant employee privacy notices.",
    ),
    (
        UUID("d3000000-0000-4000-8000-000000000063"),
        "retention_policy:manage:tenant",
        "retention_policy",
        "manage",
        "tenant",
        "Manage tenant retention-policy metadata and run count-only dry-runs.",
    ),
)

_PERMISSION_IDS_BY_CODE = {permission[1]: permission[0] for permission in _PERMISSIONS}
_OWN_PERMISSION_CODES = (
    "privacy_notice:read:own",
    "privacy_notice:acknowledge:own",
    "privacy_consent:manage:own",
)
_GRANT_CODES_BY_ROLE: dict[str, tuple[str, ...]] = {
    "tenant_admin": (
        *_OWN_PERMISSION_CODES,
        "privacy_compliance:read:tenant",
        "privacy_notice:manage:tenant",
        "retention_policy:manage:tenant",
    ),
    "hr_director": (
        *_OWN_PERMISSION_CODES,
        "privacy_compliance:read:tenant",
        "privacy_notice:manage:tenant",
        "retention_policy:manage:tenant",
    ),
    "hr_specialist": (
        *_OWN_PERMISSION_CODES,
        "privacy_compliance:read:tenant",
        "privacy_notice:manage:tenant",
    ),
    "it_admin": _OWN_PERMISSION_CODES,
    "auditor": (*_OWN_PERMISSION_CODES, "privacy_compliance:read:tenant"),
    "manager": _OWN_PERMISSION_CODES,
    "employee": _OWN_PERMISSION_CODES,
}

_ROLE_PERMISSION_ROWS = tuple(
    (_ROLE_IDS[role_code], _PERMISSION_IDS_BY_CODE[permission_code])
    for role_code, permission_codes in _GRANT_CODES_BY_ROLE.items()
    for permission_code in permission_codes
)

if len(_ROLE_PERMISSION_ROWS) != 30:  # pragma: no cover - frozen migration invariant
    raise RuntimeError("Phase 9 migration must insert exactly 30 role-permission grants")


def upgrade() -> None:
    _create_privacy_notices()
    _create_privacy_notice_acknowledgements()
    _create_privacy_consent_purposes()
    _create_privacy_consent_states()
    _create_privacy_consent_events()
    _create_retention_policies()
    _create_retention_count_indexes()
    _create_privacy_notice_immutability_trigger()
    _seed_existing_tenant_consent_purposes()
    _configure_row_security_and_grants()
    _insert_authorization_catalog()
    _bump_affected_permission_versions()


def downgrade() -> None:
    _remove_authorization_catalog()
    # Permission versions are security epochs. A downgrade invalidates affected sessions with a
    # second monotonic bump instead of risking reuse by decrementing an epoch changed at runtime.
    _bump_affected_permission_versions()
    _drop_retention_count_indexes()

    drop_policy(
        op,
        table_name="privacy_consent_purposes",
        policy_name="p9_privacy_consent_purposes_platform_insert",
    )
    for table_name in reversed(_TABLES):
        drop_policy(
            op,
            table_name=table_name,
            policy_name=f"p9_{table_name}_tenant_isolation",
        )
        revoke_all_table_privileges(op, table_name=table_name, role_name=_TENANT_ROLE)
        revoke_all_table_privileges(op, table_name=table_name, role_name=_PLATFORM_ROLE)
        disable_forced_row_security(op, table_name=table_name)

    op.execute(sa.text("DROP TRIGGER IF EXISTS trg_privacy_notices_immutable ON privacy_notices"))
    op.execute(sa.text("DROP FUNCTION IF EXISTS p9_privacy_notice_immutable_guard()"))
    for table_name in reversed(_TABLES):
        op.drop_table(table_name)


def _create_privacy_notices() -> None:
    op.create_table(
        "privacy_notices",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("locale", sa.String(length=16), nullable=False),
        sa.Column("notice_version", sa.Integer(), nullable=False),
        sa.Column("revision", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=16), server_default="draft", nullable=False),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("published_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.CheckConstraint("kind = 'employee'", name="ck_privacy_notices_kind"),
        sa.CheckConstraint(
            "status in ('draft','published','superseded')",
            name="ck_privacy_notices_status",
        ),
        sa.CheckConstraint(
            "length(trim(locale)) > 0",
            name="ck_privacy_notices_locale_not_blank",
        ),
        sa.CheckConstraint(
            "notice_version > 0",
            name="ck_privacy_notices_notice_version_positive",
        ),
        sa.CheckConstraint("revision > 0", name="ck_privacy_notices_revision_positive"),
        sa.CheckConstraint(
            "length(trim(title)) > 0",
            name="ck_privacy_notices_title_not_blank",
        ),
        sa.CheckConstraint(
            "length(trim(body)) > 0 and length(body) <= 20000",
            name="ck_privacy_notices_body_length",
        ),
        sa.CheckConstraint(
            "content_hash ~ '^[0-9a-f]{64}$'",
            name="ck_privacy_notices_content_hash",
        ),
        sa.CheckConstraint(
            "(status = 'draft' and published_by_user_id is null and published_at is null) or "
            "(status in ('published','superseded') and published_by_user_id is not null "
            "and published_at is not null)",
            name="ck_privacy_notices_lifecycle",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name="fk_privacy_notices_tenant",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "created_by_user_id"],
            ["users.tenant_id", "users.id"],
            name="fk_privacy_notices_tenant_creator",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "published_by_user_id"],
            ["users.tenant_id", "users.id"],
            name="fk_privacy_notices_tenant_publisher",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_privacy_notices"),
        sa.UniqueConstraint(
            "tenant_id",
            "id",
            name="uq_privacy_notices_tenant_id_id",
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "kind",
            "notice_version",
            name="uq_privacy_notices_tenant_kind_version",
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "id",
            "notice_version",
            "content_hash",
            name="uq_privacy_notices_tenant_id_version_hash",
        ),
    )
    op.create_index(
        "uq_privacy_notices_tenant_kind_published",
        "privacy_notices",
        ["tenant_id", "kind"],
        unique=True,
        postgresql_where=sa.text("status = 'published'"),
    )
    op.create_index(
        "ix_privacy_notices_tenant_status_created",
        "privacy_notices",
        ["tenant_id", "status", "created_at", "id"],
    )


def _create_privacy_notice_acknowledgements() -> None:
    op.create_table(
        "privacy_notice_acknowledgements",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("notice_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("notice_version", sa.Integer(), nullable=False),
        sa.Column("notice_content_hash", sa.String(length=64), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("membership_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("evidence_request_sha256", sa.String(length=64), nullable=False),
        sa.Column("evidence_session_sha256", sa.String(length=64), nullable=True),
        sa.CheckConstraint(
            "notice_version > 0",
            name="ck_privacy_notice_acknowledgements_version_positive",
        ),
        sa.CheckConstraint(
            "notice_content_hash ~ '^[0-9a-f]{64}$'",
            name="ck_privacy_notice_acknowledgements_notice_hash",
        ),
        sa.CheckConstraint(
            "evidence_request_sha256 ~ '^[0-9a-f]{64}$'",
            name="ck_privacy_notice_acknowledgements_request_hash",
        ),
        sa.CheckConstraint(
            "evidence_session_sha256 is null or "
            "evidence_session_sha256 ~ '^[0-9a-f]{64}$'",
            name="ck_privacy_notice_acknowledgements_session_hash",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name="fk_privacy_notice_acknowledgements_tenant",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "notice_id", "notice_version", "notice_content_hash"],
            [
                "privacy_notices.tenant_id",
                "privacy_notices.id",
                "privacy_notices.notice_version",
                "privacy_notices.content_hash",
            ],
            name="fk_privacy_notice_acknowledgements_exact_notice",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "user_id"],
            ["users.tenant_id", "users.id"],
            name="fk_privacy_notice_acknowledgements_tenant_user",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "membership_id"],
            ["tenant_memberships.tenant_id", "tenant_memberships.id"],
            name="fk_privacy_notice_acknowledgements_tenant_membership",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_privacy_notice_acknowledgements"),
        sa.UniqueConstraint(
            "tenant_id",
            "id",
            name="uq_privacy_notice_acknowledgements_tenant_id_id",
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "notice_id",
            "user_id",
            name="uq_privacy_notice_acknowledgements_tenant_notice_user",
        ),
    )
    op.create_index(
        "ix_privacy_notice_acknowledgements_own_history",
        "privacy_notice_acknowledgements",
        ["tenant_id", "user_id", "acknowledged_at", "id"],
    )
    op.create_index(
        "ix_privacy_notice_acknowledgements_notice_coverage",
        "privacy_notice_acknowledgements",
        ["tenant_id", "notice_id", "acknowledged_at", "id"],
    )


def _create_privacy_consent_purposes() -> None:
    op.create_table(
        "privacy_consent_purposes",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("description", sa.String(length=1000), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "code ~ '^[a-z][a-z0-9_]{0,63}$'",
            name="ck_privacy_consent_purposes_code",
        ),
        sa.CheckConstraint(
            "version > 0",
            name="ck_privacy_consent_purposes_version_positive",
        ),
        sa.CheckConstraint(
            "length(trim(title)) > 0",
            name="ck_privacy_consent_purposes_title_not_blank",
        ),
        sa.CheckConstraint(
            "length(trim(description)) > 0",
            name="ck_privacy_consent_purposes_description_not_blank",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name="fk_privacy_consent_purposes_tenant",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_privacy_consent_purposes"),
        sa.UniqueConstraint(
            "tenant_id",
            "id",
            name="uq_privacy_consent_purposes_tenant_id_id",
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "id",
            "version",
            name="uq_privacy_consent_purposes_tenant_id_version",
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "code",
            "version",
            name="uq_privacy_consent_purposes_tenant_code_version",
        ),
    )
    op.create_index(
        "uq_privacy_consent_purposes_tenant_code_active",
        "privacy_consent_purposes",
        ["tenant_id", "code"],
        unique=True,
        postgresql_where=sa.text("is_active"),
    )
    op.create_index(
        "ix_privacy_consent_purposes_tenant_active",
        "privacy_consent_purposes",
        ["tenant_id", "is_active", "code", "version"],
    )


def _create_privacy_consent_states() -> None:
    op.create_table(
        "privacy_consent_states",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("purpose_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("membership_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("granted", sa.Boolean(), nullable=False),
        sa.Column("version", sa.Integer(), server_default=sa.text("1"), nullable=False),
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
            "version > 0",
            name="ck_privacy_consent_states_version_positive",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name="fk_privacy_consent_states_tenant",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "purpose_id"],
            ["privacy_consent_purposes.tenant_id", "privacy_consent_purposes.id"],
            name="fk_privacy_consent_states_tenant_purpose",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "user_id"],
            ["users.tenant_id", "users.id"],
            name="fk_privacy_consent_states_tenant_user",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "membership_id"],
            ["tenant_memberships.tenant_id", "tenant_memberships.id"],
            name="fk_privacy_consent_states_tenant_membership",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_privacy_consent_states"),
        sa.UniqueConstraint(
            "tenant_id",
            "id",
            name="uq_privacy_consent_states_tenant_id_id",
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "purpose_id",
            "user_id",
            name="uq_privacy_consent_states_tenant_purpose_user",
        ),
    )
    op.create_index(
        "ix_privacy_consent_states_own",
        "privacy_consent_states",
        ["tenant_id", "user_id", "purpose_id"],
    )


def _create_privacy_consent_events() -> None:
    op.create_table(
        "privacy_consent_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("purpose_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("purpose_version", sa.Integer(), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("membership_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("action", sa.String(length=16), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "purpose_version > 0",
            name="ck_privacy_consent_events_purpose_version_positive",
        ),
        sa.CheckConstraint(
            "action in ('grant','withdraw')",
            name="ck_privacy_consent_events_action",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name="fk_privacy_consent_events_tenant",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "purpose_id", "purpose_version"],
            [
                "privacy_consent_purposes.tenant_id",
                "privacy_consent_purposes.id",
                "privacy_consent_purposes.version",
            ],
            name="fk_privacy_consent_events_exact_purpose",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "user_id"],
            ["users.tenant_id", "users.id"],
            name="fk_privacy_consent_events_tenant_user",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "membership_id"],
            ["tenant_memberships.tenant_id", "tenant_memberships.id"],
            name="fk_privacy_consent_events_tenant_membership",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_privacy_consent_events"),
        sa.UniqueConstraint(
            "tenant_id",
            "id",
            name="uq_privacy_consent_events_tenant_id_id",
        ),
    )
    op.create_index(
        "ix_privacy_consent_events_own_history",
        "privacy_consent_events",
        ["tenant_id", "user_id", "occurred_at", "id"],
    )
    op.create_index(
        "ix_privacy_consent_events_purpose_history",
        "privacy_consent_events",
        ["tenant_id", "purpose_id", "occurred_at", "id"],
    )


def _create_retention_policies() -> None:
    op.create_table(
        "retention_policies",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("data_category", sa.String(length=32), nullable=False),
        sa.Column("legal_basis_note", sa.String(length=1000), nullable=False),
        sa.Column("retention_days", sa.Integer(), nullable=False),
        sa.Column("anchor", sa.String(length=32), nullable=False),
        sa.Column("action", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=16), server_default="draft", nullable=False),
        sa.Column("version", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("updated_by_user_id", postgresql.UUID(as_uuid=True), nullable=False),
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
            "data_category in "
            "('employee_records','employee_documents','leave_requests','audit_events')",
            name="ck_retention_policies_data_category",
        ),
        sa.CheckConstraint(
            "length(trim(legal_basis_note)) > 0",
            name="ck_retention_policies_legal_basis_not_blank",
        ),
        sa.CheckConstraint(
            "retention_days between 1 and 36500",
            name="ck_retention_policies_retention_days",
        ),
        sa.CheckConstraint(
            "anchor in ('employment_end_date','archived_at','created_at','occurred_at')",
            name="ck_retention_policies_anchor",
        ),
        sa.CheckConstraint(
            "(data_category = 'employee_records' and anchor = 'employment_end_date') or "
            "(data_category = 'employee_documents' and anchor = 'archived_at') or "
            "(data_category = 'leave_requests' and anchor = 'created_at') or "
            "(data_category = 'audit_events' and anchor = 'occurred_at')",
            name="ck_retention_policies_category_anchor",
        ),
        sa.CheckConstraint(
            "action in ('review','delete','anonymize')",
            name="ck_retention_policies_action",
        ),
        sa.CheckConstraint(
            "status in ('draft','active','inactive')",
            name="ck_retention_policies_status",
        ),
        sa.CheckConstraint(
            "version > 0",
            name="ck_retention_policies_version_positive",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name="fk_retention_policies_tenant",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "created_by_user_id"],
            ["users.tenant_id", "users.id"],
            name="fk_retention_policies_tenant_creator",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "updated_by_user_id"],
            ["users.tenant_id", "users.id"],
            name="fk_retention_policies_tenant_updater",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_retention_policies"),
        sa.UniqueConstraint(
            "tenant_id",
            "id",
            name="uq_retention_policies_tenant_id_id",
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "data_category",
            name="uq_retention_policies_tenant_category",
        ),
    )
    op.create_index(
        "ix_retention_policies_tenant_status_category",
        "retention_policies",
        ["tenant_id", "status", "data_category"],
    )


def _create_retention_count_indexes() -> None:
    op.create_index(
        "ix_employees_tenant_employment_end_date",
        "employees",
        ["tenant_id", "employment_end_date"],
        postgresql_where=sa.text("employment_end_date IS NOT NULL"),
    )
    op.create_index(
        "ix_employee_documents_tenant_archived_at",
        "employee_documents",
        ["tenant_id", "archived_at"],
        postgresql_where=sa.text("archived_at IS NOT NULL"),
    )


def _drop_retention_count_indexes() -> None:
    op.drop_index(
        "ix_employee_documents_tenant_archived_at",
        table_name="employee_documents",
    )
    op.drop_index(
        "ix_employees_tenant_employment_end_date",
        table_name="employees",
    )


def _create_privacy_notice_immutability_trigger() -> None:
    op.execute(
        sa.text(
            """
            CREATE FUNCTION p9_privacy_notice_immutable_guard()
            RETURNS trigger
            LANGUAGE plpgsql
            AS $p9_privacy_notice_immutable_guard$
            BEGIN
                IF OLD.status = 'draft' AND NEW.status NOT IN ('draft', 'published') THEN
                    RAISE EXCEPTION 'privacy notice draft can only be published';
                END IF;

                IF OLD.status <> 'draft' THEN
                    IF NEW.id IS DISTINCT FROM OLD.id
                       OR NEW.tenant_id IS DISTINCT FROM OLD.tenant_id
                       OR NEW.kind IS DISTINCT FROM OLD.kind
                       OR NEW.locale IS DISTINCT FROM OLD.locale
                       OR NEW.notice_version IS DISTINCT FROM OLD.notice_version
                       OR NEW.title IS DISTINCT FROM OLD.title
                       OR NEW.body IS DISTINCT FROM OLD.body
                       OR NEW.content_hash IS DISTINCT FROM OLD.content_hash
                       OR NEW.created_by_user_id IS DISTINCT FROM OLD.created_by_user_id
                       OR NEW.published_by_user_id IS DISTINCT FROM OLD.published_by_user_id
                       OR NEW.published_at IS DISTINCT FROM OLD.published_at
                       OR NEW.created_at IS DISTINCT FROM OLD.created_at THEN
                        RAISE EXCEPTION 'published privacy notice versions are immutable';
                    END IF;

                    IF OLD.status = 'published' AND NEW.status <> 'superseded' THEN
                        RAISE EXCEPTION 'published privacy notice can only be superseded';
                    END IF;
                    IF OLD.status = 'superseded' THEN
                        RAISE EXCEPTION 'superseded privacy notice is immutable';
                    END IF;
                END IF;
                RETURN NEW;
            END
            $p9_privacy_notice_immutable_guard$
            """
        )
    )
    op.execute(
        sa.text(
            """
            CREATE TRIGGER trg_privacy_notices_immutable
            BEFORE UPDATE ON privacy_notices
            FOR EACH ROW
            EXECUTE FUNCTION p9_privacy_notice_immutable_guard()
            """
        )
    )
    op.execute(
        sa.text(
            "REVOKE ALL ON FUNCTION p9_privacy_notice_immutable_guard() FROM PUBLIC"
        )
    )


def _seed_existing_tenant_consent_purposes() -> None:
    # The digest is formatted as an RFC-compatible UUIDv5-shaped identifier without relying on a
    # database extension: version nibble 5, RFC variant nibble 8, remaining bits from MD5.
    op.execute(
        sa.text(
            """
            INSERT INTO privacy_consent_purposes (
                id,
                tenant_id,
                code,
                version,
                title,
                description,
                is_active,
                created_at
            )
            SELECT
                (
                    substr(seed.digest, 1, 8) || '-' ||
                    substr(seed.digest, 9, 4) || '-' ||
                    '5' || substr(seed.digest, 14, 3) || '-' ||
                    '8' || substr(seed.digest, 18, 3) || '-' ||
                    substr(seed.digest, 21, 12)
                )::uuid,
                tenants.id,
                'optional_communications',
                1,
                'İsteğe bağlı iletişimler',
                'Zorunlu olmayan çalışan iletişimleri için isteğe bağlı onay.',
                true,
                now()
            FROM tenants
            CROSS JOIN LATERAL (
                SELECT md5(
                    'p9:privacy-consent-purpose:' || tenants.id::text ||
                    ':optional_communications:1'
                ) AS digest
            ) AS seed
            """
        )
    )


def _configure_row_security_and_grants() -> None:
    for table_name in _TABLES:
        op.execute(sa.text(f'REVOKE ALL PRIVILEGES ON TABLE "{table_name}" FROM PUBLIC'))
        revoke_all_table_privileges(op, table_name=table_name, role_name=_TENANT_ROLE)
        revoke_all_table_privileges(op, table_name=table_name, role_name=_PLATFORM_ROLE)
        enable_forced_row_security(op, table_name=table_name)
        create_tenant_isolation_policy(
            op,
            table_name=table_name,
            policy_name=f"p9_{table_name}_tenant_isolation",
            role_name=_TENANT_ROLE,
        )
        grant_table_privileges(
            op,
            table_name=table_name,
            role_name=_TENANT_ROLE,
            privileges=_TENANT_PRIVILEGES[table_name],
        )

    create_unrestricted_insert_policy(
        op,
        table_name="privacy_consent_purposes",
        policy_name="p9_privacy_consent_purposes_platform_insert",
        role_name=_PLATFORM_ROLE,
    )
    grant_table_privileges(
        op,
        table_name="privacy_consent_purposes",
        role_name=_PLATFORM_ROLE,
        privileges=("INSERT",),
    )


def _insert_authorization_catalog() -> None:
    permissions = sa.table(
        "permissions",
        sa.column("id", postgresql.UUID(as_uuid=True)),
        sa.column("code", sa.String()),
        sa.column("resource", sa.String()),
        sa.column("action", sa.String()),
        sa.column("target", sa.String()),
        sa.column("target_type", sa.String()),
        sa.column("description", sa.Text()),
    )
    op.bulk_insert(
        permissions,
        [
            {
                "id": permission_id,
                "code": code,
                "resource": resource,
                "action": action,
                "target": target,
                "target_type": "scope",
                "description": description,
            }
            for permission_id, code, resource, action, target, description in _PERMISSIONS
        ],
    )

    role_permissions = sa.table(
        "role_permissions",
        sa.column("role_id", postgresql.UUID(as_uuid=True)),
        sa.column("permission_id", postgresql.UUID(as_uuid=True)),
    )
    op.bulk_insert(
        role_permissions,
        [
            {"role_id": role_id, "permission_id": permission_id}
            for role_id, permission_id in _ROLE_PERMISSION_ROWS
        ],
    )


def _remove_authorization_catalog() -> None:
    permission_ids = tuple(permission[0] for permission in _PERMISSIONS)
    role_permissions = sa.table(
        "role_permissions",
        sa.column("role_id", postgresql.UUID(as_uuid=True)),
        sa.column("permission_id", postgresql.UUID(as_uuid=True)),
    )
    permissions = sa.table(
        "permissions",
        sa.column("id", postgresql.UUID(as_uuid=True)),
    )
    bind = op.get_bind()
    bind.execute(
        sa.delete(role_permissions).where(role_permissions.c.permission_id.in_(permission_ids))
    )
    bind.execute(sa.delete(permissions).where(permissions.c.id.in_(permission_ids)))


def _bump_affected_permission_versions() -> None:
    affected_role_ids = ", ".join(f"'{role_id}'::uuid" for role_id in _ROLE_IDS.values())
    op.execute(
        sa.text(
            f"""
            WITH affected_users AS (
                SELECT DISTINCT user_roles.tenant_id, user_roles.user_id
                FROM user_roles
                WHERE user_roles.active IS TRUE
                  AND user_roles.role_id IN ({affected_role_ids})
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
