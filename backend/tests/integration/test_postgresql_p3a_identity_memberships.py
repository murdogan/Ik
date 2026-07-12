from __future__ import annotations

import asyncio
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from alembic import command as alembic_command
from alembic.config import Config
from app.platform.authorization import ROLES_BY_CODE
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
PRE_P3A_REVISION = "0021_f2f_user_insert_grant"
P3A_REVISION = "0022_p3a_identity_memberships"

TENANT_A_ID = UUID("f1000000-0000-4000-8000-000000000001")
TENANT_B_ID = UUID("f1000000-0000-4000-8000-000000000002")
DEMO_ADMIN_ID = UUID("f2000000-0000-4000-8000-000000000001")
SHARED_CANONICAL_USER_ID = UUID("12000000-0000-4000-8000-000000000001")
SHARED_OTHER_USER_ID = UUID("22000000-0000-4000-8000-000000000002")
SHARED_EMAIL_NORMALIZED = "shared.person@example.test"
SHARED_PASSWORD_HASH = "shared-legacy-password-hash"
DEMO_PASSWORD_HASH = "demo-admin-password-hash"


@pytest.fixture
def p3a_postgres_database(postgres_database_url: URL) -> URL:
    config = _alembic_config(postgres_database_url)
    alembic_command.upgrade(config, PRE_P3A_REVISION)
    asyncio.run(_seed_mergeable_legacy_projection(postgres_database_url))
    alembic_command.upgrade(config, "head")
    return postgres_database_url


async def test_p3a_backfill_is_deterministic_isolated_and_relationally_safe(
    p3a_postgres_database: URL,
) -> None:
    engine = create_async_engine(p3a_postgres_database, poolclass=NullPool)
    try:
        async with engine.connect() as connection:
            identities = (
                await connection.execute(
                    text(
                        "select id, email, email_normalized, status, password_hash "
                        "from identities order by email_normalized"
                    )
                )
            ).all()
            memberships = (
                await connection.execute(
                    text(
                        "select id, tenant_id, identity_id, legacy_user_id, full_name, "
                        "status, permission_version from tenant_memberships "
                        "order by tenant_id, id"
                    )
                )
            ).all()
            membership_roles = set(
                (
                    await connection.execute(
                        text(
                            "select tenant_id, membership_id, role_id, role_scope_type, active "
                            "from membership_roles"
                        )
                    )
                ).tuples()
            )
            legacy_users = (
                await connection.execute(
                    text(
                        "select id, tenant_id, email, full_name, status, password_hash, "
                        "permission_version from users order by id"
                    )
                )
            ).all()

            security = {
                row.relname: (row.relrowsecurity, row.relforcerowsecurity)
                for row in (
                    await connection.execute(
                        text(
                            "select c.relname, c.relrowsecurity, c.relforcerowsecurity "
                            "from pg_catalog.pg_class c "
                            "join pg_catalog.pg_namespace n on n.oid = c.relnamespace "
                            "where n.nspname = 'public' "
                            "and c.relname = any(:table_names)"
                        ),
                        {
                            "table_names": [
                                "identities",
                                "tenant_memberships",
                                "membership_roles",
                            ]
                        },
                    )
                ).mappings()
            }
            identity_policy_count = await connection.scalar(
                text(
                    "select count(*) from pg_catalog.pg_policies "
                    "where schemaname = 'public' and tablename = 'identities'"
                )
            )

        assert identities == [
            (
                DEMO_ADMIN_ID,
                "admin@wealthyfalcon.demo",
                "admin@wealthyfalcon.demo",
                "active",
                DEMO_PASSWORD_HASH,
            ),
            (
                SHARED_CANONICAL_USER_ID,
                SHARED_EMAIL_NORMALIZED,
                SHARED_EMAIL_NORMALIZED,
                "active",
                SHARED_PASSWORD_HASH,
            ),
        ]
        assert memberships == [
            (
                SHARED_OTHER_USER_ID,
                TENANT_A_ID,
                SHARED_CANONICAL_USER_ID,
                SHARED_OTHER_USER_ID,
                "Tenant A Shared Person",
                "invited",
                3,
            ),
            (
                DEMO_ADMIN_ID,
                TENANT_A_ID,
                DEMO_ADMIN_ID,
                DEMO_ADMIN_ID,
                "Maya Stone",
                "active",
                7,
            ),
            (
                SHARED_CANONICAL_USER_ID,
                TENANT_B_ID,
                SHARED_CANONICAL_USER_ID,
                SHARED_CANONICAL_USER_ID,
                "Tenant B Shared Person",
                "active",
                2,
            ),
        ]
        assert membership_roles == {
            (
                TENANT_A_ID,
                DEMO_ADMIN_ID,
                ROLES_BY_CODE["tenant_admin"].id,
                "tenant",
                True,
            ),
            (
                TENANT_A_ID,
                SHARED_OTHER_USER_ID,
                ROLES_BY_CODE["manager"].id,
                "tenant",
                True,
            ),
            (
                TENANT_B_ID,
                SHARED_CANONICAL_USER_ID,
                ROLES_BY_CODE["employee"].id,
                "tenant",
                True,
            ),
        }
        assert legacy_users == [
            (
                SHARED_CANONICAL_USER_ID,
                TENANT_B_ID,
                SHARED_EMAIL_NORMALIZED,
                "Tenant B Shared Person",
                "active",
                SHARED_PASSWORD_HASH,
                2,
            ),
            (
                SHARED_OTHER_USER_ID,
                TENANT_A_ID,
                " Shared.Person@Example.Test ",
                "Tenant A Shared Person",
                "invited",
                None,
                3,
            ),
            (
                DEMO_ADMIN_ID,
                TENANT_A_ID,
                "admin@wealthyfalcon.demo",
                "Maya Stone",
                "active",
                DEMO_PASSWORD_HASH,
                7,
            ),
        ]
        assert security == {
            "identities": (True, True),
            "tenant_memberships": (True, True),
            "membership_roles": (True, True),
        }
        assert identity_policy_count == 0

        await _assert_runtime_visibility_and_denials(engine)
        await _assert_uniqueness_and_composite_relationships(engine)
    finally:
        await engine.dispose()


def test_p3a_upgrade_refuses_conflicting_legacy_passwords_until_repaired(
    postgres_database_url: URL,
) -> None:
    config = _alembic_config(postgres_database_url)
    alembic_command.upgrade(config, PRE_P3A_REVISION)
    asyncio.run(_seed_conflicting_legacy_passwords(postgres_database_url))

    with pytest.raises(
        RuntimeError,
        match=(
            "P3A identity backfill preflight failed: "
            "conflicting_password_identities=1, blank_normalized_emails=0"
        ),
    ):
        alembic_command.upgrade(config, "head")

    assert asyncio.run(_current_revision(postgres_database_url)) == PRE_P3A_REVISION
    assert asyncio.run(_p3a_table_names(postgres_database_url)) == set()
    assert asyncio.run(_row_security_flags(postgres_database_url, "users")) == (
        True,
        True,
    )
    assert asyncio.run(_row_security_flags(postgres_database_url, "user_roles")) == (
        True,
        True,
    )

    asyncio.run(_repair_conflicting_legacy_passwords(postgres_database_url))
    alembic_command.upgrade(config, "head")

    assert asyncio.run(_current_revision(postgres_database_url)) == P3A_REVISION
    assert asyncio.run(_identity_projection(postgres_database_url)) == [
        (SHARED_CANONICAL_USER_ID, "active", SHARED_PASSWORD_HASH)
    ]
    assert asyncio.run(_membership_count(postgres_database_url)) == 2


def test_p3a_downgrade_refuses_a_new_unmergeable_legacy_credential(
    postgres_database_url: URL,
) -> None:
    config = _alembic_config(postgres_database_url)
    alembic_command.upgrade(config, PRE_P3A_REVISION)
    asyncio.run(_seed_mergeable_legacy_projection(postgres_database_url))
    alembic_command.upgrade(config, "head")
    asyncio.run(_introduce_lower_sorting_legacy_password(postgres_database_url))

    with pytest.raises(
        RuntimeError,
        match=(
            "P3A downgrade preflight failed: identity_drift=0, "
            "membership_drift=0, role_drift=0, "
            "conflicting_password_identities=1, blank_normalized_emails=0"
        ),
    ):
        alembic_command.downgrade(config, PRE_P3A_REVISION)

    assert asyncio.run(_current_revision(postgres_database_url)) == P3A_REVISION
    for table_name in (
        "users",
        "user_roles",
        "identities",
        "tenant_memberships",
        "membership_roles",
    ):
        assert asyncio.run(_row_security_flags(postgres_database_url, table_name)) == (
            True,
            True,
        )

    asyncio.run(_clear_invited_legacy_password(postgres_database_url))
    alembic_command.downgrade(config, PRE_P3A_REVISION)
    alembic_command.upgrade(config, "head")
    assert asyncio.run(_current_revision(postgres_database_url)) == P3A_REVISION


def test_p3a_downgrade_refuses_canonical_drift_and_preserves_legacy_repair_path(
    postgres_database_url: URL,
) -> None:
    config = _alembic_config(postgres_database_url)
    alembic_command.upgrade(config, PRE_P3A_REVISION)
    asyncio.run(_seed_mergeable_legacy_projection(postgres_database_url))
    alembic_command.upgrade(config, "head")
    asyncio.run(_drift_membership_name(postgres_database_url))

    with pytest.raises(
        RuntimeError,
        match=(
            "P3A downgrade preflight failed: identity_drift=0, "
            "membership_drift=1, role_drift=0"
        ),
    ):
        alembic_command.downgrade(config, PRE_P3A_REVISION)

    assert asyncio.run(_current_revision(postgres_database_url)) == P3A_REVISION
    assert asyncio.run(_p3a_table_names(postgres_database_url)) == {
        "identities",
        "tenant_memberships",
        "membership_roles",
    }
    for table_name in (
        "users",
        "user_roles",
        "identities",
        "tenant_memberships",
        "membership_roles",
    ):
        assert asyncio.run(_row_security_flags(postgres_database_url, table_name)) == (
            True,
            True,
        )

    asyncio.run(_repair_membership_names_from_legacy(postgres_database_url))
    alembic_command.downgrade(config, PRE_P3A_REVISION)

    assert asyncio.run(_current_revision(postgres_database_url)) == PRE_P3A_REVISION
    assert asyncio.run(_p3a_table_names(postgres_database_url)) == set()
    assert asyncio.run(_legacy_demo_admin_exists(postgres_database_url)) is True

    alembic_command.upgrade(config, "head")
    assert asyncio.run(_current_revision(postgres_database_url)) == P3A_REVISION
    assert asyncio.run(_membership_count(postgres_database_url)) == 3


async def _assert_runtime_visibility_and_denials(engine: AsyncEngine) -> None:
    async with engine.begin() as connection:
        await _set_local_tenant_role(connection, TENANT_A_ID)
        assert set(
            (
                await connection.execute(
                    text(
                        "select id, tenant_id, identity_id from tenant_memberships "
                        "order by id"
                    )
                )
            ).tuples()
        ) == {
            (SHARED_OTHER_USER_ID, TENANT_A_ID, SHARED_CANONICAL_USER_ID),
            (DEMO_ADMIN_ID, TENANT_A_ID, DEMO_ADMIN_ID),
        }
        assert set(
            (
                await connection.execute(
                    text("select tenant_id, membership_id from membership_roles")
                )
            ).tuples()
        ) == {
            (TENANT_A_ID, SHARED_OTHER_USER_ID),
            (TENANT_A_ID, DEMO_ADMIN_ID),
        }
        assert (
            await connection.scalar(
                text(
                    "select id from tenant_memberships "
                    "where tenant_id = :tenant_id"
                ),
                {"tenant_id": TENANT_B_ID},
            )
            is None
        )

    async with engine.begin() as connection:
        await _set_local_tenant_role(connection, TENANT_B_ID)
        assert tuple(
            await connection.scalars(
                text("select id from tenant_memberships order by id")
            )
        ) == (SHARED_CANONICAL_USER_ID,)
        assert tuple(
            await connection.scalars(
                text("select membership_id from membership_roles order by membership_id")
            )
        ) == (SHARED_CANONICAL_USER_ID,)

    with pytest.raises(DBAPIError) as identity_access:
        async with engine.begin() as connection:
            await _set_local_tenant_role(connection, TENANT_A_ID)
            await connection.execute(text("select id from identities"))
    assert sqlstate_from_error(identity_access.value) == "42501"

    with pytest.raises(DBAPIError) as membership_write:
        async with engine.begin() as connection:
            await _set_local_tenant_role(connection, TENANT_A_ID)
            await connection.execute(
                text(
                    "update tenant_memberships set full_name = full_name "
                    "where id = :membership_id"
                ),
                {"membership_id": DEMO_ADMIN_ID},
            )
    assert sqlstate_from_error(membership_write.value) == "42501"

    for table_name in ("identities", "tenant_memberships", "membership_roles"):
        with pytest.raises(DBAPIError) as platform_access:
            async with engine.begin() as connection:
                await _set_local_role(connection, PLATFORM_APPLICATION_ROLE)
                await connection.exec_driver_sql(f'SELECT 1 FROM "{table_name}" LIMIT 1')
        assert sqlstate_from_error(platform_access.value) == "42501"


async def _assert_uniqueness_and_composite_relationships(engine: AsyncEngine) -> None:
    with pytest.raises(DBAPIError) as duplicate_identity:
        async with engine.begin() as connection:
            await connection.execute(
                text(
                    "insert into identities (id, email, status, password_hash) "
                    "values (:id, ' SHARED.PERSON@example.test ', 'pending', NULL)"
                ),
                {"id": uuid4()},
            )
    assert sqlstate_from_error(duplicate_identity.value) == "23505"

    spare_user_id = uuid4()
    async with engine.begin() as connection:
        await connection.execute(
            text(
                "insert into users ("
                "id, tenant_id, email, full_name, status, password_hash, permission_version"
                ") values ("
                ":id, :tenant_id, :email, 'Spare Legacy User', 'invited', NULL, 1"
                ")"
            ),
            {
                "id": spare_user_id,
                "tenant_id": TENANT_A_ID,
                "email": f"spare-{spare_user_id}@example.test",
            },
        )

    with pytest.raises(DBAPIError) as duplicate_tenant_identity:
        async with engine.begin() as connection:
            await connection.execute(
                text(
                    "insert into tenant_memberships ("
                    "id, tenant_id, identity_id, legacy_user_id, full_name, status, "
                    "permission_version"
                    ") values ("
                    ":id, :tenant_id, :identity_id, :legacy_user_id, "
                    "'Duplicate Identity Membership', 'invited', 1"
                    ")"
                ),
                {
                    "id": uuid4(),
                    "tenant_id": TENANT_A_ID,
                    "identity_id": SHARED_CANONICAL_USER_ID,
                    "legacy_user_id": spare_user_id,
                },
            )
    assert sqlstate_from_error(duplicate_tenant_identity.value) == "23505"

    with pytest.raises(DBAPIError) as cross_tenant_membership_role:
        async with engine.begin() as connection:
            await connection.execute(
                text(
                    "insert into membership_roles ("
                    "tenant_id, membership_id, role_id, role_scope_type, active"
                    ") values ("
                    ":tenant_id, :membership_id, :role_id, 'tenant', true"
                    ")"
                ),
                {
                    "tenant_id": TENANT_A_ID,
                    "membership_id": SHARED_CANONICAL_USER_ID,
                    "role_id": ROLES_BY_CODE["manager"].id,
                },
            )
    assert sqlstate_from_error(cross_tenant_membership_role.value) == "23503"


async def _seed_mergeable_legacy_projection(database_url: URL) -> None:
    engine = create_async_engine(database_url, poolclass=NullPool)
    try:
        async with engine.begin() as connection:
            await _insert_tenants(connection)
            await connection.execute(
                text(
                    "insert into users ("
                    "id, tenant_id, email, full_name, status, password_hash, "
                    "can_invite_users, permission_version"
                    ") values ("
                    ":demo_id, :tenant_a, 'admin@wealthyfalcon.demo', 'Maya Stone', "
                    "'active', :demo_hash, true, 7"
                    "), ("
                    ":shared_other_id, :tenant_a, ' Shared.Person@Example.Test ', "
                    "'Tenant A Shared Person', 'invited', NULL, false, 3"
                    "), ("
                    ":shared_canonical_id, :tenant_b, :shared_email, "
                    "'Tenant B Shared Person', 'active', :shared_hash, false, 2"
                    ")"
                ),
                {
                    "demo_id": DEMO_ADMIN_ID,
                    "tenant_a": TENANT_A_ID,
                    "demo_hash": DEMO_PASSWORD_HASH,
                    "shared_other_id": SHARED_OTHER_USER_ID,
                    "shared_canonical_id": SHARED_CANONICAL_USER_ID,
                    "tenant_b": TENANT_B_ID,
                    "shared_email": SHARED_EMAIL_NORMALIZED,
                    "shared_hash": SHARED_PASSWORD_HASH,
                },
            )
            await connection.execute(
                text(
                    "insert into user_roles ("
                    "tenant_id, user_id, role_id, role_scope_type, active"
                    ") values ("
                    ":tenant_a, :demo_id, :tenant_admin_id, 'tenant', true"
                    "), ("
                    ":tenant_a, :shared_other_id, :manager_id, 'tenant', true"
                    "), ("
                    ":tenant_b, :shared_canonical_id, :employee_id, 'tenant', true"
                    ")"
                ),
                {
                    "tenant_a": TENANT_A_ID,
                    "tenant_b": TENANT_B_ID,
                    "demo_id": DEMO_ADMIN_ID,
                    "shared_other_id": SHARED_OTHER_USER_ID,
                    "shared_canonical_id": SHARED_CANONICAL_USER_ID,
                    "tenant_admin_id": ROLES_BY_CODE["tenant_admin"].id,
                    "manager_id": ROLES_BY_CODE["manager"].id,
                    "employee_id": ROLES_BY_CODE["employee"].id,
                },
            )
    finally:
        await engine.dispose()


async def _seed_conflicting_legacy_passwords(database_url: URL) -> None:
    engine = create_async_engine(database_url, poolclass=NullPool)
    try:
        async with engine.begin() as connection:
            await _insert_tenants(connection)
            await connection.execute(
                text(
                    "insert into users ("
                    "id, tenant_id, email, full_name, status, password_hash, permission_version"
                    ") values ("
                    ":canonical_id, :tenant_a, :email, 'Conflict A', 'active', "
                    ":password_a, 1"
                    "), ("
                    ":other_id, :tenant_b, ' SHARED.PERSON@EXAMPLE.TEST ', "
                    "'Conflict B', 'active', :password_b, 1"
                    ")"
                ),
                {
                    "canonical_id": SHARED_CANONICAL_USER_ID,
                    "other_id": SHARED_OTHER_USER_ID,
                    "tenant_a": TENANT_A_ID,
                    "tenant_b": TENANT_B_ID,
                    "email": SHARED_EMAIL_NORMALIZED,
                    "password_a": SHARED_PASSWORD_HASH,
                    "password_b": "different-legacy-password-hash",
                },
            )
    finally:
        await engine.dispose()


async def _insert_tenants(connection: AsyncConnection) -> None:
    await connection.execute(
        text(
            "insert into tenants ("
            "id, slug, name, status, plan_code, data_region, locale, timezone"
            ") values ("
            ":tenant_a, 'wealthy-falcon-demo', 'Wealthy Falcon HR Demo', "
            "'active', 'core', 'tr-1', 'en-US', 'UTC'"
            "), ("
            ":tenant_b, 'p3a-tenant-b', 'P3A Tenant B', "
            "'active', 'core', 'tr-1', 'en-US', 'UTC'"
            ")"
        ),
        {"tenant_a": TENANT_A_ID, "tenant_b": TENANT_B_ID},
    )


async def _repair_conflicting_legacy_passwords(database_url: URL) -> None:
    engine = create_async_engine(database_url, poolclass=NullPool)
    try:
        async with engine.begin() as connection:
            await connection.execute(
                text(
                    "update users set password_hash = :password_hash "
                    "where email_normalized = :email"
                ),
                {
                    "password_hash": SHARED_PASSWORD_HASH,
                    "email": SHARED_EMAIL_NORMALIZED,
                },
            )
    finally:
        await engine.dispose()


async def _introduce_lower_sorting_legacy_password(database_url: URL) -> None:
    engine = create_async_engine(database_url, poolclass=NullPool)
    try:
        async with engine.begin() as connection:
            await connection.execute(
                text(
                    "update users set password_hash = '000-lower-conflicting-hash' "
                    "where id = :user_id"
                ),
                {"user_id": SHARED_OTHER_USER_ID},
            )
    finally:
        await engine.dispose()


async def _clear_invited_legacy_password(database_url: URL) -> None:
    engine = create_async_engine(database_url, poolclass=NullPool)
    try:
        async with engine.begin() as connection:
            await connection.execute(
                text("update users set password_hash = null where id = :user_id"),
                {"user_id": SHARED_OTHER_USER_ID},
            )
    finally:
        await engine.dispose()


async def _drift_membership_name(database_url: URL) -> None:
    engine = create_async_engine(database_url, poolclass=NullPool)
    try:
        async with engine.begin() as connection:
            await connection.execute(
                text(
                    "update tenant_memberships set full_name = 'Canonical Drift' "
                    "where id = :membership_id"
                ),
                {"membership_id": DEMO_ADMIN_ID},
            )
    finally:
        await engine.dispose()


async def _repair_membership_names_from_legacy(database_url: URL) -> None:
    engine = create_async_engine(database_url, poolclass=NullPool)
    try:
        async with engine.begin() as connection:
            await connection.execute(
                text(
                    "update tenant_memberships as membership set full_name = users.full_name "
                    "from users where membership.tenant_id = users.tenant_id "
                    "and membership.legacy_user_id = users.id"
                )
            )
    finally:
        await engine.dispose()


async def _current_revision(database_url: URL) -> str | None:
    engine = create_async_engine(database_url, poolclass=NullPool)
    try:
        async with engine.connect() as connection:
            return await connection.scalar(text("select version_num from alembic_version"))
    finally:
        await engine.dispose()


async def _p3a_table_names(database_url: URL) -> set[str]:
    engine = create_async_engine(database_url, poolclass=NullPool)
    try:
        async with engine.connect() as connection:
            return set(
                await connection.scalars(
                    text(
                        "select tablename from pg_catalog.pg_tables "
                        "where schemaname = 'public' "
                        "and tablename = any(:table_names)"
                    ),
                    {
                        "table_names": [
                            "identities",
                            "tenant_memberships",
                            "membership_roles",
                        ]
                    },
                )
            )
    finally:
        await engine.dispose()


async def _row_security_flags(database_url: URL, table_name: str) -> tuple[bool, bool]:
    engine = create_async_engine(database_url, poolclass=NullPool)
    try:
        async with engine.connect() as connection:
            row = (
                await connection.execute(
                    text(
                        "select c.relrowsecurity, c.relforcerowsecurity "
                        "from pg_catalog.pg_class c "
                        "join pg_catalog.pg_namespace n on n.oid = c.relnamespace "
                        "where n.nspname = 'public' and c.relname = :table_name"
                    ),
                    {"table_name": table_name},
                )
            ).one()
            return bool(row[0]), bool(row[1])
    finally:
        await engine.dispose()


async def _identity_projection(database_url: URL) -> list[tuple[UUID, str, str | None]]:
    engine = create_async_engine(database_url, poolclass=NullPool)
    try:
        async with engine.connect() as connection:
            return list(
                (
                    await connection.execute(
                        text("select id, status, password_hash from identities order by id")
                    )
                ).tuples()
            )
    finally:
        await engine.dispose()


async def _membership_count(database_url: URL) -> int:
    engine = create_async_engine(database_url, poolclass=NullPool)
    try:
        async with engine.connect() as connection:
            return int(
                await connection.scalar(text("select count(*) from tenant_memberships"))
                or 0
            )
    finally:
        await engine.dispose()


async def _legacy_demo_admin_exists(database_url: URL) -> bool:
    engine = create_async_engine(database_url, poolclass=NullPool)
    try:
        async with engine.connect() as connection:
            return bool(
                await connection.scalar(
                    text("select count(*) = 1 from users where id = :user_id"),
                    {"user_id": DEMO_ADMIN_ID},
                )
            )
    finally:
        await engine.dispose()


async def _set_local_tenant_role(
    connection: AsyncConnection,
    tenant_id: UUID,
) -> None:
    await _set_local_role(connection, TENANT_APPLICATION_ROLE)
    await connection.execute(
        text("select set_config('app.tenant_id', :tenant_id, true)"),
        {"tenant_id": str(tenant_id)},
    )


async def _set_local_role(connection: AsyncConnection, role_name: str) -> None:
    quoted_role = connection.dialect.identifier_preparer.quote(role_name)
    await connection.exec_driver_sql(f"SET LOCAL ROLE {quoted_role}")


def _alembic_config(database_url: URL) -> Config:
    config = Config(str(ALEMBIC_INI))
    config.set_main_option(
        "sqlalchemy.url",
        database_url.render_as_string(hide_password=False).replace("%", "%%"),
    )
    return config
