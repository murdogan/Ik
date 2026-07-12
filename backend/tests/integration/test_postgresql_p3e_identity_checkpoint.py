from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from urllib.parse import parse_qs, urlsplit
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
    hash_activation_token,
    hash_password_reset_token,
    issue_activation_token,
)
from app.services.authentication_service import (
    AuthenticationService,
    InvalidActivationError,
    OrganizationSelectionRequired,
)
from app.services.password_recovery_service import (
    InvalidPasswordResetError,
    PasswordRecoveryService,
    PasswordResetDeliveryMessage,
)
from sqlalchemy import text
from sqlalchemy.engine import URL
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

pytestmark = pytest.mark.postgres

ROOT = Path(__file__).resolve().parents[3]
ALEMBIC_INI = ROOT / "alembic.ini"
IDENTITY_ID = UUID("7e200000-0000-4000-8000-000000000001")
TENANT_A_ID = UUID("7e100000-0000-4000-8000-000000000001")
TENANT_B_ID = UUID("7e100000-0000-4000-8000-000000000002")
USER_A_ID = UUID("7e300000-0000-4000-8000-000000000001")
USER_B_ID = UUID("7e300000-0000-4000-8000-000000000002")
TENANT_FAMILY_ID = UUID("7e400000-0000-4000-8000-000000000001")
PLATFORM_FAMILY_ID = UUID("7e500000-0000-4000-8000-000000000001")
EMAIL = "identity@p3e.test"
PASSWORD = "P3E PostgreSQL existing identity password"
WRONG_PASSWORD = "P3E PostgreSQL wrong existing password"
RESET_PASSWORD = "P3E PostgreSQL recovered identity password"
_RECOVERY_ROLE = "wealthy_falcon_identity_recovery"


@dataclass(slots=True)
class _CaptureDelivery:
    messages: list[PasswordResetDeliveryMessage]

    async def deliver(self, message: PasswordResetDeliveryMessage) -> None:
        self.messages.append(message)


@pytest.fixture
def p3e_postgres_database(postgres_database_url: URL) -> URL:
    config = _alembic_config(postgres_database_url)
    alembic_command.upgrade(config, "0025_p3d_platform_authentication")
    hostile_member = asyncio.run(_seed_hostile_recovery_role(postgres_database_url))
    try:
        with pytest.raises(
            DBAPIError,
            match="must not be granted to an application or gateway role",
        ):
            alembic_command.upgrade(config, "head")
        assert asyncio.run(_current_revision(postgres_database_url)) == (
            "0025_p3d_platform_authentication"
        )
    finally:
        asyncio.run(
            _remove_hostile_recovery_member(
                postgres_database_url,
                hostile_member,
            )
        )
    hostile_function = asyncio.run(_seed_hostile_recovery_owned_function(postgres_database_url))
    try:
        with pytest.raises(
            DBAPIError,
            match="owns a pre-existing public object",
        ):
            alembic_command.upgrade(config, "head")
        assert asyncio.run(_current_revision(postgres_database_url)) == (
            "0025_p3d_platform_authentication"
        )
    finally:
        asyncio.run(
            _remove_hostile_recovery_owned_function(
                postgres_database_url,
                hostile_function,
            )
        )
    alembic_command.upgrade(config, "head")
    return postgres_database_url


async def test_p3e_existing_identity_acceptance_and_recovery_are_atomic(
    p3e_postgres_database: URL,
) -> None:
    engine = create_async_engine(p3e_postgres_database, poolclass=NullPool)
    passwords = PasswordManager()
    original_hash = await passwords.hash_async(PASSWORD)
    activation = issue_activation_token(TENANT_B_ID)
    delivery = _CaptureDelivery(messages=[])
    try:
        await _seed_identity_checkpoint(
            engine,
            password_hash=original_hash,
            activation_hash=activation.token_hash,
        )
        await _assert_reset_storage_boundary(engine)
        factory = async_sessionmaker(engine, expire_on_commit=False)
        authentication = AuthenticationService(
            session_factory=factory,
            password_manager=passwords,
            access_tokens=AccessTokenCodec(
                b"p3e-postgresql-tenant-access-token-key",
                ttl=timedelta(minutes=5),
            ),
        )

        with pytest.raises(InvalidActivationError):
            await authentication.activate(
                raw_token=activation.raw_token,
                password=WRONG_PASSWORD,
            )
        accepted = await authentication.activate(
            raw_token=activation.raw_token,
            password=PASSWORD,
        )
        assert accepted.tenant_id == TENANT_B_ID
        with pytest.raises(InvalidActivationError):
            await authentication.activate(
                raw_token=activation.raw_token,
                password=PASSWORD,
            )

        login = await authentication.login(email=EMAIL, password=PASSWORD)
        assert isinstance(login, OrganizationSelectionRequired)
        assert [choice.display_name for choice in login.organizations] == [
            "P3E Organization A",
            "P3E Organization B",
        ]

        recovery = PasswordRecoveryService(
            session_factory=factory,
            password_manager=passwords,
            reset_ttl=timedelta(minutes=15),
            frontend_base_url="http://frontend.test",
            delivery=delivery,
        )
        await recovery.request_reset(email=EMAIL)
        assert len(delivery.messages) == 1
        raw_reset_token = parse_qs(urlsplit(delivery.messages[0].reset_url).fragment)["token"][0]
        await recovery.confirm_reset(
            raw_token=raw_reset_token,
            password=RESET_PASSWORD,
        )
        with pytest.raises(InvalidPasswordResetError):
            await recovery.confirm_reset(
                raw_token=raw_reset_token,
                password=RESET_PASSWORD,
            )

        async with engine.connect() as connection:
            identity = (
                await connection.execute(
                    text(
                        "select password_hash, (select count(*) from identities "
                        "where email_normalized = :email) from identities "
                        "where id = :identity_id"
                    ),
                    {"email": EMAIL, "identity_id": IDENTITY_ID},
                )
            ).one()
            user_hashes = tuple(
                await connection.scalars(
                    text(
                        "select password_hash from users where id in (:user_a, :user_b) order by id"
                    ),
                    {"user_a": USER_A_ID, "user_b": USER_B_ID},
                )
            )
            terminal_rows = (
                await connection.execute(
                    text(
                        "select "
                        "(select count(*) from user_activation_tokens where "
                        "token_hash = :activation_hash and consumed_at is not null), "
                        "(select count(*) from password_reset_tokens where "
                        "token_hash = :reset_hash and consumed_at is not null), "
                        "(select count(*) from refresh_session_families where "
                        "id = :tenant_family and revoked_at is not null), "
                        "(select count(*) from platform_refresh_session_families where "
                        "id = :platform_family and revoked_at is not null), "
                        "(select count(*) from organization_selection_transactions where "
                        "identity_id = :identity_id and consumed_at is not null)"
                    ),
                    {
                        "activation_hash": hash_activation_token(activation.raw_token),
                        "reset_hash": hash_password_reset_token(raw_reset_token),
                        "tenant_family": TENANT_FAMILY_ID,
                        "platform_family": PLATFORM_FAMILY_ID,
                        "identity_id": IDENTITY_ID,
                    },
                )
            ).one()
        assert identity[1] == 1
        assert identity[0] == user_hashes[0] == user_hashes[1]
        assert await passwords.verify_async(RESET_PASSWORD, identity[0])
        assert terminal_rows == (1, 1, 1, 1, 1)
    finally:
        await engine.dispose()


def test_p3e_downgrade_removes_expanded_rate_rows_before_constraint_contract(
    p3e_postgres_database: URL,
) -> None:
    asyncio.run(_seed_rate_limit_scope_rows(p3e_postgres_database))

    alembic_command.downgrade(
        _alembic_config(p3e_postgres_database),
        "0025_p3d_platform_authentication",
    )

    assert asyncio.run(_current_revision(p3e_postgres_database)) == (
        "0025_p3d_platform_authentication"
    )
    assert asyncio.run(_rate_limit_scope_rows(p3e_postgres_database)) == {"login_source"}
    assert asyncio.run(
        _row_security_flags(
            p3e_postgres_database,
            "authentication_rate_limit_buckets",
        )
    ) == (True, True)


async def _seed_identity_checkpoint(
    engine,
    *,
    password_hash: str,
    activation_hash: str,
) -> None:
    async with engine.begin() as connection:
        await connection.execute(
            text(
                "insert into tenants (id, slug, name, status, plan_code, data_region, "
                "locale, timezone) values "
                "(:tenant_a, 'p3e-a', 'P3E Organization A', 'active', 'core', "
                "'tr-1', 'en-US', 'UTC'), "
                "(:tenant_b, 'p3e-b', 'P3E Organization B', 'active', 'core', "
                "'tr-1', 'en-US', 'UTC')"
            ),
            {"tenant_a": TENANT_A_ID, "tenant_b": TENANT_B_ID},
        )
        await connection.execute(
            text(
                "insert into users (id, tenant_id, email, full_name, status, "
                "password_hash, permission_version) values "
                "(:user_a, :tenant_a, :email, 'Identity A', 'active', :password_hash, 1), "
                "(:user_b, :tenant_b, :email, 'Identity B', 'invited', null, 1)"
            ),
            {
                "user_a": USER_A_ID,
                "tenant_a": TENANT_A_ID,
                "user_b": USER_B_ID,
                "tenant_b": TENANT_B_ID,
                "email": EMAIL,
                "password_hash": password_hash,
            },
        )
        await connection.execute(
            text(
                "insert into identities (id, email, status, password_hash) values "
                "(:identity_id, :email, 'active', :password_hash)"
            ),
            {
                "identity_id": IDENTITY_ID,
                "email": EMAIL,
                "password_hash": password_hash,
            },
        )
        await connection.execute(
            text(
                "insert into tenant_memberships (id, tenant_id, identity_id, "
                "legacy_user_id, full_name, status, permission_version) values "
                "(:user_a, :tenant_a, :identity_id, :user_a, 'Identity A', 'active', 1), "
                "(:user_b, :tenant_b, :identity_id, :user_b, 'Identity B', 'invited', 1)"
            ),
            {
                "identity_id": IDENTITY_ID,
                "user_a": USER_A_ID,
                "tenant_a": TENANT_A_ID,
                "user_b": USER_B_ID,
                "tenant_b": TENANT_B_ID,
            },
        )
        for tenant_id, user_id in (
            (TENANT_A_ID, USER_A_ID),
            (TENANT_B_ID, USER_B_ID),
        ):
            await connection.execute(
                text(
                    "insert into user_roles (tenant_id, user_id, role_id, role_scope_type) "
                    "select :tenant_id, :user_id, id, 'tenant' from roles "
                    "where code = 'employee'"
                ),
                {"tenant_id": tenant_id, "user_id": user_id},
            )
            await connection.execute(
                text(
                    "insert into membership_roles (tenant_id, membership_id, role_id, "
                    "role_scope_type) select :tenant_id, :user_id, id, 'tenant' "
                    "from roles where code = 'employee'"
                ),
                {"tenant_id": tenant_id, "user_id": user_id},
            )
        await connection.execute(
            text(
                "insert into user_activation_tokens (id, tenant_id, user_id, token_hash, "
                "expires_at) values (:id, :tenant_id, :user_id, :token_hash, "
                "CURRENT_TIMESTAMP + interval '1 hour')"
            ),
            {
                "id": uuid4(),
                "tenant_id": TENANT_B_ID,
                "user_id": USER_B_ID,
                "token_hash": activation_hash,
            },
        )
        await connection.execute(
            text(
                "insert into refresh_session_families (id, tenant_id, user_id, "
                "membership_id, expires_at) values (:id, :tenant_id, :user_id, :user_id, "
                "CURRENT_TIMESTAMP + interval '1 hour')"
            ),
            {"id": TENANT_FAMILY_ID, "tenant_id": TENANT_A_ID, "user_id": USER_A_ID},
        )
        await connection.execute(
            text(
                "insert into platform_refresh_session_families (id, identity_id, "
                "permission_version, authentication_strength, expires_at) values "
                "(:id, :identity_id, 1, 'single_factor', "
                "CURRENT_TIMESTAMP + interval '1 hour')"
            ),
            {"id": PLATFORM_FAMILY_ID, "identity_id": IDENTITY_ID},
        )


async def _assert_reset_storage_boundary(engine) -> None:
    async with engine.connect() as connection:
        force_rls = await connection.scalar(
            text(
                "select relrowsecurity and relforcerowsecurity from pg_catalog.pg_class "
                "where oid = 'public.password_reset_tokens'::regclass"
            )
        )
        assert force_rls is True
        recovery_role = (
            await connection.execute(
                text(
                    "select rolcanlogin, rolinherit, rolbypassrls from pg_catalog.pg_roles "
                    "where rolname = :role_name"
                ),
                {"role_name": _RECOVERY_ROLE},
            )
        ).one()
        assert recovery_role == (False, False, False)
        assert (
            await connection.scalar(
                text(
                    "select count(*) from pg_catalog.pg_auth_members as membership "
                    "join pg_catalog.pg_roles as role on role.oid = membership.roleid "
                    "where role.rolname = :role_name"
                ),
                {"role_name": _RECOVERY_ROLE},
            )
            == 0
        )
        recovery_privileges = set(
            await connection.scalars(
                text(
                    "select privilege_type from information_schema.role_table_grants "
                    "where table_schema = 'public' and table_name = 'password_reset_tokens' "
                    "and grantee = :role_name"
                ),
                {"role_name": _RECOVERY_ROLE},
            )
        )
        assert recovery_privileges == {"SELECT", "INSERT", "UPDATE"}
        assert (
            set(
                await connection.scalars(
                    text(
                        "select privilege_type from information_schema.role_table_grants "
                        "where table_schema = 'public' and table_name = 'employees' "
                        "and grantee = :role_name"
                    ),
                    {"role_name": _RECOVERY_ROLE},
                )
            )
            == set()
        )
        assert (
            set(
                await connection.scalars(
                    text(
                        "select privilege_type from information_schema.column_privileges "
                        "where table_schema = 'public' and table_name = 'employees' "
                        "and column_name = 'first_name' and grantee = :role_name"
                    ),
                    {"role_name": _RECOVERY_ROLE},
                )
            )
            == set()
        )
        assert not await connection.scalar(
            text(
                "select has_function_privilege(:role_name, "
                "'public.sync_current_tenant_identity_membership(uuid,boolean)', "
                "'EXECUTE')"
            ),
            {"role_name": _RECOVERY_ROLE},
        )
        auth_privileges = set(
            await connection.scalars(
                text(
                    "select privilege_type from information_schema.role_table_grants "
                    "where table_schema = 'public' and table_name = 'password_reset_tokens' "
                    "and grantee = :role_name"
                ),
                {"role_name": AUTHENTICATION_APPLICATION_ROLE},
            )
        )
        assert auth_privileges == set()
        assert await connection.scalar(
            text(
                "select has_function_privilege(:role_name, "
                "'public.issue_identity_password_reset(uuid,uuid,text,timestamptz)', "
                "'EXECUTE')"
            ),
            {"role_name": AUTHENTICATION_APPLICATION_ROLE},
        )
        assert await connection.scalar(
            text(
                "select has_function_privilege(:role_name, "
                "'public.complete_identity_password_reset(uuid,text,text)', 'EXECUTE')"
            ),
            {"role_name": AUTHENTICATION_APPLICATION_ROLE},
        )

    for role_name in (
        TENANT_APPLICATION_ROLE,
        PLATFORM_APPLICATION_ROLE,
        AUTHENTICATION_APPLICATION_ROLE,
    ):
        with pytest.raises(DBAPIError) as denied:
            async with engine.begin() as connection:
                if role_name == TENANT_APPLICATION_ROLE:
                    await _set_local_tenant_role(connection, TENANT_A_ID)
                else:
                    await _set_local_role(connection, role_name)
                await connection.execute(text("select id from password_reset_tokens"))
        assert sqlstate_from_error(denied.value) == "42501"


async def _set_local_tenant_role(connection, tenant_id: UUID) -> None:
    await _set_local_role(connection, TENANT_APPLICATION_ROLE)
    await connection.execute(
        text("select set_config('app.tenant_id', :tenant_id, true)"),
        {"tenant_id": str(tenant_id)},
    )


async def _set_local_role(connection, role_name: str) -> None:
    quoted_role = connection.dialect.identifier_preparer.quote(role_name)
    await connection.exec_driver_sql(f"SET LOCAL ROLE {quoted_role}")


async def _seed_hostile_recovery_role(database_url: URL) -> str:
    hostile_member = f"wf_p3e_stale_gateway_{uuid4().hex[:12]}"
    engine = create_async_engine(database_url, poolclass=NullPool)
    try:
        async with engine.begin() as connection:
            quote = connection.dialect.identifier_preparer.quote
            quoted_recovery = quote(_RECOVERY_ROLE)
            quoted_member = quote(hostile_member)
            await connection.exec_driver_sql(
                f"""
                DO $p3e_test_recovery_role$
                BEGIN
                    IF NOT EXISTS (
                        SELECT 1 FROM pg_catalog.pg_roles
                        WHERE rolname = '{_RECOVERY_ROLE}'
                    ) THEN
                        CREATE ROLE {quoted_recovery} NOLOGIN NOSUPERUSER NOBYPASSRLS NOINHERIT;
                    END IF;
                END
                $p3e_test_recovery_role$
                """
            )
            await connection.exec_driver_sql(
                f"CREATE ROLE {quoted_member} NOLOGIN NOSUPERUSER NOBYPASSRLS NOINHERIT"
            )
            await connection.exec_driver_sql(f"GRANT {quoted_recovery} TO {quoted_member}")
            await connection.exec_driver_sql(
                f"GRANT DELETE ON TABLE public.employees TO {quoted_recovery}"
            )
            await connection.exec_driver_sql(
                f"GRANT SELECT (first_name) ON TABLE public.employees TO {quoted_recovery}"
            )
            await connection.exec_driver_sql(
                "GRANT EXECUTE ON FUNCTION "
                "public.sync_current_tenant_identity_membership(uuid, boolean) "
                f"TO {quoted_recovery}"
            )
        return hostile_member
    finally:
        await engine.dispose()


async def _remove_hostile_recovery_member(
    database_url: URL,
    hostile_member: str,
) -> None:
    engine = create_async_engine(database_url, poolclass=NullPool)
    try:
        async with engine.begin() as connection:
            quote = connection.dialect.identifier_preparer.quote
            quoted_recovery = quote(_RECOVERY_ROLE)
            quoted_member = quote(hostile_member)
            await connection.exec_driver_sql(f"REVOKE {quoted_recovery} FROM {quoted_member}")
            await connection.exec_driver_sql(f"DROP ROLE {quoted_member}")
    finally:
        await engine.dispose()


async def _seed_hostile_recovery_owned_function(database_url: URL) -> str:
    function_name = f"wf_p3e_stale_owned_{uuid4().hex[:12]}"
    engine = create_async_engine(database_url, poolclass=NullPool)
    try:
        async with engine.begin() as connection:
            quote = connection.dialect.identifier_preparer.quote
            quoted_function = quote(function_name)
            quoted_recovery = quote(_RECOVERY_ROLE)
            await connection.exec_driver_sql(
                f"CREATE FUNCTION public.{quoted_function}() RETURNS integer "
                "LANGUAGE sql IMMUTABLE AS 'SELECT 1'"
            )
            await connection.exec_driver_sql(
                f"ALTER FUNCTION public.{quoted_function}() OWNER TO {quoted_recovery}"
            )
        return function_name
    finally:
        await engine.dispose()


async def _remove_hostile_recovery_owned_function(
    database_url: URL,
    function_name: str,
) -> None:
    engine = create_async_engine(database_url, poolclass=NullPool)
    try:
        async with engine.begin() as connection:
            quoted_function = connection.dialect.identifier_preparer.quote(function_name)
            await connection.exec_driver_sql(f"DROP FUNCTION public.{quoted_function}()")
    finally:
        await engine.dispose()


async def _current_revision(database_url: URL) -> str | None:
    engine = create_async_engine(database_url, poolclass=NullPool)
    try:
        async with engine.connect() as connection:
            return await connection.scalar(text("select version_num from alembic_version"))
    finally:
        await engine.dispose()


async def _seed_rate_limit_scope_rows(database_url: URL) -> None:
    engine = create_async_engine(database_url, poolclass=NullPool)
    try:
        async with engine.begin() as connection:
            await connection.execute(
                text(
                    "insert into authentication_rate_limit_buckets "
                    "(bucket_key_hash, scope, window_started_at, expires_at, "
                    "attempt_count, updated_at) values "
                    "(:login_hash, 'login_source', CURRENT_TIMESTAMP, "
                    "CURRENT_TIMESTAMP + interval '5 minutes', 1, CURRENT_TIMESTAMP), "
                    "(:confirm_hash, 'password_reset_confirm_token', CURRENT_TIMESTAMP, "
                    "CURRENT_TIMESTAMP + interval '5 minutes', 1, CURRENT_TIMESTAMP)"
                ),
                {"login_hash": "a" * 64, "confirm_hash": "b" * 64},
            )
    finally:
        await engine.dispose()


async def _rate_limit_scope_rows(database_url: URL) -> set[str]:
    engine = create_async_engine(database_url, poolclass=NullPool)
    try:
        async with engine.connect() as connection:
            return set(
                await connection.scalars(
                    text("select scope from authentication_rate_limit_buckets")
                )
            )
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
                        "from pg_catalog.pg_class where oid = cast(:table_name as regclass)"
                    ),
                    {"table_name": f"public.{table_name}"},
                )
            ).one()
            return bool(row[0]), bool(row[1])
    finally:
        await engine.dispose()


def _alembic_config(database_url: URL) -> Config:
    config = Config(str(ALEMBIC_INI))
    config.set_main_option(
        "sqlalchemy.url",
        database_url.render_as_string(hide_password=False).replace("%", "%%"),
    )
    return config
