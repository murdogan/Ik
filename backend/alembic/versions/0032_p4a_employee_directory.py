"""add P4A employee directory integrity and query support

Revision ID: 0032_p4a_employee_directory
Revises: 0031_p3k_legacy_tenant_auth_boundary
Create Date: 2026-07-13
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from app.platform.db.rls_migration import (
    disable_forced_row_security,
    enable_forced_row_security,
)

revision: str = "0032_p4a_employee_directory"
down_revision: str | None = "0031_p3k_legacy_tenant_auth_boundary"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_EMPLOYEES_TABLE = "employees"
_ASSIGNMENTS_TABLE = "employee_assignments"
_NORMALIZATION_WHITESPACE = (
    " \t\n\r\f\v\x1c\x1d\x1e\x1f\u0085\u00a0\u1680"
    "\u2000\u2001\u2002\u2003\u2004\u2005\u2006\u2007\u2008\u2009\u200a"
    "\u2028\u2029\u202f\u205f\u3000"
)


def _normalized_text_sql(column_name: str) -> str:
    return (
        f"lower(ltrim(rtrim({column_name}, '{_NORMALIZATION_WHITESPACE}'), "
        f"'{_NORMALIZATION_WHITESPACE}'))"
    )


def upgrade() -> None:
    is_postgresql = op.get_bind().dialect.name == "postgresql"
    if is_postgresql:
        # FORCE RLS applies to the owner as well. The preflight must inspect the complete
        # tenant population, and the transactional revision restores FORCE on success or rolls
        # the temporary change back on failure.
        disable_forced_row_security(op, table_name=_EMPLOYEES_TABLE)

    _assert_normalized_employee_identifiers_are_safe()
    _add_employee_directory_columns()
    _create_employee_directory_indexes()
    _create_assignment_filter_indexes()

    if is_postgresql:
        enable_forced_row_security(op, table_name=_EMPLOYEES_TABLE)


def downgrade() -> None:
    is_postgresql = op.get_bind().dialect.name == "postgresql"
    if is_postgresql:
        disable_forced_row_security(op, table_name=_EMPLOYEES_TABLE)

    _assert_employee_versions_can_be_rebaselined()
    _drop_assignment_filter_indexes()
    _drop_employee_directory_indexes()
    op.drop_column(_EMPLOYEES_TABLE, "full_name_normalized")
    op.drop_column(_EMPLOYEES_TABLE, "email_normalized")
    op.drop_column(_EMPLOYEES_TABLE, "employee_number_normalized")
    op.drop_column(_EMPLOYEES_TABLE, "version")

    if is_postgresql:
        enable_forced_row_security(op, table_name=_EMPLOYEES_TABLE)


def _assert_normalized_employee_identifiers_are_safe() -> None:
    number_normalized = _normalized_text_sql("employee_number")
    email_normalized = _normalized_text_sql("email")
    number_collision_sql = (
        "select count(*) from ("
        f"select tenant_id, {number_normalized} as normalized_value "
        "from employees group by tenant_id, normalized_value having count(*) > 1"
        ") as employee_number_collisions"
    )
    blank_number_sql = (
        f"select count(*) from employees where length({number_normalized}) = 0"
    )
    email_collision_sql = (
        "select count(*) from ("
        f"select tenant_id, {email_normalized} as normalized_value "
        "from employees where email is not null "
        "group by tenant_id, normalized_value having count(*) > 1"
        ") as employee_email_collisions"
    )
    blank_email_sql = (
        "select count(*) from employees where email is not null "
        f"and length({email_normalized}) = 0"
    )

    if op.get_context().as_sql:
        op.execute(
            sa.text(
                f"""
                DO $p4a_employee_normalization_preflight$
                DECLARE
                    number_collision_count bigint;
                    blank_number_count bigint;
                    email_collision_count bigint;
                    blank_email_count bigint;
                BEGIN
                    number_collision_count := ({number_collision_sql});
                    blank_number_count := ({blank_number_sql});
                    email_collision_count := ({email_collision_sql});
                    blank_email_count := ({blank_email_sql});
                    IF number_collision_count > 0 OR blank_number_count > 0
                       OR email_collision_count > 0 OR blank_email_count > 0 THEN
                        RAISE EXCEPTION
                            'P4A employee preflight failed: normalized_number_collisions=%, '
                            'blank_employee_numbers=%, normalized_email_collisions=%, '
                            'blank_work_emails=%', number_collision_count, blank_number_count,
                            email_collision_count, blank_email_count;
                    END IF;
                END
                $p4a_employee_normalization_preflight$
                """
            )
        )
        return

    connection = op.get_bind()
    counts = {
        "normalized_number_collisions": int(
            connection.scalar(sa.text(number_collision_sql)) or 0
        ),
        "blank_employee_numbers": int(
            connection.scalar(sa.text(blank_number_sql)) or 0
        ),
        "normalized_email_collisions": int(
            connection.scalar(sa.text(email_collision_sql)) or 0
        ),
        "blank_work_emails": int(connection.scalar(sa.text(blank_email_sql)) or 0),
    }
    if any(counts.values()):
        details = ", ".join(f"{key}={value}" for key, value in counts.items())
        raise RuntimeError(f"P4A employee preflight failed: {details}")


def _assert_employee_versions_can_be_rebaselined() -> None:
    changed_versions_sql = "select count(*) from employees where version <> 1"
    if op.get_context().as_sql:
        op.execute(
            sa.text(
                f"""
                DO $p4a_employee_version_downgrade_preflight$
                DECLARE
                    changed_version_count bigint;
                BEGIN
                    changed_version_count := ({changed_versions_sql});
                    IF changed_version_count > 0 THEN
                        RAISE EXCEPTION
                            'P4A employee downgrade refused: changed_versions=%',
                            changed_version_count;
                    END IF;
                END
                $p4a_employee_version_downgrade_preflight$
                """
            )
        )
        return

    changed_version_count = int(
        op.get_bind().scalar(sa.text(changed_versions_sql)) or 0
    )
    if changed_version_count:
        raise RuntimeError(
            "P4A employee downgrade refused: "
            f"changed_versions={changed_version_count}"
        )


def _add_employee_directory_columns() -> None:
    op.add_column(
        _EMPLOYEES_TABLE,
        sa.Column(
            "version",
            sa.Integer(),
            sa.CheckConstraint("version > 0", name="ck_employees_version_positive"),
            server_default=sa.text("1"),
            nullable=False,
        ),
    )
    op.add_column(
        _EMPLOYEES_TABLE,
        sa.Column(
            "employee_number_normalized",
            sa.String(length=64),
            sa.Computed(_normalized_text_sql("employee_number")),
            sa.CheckConstraint(
                "employee_number_normalized <> ''",
                name="ck_employees_employee_number_not_blank",
            ),
            nullable=False,
        ),
    )
    op.add_column(
        _EMPLOYEES_TABLE,
        sa.Column(
            "email_normalized",
            sa.String(length=320),
            sa.Computed(
                "case when email is null then null else "
                f"{_normalized_text_sql('email')} end"
            ),
            sa.CheckConstraint(
                "email_normalized is null or email_normalized <> ''",
                name="ck_employees_email_not_blank",
            ),
            nullable=True,
        ),
    )
    op.add_column(
        _EMPLOYEES_TABLE,
        sa.Column(
            "full_name_normalized",
            sa.Text(),
            sa.Computed(
                f"{_normalized_text_sql('first_name')} || ' ' || "
                f"{_normalized_text_sql('last_name')}"
            ),
            nullable=False,
        ),
    )


def _create_employee_directory_indexes() -> None:
    op.create_index(
        "uq_employees_tenant_employee_number_normalized",
        _EMPLOYEES_TABLE,
        ["tenant_id", "employee_number_normalized"],
        unique=True,
    )
    op.create_index(
        "uq_employees_tenant_email_normalized",
        _EMPLOYEES_TABLE,
        ["tenant_id", "email_normalized"],
        unique=True,
    )
    op.create_index(
        "ix_employees_tenant_directory_cursor",
        _EMPLOYEES_TABLE,
        ["tenant_id", "employee_number", "id"],
        unique=False,
        postgresql_where=sa.text("archived_at IS NULL"),
        sqlite_where=sa.text("archived_at IS NULL"),
    )
    op.create_index(
        "ix_employees_tenant_status_directory_cursor",
        _EMPLOYEES_TABLE,
        ["tenant_id", "status", "employee_number", "id"],
        unique=False,
        postgresql_where=sa.text("archived_at IS NULL"),
        sqlite_where=sa.text("archived_at IS NULL"),
    )
    op.create_index(
        "ix_employees_full_name_normalized_trgm",
        _EMPLOYEES_TABLE,
        ["full_name_normalized"],
        unique=False,
        postgresql_using="gin",
        postgresql_ops={"full_name_normalized": "gin_trgm_ops"},
        postgresql_where=sa.text("archived_at IS NULL"),
    )


def _drop_employee_directory_indexes() -> None:
    for index_name in (
        "ix_employees_full_name_normalized_trgm",
        "ix_employees_tenant_status_directory_cursor",
        "ix_employees_tenant_directory_cursor",
        "uq_employees_tenant_email_normalized",
        "uq_employees_tenant_employee_number_normalized",
    ):
        op.drop_index(index_name, table_name=_EMPLOYEES_TABLE)


def _create_assignment_filter_indexes() -> None:
    op.create_index(
        "ix_employee_assignments_tenant_legal_entity_effective",
        _ASSIGNMENTS_TABLE,
        [
            "tenant_id",
            "legal_entity_id",
            "effective_from",
            "effective_to",
            "employee_id",
        ],
        unique=False,
    )
    op.create_index(
        "ix_employee_assignments_tenant_position_effective",
        _ASSIGNMENTS_TABLE,
        [
            "tenant_id",
            "position_id",
            "effective_from",
            "effective_to",
            "employee_id",
        ],
        unique=False,
    )


def _drop_assignment_filter_indexes() -> None:
    op.drop_index(
        "ix_employee_assignments_tenant_position_effective",
        table_name=_ASSIGNMENTS_TABLE,
    )
    op.drop_index(
        "ix_employee_assignments_tenant_legal_entity_effective",
        table_name=_ASSIGNMENTS_TABLE,
    )
