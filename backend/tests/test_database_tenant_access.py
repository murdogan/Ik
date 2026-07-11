from collections.abc import AsyncIterator
from uuid import UUID

import pytest
from app.platform.db import (
    DatabaseAccessContext,
    DatabaseAccessPath,
    attach_database_access_resolver,
    configure_platform_database_access,
    configure_tenant_database_access,
    database_access_context,
)
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

TENANT_ID = UUID("11111111-aaaa-4111-8111-111111111111")
OTHER_TENANT_ID = UUID("22222222-bbbb-4222-8222-222222222222")


@pytest.fixture
async def sqlite_session() -> AsyncIterator[AsyncSession]:
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    try:
        async with async_sessionmaker(engine, expire_on_commit=False)() as session:
            yield session
    finally:
        await engine.dispose()


def test_database_access_context_rejects_missing_invalid_or_mixed_tenant_scope() -> None:
    with pytest.raises(ValueError, match="non-zero UUID"):
        DatabaseAccessContext(path=DatabaseAccessPath.TENANT)
    with pytest.raises(ValueError, match="non-zero UUID"):
        DatabaseAccessContext(path=DatabaseAccessPath.TENANT, tenant_id=UUID(int=0))
    with pytest.raises(ValueError, match="cannot carry"):
        DatabaseAccessContext(
            path=DatabaseAccessPath.PLATFORM,
            tenant_id=TENANT_ID,
        )
    with pytest.raises(TypeError, match="DatabaseAccessPath"):
        DatabaseAccessContext(path="tenant", tenant_id=TENANT_ID)  # type: ignore[arg-type]


async def test_tenant_database_access_is_immutable_for_session_lifetime(
    sqlite_session: AsyncSession,
) -> None:
    configure_tenant_database_access(sqlite_session, TENANT_ID)
    configure_tenant_database_access(sqlite_session, TENANT_ID)

    assert database_access_context(sqlite_session) == DatabaseAccessContext(
        path=DatabaseAccessPath.TENANT,
        tenant_id=TENANT_ID,
    )

    with pytest.raises(RuntimeError, match="immutable"):
        configure_tenant_database_access(sqlite_session, OTHER_TENANT_ID)
    with pytest.raises(RuntimeError, match="immutable"):
        configure_platform_database_access(sqlite_session)


async def test_platform_database_access_has_no_tenant_identity(
    sqlite_session: AsyncSession,
) -> None:
    configure_platform_database_access(sqlite_session)

    assert database_access_context(sqlite_session) == DatabaseAccessContext(
        path=DatabaseAccessPath.PLATFORM,
    )


async def test_request_access_resolves_lazily_then_remains_immutable(
    sqlite_session: AsyncSession,
) -> None:
    selected: DatabaseAccessContext | None = None
    attach_database_access_resolver(sqlite_session, lambda: selected)

    assert database_access_context(sqlite_session) is None

    selected = DatabaseAccessContext(
        path=DatabaseAccessPath.TENANT,
        tenant_id=TENANT_ID,
    )
    assert database_access_context(sqlite_session) == selected

    selected = DatabaseAccessContext(path=DatabaseAccessPath.PLATFORM)
    assert database_access_context(sqlite_session).path is DatabaseAccessPath.TENANT
