from __future__ import annotations

import asyncio
from datetime import timedelta
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from alembic import command as alembic_command
from alembic.config import Config
from app.models.auth import RefreshSessionFamily
from app.platform.db.tenant_access import (
    AUTHENTICATION_APPLICATION_ROLE,
    TENANT_APPLICATION_ROLE,
)
from app.platform.identity import (
    AccessTokenCodec,
    PasswordManager,
    issue_organization_selection_token,
)
from app.services.auth_session_service import SessionGrant
from app.services.authentication_service import (
    AuthenticationService,
    InvalidOrganizationSelectionError,
)
from sqlalchemy import select, text
from sqlalchemy.engine import URL
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

pytestmark = pytest.mark.postgres

ROOT = Path(__file__).resolve().parents[3]
ALEMBIC_INI = ROOT / "alembic.ini"

TENANT_A_ID = UUID("7c100000-0000-4000-8000-000000000001")
TENANT_B_ID = UUID("7c100000-0000-4000-8000-000000000002")
USER_A_ID = UUID("7c200000-0000-4000-8000-000000000001")
USER_B_ID = UUID("7c200000-0000-4000-8000-000000000002")
SHARED_EMAIL = "selection-replay@p3c.test"
PASSWORD_HASH = "$argon2id$p3c-test-projection-hash"


@pytest.fixture
def p3c_postgres_database(postgres_database_url: URL) -> URL:
    alembic_command.upgrade(_alembic_config(postgres_database_url), "head")
    return postgres_database_url


async def test_concurrent_selection_consumption_has_one_session_winner_and_exact_acl(
    p3c_postgres_database: URL,
) -> None:
    engine = create_async_engine(p3c_postgres_database, poolclass=NullPool)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    token = issue_organization_selection_token()
    selection_key = uuid4()
    try:
        await _seed_multi_membership_selection(
            engine,
            transaction_id=token.transaction_id,
            token_hash=token.token_hash,
            selection_key=selection_key,
        )
        access_tokens = AccessTokenCodec(
            b"p3c-postgresql-selection-signing-key",
            ttl=timedelta(minutes=5),
        )
        service = AuthenticationService(
            session_factory=session_factory,
            password_manager=PasswordManager(),
            access_tokens=access_tokens,
        )
        start = asyncio.Event()

        async def select_once() -> SessionGrant:
            await start.wait()
            return await service.select_organization(
                raw_token=token.raw_token,
                selection_key=selection_key,
            )

        attempts = [asyncio.create_task(select_once()), asyncio.create_task(select_once())]
        start.set()
        outcomes = await asyncio.gather(*attempts, return_exceptions=True)

        winners = [outcome for outcome in outcomes if isinstance(outcome, SessionGrant)]
        replays = [
            outcome
            for outcome in outcomes
            if isinstance(outcome, InvalidOrganizationSelectionError)
        ]
        assert len(winners) == 1
        assert len(replays) == 1
        winner = winners[0]
        principal = access_tokens.decode(winner.access_token)
        assert principal.tenant_id == TENANT_B_ID
        assert principal.membership_id == USER_B_ID

        async with engine.connect() as connection:
            consumed_at = await connection.scalar(
                text(
                    "select consumed_at from organization_selection_transactions "
                    "where id = :transaction_id"
                ),
                {"transaction_id": token.transaction_id},
            )
            families = tuple(
                (
                    await connection.execute(
                        select(
                            RefreshSessionFamily.id,
                            RefreshSessionFamily.tenant_id,
                            RefreshSessionFamily.user_id,
                            RefreshSessionFamily.membership_id,
                        )
                    )
                ).all()
            )
            policies = {
                (row.tablename, row.policyname, row.cmd)
                for row in (
                    await connection.execute(
                        text(
                            "select tablename, policyname, cmd from pg_catalog.pg_policies "
                            "where schemaname = 'public' and :role_name = any(roles) "
                            "and tablename in ('organization_selection_transactions', "
                            "'organization_selection_choices')"
                        ),
                        {"role_name": AUTHENTICATION_APPLICATION_ROLE},
                    )
                )
            }
            update_columns = {
                row.column_name
                for row in (
                    await connection.execute(
                        text(
                            "select column_name from information_schema.column_privileges "
                            "where table_schema = 'public' "
                            "and table_name = 'organization_selection_transactions' "
                            "and grantee = :role_name and privilege_type = 'UPDATE'"
                        ),
                        {"role_name": AUTHENTICATION_APPLICATION_ROLE},
                    )
                )
            }

        assert consumed_at is not None
        assert len(families) == 1
        assert tuple(families[0]) == (
            principal.session_family_id,
            TENANT_B_ID,
            USER_B_ID,
            USER_B_ID,
        )
        assert {
            (
                "organization_selection_transactions",
                "authentication_selection_transaction_select",
                "SELECT",
            ),
            (
                "organization_selection_transactions",
                "authentication_selection_transaction_consume",
                "UPDATE",
            ),
            (
                "organization_selection_choices",
                "authentication_selection_choice_select",
                "SELECT",
            ),
        } <= policies
        assert update_columns == {"consumed_at", "updated_at"}
    finally:
        await engine.dispose()


async def _seed_multi_membership_selection(
    engine,
    *,
    transaction_id: UUID,
    token_hash: str,
    selection_key: UUID,
) -> None:
    async with engine.begin() as connection:
        await connection.execute(
            text(
                "insert into tenants ("
                "id, slug, name, status, plan_code, data_region, locale, timezone"
                ") values ("
                ":tenant_a, 'p3c-a', 'P3C Organization A', 'active', "
                "'core', 'tr-1', 'en-US', 'UTC'"
                "), ("
                ":tenant_b, 'p3c-b', 'P3C Organization B', 'active', "
                "'core', 'tr-1', 'en-US', 'UTC'"
                ")"
            ),
            {"tenant_a": TENANT_A_ID, "tenant_b": TENANT_B_ID},
        )
        await connection.execute(
            text(
                "insert into users ("
                "id, tenant_id, email, full_name, status, password_hash, permission_version"
                ") values ("
                ":user_a, :tenant_a, :email, 'P3C User A', 'active', :password_hash, 1"
                "), ("
                ":user_b, :tenant_b, :email, 'P3C User B', 'active', :password_hash, 1"
                ")"
            ),
            {
                "user_a": USER_A_ID,
                "tenant_a": TENANT_A_ID,
                "user_b": USER_B_ID,
                "tenant_b": TENANT_B_ID,
                "email": SHARED_EMAIL,
                "password_hash": PASSWORD_HASH,
            },
        )

    for tenant_id, user_id in (
        (TENANT_A_ID, USER_A_ID),
        (TENANT_B_ID, USER_B_ID),
    ):
        async with engine.begin() as connection:
            await connection.exec_driver_sql(
                f'SET LOCAL ROLE "{TENANT_APPLICATION_ROLE}"'
            )
            await connection.exec_driver_sql(
                f"SET LOCAL app.tenant_id = '{tenant_id}'"
            )
            await connection.execute(
                text("select public.sync_current_tenant_identity_membership(:user_id)"),
                {"user_id": user_id},
            )

    async with engine.begin() as connection:
        await connection.exec_driver_sql(
            f'SET LOCAL ROLE "{AUTHENTICATION_APPLICATION_ROLE}"'
        )
        await connection.execute(
            text(
                "insert into organization_selection_transactions ("
                "id, identity_id, token_hash, expires_at"
                ") values ("
                ":transaction_id, :identity_id, :token_hash, "
                "CURRENT_TIMESTAMP + interval '5 minutes'"
                ")"
            ),
            {
                "transaction_id": transaction_id,
                "identity_id": USER_A_ID,
                "token_hash": token_hash,
            },
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
                "tenant_id": TENANT_B_ID,
            },
        )


def _alembic_config(database_url: URL) -> Config:
    config = Config(str(ALEMBIC_INI))
    config.set_main_option("sqlalchemy.url", database_url.render_as_string(hide_password=False))
    return config
