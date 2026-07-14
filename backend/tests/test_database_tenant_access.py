from collections.abc import AsyncIterator
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import UUID

import pytest
from app.platform.db import (
    DatabaseAccessContext,
    DatabaseAccessPath,
    DatabaseCommandContext,
    DatabaseCommandIntent,
    attach_database_access_resolver,
    clear_database_command_context,
    configure_authentication_database_access,
    configure_database_command_context,
    configure_platform_database_access,
    configure_tenant_database_access,
    database_access_context,
    database_command_context,
)
from app.platform.db.tenant_access import _bind_transaction_database_access
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

TENANT_ID = UUID("11111111-aaaa-4111-8111-111111111111")
OTHER_TENANT_ID = UUID("22222222-bbbb-4222-8222-222222222222")
ACTOR_ID = UUID("33333333-cccc-4333-8333-333333333333")
MEMBERSHIP_ID = UUID("44444444-dddd-4444-8444-444444444444")
TARGET_ID = UUID("55555555-eeee-4555-8555-555555555555")
AUDIT_EVENT_ID = UUID("66666666-ffff-4666-8666-666666666666")
SESSION_ID = UUID("77777777-aaaa-4777-8777-777777777777")


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
    with pytest.raises(ValueError, match="together"):
        DatabaseAccessContext(
            path=DatabaseAccessPath.TENANT,
            tenant_id=TENANT_ID,
            actor_id=ACTOR_ID,
        )
    with pytest.raises(ValueError, match="non-zero UUID"):
        DatabaseAccessContext(
            path=DatabaseAccessPath.TENANT,
            tenant_id=TENANT_ID,
            actor_id=UUID(int=0),
            membership_id=MEMBERSHIP_ID,
        )
    with pytest.raises(ValueError, match="cannot carry"):
        DatabaseAccessContext(
            path=DatabaseAccessPath.AUTHENTICATION,
            actor_id=ACTOR_ID,
            membership_id=MEMBERSHIP_ID,
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


async def test_tenant_database_access_carries_immutable_actor_context(
    sqlite_session: AsyncSession,
) -> None:
    configure_tenant_database_access(
        sqlite_session,
        TENANT_ID,
        actor_id=ACTOR_ID,
        membership_id=MEMBERSHIP_ID,
    )

    assert database_access_context(sqlite_session) == DatabaseAccessContext(
        path=DatabaseAccessPath.TENANT,
        tenant_id=TENANT_ID,
        actor_id=ACTOR_ID,
        membership_id=MEMBERSHIP_ID,
    )
    with pytest.raises(RuntimeError, match="immutable"):
        configure_tenant_database_access(sqlite_session, TENANT_ID)


def test_database_command_context_is_closed_and_validated() -> None:
    context = _database_command_context()

    assert context.intent is DatabaseCommandIntent.P4E_APPROVE
    with pytest.raises(TypeError, match="DatabaseCommandIntent"):
        DatabaseCommandContext(
            **{
                **_database_command_context_values(),
                "intent": "p4e_approve",
            }
        )
    with pytest.raises(ValueError, match="target_id"):
        DatabaseCommandContext(
            **{
                **_database_command_context_values(),
                "target_id": UUID(int=0),
            }
        )
    with pytest.raises(ValueError, match="correlation_request_id"):
        DatabaseCommandContext(
            **{
                **_database_command_context_values(),
                "correlation_request_id": "unsafe request",
            }
        )
    with pytest.raises(ValueError, match="trace_id"):
        DatabaseCommandContext(
            **{
                **_database_command_context_values(),
                "trace_id": "0" * 32,
            }
        )


async def test_database_command_context_matches_access_and_clears_between_uows(
    sqlite_session: AsyncSession,
) -> None:
    configure_tenant_database_access(
        sqlite_session,
        TENANT_ID,
        actor_id=ACTOR_ID,
        membership_id=MEMBERSHIP_ID,
    )
    context = _database_command_context()

    configure_database_command_context(sqlite_session, context)
    configure_database_command_context(sqlite_session, context)
    assert database_command_context(sqlite_session) == context

    with pytest.raises(RuntimeError, match="immutable"):
        configure_database_command_context(
            sqlite_session,
            DatabaseCommandContext(
                **{
                    **_database_command_context_values(),
                    "target_id": OTHER_TENANT_ID,
                }
            ),
        )

    clear_database_command_context(sqlite_session)
    assert database_command_context(sqlite_session) is None


async def test_database_command_context_rejects_missing_or_mismatched_access(
    sqlite_session: AsyncSession,
) -> None:
    with pytest.raises(RuntimeError, match="requires tenant"):
        configure_database_command_context(sqlite_session, _database_command_context())

    configure_tenant_database_access(
        sqlite_session,
        TENANT_ID,
        actor_id=ACTOR_ID,
        membership_id=MEMBERSHIP_ID,
    )
    with pytest.raises(RuntimeError, match="does not match"):
        configure_database_command_context(
            sqlite_session,
            DatabaseCommandContext(
                **{
                    **_database_command_context_values(),
                    "actor_user_id": OTHER_TENANT_ID,
                }
            ),
        )


async def test_root_transaction_binds_command_before_role_and_nested_does_not_rebind(
    sqlite_session: AsyncSession,
) -> None:
    configure_tenant_database_access(
        sqlite_session,
        TENANT_ID,
        actor_id=ACTOR_ID,
        membership_id=MEMBERSHIP_ID,
    )
    configure_database_command_context(sqlite_session, _database_command_context())
    connection = Mock()
    connection.dialect = SimpleNamespace(
        name="postgresql",
        identifier_preparer=SimpleNamespace(quote=lambda role: role),
    )

    _bind_transaction_database_access(
        sqlite_session.sync_session,
        SimpleNamespace(parent=None),
        connection,
    )

    assert connection.mock_calls[0][0] == "execute"
    parameters = connection.execute.call_args.args[1]
    assert parameters == {
        "tenant_id": TENANT_ID,
        "actor_user_id": ACTOR_ID,
        "membership_id": MEMBERSHIP_ID,
        "intent": "p4e_approve",
        "target_id": TARGET_ID,
        "audit_event_id": AUDIT_EVENT_ID,
        "correlation_request_id": "req-p4e-command",
        "trace_id": "1234567890abcdef1234567890abcdef",
        "session_id": SESSION_ID,
    }
    assert connection.exec_driver_sql.call_args_list[0].args == (
        "SET LOCAL ROLE wealthy_falcon_app",
    )

    connection.reset_mock()
    _bind_transaction_database_access(
        sqlite_session.sync_session,
        SimpleNamespace(parent=object()),
        connection,
    )
    connection.execute.assert_not_called()
    connection.exec_driver_sql.assert_any_call("SET LOCAL ROLE wealthy_falcon_app")


async def test_authentication_database_access_is_global_but_not_platform(
    sqlite_session: AsyncSession,
) -> None:
    configure_authentication_database_access(sqlite_session)

    assert database_access_context(sqlite_session) == DatabaseAccessContext(
        path=DatabaseAccessPath.AUTHENTICATION,
    )
    with pytest.raises(RuntimeError, match="immutable"):
        configure_platform_database_access(sqlite_session)


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


def _database_command_context() -> DatabaseCommandContext:
    return DatabaseCommandContext(**_database_command_context_values())


def _database_command_context_values() -> dict[str, object]:
    return {
        "tenant_id": TENANT_ID,
        "actor_user_id": ACTOR_ID,
        "membership_id": MEMBERSHIP_ID,
        "intent": DatabaseCommandIntent.P4E_APPROVE,
        "target_id": TARGET_ID,
        "audit_event_id": AUDIT_EVENT_ID,
        "correlation_request_id": "req-p4e-command",
        "trace_id": "1234567890abcdef1234567890abcdef",
        "session_id": SESSION_ID,
    }
