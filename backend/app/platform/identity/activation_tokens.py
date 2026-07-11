"""High-entropy activation token creation and tenant-bound lookup hashing."""

from dataclasses import dataclass
from hashlib import sha256
from secrets import token_urlsafe
from uuid import UUID

ACTIVATION_TOKEN_VERSION = "v1"


class InvalidActivationTokenFormatError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class ActivationTokenMaterial:
    raw_token: str
    token_hash: str
    tenant_id: UUID


def issue_activation_token(tenant_id: UUID) -> ActivationTokenMaterial:
    if not isinstance(tenant_id, UUID) or tenant_id.int == 0:
        raise ValueError("A non-zero tenant ID is required")
    raw_token = f"{ACTIVATION_TOKEN_VERSION}.{tenant_id}.{token_urlsafe(32)}"
    return ActivationTokenMaterial(
        raw_token=raw_token,
        token_hash=hash_activation_token(raw_token),
        tenant_id=tenant_id,
    )


def parse_activation_token(raw_token: str) -> ActivationTokenMaterial:
    if not isinstance(raw_token, str) or len(raw_token) > 160:
        raise InvalidActivationTokenFormatError("Activation token format is invalid")
    try:
        version, tenant_value, secret = raw_token.split(".", maxsplit=2)
        tenant_id = UUID(tenant_value)
    except (ValueError, AttributeError) as exc:
        raise InvalidActivationTokenFormatError("Activation token format is invalid") from exc
    if (
        version != ACTIVATION_TOKEN_VERSION
        or tenant_id.int == 0
        or tenant_value != str(tenant_id)
        or len(secret) < 40
        or not secret.replace("-", "").replace("_", "").isalnum()
    ):
        raise InvalidActivationTokenFormatError("Activation token format is invalid")
    return ActivationTokenMaterial(
        raw_token=raw_token,
        token_hash=hash_activation_token(raw_token),
        tenant_id=tenant_id,
    )


def hash_activation_token(raw_token: str) -> str:
    return sha256(raw_token.encode("utf-8")).hexdigest()


__all__ = [
    "ActivationTokenMaterial",
    "InvalidActivationTokenFormatError",
    "hash_activation_token",
    "issue_activation_token",
    "parse_activation_token",
]
