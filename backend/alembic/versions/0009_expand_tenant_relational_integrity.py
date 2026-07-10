"""expand tenant relational integrity constraints

Revision ID: 0009_expand_tenant_relational_integrity
Revises: 0008_employee_lifecycle_status_dates
Create Date: 2026-07-10
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0009_expand_tenant_relational_integrity"
down_revision: str | None = "0008_employee_lifecycle_status_dates"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TENANT_RELATIONSHIP_PREFLIGHT_SQL = """
with violations as (
    select
        'users.tenant_id' as relationship_name,
        'orphan' as violation_type,
        child.id as child_id,
        child.tenant_id as child_tenant_id,
        child.tenant_id as referenced_id,
        parent.id as parent_tenant_id
    from users as child
    left join tenants as parent on parent.id = child.tenant_id
    where parent.id is null

    union all

    select
        'employees.tenant_id',
        'orphan',
        child.id,
        child.tenant_id,
        child.tenant_id,
        parent.id
    from employees as child
    left join tenants as parent on parent.id = child.tenant_id
    where parent.id is null

    union all

    select
        'leave_requests.tenant_id',
        'orphan',
        child.id,
        child.tenant_id,
        child.tenant_id,
        parent.id
    from leave_requests as child
    left join tenants as parent on parent.id = child.tenant_id
    where parent.id is null

    union all

    select
        'leave_balance_summaries.tenant_id',
        'orphan',
        child.id,
        child.tenant_id,
        child.tenant_id,
        parent.id
    from leave_balance_summaries as child
    left join tenants as parent on parent.id = child.tenant_id
    where parent.id is null

    union all

    select
        'leave_requests.employee_id',
        case when parent.id is null then 'orphan' else 'cross_tenant' end,
        child.id,
        child.tenant_id,
        child.employee_id,
        parent.tenant_id
    from leave_requests as child
    left join employees as parent on parent.id = child.employee_id
    where parent.id is null or parent.tenant_id <> child.tenant_id

    union all

    select
        'leave_requests.requested_by_user_id',
        case when parent.id is null then 'orphan' else 'cross_tenant' end,
        child.id,
        child.tenant_id,
        child.requested_by_user_id,
        parent.tenant_id
    from leave_requests as child
    left join users as parent on parent.id = child.requested_by_user_id
    where parent.id is null or parent.tenant_id <> child.tenant_id

    union all

    select
        'leave_requests.decided_by_user_id',
        case when parent.id is null then 'orphan' else 'cross_tenant' end,
        child.id,
        child.tenant_id,
        child.decided_by_user_id,
        parent.tenant_id
    from leave_requests as child
    left join users as parent on parent.id = child.decided_by_user_id
    where child.decided_by_user_id is not null
      and (parent.id is null or parent.tenant_id <> child.tenant_id)

    union all

    select
        'leave_balance_summaries.employee_id',
        case when parent.id is null then 'orphan' else 'cross_tenant' end,
        child.id,
        child.tenant_id,
        child.employee_id,
        parent.tenant_id
    from leave_balance_summaries as child
    left join employees as parent on parent.id = child.employee_id
    where parent.id is null or parent.tenant_id <> child.tenant_id
)
select
    relationship_name,
    violation_type,
    child_id,
    child_tenant_id,
    referenced_id,
    parent_tenant_id
from violations
"""

_CANDIDATE_KEYS = (
    ("employees", "uq_employees_tenant_id_id", ("tenant_id", "id")),
    ("users", "uq_users_tenant_id_id", ("tenant_id", "id")),
)

_COMPOSITE_FOREIGN_KEYS = (
    (
        "leave_requests",
        "fk_leave_requests_tenant_employee_id_employees",
        ("tenant_id", "employee_id"),
        "employees",
        ("tenant_id", "id"),
        "CASCADE",
    ),
    (
        "leave_requests",
        "fk_leave_requests_tenant_requested_by_user_id_users",
        ("tenant_id", "requested_by_user_id"),
        "users",
        ("tenant_id", "id"),
        None,
    ),
    (
        "leave_requests",
        "fk_leave_requests_tenant_decided_by_user_id_users",
        ("tenant_id", "decided_by_user_id"),
        "users",
        ("tenant_id", "id"),
        None,
    ),
    (
        "leave_balance_summaries",
        "fk_leave_balance_summaries_tenant_employee_id_employees",
        ("tenant_id", "employee_id"),
        "employees",
        ("tenant_id", "id"),
        "CASCADE",
    ),
)


def upgrade() -> None:
    _assert_preflight_is_clean()
    if op.get_bind().dialect.name == "postgresql":
        _postgresql_expand()
        # NOT VALID protects subsequent writes. Re-scan while the ALTER TABLE
        # locks are still held so a row committed during concurrent index creation
        # cannot let the expand revision stamp with known-invalid existing data.
        _assert_preflight_is_clean()
    else:
        _portable_expand()


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        _postgresql_remove_expansion()
    else:
        _portable_remove_expansion()


def _assert_preflight_is_clean() -> None:
    if op.get_context().as_sql:
        op.execute(
            sa.text(
                f"""
                DO $tenant_integrity_preflight$
                BEGIN
                    IF EXISTS (
                        SELECT 1
                        FROM ({TENANT_RELATIONSHIP_PREFLIGHT_SQL})
                            AS tenant_integrity_violations
                    ) THEN
                        RAISE EXCEPTION
                            'tenant relational integrity preflight failed; '
                            'repair orphan/cross-tenant rows before retrying';
                    END IF;
                END
                $tenant_integrity_preflight$
                """
            )
        )
        return

    summary_sql = sa.text(
        "select relationship_name, violation_type, count(*) as row_count "
        f"from ({TENANT_RELATIONSHIP_PREFLIGHT_SQL}) as tenant_integrity_violations "
        "group by relationship_name, violation_type "
        "order by relationship_name, violation_type"
    )
    violations = op.get_bind().execute(summary_sql).mappings().all()
    if not violations:
        return

    summary = ", ".join(
        f"{row['relationship_name']}:{row['violation_type']}={row['row_count']}"
        for row in violations
    )
    raise RuntimeError(
        "tenant relational integrity preflight failed; repair the reported "
        f"orphan/cross-tenant rows before retrying: {summary}"
    )


def _postgresql_expand() -> None:
    _prepare_postgresql_candidate_indexes()
    for table_name, constraint_name, _columns in _CANDIDATE_KEYS:
        op.execute(
            sa.text(
                f'ALTER TABLE "{table_name}" ADD CONSTRAINT "{constraint_name}" '
                f'UNIQUE USING INDEX "{constraint_name}"'
            )
        )

    for (
        table_name,
        constraint_name,
        local_columns,
        referred_table,
        remote_columns,
        ondelete,
    ) in _COMPOSITE_FOREIGN_KEYS:
        delete_clause = f" ON DELETE {ondelete}" if ondelete is not None else ""
        op.execute(
            sa.text(
                f'ALTER TABLE "{table_name}" ADD CONSTRAINT "{constraint_name}" '
                f"FOREIGN KEY ({_quoted_columns(local_columns)}) "
                f'REFERENCES "{referred_table}" ({_quoted_columns(remote_columns)})'
                f"{delete_clause} NOT VALID"
            )
        )


def _prepare_postgresql_candidate_indexes() -> None:
    if op.get_context().as_sql:
        with op.get_context().autocommit_block():
            for table_name, index_name, columns in _CANDIDATE_KEYS:
                op.execute(
                    sa.text(
                        f'CREATE UNIQUE INDEX CONCURRENTLY "{index_name}" '
                        f'ON "{table_name}" ({_quoted_columns(columns)})'
                    )
                )
        return

    indexes_to_create: list[tuple[str, str, tuple[str, ...]]] = []
    indexes_to_replace: list[str] = []

    for table_name, index_name, columns in _CANDIDATE_KEYS:
        state = _postgresql_index_state(index_name)
        if state is None:
            indexes_to_create.append((table_name, index_name, columns))
            continue

        actual_table = str(state["table_name"])
        actual_columns = tuple(state["column_names"])
        if (
            actual_table != table_name
            or actual_columns != columns
            or not bool(state["indisunique"])
            or not bool(state["is_plain"])
        ):
            raise RuntimeError(
                f"cannot reuse migration index {index_name}: its definition is unexpected"
            )
        if bool(state["indisvalid"]):
            continue
        indexes_to_replace.append(index_name)
        indexes_to_create.append((table_name, index_name, columns))

    with op.get_context().autocommit_block():
        for index_name in indexes_to_replace:
            op.execute(sa.text(f'DROP INDEX CONCURRENTLY IF EXISTS "{index_name}"'))
        for table_name, index_name, columns in indexes_to_create:
            op.execute(
                sa.text(
                    f'CREATE UNIQUE INDEX CONCURRENTLY "{index_name}" '
                    f'ON "{table_name}" ({_quoted_columns(columns)})'
                )
            )


def _postgresql_index_state(index_name: str):
    return (
        op.get_bind()
        .execute(
            sa.text(
                """
                select
                    table_relation.relname as table_name,
                    index_data.indisvalid,
                    index_data.indisunique,
                    index_data.indexprs is null
                        and index_data.indpred is null
                        and index_data.indnkeyatts = array_length(index_data.indkey, 1)
                        as is_plain,
                    array(
                        select table_attribute.attname
                        from unnest(index_data.indkey) with ordinality
                            as index_key(attribute_number, key_order)
                        join pg_attribute as table_attribute
                          on table_attribute.attrelid = index_data.indrelid
                         and table_attribute.attnum = index_key.attribute_number
                        order by index_key.key_order
                    ) as column_names
                from pg_class as index_relation
                join pg_namespace as index_namespace
                  on index_namespace.oid = index_relation.relnamespace
                join pg_index as index_data
                  on index_data.indexrelid = index_relation.oid
                join pg_class as table_relation
                  on table_relation.oid = index_data.indrelid
                where index_namespace.nspname = current_schema()
                  and index_relation.relname = :index_name
                """
            ),
            {"index_name": index_name},
        )
        .mappings()
        .one_or_none()
    )


def _portable_expand() -> None:
    for table_name, constraint_name, columns in _CANDIDATE_KEYS:
        with op.batch_alter_table(table_name) as batch_op:
            batch_op.create_unique_constraint(constraint_name, list(columns))

    for table_name in ("leave_requests", "leave_balance_summaries"):
        with op.batch_alter_table(table_name) as batch_op:
            for (
                foreign_key_table,
                constraint_name,
                local_columns,
                referred_table,
                remote_columns,
                ondelete,
            ) in _COMPOSITE_FOREIGN_KEYS:
                if foreign_key_table != table_name:
                    continue
                batch_op.create_foreign_key(
                    constraint_name,
                    referred_table,
                    list(local_columns),
                    list(remote_columns),
                    ondelete=ondelete,
                )


def _postgresql_remove_expansion() -> None:
    for table_name in ("leave_balance_summaries", "leave_requests"):
        for foreign_key in _COMPOSITE_FOREIGN_KEYS:
            if foreign_key[0] == table_name:
                op.drop_constraint(foreign_key[1], table_name, type_="foreignkey")
    for table_name, constraint_name, _columns in reversed(_CANDIDATE_KEYS):
        op.drop_constraint(constraint_name, table_name, type_="unique")


def _portable_remove_expansion() -> None:
    for table_name in ("leave_balance_summaries", "leave_requests"):
        with op.batch_alter_table(table_name) as batch_op:
            for foreign_key in _COMPOSITE_FOREIGN_KEYS:
                if foreign_key[0] == table_name:
                    batch_op.drop_constraint(foreign_key[1], type_="foreignkey")
    for table_name, constraint_name, _columns in reversed(_CANDIDATE_KEYS):
        with op.batch_alter_table(table_name) as batch_op:
            batch_op.drop_constraint(constraint_name, type_="unique")


def _quoted_columns(columns: tuple[str, ...]) -> str:
    return ", ".join(f'"{column}"' for column in columns)
