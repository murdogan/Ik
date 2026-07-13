from __future__ import annotations

import asyncio
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from alembic import command as alembic_command
from alembic.config import Config
from app.platform.db import (
    SqlAlchemyUnitOfWork,
    configure_platform_database_access,
    sqlstate_from_error,
)
from app.platform.db.tenant_access import (
    AUTHENTICATION_APPLICATION_ROLE,
    PLATFORM_APPLICATION_ROLE,
    TENANT_APPLICATION_ROLE,
)
from app.platform.request_context import AuthenticationStrength, RequestContext
from app.platform.tenancy import TenantContext
from app.schemas.organization import BranchCreate, LegalEntityUpdate
from app.schemas.tenant import TenantPlatformCreate
from app.services.organization_service import (
    ORGANIZATION_READ_PERMISSION,
    ORGANIZATION_UPDATE_PERMISSION,
    OrganizationConflictError,
    OrganizationService,
)
from app.services.tenant_service import TenantReadOnlyError, TenantService
from sqlalchemy import text
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
PRE_P3F_REVISION = "0026_p3e_identity_checkpoint"

TENANT_A_ID = UUID("d1000000-0000-4000-8000-000000000001")
TENANT_B_ID = UUID("d1000000-0000-4000-8000-000000000002")
BRANCH_A_ID = UUID("d2000000-0000-4000-8000-000000000001")
BRANCH_B_ID = UUID("d2000000-0000-4000-8000-000000000002")
CROSS_TENANT_BRANCH_ID = UUID("d2000000-0000-4000-8000-000000000003")
CONCURRENT_ENTITY_ID = UUID("d3000000-0000-4000-8000-000000000001")

SECURED_TABLES = ("legal_entities", "branches")
CAPABILITY_ROLES = (
    TENANT_APPLICATION_ROLE,
    PLATFORM_APPLICATION_ROLE,
    AUTHENTICATION_APPLICATION_ROLE,
)
LEGAL_ENTITY_UPDATE_COLUMNS = frozenset(
    {
        "name",
        "registered_name",
        "country_code",
        "tax_number",
        "timezone",
        "status",
        "updated_at",
    }
)
BRANCH_UPDATE_COLUMNS = frozenset(
    {
        "name",
        "timezone",
        "country_code",
        "city",
        "address",
        "status",
        "archived_at",
        "updated_at",
    }
)


@pytest.fixture
def p3f_postgres_database(postgres_database_url: URL) -> URL:
    config = _alembic_config(postgres_database_url)
    alembic_command.upgrade(config, PRE_P3F_REVISION)
    asyncio.run(_seed_pre_p3f_tenants(postgres_database_url))
    alembic_command.upgrade(config, "head")
    return postgres_database_url


def test_p3f_backfill_rls_acl_relational_isolation_and_platform_provisioning(
    p3f_postgres_database: URL,
) -> None:
    asyncio.run(_assert_p3f_postgresql_contract(p3f_postgres_database))


async def _assert_p3f_postgresql_contract(database_url: URL) -> None:
    engine = create_async_engine(database_url, poolclass=NullPool)
    try:
        await _assert_backfilled_defaults(engine)
        await _assert_security_catalog(engine)
        await _insert_branch(
            engine,
            tenant_id=TENANT_A_ID,
            branch_id=BRANCH_A_ID,
            code="A-HQ",
            name="Tenant A Headquarters",
        )
        await _insert_branch(
            engine,
            tenant_id=TENANT_B_ID,
            branch_id=BRANCH_B_ID,
            code="B-HQ",
            name="Tenant B Headquarters",
        )
        await _assert_tenant_runtime_isolation(engine)
        await _assert_cross_tenant_composite_fk(engine)
        await _assert_branch_create_and_parent_deactivation_serialize(engine)
        await _assert_organization_write_serializes_with_tenant_lifecycle(engine)
        await _assert_immutable_code_and_no_delete_acl(engine)
        await _assert_non_tenant_capabilities_cannot_read_organization(engine)
        await _assert_platform_cannot_insert_nondefault_legal_entity(engine)
        await _assert_platform_tenant_service_creates_default(engine)
    finally:
        await engine.dispose()


async def _assert_backfilled_defaults(engine: AsyncEngine) -> None:
    expected = {
        TENANT_A_ID: (
            "DEFAULT",
            "P3F Tenant A",
            "P3F Tenant A",
            "Europe/Istanbul",
        ),
        TENANT_B_ID: (
            "DEFAULT",
            "P3F Tenant B",
            "P3F Tenant B",
            "Europe/London",
        ),
    }
    for tenant_id, expected_values in expected.items():
        async with engine.begin() as connection:
            await _set_local_tenant_role(connection, tenant_id)
            rows = (
                await connection.execute(
                    text(
                        "select id, tenant_id, code, name, registered_name, timezone, "
                        "status, is_default from legal_entities"
                    )
                )
            ).all()
        assert rows == [
            (
                tenant_id,
                tenant_id,
                *expected_values,
                "active",
                True,
            )
        ]


async def _assert_security_catalog(engine: AsyncEngine) -> None:
    async with engine.connect() as connection:
        security_rows = (
            await connection.execute(
                text(
                    "select c.relname, c.relrowsecurity, c.relforcerowsecurity "
                    "from pg_catalog.pg_class c "
                    "join pg_catalog.pg_namespace n on n.oid = c.relnamespace "
                    "where n.nspname = 'public' and c.relname = any(:table_names)"
                ),
                {"table_names": list(SECURED_TABLES)},
            )
        ).mappings()
        security = {
            row["relname"]: (row["relrowsecurity"], row["relforcerowsecurity"])
            for row in security_rows
        }
        assert security == {
            "legal_entities": (True, True),
            "branches": (True, True),
        }

        policy_rows = (
            await connection.execute(
                text(
                    "select tablename, policyname, roles, cmd, qual, with_check "
                    "from pg_catalog.pg_policies where schemaname = 'public' "
                    "and tablename = any(:table_names)"
                ),
                {"table_names": list(SECURED_TABLES)},
            )
        ).mappings()
        policies = {(row["tablename"], row["policyname"]): row for row in policy_rows}
        assert set(policies) == {
            ("legal_entities", "tenant_isolation_app"),
            ("legal_entities", "platform_provision_legal_entity"),
            ("branches", "tenant_isolation_app"),
        }
        for table_name in SECURED_TABLES:
            policy = policies[(table_name, "tenant_isolation_app")]
            assert tuple(policy["roles"]) == (TENANT_APPLICATION_ROLE,)
            assert policy["cmd"] == "ALL"
            assert "app.tenant_id" in policy["qual"]
            assert policy["with_check"] == policy["qual"]
        platform_insert = policies[("legal_entities", "platform_provision_legal_entity")]
        assert tuple(platform_insert["roles"]) == (PLATFORM_APPLICATION_ROLE,)
        assert platform_insert["cmd"] == "INSERT"
        assert platform_insert["qual"] is None
        platform_check = platform_insert["with_check"]
        assert platform_check != "true"
        for required_identifier in (
            "id",
            "tenant_id",
            "code",
            "name",
            "registered_name",
            "country_code",
            "tax_number",
            "status",
            "is_default",
        ):
            assert required_identifier in platform_check

        assert await _direct_table_acl(connection) == {
            ("legal_entities", TENANT_APPLICATION_ROLE, "SELECT", False),
            ("legal_entities", TENANT_APPLICATION_ROLE, "INSERT", False),
            ("legal_entities", PLATFORM_APPLICATION_ROLE, "INSERT", False),
            ("branches", TENANT_APPLICATION_ROLE, "SELECT", False),
            ("branches", TENANT_APPLICATION_ROLE, "INSERT", False),
        }
        assert await _direct_update_column_acl(connection) == {
            *(
                ("legal_entities", column_name, TENANT_APPLICATION_ROLE, False)
                for column_name in LEGAL_ENTITY_UPDATE_COLUMNS
            ),
            *(
                ("branches", column_name, TENANT_APPLICATION_ROLE, False)
                for column_name in BRANCH_UPDATE_COLUMNS
            ),
        }


async def _insert_branch(
    engine: AsyncEngine,
    *,
    tenant_id: UUID,
    branch_id: UUID,
    code: str,
    name: str,
) -> None:
    async with engine.begin() as connection:
        await _set_local_tenant_role(connection, tenant_id)
        await connection.execute(
            text(
                "insert into branches ("
                "id, tenant_id, legal_entity_id, code, name, timezone, status"
                ") values ("
                ":id, :tenant_id, :legal_entity_id, :code, :name, 'UTC', 'active'"
                ")"
            ),
            {
                "id": branch_id,
                "tenant_id": tenant_id,
                "legal_entity_id": tenant_id,
                "code": code,
                "name": name,
            },
        )


async def _assert_tenant_runtime_isolation(engine: AsyncEngine) -> None:
    async with engine.begin() as connection:
        await _set_local_tenant_role(connection, TENANT_A_ID)
        assert tuple(
            await connection.scalars(
                text("select tenant_id from legal_entities order by tenant_id")
            )
        ) == (TENANT_A_ID,)
        assert tuple(await connection.scalars(text("select id from branches order by id"))) == (
            BRANCH_A_ID,
        )
        branch_update = await connection.execute(
            text("update branches set name = 'must-not-change' where id = :id"),
            {"id": BRANCH_B_ID},
        )
        entity_update = await connection.execute(
            text("update legal_entities set name = 'must-not-change' where id = :id"),
            {"id": TENANT_B_ID},
        )
        assert branch_update.rowcount == 0
        assert entity_update.rowcount == 0

    async with engine.begin() as connection:
        await _set_local_tenant_role(connection, TENANT_B_ID)
        assert (
            await connection.scalar(
                text("select name from branches where id = :id"),
                {"id": BRANCH_B_ID},
            )
            == "Tenant B Headquarters"
        )
        assert (
            await connection.scalar(
                text("select name from legal_entities where id = :id"),
                {"id": TENANT_B_ID},
            )
            == "P3F Tenant B"
        )


async def _assert_cross_tenant_composite_fk(engine: AsyncEngine) -> None:
    with pytest.raises(DBAPIError) as foreign_key_error:
        async with engine.begin() as connection:
            await _set_local_tenant_role(connection, TENANT_A_ID)
            await connection.execute(
                text(
                    "insert into branches ("
                    "id, tenant_id, legal_entity_id, code, name, timezone, status"
                    ") values ("
                    ":id, :tenant_id, :legal_entity_id, 'ESCAPE', "
                    "'Cross tenant branch', 'UTC', 'active'"
                    ")"
                ),
                {
                    "id": CROSS_TENANT_BRANCH_ID,
                    "tenant_id": TENANT_A_ID,
                    "legal_entity_id": TENANT_B_ID,
                },
            )
    assert sqlstate_from_error(foreign_key_error.value) == "23503"


class _NoopAuditRecorder:
    async def record(self, _event: object) -> None:
        return None


async def _assert_branch_create_and_parent_deactivation_serialize(
    engine: AsyncEngine,
) -> None:
    async with engine.begin() as connection:
        await _set_local_tenant_role(connection, TENANT_A_ID)
        await connection.execute(
            text(
                "insert into tenant_feature_flags (tenant_id, key, enabled) "
                "values (:tenant_id, 'organization', true) "
                "on conflict (tenant_id, key) do update set enabled = excluded.enabled"
            ),
            {"tenant_id": TENANT_A_ID},
        )
        await connection.execute(
            text(
                "insert into legal_entities ("
                "id, tenant_id, code, name, registered_name, timezone, status, is_default"
                ") values ("
                ":id, :tenant_id, 'CONCURRENT', 'Concurrent entity', "
                "'Concurrent entity', 'UTC', 'active', false)"
            ),
            {"id": CONCURRENT_ENTITY_ID, "tenant_id": TENANT_A_ID},
        )

    service = OrganizationService(
        session_factory=async_sessionmaker(engine, expire_on_commit=False),
        audit_recorder_factory=lambda _session: _NoopAuditRecorder(),
    )
    context = RequestContext(
        request_id="req-p3f-concurrency",
        trace_id="1234567890abcdef1234567890abcdef",
        tenant=TenantContext(tenant_id=TENANT_A_ID, slug="p3f-tenant-a"),
        actor_id=uuid4(),
        authentication_strength=AuthenticationStrength.SINGLE_FACTOR,
    )
    permissions = (ORGANIZATION_READ_PERMISSION, ORGANIZATION_UPDATE_PERMISSION)
    results = await asyncio.gather(
        service.create_branch(
            request_context=context,
            payload=BranchCreate(
                legal_entity_id=CONCURRENT_ENTITY_ID,
                code="CONCURRENT-BRANCH",
                name="Concurrent branch",
                timezone="UTC",
            ),
            granted_permissions=permissions,
        ),
        service.update_legal_entity(
            request_context=context,
            legal_entity_id=CONCURRENT_ENTITY_ID,
            payload=LegalEntityUpdate(status="inactive"),
            granted_permissions=permissions,
        ),
        return_exceptions=True,
    )
    assert sum(isinstance(result, OrganizationConflictError) for result in results) == 1

    async with engine.begin() as connection:
        await _set_local_tenant_role(connection, TENANT_A_ID)
        entity_status = await connection.scalar(
            text("select status from legal_entities where id = :id"),
            {"id": CONCURRENT_ENTITY_ID},
        )
        active_branch_count = await connection.scalar(
            text(
                "select count(*) from branches "
                "where legal_entity_id = :id and status = 'active'"
            ),
            {"id": CONCURRENT_ENTITY_ID},
        )
    assert (entity_status, active_branch_count) in {("active", 1), ("inactive", 0)}


async def _assert_organization_write_serializes_with_tenant_lifecycle(
    engine: AsyncEngine,
) -> None:
    service = OrganizationService(
        session_factory=async_sessionmaker(engine, expire_on_commit=False),
        audit_recorder_factory=lambda _session: _NoopAuditRecorder(),
    )
    context = RequestContext(
        request_id="req-p3f-lifecycle-race",
        trace_id="abcdef1234567890abcdef1234567890",
        tenant=TenantContext(tenant_id=TENANT_A_ID, slug="p3f-tenant-a"),
        actor_id=uuid4(),
        authentication_strength=AuthenticationStrength.SINGLE_FACTOR,
    )
    connection = await engine.connect()
    transaction = await connection.begin()
    task = None
    try:
        await connection.execute(
            text("update tenants set status = 'suspended' where id = :tenant_id"),
            {"tenant_id": TENANT_A_ID},
        )
        task = asyncio.create_task(
            service.create_branch(
                request_context=context,
                payload=BranchCreate(
                    legal_entity_id=TENANT_A_ID,
                    code="LIFECYCLE-RACE",
                    name="Must not commit after suspension",
                    timezone="UTC",
                ),
                granted_permissions=(
                    ORGANIZATION_READ_PERMISSION,
                    ORGANIZATION_UPDATE_PERMISSION,
                ),
            )
        )
        with pytest.raises(TimeoutError):
            await asyncio.wait_for(asyncio.shield(task), timeout=0.25)
        await transaction.commit()
        with pytest.raises(TenantReadOnlyError):
            await task
    finally:
        if transaction.is_active:
            await transaction.rollback()
        if task is not None and not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        await connection.close()

    async with engine.begin() as restore_connection:
        await restore_connection.execute(
            text("update tenants set status = 'active' where id = :tenant_id"),
            {"tenant_id": TENANT_A_ID},
        )
        assert (
            await restore_connection.scalar(
                text("select count(*) from branches where code = 'LIFECYCLE-RACE'")
            )
            == 0
        )


async def _assert_immutable_code_and_no_delete_acl(engine: AsyncEngine) -> None:
    for statement, parameters in (
        (
            "update legal_entities set code = 'RENAMED' where id = :id",
            {"id": TENANT_A_ID},
        ),
        (
            "update branches set code = 'RENAMED' where id = :id",
            {"id": BRANCH_A_ID},
        ),
        (
            "delete from branches where id = :id",
            {"id": BRANCH_A_ID},
        ),
    ):
        with pytest.raises(DBAPIError) as privilege_error:
            async with engine.begin() as connection:
                await _set_local_tenant_role(connection, TENANT_A_ID)
                await connection.execute(text(statement), parameters)
        assert sqlstate_from_error(privilege_error.value) == "42501"


async def _assert_non_tenant_capabilities_cannot_read_organization(
    engine: AsyncEngine,
) -> None:
    for role_name in (PLATFORM_APPLICATION_ROLE, AUTHENTICATION_APPLICATION_ROLE):
        for table_name in SECURED_TABLES:
            with pytest.raises(DBAPIError) as privilege_error:
                async with engine.begin() as connection:
                    await _set_local_role(connection, role_name)
                    await connection.execute(text(f'select count(*) from "{table_name}"'))
            assert sqlstate_from_error(privilege_error.value) == "42501"


async def _assert_platform_cannot_insert_nondefault_legal_entity(
    engine: AsyncEngine,
) -> None:
    with pytest.raises(DBAPIError) as privilege_error:
        async with engine.begin() as connection:
            await _set_local_role(connection, PLATFORM_APPLICATION_ROLE)
            await connection.execute(
                text(
                    "insert into legal_entities ("
                    "id, tenant_id, code, name, registered_name, timezone, status, is_default"
                    ") values ("
                    ":id, :tenant_id, 'EXTRA', 'Platform extra', 'Platform extra', "
                    "'UTC', 'active', false)"
                ),
                {"id": uuid4(), "tenant_id": TENANT_A_ID},
            )
    assert sqlstate_from_error(privilege_error.value) == "42501"


async def _assert_platform_tenant_service_creates_default(engine: AsyncEngine) -> None:
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    payload = TenantPlatformCreate(
        slug=f"p3f-provisioned-{uuid4().hex[:16]}",
        name="P3F Provisioned Tenant",
        timezone="Europe/Amsterdam",
    )
    async with session_factory() as session:
        configure_platform_database_access(session)
        unit_of_work = SqlAlchemyUnitOfWork(session)

        async def create_tenant():
            return await TenantService(session).create_tenant(payload)

        tenant = await unit_of_work.execute(create_tenant)

    async with engine.begin() as connection:
        await _set_local_tenant_role(connection, tenant.id)
        rows = (
            await connection.execute(
                text(
                    "select id, tenant_id, code, name, registered_name, timezone, "
                    "status, is_default from legal_entities"
                )
            )
        ).all()
    assert rows == [
        (
            tenant.id,
            tenant.id,
            "DEFAULT",
            payload.name,
            payload.name,
            payload.timezone,
            "active",
            True,
        )
    ]


async def _direct_table_acl(
    connection: AsyncConnection,
) -> set[tuple[str, str, str, bool]]:
    rows = (
        await connection.execute(
            text(
                "select table_class.relname as table_name, "
                "coalesce(grantee.rolname, 'PUBLIC') as grantee, "
                "privilege.privilege_type, privilege.is_grantable "
                "from pg_catalog.pg_class table_class "
                "join pg_catalog.pg_namespace namespace "
                "on namespace.oid = table_class.relnamespace "
                "cross join lateral pg_catalog.aclexplode(table_class.relacl) privilege "
                "left join pg_catalog.pg_roles grantee on grantee.oid = privilege.grantee "
                "where namespace.nspname = 'public' "
                "and table_class.relname = any(:table_names) "
                "and (privilege.grantee = 0 or grantee.rolname = any(:role_names))"
            ),
            {
                "table_names": list(SECURED_TABLES),
                "role_names": list(CAPABILITY_ROLES),
            },
        )
    ).mappings()
    return {
        (
            row["table_name"],
            row["grantee"],
            row["privilege_type"],
            row["is_grantable"],
        )
        for row in rows
    }


async def _direct_update_column_acl(
    connection: AsyncConnection,
) -> set[tuple[str, str, str, bool]]:
    rows = (
        await connection.execute(
            text(
                "select table_class.relname as table_name, attribute.attname as column_name, "
                "coalesce(grantee.rolname, 'PUBLIC') as grantee, privilege.is_grantable "
                "from pg_catalog.pg_attribute attribute "
                "join pg_catalog.pg_class table_class on table_class.oid = attribute.attrelid "
                "join pg_catalog.pg_namespace namespace "
                "on namespace.oid = table_class.relnamespace "
                "cross join lateral pg_catalog.aclexplode(attribute.attacl) privilege "
                "left join pg_catalog.pg_roles grantee on grantee.oid = privilege.grantee "
                "where namespace.nspname = 'public' "
                "and table_class.relname = any(:table_names) "
                "and privilege.privilege_type = 'UPDATE' "
                "and (privilege.grantee = 0 or grantee.rolname = any(:role_names))"
            ),
            {
                "table_names": list(SECURED_TABLES),
                "role_names": list(CAPABILITY_ROLES),
            },
        )
    ).mappings()
    return {
        (
            row["table_name"],
            row["column_name"],
            row["grantee"],
            row["is_grantable"],
        )
        for row in rows
    }


async def _seed_pre_p3f_tenants(database_url: URL) -> None:
    engine = create_async_engine(database_url, poolclass=NullPool)
    try:
        async with engine.begin() as connection:
            await connection.execute(
                text(
                    "insert into tenants ("
                    "id, slug, name, status, plan_code, data_region, locale, timezone"
                    ") values "
                    "(:tenant_a, 'p3f-tenant-a', 'P3F Tenant A', 'active', "
                    "'core', 'tr-1', 'en-US', 'Europe/Istanbul'), "
                    "(:tenant_b, 'p3f-tenant-b', 'P3F Tenant B', 'active', "
                    "'core', 'eu-1', 'en-US', 'Europe/London')"
                ),
                {"tenant_a": TENANT_A_ID, "tenant_b": TENANT_B_ID},
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
