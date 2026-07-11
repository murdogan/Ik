from __future__ import annotations

import asyncio
import subprocess
import sys
from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command as alembic_command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from app.core.config import Settings
from app.db.base import Base
from app.db.session import create_database_runtime
from app.models import (  # noqa: F401
    CommandIdempotency,
    Employee,
    LeaveBalanceSummary,
    LeaveRequest,
    RefreshSessionFamily,
    RefreshSessionToken,
    Tenant,
    TenantFeatureFlag,
    TenantSettings,
    User,
    UserActivationToken,
)
from sqlalchemy import text
from sqlalchemy.engine import URL
from sqlalchemy.exc import IntegrityError
from sqlalchemy.exc import TimeoutError as SqlAlchemyTimeoutError
from sqlalchemy.ext.asyncio import AsyncConnection, create_async_engine
from sqlalchemy.pool import NullPool

pytestmark = pytest.mark.postgres

ROOT = Path(__file__).resolve().parents[3]
ALEMBIC_INI = ROOT / "alembic.ini"

EXPECTED_UUID_COLUMNS = {
    ("command_idempotency", "id"),
    ("command_idempotency", "resource_id"),
    ("command_idempotency", "tenant_id"),
    ("employees", "id"),
    ("employees", "tenant_id"),
    ("leave_balance_summaries", "employee_id"),
    ("leave_balance_summaries", "id"),
    ("leave_balance_summaries", "tenant_id"),
    ("leave_requests", "decided_by_user_id"),
    ("leave_requests", "employee_id"),
    ("leave_requests", "id"),
    ("leave_requests", "requested_by_user_id"),
    ("leave_requests", "tenant_id"),
    ("tenants", "id"),
    ("tenant_settings", "tenant_id"),
    ("tenant_feature_flags", "tenant_id"),
    ("users", "id"),
    ("users", "tenant_id"),
    ("user_activation_tokens", "id"),
    ("user_activation_tokens", "tenant_id"),
    ("user_activation_tokens", "user_id"),
    ("refresh_session_families", "id"),
    ("refresh_session_families", "tenant_id"),
    ("refresh_session_families", "user_id"),
    ("refresh_session_tokens", "id"),
    ("refresh_session_tokens", "tenant_id"),
    ("refresh_session_tokens", "family_id"),
}
EXPECTED_TIMESTAMP_COLUMNS = {
    (table_name, column_name)
    for table_name in {
        "employees",
        "leave_balance_summaries",
        "leave_requests",
        "tenants",
        "tenant_settings",
        "tenant_feature_flags",
        "users",
        "user_activation_tokens",
        "refresh_session_families",
        "refresh_session_tokens",
    }
    for column_name in {"created_at", "updated_at"}
} | {
    ("command_idempotency", "created_at"),
    ("command_idempotency", "completed_at"),
    ("employees", "archived_at"),
    ("user_activation_tokens", "expires_at"),
    ("user_activation_tokens", "consumed_at"),
    ("user_activation_tokens", "revoked_at"),
    ("refresh_session_families", "expires_at"),
    ("refresh_session_families", "revoked_at"),
    ("refresh_session_tokens", "consumed_at"),
}
EXPECTED_CHECK_CONSTRAINTS = {
    "ck_command_idempotency_completion",
    "ck_employees_date_order",
    "ck_employees_lifecycle_status_dates",
    "ck_employees_status",
    "ck_leave_balance_summaries_opening_non_negative",
    "ck_leave_balance_summaries_period_year",
    "ck_leave_balance_summaries_planned_non_negative",
    "ck_leave_balance_summaries_used_non_negative",
    "ck_leave_requests_date_order",
    "ck_leave_requests_status",
    "ck_tenants_status",
    "ck_tenants_active_employee_limit_positive",
    "ck_tenant_feature_flags_enabled",
    "ck_tenant_feature_flags_key",
    "ck_tenant_settings_date_format",
    "ck_tenant_settings_time_format",
    "ck_tenant_settings_week_start_day",
    "ck_users_status",
    "ck_users_email_normalized_not_empty",
    "ck_user_activation_tokens_hash_length",
    "ck_user_activation_tokens_expiry_order",
    "ck_user_activation_tokens_consumed_order",
    "ck_user_activation_tokens_revoked_order",
    "ck_user_activation_tokens_terminal_state",
    "ck_refresh_session_families_expiry_order",
    "ck_refresh_session_families_revoked_order",
    "ck_refresh_session_tokens_hash_length",
    "ck_refresh_session_tokens_consumed_order",
}
EXPECTED_NAMED_UNIQUE_CONSTRAINTS = {
    "uq_command_idempotency_tenant_key",
    "uq_employees_tenant_id_id",
    "uq_employees_tenant_employee_number",
    "uq_leave_balance_summaries_tenant_employee_type_period",
    "uq_users_tenant_id_id",
    "uq_users_tenant_email",
    "uq_users_tenant_email_normalized",
    "uq_user_activation_tokens_token_hash",
    "uq_refresh_session_families_tenant_id_id",
    "uq_refresh_session_tokens_token_hash",
}
EXPECTED_FOREIGN_KEY_COUNTS = {
    "command_idempotency": 1,
    "employees": 1,
    "leave_balance_summaries": 2,
    "leave_requests": 4,
    "tenant_settings": 1,
    "tenant_feature_flags": 1,
    "users": 1,
    "user_activation_tokens": 2,
    "refresh_session_families": 2,
    "refresh_session_tokens": 2,
}


@pytest.fixture
def migrated_postgres_database(postgres_database_url: URL) -> URL:
    alembic_command.upgrade(_alembic_config(postgres_database_url), "head")
    return postgres_database_url


def test_alembic_round_trip_reaches_current_head(postgres_database_url: URL) -> None:
    config = _alembic_config(postgres_database_url)
    expected_head = ScriptDirectory.from_config(config).get_current_head()

    alembic_command.downgrade(config, "base")
    alembic_command.upgrade(config, "0005_employee_date_order")
    asyncio.run(_set_alembic_version_column_length(postgres_database_url, 32))
    alembic_command.upgrade(config, "head")
    assert asyncio.run(_current_revision(postgres_database_url)) == expected_head
    assert asyncio.run(_alembic_version_column_length(postgres_database_url)) == 128

    alembic_command.downgrade(config, "base")
    assert asyncio.run(_current_revision(postgres_database_url)) is None

    alembic_command.upgrade(config, "head")
    assert asyncio.run(_current_revision(postgres_database_url)) == expected_head


def test_tenant_settings_migration_backfills_and_round_trips_postgresql(
    postgres_database_url: URL,
) -> None:
    config = _alembic_config(postgres_database_url)
    tenant_id = uuid4()

    alembic_command.upgrade(config, "0012_p0f_query_performance")
    asyncio.run(_insert_pre_settings_tenant(postgres_database_url, tenant_id))
    alembic_command.upgrade(config, "head")
    assert asyncio.run(_tenant_settings_values(postgres_database_url, tenant_id)) == (
        "monday",
        "DD.MM.YYYY",
        "24h",
    )

    alembic_command.downgrade(config, "0012_p0f_query_performance")
    assert asyncio.run(_tenant_exists(postgres_database_url, tenant_id)) is True
    alembic_command.upgrade(config, "head")
    assert asyncio.run(_tenant_settings_values(postgres_database_url, tenant_id)) == (
        "monday",
        "DD.MM.YYYY",
        "24h",
    )


def test_tenant_settings_downgrade_refuses_custom_postgresql_values(
    postgres_database_url: URL,
) -> None:
    config = _alembic_config(postgres_database_url)
    tenant_id = uuid4()
    alembic_command.upgrade(config, "head")
    asyncio.run(
        _insert_tenant_with_settings(
            postgres_database_url,
            tenant_id,
            week_start_day="sunday",
        )
    )

    with pytest.raises(
        RuntimeError,
        match="F1A downgrade preflight failed.*custom_tenant_settings=1",
    ):
        alembic_command.downgrade(config, "0012_p0f_query_performance")

    assert asyncio.run(_current_revision(postgres_database_url)) == "0013_tenant_settings"
    assert asyncio.run(_tenant_settings_values(postgres_database_url, tenant_id)) == (
        "sunday",
        "DD.MM.YYYY",
        "24h",
    )


def test_f1d_migration_owner_without_bypass_backfills_and_guards_limits(
    postgres_database_url: URL,
) -> None:
    migration_role = f"wf_f1d_owner_{uuid4().hex[:12]}"
    admin_user = postgres_database_url.username
    assert admin_user is not None
    asyncio.run(
        _create_non_bypass_migration_owner(
            postgres_database_url,
            migration_role,
        )
    )
    owner_url = postgres_database_url.set(
        username=migration_role,
        password=None,
    )
    owner_config = _alembic_config(owner_url)
    admin_config = _alembic_config(postgres_database_url)
    tenant_id = uuid4()
    try:
        alembic_command.upgrade(owner_config, "0013_tenant_settings")
        alembic_command.upgrade(admin_config, "0014_f1c_postgresql_rls")
        asyncio.run(_insert_pre_settings_tenant(postgres_database_url, tenant_id))
        asyncio.run(_set_hostile_feature_default_privileges(owner_url))

        alembic_command.upgrade(owner_config, "head")
        assert asyncio.run(_tenant_feature_count(postgres_database_url, tenant_id)) == 7
        assert asyncio.run(_unexpected_feature_delete_grantees(postgres_database_url)) == set()
        assert asyncio.run(_row_security_flags(postgres_database_url, "tenants")) == (
            True,
            True,
        )

        asyncio.run(_set_active_employee_limit(postgres_database_url, tenant_id, 250))
        with pytest.raises(
            RuntimeError,
            match=(
                "F1D downgrade preflight failed.*"
                "configured_active_employee_limits=1"
            ),
        ):
            alembic_command.downgrade(owner_config, "0014_f1c_postgresql_rls")

        assert asyncio.run(_current_revision(postgres_database_url)) == (
            "0015_f1d_feature_flags"
        )
        assert asyncio.run(_row_security_flags(postgres_database_url, "tenants")) == (
            True,
            True,
        )
        assert asyncio.run(
            _row_security_flags(postgres_database_url, "tenant_feature_flags")
        ) == (True, True)

        asyncio.run(_set_active_employee_limit(postgres_database_url, tenant_id, None))
        alembic_command.downgrade(owner_config, "0014_f1c_postgresql_rls")
    finally:
        asyncio.run(
            _remove_migration_owner(
                postgres_database_url,
                migration_role,
                replacement_owner=admin_user,
            )
        )


def test_live_postgresql_schema_has_no_autogenerate_drift(
    migrated_postgres_database: URL,
) -> None:
    schema_diffs = asyncio.run(_schema_diffs(migrated_postgres_database))

    assert schema_diffs == []


def test_postgresql_catalog_and_constraints_are_native_and_enforced(
    migrated_postgres_database: URL,
) -> None:
    snapshot = asyncio.run(_catalog_snapshot(migrated_postgres_database))

    assert snapshot["server_version_num"] >= 160_000
    assert snapshot["alembic_version_column_length"] == 128
    assert snapshot["uuid_columns"] == EXPECTED_UUID_COLUMNS
    assert snapshot["timestamp_columns"] == EXPECTED_TIMESTAMP_COLUMNS
    assert EXPECTED_CHECK_CONSTRAINTS <= snapshot["check_constraints"]
    assert EXPECTED_NAMED_UNIQUE_CONSTRAINTS <= snapshot["unique_constraints"]
    assert snapshot["foreign_key_counts"] == EXPECTED_FOREIGN_KEY_COUNTS

    asyncio.run(_assert_constraints_reject_invalid_rows(migrated_postgres_database))


def test_runtime_applies_pool_and_postgresql_server_timeouts(
    migrated_postgres_database: URL,
) -> None:
    asyncio.run(_assert_runtime_configuration(migrated_postgres_database))


def test_full_api_smoke_uses_alembic_migrated_postgresql(
    postgres_database_url: URL,
) -> None:
    config = _alembic_config(postgres_database_url)
    alembic_command.downgrade(config, "base")
    alembic_command.upgrade(config, "head")

    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "backend_api_smoke.py"),
            "--database-url",
            _render_database_url(postgres_database_url),
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
        timeout=180,
    )

    output = "\n".join(part for part in (result.stdout, result.stderr) if part)
    assert result.returncode == 0, output
    assert "BACKEND_SMOKE_OK" in result.stdout
    assert "documented_endpoints=31" in result.stdout


def _alembic_config(database_url: URL) -> Config:
    config = Config(str(ALEMBIC_INI))
    config.set_main_option(
        "sqlalchemy.url",
        _render_database_url(database_url).replace("%", "%%"),
    )
    return config


def _render_database_url(database_url: URL) -> str:
    return database_url.render_as_string(hide_password=False)


async def _current_revision(database_url: URL) -> str | None:
    engine = create_async_engine(database_url, poolclass=NullPool)
    try:
        async with engine.connect() as connection:
            return await connection.run_sync(
                lambda sync_connection: MigrationContext.configure(
                    sync_connection
                ).get_current_revision()
            )
    finally:
        await engine.dispose()


async def _insert_pre_settings_tenant(database_url: URL, tenant_id) -> None:
    engine = create_async_engine(database_url, poolclass=NullPool)
    try:
        async with engine.begin() as connection:
            await connection.execute(
                text(
                    "insert into tenants ("
                    "id, slug, name, status, plan_code, data_region, locale, timezone"
                    ") values ("
                    ":id, :slug, 'F1A migration tenant', 'active', 'core', 'tr-1', "
                    "'tr-TR', 'Europe/Istanbul'"
                    ")"
                ),
                {"id": tenant_id, "slug": f"f1a-backfill-{tenant_id.hex}"},
            )
    finally:
        await engine.dispose()


async def _insert_tenant_with_settings(
    database_url: URL,
    tenant_id,
    *,
    week_start_day: str,
) -> None:
    engine = create_async_engine(database_url, poolclass=NullPool)
    try:
        async with engine.begin() as connection:
            await connection.execute(
                text(
                    "insert into tenants ("
                    "id, slug, name, status, plan_code, data_region, locale, timezone"
                    ") values ("
                    ":id, :slug, 'F1A guarded tenant', 'active', 'core', 'tr-1', "
                    "'tr-TR', 'Europe/Istanbul'"
                    ")"
                ),
                {"id": tenant_id, "slug": f"f1a-guard-{tenant_id.hex}"},
            )
            await connection.execute(
                text(
                    "insert into tenant_settings ("
                    "tenant_id, week_start_day, date_format, time_format"
                    ") values ("
                    ":tenant_id, :week_start_day, 'DD.MM.YYYY', '24h'"
                    ")"
                ),
                {"tenant_id": tenant_id, "week_start_day": week_start_day},
            )
    finally:
        await engine.dispose()


async def _tenant_settings_values(database_url: URL, tenant_id) -> tuple[str, str, str]:
    engine = create_async_engine(database_url, poolclass=NullPool)
    try:
        async with engine.connect() as connection:
            row = (
                await connection.execute(
                    text(
                        "select week_start_day, date_format, time_format "
                        "from tenant_settings where tenant_id = :tenant_id"
                    ),
                    {"tenant_id": tenant_id},
                )
            ).one()
            return str(row[0]), str(row[1]), str(row[2])
    finally:
        await engine.dispose()


async def _tenant_exists(database_url: URL, tenant_id) -> bool:
    engine = create_async_engine(database_url, poolclass=NullPool)
    try:
        async with engine.connect() as connection:
            return bool(
                await connection.scalar(
                    text("select exists(select 1 from tenants where id = :tenant_id)"),
                    {"tenant_id": tenant_id},
                )
            )
    finally:
        await engine.dispose()


async def _create_non_bypass_migration_owner(
    database_url: URL,
    role_name: str,
) -> None:
    engine = create_async_engine(database_url, poolclass=NullPool)
    try:
        async with engine.begin() as connection:
            quote = connection.dialect.identifier_preparer.quote
            quoted_role = quote(role_name)
            quoted_database = quote(database_url.database)
            await connection.exec_driver_sql(
                f"CREATE ROLE {quoted_role} LOGIN NOSUPERUSER NOBYPASSRLS NOINHERIT"
            )
            await connection.exec_driver_sql(
                f"ALTER DATABASE {quoted_database} OWNER TO {quoted_role}"
            )
            await connection.exec_driver_sql(
                f"ALTER SCHEMA public OWNER TO {quoted_role}"
            )
            role = (
                await connection.execute(
                    text(
                        "select rolsuper, rolbypassrls from pg_catalog.pg_roles "
                        "where rolname = :role_name"
                    ),
                    {"role_name": role_name},
                )
            ).one()
            assert role == (False, False)
    finally:
        await engine.dispose()


async def _remove_migration_owner(
    database_url: URL,
    role_name: str,
    *,
    replacement_owner: str,
) -> None:
    engine = create_async_engine(database_url, poolclass=NullPool)
    try:
        async with engine.begin() as connection:
            if not await connection.scalar(
                text(
                    "select exists(select 1 from pg_catalog.pg_roles where rolname = :role_name)"
                ),
                {"role_name": role_name},
            ):
                return
            quote = connection.dialect.identifier_preparer.quote
            quoted_role = quote(role_name)
            quoted_replacement = quote(replacement_owner)
            quoted_database = quote(database_url.database)
            await connection.exec_driver_sql(
                f"REASSIGN OWNED BY {quoted_role} TO {quoted_replacement}"
            )
            await connection.exec_driver_sql(
                f"ALTER DATABASE {quoted_database} OWNER TO {quoted_replacement}"
            )
            await connection.exec_driver_sql(
                f"ALTER SCHEMA public OWNER TO {quoted_replacement}"
            )
            await connection.exec_driver_sql(f"DROP OWNED BY {quoted_role}")
            await connection.exec_driver_sql(f"DROP ROLE {quoted_role}")
    finally:
        await engine.dispose()


async def _tenant_feature_count(database_url: URL, tenant_id) -> int:
    engine = create_async_engine(database_url, poolclass=NullPool)
    try:
        async with engine.connect() as connection:
            return int(
                await connection.scalar(
                    text(
                        "select count(*) from tenant_feature_flags "
                        "where tenant_id = :tenant_id"
                    ),
                    {"tenant_id": tenant_id},
                )
                or 0
            )
    finally:
        await engine.dispose()


async def _set_hostile_feature_default_privileges(database_url: URL) -> None:
    engine = create_async_engine(database_url, poolclass=NullPool)
    try:
        async with engine.begin() as connection:
            await connection.exec_driver_sql(
                "ALTER DEFAULT PRIVILEGES GRANT DELETE ON TABLES TO PUBLIC"
            )
            await connection.exec_driver_sql(
                'ALTER DEFAULT PRIVILEGES GRANT DELETE ON TABLES TO "wealthy_falcon_app"'
            )
            await connection.exec_driver_sql(
                'ALTER DEFAULT PRIVILEGES GRANT DELETE ON TABLES TO "wealthy_falcon_platform"'
            )
    finally:
        await engine.dispose()


async def _unexpected_feature_delete_grantees(database_url: URL) -> set[str]:
    engine = create_async_engine(database_url, poolclass=NullPool)
    try:
        async with engine.connect() as connection:
            rows = await connection.scalars(
                text(
                    "select grantee from information_schema.table_privileges "
                    "where table_schema = 'public' "
                    "and table_name = 'tenant_feature_flags' "
                    "and privilege_type = 'DELETE' "
                    "and grantee = any(:grantees)"
                ),
                {
                    "grantees": [
                        "PUBLIC",
                        "wealthy_falcon_app",
                        "wealthy_falcon_platform",
                    ]
                },
            )
            return set(rows)
    finally:
        await engine.dispose()


async def _row_security_flags(
    database_url: URL,
    table_name: str,
) -> tuple[bool, bool]:
    engine = create_async_engine(database_url, poolclass=NullPool)
    try:
        async with engine.connect() as connection:
            row = (
                await connection.execute(
                    text(
                        "select relrowsecurity, relforcerowsecurity "
                        "from pg_catalog.pg_class table_class "
                        "join pg_catalog.pg_namespace namespace "
                        "on namespace.oid = table_class.relnamespace "
                        "where namespace.nspname = 'public' and table_class.relname = :table_name"
                    ),
                    {"table_name": table_name},
                )
            ).one()
            return bool(row[0]), bool(row[1])
    finally:
        await engine.dispose()


async def _set_active_employee_limit(
    database_url: URL,
    tenant_id,
    value: int | None,
) -> None:
    engine = create_async_engine(database_url, poolclass=NullPool)
    try:
        async with engine.begin() as connection:
            await connection.execute(
                text(
                    "update tenants set active_employee_limit = :value "
                    "where id = :tenant_id"
                ),
                {"tenant_id": tenant_id, "value": value},
            )
    finally:
        await engine.dispose()


async def _set_alembic_version_column_length(database_url: URL, length: int) -> None:
    engine = create_async_engine(database_url, poolclass=NullPool)
    try:
        async with engine.begin() as connection:
            await connection.exec_driver_sql(
                f"alter table alembic_version alter column version_num type varchar({length})"
            )
    finally:
        await engine.dispose()


async def _alembic_version_column_length(database_url: URL) -> int:
    engine = create_async_engine(database_url, poolclass=NullPool)
    try:
        async with engine.connect() as connection:
            value = await connection.scalar(
                text(
                    "select character_maximum_length "
                    "from information_schema.columns "
                    "where table_schema = current_schema() "
                    "and table_name = 'alembic_version' and column_name = 'version_num'"
                )
            )
            assert value is not None
            return int(value)
    finally:
        await engine.dispose()


async def _schema_diffs(database_url: URL) -> list[object]:
    engine = create_async_engine(database_url, poolclass=NullPool)
    try:
        async with engine.connect() as connection:
            return await connection.run_sync(_compare_live_schema)
    finally:
        await engine.dispose()


def _compare_live_schema(sync_connection) -> list[object]:
    migration_context = MigrationContext.configure(
        sync_connection,
        opts={
            "compare_server_default": True,
            "compare_type": True,
            "target_metadata": Base.metadata,
        },
    )
    return compare_metadata(migration_context, Base.metadata)


async def _catalog_snapshot(database_url: URL) -> dict[str, object]:
    engine = create_async_engine(database_url, poolclass=NullPool)
    try:
        async with engine.connect() as connection:
            server_version_num = int(
                await connection.scalar(text("select current_setting('server_version_num')"))
            )
            uuid_columns = await _typed_columns(connection, "uuid")
            timestamp_columns = await _typed_columns(connection, "timestamptz")
            alembic_version_column_length = await connection.scalar(
                text(
                    "select character_maximum_length "
                    "from information_schema.columns "
                    "where table_schema = current_schema() "
                    "and table_name = 'alembic_version' and column_name = 'version_num'"
                )
            )
            constraint_rows = (
                await connection.execute(
                    text(
                        "select c.relname as table_name, p.conname, p.contype::text as contype "
                        "from pg_constraint p "
                        "join pg_class c on c.oid = p.conrelid "
                        "join pg_namespace n on n.oid = c.relnamespace "
                        "where n.nspname = current_schema()"
                    )
                )
            ).mappings()
            constraints = [dict(row) for row in constraint_rows]
    finally:
        await engine.dispose()

    return {
        "server_version_num": server_version_num,
        "alembic_version_column_length": alembic_version_column_length,
        "uuid_columns": uuid_columns,
        "timestamp_columns": timestamp_columns,
        "check_constraints": {
            row["conname"] for row in constraints if row["contype"] == "c"
        },
        "unique_constraints": {
            row["conname"] for row in constraints if row["contype"] == "u"
        },
        "foreign_key_counts": {
            table_name: sum(
                row["table_name"] == table_name and row["contype"] == "f"
                for row in constraints
            )
            for table_name in EXPECTED_FOREIGN_KEY_COUNTS
        },
    }


async def _typed_columns(
    connection: AsyncConnection,
    postgres_type_name: str,
) -> set[tuple[str, str]]:
    rows = await connection.execute(
        text(
            "select table_name, column_name "
            "from information_schema.columns "
            "where table_schema = current_schema() and udt_name = :postgres_type_name"
        ),
        {"postgres_type_name": postgres_type_name},
    )
    return {(row.table_name, row.column_name) for row in rows}


async def _assert_constraints_reject_invalid_rows(database_url: URL) -> None:
    engine = create_async_engine(database_url, poolclass=NullPool)
    unique_slug = f"p0a-{uuid4().hex}"
    valid_tenant_id = uuid4()
    try:
        await _expect_constraint_error(
            engine,
            """
            insert into tenants (
                id, slug, name, status, plan_code, data_region, locale, timezone
            ) values (
                :id, :slug, 'Invalid status tenant', 'invalid', 'core', 'tr-1',
                'tr-TR', 'Europe/Istanbul'
            )
            """,
            {"id": uuid4(), "slug": f"invalid-{uuid4().hex}"},
            "ck_tenants_status",
        )
        for invalid_limit in (0, 1_000_001):
            await _expect_constraint_error(
                engine,
                """
                insert into tenants (
                    id, slug, name, status, plan_code, data_region, locale, timezone,
                    active_employee_limit
                ) values (
                    :id, :slug, 'Invalid limit tenant', 'active', 'core', 'tr-1',
                    'tr-TR', 'Europe/Istanbul', :active_employee_limit
                )
                """,
                {
                    "id": uuid4(),
                    "slug": f"invalid-limit-{uuid4().hex}",
                    "active_employee_limit": invalid_limit,
                },
                "ck_tenants_active_employee_limit_positive",
            )
        await _expect_constraint_error(
            engine,
            """
            insert into users (id, tenant_id, email, full_name, status)
            values (:id, :tenant_id, :email, 'Missing tenant user', 'active')
            """,
            {
                "id": uuid4(),
                "tenant_id": uuid4(),
                "email": f"missing-{uuid4().hex}@example.test",
            },
            "users_tenant_id_fkey",
        )
        await _expect_constraint_error(
            engine,
            """
            insert into tenant_settings (
                tenant_id, week_start_day, date_format, time_format
            ) values (
                :tenant_id, 'monday', 'DD.MM.YYYY', '24h'
            )
            """,
            {"tenant_id": uuid4()},
            "fk_tenant_settings_tenant_id_tenants",
        )

        async with engine.begin() as connection:
            await connection.execute(
                text(
                    """
                    insert into tenants (
                        id, slug, name, status, plan_code, data_region, locale, timezone
                    ) values (
                        :id, :slug, 'Unique tenant', 'active', 'core', 'tr-1',
                        'tr-TR', 'Europe/Istanbul'
                    )
                    """
                ),
                {"id": valid_tenant_id, "slug": unique_slug},
            )

        await _expect_constraint_error(
            engine,
            """
            insert into tenant_feature_flags (tenant_id, key, enabled)
            values (:tenant_id, 'payroll', false)
            """,
            {"tenant_id": valid_tenant_id},
            "ck_tenant_feature_flags_key",
        )
        await _expect_constraint_error(
            engine,
            """
            insert into tenant_feature_flags (tenant_id, key, enabled)
            values (:tenant_id, 'organization', false)
            """,
            {"tenant_id": uuid4()},
            "fk_tenant_feature_flags_tenant_id_tenants",
        )

        for week_start_day, date_format, time_format, constraint_name in (
            (
                "friday",
                "DD.MM.YYYY",
                "24h",
                "ck_tenant_settings_week_start_day",
            ),
            (
                "monday",
                "DD/MM/YYYY",
                "24h",
                "ck_tenant_settings_date_format",
            ),
            (
                "monday",
                "DD.MM.YYYY",
                "military",
                "ck_tenant_settings_time_format",
            ),
        ):
            await _expect_constraint_error(
                engine,
                """
                insert into tenant_settings (
                    tenant_id, week_start_day, date_format, time_format
                ) values (
                    :tenant_id, :week_start_day, :date_format, :time_format
                )
                """,
                {
                    "tenant_id": valid_tenant_id,
                    "week_start_day": week_start_day,
                    "date_format": date_format,
                    "time_format": time_format,
                },
                constraint_name,
            )

        await _expect_constraint_error(
            engine,
            """
            insert into tenants (
                id, slug, name, status, plan_code, data_region, locale, timezone
            ) values (
                :id, :slug, 'Duplicate tenant', 'active', 'core', 'tr-1',
                'tr-TR', 'Europe/Istanbul'
            )
            """,
            {"id": uuid4(), "slug": unique_slug},
            "tenants_slug_key",
        )
    finally:
        await engine.dispose()


async def _expect_constraint_error(
    engine,
    sql: str,
    parameters: dict[str, object],
    constraint_name: str,
) -> None:
    with pytest.raises(IntegrityError) as error:
        async with engine.begin() as connection:
            await connection.execute(text(sql), parameters)

    assert constraint_name in str(error.value)


async def _assert_runtime_configuration(database_url: URL) -> None:
    runtime = create_database_runtime(
        Settings(
            _env_file=None,
            environment="test",
            database_url=_render_database_url(database_url),
            database_pool_size=2,
            database_max_overflow=1,
            database_pool_timeout_seconds=0.05,
            database_pool_recycle_seconds=60,
            database_connect_timeout_seconds=5,
            database_statement_timeout_ms=4321,
            database_idle_transaction_timeout_ms=9876,
        )
    )
    connections = []
    try:
        assert runtime.engine.pool.size() == 2
        assert runtime.engine.pool.timeout() == pytest.approx(0.05)

        connections = [await runtime.engine.connect() for _ in range(3)]
        timeout_values = (
            await connections[0].execute(
                text(
                    "select current_setting('statement_timeout'), "
                    "current_setting('idle_in_transaction_session_timeout')"
                )
            )
        ).one()
        assert timeout_values == ("4321ms", "9876ms")

        with pytest.raises(SqlAlchemyTimeoutError):
            await runtime.engine.connect()
    finally:
        for connection in reversed(connections):
            await connection.close()
        await runtime.dispose()
