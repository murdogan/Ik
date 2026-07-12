from __future__ import annotations

import json
from collections import Counter
from datetime import timedelta
from pathlib import Path
from uuid import UUID

import pytest
from alembic import command as alembic_command
from alembic.config import Config
from app.platform.audit import AuditScopeType
from app.platform.identity import AccessTokenCodec, PasswordManager
from app.platform.request_context import AuthenticationStrength, RequestContext
from app.platform.tenancy import TenantContext
from app.schemas.audit import AuditListPagination
from app.schemas.user_administration import UserListPagination
from app.services.audit_query_service import AuditQueryService
from app.services.authentication_service import AuthenticationService
from app.services.user_administration_service import UserAdministrationService
from sqlalchemy import event, text
from sqlalchemy.engine import URL
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
TENANT_ID = UUID("fa000000-0000-4000-8000-000000000001")
ADMIN_ID = UUID("fa100000-0000-4000-8000-000000000001")
TENANT_SLUG = "f2f-query-smoke"
ADMIN_EMAIL = "admin@f2f-query.test"
PASSWORD = "F2F bounded query smoke password"
DATASET_SIZE = 1_000


@pytest.fixture
def f2f_postgres_database(postgres_database_url: URL) -> URL:
    alembic_command.upgrade(_alembic_config(postgres_database_url), "head")
    return postgres_database_url


async def test_login_user_list_and_audit_list_stay_bounded(
    f2f_postgres_database: URL,
) -> None:
    engine = create_async_engine(f2f_postgres_database, poolclass=NullPool)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    passwords = PasswordManager()
    try:
        await _seed_query_smoke_dataset(
            engine,
            password_hash=await passwords.hash_async(PASSWORD),
        )
        statements: list[str] = []

        def capture_statement(
            _connection,
            _cursor,
            statement: str,
            _parameters,
            _context,
            _executemany: bool,
        ) -> None:
            statements.append(statement)

        event.listen(engine.sync_engine, "before_cursor_execute", capture_statement)
        try:
            authentication = AuthenticationService(
                session_factory=session_factory,
                password_manager=passwords,
                access_tokens=AccessTokenCodec(
                    b"f2f-query-smoke-signing-key-material",
                    ttl=timedelta(minutes=5),
                ),
            )
            statements.clear()
            grant = await authentication.login(
                tenant_slug=TENANT_SLUG,
                email=ADMIN_EMAIL,
                password=PASSWORD,
            )
            login_counts = _statement_counts(statements)

            request_context = RequestContext(
                request_id="req_f2f_query_smoke",
                trace_id="f2f00000000000000000000000000001",
                tenant=TenantContext(tenant_id=TENANT_ID, slug=TENANT_SLUG),
                actor_id=ADMIN_ID,
                session_id=grant.session_family_id,
                authentication_strength=AuthenticationStrength.SINGLE_FACTOR,
            )
            statements.clear()
            user_page = await UserAdministrationService(
                session_factory=session_factory
            ).list_users(
                request_context=request_context,
                pagination=UserListPagination(limit=25),
                granted_permissions=("user:read:tenant",),
            )
            user_list_counts = _statement_counts(statements)

            statements.clear()
            audit_page = await AuditQueryService(
                session_factory=session_factory
            ).list_tenant_events(
                tenant_id=TENANT_ID,
                role_codes=("tenant_admin",),
                pagination=AuditListPagination(
                    limit=25,
                    scope_type=AuditScopeType.TENANT,
                ),
            )
            audit_list_counts = _statement_counts(statements)
        finally:
            event.remove(engine.sync_engine, "before_cursor_execute", capture_statement)

        evidence = {
            "dataset_rows": DATASET_SIZE,
            "login": dict(sorted(login_counts.items())),
            "user_list": dict(sorted(user_list_counts.items())),
            "audit_list": dict(sorted(audit_list_counts.items())),
        }
        print(f"F2F_QUERY_BUDGET_EVIDENCE={json.dumps(evidence, sort_keys=True)}")

        assert grant.user.id == ADMIN_ID
        assert login_counts["SELECT"] <= 4
        assert sum(login_counts.values()) <= 13

        assert len(user_page.items) == 25
        assert user_page.next_cursor is not None
        assert user_list_counts["SELECT"] <= 2
        assert sum(user_list_counts.values()) <= 4

        assert len(audit_page.items) == 25
        assert audit_page.next_cursor is not None
        assert audit_list_counts["SELECT"] <= 1
        assert sum(audit_list_counts.values()) <= 3
    finally:
        await engine.dispose()


def _alembic_config(database_url: URL) -> Config:
    config = Config(str(ALEMBIC_INI))
    config.set_main_option(
        "sqlalchemy.url",
        database_url.render_as_string(hide_password=False).replace("%", "%%"),
    )
    return config


def _statement_counts(statements: list[str]) -> Counter[str]:
    return Counter(statement.lstrip().partition(" ")[0].upper() for statement in statements)


async def _seed_query_smoke_dataset(
    engine: AsyncEngine,
    *,
    password_hash: str,
) -> None:
    async with engine.begin() as connection:
        await connection.execute(
            text(
                "insert into tenants ("
                "id, slug, name, status, plan_code, data_region, locale, timezone"
                ") values ("
                ":tenant_id, :slug, 'F2F Query Smoke', 'active', 'core', "
                "'tr-1', 'en-US', 'UTC'"
                ")"
            ),
            {"tenant_id": TENANT_ID, "slug": TENANT_SLUG},
        )
        await connection.execute(
            text(
                "insert into users ("
                "id, tenant_id, email, full_name, status, password_hash, can_invite_users"
                ") values ("
                ":admin_id, :tenant_id, :email, 'F2F Tenant Administrator', "
                "'active', :password_hash, true"
                ")"
            ),
            {
                "admin_id": ADMIN_ID,
                "tenant_id": TENANT_ID,
                "email": ADMIN_EMAIL,
                "password_hash": password_hash,
            },
        )
        await connection.execute(
            text(
                "insert into users (id, tenant_id, email, full_name, status) "
                "select "
                "('fa200000-0000-4000-8000-' || lpad(gs::text, 12, '0'))::uuid, "
                ":tenant_id, "
                "'employee' || lpad(gs::text, 6, '0') || '@f2f-query.test', "
                "'F2F Employee ' || lpad(gs::text, 6, '0'), "
                "'active' "
                "from generate_series(1, :dataset_size) as gs"
            ),
            {"tenant_id": TENANT_ID, "dataset_size": DATASET_SIZE},
        )
        await _assign_role(
            connection,
            user_predicate="users.id = :admin_id",
            role_code="tenant_admin",
            parameters={"admin_id": ADMIN_ID},
        )
        await _assign_role(
            connection,
            user_predicate="users.id <> :admin_id",
            role_code="employee",
            parameters={"admin_id": ADMIN_ID},
        )
        await connection.execute(
            text(
                "insert into audit_events ("
                "id, occurred_at, scope_type, tenant_id, actor_type, actor_user_id, "
                "event_type, category, severity, resource_type, resource_id, action, result, "
                "request_id, trace_id, changed_fields, before_data, after_data, metadata, "
                "data_classification, visibility_class"
                ") select "
                "('fa300000-0000-4000-8000-' || lpad(gs::text, 12, '0'))::uuid, "
                "timestamptz '2026-07-12 09:00:00+00' - gs * interval '1 second', "
                "'tenant', :tenant_id, 'system', :admin_id, "
                "case when gs % 2 = 0 then 'auth.login.succeeded' "
                "else 'user.status.changed' end, "
                "case when gs % 2 = 0 then 'tenant_security' else 'tenant_admin' end, "
                "'info', 'user', :admin_id, 'read', 'success', "
                "'req_f2f_query_' || lpad(gs::text, 6, '0'), "
                "'f2f00000000000000000000000000001', "
                "'[]'::jsonb, '{}'::jsonb, '{}'::jsonb, '{}'::jsonb, "
                "'security_metadata', "
                "case when gs % 2 = 0 then 'tenant_security' else 'tenant_admin' end "
                "from generate_series(1, :dataset_size) as gs"
            ),
            {
                "tenant_id": TENANT_ID,
                "admin_id": ADMIN_ID,
                "dataset_size": DATASET_SIZE,
            },
        )


async def _assign_role(
    connection: AsyncConnection,
    *,
    user_predicate: str,
    role_code: str,
    parameters: dict[str, object],
) -> None:
    await connection.execute(
        text(
            "insert into user_roles ("
            "tenant_id, user_id, role_id, role_scope_type, active"
            ") select users.tenant_id, users.id, roles.id, roles.scope_type, true "
            "from users cross join roles "
            f"where {user_predicate} and roles.code = :role_code"
        ),
        {**parameters, "role_code": role_code},
    )
