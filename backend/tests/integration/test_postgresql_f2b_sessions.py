from __future__ import annotations

import asyncio
from datetime import timedelta
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from alembic import command as alembic_command
from alembic.config import Config
from app.models.auth import RefreshSessionFamily, RefreshSessionToken
from app.platform.db import sqlstate_from_error
from app.platform.db.tenant_access import (
    PLATFORM_APPLICATION_ROLE,
    TENANT_APPLICATION_ROLE,
)
from app.platform.identity import AccessTokenCodec, parse_refresh_token
from app.services.auth_session_service import (
    AuthSessionService,
    InvalidSessionError,
    SessionGrant,
)
from sqlalchemy import select, text
from sqlalchemy.engine import URL
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import (
    AsyncConnection,
    AsyncEngine,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

pytestmark = pytest.mark.postgres

ROOT = Path(__file__).resolve().parents[3]
ALEMBIC_INI = ROOT / "alembic.ini"

SESSION_TABLES = ("refresh_session_families", "refresh_session_tokens")
TABLE_PRIVILEGES = (
    "SELECT",
    "INSERT",
    "UPDATE",
    "DELETE",
    "TRUNCATE",
    "REFERENCES",
    "TRIGGER",
)
TENANT_A_ID = UUID("71000000-0000-4000-8000-000000000001")
TENANT_B_ID = UUID("71000000-0000-4000-8000-000000000002")
USER_A_ID = UUID("72000000-0000-4000-8000-000000000001")
USER_B_ID = UUID("72000000-0000-4000-8000-000000000002")
FAMILY_A_ID = UUID("73000000-0000-4000-8000-000000000001")
FAMILY_B_ID = UUID("73000000-0000-4000-8000-000000000002")
TOKEN_A_ID = UUID("74000000-0000-4000-8000-000000000001")
TOKEN_B_ID = UUID("74000000-0000-4000-8000-000000000002")


@pytest.fixture
def f2b_postgres_database(postgres_database_url: URL) -> URL:
    alembic_command.upgrade(_alembic_config(postgres_database_url), "head")
    return postgres_database_url


async def test_session_tables_force_tenant_isolation_and_have_no_platform_visibility(
    f2b_postgres_database: URL,
) -> None:
    engine = create_async_engine(f2b_postgres_database, poolclass=NullPool)
    try:
        await _seed_identity_rows(engine)
        await _seed_session_rows(engine)

        async with engine.connect() as connection:
            security_rows = (
                await connection.execute(
                    text(
                        "select c.relname, c.relrowsecurity, c.relforcerowsecurity "
                        "from pg_catalog.pg_class c "
                        "join pg_catalog.pg_namespace n on n.oid = c.relnamespace "
                        "where n.nspname = 'public' and c.relname = any(:table_names)"
                    ),
                    {"table_names": list(SESSION_TABLES)},
                )
            ).mappings()
            security = {row["relname"]: row for row in security_rows}
            assert set(security) == set(SESSION_TABLES)
            assert all(row["relrowsecurity"] for row in security.values())
            assert all(row["relforcerowsecurity"] for row in security.values())

            policy_rows = (
                await connection.execute(
                    text(
                        "select tablename, policyname, roles, cmd, qual, with_check "
                        "from pg_catalog.pg_policies where schemaname = 'public' "
                        "and tablename = any(:table_names)"
                    ),
                    {"table_names": list(SESSION_TABLES)},
                )
            ).mappings()
            policies = {row["tablename"]: row for row in policy_rows}
            assert set(policies) == set(SESSION_TABLES)
            for policy in policies.values():
                assert policy["policyname"] == "tenant_isolation_app"
                assert tuple(policy["roles"]) == (TENANT_APPLICATION_ROLE,)
                assert policy["cmd"] == "ALL"
                assert "tenant_id" in policy["qual"]
                assert "app.tenant_id" in policy["qual"]
                assert policy["with_check"] == policy["qual"]

            for table_name in SESSION_TABLES:
                assert await _granted_privileges(
                    connection,
                    role_name=TENANT_APPLICATION_ROLE,
                    table_name=table_name,
                ) == {"SELECT", "INSERT", "UPDATE"}
                assert await _granted_privileges(
                    connection,
                    role_name=PLATFORM_APPLICATION_ROLE,
                    table_name=table_name,
                ) == set()

        async with engine.begin() as connection:
            await _set_local_tenant_role(connection, TENANT_A_ID)
            assert tuple(
                await connection.scalars(
                    text("select id from refresh_session_families order by id")
                )
            ) == (FAMILY_A_ID,)
            assert tuple(
                await connection.scalars(
                    text("select id from refresh_session_tokens order by id")
                )
            ) == (TOKEN_A_ID,)
            hidden_family_update = await connection.execute(
                text(
                    "update refresh_session_families set revoked_at = CURRENT_TIMESTAMP "
                    "where id = :family_id"
                ),
                {"family_id": FAMILY_B_ID},
            )
            hidden_token_update = await connection.execute(
                text(
                    "update refresh_session_tokens set consumed_at = CURRENT_TIMESTAMP "
                    "where id = :token_id"
                ),
                {"token_id": TOKEN_B_ID},
            )
            assert hidden_family_update.rowcount == 0
            assert hidden_token_update.rowcount == 0

        with pytest.raises(DBAPIError) as cross_tenant_family_insert:
            async with engine.begin() as connection:
                await _set_local_tenant_role(connection, TENANT_A_ID)
                await connection.execute(
                    text(
                        "insert into refresh_session_families ("
                        "id, tenant_id, user_id, expires_at"
                        ") values ("
                        ":id, :tenant_id, :user_id, "
                        "CURRENT_TIMESTAMP + INTERVAL '1 day'"
                        ")"
                    ),
                    {
                        "id": uuid4(),
                        "tenant_id": TENANT_B_ID,
                        "user_id": USER_B_ID,
                    },
                )
        assert sqlstate_from_error(cross_tenant_family_insert.value) == "42501"

        with pytest.raises(DBAPIError) as cross_tenant_token_insert:
            async with engine.begin() as connection:
                await _set_local_tenant_role(connection, TENANT_A_ID)
                await connection.execute(
                    text(
                        "insert into refresh_session_tokens ("
                        "id, tenant_id, family_id, token_hash"
                        ") values (:id, :tenant_id, :family_id, :token_hash)"
                    ),
                    {
                        "id": uuid4(),
                        "tenant_id": TENANT_B_ID,
                        "family_id": FAMILY_B_ID,
                        "token_hash": "c" * 64,
                    },
                )
        assert sqlstate_from_error(cross_tenant_token_insert.value) == "42501"

        for table_name in SESSION_TABLES:
            with pytest.raises(DBAPIError) as platform_access:
                async with engine.begin() as connection:
                    await _set_local_role(connection, PLATFORM_APPLICATION_ROLE)
                    await connection.exec_driver_sql(f'SELECT 1 FROM "{table_name}" LIMIT 1')
            assert sqlstate_from_error(platform_access.value) == "42501"

        async with engine.connect() as connection:
            family_b_revoked_at = await connection.scalar(
                text(
                    "select revoked_at from refresh_session_families "
                    "where id = :family_id"
                ),
                {"family_id": FAMILY_B_ID},
            )
            token_b_consumed_at = await connection.scalar(
                text(
                    "select consumed_at from refresh_session_tokens "
                    "where id = :token_id"
                ),
                {"token_id": TOKEN_B_ID},
            )
            assert family_b_revoked_at is None
            assert token_b_consumed_at is None
    finally:
        await engine.dispose()


async def test_concurrent_refresh_replay_commits_revoke_and_kills_successor_session(
    f2b_postgres_database: URL,
) -> None:
    engine = create_async_engine(f2b_postgres_database, poolclass=NullPool)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    access_tokens = AccessTokenCodec(
        b"f2b-postgresql-session-signing-key",
        ttl=timedelta(minutes=5),
    )
    service = AuthSessionService(
        session_factory=session_factory,
        access_tokens=access_tokens,
        refresh_ttl=timedelta(days=14),
    )
    try:
        await _seed_identity_rows(engine)
        original = await service.start_session(
            tenant_id=TENANT_A_ID,
            tenant_slug="f2b-pg-tenant-a",
            user_id=USER_A_ID,
        )
        original_material = parse_refresh_token(original.refresh_token)
        start = asyncio.Event()

        async def rotate() -> SessionGrant:
            await start.wait()
            return await service.refresh(original.refresh_token)

        attempts = [asyncio.create_task(rotate()), asyncio.create_task(rotate())]
        start.set()
        outcomes = await asyncio.gather(*attempts, return_exceptions=True)

        winners = [outcome for outcome in outcomes if isinstance(outcome, SessionGrant)]
        replays = [outcome for outcome in outcomes if isinstance(outcome, InvalidSessionError)]
        assert len(winners) == 1
        assert len(replays) == 1
        successor = winners[0]
        successor_material = parse_refresh_token(successor.refresh_token)
        assert successor.session_family_id == original.session_family_id

        async with engine.connect() as connection:
            family_revoked_at = await connection.scalar(
                select(RefreshSessionFamily.revoked_at).where(
                    RefreshSessionFamily.id == original.session_family_id
                )
            )
            token_rows = (
                await connection.execute(
                    select(RefreshSessionToken.id, RefreshSessionToken.consumed_at)
                    .where(
                        RefreshSessionToken.family_id == original.session_family_id
                    )
                    .order_by(RefreshSessionToken.id)
                )
            ).all()
        assert family_revoked_at is not None
        assert {row.id for row in token_rows} == {
            original_material.token_id,
            successor_material.token_id,
        }
        consumed_by_id = {row.id: row.consumed_at for row in token_rows}
        assert consumed_by_id[original_material.token_id] is not None
        assert consumed_by_id[successor_material.token_id] is None

        with pytest.raises(InvalidSessionError):
            await service.refresh(successor.refresh_token)
        with pytest.raises(InvalidSessionError):
            await service.current_user(access_tokens.decode(successor.access_token))

        async with engine.connect() as connection:
            assert await connection.scalar(
                select(RefreshSessionFamily.revoked_at).where(
                    RefreshSessionFamily.id == original.session_family_id
                )
            ) == family_revoked_at
    finally:
        await engine.dispose()


def _alembic_config(database_url: URL) -> Config:
    config = Config(str(ALEMBIC_INI))
    config.set_main_option(
        "sqlalchemy.url",
        database_url.render_as_string(hide_password=False).replace("%", "%%"),
    )
    return config


async def _seed_identity_rows(engine: AsyncEngine) -> None:
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
                {"id": TENANT_A_ID, "slug": "f2b-pg-tenant-a", "name": "Tenant A"},
                {"id": TENANT_B_ID, "slug": "f2b-pg-tenant-b", "name": "Tenant B"},
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
                    "email": "session-a@example.test",
                    "full_name": "Session A",
                },
                {
                    "id": USER_B_ID,
                    "tenant_id": TENANT_B_ID,
                    "email": "session-b@example.test",
                    "full_name": "Session B",
                },
            ],
        )


async def _seed_session_rows(engine: AsyncEngine) -> None:
    async with engine.begin() as connection:
        await connection.execute(
            text(
                "insert into refresh_session_families ("
                "id, tenant_id, user_id, expires_at"
                ") values ("
                ":id, :tenant_id, :user_id, CURRENT_TIMESTAMP + INTERVAL '1 day'"
                ")"
            ),
            [
                {"id": FAMILY_A_ID, "tenant_id": TENANT_A_ID, "user_id": USER_A_ID},
                {"id": FAMILY_B_ID, "tenant_id": TENANT_B_ID, "user_id": USER_B_ID},
            ],
        )
        await connection.execute(
            text(
                "insert into refresh_session_tokens ("
                "id, tenant_id, family_id, token_hash"
                ") values (:id, :tenant_id, :family_id, :token_hash)"
            ),
            [
                {
                    "id": TOKEN_A_ID,
                    "tenant_id": TENANT_A_ID,
                    "family_id": FAMILY_A_ID,
                    "token_hash": "a" * 64,
                },
                {
                    "id": TOKEN_B_ID,
                    "tenant_id": TENANT_B_ID,
                    "family_id": FAMILY_B_ID,
                    "token_hash": "b" * 64,
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
        granted = await connection.scalar(
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
        )
        if granted:
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
