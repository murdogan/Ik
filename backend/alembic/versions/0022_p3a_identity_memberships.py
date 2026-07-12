"""add the P3A global identity and tenant-membership expand foundation

Revision ID: 0022_p3a_identity_memberships
Revises: 0021_f2f_user_insert_grant
Create Date: 2026-07-12
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
    revoke_all_column_privileges,
    revoke_all_table_privileges,
)
from app.platform.db.tenant_access import (
    PLATFORM_APPLICATION_ROLE,
    TENANT_APPLICATION_ROLE,
)
from sqlalchemy.dialects import postgresql

revision: str = "0022_p3a_identity_memberships"
down_revision: str | None = "0021_f2f_user_insert_grant"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_IDENTITIES_TABLE = "identities"
_MEMBERSHIPS_TABLE = "tenant_memberships"
_MEMBERSHIP_ROLES_TABLE = "membership_roles"
_USERS_TABLE = "users"
_USER_ROLES_TABLE = "user_roles"
_TENANT_POLICY = "tenant_isolation_app"

_IDENTITY_COLUMNS = (
    "id",
    "email",
    "email_normalized",
    "status",
    "password_hash",
    "created_at",
    "updated_at",
)
_MEMBERSHIP_COLUMNS = (
    "id",
    "tenant_id",
    "identity_id",
    "legacy_user_id",
    "full_name",
    "status",
    "permission_version",
    "created_at",
    "updated_at",
)
_MEMBERSHIP_ROLE_COLUMNS = (
    "tenant_id",
    "membership_id",
    "role_id",
    "role_scope_type",
    "active",
    "created_at",
    "updated_at",
)

_RANKED_USERS_CTE = """
ranked_users as (
    select
        users.id,
        users.tenant_id,
        users.email,
        users.email_normalized,
        users.full_name,
        users.status,
        users.permission_version,
        users.created_at,
        users.updated_at,
        row_number() over (
            partition by users.email_normalized
            order by users.id
        ) as canonical_rank,
        max(users.password_hash) over (
            partition by users.email_normalized
        ) as identity_password_hash,
        min(users.created_at) over (
            partition by users.email_normalized
        ) as identity_created_at,
        max(users.updated_at) over (
            partition by users.email_normalized
        ) as identity_updated_at
    from users
)
"""


def upgrade() -> None:
    is_postgresql = op.get_bind().dialect.name == "postgresql"
    if is_postgresql:
        # Both legacy sources are FORCE RLS tables. The migration owner must see every tenant in
        # one deterministic projection; transaction-per-revision restores the flags on failure.
        disable_forced_row_security(op, table_name=_USERS_TABLE)
        disable_forced_row_security(op, table_name=_USER_ROLES_TABLE)

    _assert_legacy_credentials_are_mergeable()
    _create_identities_table()
    _create_memberships_table()
    _create_membership_roles_table()
    _backfill_identities()
    _backfill_memberships()
    _backfill_membership_roles()
    _assert_backfill_complete()

    if is_postgresql:
        enable_forced_row_security(op, table_name=_USERS_TABLE)
        enable_forced_row_security(op, table_name=_USER_ROLES_TABLE)
        _configure_postgresql_security()


def downgrade() -> None:
    is_postgresql = op.get_bind().dialect.name == "postgresql"
    if is_postgresql:
        # Application rollback remains possible because P3A never removes the legacy projection.
        # Schema rollback is allowed only while all new rows are still exactly reproducible from
        # that projection. Any canonical write must be repaired forward instead of discarded.
        for table_name in (
            _USERS_TABLE,
            _USER_ROLES_TABLE,
            _IDENTITIES_TABLE,
            _MEMBERSHIPS_TABLE,
            _MEMBERSHIP_ROLES_TABLE,
        ):
            disable_forced_row_security(op, table_name=table_name)

    _assert_downgrade_projection_is_reproducible()

    if is_postgresql:
        drop_policy(
            op,
            table_name=_MEMBERSHIP_ROLES_TABLE,
            policy_name=_TENANT_POLICY,
        )
        drop_policy(
            op,
            table_name=_MEMBERSHIPS_TABLE,
            policy_name=_TENANT_POLICY,
        )

    op.drop_table(_MEMBERSHIP_ROLES_TABLE)
    op.drop_table(_MEMBERSHIPS_TABLE)
    op.drop_table(_IDENTITIES_TABLE)

    if is_postgresql:
        enable_forced_row_security(op, table_name=_USER_ROLES_TABLE)
        enable_forced_row_security(op, table_name=_USERS_TABLE)


def _assert_legacy_credentials_are_mergeable() -> None:
    conflict_count_sql = _conflicting_password_count_sql()
    blank_count_sql = _blank_normalized_email_count_sql()

    if op.get_context().as_sql:
        op.execute(
            sa.text(
                f"""
                DO $p3a_identity_backfill_preflight$
                DECLARE
                    conflict_count bigint;
                    blank_count bigint;
                BEGIN
                    conflict_count := ({conflict_count_sql});
                    blank_count := ({blank_count_sql});
                    IF conflict_count > 0 OR blank_count > 0 THEN
                        RAISE EXCEPTION
                            'P3A identity backfill preflight failed: '
                            'conflicting_password_identities=%, blank_normalized_emails=%',
                            conflict_count, blank_count;
                    END IF;
                END
                $p3a_identity_backfill_preflight$
                """
            )
        )
        return

    connection = op.get_bind()
    conflict_count = int(
        connection.execute(sa.text(conflict_count_sql)).scalar_one()
    )
    blank_count = int(connection.execute(sa.text(blank_count_sql)).scalar_one())
    if conflict_count or blank_count:
        raise RuntimeError(
            "P3A identity backfill preflight failed: "
            f"conflicting_password_identities={conflict_count}, "
            f"blank_normalized_emails={blank_count}"
        )


def _conflicting_password_count_sql() -> str:
    return (
        "select count(*) from ("
        "select email_normalized from users where password_hash is not null "
        "group by email_normalized having count(distinct password_hash) > 1"
        ") as conflicting_passwords"
    )


def _blank_normalized_email_count_sql() -> str:
    return "select count(*) from users where length(email_normalized) = 0"


def _timestamp_columns() -> tuple[sa.Column, sa.Column]:
    return (
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
    )


def _create_identities_table() -> None:
    op.create_table(
        _IDENTITIES_TABLE,
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column(
            "email_normalized",
            sa.String(length=320),
            sa.Computed("lower(ltrim(rtrim(email)))", persisted=True),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.String(length=32),
            server_default="pending",
            nullable=False,
        ),
        sa.Column("password_hash", sa.Text(), nullable=True),
        *_timestamp_columns(),
        sa.CheckConstraint(
            "status in ('pending','active','locked','disabled')",
            name="ck_identities_status",
        ),
        sa.CheckConstraint(
            "length(email_normalized) > 0",
            name="ck_identities_email_normalized_not_empty",
        ),
        sa.CheckConstraint(
            "(status = 'pending' and password_hash is null) or "
            "(status in ('active','locked') and password_hash is not null) or "
            "status = 'disabled'",
            name="ck_identities_password_ownership",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_identities"),
        sa.UniqueConstraint(
            "email_normalized",
            name="uq_identities_email_normalized",
        ),
    )


def _create_memberships_table() -> None:
    op.create_table(
        _MEMBERSHIPS_TABLE,
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("identity_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("legacy_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("full_name", sa.Text(), nullable=False),
        sa.Column(
            "status",
            sa.String(length=32),
            server_default="invited",
            nullable=False,
        ),
        sa.Column(
            "permission_version",
            sa.Integer(),
            server_default=sa.text("1"),
            nullable=False,
        ),
        *_timestamp_columns(),
        sa.CheckConstraint(
            "status in ('invited','active','locked','disabled')",
            name="ck_tenant_memberships_status",
        ),
        sa.CheckConstraint(
            "permission_version >= 1",
            name="ck_tenant_memberships_permission_version_positive",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name="fk_tenant_memberships_tenant_id_tenants",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["identity_id"],
            ["identities.id"],
            name="fk_tenant_memberships_identity_id_identities",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "legacy_user_id"],
            ["users.tenant_id", "users.id"],
            name="fk_tenant_memberships_tenant_legacy_user_id_users",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_tenant_memberships"),
        sa.UniqueConstraint(
            "tenant_id",
            "id",
            name="uq_tenant_memberships_tenant_id_id",
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "identity_id",
            name="uq_tenant_memberships_tenant_identity",
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "legacy_user_id",
            name="uq_tenant_memberships_tenant_legacy_user",
        ),
    )
    op.create_index(
        "ix_tenant_memberships_identity_id",
        _MEMBERSHIPS_TABLE,
        ["identity_id"],
        unique=False,
    )
    op.create_index(
        "ix_tenant_memberships_tenant_status_created_at_id",
        _MEMBERSHIPS_TABLE,
        ["tenant_id", "status", "created_at", "id"],
        unique=False,
    )


def _create_membership_roles_table() -> None:
    op.create_table(
        _MEMBERSHIP_ROLES_TABLE,
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("membership_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("role_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "role_scope_type",
            sa.String(length=16),
            server_default="tenant",
            nullable=False,
        ),
        sa.Column(
            "active",
            sa.Boolean(),
            server_default=sa.true(),
            nullable=False,
        ),
        *_timestamp_columns(),
        sa.CheckConstraint(
            "role_scope_type = 'tenant'",
            name="ck_membership_roles_tenant_role_scope",
        ),
        sa.CheckConstraint(
            "active in (false, true)",
            name="ck_membership_roles_active",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "membership_id"],
            ["tenant_memberships.tenant_id", "tenant_memberships.id"],
            name="fk_membership_roles_tenant_membership_id_memberships",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["role_id", "role_scope_type"],
            ["roles.id", "roles.scope_type"],
            name="fk_membership_roles_role_id_scope_roles",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint(
            "tenant_id",
            "membership_id",
            "role_id",
            name="pk_membership_roles",
        ),
    )
    op.create_index(
        "ix_membership_roles_tenant_membership_active",
        _MEMBERSHIP_ROLES_TABLE,
        ["tenant_id", "membership_id", "active"],
        unique=False,
    )


def _backfill_identities() -> None:
    op.execute(
        sa.text(
            f"""
            with {_RANKED_USERS_CTE}
            insert into identities (
                id, email, status, password_hash, created_at, updated_at
            )
            select
                id,
                email,
                case
                    when identity_password_hash is null then 'pending'
                    else 'active'
                end,
                identity_password_hash,
                identity_created_at,
                identity_updated_at
            from ranked_users
            where canonical_rank = 1
            """
        )
    )


def _backfill_memberships() -> None:
    op.execute(
        sa.text(
            """
            insert into tenant_memberships (
                id, tenant_id, identity_id, legacy_user_id, full_name, status,
                permission_version, created_at, updated_at
            )
            select
                users.id,
                users.tenant_id,
                identities.id,
                users.id,
                users.full_name,
                users.status,
                users.permission_version,
                users.created_at,
                users.updated_at
            from users
            join identities
              on identities.email_normalized = users.email_normalized
            """
        )
    )


def _backfill_membership_roles() -> None:
    op.execute(
        sa.text(
            """
            insert into membership_roles (
                tenant_id, membership_id, role_id, role_scope_type, active,
                created_at, updated_at
            )
            select
                tenant_id, user_id, role_id, role_scope_type, active,
                created_at, updated_at
            from user_roles
            """
        )
    )


def _assert_backfill_complete() -> None:
    identity_count_sql = "select count(*) from identities"
    expected_identity_count_sql = (
        "select count(*) from (select email_normalized from users "
        "group by email_normalized) as expected_identities"
    )
    membership_count_sql = "select count(*) from tenant_memberships"
    user_count_sql = "select count(*) from users"
    membership_role_count_sql = "select count(*) from membership_roles"
    user_role_count_sql = "select count(*) from user_roles"

    if op.get_context().as_sql:
        op.execute(
            sa.text(
                f"""
                DO $p3a_identity_backfill_verification$
                DECLARE
                    identity_count bigint;
                    expected_identity_count bigint;
                    membership_count bigint;
                    user_count bigint;
                    membership_role_count bigint;
                    user_role_count bigint;
                BEGIN
                    identity_count := ({identity_count_sql});
                    expected_identity_count := ({expected_identity_count_sql});
                    membership_count := ({membership_count_sql});
                    user_count := ({user_count_sql});
                    membership_role_count := ({membership_role_count_sql});
                    user_role_count := ({user_role_count_sql});
                    IF identity_count <> expected_identity_count
                       OR membership_count <> user_count
                       OR membership_role_count <> user_role_count THEN
                        RAISE EXCEPTION
                            'P3A identity backfill verification failed: identities=%/%,'
                            ' memberships=%/%, membership_roles=%/%',
                            identity_count, expected_identity_count,
                            membership_count, user_count,
                            membership_role_count, user_role_count;
                    END IF;
                END
                $p3a_identity_backfill_verification$
                """
            )
        )
        return

    connection = op.get_bind()
    actual = (
        int(connection.execute(sa.text(identity_count_sql)).scalar_one()),
        int(connection.execute(sa.text(membership_count_sql)).scalar_one()),
        int(connection.execute(sa.text(membership_role_count_sql)).scalar_one()),
    )
    expected = (
        int(
            connection.execute(sa.text(expected_identity_count_sql)).scalar_one()
        ),
        int(connection.execute(sa.text(user_count_sql)).scalar_one()),
        int(connection.execute(sa.text(user_role_count_sql)).scalar_one()),
    )
    if actual != expected:
        raise RuntimeError(
            "P3A identity backfill verification failed: "
            f"identities={actual[0]}/{expected[0]}, "
            f"memberships={actual[1]}/{expected[1]}, "
            f"membership_roles={actual[2]}/{expected[2]}"
        )


def _expected_projection_ctes() -> str:
    return f"""
    {_RANKED_USERS_CTE},
    expected_identities as (
        select
            id,
            email,
            email_normalized,
            case
                when identity_password_hash is null then 'pending'
                else 'active'
            end as status,
            identity_password_hash as password_hash,
            identity_created_at as created_at,
            identity_updated_at as updated_at
        from ranked_users
        where canonical_rank = 1
    ),
    expected_memberships as (
        select
            ranked_users.id,
            ranked_users.tenant_id,
            expected_identities.id as identity_id,
            ranked_users.id as legacy_user_id,
            ranked_users.full_name,
            ranked_users.status,
            ranked_users.permission_version,
            ranked_users.created_at,
            ranked_users.updated_at
        from ranked_users
        join expected_identities
          on expected_identities.email_normalized = ranked_users.email_normalized
    ),
    expected_membership_roles as (
        select
            tenant_id,
            user_id as membership_id,
            role_id,
            role_scope_type,
            active,
            created_at,
            updated_at
        from user_roles
    )
    """


def _identity_drift_count_sql() -> str:
    return f"""
    with {_expected_projection_ctes()}
    select
        (select count(*) from expected_identities as expected
         where not exists (
             select 1 from identities as actual
             where actual.id = expected.id
               and actual.email = expected.email
               and actual.email_normalized = expected.email_normalized
               and actual.status = expected.status
               and (
                   actual.password_hash = expected.password_hash
                   or (actual.password_hash is null and expected.password_hash is null)
               )
               and actual.created_at = expected.created_at
               and actual.updated_at = expected.updated_at
         ))
        +
        (select count(*) from identities as actual
         where not exists (
             select 1 from expected_identities as expected
             where expected.id = actual.id
         ))
    """


def _membership_drift_count_sql() -> str:
    return f"""
    with {_expected_projection_ctes()}
    select
        (select count(*) from expected_memberships as expected
         where not exists (
             select 1 from tenant_memberships as actual
             where actual.id = expected.id
               and actual.tenant_id = expected.tenant_id
               and actual.identity_id = expected.identity_id
               and actual.legacy_user_id = expected.legacy_user_id
               and actual.full_name = expected.full_name
               and actual.status = expected.status
               and actual.permission_version = expected.permission_version
               and actual.created_at = expected.created_at
               and actual.updated_at = expected.updated_at
         ))
        +
        (select count(*) from tenant_memberships as actual
         where not exists (
             select 1 from expected_memberships as expected
             where expected.id = actual.id
         ))
    """


def _role_drift_count_sql() -> str:
    return f"""
    with {_expected_projection_ctes()}
    select
        (select count(*) from expected_membership_roles as expected
         where not exists (
             select 1 from membership_roles as actual
             where actual.tenant_id = expected.tenant_id
               and actual.membership_id = expected.membership_id
               and actual.role_id = expected.role_id
               and actual.role_scope_type = expected.role_scope_type
               and actual.active = expected.active
               and actual.created_at = expected.created_at
               and actual.updated_at = expected.updated_at
         ))
        +
        (select count(*) from membership_roles as actual
         where not exists (
             select 1 from expected_membership_roles as expected
             where expected.tenant_id = actual.tenant_id
               and expected.membership_id = actual.membership_id
               and expected.role_id = actual.role_id
         ))
    """


def _assert_downgrade_projection_is_reproducible() -> None:
    identity_drift_sql = _identity_drift_count_sql()
    membership_drift_sql = _membership_drift_count_sql()
    role_drift_sql = _role_drift_count_sql()
    conflict_count_sql = _conflicting_password_count_sql()
    blank_count_sql = _blank_normalized_email_count_sql()

    if op.get_context().as_sql:
        op.execute(
            sa.text(
                f"""
                DO $p3a_downgrade_preflight$
                DECLARE
                    identity_drift bigint;
                    membership_drift bigint;
                    role_drift bigint;
                    conflict_count bigint;
                    blank_count bigint;
                BEGIN
                    identity_drift := ({identity_drift_sql});
                    membership_drift := ({membership_drift_sql});
                    role_drift := ({role_drift_sql});
                    conflict_count := ({conflict_count_sql});
                    blank_count := ({blank_count_sql});
                    IF identity_drift > 0 OR membership_drift > 0 OR role_drift > 0
                       OR conflict_count > 0 OR blank_count > 0 THEN
                        RAISE EXCEPTION
                            'P3A downgrade preflight failed: identity_drift=%,'
                            ' membership_drift=%, role_drift=%,'
                            ' conflicting_password_identities=%,'
                            ' blank_normalized_emails=%',
                            identity_drift, membership_drift, role_drift,
                            conflict_count, blank_count;
                    END IF;
                END
                $p3a_downgrade_preflight$
                """
            )
        )
        return

    connection = op.get_bind()
    identity_drift = int(
        connection.execute(sa.text(identity_drift_sql)).scalar_one()
    )
    membership_drift = int(
        connection.execute(sa.text(membership_drift_sql)).scalar_one()
    )
    role_drift = int(connection.execute(sa.text(role_drift_sql)).scalar_one())
    conflict_count = int(
        connection.execute(sa.text(conflict_count_sql)).scalar_one()
    )
    blank_count = int(connection.execute(sa.text(blank_count_sql)).scalar_one())
    if (
        identity_drift
        or membership_drift
        or role_drift
        or conflict_count
        or blank_count
    ):
        raise RuntimeError(
            "P3A downgrade preflight failed: "
            f"identity_drift={identity_drift}, "
            f"membership_drift={membership_drift}, role_drift={role_drift}, "
            f"conflicting_password_identities={conflict_count}, "
            f"blank_normalized_emails={blank_count}"
        )


def _configure_postgresql_security() -> None:
    for table_name, column_names in (
        (_IDENTITIES_TABLE, _IDENTITY_COLUMNS),
        (_MEMBERSHIPS_TABLE, _MEMBERSHIP_COLUMNS),
        (_MEMBERSHIP_ROLES_TABLE, _MEMBERSHIP_ROLE_COLUMNS),
    ):
        _reset_postgresql_acl(table_name, column_names)
        enable_forced_row_security(op, table_name=table_name)

    # Global credential rows are deliberately inaccessible to both existing capabilities. A
    # later authentication slice must introduce its own narrow capability instead of reusing the
    # tenant or platform metadata role.
    for table_name in (_MEMBERSHIPS_TABLE, _MEMBERSHIP_ROLES_TABLE):
        create_tenant_isolation_policy(
            op,
            table_name=table_name,
            policy_name=_TENANT_POLICY,
            role_name=TENANT_APPLICATION_ROLE,
        )
        grant_table_privileges(
            op,
            table_name=table_name,
            role_name=TENANT_APPLICATION_ROLE,
            privileges=("SELECT",),
        )


def _reset_postgresql_acl(
    table_name: str,
    column_names: tuple[str, ...],
) -> None:
    quoted_columns = ", ".join(f'"{column_name}"' for column_name in column_names)
    op.execute(sa.text(f'REVOKE ALL PRIVILEGES ON TABLE "{table_name}" FROM PUBLIC'))
    op.execute(
        sa.text(
            f'REVOKE ALL PRIVILEGES ({quoted_columns}) '
            f'ON TABLE "{table_name}" FROM PUBLIC'
        )
    )
    for role_name in (TENANT_APPLICATION_ROLE, PLATFORM_APPLICATION_ROLE):
        revoke_all_table_privileges(
            op,
            table_name=table_name,
            role_name=role_name,
        )
        revoke_all_column_privileges(
            op,
            table_name=table_name,
            role_name=role_name,
            column_names=column_names,
        )


__all__ = ["revision", "down_revision", "upgrade", "downgrade"]
