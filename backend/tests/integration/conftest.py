from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.engine import URL, make_url
from sqlalchemy.ext.asyncio import AsyncConnection, create_async_engine
from sqlalchemy.pool import NullPool

TEST_DATABASE_URL_ENV = "IK_TEST_DATABASE_URL"
_POSTGRES_MARKER = "postgres"
_TEMP_DATABASE_PREFIX = "ik_p0a_test_"


def pytest_collection_modifyitems(config: pytest.Config) -> None:
    marker_expression = config.getoption("markexpr").strip()
    if marker_expression == _POSTGRES_MARKER and not os.environ.get(TEST_DATABASE_URL_ENV):
        raise pytest.UsageError(
            "-m postgres requires IK_TEST_DATABASE_URL to point to a PostgreSQL admin DSN; "
            "the supplied database is never modified and is used only to create a temporary "
            "test database"
        )


@pytest.fixture(scope="session")
def postgres_database_url() -> Iterator[URL]:
    admin_url = _postgres_admin_url(os.environ[TEST_DATABASE_URL_ENV])
    database_name = f"{_TEMP_DATABASE_PREFIX}{uuid4().hex}"
    temporary_url = admin_url.set(database=database_name)

    asyncio.run(_create_database(admin_url, database_name))
    try:
        yield temporary_url
    finally:
        asyncio.run(_drop_database(admin_url, database_name))


def _postgres_admin_url(raw_url: str) -> URL:
    try:
        url = make_url(raw_url)
    except Exception as exc:
        raise pytest.UsageError(f"{TEST_DATABASE_URL_ENV} is not a valid SQLAlchemy URL") from exc

    if url.get_backend_name() != "postgresql":
        raise pytest.UsageError(f"{TEST_DATABASE_URL_ENV} must use PostgreSQL")
    if not url.database:
        raise pytest.UsageError(
            f"{TEST_DATABASE_URL_ENV} must name an existing admin database"
        )
    if url.drivername not in {"postgresql", "postgresql+asyncpg"}:
        raise pytest.UsageError(
            f"{TEST_DATABASE_URL_ENV} must use postgresql or postgresql+asyncpg"
        )
    return url.set(drivername="postgresql+asyncpg")


async def _create_database(admin_url: URL, database_name: str) -> None:
    async with _admin_connection(admin_url) as connection:
        await connection.exec_driver_sql(
            f"CREATE DATABASE {_quoted_database_name(connection, database_name)} TEMPLATE template0"
        )


async def _drop_database(admin_url: URL, database_name: str) -> None:
    async with _admin_connection(admin_url) as connection:
        await connection.execute(
            text(
                "select pg_terminate_backend(pid) "
                "from pg_stat_activity "
                "where datname = :database_name and pid <> pg_backend_pid()"
            ),
            {"database_name": database_name},
        )
        await connection.exec_driver_sql(
            f"DROP DATABASE IF EXISTS {_quoted_database_name(connection, database_name)}"
        )


@asynccontextmanager
async def _admin_connection(admin_url: URL) -> AsyncIterator[AsyncConnection]:
    engine = create_async_engine(
        admin_url,
        isolation_level="AUTOCOMMIT",
        poolclass=NullPool,
    )
    try:
        async with engine.connect() as connection:
            yield connection
    finally:
        await engine.dispose()


def _quoted_database_name(connection: AsyncConnection, database_name: str) -> str:
    return connection.dialect.identifier_preparer.quote(database_name)
