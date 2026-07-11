from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

from fastapi import Request
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool

from app.core.config import Settings
from app.platform.db.tenant_access import (
    DATABASE_ACCESS_CONTEXT_STATE_KEY,
    MANAGED_DATABASE_SESSION_KEY,
    DatabaseAccessContext,
    attach_database_access_resolver,
)

DATABASE_RUNTIME_STATE_KEY = "database_runtime"


@dataclass(slots=True)
class DatabaseRuntime:
    engine: AsyncEngine
    session_factory: async_sessionmaker[AsyncSession]

    async def dispose(self) -> None:
        await self.engine.dispose()


def build_engine_options(settings: Settings) -> dict[str, Any]:
    database_url = make_url(settings.database_url)
    options: dict[str, Any] = {"pool_pre_ping": True}

    if database_url.get_backend_name() == "postgresql":
        if database_url.drivername != "postgresql+asyncpg":
            raise ValueError("PostgreSQL database URLs must use the asyncpg driver")
        options.update(
            pool_size=settings.database_pool_size,
            max_overflow=settings.database_max_overflow,
            pool_timeout=settings.database_pool_timeout_seconds,
            pool_recycle=settings.database_pool_recycle_seconds,
            connect_args={
                "timeout": settings.database_connect_timeout_seconds,
                "server_settings": {
                    "statement_timeout": str(settings.database_statement_timeout_ms),
                    "idle_in_transaction_session_timeout": str(
                        settings.database_idle_transaction_timeout_ms
                    ),
                },
            },
        )
    elif database_url.get_backend_name() == "sqlite" and database_url.database in {
        None,
        "",
        ":memory:",
    }:
        options.update(
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
            use_insertmanyvalues=False,
        )

    return options


def create_database_runtime(settings: Settings) -> DatabaseRuntime:
    engine = create_async_engine(
        settings.database_url,
        **build_engine_options(settings),
    )
    return DatabaseRuntime(
        engine=engine,
        session_factory=async_sessionmaker(
            engine,
            expire_on_commit=False,
            info={MANAGED_DATABASE_SESSION_KEY: True},
        ),
    )


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    runtime = getattr(request.app.state, DATABASE_RUNTIME_STATE_KEY, None)
    if runtime is None:
        raise RuntimeError("Database runtime is unavailable outside the application lifespan")

    async with runtime.session_factory() as session:
        def resolve_request_database_access() -> DatabaseAccessContext | None:
            context = getattr(
                request.state,
                DATABASE_ACCESS_CONTEXT_STATE_KEY,
                None,
            )
            if context is not None and not isinstance(context, DatabaseAccessContext):
                raise RuntimeError("Request database access context is corrupt")
            return context

        attach_database_access_resolver(session, resolve_request_database_access)
        yield session
