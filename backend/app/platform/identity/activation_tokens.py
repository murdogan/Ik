"""High-entropy activation token creation and tenant-bound lookup hashing."""

from dataclasses import dataclass
from hashlib import sha256
from hmac import new as hmac_new
from secrets import token_urlsafe
from uuid import UUID, uuid5

ACTIVATION_TOKEN_VERSION = "v1"
_DELIVERY_TOKEN_PURPOSE = b"wealthy-falcon:activation-delivery:v1"
_MANUAL_DELIVERY_EVENT_NAMESPACE = UUID("95b524cb-b0bd-4d54-96b2-f7a15988835e")


class InvalidActivationTokenFormatError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class ActivationTokenMaterial:
    raw_token: str
    token_hash: str
    tenant_id: UUID


class ActivationDeliveryTokenCodec:
    """Reproduce one opaque activation credential for idempotent email retries."""

    __slots__ = ("_signing_key",)

    def __init__(self, signing_key: bytes) -> None:
        if len(signing_key) < 32:
            raise ValueError("Activation delivery signing keys must contain at least 32 bytes")
        self._signing_key = signing_key

    def issue(self, tenant_id: UUID, activation_id: UUID) -> ActivationTokenMaterial:
        _require_nonzero_uuid(tenant_id, "tenant")
        _require_nonzero_uuid(activation_id, "activation")
        material = b"\0".join(
            (
                _DELIVERY_TOKEN_PURPOSE,
                tenant_id.bytes,
                activation_id.bytes,
            )
        )
        secret = hmac_new(self._signing_key, material, sha256).hexdigest()
        return _activation_token_material(tenant_id, secret)


def issue_activation_token(tenant_id: UUID) -> ActivationTokenMaterial:
    _require_nonzero_uuid(tenant_id, "tenant")
    return _activation_token_material(tenant_id, token_urlsafe(32))


def manual_activation_delivery_event_id(activation_id: UUID) -> UUID:
    """Return the recognizable outbox marker for a copy-only manual credential."""

    _require_nonzero_uuid(activation_id, "activation")
    return uuid5(_MANUAL_DELIVERY_EVENT_NAMESPACE, str(activation_id))


def is_manual_activation_delivery_event(event_id: UUID, activation_id: UUID) -> bool:
    """Recognize only markers derived from the event's own activation credential."""

    if not isinstance(event_id, UUID) or event_id.int == 0:
        return False
    try:
        return event_id == manual_activation_delivery_event_id(activation_id)
    except ValueError:
        return False


def _activation_token_material(tenant_id: UUID, secret: str) -> ActivationTokenMaterial:
    raw_token = f"{ACTIVATION_TOKEN_VERSION}.{tenant_id}.{secret}"
    return ActivationTokenMaterial(
        raw_token=raw_token,
        token_hash=hash_activation_token(raw_token),
        tenant_id=tenant_id,
    )


def _require_nonzero_uuid(value: UUID, label: str) -> None:
    if not isinstance(value, UUID) or value.int == 0:
        raise ValueError(f"A non-zero {label} ID is required")


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
    "ActivationDeliveryTokenCodec",
    "ActivationTokenMaterial",
    "InvalidActivationTokenFormatError",
    "hash_activation_token",
    "is_manual_activation_delivery_event",
    "issue_activation_token",
    "manual_activation_delivery_event_id",
    "parse_activation_token",
]
