# ruff: noqa: E402

from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.parse import quote
from uuid import uuid4

from sqlalchemy import select, update
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError, SQLAlchemyError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = ROOT / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.core.config import get_settings
from app.models.auth import (
    OrganizationSelectionTransaction,
    PasswordResetToken,
    PlatformRefreshSessionFamily,
    RefreshSessionFamily,
    UserActivationToken,
)
from app.models.identity import Identity, IdentityStatus, TenantMembership
from app.models.user import User, UserStatus
from app.platform.identity import issue_activation_token
from app.services.demo_seed_service import (
    DEMO_USERS,
    DemoSeedConflictError,
    DemoSeedResult,
    seed_demo_data,
)

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
        result, activation_url = asyncio.run(
            _run_seed(
                database_url,
                auth_demo=args.auth_demo,
                frontend_base_url=settings.frontend_base_url,
                activation_ttl_hours=settings.auth_activation_token_ttl_hours,
            )
        )
    except DemoSeedConflictError as exc:
        print(f"DEMO_SEED_CONFLICT {exc}", file=sys.stderr)
        return 1
    except SQLAlchemyError as exc:
        print(f"DEMO_SEED_FAILED {exc.__class__.__name__}: {exc}", file=sys.stderr)
        return 1

    print(_format_success(result))
    if activation_url is not None:
        print(f"DEMO_AUTH_ACTIVATION_URL {activation_url}")
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
    parser.add_argument(
        "--auth-demo",
        action="store_true",
        help=(
            "Reset the local Wealthy Falcon demo admin to invited and print one single-use "
            "activation URL. Never enabled implicitly."
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


async def _run_seed(
    database_url: str,
    *,
    auth_demo: bool = False,
    frontend_base_url: str = "http://localhost:3000",
    activation_ttl_hours: int = 48,
) -> tuple[DemoSeedResult, str | None]:
    engine = create_async_engine(database_url, pool_pre_ping=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with session_factory.begin() as session:
            result = await seed_demo_data(session)
            activation_url = None
            if auth_demo:
                activation_url = await _reset_demo_admin_activation(
                    session,
                    frontend_base_url=frontend_base_url,
                    activation_ttl_hours=activation_ttl_hours,
                )
            return result, activation_url
    finally:
        await engine.dispose()


async def _reset_demo_admin_activation(
    session,
    *,
    frontend_base_url: str,
    activation_ttl_hours: int,
) -> str:
    demo_admin_id = next(fixture.id for fixture in DEMO_USERS if fixture.key == "wf_admin")
    user = await session.get(User, demo_admin_id)
    if user is None:  # pragma: no cover - seed invariant
        raise DemoSeedConflictError("Wealthy Falcon demo admin was not seeded")

    now = datetime.now(UTC)
    token = issue_activation_token(user.tenant_id)
    user.status = UserStatus.INVITED.value
    user.password_hash = None
    user.can_invite_users = True
    identity = await session.scalar(
        select(Identity).where(Identity.email_normalized == user.email_normalized)
    )
    if identity is None:  # pragma: no cover - canonical demo seed invariant
        raise DemoSeedConflictError("Wealthy Falcon demo identity was not seeded")
    identity.status = IdentityStatus.PENDING.value
    identity.password_hash = None
    membership_ids = select(TenantMembership.id).where(
        TenantMembership.identity_id == identity.id
    )
    legacy_user_ids = select(TenantMembership.legacy_user_id).where(
        TenantMembership.identity_id == identity.id
    )
    await session.execute(
        update(User)
        .where(User.id.in_(legacy_user_ids))
        .values(password_hash=None)
    )
    await session.execute(
        update(RefreshSessionFamily)
        .where(
            RefreshSessionFamily.membership_id.in_(membership_ids),
            RefreshSessionFamily.revoked_at.is_(None),
        )
        .values(revoked_at=now)
    )
    await session.execute(
        update(PlatformRefreshSessionFamily)
        .where(
            PlatformRefreshSessionFamily.identity_id == identity.id,
            PlatformRefreshSessionFamily.revoked_at.is_(None),
        )
        .values(revoked_at=now)
    )
    await session.execute(
        update(OrganizationSelectionTransaction)
        .where(
            OrganizationSelectionTransaction.identity_id == identity.id,
            OrganizationSelectionTransaction.consumed_at.is_(None),
        )
        .values(consumed_at=now)
    )
    await session.execute(
        update(PasswordResetToken)
        .where(
            PasswordResetToken.identity_id == identity.id,
            PasswordResetToken.consumed_at.is_(None),
            PasswordResetToken.revoked_at.is_(None),
        )
        .values(revoked_at=now)
    )
    await session.execute(
        update(UserActivationToken)
        .where(
            UserActivationToken.tenant_id == user.tenant_id,
            UserActivationToken.user_id == user.id,
            UserActivationToken.consumed_at.is_(None),
            UserActivationToken.revoked_at.is_(None),
        )
        .values(revoked_at=now)
    )
    session.add(
        UserActivationToken(
            id=uuid4(),
            tenant_id=user.tenant_id,
            user_id=user.id,
            token_hash=token.token_hash,
            expires_at=now + timedelta(hours=activation_ttl_hours),
        )
    )
    safe_token = quote(token.raw_token, safe=".-_")
    return f"{frontend_base_url.rstrip('/')}/activate#token={safe_token}"


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
