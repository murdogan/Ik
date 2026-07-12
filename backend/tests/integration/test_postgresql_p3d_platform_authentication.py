from __future__ import annotations

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
    AccessPrincipal,
    AccessTokenCodec,
    InvalidAccessTokenError,
    InvalidPlatformAccessTokenError,
    PlatformAccessPrincipal,
    PlatformAccessTokenCodec,
)
from app.platform.request_context import AuthenticationStrength
from sqlalchemy import text
from sqlalchemy.engine import URL
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncConnection, create_async_engine
from sqlalchemy.pool import NullPool

pytestmark = pytest.mark.postgres

ROOT = Path(__file__).resolve().parents[3]
ALEMBIC_INI = ROOT / "alembic.ini"

IDENTITY_ID = UUID("7d200000-0000-4000-8000-000000000001")
TENANT_ID = UUID("7d100000-0000-4000-8000-000000000001")
TENANT_USER_ID = UUID("7d300000-0000-4000-8000-000000000001")
TENANT_MEMBERSHIP_ID = UUID("7d400000-0000-4000-8000-000000000001")
PLATFORM_FAMILY_ID = UUID("7d500000-0000-4000-8000-000000000001")
PLATFORM_TOKEN_ID = UUID("7d600000-0000-4000-8000-000000000001")

PLATFORM_TABLES = (
    "platform_identity_roles",
    "platform_refresh_session_families",
    "platform_refresh_session_tokens",
)

_AUDIT_INSERT = text(
    "insert into audit_events ("
    "id, occurred_at, scope_type, tenant_id, actor_type, actor_user_id, "
    "impersonator_user_id, event_type, category, severity, resource_type, "
    "resource_id, action, result, request_id, trace_id, session_id, "
    "ip_address, user_agent, reason, support_ticket_id, changed_fields, "
    "before_data, after_data, metadata, data_classification, visibility_class, "
    "integrity_hash"
    ") values ("
    ":id, CURRENT_TIMESTAMP, :scope_type, :tenant_id, 'system', null, null, "
    "'platform.auth.login.failed', :category, 'info', 'authentication', null, "
    "'login', 'failure', 'p3d-platform-auth-proof', "
    "'7d700000000040008000000000000001', null, null, null, null, null, "
    "'[]'::jsonb, '{}'::jsonb, '{}'::jsonb, '{}'::jsonb, "
    ":data_classification, :visibility_class, null"
    ")"
)


@pytest.fixture
def p3d_postgres_database(postgres_database_url: URL) -> URL:
    alembic_command.upgrade(
        _alembic_config(postgres_database_url),
        "0025_p3d_platform_authentication",
    )
    return postgres_database_url


async def test_platform_realm_has_tenantless_persistence_narrow_acl_and_distinct_audience(
    p3d_postgres_database: URL,
) -> None:
    engine = create_async_engine(p3d_postgres_database, poolclass=NullPool)
    try:
        await _seed_platform_assignment(engine)

        async with engine.connect() as connection:
            columns = {
                row.table_name: set(row.column_names)
                for row in (
                    await connection.execute(
                        text(
                            "select table_name, array_agg(column_name order by ordinal_position) "
                            "as column_names from information_schema.columns "
                            "where table_schema = 'public' and table_name in ("
                            "'platform_identity_roles', "
                            "'platform_refresh_session_families', "
                            "'platform_refresh_session_tokens'"
                            ") group by table_name"
                        )
                    )
                )
            }
            assert set(columns) == set(PLATFORM_TABLES)
            assert all("tenant_id" not in table_columns for table_columns in columns.values())
            assert "identity_id" in columns["platform_identity_roles"]
            assert "identity_id" in columns["platform_refresh_session_families"]
            assert "family_id" in columns["platform_refresh_session_tokens"]

            await _assert_exact_table_acl(connection)

        async with engine.begin() as connection:
            await _set_local_role(connection, AUTHENTICATION_APPLICATION_ROLE)
            assignment = (
                await connection.execute(
                    text(
                        "select identities.email, identities.platform_permission_version, "
                        "roles.code, assignments.active "
                        "from platform_identity_roles as assignments "
                        "join identities on identities.id = assignments.identity_id "
                        "join roles on roles.id = assignments.role_id "
                        "where assignments.identity_id = :identity_id "
                        "and assignments.active is true"
                    ),
                    {"identity_id": IDENTITY_ID},
                )
            ).one()
            assert tuple(assignment) == ("platform-admin@p3d.test", 1, "super_admin", True)

            await connection.execute(
                text(
                    "insert into platform_refresh_session_families ("
                    "id, identity_id, permission_version, authentication_strength, expires_at"
                    ") values ("
                    ":family_id, :identity_id, 1, 'single_factor', "
                    "CURRENT_TIMESTAMP + interval '1 hour'"
                    ")"
                ),
                {"family_id": PLATFORM_FAMILY_ID, "identity_id": IDENTITY_ID},
            )
            await connection.execute(
                text(
                    "insert into platform_refresh_session_tokens ("
                    "id, family_id, token_hash"
                    ") values (:token_id, :family_id, repeat('a', 64))"
                ),
                {"token_id": PLATFORM_TOKEN_ID, "family_id": PLATFORM_FAMILY_ID},
            )
            family = (
                await connection.execute(
                    text(
                        "select identity_id, permission_version, authentication_strength, "
                        "revoked_at from platform_refresh_session_families where id = :family_id"
                    ),
                    {"family_id": PLATFORM_FAMILY_ID},
                )
            ).one()
            token = (
                await connection.execute(
                    text(
                        "select family_id, token_hash, consumed_at "
                        "from platform_refresh_session_tokens where id = :token_id"
                    ),
                    {"token_id": PLATFORM_TOKEN_ID},
                )
            ).one()
            assert tuple(family) == (IDENTITY_ID, 1, "single_factor", None)
            assert tuple(token) == (PLATFORM_FAMILY_ID, "a" * 64, None)

            await connection.execute(
                text(
                    "update platform_refresh_session_tokens "
                    "set consumed_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP "
                    "where id = :token_id"
                ),
                {"token_id": PLATFORM_TOKEN_ID},
            )
            await connection.execute(
                text(
                    "update platform_refresh_session_families "
                    "set revoked_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP "
                    "where id = :family_id"
                ),
                {"family_id": PLATFORM_FAMILY_ID},
            )
            assert await connection.scalar(
                text(
                    "select count(*) from platform_refresh_session_tokens "
                    "where id = :token_id and consumed_at is not null"
                ),
                {"token_id": PLATFORM_TOKEN_ID},
            ) == 1
            assert await connection.scalar(
                text(
                    "select count(*) from platform_refresh_session_families "
                    "where id = :family_id and revoked_at is not null"
                ),
                {"family_id": PLATFORM_FAMILY_ID},
            ) == 1

        for role_name in (TENANT_APPLICATION_ROLE, PLATFORM_APPLICATION_ROLE):
            for table_name in PLATFORM_TABLES:
                with pytest.raises(DBAPIError) as denied:
                    async with engine.begin() as connection:
                        if role_name == TENANT_APPLICATION_ROLE:
                            await _set_local_tenant_role(connection, TENANT_ID)
                        else:
                            await _set_local_role(connection, role_name)
                        await connection.execute(text(f'SELECT * FROM "{table_name}"'))
                assert sqlstate_from_error(denied.value) == "42501"

        valid_audit_id = uuid4()
        async with engine.begin() as connection:
            await _set_local_role(connection, AUTHENTICATION_APPLICATION_ROLE)
            await connection.execute(
                _AUDIT_INSERT,
                {
                    "id": valid_audit_id,
                    "scope_type": "platform",
                    "tenant_id": None,
                    "category": "platform_operations",
                    "data_classification": "security_metadata",
                    "visibility_class": "platform_ops",
                },
            )

        with pytest.raises(DBAPIError) as tenant_shaped_audit:
            async with engine.begin() as connection:
                await _set_local_role(connection, AUTHENTICATION_APPLICATION_ROLE)
                await connection.execute(
                    _AUDIT_INSERT,
                    {
                        "id": uuid4(),
                        "scope_type": "tenant",
                        "tenant_id": TENANT_ID,
                        "category": "tenant_security",
                        "data_classification": "security_metadata",
                        "visibility_class": "tenant_security",
                    },
                )
        assert sqlstate_from_error(tenant_shaped_audit.value) == "42501"

        async with engine.connect() as connection:
            assert await connection.scalar(
                text("select count(*) from audit_events where id = :event_id"),
                {"event_id": valid_audit_id},
            ) == 1
            assert await connection.scalar(
                text(
                    "select count(*) from audit_events "
                    "where event_type = 'platform.auth.login.failed' and scope_type = 'tenant'"
                )
            ) == 0

        _assert_access_token_audiences_are_mutually_exclusive()
    finally:
        await engine.dispose()


async def _seed_platform_assignment(engine) -> None:
    async with engine.begin() as connection:
        await connection.execute(
            text(
                "insert into tenants ("
                "id, slug, name, status, plan_code, data_region, locale, timezone"
                ") values ("
                ":tenant_id, 'p3d-proof-tenant', 'P3D Proof Tenant', 'active', "
                "'core', 'tr-1', 'en-US', 'UTC'"
                ")"
            ),
            {"tenant_id": TENANT_ID},
        )
        await connection.execute(
            text(
                "insert into identities (id, email, status, password_hash) values ("
                ":identity_id, 'platform-admin@p3d.test', 'active', "
                "'$argon2id$p3d-postgresql-proof'"
                ")"
            ),
            {"identity_id": IDENTITY_ID},
        )
        await connection.execute(
            text(
                "insert into platform_identity_roles ("
                "identity_id, role_id, role_scope_type, active"
                ") select :identity_id, id, scope_type, true from roles "
                "where code = 'super_admin' and scope_type = 'platform'"
            ),
            {"identity_id": IDENTITY_ID},
        )


async def _assert_exact_table_acl(connection: AsyncConnection) -> None:
    expected_authentication_privileges = {
        "platform_identity_roles": {"SELECT"},
        "platform_refresh_session_families": {"SELECT", "INSERT", "UPDATE"},
        "platform_refresh_session_tokens": {"SELECT", "INSERT", "UPDATE"},
    }
    all_privileges = {
        "SELECT",
        "INSERT",
        "UPDATE",
        "DELETE",
        "TRUNCATE",
        "REFERENCES",
        "TRIGGER",
    }
    for table_name in PLATFORM_TABLES:
        authentication_privileges = {
            privilege
            for privilege in all_privileges
            if await connection.scalar(
                text("select has_table_privilege(:role_name, :table_name, :privilege)"),
                {
                    "role_name": AUTHENTICATION_APPLICATION_ROLE,
                    "table_name": f"public.{table_name}",
                    "privilege": privilege,
                },
            )
        }
        assert authentication_privileges == expected_authentication_privileges[table_name]

        for role_name in (TENANT_APPLICATION_ROLE, PLATFORM_APPLICATION_ROLE):
            for privilege in all_privileges:
                assert not await connection.scalar(
                    text("select has_table_privilege(:role_name, :table_name, :privilege)"),
                    {
                        "role_name": role_name,
                        "table_name": f"public.{table_name}",
                        "privilege": privilege,
                    },
                )


def _assert_access_token_audiences_are_mutually_exclusive() -> None:
    signing_key = b"p3d-postgresql-shared-signing-key-material"
    tenant_codec = AccessTokenCodec(signing_key, ttl=timedelta(minutes=5))
    platform_codec = PlatformAccessTokenCodec(signing_key, ttl=timedelta(minutes=5))
    tenant_token = tenant_codec.issue(
        AccessPrincipal(
            user_id=TENANT_USER_ID,
            tenant_id=TENANT_ID,
            membership_id=TENANT_MEMBERSHIP_ID,
            tenant_slug="p3d-proof-tenant",
            session_family_id=uuid4(),
        )
    ).token
    platform_principal = PlatformAccessPrincipal(
        identity_id=IDENTITY_ID,
        session_family_id=PLATFORM_FAMILY_ID,
        permission_version=1,
        authentication_strength=AuthenticationStrength.SINGLE_FACTOR,
    )
    platform_token = platform_codec.issue(platform_principal).token

    assert tenant_codec.decode(tenant_token).tenant_id == TENANT_ID
    assert platform_codec.decode(platform_token) == platform_principal
    with pytest.raises(InvalidPlatformAccessTokenError):
        platform_codec.decode(tenant_token)
    with pytest.raises(InvalidAccessTokenError):
        tenant_codec.decode(platform_token)


async def _set_local_tenant_role(connection: AsyncConnection, tenant_id: UUID) -> None:
    await _set_local_role(connection, TENANT_APPLICATION_ROLE)
    await connection.exec_driver_sql(f"SET LOCAL app.tenant_id = '{tenant_id}'")


async def _set_local_role(connection: AsyncConnection, role_name: str) -> None:
    await connection.exec_driver_sql(f'SET LOCAL ROLE "{role_name}"')


def _alembic_config(database_url: URL) -> Config:
    config = Config(str(ALEMBIC_INI))
    config.set_main_option(
        "sqlalchemy.url",
        database_url.render_as_string(hide_password=False),
    )
    return config
