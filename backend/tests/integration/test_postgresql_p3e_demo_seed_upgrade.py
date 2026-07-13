from __future__ import annotations

import asyncio
from pathlib import Path
from uuid import UUID

import pytest
from alembic import command as alembic_command
from alembic.config import Config
from app.services.demo_seed_service import seed_demo_data
from sqlalchemy import text
from sqlalchemy.engine import URL
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

pytestmark = pytest.mark.postgres

ROOT = Path(__file__).resolve().parents[3]
ALEMBIC_INI = ROOT / "alembic.ini"
PRE_IDENTITY_REVISION = "0021_f2f_user_insert_grant"
WF_TENANT_ID = UUID("f1000000-0000-4000-8000-000000000001")
ATLAS_TENANT_ID = UUID("f1000000-0000-4000-8000-000000000002")
WF_ADMIN_ID = UUID("f2000000-0000-4000-8000-000000000001")
ATLAS_ADMIN_ID = UUID("f2000000-0000-4000-8000-000000000004")


@pytest.fixture
def legacy_demo_seed_postgres_database(postgres_database_url: URL) -> URL:
    config = _alembic_config(postgres_database_url)
    alembic_command.upgrade(config, PRE_IDENTITY_REVISION)
    asyncio.run(_seed_pre_p3_demo_admins(postgres_database_url))
    alembic_command.upgrade(config, "head")
    return postgres_database_url


async def test_current_demo_seed_repoints_pre_p3_membership_idempotently(
    legacy_demo_seed_postgres_database: URL,
) -> None:
    engine = create_async_engine(
        legacy_demo_seed_postgres_database,
        poolclass=NullPool,
    )
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        results = []
        for _attempt in range(2):
            async with factory.begin() as session:
                results.append(await seed_demo_data(session))

        assert results[1] == results[0]
        async with engine.connect() as connection:
            atlas_membership = (
                await connection.execute(
                    text(
                        "select id, tenant_id, identity_id, legacy_user_id "
                        "from tenant_memberships where legacy_user_id = :user_id"
                    ),
                    {"user_id": ATLAS_ADMIN_ID},
                )
            ).one()
            detached_identity = (
                await connection.execute(
                    text(
                        "select id, email_normalized, status, password_hash, "
                        "(select count(*) from tenant_memberships "
                        "where identity_id = identities.id) "
                        "from identities where id = :identity_id"
                    ),
                    {"identity_id": ATLAS_ADMIN_ID},
                )
            ).one()
            counts = (
                await connection.execute(
                    text(
                        "select "
                        "(select count(*) from identities), "
                        "(select count(distinct identity_id) from tenant_memberships), "
                        "(select count(*) from tenant_memberships), "
                        "(select count(*) from membership_roles), "
                        "(select count(*) from platform_identity_roles "
                        "where active is true)"
                    )
                )
            ).one()
            shared_platform_role = (
                await connection.execute(
                    text(
                        "select identities.id, roles.code "
                        "from platform_identity_roles "
                        "join identities on identities.id = "
                        "platform_identity_roles.identity_id "
                        "join roles on roles.id = platform_identity_roles.role_id "
                        "where platform_identity_roles.active is true"
                    )
                )
            ).one()
            atlas_email = await connection.scalar(
                text("select email_normalized from users where id = :user_id"),
                {"user_id": ATLAS_ADMIN_ID},
            )

        assert atlas_membership == (
            ATLAS_ADMIN_ID,
            ATLAS_TENANT_ID,
            WF_ADMIN_ID,
            ATLAS_ADMIN_ID,
        )
        assert atlas_email == "admin@wealthyfalcon.demo"
        assert detached_identity == (
            ATLAS_ADMIN_ID,
            "admin@atlaspeople.demo",
            "pending",
            None,
            0,
        )
        # Four identities back the five current demo memberships. The fifth row is the deliberately
        # retained, detached historical identity from the pre-P3 Atlas fixture.
        assert counts == (5, 4, 5, 6, 1)
        assert shared_platform_role == (WF_ADMIN_ID, "super_admin")
    finally:
        await engine.dispose()


async def _seed_pre_p3_demo_admins(database_url: URL) -> None:
    engine = create_async_engine(database_url, poolclass=NullPool)
    try:
        async with engine.begin() as connection:
            await connection.execute(
                text(
                    "insert into tenants (id, slug, name, status, plan_code, data_region, "
                    "locale, timezone) values "
                    "(:wf_tenant, 'wealthy-falcon-demo', 'Wealthy Falcon HR Demo', "
                    "'active', 'core', 'tr-1', 'en-US', 'Europe/Istanbul'), "
                    "(:atlas_tenant, 'atlas-people-demo', 'Atlas People Operations', "
                    "'active', 'core', 'eu-1', 'en-US', 'Europe/Amsterdam')"
                ),
                {
                    "wf_tenant": WF_TENANT_ID,
                    "atlas_tenant": ATLAS_TENANT_ID,
                },
            )
            await connection.execute(
                text(
                    "insert into users (id, tenant_id, email, full_name, status, "
                    "password_hash, can_invite_users, permission_version) values "
                    "(:wf_admin, :wf_tenant, 'admin@wealthyfalcon.demo', 'Maya Stone', "
                    "'active', null, true, 1), "
                    "(:atlas_admin, :atlas_tenant, 'admin@atlaspeople.demo', 'Arda Blake', "
                    "'active', null, true, 1)"
                ),
                {
                    "wf_admin": WF_ADMIN_ID,
                    "wf_tenant": WF_TENANT_ID,
                    "atlas_admin": ATLAS_ADMIN_ID,
                    "atlas_tenant": ATLAS_TENANT_ID,
                },
            )
            await connection.execute(
                text(
                    "insert into user_roles (tenant_id, user_id, role_id, role_scope_type) "
                    "select fixture.tenant_id, fixture.user_id, roles.id, 'tenant' "
                    "from (values (cast(:wf_tenant as uuid), cast(:wf_admin as uuid)), "
                    "(cast(:atlas_tenant as uuid), cast(:atlas_admin as uuid))) "
                    "as fixture(tenant_id, user_id) "
                    "join roles on roles.code = 'tenant_admin'"
                ),
                {
                    "wf_admin": WF_ADMIN_ID,
                    "wf_tenant": WF_TENANT_ID,
                    "atlas_admin": ATLAS_ADMIN_ID,
                    "atlas_tenant": ATLAS_TENANT_ID,
                },
            )
    finally:
        await engine.dispose()


def _alembic_config(database_url: URL) -> Config:
    config = Config(str(ALEMBIC_INI))
    config.set_main_option(
        "sqlalchemy.url",
        database_url.render_as_string(hide_password=False).replace("%", "%%"),
    )
    return config
