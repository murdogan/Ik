from typing import Annotated
from unittest.mock import AsyncMock, Mock

from app.core.config import Settings
from app.db.session import (
    DATABASE_RUNTIME_STATE_KEY,
    build_engine_options,
    create_database_runtime,
    get_session,
)
from app.main import create_app
from fastapi import Depends, HTTPException
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.pool import StaticPool


def _settings(**overrides: object) -> Settings:
    return Settings(_env_file=None, **overrides)


def test_database_runtime_settings_are_environment_driven(monkeypatch) -> None:
    monkeypatch.setenv("IK_DATABASE_POOL_SIZE", "7")
    monkeypatch.setenv("IK_DATABASE_MAX_OVERFLOW", "11")
    monkeypatch.setenv("IK_DATABASE_POOL_TIMEOUT_SECONDS", "4.5")
    monkeypatch.setenv("IK_DATABASE_POOL_RECYCLE_SECONDS", "900")
    monkeypatch.setenv("IK_DATABASE_CONNECT_TIMEOUT_SECONDS", "2.5")
    monkeypatch.setenv("IK_DATABASE_STATEMENT_TIMEOUT_MS", "1250")
    monkeypatch.setenv("IK_DATABASE_IDLE_TRANSACTION_TIMEOUT_MS", "2500")

    settings = _settings()

    assert settings.database_pool_size == 7
    assert settings.database_max_overflow == 11
    assert settings.database_pool_timeout_seconds == 4.5
    assert settings.database_pool_recycle_seconds == 900
    assert settings.database_connect_timeout_seconds == 2.5
    assert settings.database_statement_timeout_ms == 1250
    assert settings.database_idle_transaction_timeout_ms == 2500


def test_postgresql_engine_options_include_pool_and_server_timeouts() -> None:
    settings = _settings(
        database_url="postgresql+asyncpg://ik:ik@localhost:5432/ik",
        database_pool_size=3,
        database_max_overflow=4,
        database_pool_timeout_seconds=5.5,
        database_pool_recycle_seconds=600,
        database_connect_timeout_seconds=1.5,
        database_statement_timeout_ms=1200,
        database_idle_transaction_timeout_ms=2400,
    )

    options = build_engine_options(settings)

    assert options == {
        "pool_pre_ping": True,
        "pool_size": 3,
        "max_overflow": 4,
        "pool_timeout": 5.5,
        "pool_recycle": 600,
        "connect_args": {
            "timeout": 1.5,
            "server_settings": {
                "statement_timeout": "1200",
                "idle_in_transaction_session_timeout": "2400",
            },
        },
    }


def test_in_memory_sqlite_engine_options_have_safe_test_defaults() -> None:
    settings = _settings(database_url="sqlite+aiosqlite:///:memory:")

    options = build_engine_options(settings)

    assert options == {
        "pool_pre_ping": True,
        "connect_args": {"check_same_thread": False},
        "poolclass": StaticPool,
        "use_insertmanyvalues": False,
    }


async def test_app_lifespan_owns_runtime_and_disposes_it_once(monkeypatch) -> None:
    runtime = Mock()
    runtime.dispose = AsyncMock()
    runtime_factory = Mock(return_value=runtime)
    settings = _settings(database_url="sqlite+aiosqlite:///:memory:")
    monkeypatch.setattr("app.main.get_settings", lambda: settings)
    monkeypatch.setattr("app.main.create_database_runtime", runtime_factory)

    application = create_app()

    assert not hasattr(application.state, DATABASE_RUNTIME_STATE_KEY)
    async with application.router.lifespan_context(application):
        assert getattr(application.state, DATABASE_RUNTIME_STATE_KEY) is runtime
        runtime.dispose.assert_not_awaited()

    runtime_factory.assert_called_once_with(settings)
    runtime.dispose.assert_awaited_once_with()
    assert not hasattr(application.state, DATABASE_RUNTIME_STATE_KEY)


async def test_session_dependency_rolls_back_after_endpoint_error(monkeypatch) -> None:
    settings = _settings(database_url="sqlite+aiosqlite:///:memory:")
    monkeypatch.setattr("app.main.get_settings", lambda: settings)
    application = create_app()

    @application.post("/_test/rollback")
    async def rollback_route(
        session: Annotated[AsyncSession, Depends(get_session)],
    ) -> None:
        await session.execute(text("insert into p0a_runtime_probe (value) values ('pending')"))
        raise HTTPException(status_code=409, detail="expected test error")

    async with application.router.lifespan_context(application):
        runtime = getattr(application.state, DATABASE_RUNTIME_STATE_KEY)
        async with runtime.engine.begin() as connection:
            await connection.execute(
                text("create table p0a_runtime_probe (value varchar(32) not null)")
            )

        async with AsyncClient(
            transport=ASGITransport(app=application),
            base_url="http://testserver",
        ) as client:
            response = await client.post("/_test/rollback")

        assert response.status_code == 409
        async with runtime.session_factory() as verification_session:
            row_count = await verification_session.scalar(
                text("select count(*) from p0a_runtime_probe")
            )
        assert row_count == 0


async def test_database_runtime_can_be_disposed_more_than_once_safely() -> None:
    runtime = create_database_runtime(
        _settings(database_url="sqlite+aiosqlite:///:memory:")
    )

    await runtime.dispose()
    await runtime.dispose()
