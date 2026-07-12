from __future__ import annotations

from pathlib import Path
from uuid import UUID

import pytest
from alembic import command as alembic_command
from alembic.config import Config
from app.platform.authorization import PERMISSIONS_BY_CODE, ROLES_BY_CODE
from app.platform.db import sqlstate_from_error
from app.platform.db.tenant_access import (
    PLATFORM_APPLICATION_ROLE,
    TENANT_APPLICATION_ROLE,
)
from sqlalchemy import text
from sqlalchemy.engine import URL
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, create_async_engine
from sqlalchemy.pool import NullPool

pytestmark = pytest.mark.postgres

ROOT = Path(__file__).resolve().parents[3]
ALEMBIC_INI = ROOT / "alembic.ini"

TABLE_PRIVILEGES = (
    "SELECT",
    "INSERT",
    "UPDATE",
    "DELETE",
    "TRUNCATE",
    "REFERENCES",
    "TRIGGER",
)
TENANT_A_ID = UUID("91000000-0000-4000-8000-000000000001")
TENANT_B_ID = UUID("91000000-0000-4000-8000-000000000002")
TENANT_A_EVENT_ID = UUID("92000000-0000-4000-8000-000000000001")
TENANT_B_EVENT_ID = UUID("92000000-0000-4000-8000-000000000002")
PLATFORM_EVENT_ID = UUID("92000000-0000-4000-8000-000000000003")


@pytest.fixture
def f2e_postgres_database(postgres_database_url: URL) -> URL:
    alembic_command.upgrade(
        _alembic_config(postgres_database_url),
        "0020_f2e_audit_events",
    )
    return postgres_database_url


async def test_audit_runtime_privileges_are_append_only_and_catalog_grants_are_seeded(
    f2e_postgres_database: URL,
) -> None:
    engine = create_async_engine(f2e_postgres_database, poolclass=NullPool)
    try:
        async with engine.connect() as connection:
            security = (
                await connection.execute(
                    text(
                        "select c.relrowsecurity, c.relforcerowsecurity "
                        "from pg_catalog.pg_class c "
                        "join pg_catalog.pg_namespace n on n.oid = c.relnamespace "
                        "where n.nspname = 'public' and c.relname = 'audit_events'"
                    )
                )
            ).one()
            assert security == (True, True)

            policies = {
                row["policyname"]: row
                for row in (
                    await connection.execute(
                        text(
                            "select policyname, roles, cmd, qual, with_check "
                            "from pg_catalog.pg_policies "
                            "where schemaname = 'public' and tablename = 'audit_events'"
                        )
                    )
                ).mappings()
            }
            assert set(policies) == {
                "tenant_audit_isolation_app",
                "platform_audit_isolation_app",
            }
            tenant_policy = policies["tenant_audit_isolation_app"]
            assert tuple(tenant_policy["roles"]) == (TENANT_APPLICATION_ROLE,)
            assert tenant_policy["cmd"] == "ALL"
            assert "app.tenant_id" in tenant_policy["qual"]
            assert "scope_type" in tenant_policy["qual"]
            assert tenant_policy["with_check"] == tenant_policy["qual"]
            platform_policy = policies["platform_audit_isolation_app"]
            assert tuple(platform_policy["roles"]) == (PLATFORM_APPLICATION_ROLE,)
            assert platform_policy["cmd"] == "ALL"
            assert "scope_type" in platform_policy["qual"]
            assert "tenant_id IS NULL" in platform_policy["qual"]
            assert platform_policy["with_check"] == platform_policy["qual"]

            for role_name in (TENANT_APPLICATION_ROLE, PLATFORM_APPLICATION_ROLE):
                assert await _granted_privileges(
                    connection,
                    role_name=role_name,
                    table_name="audit_events",
                ) == {"SELECT", "INSERT"}

            platform_audit_id = await connection.scalar(
                text("select id from permissions where code = 'audit:read:platform'")
            )
            assert platform_audit_id == PERMISSIONS_BY_CODE["audit:read:platform"].id
            grants = set(
                (
                    await connection.execute(
                        text(
                            "select role_id, permission_id from role_permissions "
                            "where permission_id in (:tenant_audit_id, :platform_audit_id)"
                        ),
                        {
                            "tenant_audit_id": PERMISSIONS_BY_CODE["audit:read:tenant"].id,
                            "platform_audit_id": platform_audit_id,
                        },
                    )
                ).tuples()
            )
            assert grants == {
                (
                    ROLES_BY_CODE["super_admin"].id,
                    PERMISSIONS_BY_CODE["audit:read:platform"].id,
                ),
                (
                    ROLES_BY_CODE["tenant_admin"].id,
                    PERMISSIONS_BY_CODE["audit:read:tenant"].id,
                ),
                (
                    ROLES_BY_CODE["hr_director"].id,
                    PERMISSIONS_BY_CODE["audit:read:tenant"].id,
                ),
                (
                    ROLES_BY_CODE["it_admin"].id,
                    PERMISSIONS_BY_CODE["audit:read:tenant"].id,
                ),
                (
                    ROLES_BY_CODE["auditor"].id,
                    PERMISSIONS_BY_CODE["audit:read:tenant"].id,
                ),
            }

        await _seed_tenants(engine)
        async with engine.begin() as connection:
            await _set_local_tenant_role(connection, TENANT_A_ID)
            await _insert_tenant_event(connection, TENANT_A_EVENT_ID, TENANT_A_ID)
        async with engine.begin() as connection:
            await _set_local_tenant_role(connection, TENANT_B_ID)
            await _insert_tenant_event(connection, TENANT_B_EVENT_ID, TENANT_B_ID)
        async with engine.begin() as connection:
            await _set_local_role(connection, PLATFORM_APPLICATION_ROLE)
            await _insert_platform_event(connection, PLATFORM_EVENT_ID)

        for role_name, tenant_id, event_id in (
            (TENANT_APPLICATION_ROLE, TENANT_A_ID, TENANT_A_EVENT_ID),
            (PLATFORM_APPLICATION_ROLE, None, PLATFORM_EVENT_ID),
        ):
            with pytest.raises(DBAPIError) as update_error:
                async with engine.begin() as connection:
                    if tenant_id is None:
                        await _set_local_role(connection, role_name)
                    else:
                        await _set_local_tenant_role(connection, tenant_id)
                    await connection.execute(
                        text("update audit_events set severity = 'warning' where id = :id"),
                        {"id": event_id},
                    )
            assert sqlstate_from_error(update_error.value) == "42501"

            with pytest.raises(DBAPIError) as delete_error:
                async with engine.begin() as connection:
                    if tenant_id is None:
                        await _set_local_role(connection, role_name)
                    else:
                        await _set_local_tenant_role(connection, tenant_id)
                    await connection.execute(
                        text("delete from audit_events where id = :id"),
                        {"id": event_id},
                    )
            assert sqlstate_from_error(delete_error.value) == "42501"
    finally:
        await engine.dispose()


async def test_audit_rls_separates_tenants_and_platform_scope(
    f2e_postgres_database: URL,
) -> None:
    engine = create_async_engine(f2e_postgres_database, poolclass=NullPool)
    try:
        await _seed_tenants(engine)
        async with engine.begin() as connection:
            await _set_local_tenant_role(connection, TENANT_A_ID)
            await _insert_tenant_event(connection, TENANT_A_EVENT_ID, TENANT_A_ID)
        async with engine.begin() as connection:
            await _set_local_tenant_role(connection, TENANT_B_ID)
            await _insert_tenant_event(connection, TENANT_B_EVENT_ID, TENANT_B_ID)
        async with engine.begin() as connection:
            await _set_local_role(connection, PLATFORM_APPLICATION_ROLE)
            await _insert_platform_event(connection, PLATFORM_EVENT_ID)

        async with engine.begin() as connection:
            await _set_local_tenant_role(connection, TENANT_A_ID)
            assert list(await connection.scalars(text("select id from audit_events"))) == [
                TENANT_A_EVENT_ID
            ]
        async with engine.begin() as connection:
            await _set_local_tenant_role(connection, TENANT_B_ID)
            assert list(await connection.scalars(text("select id from audit_events"))) == [
                TENANT_B_EVENT_ID
            ]
        async with engine.begin() as connection:
            await _set_local_role(connection, PLATFORM_APPLICATION_ROLE)
            assert list(await connection.scalars(text("select id from audit_events"))) == [
                PLATFORM_EVENT_ID
            ]

        with pytest.raises(DBAPIError) as cross_tenant_insert:
            async with engine.begin() as connection:
                await _set_local_tenant_role(connection, TENANT_A_ID)
                await _insert_tenant_event(
                    connection,
                    UUID("92000000-0000-4000-8000-000000000004"),
                    TENANT_B_ID,
                )
        assert sqlstate_from_error(cross_tenant_insert.value) == "42501"

        with pytest.raises(DBAPIError) as tenant_platform_insert:
            async with engine.begin() as connection:
                await _set_local_tenant_role(connection, TENANT_A_ID)
                await _insert_platform_event(
                    connection,
                    UUID("92000000-0000-4000-8000-000000000005"),
                )
        assert sqlstate_from_error(tenant_platform_insert.value) == "42501"

        with pytest.raises(DBAPIError) as platform_tenant_insert:
            async with engine.begin() as connection:
                await _set_local_role(connection, PLATFORM_APPLICATION_ROLE)
                await _insert_tenant_event(
                    connection,
                    UUID("92000000-0000-4000-8000-000000000006"),
                    TENANT_A_ID,
                )
        assert sqlstate_from_error(platform_tenant_insert.value) == "42501"
    finally:
        await engine.dispose()


def _alembic_config(database_url: URL) -> Config:
    config = Config(str(ALEMBIC_INI))
    config.set_main_option(
        "sqlalchemy.url",
        database_url.render_as_string(hide_password=False).replace("%", "%%"),
    )
    return config


async def _seed_tenants(engine: AsyncEngine) -> None:
    async with engine.begin() as connection:
        await connection.execute(
            text(
                "insert into tenants ("
                "id, slug, name, status, plan_code, data_region, locale, timezone"
                ") values ("
                ":id, :slug, :name, 'active', 'core', 'tr-1', 'en-US', 'UTC'"
                ")"
            ),
            [
                {"id": TENANT_A_ID, "slug": "f2e-pg-tenant-a", "name": "Tenant A"},
                {"id": TENANT_B_ID, "slug": "f2e-pg-tenant-b", "name": "Tenant B"},
            ],
        )


async def _insert_tenant_event(
    connection: AsyncConnection,
    event_id: UUID,
    tenant_id: UUID,
) -> None:
    await _insert_audit_event(
        connection,
        event_id=event_id,
        scope_type="tenant",
        tenant_id=tenant_id,
        event_type="auth.login.succeeded",
        category="tenant_security",
    )


async def _insert_platform_event(connection: AsyncConnection, event_id: UUID) -> None:
    await _insert_audit_event(
        connection,
        event_id=event_id,
        scope_type="platform",
        tenant_id=None,
        event_type="platform.tenant.created",
        category="platform_operations",
    )


async def _insert_audit_event(
    connection: AsyncConnection,
    *,
    event_id: UUID,
    scope_type: str,
    tenant_id: UUID | None,
    event_type: str,
    category: str,
) -> None:
    await connection.execute(
        text(
            "insert into audit_events ("
            "id, occurred_at, scope_type, tenant_id, actor_type, event_type, category, "
            "severity, action, result, request_id, trace_id, changed_fields, before_data, "
            "after_data, metadata, data_classification, visibility_class"
            ") values ("
            ":id, CURRENT_TIMESTAMP, :scope_type, :tenant_id, 'system', :event_type, "
            ":category, 'info', 'record', 'success', :request_id, "
            "'0123456789abcdef0123456789abcdef', '[]'::jsonb, '{}'::jsonb, '{}'::jsonb, "
            "'{}'::jsonb, 'security_metadata', :visibility_class"
            ")"
        ),
        {
            "id": event_id,
            "scope_type": scope_type,
            "tenant_id": tenant_id,
            "event_type": event_type,
            "category": category,
            "request_id": f"req_{str(event_id).replace('-', '')}",
            "visibility_class": ("platform_ops" if scope_type == "platform" else "tenant_security"),
        },
    )


async def _granted_privileges(
    connection: AsyncConnection,
    *,
    role_name: str,
    table_name: str,
) -> set[str]:
    privileges: set[str] = set()
    for privilege in TABLE_PRIVILEGES:
        if await connection.scalar(
            text("select has_table_privilege(:role_name, :relation_name, :privilege)"),
            {
                "role_name": role_name,
                "relation_name": f"public.{table_name}",
                "privilege": privilege,
            },
        ):
            privileges.add(privilege)
    return privileges


async def _set_local_tenant_role(
    connection: AsyncConnection,
    tenant_id: UUID,
) -> None:
    await _set_local_role(connection, TENANT_APPLICATION_ROLE)
    await connection.exec_driver_sql(f"SET LOCAL app.tenant_id = '{tenant_id}'")


async def _set_local_role(connection: AsyncConnection, role_name: str) -> None:
    await connection.exec_driver_sql(f'SET LOCAL ROLE "{role_name}"')
    assert await connection.scalar(text("select current_user")) == role_name
