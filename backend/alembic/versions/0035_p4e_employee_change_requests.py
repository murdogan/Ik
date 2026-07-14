"""add P4E employee personal-profile change requests

Revision ID: 0035_p4e_employee_change_requests
Revises: 0034_p4c_employee_account_links
Create Date: 2026-07-14
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from app.platform.db.rls_migration import (
    create_tenant_isolation_policy,
    disable_forced_row_security,
    drop_policy,
    enable_forced_row_security,
    grant_column_privilege,
    revoke_all_column_privileges,
    revoke_all_table_privileges,
    revoke_column_privilege,
    revoke_table_privileges,
)
from app.platform.db.tenant_access import (
    AUTHENTICATION_APPLICATION_ROLE,
    PLATFORM_APPLICATION_ROLE,
    TENANT_APPLICATION_ROLE,
)
from sqlalchemy.dialects import postgresql

revision: str = "0035_p4e_employee_change_requests"
down_revision: str | None = "0034_p4c_employee_account_links"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_REQUESTS_TABLE = "employee_profile_change_requests"
_PROFILES_TABLE = "employee_profiles"
_EMPLOYEES_TABLE = "employees"
_LINKS_TABLE = "employee_account_links"
_MEMBERSHIPS_TABLE = "tenant_memberships"
_MEMBERSHIP_ROLES_TABLE = "membership_roles"
_ROLE_PERMISSIONS_TABLE = "role_permissions"
_PERMISSIONS_TABLE = "permissions"
_AUDIT_EVENTS_TABLE = "audit_events"

_COMMAND_SCHEMA = "p4e_command"
_COMMAND_BINDINGS_TABLE = "database_command_bindings"
_BIND_FUNCTION = "bind_database_command"
_CLAIM_FUNCTION = "claim_database_command"
_AUDIT_FUNCTION = "write_employee_profile_change_request_audit"
_BIND_SIGNATURE = (
    f"{_COMMAND_SCHEMA}.{_BIND_FUNCTION}"
    "(uuid, uuid, uuid, character varying, uuid, uuid, character varying, "
    "character varying, uuid)"
)
_CLAIM_SIGNATURE = f"{_COMMAND_SCHEMA}.{_CLAIM_FUNCTION}(character varying, uuid)"
_AUDIT_SIGNATURE = f"{_COMMAND_SCHEMA}.{_AUDIT_FUNCTION}()"

_TENANT_POLICY = "tenant_isolation_app"
_EXECUTOR_ROLE = "wealthy_falcon_identity_recovery"
_IDENTITY_PROJECTION_ROLE = "wealthy_falcon_identity_projection"

_EXECUTOR_REQUEST_POLICY = "p4e_executor_request_access"
_EXECUTOR_PROFILE_POLICY = "p4e_executor_profile_access"
_EXECUTOR_EMPLOYEE_POLICY = "p4e_executor_employee_read"
_EXECUTOR_LINK_POLICY = "p4e_executor_account_link_read"
_EXECUTOR_MEMBERSHIP_ROLE_POLICY = "p4e_executor_membership_role_read"
_EXECUTOR_AUDIT_POLICY = "p4e_executor_audit_insert"
_COMMAND_EXECUTOR_SELECT_POLICY = "p4e_command_executor_select"
_COMMAND_EXECUTOR_INSERT_POLICY = "p4e_command_executor_insert"
_COMMAND_EXECUTOR_UPDATE_POLICY = "p4e_command_executor_update"
_COMMAND_EXECUTOR_DELETE_POLICY = "p4e_command_executor_delete_committed"

_SUBMIT_FUNCTION = "submit_own_employee_profile_change_request"
_TRANSITION_FUNCTION = "transition_employee_profile_change_request"
_PERSONAL_UPDATE_FUNCTION = "update_employee_personal_profile_values"
_SUBMIT_SIGNATURE = (
    f"public.{_SUBMIT_FUNCTION}"
    "(uuid, boolean, character varying, boolean, character varying, boolean, date)"
)
_TRANSITION_SIGNATURE = (
    f"public.{_TRANSITION_FUNCTION}(uuid, integer, character varying, character varying)"
)
_PERSONAL_UPDATE_SIGNATURE = (
    f"public.{_PERSONAL_UPDATE_FUNCTION}"
    "(uuid, integer, boolean, character varying, boolean, character varying, "
    "boolean, date)"
)

_UUID = postgresql.UUID(as_uuid=True)
_REQUEST_COLUMNS = (
    "id",
    "tenant_id",
    "employee_id",
    "requester_membership_id",
    "requester_user_id",
    "status",
    "version",
    "base_profile_version",
    "preferred_name_changed",
    "previous_preferred_name",
    "proposed_preferred_name",
    "phone_changed",
    "previous_phone",
    "proposed_phone",
    "birth_date_changed",
    "previous_birth_date",
    "proposed_birth_date",
    "submitted_at",
    "decided_at",
    "cancelled_at",
    "decided_by_membership_id",
    "decided_by_user_id",
    "rejection_reason",
    "created_at",
    "updated_at",
)
_REQUEST_INSERT_COLUMNS = (
    "id",
    "tenant_id",
    "employee_id",
    "requester_membership_id",
    "requester_user_id",
    "status",
    "version",
    "base_profile_version",
    "preferred_name_changed",
    "previous_preferred_name",
    "proposed_preferred_name",
    "phone_changed",
    "previous_phone",
    "proposed_phone",
    "birth_date_changed",
    "previous_birth_date",
    "proposed_birth_date",
    "submitted_at",
    "created_at",
    "updated_at",
)
_REQUEST_UPDATE_COLUMNS = (
    "status",
    "version",
    "decided_at",
    "cancelled_at",
    "decided_by_membership_id",
    "decided_by_user_id",
    "rejection_reason",
    "updated_at",
)
_PROFILE_UPDATE_COLUMNS = (
    "preferred_name",
    "birth_date",
    "phone",
    "version",
    "updated_at",
)
_AUDIT_INSERT_COLUMNS = (
    "id",
    "occurred_at",
    "scope_type",
    "tenant_id",
    "actor_type",
    "actor_user_id",
    "impersonator_user_id",
    "event_type",
    "category",
    "severity",
    "resource_type",
    "resource_id",
    "action",
    "result",
    "request_id",
    "trace_id",
    "session_id",
    "ip_address",
    "user_agent",
    "reason",
    "support_ticket_id",
    "changed_fields",
    "before_data",
    "after_data",
    "metadata",
    "data_classification",
    "visibility_class",
    "integrity_hash",
)


def upgrade() -> None:
    _create_requests_table()
    if op.get_bind().dialect.name == "postgresql":
        _create_command_binding_storage()
        _configure_postgresql_security()
        _create_command_binding_functions()
        _create_command_functions()
        # P4B originally needed direct column UPDATE. P4E closes that raw-SQL bypass and routes
        # both existing HR personal writes and request approval through checked command functions.
        revoke_table_privileges(
            op,
            table_name=_PROFILES_TABLE,
            role_name=TENANT_APPLICATION_ROLE,
            privileges=("UPDATE",),
        )
        revoke_column_privilege(
            op,
            table_name=_PROFILES_TABLE,
            role_name=TENANT_APPLICATION_ROLE,
            privilege="UPDATE",
            column_names=_PROFILE_UPDATE_COLUMNS,
        )


def downgrade() -> None:
    is_postgresql = op.get_bind().dialect.name == "postgresql"
    if is_postgresql:
        # The migration owner is subject to FORCE RLS. A refused downgrade is transactional and
        # therefore restores ENABLE + FORCE together with every function/grant below.
        disable_forced_row_security(op, table_name=_REQUESTS_TABLE)

    _assert_downgrade_is_safe()

    if is_postgresql:
        _drop_command_functions()
        _drop_command_binding_functions()
        grant_column_privilege(
            op,
            table_name=_PROFILES_TABLE,
            role_name=TENANT_APPLICATION_ROLE,
            privilege="UPDATE",
            column_names=_PROFILE_UPDATE_COLUMNS,
        )
        _remove_postgresql_security()
        _drop_command_binding_storage()

    op.drop_table(_REQUESTS_TABLE)


def _create_requests_table() -> None:
    op.create_table(
        _REQUESTS_TABLE,
        sa.Column("id", _UUID, nullable=False),
        sa.Column("tenant_id", _UUID, nullable=False),
        sa.Column("employee_id", _UUID, nullable=False),
        sa.Column("requester_membership_id", _UUID, nullable=False),
        sa.Column("requester_user_id", _UUID, nullable=False),
        sa.Column(
            "status",
            sa.String(length=32),
            server_default="submitted",
            nullable=False,
        ),
        sa.Column("version", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column("base_profile_version", sa.Integer(), nullable=False),
        sa.Column(
            "preferred_name_changed",
            sa.Boolean(),
            server_default=sa.false(),
            nullable=False,
        ),
        sa.Column("previous_preferred_name", sa.String(length=200), nullable=True),
        sa.Column("proposed_preferred_name", sa.String(length=200), nullable=True),
        sa.Column(
            "phone_changed",
            sa.Boolean(),
            server_default=sa.false(),
            nullable=False,
        ),
        sa.Column("previous_phone", sa.String(length=32), nullable=True),
        sa.Column("proposed_phone", sa.String(length=32), nullable=True),
        sa.Column(
            "birth_date_changed",
            sa.Boolean(),
            server_default=sa.false(),
            nullable=False,
        ),
        sa.Column("previous_birth_date", sa.Date(), nullable=True),
        sa.Column("proposed_birth_date", sa.Date(), nullable=True),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("decided_by_membership_id", _UUID, nullable=True),
        sa.Column("decided_by_user_id", _UUID, nullable=True),
        sa.Column("rejection_reason", sa.String(length=500), nullable=True),
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
            "status in ('submitted','approved','rejected','cancelled')",
            name="ck_employee_profile_change_requests_status",
        ),
        sa.CheckConstraint(
            "version > 0",
            name="ck_employee_profile_change_requests_version_positive",
        ),
        sa.CheckConstraint(
            "base_profile_version > 0",
            name="ck_employee_profile_change_requests_base_version_positive",
        ),
        sa.CheckConstraint(
            "preferred_name_changed or phone_changed or birth_date_changed",
            name="ck_employee_profile_change_requests_has_change",
        ),
        sa.CheckConstraint(
            "(preferred_name_changed and previous_preferred_name is distinct from "
            "proposed_preferred_name) or (not preferred_name_changed and "
            "previous_preferred_name is null and proposed_preferred_name is null)",
            name="ck_employee_profile_change_requests_preferred_snapshot",
        ),
        sa.CheckConstraint(
            "(phone_changed and previous_phone is distinct from proposed_phone) or "
            "(not phone_changed and previous_phone is null and proposed_phone is null)",
            name="ck_employee_profile_change_requests_phone_snapshot",
        ),
        sa.CheckConstraint(
            "(birth_date_changed and previous_birth_date is distinct from "
            "proposed_birth_date) or (not birth_date_changed and "
            "previous_birth_date is null and proposed_birth_date is null)",
            name="ck_employee_profile_change_requests_birth_snapshot",
        ),
        sa.CheckConstraint(
            "(decided_at is null or decided_at >= submitted_at) and "
            "(cancelled_at is null or cancelled_at >= submitted_at)",
            name="ck_employee_profile_change_requests_timestamp_order",
        ),
        sa.CheckConstraint(
            "(status = 'submitted' and decided_at is null and cancelled_at is null "
            "and decided_by_membership_id is null and decided_by_user_id is null "
            "and rejection_reason is null) or "
            "(status = 'approved' and decided_at is not null and cancelled_at is null "
            "and decided_by_membership_id is not null and decided_by_user_id is not null "
            "and rejection_reason is null) or "
            "(status = 'rejected' and decided_at is not null and cancelled_at is null "
            "and decided_by_membership_id is not null and decided_by_user_id is not null "
            "and rejection_reason is not null and length(trim(rejection_reason)) > 0) or "
            "(status = 'cancelled' and decided_at is null and cancelled_at is not null "
            "and decided_by_membership_id is null and decided_by_user_id is null "
            "and rejection_reason is null)",
            name="ck_employee_profile_change_requests_state",
        ),
        sa.ForeignKeyConstraint(
            ("tenant_id",),
            ("tenants.id",),
            name="fk_employee_profile_change_requests_tenant_id_tenants",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ("tenant_id", "employee_id"),
            ("employees.tenant_id", "employees.id"),
            name="fk_epcr_tenant_employee_employees",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ("tenant_id", "requester_membership_id"),
            ("tenant_memberships.tenant_id", "tenant_memberships.id"),
            name="fk_epcr_requester_membership_memberships",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ("tenant_id", "requester_user_id"),
            ("users.tenant_id", "users.id"),
            name="fk_epcr_requester_user_users",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ("tenant_id", "decided_by_membership_id"),
            ("tenant_memberships.tenant_id", "tenant_memberships.id"),
            name="fk_epcr_decider_membership_memberships",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ("tenant_id", "decided_by_user_id"),
            ("users.tenant_id", "users.id"),
            name="fk_epcr_decider_user_users",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_employee_profile_change_requests"),
        sa.UniqueConstraint(
            "tenant_id",
            "id",
            name="uq_employee_profile_change_requests_tenant_id_id",
        ),
    )
    op.create_index(
        "uq_employee_profile_change_requests_active_employee",
        _REQUESTS_TABLE,
        ["tenant_id", "employee_id"],
        unique=True,
        postgresql_where=sa.text("status = 'submitted'"),
        sqlite_where=sa.text("status = 'submitted'"),
    )
    op.create_index(
        "ix_employee_profile_change_requests_tenant_queue_cursor",
        _REQUESTS_TABLE,
        ["tenant_id", "status", "submitted_at", "id"],
    )
    op.create_index(
        "ix_employee_profile_change_requests_own_cursor",
        _REQUESTS_TABLE,
        [
            "tenant_id",
            "employee_id",
            "requester_membership_id",
            "submitted_at",
            "id",
        ],
    )


def _create_command_binding_storage() -> None:
    op.execute(sa.text(f'CREATE SCHEMA "{_COMMAND_SCHEMA}"'))
    op.execute(sa.text(f'REVOKE ALL PRIVILEGES ON SCHEMA "{_COMMAND_SCHEMA}" FROM PUBLIC'))
    for role_name in (
        TENANT_APPLICATION_ROLE,
        PLATFORM_APPLICATION_ROLE,
        AUTHENTICATION_APPLICATION_ROLE,
        _IDENTITY_PROJECTION_ROLE,
    ):
        op.execute(
            sa.text(f'REVOKE ALL PRIVILEGES ON SCHEMA "{_COMMAND_SCHEMA}" FROM "{role_name}"')
        )
    # CREATE is needed only while ownership of the fixed set of helper functions transfers to
    # the private role. It is revoked immediately after those ALTER FUNCTION statements.
    op.execute(sa.text(f'GRANT USAGE, CREATE ON SCHEMA "{_COMMAND_SCHEMA}" TO "{_EXECUTOR_ROLE}"'))
    op.execute(
        sa.text(
            f"""
            CREATE TABLE {_COMMAND_SCHEMA}.{_COMMAND_BINDINGS_TABLE} (
                backend_pid integer NOT NULL,
                transaction_id xid8 NOT NULL,
                gateway_session_user text NOT NULL,
                tenant_id uuid NOT NULL,
                actor_user_id uuid NOT NULL,
                membership_id uuid NOT NULL,
                intent character varying(32) NOT NULL,
                target_id uuid NOT NULL,
                audit_event_id uuid NOT NULL,
                correlation_request_id character varying(128) NOT NULL,
                trace_id character varying(32) NOT NULL,
                session_id uuid NULL,
                state character varying(16) NOT NULL DEFAULT 'bound',
                bound_at timestamptz NOT NULL DEFAULT clock_timestamp(),
                executed_at timestamptz NULL,
                audit_written_at timestamptz NULL,
                CONSTRAINT pk_p4e_database_command_bindings
                    PRIMARY KEY (backend_pid, transaction_id),
                CONSTRAINT ck_p4e_database_command_bindings_backend
                    CHECK (backend_pid > 0),
                CONSTRAINT ck_p4e_database_command_bindings_context
                    CHECK (
                        tenant_id <> '00000000-0000-0000-0000-000000000000'::uuid
                        AND actor_user_id <> '00000000-0000-0000-0000-000000000000'::uuid
                        AND membership_id <> '00000000-0000-0000-0000-000000000000'::uuid
                        AND target_id <> '00000000-0000-0000-0000-000000000000'::uuid
                        AND audit_event_id <> '00000000-0000-0000-0000-000000000000'::uuid
                        AND (
                            session_id IS NULL
                            OR session_id <> '00000000-0000-0000-0000-000000000000'::uuid
                        )
                    ),
                CONSTRAINT ck_p4e_database_command_bindings_intent
                    CHECK (intent IN (
                        'p4e_submit',
                        'p4e_cancel',
                        'p4e_approve',
                        'p4e_reject',
                        'p4b_personal_update'
                    )),
                CONSTRAINT ck_p4e_database_command_bindings_request_id
                    CHECK (
                        length(correlation_request_id) BETWEEN 1 AND 128
                        AND correlation_request_id ~
                            '^[A-Za-z0-9]$|^[A-Za-z0-9][A-Za-z0-9._-]{{0,126}}[A-Za-z0-9]$'
                    ),
                CONSTRAINT ck_p4e_database_command_bindings_trace_id
                    CHECK (
                        trace_id ~ '^[0-9a-f]{{32}}$'
                        AND trace_id <> repeat('0', 32)
                    ),
                CONSTRAINT ck_p4e_database_command_bindings_state
                    CHECK (
                        (
                            state = 'bound'
                            AND executed_at IS NULL
                            AND audit_written_at IS NULL
                        ) OR (
                            state = 'executed'
                            AND executed_at IS NOT NULL
                            AND (
                                audit_written_at IS NULL
                                OR audit_written_at >= executed_at
                            )
                        )
                    )
            )
            """
        )
    )
    op.execute(
        sa.text(
            f"CREATE INDEX ix_p4e_database_command_bindings_bound_at "
            f"ON {_COMMAND_SCHEMA}.{_COMMAND_BINDINGS_TABLE} (bound_at)"
        )
    )
    op.execute(
        sa.text(
            f'REVOKE ALL PRIVILEGES ON TABLE "{_COMMAND_SCHEMA}".'
            f'"{_COMMAND_BINDINGS_TABLE}" FROM PUBLIC'
        )
    )
    for role_name in (
        TENANT_APPLICATION_ROLE,
        PLATFORM_APPLICATION_ROLE,
        AUTHENTICATION_APPLICATION_ROLE,
        _IDENTITY_PROJECTION_ROLE,
    ):
        op.execute(
            sa.text(
                f'REVOKE ALL PRIVILEGES ON TABLE "{_COMMAND_SCHEMA}".'
                f'"{_COMMAND_BINDINGS_TABLE}" FROM "{role_name}"'
            )
        )
    op.execute(
        sa.text(
            f'ALTER TABLE "{_COMMAND_SCHEMA}"."{_COMMAND_BINDINGS_TABLE}" ENABLE ROW LEVEL SECURITY'
        )
    )
    op.execute(
        sa.text(
            f'ALTER TABLE "{_COMMAND_SCHEMA}"."{_COMMAND_BINDINGS_TABLE}" FORCE ROW LEVEL SECURITY'
        )
    )
    binding_predicate = (
        "backend_pid = pg_backend_pid() "
        "AND transaction_id = pg_current_xact_id() "
        "AND gateway_session_user = session_user"
    )
    op.execute(
        sa.text(
            f'CREATE POLICY "{_COMMAND_EXECUTOR_SELECT_POLICY}" '
            f'ON "{_COMMAND_SCHEMA}"."{_COMMAND_BINDINGS_TABLE}" '
            f'AS PERMISSIVE FOR SELECT TO "{_EXECUTOR_ROLE}" '
            f"USING (({binding_predicate}) "
            "OR transaction_id <> pg_current_xact_id())"
        )
    )
    op.execute(
        sa.text(
            f'CREATE POLICY "{_COMMAND_EXECUTOR_INSERT_POLICY}" '
            f'ON "{_COMMAND_SCHEMA}"."{_COMMAND_BINDINGS_TABLE}" '
            f'AS PERMISSIVE FOR INSERT TO "{_EXECUTOR_ROLE}" '
            f"WITH CHECK ({binding_predicate})"
        )
    )
    op.execute(
        sa.text(
            f'CREATE POLICY "{_COMMAND_EXECUTOR_UPDATE_POLICY}" '
            f'ON "{_COMMAND_SCHEMA}"."{_COMMAND_BINDINGS_TABLE}" '
            f'AS PERMISSIVE FOR UPDATE TO "{_EXECUTOR_ROLE}" '
            f"USING (({binding_predicate}) "
            "OR transaction_id <> pg_current_xact_id()) "
            f"WITH CHECK ({binding_predicate})"
        )
    )
    op.execute(
        sa.text(
            f'CREATE POLICY "{_COMMAND_EXECUTOR_DELETE_POLICY}" '
            f'ON "{_COMMAND_SCHEMA}"."{_COMMAND_BINDINGS_TABLE}" '
            f'AS PERMISSIVE FOR DELETE TO "{_EXECUTOR_ROLE}" '
            "USING (transaction_id <> pg_current_xact_id())"
        )
    )
    binding_columns = (
        "backend_pid",
        "transaction_id",
        "gateway_session_user",
        "tenant_id",
        "actor_user_id",
        "membership_id",
        "intent",
        "target_id",
        "audit_event_id",
        "correlation_request_id",
        "trace_id",
        "session_id",
        "state",
        "bound_at",
        "executed_at",
        "audit_written_at",
    )
    quoted_binding_columns = ", ".join(f'"{column}"' for column in binding_columns)
    op.execute(
        sa.text(
            f"GRANT SELECT ({quoted_binding_columns}) ON TABLE "
            f'"{_COMMAND_SCHEMA}"."{_COMMAND_BINDINGS_TABLE}" TO "{_EXECUTOR_ROLE}"'
        )
    )
    op.execute(
        sa.text(
            f"GRANT INSERT ({quoted_binding_columns}) ON TABLE "
            f'"{_COMMAND_SCHEMA}"."{_COMMAND_BINDINGS_TABLE}" TO "{_EXECUTOR_ROLE}"'
        )
    )
    op.execute(
        sa.text(
            f"GRANT UPDATE (state, executed_at, audit_written_at) ON TABLE "
            f'"{_COMMAND_SCHEMA}"."{_COMMAND_BINDINGS_TABLE}" TO "{_EXECUTOR_ROLE}"'
        )
    )
    op.execute(
        sa.text(
            f'GRANT DELETE ON TABLE "{_COMMAND_SCHEMA}".'
            f'"{_COMMAND_BINDINGS_TABLE}" TO "{_EXECUTOR_ROLE}"'
        )
    )


def _drop_command_binding_storage() -> None:
    op.execute(sa.text(f'DROP TABLE IF EXISTS "{_COMMAND_SCHEMA}"."{_COMMAND_BINDINGS_TABLE}"'))
    op.execute(sa.text(f'DROP SCHEMA IF EXISTS "{_COMMAND_SCHEMA}"'))


def _assert_downgrade_is_safe() -> None:
    request_count_sql = f"select count(*) from {_REQUESTS_TABLE}"
    if op.get_context().as_sql:
        op.execute(
            sa.text(
                f"""
                DO $p4e_employee_change_request_downgrade_preflight$
                DECLARE
                    retained_request_count bigint;
                BEGIN
                    retained_request_count := ({request_count_sql});
                    IF retained_request_count > 0 THEN
                        RAISE EXCEPTION
                            'P4E employee change request downgrade refused: requests=%',
                            retained_request_count;
                    END IF;
                END
                $p4e_employee_change_request_downgrade_preflight$
                """
            )
        )
        return

    request_count = int(op.get_bind().scalar(sa.text(request_count_sql)) or 0)
    if request_count:
        raise RuntimeError(
            f"P4E employee change request downgrade refused: requests={request_count}"
        )


def _configure_postgresql_security() -> None:
    _assert_executor_owner_is_private()
    _reset_request_acl()
    enable_forced_row_security(op, table_name=_REQUESTS_TABLE)
    create_tenant_isolation_policy(
        op,
        table_name=_REQUESTS_TABLE,
        policy_name=_TENANT_POLICY,
        role_name=TENANT_APPLICATION_ROLE,
    )
    _create_executor_policy(
        table_name=_REQUESTS_TABLE,
        policy_name=_EXECUTOR_REQUEST_POLICY,
        command="ALL",
    )
    _create_executor_policy(
        table_name=_PROFILES_TABLE,
        policy_name=_EXECUTOR_PROFILE_POLICY,
        command="ALL",
    )
    for table_name, policy_name in (
        (_EMPLOYEES_TABLE, _EXECUTOR_EMPLOYEE_POLICY),
        (_LINKS_TABLE, _EXECUTOR_LINK_POLICY),
        (_MEMBERSHIP_ROLES_TABLE, _EXECUTOR_MEMBERSHIP_ROLE_POLICY),
    ):
        _create_executor_policy(
            table_name=table_name,
            policy_name=policy_name,
            command="SELECT",
        )

    op.execute(
        sa.text(
            f'CREATE POLICY "{_EXECUTOR_AUDIT_POLICY}" ON "{_AUDIT_EVENTS_TABLE}" '
            f'AS PERMISSIVE FOR INSERT TO "{_EXECUTOR_ROLE}" '
            "WITH CHECK ("
            "scope_type = 'tenant' "
            "AND tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid "
            "AND resource_type = 'employee_profile_change_request' "
            "AND event_type IN ("
            "'employee.profile_change_request.submitted',"
            "'employee.profile_change_request.approved',"
            "'employee.profile_change_request.rejected',"
            "'employee.profile_change_request.cancelled'"
            ")"
            ")"
        )
    )

    grant_column_privilege(
        op,
        table_name=_REQUESTS_TABLE,
        role_name=TENANT_APPLICATION_ROLE,
        privilege="SELECT",
        column_names=_REQUEST_COLUMNS,
    )
    grant_column_privilege(
        op,
        table_name=_REQUESTS_TABLE,
        role_name=_EXECUTOR_ROLE,
        privilege="SELECT",
        column_names=_REQUEST_COLUMNS,
    )
    grant_column_privilege(
        op,
        table_name=_REQUESTS_TABLE,
        role_name=_EXECUTOR_ROLE,
        privilege="INSERT",
        column_names=_REQUEST_INSERT_COLUMNS,
    )
    grant_column_privilege(
        op,
        table_name=_REQUESTS_TABLE,
        role_name=_EXECUTOR_ROLE,
        privilege="UPDATE",
        column_names=_REQUEST_UPDATE_COLUMNS,
    )

    _reset_executor_acl(
        table_name=_PROFILES_TABLE,
        column_names=(
            "id",
            "tenant_id",
            "employee_id",
            "preferred_name",
            "birth_date",
            "phone",
            "version",
            "created_at",
            "updated_at",
        ),
    )
    grant_column_privilege(
        op,
        table_name=_PROFILES_TABLE,
        role_name=_EXECUTOR_ROLE,
        privilege="SELECT",
        column_names=(
            "id",
            "tenant_id",
            "employee_id",
            "preferred_name",
            "birth_date",
            "phone",
            "version",
        ),
    )
    grant_column_privilege(
        op,
        table_name=_PROFILES_TABLE,
        role_name=_EXECUTOR_ROLE,
        privilege="UPDATE",
        column_names=_PROFILE_UPDATE_COLUMNS,
    )

    executor_select_columns = {
        _EMPLOYEES_TABLE: ("id", "tenant_id", "archived_at"),
        _LINKS_TABLE: ("tenant_id", "employee_id", "membership_id"),
        _MEMBERSHIP_ROLES_TABLE: (
            "tenant_id",
            "membership_id",
            "role_id",
            "active",
        ),
        _ROLE_PERMISSIONS_TABLE: ("role_id", "permission_id"),
        _PERMISSIONS_TABLE: ("id", "code"),
    }
    for table_name, column_names in executor_select_columns.items():
        _reset_executor_acl(table_name=table_name, column_names=column_names)
        grant_column_privilege(
            op,
            table_name=table_name,
            role_name=_EXECUTOR_ROLE,
            privilege="SELECT",
            column_names=column_names,
        )

    _reset_executor_acl(
        table_name=_AUDIT_EVENTS_TABLE,
        column_names=_AUDIT_INSERT_COLUMNS,
    )
    grant_column_privilege(
        op,
        table_name=_AUDIT_EVENTS_TABLE,
        role_name=_EXECUTOR_ROLE,
        privilege="INSERT",
        column_names=_AUDIT_INSERT_COLUMNS,
    )


def _remove_postgresql_security() -> None:
    revoke_column_privilege(
        op,
        table_name=_AUDIT_EVENTS_TABLE,
        role_name=_EXECUTOR_ROLE,
        privilege="INSERT",
        column_names=_AUDIT_INSERT_COLUMNS,
    )
    drop_policy(
        op,
        table_name=_AUDIT_EVENTS_TABLE,
        policy_name=_EXECUTOR_AUDIT_POLICY,
    )
    revoke_column_privilege(
        op,
        table_name=_REQUESTS_TABLE,
        role_name=_EXECUTOR_ROLE,
        privilege="UPDATE",
        column_names=_REQUEST_UPDATE_COLUMNS,
    )
    revoke_column_privilege(
        op,
        table_name=_REQUESTS_TABLE,
        role_name=_EXECUTOR_ROLE,
        privilege="INSERT",
        column_names=_REQUEST_INSERT_COLUMNS,
    )
    revoke_column_privilege(
        op,
        table_name=_REQUESTS_TABLE,
        role_name=_EXECUTOR_ROLE,
        privilege="SELECT",
        column_names=_REQUEST_COLUMNS,
    )
    revoke_column_privilege(
        op,
        table_name=_REQUESTS_TABLE,
        role_name=TENANT_APPLICATION_ROLE,
        privilege="SELECT",
        column_names=_REQUEST_COLUMNS,
    )

    revoke_column_privilege(
        op,
        table_name=_PROFILES_TABLE,
        role_name=_EXECUTOR_ROLE,
        privilege="UPDATE",
        column_names=_PROFILE_UPDATE_COLUMNS,
    )
    revoke_column_privilege(
        op,
        table_name=_PROFILES_TABLE,
        role_name=_EXECUTOR_ROLE,
        privilege="SELECT",
        column_names=(
            "id",
            "tenant_id",
            "employee_id",
            "preferred_name",
            "birth_date",
            "phone",
            "version",
        ),
    )
    for table_name, column_names in {
        _EMPLOYEES_TABLE: ("id", "tenant_id", "archived_at"),
        _LINKS_TABLE: ("tenant_id", "employee_id", "membership_id"),
        _MEMBERSHIP_ROLES_TABLE: (
            "tenant_id",
            "membership_id",
            "role_id",
            "active",
        ),
        _ROLE_PERMISSIONS_TABLE: ("role_id", "permission_id"),
        _PERMISSIONS_TABLE: ("id", "code"),
    }.items():
        revoke_column_privilege(
            op,
            table_name=table_name,
            role_name=_EXECUTOR_ROLE,
            privilege="SELECT",
            column_names=column_names,
        )

    for table_name, policy_name in (
        (_MEMBERSHIP_ROLES_TABLE, _EXECUTOR_MEMBERSHIP_ROLE_POLICY),
        (_LINKS_TABLE, _EXECUTOR_LINK_POLICY),
        (_EMPLOYEES_TABLE, _EXECUTOR_EMPLOYEE_POLICY),
        (_PROFILES_TABLE, _EXECUTOR_PROFILE_POLICY),
        (_REQUESTS_TABLE, _EXECUTOR_REQUEST_POLICY),
    ):
        drop_policy(op, table_name=table_name, policy_name=policy_name)
    drop_policy(
        op,
        table_name=_REQUESTS_TABLE,
        policy_name=_TENANT_POLICY,
    )


def _reset_request_acl() -> None:
    quoted_columns = ", ".join(f'"{column_name}"' for column_name in _REQUEST_COLUMNS)
    op.execute(sa.text(f'REVOKE ALL PRIVILEGES ON TABLE "{_REQUESTS_TABLE}" FROM PUBLIC'))
    op.execute(
        sa.text(
            f'REVOKE ALL PRIVILEGES ({quoted_columns}) ON TABLE "{_REQUESTS_TABLE}" FROM PUBLIC'
        )
    )
    for role_name in (
        TENANT_APPLICATION_ROLE,
        PLATFORM_APPLICATION_ROLE,
        AUTHENTICATION_APPLICATION_ROLE,
        _IDENTITY_PROJECTION_ROLE,
        _EXECUTOR_ROLE,
    ):
        revoke_all_table_privileges(
            op,
            table_name=_REQUESTS_TABLE,
            role_name=role_name,
        )
        revoke_all_column_privileges(
            op,
            table_name=_REQUESTS_TABLE,
            role_name=role_name,
            column_names=_REQUEST_COLUMNS,
        )


def _reset_executor_acl(*, table_name: str, column_names: tuple[str, ...]) -> None:
    revoke_all_table_privileges(
        op,
        table_name=table_name,
        role_name=_EXECUTOR_ROLE,
    )
    revoke_all_column_privileges(
        op,
        table_name=table_name,
        role_name=_EXECUTOR_ROLE,
        column_names=column_names,
    )


def _create_executor_policy(
    *,
    table_name: str,
    policy_name: str,
    command: str,
) -> None:
    using = "tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid"
    with_check = f" WITH CHECK ({using})" if command in {"ALL", "UPDATE"} else ""
    op.execute(
        sa.text(
            f'CREATE POLICY "{policy_name}" ON "{table_name}" '
            f'AS PERMISSIVE FOR {command} TO "{_EXECUTOR_ROLE}" '
            f"USING ({using}){with_check}"
        )
    )


def _assert_executor_owner_is_private() -> None:
    op.execute(
        sa.text(
            f"""
            DO $p4e_executor_owner_preflight$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM pg_catalog.pg_roles
                    WHERE rolname = '{_EXECUTOR_ROLE}'
                      AND rolcanlogin = false
                      AND rolsuper = false
                      AND rolcreatedb = false
                      AND rolcreaterole = false
                      AND rolinherit = false
                      AND rolbypassrls = false
                      AND rolreplication = false
                ) THEN
                    RAISE EXCEPTION
                        'P4E executor preflight failed: private owner is missing or unsafe';
                END IF;

                IF EXISTS (
                    SELECT 1
                    FROM pg_catalog.pg_auth_members AS membership
                    JOIN pg_catalog.pg_roles AS owner_role
                      ON owner_role.oid = membership.member
                    WHERE owner_role.rolname = '{_EXECUTOR_ROLE}'
                ) OR EXISTS (
                    SELECT 1
                    FROM pg_catalog.pg_auth_members AS membership
                    JOIN pg_catalog.pg_roles AS owner_role
                      ON owner_role.oid = membership.roleid
                    JOIN pg_catalog.pg_roles AS member_role
                      ON member_role.oid = membership.member
                    WHERE owner_role.rolname = '{_EXECUTOR_ROLE}'
                      AND member_role.rolname <> current_user
                ) THEN
                    RAISE EXCEPTION
                        'P4E executor preflight failed: private owner membership is unsafe';
                END IF;
            END
            $p4e_executor_owner_preflight$
            """
        )
    )


def _create_command_binding_functions() -> None:
    _create_bind_function()
    _create_claim_function()
    _create_audit_function()
    for signature in (_BIND_SIGNATURE, _CLAIM_SIGNATURE, _AUDIT_SIGNATURE):
        op.execute(sa.text(f'ALTER FUNCTION {signature} OWNER TO "{_EXECUTOR_ROLE}"'))
        op.execute(sa.text(f"REVOKE ALL PRIVILEGES ON FUNCTION {signature} FROM PUBLIC"))
        for role_name in (
            TENANT_APPLICATION_ROLE,
            PLATFORM_APPLICATION_ROLE,
            AUTHENTICATION_APPLICATION_ROLE,
            _IDENTITY_PROJECTION_ROLE,
        ):
            op.execute(sa.text(f'REVOKE ALL PRIVILEGES ON FUNCTION {signature} FROM "{role_name}"'))

    op.execute(
        sa.text(
            f"""
            DO $p4e_gateway_binding_grants$
            DECLARE
                gateway_role record;
            BEGIN
                FOR gateway_role IN
                    SELECT DISTINCT member_role.rolname
                    FROM pg_catalog.pg_auth_members AS membership
                    JOIN pg_catalog.pg_roles AS capability_role
                      ON capability_role.oid = membership.roleid
                    JOIN pg_catalog.pg_roles AS member_role
                      ON member_role.oid = membership.member
                    WHERE capability_role.rolname = '{TENANT_APPLICATION_ROLE}'
                      AND member_role.rolcanlogin = true
                      AND member_role.rolsuper = false
                      AND member_role.rolbypassrls = false
                LOOP
                    EXECUTE format(
                        'GRANT USAGE ON SCHEMA {_COMMAND_SCHEMA} TO %I',
                        gateway_role.rolname
                    );
                    EXECUTE format(
                        'GRANT EXECUTE ON FUNCTION {_BIND_SIGNATURE} TO %I',
                        gateway_role.rolname
                    );
                END LOOP;
            END
            $p4e_gateway_binding_grants$
            """
        )
    )
    op.execute(sa.text(f'REVOKE CREATE ON SCHEMA "{_COMMAND_SCHEMA}" FROM "{_EXECUTOR_ROLE}"'))


def _drop_command_binding_functions() -> None:
    for signature in (_AUDIT_SIGNATURE, _CLAIM_SIGNATURE, _BIND_SIGNATURE):
        op.execute(sa.text(f"DROP FUNCTION IF EXISTS {signature}"))


def _create_bind_function() -> None:
    op.execute(
        sa.text(
            f"""
            CREATE FUNCTION {_COMMAND_SCHEMA}.{_BIND_FUNCTION}(
                requested_tenant_id uuid,
                requested_actor_user_id uuid,
                requested_membership_id uuid,
                requested_intent character varying,
                requested_target_id uuid,
                requested_audit_event_id uuid,
                requested_correlation_request_id character varying,
                requested_trace_id character varying,
                requested_session_id uuid
            ) RETURNS void
            LANGUAGE plpgsql
            SECURITY DEFINER
            SET search_path = pg_catalog, {_COMMAND_SCHEMA}, public
            AS $p4e_bind_database_command$
            DECLARE
                login_role record;
            BEGIN
                SELECT roles.rolcanlogin,
                       roles.rolsuper,
                       roles.rolbypassrls
                INTO login_role
                FROM pg_catalog.pg_roles AS roles
                WHERE roles.rolname = session_user;
                IF NOT FOUND
                   OR login_role.rolcanlogin = false
                   OR (
                       login_role.rolsuper = false
                       AND (
                           login_role.rolbypassrls = true
                           OR NOT pg_catalog.pg_has_role(
                               session_user,
                               '{TENANT_APPLICATION_ROLE}',
                               'SET'
                           )
                       )
                   ) THEN
                    RAISE EXCEPTION 'database command binding denied'
                        USING ERRCODE = '42501';
                END IF;

                IF requested_tenant_id IS NULL
                   OR requested_actor_user_id IS NULL
                   OR requested_membership_id IS NULL
                   OR requested_target_id IS NULL
                   OR requested_audit_event_id IS NULL
                   OR requested_tenant_id = '00000000-0000-0000-0000-000000000000'::uuid
                   OR requested_actor_user_id = '00000000-0000-0000-0000-000000000000'::uuid
                   OR requested_membership_id = '00000000-0000-0000-0000-000000000000'::uuid
                   OR requested_target_id = '00000000-0000-0000-0000-000000000000'::uuid
                   OR requested_audit_event_id = '00000000-0000-0000-0000-000000000000'::uuid
                   OR requested_intent IS NULL
                   OR requested_intent NOT IN (
                       'p4e_submit',
                       'p4e_cancel',
                       'p4e_approve',
                       'p4e_reject',
                       'p4b_personal_update'
                   )
                   OR requested_correlation_request_id IS NULL
                   OR length(requested_correlation_request_id) NOT BETWEEN 1 AND 128
                   OR requested_correlation_request_id !~
                       '^[A-Za-z0-9]$|^[A-Za-z0-9][A-Za-z0-9._-]{{0,126}}[A-Za-z0-9]$'
                   OR requested_trace_id IS NULL
                   OR requested_trace_id !~ '^[0-9a-f]{{32}}$'
                   OR requested_trace_id = repeat('0', 32)
                   OR requested_session_id =
                       '00000000-0000-0000-0000-000000000000'::uuid THEN
                    RAISE EXCEPTION 'database command binding invalid'
                        USING ERRCODE = '22023';
                END IF;

                PERFORM pg_catalog.set_config(
                    'app.tenant_id', requested_tenant_id::text, true
                );
                IF NOT public.is_current_tenant_membership_link_eligible(
                    requested_membership_id
                ) OR NOT EXISTS (
                    SELECT 1
                    FROM public.tenant_memberships AS memberships
                    WHERE memberships.tenant_id = requested_tenant_id
                      AND memberships.id = requested_membership_id
                      AND memberships.legacy_user_id = requested_actor_user_id
                ) THEN
                    RAISE EXCEPTION 'database command binding context invalid'
                        USING ERRCODE = '42501';
                END IF;

                -- Only rows committed before this statement are visible. The DELETE policy
                -- excludes this transaction, so its one-use binding remains an immutable
                -- tombstone until commit while old tombstones cannot accumulate indefinitely.
                DELETE FROM {_COMMAND_SCHEMA}.{_COMMAND_BINDINGS_TABLE} AS bindings
                WHERE (bindings.backend_pid, bindings.transaction_id) IN (
                    SELECT cleanup_candidates.backend_pid,
                           cleanup_candidates.transaction_id
                    FROM {_COMMAND_SCHEMA}.{_COMMAND_BINDINGS_TABLE}
                        AS cleanup_candidates
                    WHERE cleanup_candidates.transaction_id <> pg_current_xact_id()
                    FOR UPDATE OF cleanup_candidates SKIP LOCKED
                );

                BEGIN
                    INSERT INTO {_COMMAND_SCHEMA}.{_COMMAND_BINDINGS_TABLE} (
                        backend_pid,
                        transaction_id,
                        gateway_session_user,
                        tenant_id,
                        actor_user_id,
                        membership_id,
                        intent,
                        target_id,
                        audit_event_id,
                        correlation_request_id,
                        trace_id,
                        session_id,
                        state,
                        bound_at
                    ) VALUES (
                        pg_backend_pid(),
                        pg_current_xact_id(),
                        session_user,
                        requested_tenant_id,
                        requested_actor_user_id,
                        requested_membership_id,
                        requested_intent,
                        requested_target_id,
                        requested_audit_event_id,
                        requested_correlation_request_id,
                        requested_trace_id,
                        requested_session_id,
                        'bound',
                        clock_timestamp()
                    );
                EXCEPTION WHEN unique_violation THEN
                    RAISE EXCEPTION 'database command already bound'
                        USING ERRCODE = '55000';
                END;
            END
            $p4e_bind_database_command$
            """
        )
    )


def _create_claim_function() -> None:
    op.execute(
        sa.text(
            f"""
            CREATE FUNCTION {_COMMAND_SCHEMA}.{_CLAIM_FUNCTION}(
                expected_intent character varying,
                expected_target_id uuid
            ) RETURNS TABLE (
                bound_tenant_id uuid,
                bound_actor_user_id uuid,
                bound_membership_id uuid
            )
            LANGUAGE plpgsql
            SECURITY DEFINER
            SET search_path = pg_catalog, {_COMMAND_SCHEMA}, public
            AS $p4e_claim_database_command$
            DECLARE
                claimed_binding record;
            BEGIN
                UPDATE {_COMMAND_SCHEMA}.{_COMMAND_BINDINGS_TABLE} AS bindings
                SET state = 'executed',
                    executed_at = clock_timestamp()
                WHERE bindings.backend_pid = pg_backend_pid()
                  AND bindings.transaction_id = pg_current_xact_id()
                  AND bindings.gateway_session_user = session_user
                  AND bindings.state = 'bound'
                  AND bindings.intent = expected_intent
                  AND bindings.target_id = expected_target_id
                RETURNING bindings.tenant_id,
                          bindings.actor_user_id,
                          bindings.membership_id
                INTO claimed_binding;
                IF NOT FOUND THEN
                    RETURN;
                END IF;

                PERFORM pg_catalog.set_config(
                    'app.tenant_id', claimed_binding.tenant_id::text, true
                );
                PERFORM pg_catalog.set_config(
                    'app.actor_id', claimed_binding.actor_user_id::text, true
                );
                PERFORM pg_catalog.set_config(
                    'app.membership_id', claimed_binding.membership_id::text, true
                );
                bound_tenant_id := claimed_binding.tenant_id;
                bound_actor_user_id := claimed_binding.actor_user_id;
                bound_membership_id := claimed_binding.membership_id;
                RETURN NEXT;
            END
            $p4e_claim_database_command$
            """
        )
    )


def _create_audit_function() -> None:
    op.execute(
        sa.text(
            f"""
            CREATE FUNCTION {_COMMAND_SCHEMA}.{_AUDIT_FUNCTION}()
            RETURNS void
            LANGUAGE plpgsql
            SECURITY DEFINER
            SET search_path = pg_catalog, {_COMMAND_SCHEMA}, public
            AS $p4e_write_change_request_audit$
            DECLARE
                command_binding record;
                request_row record;
                audit_event_type character varying;
                audit_action character varying;
                before_status character varying;
                after_status character varying;
                reason_code character varying;
                changed_field_names text[];
                audit_timestamp timestamptz;
            BEGIN
                SELECT bindings.*
                INTO command_binding
                FROM {_COMMAND_SCHEMA}.{_COMMAND_BINDINGS_TABLE} AS bindings
                WHERE bindings.backend_pid = pg_backend_pid()
                  AND bindings.transaction_id = pg_current_xact_id()
                  AND bindings.gateway_session_user = session_user
                  AND bindings.state = 'executed'
                  AND bindings.intent IN (
                      'p4e_submit',
                      'p4e_cancel',
                      'p4e_approve',
                      'p4e_reject'
                  )
                  AND bindings.audit_written_at IS NULL
                FOR UPDATE OF bindings;
                IF NOT FOUND THEN
                    RAISE EXCEPTION 'profile-change audit binding unavailable'
                        USING ERRCODE = '55000';
                END IF;

                SELECT requests.employee_id,
                       requests.preferred_name_changed,
                       requests.phone_changed,
                       requests.birth_date_changed
                INTO request_row
                FROM public.employee_profile_change_requests AS requests
                WHERE requests.tenant_id = command_binding.tenant_id
                  AND requests.id = command_binding.target_id;
                IF NOT FOUND THEN
                    RAISE EXCEPTION 'profile-change audit resource unavailable'
                        USING ERRCODE = '55000';
                END IF;

                changed_field_names := array_remove(
                    ARRAY[
                        CASE WHEN request_row.preferred_name_changed
                            THEN 'preferred_name' END,
                        CASE WHEN request_row.phone_changed THEN 'phone' END,
                        CASE WHEN request_row.birth_date_changed THEN 'birth_date' END
                    ]::text[],
                    NULL
                );
                CASE command_binding.intent
                    WHEN 'p4e_submit' THEN
                        audit_event_type := 'employee.profile_change_request.submitted';
                        audit_action := 'submit_profile_change_request';
                        before_status := 'none';
                        after_status := 'submitted';
                        reason_code := 'employee_submitted';
                    WHEN 'p4e_cancel' THEN
                        audit_event_type := 'employee.profile_change_request.cancelled';
                        audit_action := 'cancel_profile_change_request';
                        before_status := 'submitted';
                        after_status := 'cancelled';
                        reason_code := 'employee_cancelled';
                    WHEN 'p4e_approve' THEN
                        audit_event_type := 'employee.profile_change_request.approved';
                        audit_action := 'approve_profile_change_request';
                        before_status := 'submitted';
                        after_status := 'approved';
                        reason_code := 'hr_approved';
                    WHEN 'p4e_reject' THEN
                        audit_event_type := 'employee.profile_change_request.rejected';
                        audit_action := 'reject_profile_change_request';
                        before_status := 'submitted';
                        after_status := 'rejected';
                        reason_code := 'hr_rejected';
                    ELSE
                        RAISE EXCEPTION 'profile-change audit intent invalid'
                            USING ERRCODE = '55000';
                END CASE;

                audit_timestamp := clock_timestamp();
                INSERT INTO public.audit_events (
                    id,
                    occurred_at,
                    scope_type,
                    tenant_id,
                    actor_type,
                    actor_user_id,
                    impersonator_user_id,
                    event_type,
                    category,
                    severity,
                    resource_type,
                    resource_id,
                    action,
                    result,
                    request_id,
                    trace_id,
                    session_id,
                    ip_address,
                    user_agent,
                    reason,
                    support_ticket_id,
                    changed_fields,
                    before_data,
                    after_data,
                    metadata,
                    data_classification,
                    visibility_class,
                    integrity_hash
                ) VALUES (
                    command_binding.audit_event_id,
                    audit_timestamp,
                    'tenant',
                    command_binding.tenant_id,
                    'user',
                    command_binding.actor_user_id,
                    NULL,
                    audit_event_type,
                    'hr_operations',
                    'info',
                    'employee_profile_change_request',
                    command_binding.target_id,
                    audit_action,
                    'success',
                    command_binding.correlation_request_id,
                    command_binding.trace_id,
                    command_binding.session_id,
                    NULL,
                    NULL,
                    NULL,
                    NULL,
                    to_jsonb(changed_field_names),
                    '{{}}'::jsonb,
                    '{{}}'::jsonb,
                    jsonb_build_object(
                        'request_id', command_binding.target_id,
                        'employee_id', request_row.employee_id,
                        'before_request_status', before_status,
                        'after_request_status', after_status,
                        'reason_code', reason_code
                    ),
                    'hr_metadata',
                    'hr_operations',
                    NULL
                );

                UPDATE {_COMMAND_SCHEMA}.{_COMMAND_BINDINGS_TABLE} AS bindings
                SET audit_written_at = audit_timestamp
                WHERE bindings.backend_pid = pg_backend_pid()
                  AND bindings.transaction_id = pg_current_xact_id()
                  AND bindings.gateway_session_user = session_user;
            END
            $p4e_write_change_request_audit$
            """
        )
    )


def _create_command_functions() -> None:
    _create_submit_function()
    _create_transition_function()
    _create_personal_update_function()
    op.execute(
        sa.text(
            f"""
            DO $p4e_public_create_preflight$
            BEGIN
                IF pg_catalog.has_schema_privilege(
                    '{_EXECUTOR_ROLE}', 'public', 'CREATE'
                ) THEN
                    RAISE EXCEPTION
                        'P4E executor preflight failed: unexpected public CREATE privilege';
                END IF;
            END
            $p4e_public_create_preflight$
            """
        )
    )
    op.execute(sa.text(f'GRANT CREATE ON SCHEMA public TO "{_EXECUTOR_ROLE}"'))
    for signature in (
        _SUBMIT_SIGNATURE,
        _TRANSITION_SIGNATURE,
        _PERSONAL_UPDATE_SIGNATURE,
    ):
        op.execute(sa.text(f'ALTER FUNCTION {signature} OWNER TO "{_EXECUTOR_ROLE}"'))
        op.execute(sa.text(f"REVOKE ALL PRIVILEGES ON FUNCTION {signature} FROM PUBLIC"))
        for role_name in (
            TENANT_APPLICATION_ROLE,
            PLATFORM_APPLICATION_ROLE,
            AUTHENTICATION_APPLICATION_ROLE,
            _IDENTITY_PROJECTION_ROLE,
        ):
            op.execute(sa.text(f'REVOKE ALL PRIVILEGES ON FUNCTION {signature} FROM "{role_name}"'))
        op.execute(sa.text(f'GRANT EXECUTE ON FUNCTION {signature} TO "{TENANT_APPLICATION_ROLE}"'))
    op.execute(sa.text(f'REVOKE CREATE ON SCHEMA public FROM "{_EXECUTOR_ROLE}"'))


def _drop_command_functions() -> None:
    for signature in (
        _PERSONAL_UPDATE_SIGNATURE,
        _TRANSITION_SIGNATURE,
        _SUBMIT_SIGNATURE,
    ):
        op.execute(
            sa.text(f'REVOKE EXECUTE ON FUNCTION {signature} FROM "{TENANT_APPLICATION_ROLE}"')
        )
        op.execute(sa.text(f"DROP FUNCTION IF EXISTS {signature}"))


def _create_submit_function() -> None:
    op.execute(
        sa.text(
            f"""
            CREATE FUNCTION public.{_SUBMIT_FUNCTION}(
                requested_request_id uuid,
                requested_preferred_name_changed boolean,
                requested_preferred_name character varying,
                requested_phone_changed boolean,
                requested_phone character varying,
                requested_birth_date_changed boolean,
                requested_birth_date date
            ) RETURNS text
            LANGUAGE plpgsql
            SECURITY DEFINER
            SET search_path = pg_catalog, {_COMMAND_SCHEMA}, public
            AS $p4e_submit$
            DECLARE
                current_tenant_id uuid;
                current_actor_id uuid;
                current_membership_id uuid;
                target_employee_id uuid;
                current_profile_version integer;
                current_preferred_name character varying;
                current_phone character varying;
                current_birth_date date;
                normalized_current_preferred_name character varying;
                normalized_current_phone character varying;
                inserted_request_id uuid;
                submitted_at_value timestamptz;
            BEGIN
                SELECT claimed.bound_tenant_id,
                       claimed.bound_actor_user_id,
                       claimed.bound_membership_id
                INTO current_tenant_id,
                     current_actor_id,
                     current_membership_id
                FROM {_COMMAND_SCHEMA}.{_CLAIM_FUNCTION}(
                    'p4e_submit', requested_request_id
                ) AS claimed;
                IF NOT FOUND THEN
                    RETURN 'context_invalid';
                END IF;
                IF current_tenant_id IS NULL OR current_actor_id IS NULL
                   OR current_membership_id IS NULL
                   OR current_tenant_id = '00000000-0000-0000-0000-000000000000'::uuid
                   OR current_actor_id = '00000000-0000-0000-0000-000000000000'::uuid
                   OR current_membership_id = '00000000-0000-0000-0000-000000000000'::uuid
                   OR requested_request_id IS NULL
                   OR requested_request_id = '00000000-0000-0000-0000-000000000000'::uuid
                   OR NOT public.is_current_tenant_membership_link_eligible(
                       current_membership_id
                   ) THEN
                    RETURN 'context_invalid';
                END IF;

                IF requested_preferred_name_changed IS NULL
                   OR requested_phone_changed IS NULL
                   OR requested_birth_date_changed IS NULL
                   OR NOT (
                       requested_preferred_name_changed
                       OR requested_phone_changed
                       OR requested_birth_date_changed
                   )
                   OR (
                       NOT requested_preferred_name_changed
                       AND requested_preferred_name IS NOT NULL
                   )
                   OR (
                       requested_preferred_name_changed
                       AND requested_preferred_name IS NOT NULL
                       AND (
                           length(requested_preferred_name) = 0
                           OR length(requested_preferred_name) > 200
                           OR regexp_replace(
                               btrim(requested_preferred_name),
                               '[[:space:]]+', ' ', 'g'
                           ) <> requested_preferred_name
                           OR position('*' in requested_preferred_name) > 0
                           OR position('•' in requested_preferred_name) > 0
                           OR position('●' in requested_preferred_name) > 0
                           OR position('·' in requested_preferred_name) > 0
                           OR position('▪' in requested_preferred_name) > 0
                           OR position('◦' in requested_preferred_name) > 0
                       )
                   )
                   OR (NOT requested_phone_changed AND requested_phone IS NOT NULL)
                   OR (
                       requested_phone_changed
                       AND requested_phone IS NOT NULL
                       AND requested_phone !~ '^\\+?[0-9]{{7,15}}$'
                   )
                   OR (
                       NOT requested_birth_date_changed
                       AND requested_birth_date IS NOT NULL
                   ) THEN
                    RETURN 'invalid_request';
                END IF;

                SELECT links.employee_id
                INTO target_employee_id
                FROM public.employee_account_links AS links
                JOIN public.employees AS employees
                  ON employees.tenant_id = links.tenant_id
                 AND employees.id = links.employee_id
                JOIN public.tenant_memberships AS memberships
                  ON memberships.tenant_id = links.tenant_id
                 AND memberships.id = links.membership_id
                WHERE links.tenant_id = current_tenant_id
                  AND links.membership_id = current_membership_id
                  AND memberships.legacy_user_id = current_actor_id
                  AND employees.archived_at IS NULL;
                IF NOT FOUND THEN
                    RETURN 'profile_unavailable';
                END IF;

                -- Avoid profile/request lock inversion with approval. The partial unique index
                -- remains the final concurrent-submit authority after this non-locking fast path.
                IF EXISTS (
                    SELECT 1
                    FROM public.employee_profile_change_requests AS active_requests
                    WHERE active_requests.tenant_id = current_tenant_id
                      AND active_requests.employee_id = target_employee_id
                      AND active_requests.status = 'submitted'
                ) THEN
                    RETURN 'active_request_exists';
                END IF;

                SELECT profiles.version,
                       profiles.preferred_name,
                       profiles.phone,
                       profiles.birth_date
                INTO current_profile_version,
                     current_preferred_name,
                     current_phone,
                     current_birth_date
                FROM public.employee_profiles AS profiles
                WHERE profiles.tenant_id = current_tenant_id
                  AND profiles.employee_id = target_employee_id
                FOR UPDATE OF profiles;
                IF NOT FOUND THEN
                    RETURN 'profile_unavailable';
                END IF;

                normalized_current_preferred_name := CASE
                    WHEN current_preferred_name IS NULL THEN NULL
                    ELSE regexp_replace(
                        btrim(current_preferred_name), '[[:space:]]+', ' ', 'g'
                    )
                END;
                normalized_current_phone := CASE
                    WHEN current_phone IS NULL THEN NULL
                    WHEN btrim(current_phone) ~ '^\\+?[0-9 ()-]+$'
                         AND length(
                             regexp_replace(btrim(current_phone), '[^0-9]', '', 'g')
                         ) BETWEEN 7 AND 15
                    THEN CASE WHEN left(btrim(current_phone), 1) = '+'
                        THEN '+' ELSE '' END
                        || regexp_replace(btrim(current_phone), '[^0-9]', '', 'g')
                    ELSE btrim(current_phone)
                END;

                IF (
                    requested_preferred_name_changed
                    AND requested_preferred_name IS NOT DISTINCT FROM
                        normalized_current_preferred_name
                ) OR (
                    requested_phone_changed
                    AND requested_phone IS NOT DISTINCT FROM normalized_current_phone
                ) OR (
                    requested_birth_date_changed
                    AND requested_birth_date IS NOT DISTINCT FROM current_birth_date
                ) THEN
                    RETURN 'invalid_request';
                END IF;

                submitted_at_value := clock_timestamp();
                BEGIN
                    INSERT INTO public.employee_profile_change_requests (
                        id,
                        tenant_id,
                        employee_id,
                        requester_membership_id,
                        requester_user_id,
                        status,
                        version,
                        base_profile_version,
                        preferred_name_changed,
                        previous_preferred_name,
                        proposed_preferred_name,
                        phone_changed,
                        previous_phone,
                        proposed_phone,
                        birth_date_changed,
                        previous_birth_date,
                        proposed_birth_date,
                        submitted_at,
                        created_at,
                        updated_at
                    ) VALUES (
                        requested_request_id,
                        current_tenant_id,
                        target_employee_id,
                        current_membership_id,
                        current_actor_id,
                        'submitted',
                        1,
                        current_profile_version,
                        requested_preferred_name_changed,
                        CASE WHEN requested_preferred_name_changed
                            THEN current_preferred_name ELSE NULL END,
                        CASE WHEN requested_preferred_name_changed
                            THEN requested_preferred_name ELSE NULL END,
                        requested_phone_changed,
                        CASE WHEN requested_phone_changed THEN current_phone ELSE NULL END,
                        CASE WHEN requested_phone_changed THEN requested_phone ELSE NULL END,
                        requested_birth_date_changed,
                        CASE WHEN requested_birth_date_changed
                            THEN current_birth_date ELSE NULL END,
                        CASE WHEN requested_birth_date_changed
                            THEN requested_birth_date ELSE NULL END,
                        submitted_at_value,
                        submitted_at_value,
                        submitted_at_value
                    )
                    ON CONFLICT (tenant_id, employee_id)
                        WHERE status = 'submitted'
                    DO NOTHING
                    RETURNING id INTO inserted_request_id;
                EXCEPTION WHEN unique_violation THEN
                    RETURN 'invalid_request';
                END;
                IF inserted_request_id IS NULL THEN
                    RETURN 'active_request_exists';
                END IF;
                PERFORM {_COMMAND_SCHEMA}.{_AUDIT_FUNCTION}();
                RETURN 'submitted';
            END
            $p4e_submit$
            """
        )
    )


def _create_transition_function() -> None:
    op.execute(
        sa.text(
            f"""
            CREATE FUNCTION public.{_TRANSITION_FUNCTION}(
                requested_request_id uuid,
                expected_request_version integer,
                requested_action character varying,
                requested_rejection_reason character varying
            ) RETURNS text
            LANGUAGE plpgsql
            SECURITY DEFINER
            SET search_path = pg_catalog, {_COMMAND_SCHEMA}, public
            AS $p4e_transition$
            DECLARE
                current_tenant_id uuid;
                current_actor_id uuid;
                current_membership_id uuid;
                request_row public.employee_profile_change_requests%ROWTYPE;
                current_profile_id uuid;
                current_profile_version integer;
                current_preferred_name character varying;
                current_phone character varying;
                current_birth_date date;
                transition_at timestamptz;
                granted_permission_count integer;
                expected_intent character varying;
            BEGIN
                IF requested_request_id IS NULL
                   OR expected_request_version IS NULL
                   OR expected_request_version < 1
                   OR requested_action IS NULL
                   OR requested_action NOT IN ('approve', 'reject', 'cancel') THEN
                    RETURN 'context_invalid';
                END IF;
                expected_intent := CASE requested_action
                    WHEN 'approve' THEN 'p4e_approve'
                    WHEN 'reject' THEN 'p4e_reject'
                    WHEN 'cancel' THEN 'p4e_cancel'
                END;
                SELECT claimed.bound_tenant_id,
                       claimed.bound_actor_user_id,
                       claimed.bound_membership_id
                INTO current_tenant_id,
                     current_actor_id,
                     current_membership_id
                FROM {_COMMAND_SCHEMA}.{_CLAIM_FUNCTION}(
                    expected_intent, requested_request_id
                ) AS claimed;
                IF NOT FOUND THEN
                    RETURN 'context_invalid';
                END IF;
                IF current_tenant_id IS NULL OR current_actor_id IS NULL
                   OR current_membership_id IS NULL
                   OR NOT public.is_current_tenant_membership_link_eligible(
                       current_membership_id
                   )
                   OR NOT EXISTS (
                       SELECT 1
                       FROM public.tenant_memberships AS memberships
                       WHERE memberships.tenant_id = current_tenant_id
                         AND memberships.id = current_membership_id
                         AND memberships.legacy_user_id = current_actor_id
                   ) THEN
                    RETURN 'context_invalid';
                END IF;

                IF requested_action = 'cancel' THEN
                    IF requested_rejection_reason IS NOT NULL THEN
                        RETURN 'invalid_request';
                    END IF;
                ELSE
                    IF requested_action = 'reject' THEN
                        IF requested_rejection_reason IS NULL
                           OR length(btrim(requested_rejection_reason)) = 0
                           OR length(requested_rejection_reason) > 500
                           OR regexp_replace(
                               btrim(requested_rejection_reason),
                               '[[:space:]]+', ' ', 'g'
                           ) <> requested_rejection_reason THEN
                            RETURN 'invalid_request';
                        END IF;
                    ELSIF requested_rejection_reason IS NOT NULL THEN
                        RETURN 'invalid_request';
                    END IF;

                    SELECT count(DISTINCT permissions.code)::integer
                    INTO granted_permission_count
                    FROM public.membership_roles AS membership_roles
                    JOIN public.role_permissions AS role_permissions
                      ON role_permissions.role_id = membership_roles.role_id
                    JOIN public.permissions AS permissions
                      ON permissions.id = role_permissions.permission_id
                    WHERE membership_roles.tenant_id = current_tenant_id
                      AND membership_roles.membership_id = current_membership_id
                      AND membership_roles.active = true
                      AND permissions.code IN (
                          'employee:read:tenant',
                          'employee:update:tenant'
                      );
                    IF granted_permission_count <> 2 THEN
                        RETURN 'access_denied';
                    END IF;
                END IF;

                IF requested_action = 'cancel' THEN
                    SELECT requests.* INTO request_row
                    FROM public.employee_profile_change_requests AS requests
                    WHERE requests.tenant_id = current_tenant_id
                      AND requests.id = requested_request_id
                      AND requests.requester_membership_id = current_membership_id
                      AND requests.requester_user_id = current_actor_id
                      AND EXISTS (
                          SELECT 1
                          FROM public.employee_account_links AS links
                          JOIN public.employees AS employees
                            ON employees.tenant_id = links.tenant_id
                           AND employees.id = links.employee_id
                          WHERE links.tenant_id = current_tenant_id
                            AND links.employee_id = requests.employee_id
                            AND links.membership_id = current_membership_id
                            AND employees.archived_at IS NULL
                      )
                    FOR UPDATE OF requests;
                ELSE
                    SELECT requests.* INTO request_row
                    FROM public.employee_profile_change_requests AS requests
                    WHERE requests.tenant_id = current_tenant_id
                      AND requests.id = requested_request_id
                    FOR UPDATE OF requests;
                END IF;
                IF NOT FOUND THEN
                    RETURN 'not_found';
                END IF;

                IF request_row.status <> 'submitted'
                   OR request_row.version <> expected_request_version THEN
                    RETURN 'version_conflict';
                END IF;

                transition_at := clock_timestamp();
                IF requested_action = 'cancel' THEN
                    UPDATE public.employee_profile_change_requests
                    SET status = 'cancelled',
                        cancelled_at = transition_at,
                        version = version + 1,
                        updated_at = transition_at
                    WHERE tenant_id = current_tenant_id
                      AND id = requested_request_id;
                    PERFORM {_COMMAND_SCHEMA}.{_AUDIT_FUNCTION}();
                    RETURN 'cancelled';
                END IF;

                IF requested_action = 'reject' THEN
                    UPDATE public.employee_profile_change_requests
                    SET status = 'rejected',
                        decided_at = transition_at,
                        decided_by_membership_id = current_membership_id,
                        decided_by_user_id = current_actor_id,
                        rejection_reason = requested_rejection_reason,
                        version = version + 1,
                        updated_at = transition_at
                    WHERE tenant_id = current_tenant_id
                      AND id = requested_request_id;
                    PERFORM {_COMMAND_SCHEMA}.{_AUDIT_FUNCTION}();
                    RETURN 'rejected';
                END IF;

                SELECT profiles.id,
                       profiles.version,
                       profiles.preferred_name,
                       profiles.phone,
                       profiles.birth_date
                INTO current_profile_id,
                     current_profile_version,
                     current_preferred_name,
                     current_phone,
                     current_birth_date
                FROM public.employee_profiles AS profiles
                WHERE profiles.tenant_id = current_tenant_id
                  AND profiles.employee_id = request_row.employee_id
                FOR UPDATE OF profiles;
                IF NOT FOUND
                   OR current_profile_version <> request_row.base_profile_version
                   OR (
                       request_row.preferred_name_changed
                       AND current_preferred_name IS DISTINCT FROM
                           request_row.previous_preferred_name
                   )
                   OR (
                       request_row.phone_changed
                       AND current_phone IS DISTINCT FROM request_row.previous_phone
                   )
                   OR (
                       request_row.birth_date_changed
                       AND current_birth_date IS DISTINCT FROM request_row.previous_birth_date
                   ) THEN
                    RETURN 'profile_conflict';
                END IF;

                UPDATE public.employee_profiles
                SET preferred_name = CASE WHEN request_row.preferred_name_changed
                        THEN request_row.proposed_preferred_name ELSE preferred_name END,
                    phone = CASE WHEN request_row.phone_changed
                        THEN request_row.proposed_phone ELSE phone END,
                    birth_date = CASE WHEN request_row.birth_date_changed
                        THEN request_row.proposed_birth_date ELSE birth_date END,
                    version = version + 1,
                    updated_at = transition_at
                WHERE tenant_id = current_tenant_id
                  AND id = current_profile_id;

                UPDATE public.employee_profile_change_requests
                SET status = 'approved',
                    decided_at = transition_at,
                    decided_by_membership_id = current_membership_id,
                    decided_by_user_id = current_actor_id,
                    version = version + 1,
                    updated_at = transition_at
                WHERE tenant_id = current_tenant_id
                  AND id = requested_request_id;
                PERFORM {_COMMAND_SCHEMA}.{_AUDIT_FUNCTION}();
                RETURN 'approved';
            END
            $p4e_transition$
            """
        )
    )


def _create_personal_update_function() -> None:
    op.execute(
        sa.text(
            f"""
            CREATE FUNCTION public.{_PERSONAL_UPDATE_FUNCTION}(
                requested_employee_id uuid,
                expected_profile_version integer,
                requested_preferred_name_changed boolean,
                requested_preferred_name character varying,
                requested_phone_changed boolean,
                requested_phone character varying,
                requested_birth_date_changed boolean,
                requested_birth_date date
            ) RETURNS text
            LANGUAGE plpgsql
            SECURITY DEFINER
            SET search_path = pg_catalog, {_COMMAND_SCHEMA}, public
            AS $p4e_personal_update$
            DECLARE
                current_tenant_id uuid;
                current_actor_id uuid;
                current_membership_id uuid;
                current_profile_id uuid;
                current_profile_version integer;
                current_preferred_name character varying;
                current_phone character varying;
                current_birth_date date;
                granted_permission_count integer;
            BEGIN
                SELECT claimed.bound_tenant_id,
                       claimed.bound_actor_user_id,
                       claimed.bound_membership_id
                INTO current_tenant_id,
                     current_actor_id,
                     current_membership_id
                FROM {_COMMAND_SCHEMA}.{_CLAIM_FUNCTION}(
                    'p4b_personal_update', requested_employee_id
                ) AS claimed;
                IF NOT FOUND THEN
                    RETURN 'context_invalid';
                END IF;
                IF current_tenant_id IS NULL OR current_actor_id IS NULL
                   OR current_membership_id IS NULL
                   OR requested_employee_id IS NULL
                   OR expected_profile_version IS NULL
                   OR expected_profile_version < 1
                   OR requested_preferred_name_changed IS NULL
                   OR requested_phone_changed IS NULL
                   OR requested_birth_date_changed IS NULL
                   OR NOT public.is_current_tenant_membership_link_eligible(
                       current_membership_id
                   )
                   OR NOT EXISTS (
                       SELECT 1
                       FROM public.tenant_memberships AS memberships
                       WHERE memberships.tenant_id = current_tenant_id
                         AND memberships.id = current_membership_id
                         AND memberships.legacy_user_id = current_actor_id
                   ) THEN
                    RETURN 'context_invalid';
                END IF;

                SELECT count(DISTINCT permissions.code)::integer
                INTO granted_permission_count
                FROM public.membership_roles AS membership_roles
                JOIN public.role_permissions AS role_permissions
                  ON role_permissions.role_id = membership_roles.role_id
                JOIN public.permissions AS permissions
                  ON permissions.id = role_permissions.permission_id
                WHERE membership_roles.tenant_id = current_tenant_id
                  AND membership_roles.membership_id = current_membership_id
                  AND membership_roles.active = true
                  AND permissions.code = 'employee:update:tenant';
                IF granted_permission_count <> 1 THEN
                    RETURN 'access_denied';
                END IF;

                IF (
                    NOT requested_preferred_name_changed
                    AND requested_preferred_name IS NOT NULL
                ) OR (
                    requested_preferred_name_changed
                    AND requested_preferred_name IS NOT NULL
                    AND (
                        length(requested_preferred_name) = 0
                        OR length(requested_preferred_name) > 200
                        OR btrim(requested_preferred_name) <> requested_preferred_name
                    )
                ) OR (
                    NOT requested_phone_changed
                    AND requested_phone IS NOT NULL
                ) OR (
                    requested_phone_changed
                    AND requested_phone IS NOT NULL
                    AND (
                        length(requested_phone) = 0
                        OR length(requested_phone) > 32
                        OR btrim(requested_phone) <> requested_phone
                    )
                ) OR (
                    NOT requested_birth_date_changed
                    AND requested_birth_date IS NOT NULL
                ) THEN
                    RETURN 'invalid_request';
                END IF;

                SELECT profiles.id,
                       profiles.version,
                       profiles.preferred_name,
                       profiles.phone,
                       profiles.birth_date
                INTO current_profile_id,
                     current_profile_version,
                     current_preferred_name,
                     current_phone,
                     current_birth_date
                FROM public.employee_profiles AS profiles
                JOIN public.employees AS employees
                  ON employees.tenant_id = profiles.tenant_id
                 AND employees.id = profiles.employee_id
                WHERE profiles.tenant_id = current_tenant_id
                  AND profiles.employee_id = requested_employee_id
                  AND employees.archived_at IS NULL
                FOR UPDATE OF profiles;
                IF NOT FOUND THEN
                    RETURN 'not_found';
                END IF;
                IF current_profile_version <> expected_profile_version THEN
                    RETURN 'version_conflict';
                END IF;
                IF (
                    requested_preferred_name_changed
                    AND requested_preferred_name IS NOT DISTINCT FROM current_preferred_name
                ) OR (
                    requested_phone_changed
                    AND requested_phone IS NOT DISTINCT FROM current_phone
                ) OR (
                    requested_birth_date_changed
                    AND requested_birth_date IS NOT DISTINCT FROM current_birth_date
                ) THEN
                    RETURN 'invalid_request';
                END IF;

                UPDATE public.employee_profiles
                SET preferred_name = CASE WHEN requested_preferred_name_changed
                        THEN requested_preferred_name ELSE preferred_name END,
                    phone = CASE WHEN requested_phone_changed
                        THEN requested_phone ELSE phone END,
                    birth_date = CASE WHEN requested_birth_date_changed
                        THEN requested_birth_date ELSE birth_date END,
                    version = version + 1,
                    updated_at = clock_timestamp()
                WHERE tenant_id = current_tenant_id
                  AND id = current_profile_id;
                RETURN 'updated';
            END
            $p4e_personal_update$
            """
        )
    )


__all__ = ["revision", "down_revision", "upgrade", "downgrade"]
