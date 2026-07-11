"""High-entropy refresh credentials stored only as SHA-256 hashes."""

from dataclasses import dataclass
from hashlib import sha256
from secrets import token_urlsafe
from uuid import UUID, uuid4

REFRESH_TOKEN_VERSION = "rf1"


class InvalidRefreshTokenFormatError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class RefreshTokenMaterial:
    raw_token: str
    token_hash: str
    tenant_id: UUID
    token_id: UUID


def issue_refresh_token(tenant_id: UUID) -> RefreshTokenMaterial:
    if not isinstance(tenant_id, UUID) or tenant_id.int == 0:
        raise ValueError("A non-zero tenant ID is required")
    token_id = uuid4()
    raw_token = (
        f"{REFRESH_TOKEN_VERSION}.{tenant_id}.{token_id}.{token_urlsafe(48)}"
    )
    return RefreshTokenMaterial(
        raw_token=raw_token,
        token_hash=hash_refresh_token(raw_token),
        tenant_id=tenant_id,
        token_id=token_id,
    )


def parse_refresh_token(raw_token: str) -> RefreshTokenMaterial:
    if not isinstance(raw_token, str) or len(raw_token) > 192:
        raise InvalidRefreshTokenFormatError("Refresh token format is invalid")
    try:
        version, tenant_value, token_value, secret = raw_token.split(".", maxsplit=3)
        tenant_id = UUID(tenant_value)
        token_id = UUID(token_value)
    except (ValueError, AttributeError) as exc:
        raise InvalidRefreshTokenFormatError("Refresh token format is invalid") from exc
    if (
        version != REFRESH_TOKEN_VERSION
        or tenant_id.int == 0
        or tenant_value != str(tenant_id)
        or token_id.int == 0
        or token_value != str(token_id)
        or len(secret) < 60
        or not secret.replace("-", "").replace("_", "").isalnum()
    ):
        raise InvalidRefreshTokenFormatError("Refresh token format is invalid")
    return RefreshTokenMaterial(
        raw_token=raw_token,
        token_hash=hash_refresh_token(raw_token),
        tenant_id=tenant_id,
        token_id=token_id,
    )


def hash_refresh_token(raw_token: str) -> str:
    return sha256(raw_token.encode("utf-8")).hexdigest()


__all__ = [
    "InvalidRefreshTokenFormatError",
    "RefreshTokenMaterial",
    "hash_refresh_token",
    "issue_refresh_token",
    "parse_refresh_token",
]
