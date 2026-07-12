"""Database-backed, PII-free fixed-window limits for public tenant login."""

from __future__ import annotations

import hmac
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from hashlib import sha256

from sqlalchemy import case
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.auth import AuthenticationRateLimitBucket
from app.platform.db import configure_authentication_database_access
from app.platform.errors.application import ApplicationError


class AuthenticationRateLimitExceededError(ApplicationError):
    def __init__(self, retry_after_seconds: int) -> None:
        super().__init__("Authentication rate limit exceeded")
        self.retry_after_seconds = max(1, retry_after_seconds)


class AuthenticationRateLimitKeyHasher:
    """Key login identifiers without storing reversible email or network values."""

    __slots__ = ("_key",)

    def __init__(self, key: bytes) -> None:
        if len(key) < 32:
            raise ValueError("Authentication rate-limit keys require at least 32 bytes")
        self._key = key

    def source_bucket(self, source_address: str) -> str:
        return self._digest("login-source", source_address)

    def identity_bucket(self, normalized_email: str) -> str:
        return self._digest("login-identity", normalized_email)

    def _digest(self, purpose: str, *parts: str) -> str:
        material = "\0".join((purpose, *parts)).encode("utf-8")
        return hmac.new(self._key, material, sha256).hexdigest()


@dataclass(frozen=True, slots=True)
class AuthenticationRateLimitPolicy:
    window: timedelta
    source_attempts: int
    identity_attempts: int

    def __post_init__(self) -> None:
        if self.window <= timedelta(0):
            raise ValueError("Authentication rate-limit window must be positive")
        if self.source_attempts < 1 or self.identity_attempts < 1:
            raise ValueError("Authentication rate-limit attempt counts must be positive")


class AuthenticationRateLimitService:
    def __init__(
        self,
        *,
        session_factory: async_sessionmaker[AsyncSession],
        key_hasher: AuthenticationRateLimitKeyHasher,
        policy: AuthenticationRateLimitPolicy,
    ) -> None:
        self._session_factory = session_factory
        self._key_hasher = key_hasher
        self._policy = policy

    async def consume_login_attempt(
        self,
        *,
        source_address: str,
        normalized_email: str,
    ) -> None:
        now = datetime.now(UTC)
        expires_at = now + self._policy.window
        buckets = (
            (
                self._key_hasher.source_bucket(source_address),
                "login_source",
                self._policy.source_attempts,
            ),
            (
                self._key_hasher.identity_bucket(normalized_email),
                "login_identity",
                self._policy.identity_attempts,
            ),
        )
        exceeded_until: datetime | None = None
        async with self._session_factory() as session:
            configure_authentication_database_access(session)
            async with session.begin():
                for bucket_key, scope, maximum in buckets:
                    attempt_count, bucket_expiry = await _increment_bucket(
                        session,
                        bucket_key=bucket_key,
                        scope=scope,
                        now=now,
                        expires_at=expires_at,
                    )
                    if attempt_count > maximum:
                        if exceeded_until is None or bucket_expiry > exceeded_until:
                            exceeded_until = bucket_expiry

        if exceeded_until is not None:
            retry_after = max(1, int((exceeded_until - now).total_seconds()))
            raise AuthenticationRateLimitExceededError(retry_after)


async def _increment_bucket(
    session: AsyncSession,
    *,
    bucket_key: str,
    scope: str,
    now: datetime,
    expires_at: datetime,
) -> tuple[int, datetime]:
    table = AuthenticationRateLimitBucket.__table__
    dialect_name = session.get_bind().dialect.name
    insert_factory = (
        postgresql_insert if dialect_name == "postgresql" else sqlite_insert
    )
    statement = insert_factory(table).values(
        bucket_key_hash=bucket_key,
        scope=scope,
        window_started_at=now,
        expires_at=expires_at,
        attempt_count=1,
        updated_at=now,
    )
    reset_window = table.c.expires_at <= now
    statement = statement.on_conflict_do_update(
        index_elements=(table.c.bucket_key_hash,),
        set_={
            "scope": scope,
            "window_started_at": case(
                (reset_window, now),
                else_=table.c.window_started_at,
            ),
            "expires_at": case(
                (reset_window, expires_at),
                else_=table.c.expires_at,
            ),
            "attempt_count": case(
                (reset_window, 1),
                else_=table.c.attempt_count + 1,
            ),
            "updated_at": now,
        },
    ).returning(table.c.attempt_count, table.c.expires_at)
    row = (await session.execute(statement)).one()
    bucket_expiry = row.expires_at
    if bucket_expiry.tzinfo is None or bucket_expiry.utcoffset() is None:
        bucket_expiry = bucket_expiry.replace(tzinfo=UTC)
    return int(row.attempt_count), bucket_expiry.astimezone(UTC)


__all__ = [
    "AuthenticationRateLimitExceededError",
    "AuthenticationRateLimitKeyHasher",
    "AuthenticationRateLimitPolicy",
    "AuthenticationRateLimitService",
]
