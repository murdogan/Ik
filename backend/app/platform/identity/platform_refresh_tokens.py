"""High-entropy refresh credentials for tenantless platform sessions."""

from dataclasses import dataclass
from hashlib import sha256
from secrets import token_urlsafe
from uuid import UUID, uuid4

PLATFORM_REFRESH_TOKEN_VERSION = "prf1"


class InvalidPlatformRefreshTokenFormatError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class PlatformRefreshTokenMaterial:
    raw_token: str
    token_hash: str
    token_id: UUID


def issue_platform_refresh_token() -> PlatformRefreshTokenMaterial:
    token_id = uuid4()
    raw_token = f"{PLATFORM_REFRESH_TOKEN_VERSION}.{token_id}.{token_urlsafe(48)}"
    return PlatformRefreshTokenMaterial(
        raw_token=raw_token,
        token_hash=hash_platform_refresh_token(raw_token),
        token_id=token_id,
    )


def parse_platform_refresh_token(raw_token: str) -> PlatformRefreshTokenMaterial:
    if not isinstance(raw_token, str) or len(raw_token) > 160:
        raise InvalidPlatformRefreshTokenFormatError("Platform refresh token format is invalid")
    try:
        version, token_value, secret = raw_token.split(".", maxsplit=2)
        token_id = UUID(token_value)
    except (ValueError, AttributeError) as exc:
        raise InvalidPlatformRefreshTokenFormatError(
            "Platform refresh token format is invalid"
        ) from exc
    if (
        version != PLATFORM_REFRESH_TOKEN_VERSION
        or token_id.int == 0
        or token_value != str(token_id)
        or len(secret) < 60
        or not secret.replace("-", "").replace("_", "").isalnum()
    ):
        raise InvalidPlatformRefreshTokenFormatError("Platform refresh token format is invalid")
    return PlatformRefreshTokenMaterial(
        raw_token=raw_token,
        token_hash=hash_platform_refresh_token(raw_token),
        token_id=token_id,
    )


def hash_platform_refresh_token(raw_token: str) -> str:
    return sha256(raw_token.encode("utf-8")).hexdigest()


__all__ = [
    "InvalidPlatformRefreshTokenFormatError",
    "PLATFORM_REFRESH_TOKEN_VERSION",
    "PlatformRefreshTokenMaterial",
    "hash_platform_refresh_token",
    "issue_platform_refresh_token",
    "parse_platform_refresh_token",
]
