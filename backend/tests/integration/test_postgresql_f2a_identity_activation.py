from __future__ import annotations

import asyncio
from datetime import timedelta
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from alembic import command as alembic_command
from alembic.config import Config
from app.models.auth import UserActivationToken
from app.models.user import User, UserStatus
from app.platform.db import sqlstate_from_error
from app.platform.db.tenant_access import TENANT_APPLICATION_ROLE
from app.platform.identity import (
    AccessTokenCodec,
    PasswordManager,
    issue_activation_token,
)
from app.services.authentication_service import (
    AuthenticatedUser,
    AuthenticationService,
    InvalidActivationError,
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

TENANT_A_ID = UUID("61000000-0000-4000-8000-000000000001")
TENANT_B_ID = UUID("61000000-0000-4000-8000-000000000002")
USER_A_ID = UUID("62000000-0000-4000-8000-000000000001")
USER_B_ID = UUID("62000000-0000-4000-8000-000000000002")
TOKEN_A_ID = UUID("63000000-0000-4000-8000-000000000001")
TOKEN_B_ID = UUID("63000000-0000-4000-8000-000000000002")

PASSWORD_A = "F2A concurrent activation password A"
PASSWORD_B = "F2A concurrent activation password B"


@pytest.fixture
def f2a_postgres_database(postgres_database_url: URL) -> URL:
    alembic_command.upgrade(_alembic_config(postgres_database_url), "head")
    return postgres_database_url


async def test_activation_token_rows_are_hidden_and_cross_tenant_writes_are_blocked(
    f2a_postgres_database: URL,
) -> None:
    engine = create_async_engine(f2a_postgres_database, poolclass=NullPool)
    try:
        token_a = issue_activation_token(TENANT_A_ID)
        token_b = issue_activation_token(TENANT_B_ID)
        await _seed_identity_rows(
            engine,
            token_a_hash=token_a.token_hash,
            token_b_hash=token_b.token_hash,
        )

        async with engine.begin() as connection:
            await _set_local_tenant_role(connection, TENANT_A_ID)
            assert tuple(
                await connection.scalars(
                    text("select id from user_activation_tokens order by id")
                )
            ) == (TOKEN_A_ID,)
            assert (
                await connection.scalar(
                    text(
                        "select id from user_activation_tokens "
                        "where token_hash = :token_hash"
                    ),
                    {"token_hash": token_b.token_hash},
                )
                is None
            )
            hidden_update = await connection.execute(
                text(
                    "update user_activation_tokens set revoked_at = CURRENT_TIMESTAMP "
                    "where id = :token_id"
                ),
                {"token_id": TOKEN_B_ID},
            )
            assert hidden_update.rowcount == 0

        with pytest.raises(DBAPIError) as cross_tenant_insert:
            async with engine.begin() as connection:
                await _set_local_tenant_role(connection, TENANT_A_ID)
                await connection.execute(
                    text(
                        "insert into user_activation_tokens ("
                        "id, tenant_id, user_id, token_hash, expires_at"
                        ") values ("
                        ":id, :tenant_id, :user_id, :token_hash, "
                        "CURRENT_TIMESTAMP + INTERVAL '1 hour'"
                        ")"
                    ),
                    {
                        "id": uuid4(),
                        "tenant_id": TENANT_B_ID,
                        "user_id": USER_B_ID,
                        "token_hash": "c" * 64,
                    },
                )
        assert sqlstate_from_error(cross_tenant_insert.value) == "42501"

        async with engine.begin() as connection:
            await _set_local_tenant_role(connection, TENANT_B_ID)
            assert tuple(
                await connection.scalars(
                    text("select id from user_activation_tokens order by id")
                )
            ) == (TOKEN_B_ID,)

        async with engine.connect() as connection:
            token_b_state = (
                await connection.execute(
                    text(
                        "select consumed_at, revoked_at from user_activation_tokens "
                        "where id = :token_id"
                    ),
                    {"token_id": TOKEN_B_ID},
                )
            ).one()
            assert token_b_state == (None, None)
    finally:
        await engine.dispose()


async def test_two_concurrent_activations_have_exactly_one_winner(
    f2a_postgres_database: URL,
) -> None:
    engine = create_async_engine(f2a_postgres_database, poolclass=NullPool)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    password_manager = PasswordManager()
    activation = issue_activation_token(TENANT_A_ID)
    service = AuthenticationService(
        session_factory=session_factory,
        password_manager=password_manager,
        access_tokens=AccessTokenCodec(
            b"f2a-postgresql-test-signing-key!",
            ttl=timedelta(minutes=5),
        ),
    )
    try:
        await _seed_identity_rows(
            engine,
            token_a_hash=activation.token_hash,
            token_b_hash=issue_activation_token(TENANT_B_ID).token_hash,
        )

        start = asyncio.Event()

        async def activate(password: str) -> AuthenticatedUser:
            await start.wait()
            return await service.activate(raw_token=activation.raw_token, password=password)

        attempts = [
            asyncio.create_task(activate(PASSWORD_A)),
            asyncio.create_task(activate(PASSWORD_B)),
        ]
        start.set()
        outcomes = await asyncio.gather(*attempts, return_exceptions=True)

        winners = [outcome for outcome in outcomes if isinstance(outcome, AuthenticatedUser)]
        losers = [outcome for outcome in outcomes if isinstance(outcome, InvalidActivationError)]
        assert len(winners) == 1
        assert len(losers) == 1
        assert winners[0].id == USER_A_ID

        async with engine.connect() as connection:
            user_row = (
                await connection.execute(
                    select(User.status, User.password_hash).where(User.id == USER_A_ID)
                )
            ).one()
            consumed_at = await connection.scalar(
                select(UserActivationToken.consumed_at).where(
                    UserActivationToken.id == TOKEN_A_ID
                )
            )

        assert user_row.status == UserStatus.ACTIVE.value
        assert user_row.password_hash is not None
        password_matches = {
            password
            for password in (PASSWORD_A, PASSWORD_B)
            if password_manager.verify(password, user_row.password_hash)
        }
        assert len(password_matches) == 1
        assert consumed_at is not None
    finally:
        await engine.dispose()


def _alembic_config(database_url: URL) -> Config:
    config = Config(str(ALEMBIC_INI))
    config.set_main_option(
        "sqlalchemy.url",
        database_url.render_as_string(hide_password=False).replace("%", "%%"),
    )
    return config


async def _seed_identity_rows(
    engine: AsyncEngine,
    *,
    token_a_hash: str,
    token_b_hash: str,
) -> None:
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
                {"id": TENANT_A_ID, "slug": "f2a-pg-tenant-a", "name": "Tenant A"},
                {"id": TENANT_B_ID, "slug": "f2a-pg-tenant-b", "name": "Tenant B"},
            ],
        )
        await connection.execute(
            text(
                "insert into users ("
                "id, tenant_id, email, full_name, status, password_hash"
                ") values ("
                ":id, :tenant_id, :email, :full_name, 'invited', NULL"
                ")"
            ),
            [
                {
                    "id": USER_A_ID,
                    "tenant_id": TENANT_A_ID,
                    "email": "activation-a@example.test",
                    "full_name": "Activation A",
                },
                {
                    "id": USER_B_ID,
                    "tenant_id": TENANT_B_ID,
                    "email": "activation-b@example.test",
                    "full_name": "Activation B",
                },
            ],
        )
        await connection.execute(
            text(
                "insert into user_activation_tokens ("
                "id, tenant_id, user_id, token_hash, expires_at"
                ") values ("
                ":id, :tenant_id, :user_id, :token_hash, "
                "CURRENT_TIMESTAMP + INTERVAL '1 hour'"
                ")"
            ),
            [
                {
                    "id": TOKEN_A_ID,
                    "tenant_id": TENANT_A_ID,
                    "user_id": USER_A_ID,
                    "token_hash": token_a_hash,
                },
                {
                    "id": TOKEN_B_ID,
                    "tenant_id": TENANT_B_ID,
                    "user_id": USER_B_ID,
                    "token_hash": token_b_hash,
                },
            ],
        )


async def _set_local_tenant_role(
    connection: AsyncConnection,
    tenant_id: UUID,
) -> None:
    await connection.exec_driver_sql(f'SET LOCAL ROLE "{TENANT_APPLICATION_ROLE}"')
    await connection.exec_driver_sql(f"SET LOCAL app.tenant_id = '{tenant_id}'")
