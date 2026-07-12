"""High-entropy, identity-bound password-reset credential helpers."""

from dataclasses import dataclass
from hashlib import sha256
from secrets import token_urlsafe
from uuid import UUID

PASSWORD_RESET_TOKEN_VERSION = "pr1"


class InvalidPasswordResetTokenFormatError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class PasswordResetTokenMaterial:
    raw_token: str
    token_hash: str
    identity_id: UUID


def issue_password_reset_token(identity_id: UUID) -> PasswordResetTokenMaterial:
    if not isinstance(identity_id, UUID) or identity_id.int == 0:
        raise ValueError("A non-zero identity ID is required")
    raw_token = f"{PASSWORD_RESET_TOKEN_VERSION}.{identity_id}.{token_urlsafe(32)}"
    return PasswordResetTokenMaterial(
        raw_token=raw_token,
        token_hash=hash_password_reset_token(raw_token),
        identity_id=identity_id,
    )


def parse_password_reset_token(raw_token: str) -> PasswordResetTokenMaterial:
    if not isinstance(raw_token, str) or len(raw_token) > 160:
        raise InvalidPasswordResetTokenFormatError("Password-reset token format is invalid")
    try:
        version, identity_value, secret = raw_token.split(".", maxsplit=2)
        identity_id = UUID(identity_value)
    except (ValueError, AttributeError) as exc:
        raise InvalidPasswordResetTokenFormatError(
            "Password-reset token format is invalid"
        ) from exc
    if (
        version != PASSWORD_RESET_TOKEN_VERSION
        or identity_id.int == 0
        or identity_value != str(identity_id)
        or len(secret) < 40
        or not secret.replace("-", "").replace("_", "").isalnum()
    ):
        raise InvalidPasswordResetTokenFormatError("Password-reset token format is invalid")
    return PasswordResetTokenMaterial(
        raw_token=raw_token,
        token_hash=hash_password_reset_token(raw_token),
        identity_id=identity_id,
    )


def hash_password_reset_token(raw_token: str) -> str:
    return sha256(raw_token.encode("utf-8")).hexdigest()


__all__ = [
    "InvalidPasswordResetTokenFormatError",
    "PASSWORD_RESET_TOKEN_VERSION",
    "PasswordResetTokenMaterial",
    "hash_password_reset_token",
    "issue_password_reset_token",
    "parse_password_reset_token",
]
