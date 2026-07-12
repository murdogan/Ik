"""Short-lived access credentials for the tenantless platform realm."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import jwt

from app.platform.request_context import AuthenticationStrength

PLATFORM_ACCESS_TOKEN_ISSUER = "wealthy-falcon-hr"
PLATFORM_ACCESS_TOKEN_AUDIENCE = "wealthy-falcon-platform-api"


class InvalidPlatformAccessTokenError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class PlatformAccessPrincipal:
    identity_id: UUID
    session_family_id: UUID
    permission_version: int
    authentication_strength: AuthenticationStrength


@dataclass(frozen=True, slots=True)
class IssuedPlatformAccessToken:
    token: str
    expires_at: datetime


class PlatformAccessTokenCodec:
    """Issue and validate only platform-audience access credentials."""

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

    def issue(self, principal: PlatformAccessPrincipal) -> IssuedPlatformAccessToken:
        _validate_principal(principal)
        now = datetime.now(UTC)
        expires_at = now + self._ttl
        token = jwt.encode(
            {
                "iss": PLATFORM_ACCESS_TOKEN_ISSUER,
                "aud": PLATFORM_ACCESS_TOKEN_AUDIENCE,
                "typ": "platform_access",
                "sub": str(principal.identity_id),
                "sid": str(principal.session_family_id),
                "pver": principal.permission_version,
                "acr": principal.authentication_strength.value,
                "jti": str(uuid4()),
                "iat": now,
                "exp": expires_at,
            },
            self._signing_key,
            algorithm="HS256",
        )
        return IssuedPlatformAccessToken(token=token, expires_at=expires_at)

    def decode(self, token: str) -> PlatformAccessPrincipal:
        if not isinstance(token, str) or not token or len(token) > 4096:
            raise InvalidPlatformAccessTokenError("Platform access token is invalid")
        try:
            claims = jwt.decode(
                token,
                self._signing_key,
                algorithms=["HS256"],
                audience=PLATFORM_ACCESS_TOKEN_AUDIENCE,
                issuer=PLATFORM_ACCESS_TOKEN_ISSUER,
                options={
                    "require": [
                        "iss",
                        "aud",
                        "typ",
                        "sub",
                        "sid",
                        "pver",
                        "acr",
                        "jti",
                        "iat",
                        "exp",
                    ]
                },
            )
            if claims["typ"] != "platform_access":
                raise InvalidPlatformAccessTokenError("Platform access token is invalid")
            identity_id = _canonical_uuid(claims["sub"])
            session_family_id = _canonical_uuid(claims["sid"])
            permission_version = claims["pver"]
            if (
                not isinstance(permission_version, int)
                or isinstance(permission_version, bool)
                or permission_version < 1
            ):
                raise InvalidPlatformAccessTokenError("Platform access token is invalid")
            authentication_strength = AuthenticationStrength(claims["acr"])
            if authentication_strength is AuthenticationStrength.UNAUTHENTICATED:
                raise InvalidPlatformAccessTokenError("Platform access token is invalid")
        except (
            jwt.PyJWTError,
            KeyError,
            TypeError,
            ValueError,
            InvalidPlatformAccessTokenError,
        ) as exc:
            raise InvalidPlatformAccessTokenError("Platform access token is invalid") from exc
        return PlatformAccessPrincipal(
            identity_id=identity_id,
            session_family_id=session_family_id,
            permission_version=permission_version,
            authentication_strength=authentication_strength,
        )


def _validate_principal(principal: PlatformAccessPrincipal) -> None:
    if not isinstance(principal, PlatformAccessPrincipal):
        raise TypeError("principal must be a PlatformAccessPrincipal")
    for field_name in ("identity_id", "session_family_id"):
        value = getattr(principal, field_name)
        if not isinstance(value, UUID) or value.int == 0:
            raise ValueError(f"{field_name} must be a non-zero UUID")
    if (
        not isinstance(principal.permission_version, int)
        or isinstance(principal.permission_version, bool)
        or principal.permission_version < 1
    ):
        raise ValueError("permission_version must be a positive integer")
    if (
        not isinstance(principal.authentication_strength, AuthenticationStrength)
        or principal.authentication_strength is AuthenticationStrength.UNAUTHENTICATED
    ):
        raise ValueError("Platform authentication strength must be authenticated")


def _canonical_uuid(value: object) -> UUID:
    if not isinstance(value, str):
        raise InvalidPlatformAccessTokenError("Platform access token is invalid")
    try:
        identifier = UUID(value)
    except ValueError as exc:
        raise InvalidPlatformAccessTokenError("Platform access token is invalid") from exc
    if identifier.int == 0 or value != str(identifier):
        raise InvalidPlatformAccessTokenError("Platform access token is invalid")
    return identifier


__all__ = [
    "IssuedPlatformAccessToken",
    "InvalidPlatformAccessTokenError",
    "PLATFORM_ACCESS_TOKEN_AUDIENCE",
    "PLATFORM_ACCESS_TOKEN_ISSUER",
    "PlatformAccessPrincipal",
    "PlatformAccessTokenCodec",
]
