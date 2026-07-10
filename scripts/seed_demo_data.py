# ruff: noqa: E402

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError, SQLAlchemyError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = ROOT / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.core.config import get_settings
from app.services.demo_seed_service import DemoSeedConflictError, DemoSeedResult, seed_demo_data

LOCAL_DEMO_ENVIRONMENTS = {"local", "dev"}
LOCAL_DATABASE_HOSTS = {"", "localhost", "127.0.0.1", "::1"}


def main() -> int:
    args = _parse_args()
    settings = get_settings()
    if settings.environment not in LOCAL_DEMO_ENVIRONMENTS:
        print(
            "DEMO_SEED_REFUSED "
            f"environment={settings.environment!r} "
            "allowed_environments=local,dev",
            file=sys.stderr,
        )
        return 2

    database_url = args.database_url or settings.database_url
    try:
        _ensure_local_database_url(database_url)
    except ValueError as exc:
        print(f"DEMO_SEED_REFUSED {exc}", file=sys.stderr)
        return 2

    try:
        result = asyncio.run(_run_seed(database_url))
    except DemoSeedConflictError as exc:
        print(f"DEMO_SEED_CONFLICT {exc}", file=sys.stderr)
        return 1
    except SQLAlchemyError as exc:
        print(f"DEMO_SEED_FAILED {exc.__class__.__name__}: {exc}", file=sys.stderr)
        return 1

    print(_format_success(result))
    return 0


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Seed local Wealthy Falcon HR demo tenants, users, employees, and leaves.",
    )
    parser.add_argument(
        "--database-url",
        help=(
            "Optional local database URL override. Defaults to IK_DATABASE_URL/settings. "
            "The target schema must already be migrated."
        ),
    )
    return parser.parse_args()


def _ensure_local_database_url(database_url: str) -> None:
    try:
        url = make_url(database_url)
    except ArgumentError as exc:
        raise ValueError("database_url_invalid") from exc

    if url.drivername.startswith("sqlite"):
        return

    host = (url.host or "").lower()
    if host in LOCAL_DATABASE_HOSTS:
        return

    allowed_hosts = ",".join(sorted(LOCAL_DATABASE_HOSTS - {""}))
    raise ValueError(f"database_url_not_local host={host!r} allowed_hosts={allowed_hosts}")


async def _run_seed(database_url: str) -> DemoSeedResult:
    engine = create_async_engine(database_url, pool_pre_ping=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with session_factory.begin() as session:
            return await seed_demo_data(session)
    finally:
        await engine.dispose()


def _format_success(result: DemoSeedResult) -> str:
    tenant_ids = ",".join(str(tenant_id) for tenant_id in result.tenant_ids)
    return (
        "DEMO_SEED_OK "
        f"tenants={result.tenants} "
        f"users={result.users} "
        f"employees={result.employees} "
        f"leave_requests={result.leave_requests} "
        f"tenant_ids={tenant_ids}"
    )


if __name__ == "__main__":
    raise SystemExit(main())
