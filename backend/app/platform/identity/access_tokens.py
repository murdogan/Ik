"""Short-lived signed access credentials for the F2A login slice."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import jwt

ACCESS_TOKEN_ISSUER = "wealthy-falcon-hr"
ACCESS_TOKEN_AUDIENCE = "wealthy-falcon-api"


class InvalidAccessTokenError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class AccessPrincipal:
    user_id: UUID
    tenant_id: UUID
    tenant_slug: str


@dataclass(frozen=True, slots=True)
class IssuedAccessToken:
    token: str
    expires_at: datetime


class AccessTokenCodec:
    def __init__(self, signing_key: bytes, *, ttl: timedelta) -> None:
        if len(signing_key) < 32:
            raise ValueError("Auth signing keys must contain at least 32 bytes")
        if ttl <= timedelta(0):
            raise ValueError("Access token TTL must be positive")
        self._signing_key = signing_key
        self._ttl = ttl

    @property
    def expires_in_seconds(self) -> int:
        return int(self._ttl.total_seconds())

    def issue(self, principal: AccessPrincipal) -> IssuedAccessToken:
        now = datetime.now(UTC)
        expires_at = now + self._ttl
        token = jwt.encode(
            {
                "iss": ACCESS_TOKEN_ISSUER,
                "aud": ACCESS_TOKEN_AUDIENCE,
                "typ": "access",
                "sub": str(principal.user_id),
                "tenant_id": str(principal.tenant_id),
                "tenant_slug": principal.tenant_slug,
                "jti": str(uuid4()),
                "iat": now,
                "exp": expires_at,
            },
            self._signing_key,
            algorithm="HS256",
        )
        return IssuedAccessToken(token=token, expires_at=expires_at)

    def decode(self, token: str) -> AccessPrincipal:
        if not isinstance(token, str) or not token or len(token) > 4096:
            raise InvalidAccessTokenError("Access token is invalid")
        try:
            claims = jwt.decode(
                token,
                self._signing_key,
                algorithms=["HS256"],
                audience=ACCESS_TOKEN_AUDIENCE,
                issuer=ACCESS_TOKEN_ISSUER,
                options={
                    "require": [
                        "iss",
                        "aud",
                        "typ",
                        "sub",
                        "tenant_id",
                        "tenant_slug",
                        "jti",
                        "iat",
                        "exp",
                    ]
                },
            )
            if claims["typ"] != "access":
                raise InvalidAccessTokenError("Access token is invalid")
            user_id = _canonical_uuid(claims["sub"])
            tenant_id = _canonical_uuid(claims["tenant_id"])
            tenant_slug = claims["tenant_slug"]
            if not isinstance(tenant_slug, str) or not tenant_slug.strip():
                raise InvalidAccessTokenError("Access token is invalid")
        except (jwt.PyJWTError, KeyError, TypeError, InvalidAccessTokenError) as exc:
            raise InvalidAccessTokenError("Access token is invalid") from exc
        return AccessPrincipal(
            user_id=user_id,
            tenant_id=tenant_id,
            tenant_slug=tenant_slug,
        )


def _canonical_uuid(value: object) -> UUID:
    if not isinstance(value, str):
        raise InvalidAccessTokenError("Access token is invalid")
    try:
        identifier = UUID(value)
    except ValueError as exc:
        raise InvalidAccessTokenError("Access token is invalid") from exc
    if identifier.int == 0 or value != str(identifier):
        raise InvalidAccessTokenError("Access token is invalid")
    return identifier


__all__ = [
    "AccessPrincipal",
    "AccessTokenCodec",
    "InvalidAccessTokenError",
    "IssuedAccessToken",
]
