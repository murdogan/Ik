from __future__ import annotations

from sqlalchemy.engine import make_url

_DEPLOYED_ENVIRONMENTS = frozenset({"staging", "prod"})


def resolve_migration_database_url(
    *,
    configured_url: str,
    environment: str | None,
    runtime_url: str | None,
) -> str:
    normalized_environment = (environment or "local").strip().casefold()
    candidate = runtime_url.strip() if runtime_url is not None else ""
    if not candidate:
        if normalized_environment in _DEPLOYED_ENVIRONMENTS:
            raise RuntimeError("Migration database URL is required in deployed environments")
        candidate = configured_url

    parsed = make_url(candidate)
    if normalized_environment in _DEPLOYED_ENVIRONMENTS and (
        parsed.get_backend_name() != "postgresql" or parsed.drivername != "postgresql+asyncpg"
    ):
        raise RuntimeError("Deployed migrations require PostgreSQL with the asyncpg driver")
    return candidate


__all__ = ["resolve_migration_database_url"]
