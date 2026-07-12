from __future__ import annotations

from pathlib import Path
from uuid import UUID

import pytest
from alembic import command as alembic_command
from alembic.config import Config
from app.platform.authorization import (
    PERMISSIONS,
    ROLE_PERMISSION_CODES,
    ROLES,
    ROLES_BY_CODE,
)
from app.platform.db import sqlstate_from_error
from app.platform.db.tenant_access import (
    PLATFORM_APPLICATION_ROLE,
    TENANT_APPLICATION_ROLE,
)
from sqlalchemy import text
from sqlalchemy.engine import URL
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import (
    AsyncConnection,
    AsyncEngine,
    create_async_engine,
)
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
CATALOG_TABLES = ("roles", "permissions", "role_permissions")
TENANT_A_ID = UUID("81000000-0000-4000-8000-000000000001")
TENANT_B_ID = UUID("81000000-0000-4000-8000-000000000002")
USER_A_ID = UUID("82000000-0000-4000-8000-000000000001")
USER_B_ID = UUID("82000000-0000-4000-8000-000000000002")


@pytest.fixture
def f2d_postgres_database(postgres_database_url: URL) -> URL:
    alembic_command.upgrade(_alembic_config(postgres_database_url), "head")
    return postgres_database_url


async def test_rbac_catalog_is_seeded_read_only_and_assignments_are_force_rls(
    f2d_postgres_database: URL,
) -> None:
    engine = create_async_engine(f2d_postgres_database, poolclass=NullPool)
    try:
        async with engine.connect() as connection:
            assert set(
                (await connection.execute(text("select code, scope_type from roles"))).tuples()
            ) == {(role.code, role.scope_type.value) for role in ROLES}
            assert set(await connection.scalars(text("select code from permissions"))) == {
                permission.code for permission in PERMISSIONS
            }
            assert await connection.scalar(text("select count(*) from role_permissions")) == sum(
                len(permission_codes)
                for permission_codes in ROLE_PERMISSION_CODES.values()
            )

            security = (
                await connection.execute(
                    text(
                        "select c.relrowsecurity, c.relforcerowsecurity "
                        "from pg_catalog.pg_class c "
                        "join pg_catalog.pg_namespace n on n.oid = c.relnamespace "
                        "where n.nspname = 'public' and c.relname = 'user_roles'"
                    )
                )
            ).one()
            assert security == (True, True)

            policy = (
                await connection.execute(
                    text(
                        "select policyname, roles, cmd, qual, with_check "
                        "from pg_catalog.pg_policies "
                        "where schemaname = 'public' and tablename = 'user_roles' "
                        "and policyname = 'tenant_isolation_app'"
                    )
                )
            ).mappings().one()
            assert policy["policyname"] == "tenant_isolation_app"
            assert tuple(policy["roles"]) == (TENANT_APPLICATION_ROLE,)
            assert policy["cmd"] == "ALL"
            assert "tenant_id" in policy["qual"]
            assert "app.tenant_id" in policy["qual"]
            assert policy["with_check"] == policy["qual"]

            for table_name in CATALOG_TABLES:
                for role_name in (
                    TENANT_APPLICATION_ROLE,
                    PLATFORM_APPLICATION_ROLE,
                ):
                    assert await _granted_privileges(
                        connection,
                        role_name=role_name,
                        table_name=table_name,
                    ) == {"SELECT"}
            assert await _granted_privileges(
                connection,
                role_name=TENANT_APPLICATION_ROLE,
                table_name="user_roles",
            ) == {"SELECT", "INSERT", "UPDATE"}
            assert await _granted_privileges(
                connection,
                role_name=PLATFORM_APPLICATION_ROLE,
                table_name="user_roles",
            ) == set()
            assert await _has_column_privilege(
                connection,
                role_name=TENANT_APPLICATION_ROLE,
                table_name="users",
                column_name="permission_version",
                privilege="UPDATE",
            ) is True
            assert await _has_column_privilege(
                connection,
                role_name=PLATFORM_APPLICATION_ROLE,
                table_name="users",
                column_name="permission_version",
                privilege="UPDATE",
            ) is False

        for role_name in (TENANT_APPLICATION_ROLE, PLATFORM_APPLICATION_ROLE):
            with pytest.raises(DBAPIError) as catalog_write:
                async with engine.begin() as connection:
                    await _set_local_role(connection, role_name)
                    await connection.execute(
                        text("update roles set name = name where code = 'employee'")
                    )
            assert sqlstate_from_error(catalog_write.value) == "42501"
    finally:
        await engine.dispose()


async def test_user_role_and_permission_version_writes_are_tenant_isolated(
    f2d_postgres_database: URL,
) -> None:
    engine = create_async_engine(f2d_postgres_database, poolclass=NullPool)
    try:
        await _seed_tenant_users_and_assignments(engine)
        employee_role_id = ROLES_BY_CODE["employee"].id
        manager_role_id = ROLES_BY_CODE["manager"].id

        async with engine.begin() as connection:
            await _set_local_tenant_role(connection, TENANT_A_ID)
            assert (
                await connection.execute(
                    text(
                        "select user_id, role_id, active from user_roles order by role_id"
                    )
                )
            ).all() == [(USER_A_ID, employee_role_id, True)]

            await connection.execute(
                text(
                    "insert into user_roles ("
                    "tenant_id, user_id, role_id, role_scope_type, active"
                    ") values (:tenant_id, :user_id, :role_id, 'tenant', true)"
                ),
                {
                    "tenant_id": TENANT_A_ID,
                    "user_id": USER_A_ID,
                    "role_id": manager_role_id,
                },
            )
            own_update = await connection.execute(
                text(
                    "update user_roles set active = false, updated_at = CURRENT_TIMESTAMP "
                    "where tenant_id = :tenant_id and user_id = :user_id "
                    "and role_id = :role_id"
                ),
                {
                    "tenant_id": TENANT_A_ID,
                    "user_id": USER_A_ID,
                    "role_id": employee_role_id,
                },
            )
            hidden_update = await connection.execute(
                text(
                    "update user_roles set active = false "
                    "where tenant_id = :tenant_id and user_id = :user_id"
                ),
                {"tenant_id": TENANT_B_ID, "user_id": USER_B_ID},
            )
            own_permission_version = await connection.execute(
                text(
                    "update users set permission_version = permission_version + 1 "
                    "where tenant_id = :tenant_id and id = :user_id"
                ),
                {"tenant_id": TENANT_A_ID, "user_id": USER_A_ID},
            )
            hidden_permission_version = await connection.execute(
                text(
                    "update users set permission_version = permission_version + 1 "
                    "where tenant_id = :tenant_id and id = :user_id"
                ),
                {"tenant_id": TENANT_B_ID, "user_id": USER_B_ID},
            )
            assert own_update.rowcount == 1
            assert hidden_update.rowcount == 0
            assert own_permission_version.rowcount == 1
            assert hidden_permission_version.rowcount == 0

        async with engine.begin() as connection:
            await _set_local_tenant_role(connection, TENANT_B_ID)
            assert (
                await connection.execute(
                    text("select user_id, role_id, active from user_roles")
                )
            ).all() == [(USER_B_ID, employee_role_id, True)]

        with pytest.raises(DBAPIError) as cross_tenant_insert:
            async with engine.begin() as connection:
                await _set_local_tenant_role(connection, TENANT_A_ID)
                await connection.execute(
                    text(
                        "insert into user_roles ("
                        "tenant_id, user_id, role_id, role_scope_type, active"
                        ") values (:tenant_id, :user_id, :role_id, 'tenant', true)"
                    ),
                    {
                        "tenant_id": TENANT_B_ID,
                        "user_id": USER_B_ID,
                        "role_id": manager_role_id,
                    },
                )
        assert sqlstate_from_error(cross_tenant_insert.value) == "42501"

        with pytest.raises(DBAPIError) as platform_assignment_read:
            async with engine.begin() as connection:
                await _set_local_role(connection, PLATFORM_APPLICATION_ROLE)
                await connection.execute(text("select user_id from user_roles"))
        assert sqlstate_from_error(platform_assignment_read.value) == "42501"

        with pytest.raises(DBAPIError) as platform_role_assignment:
            async with engine.begin() as connection:
                await _set_local_tenant_role(connection, TENANT_A_ID)
                await connection.execute(
                    text(
                        "insert into user_roles ("
                        "tenant_id, user_id, role_id, role_scope_type, active"
                        ") values (:tenant_id, :user_id, :role_id, 'tenant', true)"
                    ),
                    {
                        "tenant_id": TENANT_A_ID,
                        "user_id": USER_A_ID,
                        "role_id": ROLES_BY_CODE["super_admin"].id,
                    },
                )
        assert sqlstate_from_error(platform_role_assignment.value) == "23503"

        async with engine.connect() as connection:
            permission_versions = dict(
                list(
                    (
                        await connection.execute(
                            text("select id, permission_version from users order by id")
                        )
                    ).tuples()
                )
            )
            assignments = set(
                (
                    await connection.execute(
                        text(
                            "select tenant_id, user_id, role_id, active "
                            "from user_roles"
                        )
                    )
                ).tuples()
            )
        assert permission_versions == {USER_A_ID: 2, USER_B_ID: 1}
        assert assignments == {
            (TENANT_A_ID, USER_A_ID, employee_role_id, False),
            (TENANT_A_ID, USER_A_ID, manager_role_id, True),
            (TENANT_B_ID, USER_B_ID, employee_role_id, True),
        }
    finally:
        await engine.dispose()


def _alembic_config(database_url: URL) -> Config:
    config = Config(str(ALEMBIC_INI))
    config.set_main_option(
        "sqlalchemy.url",
        database_url.render_as_string(hide_password=False).replace("%", "%%"),
    )
    return config


async def _seed_tenant_users_and_assignments(engine: AsyncEngine) -> None:
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
                {"id": TENANT_A_ID, "slug": "f2d-pg-tenant-a", "name": "Tenant A"},
                {"id": TENANT_B_ID, "slug": "f2d-pg-tenant-b", "name": "Tenant B"},
            ],
        )
        await connection.execute(
            text(
                "insert into users ("
                "id, tenant_id, email, full_name, status"
                ") values (:id, :tenant_id, :email, :full_name, 'active')"
            ),
            [
                {
                    "id": USER_A_ID,
                    "tenant_id": TENANT_A_ID,
                    "email": "rbac-a@example.test",
                    "full_name": "RBAC A",
                },
                {
                    "id": USER_B_ID,
                    "tenant_id": TENANT_B_ID,
                    "email": "rbac-b@example.test",
                    "full_name": "RBAC B",
                },
            ],
        )
        await connection.execute(
            text(
                "insert into user_roles ("
                "tenant_id, user_id, role_id, role_scope_type, active"
                ") values (:tenant_id, :user_id, :role_id, 'tenant', true)"
            ),
            [
                {
                    "tenant_id": TENANT_A_ID,
                    "user_id": USER_A_ID,
                    "role_id": ROLES_BY_CODE["employee"].id,
                },
                {
                    "tenant_id": TENANT_B_ID,
                    "user_id": USER_B_ID,
                    "role_id": ROLES_BY_CODE["employee"].id,
                },
            ],
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
            text(
                "select has_table_privilege("
                ":role_name, :relation_name, :privilege"
                ")"
            ),
            {
                "role_name": role_name,
                "relation_name": f"public.{table_name}",
                "privilege": privilege,
            },
        ):
            privileges.add(privilege)
    return privileges


async def _has_column_privilege(
    connection: AsyncConnection,
    *,
    role_name: str,
    table_name: str,
    column_name: str,
    privilege: str,
) -> bool:
    return bool(
        await connection.scalar(
            text(
                "select has_column_privilege("
                ":role_name, :relation_name, :column_name, :privilege"
                ")"
            ),
            {
                "role_name": role_name,
                "relation_name": f"public.{table_name}",
                "column_name": column_name,
                "privilege": privilege,
            },
        )
    )


async def _set_local_tenant_role(
    connection: AsyncConnection,
    tenant_id: UUID,
) -> None:
    await _set_local_role(connection, TENANT_APPLICATION_ROLE)
    await connection.exec_driver_sql(f"SET LOCAL app.tenant_id = '{tenant_id}'")


async def _set_local_role(connection: AsyncConnection, role_name: str) -> None:
    await connection.exec_driver_sql(f'SET LOCAL ROLE "{role_name}"')
    assert await connection.scalar(text("select current_user")) == role_name
