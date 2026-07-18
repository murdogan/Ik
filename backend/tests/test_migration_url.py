from __future__ import annotations

import pytest
from app.db.migration_url import resolve_migration_database_url


def test_deployed_migration_uses_runtime_database_url() -> None:
    runtime_url = "postgresql+asyncpg://runtime:secret@database:5432/ik_staging"

    assert (
        resolve_migration_database_url(
            configured_url="postgresql+asyncpg://local:local@localhost:5432/ik",
            environment="staging",
            runtime_url=runtime_url,
        )
        == runtime_url
    )


@pytest.mark.parametrize("environment", ["staging", "prod"])
def test_deployed_migration_requires_runtime_database_url(environment: str) -> None:
    with pytest.raises(RuntimeError, match="required"):
        resolve_migration_database_url(
            configured_url="postgresql+asyncpg://local:local@localhost:5432/ik",
            environment=environment,
            runtime_url=None,
        )


def test_deployed_migration_rejects_non_async_postgresql_url() -> None:
    with pytest.raises(RuntimeError, match="asyncpg"):
        resolve_migration_database_url(
            configured_url="postgresql+asyncpg://local:local@localhost:5432/ik",
            environment="staging",
            runtime_url="sqlite+aiosqlite:///:memory:",
        )


def test_local_migration_retains_configured_url_fallback() -> None:
    configured_url = "sqlite+aiosqlite:///:memory:"

    assert (
        resolve_migration_database_url(
            configured_url=configured_url,
            environment="local",
            runtime_url=None,
        )
        == configured_url
    )
