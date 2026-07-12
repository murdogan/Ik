from __future__ import annotations

import asyncio
from datetime import timedelta
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from alembic import command as alembic_command
from alembic.config import Config
from app.platform.db import sqlstate_from_error
from app.platform.db.tenant_access import (
    AUTHENTICATION_APPLICATION_ROLE,
    PLATFORM_APPLICATION_ROLE,
    TENANT_APPLICATION_ROLE,
)
from app.platform.identity import (
    AccessTokenCodec,
    PasswordManager,
    hash_organization_selection_token,
)
from app.services.authentication_service import (
    AuthenticationService,
    InvalidCredentialsError,
    OrganizationSelectionRequired,
)
from sqlalchemy import text
from sqlalchemy.engine import URL
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import (
    AsyncConnection,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

pytestmark = pytest.mark.postgres

ROOT = Path(__file__).resolve().parents[3]
ALEMBIC_INI = ROOT / "alembic.ini"
TENANT_ID = UUID("7b100000-0000-4000-8000-000000000001")
USER_ID = UUID("7b200000-0000-4000-8000-000000000001")
SECOND_TENANT_ID = UUID("7b100000-0000-4000-8000-000000000002")
SECOND_USER_ID = UUID("7b200000-0000-4000-8000-000000000002")
RACE_TENANT_ID = UUID("7b100000-0000-4000-8000-000000000003")
RACE_USER_ID = UUID("7b200000-0000-4000-8000-000000000003")
PASSWORD = "P3B PostgreSQL global identity password"
SECOND_PASSWORD = "P3B PostgreSQL replacement identity password"


@pytest.fixture
def p3b_postgres_database(postgres_database_url: URL) -> URL:
    alembic_command.upgrade(
        _alembic_config(postgres_database_url),
        "0022_p3a_identity_memberships",
    )
    asyncio.run(_seed_stale_authentication_grants(postgres_database_url))
    alembic_command.upgrade(_alembic_config(postgres_database_url), "head")
    return postgres_database_url


async def _seed_stale_authentication_grants(database_url: URL) -> None:
    engine = create_async_engine(database_url, poolclass=NullPool)
    try:
        async with engine.begin() as connection:
            await connection.execute(
                text(
                    f"""
                    DO $p3b_stale_authentication_role$
                    BEGIN
                        IF NOT EXISTS (
                            SELECT 1 FROM pg_catalog.pg_roles
                            WHERE rolname = '{AUTHENTICATION_APPLICATION_ROLE}'
                        ) THEN
                            CREATE ROLE "{AUTHENTICATION_APPLICATION_ROLE}" NOLOGIN;
                        END IF;
                    END
                    $p3b_stale_authentication_role$
                    """
                )
            )
            await connection.execute(
                text(
                    f'GRANT SELECT ON TABLE employees TO "{AUTHENTICATION_APPLICATION_ROLE}"'
                )
            )
            await connection.execute(
                text(
                    f'GRANT SELECT (email) ON TABLE users TO "{AUTHENTICATION_APPLICATION_ROLE}"'
                )
            )
            await connection.execute(
                text(
                    f'GRANT SELECT (plan_code) ON TABLE tenants '
                    f'TO "{AUTHENTICATION_APPLICATION_ROLE}"'
                )
            )
            await connection.execute(
                text(
                    f'GRANT SELECT ON TABLE audit_events '
                    f'TO "{AUTHENTICATION_APPLICATION_ROLE}"'
                )
            )
    finally:
        await engine.dispose()


async def test_p3b_authentication_role_is_narrow_and_selection_rows_are_private(
    p3b_postgres_database: URL,
) -> None:
    engine = create_async_engine(p3b_postgres_database, poolclass=NullPool)
    passwords = PasswordManager()
    password_hash = await passwords.hash_async(PASSWORD)
    second_password_hash = await passwords.hash_async(SECOND_PASSWORD)
    try:
        async with engine.begin() as connection:
            await connection.execute(
                text(
                    "insert into tenants ("
                    "id, slug, name, status, plan_code, data_region, locale, timezone"
                    ") values ("
                    ":tenant_id, 'p3b-tenant', 'P3B Organization', 'active', "
                    "'core', 'tr-1', 'en-US', 'UTC'"
                    "), ("
                    ":second_tenant_id, 'p3b-second', 'Second P3B Organization', "
                    "'active', 'core', 'tr-1', 'en-US', 'UTC'"
                    "), ("
                    ":race_tenant_id, 'p3b-race', 'Race P3B Organization', "
                    "'active', 'core', 'tr-1', 'en-US', 'UTC'"
                    ")"
                ),
                {
                    "tenant_id": TENANT_ID,
                    "second_tenant_id": SECOND_TENANT_ID,
                    "race_tenant_id": RACE_TENANT_ID,
                },
            )
            await connection.execute(
                text(
                    "insert into users ("
                    "id, tenant_id, email, full_name, status, password_hash, permission_version"
                    ") values ("
                    ":user_id, :tenant_id, 'identity@p3b.test', 'P3B User', "
                    "'active', :password_hash, 1"
                    "), ("
                    ":second_user_id, :second_tenant_id, 'identity@p3b.test', "
                    "'Second P3B User', 'active', :second_password_hash, 1"
                    "), ("
                    ":race_user_id, :race_tenant_id, 'identity@p3b.test', "
                    "'Race P3B User', 'invited', null, 1"
                    ")"
                ),
                {
                    "user_id": USER_ID,
                    "tenant_id": TENANT_ID,
                    "second_user_id": SECOND_USER_ID,
                    "second_tenant_id": SECOND_TENANT_ID,
                    "race_user_id": RACE_USER_ID,
                    "race_tenant_id": RACE_TENANT_ID,
                    "password_hash": password_hash,
                    "second_password_hash": second_password_hash,
                },
            )

        async with engine.begin() as connection:
            await _set_local_tenant_role(connection, TENANT_ID)
            await connection.execute(
                text("select public.sync_current_tenant_identity_membership(:user_id)"),
                {"user_id": USER_ID},
            )
        async with engine.begin() as connection:
            await _set_local_tenant_role(connection, SECOND_TENANT_ID)
            await connection.execute(
                text("select public.sync_current_tenant_identity_membership(:user_id)"),
                {"user_id": SECOND_USER_ID},
            )
        async with engine.begin() as connection:
            await _set_local_tenant_role(connection, RACE_TENANT_ID)
            await connection.execute(
                text("select public.sync_current_tenant_identity_membership(:user_id)"),
                {"user_id": RACE_USER_ID},
            )

        with pytest.raises(DBAPIError) as raced_activation:
            async with engine.begin() as connection:
                await _set_local_tenant_role(connection, RACE_TENANT_ID)
                await connection.execute(
                    text(
                        "update users set status = 'active', password_hash = :password_hash "
                        "where tenant_id = :tenant_id and id = :user_id"
                    ),
                    {
                        "password_hash": second_password_hash,
                        "tenant_id": RACE_TENANT_ID,
                        "user_id": RACE_USER_ID,
                    },
                )
                await connection.execute(
                    text(
                        "select public.sync_current_tenant_identity_membership("
                        ":user_id, true)"
                    ),
                    {"user_id": RACE_USER_ID},
                )
        assert sqlstate_from_error(raced_activation.value) == "WF001"
        async with engine.connect() as connection:
            raced_user = (
                await connection.execute(
                    text(
                        "select users.status, users.password_hash, memberships.status "
                        "from users join tenant_memberships as memberships "
                        "on memberships.tenant_id = users.tenant_id "
                        "and memberships.legacy_user_id = users.id "
                        "where users.tenant_id = :tenant_id and users.id = :user_id"
                    ),
                    {"tenant_id": RACE_TENANT_ID, "user_id": RACE_USER_ID},
                )
            ).one()
        assert tuple(raced_user) == ("invited", None, "invited")

        transaction_id = uuid4()
        selection_key = uuid4()
        async with engine.begin() as connection:
            await _set_local_role(connection, AUTHENTICATION_APPLICATION_ROLE)
            assert await connection.scalar(
                text("select count(id) from identities where id = :user_id"),
                {"user_id": USER_ID},
            ) == 1
            assert await connection.scalar(
                text(
                    "select count(id) from tenant_memberships "
                    "where identity_id = :user_id"
                ),
                {"user_id": USER_ID},
            ) == 3
            assert await connection.scalar(
                text("select name from tenants where id = :tenant_id"),
                {"tenant_id": TENANT_ID},
            ) == "P3B Organization"
            await connection.execute(
                text(
                    "insert into organization_selection_transactions ("
                    "id, identity_id, token_hash, expires_at"
                    ") values ("
                    ":id, :identity_id, repeat('a', 64), CURRENT_TIMESTAMP + interval '5 minutes'"
                    ")"
                ),
                {"id": transaction_id, "identity_id": USER_ID},
            )
            await connection.execute(
                text(
                    "insert into organization_selection_choices ("
                    "selection_key, transaction_id, tenant_id"
                    ") values (:selection_key, :transaction_id, :tenant_id)"
                ),
                {
                    "selection_key": selection_key,
                    "transaction_id": transaction_id,
                    "tenant_id": TENANT_ID,
                },
            )

        async with engine.connect() as connection:
            role = (
                await connection.execute(
                    text(
                        "select rolcanlogin, rolsuper, rolcreaterole, rolcreatedb, "
                        "rolinherit, rolbypassrls from pg_catalog.pg_roles "
                        "where rolname = :role_name"
                    ),
                    {"role_name": AUTHENTICATION_APPLICATION_ROLE},
                )
            ).one()
            assert role == (False, False, False, False, False, False)
            policies = {
                (row.tablename, row.policyname, row.cmd)
                for row in (
                    await connection.execute(
                        text(
                            "select tablename, policyname, cmd from pg_catalog.pg_policies "
                            "where schemaname = 'public' and :role_name = any(roles)"
                        ),
                        {"role_name": AUTHENTICATION_APPLICATION_ROLE},
                    )
                )
            }
            assert {
                ("identities", "authentication_identity_read", "SELECT"),
                ("tenant_memberships", "authentication_membership_read", "SELECT"),
                ("tenants", "authentication_tenant_read", "SELECT"),
                ("users", "authentication_legacy_user_read", "SELECT"),
                (
                    "organization_selection_transactions",
                    "authentication_selection_transaction_insert",
                    "INSERT",
                ),
                (
                    "organization_selection_choices",
                    "authentication_selection_choice_insert",
                    "INSERT",
                ),
                (
                    "authentication_rate_limit_buckets",
                    "authentication_rate_limit_access",
                    "ALL",
                ),
                ("audit_events", "authentication_failure_insert", "INSERT"),
            } <= policies
            assert await connection.scalar(
                text(
                    "select count(*) from organization_selection_transactions "
                    "where id = :id and token_hash = repeat('a', 64)"
                ),
                {"id": transaction_id},
            ) == 1

        for role_name in (TENANT_APPLICATION_ROLE, PLATFORM_APPLICATION_ROLE):
            with pytest.raises(DBAPIError) as denied:
                async with engine.begin() as connection:
                    if role_name == TENANT_APPLICATION_ROLE:
                        await _set_local_tenant_role(connection, TENANT_ID)
                    else:
                        await _set_local_role(connection, role_name)
                    await connection.execute(
                        text("select id from organization_selection_transactions")
                    )
            assert sqlstate_from_error(denied.value) == "42501"

        with pytest.raises(DBAPIError) as hr_access:
            async with engine.begin() as connection:
                await _set_local_role(connection, AUTHENTICATION_APPLICATION_ROLE)
                await connection.execute(text("select id from employees"))
        assert sqlstate_from_error(hr_access.value) == "42501"

        for private_query in (
            "select email, created_at from identities",
            "select full_name, permission_version from tenant_memberships",
            "select email from users",
            "select plan_code from tenants",
            "select id from audit_events",
        ):
            with pytest.raises(DBAPIError) as private_column_access:
                async with engine.begin() as connection:
                    await _set_local_role(connection, AUTHENTICATION_APPLICATION_ROLE)
                    await connection.execute(text(private_query))
            assert sqlstate_from_error(private_column_access.value) == "42501"

        with pytest.raises(DBAPIError) as unsafe_audit:
            async with engine.begin() as connection:
                await _set_local_role(connection, AUTHENTICATION_APPLICATION_ROLE)
                await connection.execute(
                    text(
                        "insert into audit_events ("
                        "id, occurred_at, scope_type, tenant_id, actor_type, actor_user_id, "
                        "impersonator_user_id, event_type, category, severity, resource_type, "
                        "resource_id, action, result, request_id, trace_id, session_id, "
                        "ip_address, user_agent, reason, support_ticket_id, changed_fields, "
                        "before_data, after_data, metadata, data_classification, "
                        "visibility_class, integrity_hash"
                        ") values ("
                        ":id, CURRENT_TIMESTAMP, 'platform', null, 'system', null, null, "
                        "'auth.login.failed', 'platform_operations', 'info', "
                        "'authentication', null, 'login', 'failure', 'p3b-malicious-audit', "
                        "'1234567890abcdef1234567890abcdef', null, null, null, null, null, "
                        "'[]'::jsonb, '{}'::jsonb, '{}'::jsonb, "
                        "jsonb_build_object('failure_reason', 'authentication_failed', "
                        "'identity_id', cast(:identity_id as text)), "
                        "'platform_metadata', 'platform_ops', null"
                        ")"
                    ),
                    {"id": uuid4(), "identity_id": str(USER_ID)},
                )
        assert sqlstate_from_error(unsafe_audit.value) == "42501"

        service = AuthenticationService(
            session_factory=async_sessionmaker(engine, expire_on_commit=False),
            password_manager=passwords,
            access_tokens=AccessTokenCodec(
                b"p3b-postgresql-signing-key-material",
                ttl=timedelta(minutes=5),
            ),
        )
        result = await service.login(
            email="identity@p3b.test",
            password=PASSWORD,
        )
        assert isinstance(result, OrganizationSelectionRequired)
        assert [choice.display_name for choice in result.organizations] == [
            "P3B Organization",
            "Second P3B Organization",
        ]
        async with engine.connect() as connection:
            persisted_hash = await connection.scalar(
                text(
                    "select token_hash from organization_selection_transactions "
                    "where token_hash <> repeat('a', 64)"
                )
            )
        assert persisted_hash == hash_organization_selection_token(
            result.selection_transaction
        )
        with pytest.raises(InvalidCredentialsError):
            await service.login(
                email="identity@p3b.test",
                password=SECOND_PASSWORD,
            )
        async with engine.connect() as connection:
            failure = (
                await connection.execute(
                    text(
                        "select scope_type, tenant_id, actor_type, category, metadata "
                        "from audit_events where event_type = 'auth.login.failed'"
                    )
                )
            ).one()
        assert tuple(failure) == (
            "platform",
            None,
            "system",
            "platform_operations",
            {"failure_reason": "authentication_failed"},
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
