"""Opaque, one-use credentials for authenticated organization selection."""

from dataclasses import dataclass
from hashlib import sha256
from secrets import token_urlsafe
from uuid import UUID, uuid4

ORGANIZATION_SELECTION_TOKEN_VERSION = "os1"


@dataclass(frozen=True, slots=True)
class OrganizationSelectionTokenMaterial:
    raw_token: str
    token_hash: str
    transaction_id: UUID


class InvalidOrganizationSelectionTokenFormatError(ValueError):
    pass


def issue_organization_selection_token() -> OrganizationSelectionTokenMaterial:
    transaction_id = uuid4()
    raw_token = f"{ORGANIZATION_SELECTION_TOKEN_VERSION}.{transaction_id}.{token_urlsafe(48)}"
    return OrganizationSelectionTokenMaterial(
        raw_token=raw_token,
        token_hash=hash_organization_selection_token(raw_token),
        transaction_id=transaction_id,
    )


def hash_organization_selection_token(raw_token: str) -> str:
    return sha256(raw_token.encode("utf-8")).hexdigest()


def parse_organization_selection_token(
    raw_token: str,
) -> OrganizationSelectionTokenMaterial:
    if not isinstance(raw_token, str) or not 80 <= len(raw_token) <= 160:
        raise InvalidOrganizationSelectionTokenFormatError(
            "Organization selection token is invalid"
        )
    version, separator, remainder = raw_token.partition(".")
    transaction_text, second_separator, secret = remainder.partition(".")
    if (
        separator != "."
        or second_separator != "."
        or version != ORGANIZATION_SELECTION_TOKEN_VERSION
        or not secret
        or "." in secret
    ):
        raise InvalidOrganizationSelectionTokenFormatError(
            "Organization selection token is invalid"
        )
    try:
        transaction_id = UUID(transaction_text)
    except ValueError as exc:
        raise InvalidOrganizationSelectionTokenFormatError(
            "Organization selection token is invalid"
        ) from exc
    if transaction_id.int == 0 or transaction_text != str(transaction_id):
        raise InvalidOrganizationSelectionTokenFormatError(
            "Organization selection token is invalid"
        )
    return OrganizationSelectionTokenMaterial(
        raw_token=raw_token,
        token_hash=hash_organization_selection_token(raw_token),
        transaction_id=transaction_id,
    )


__all__ = [
    "OrganizationSelectionTokenMaterial",
    "InvalidOrganizationSelectionTokenFormatError",
    "hash_organization_selection_token",
    "issue_organization_selection_token",
    "parse_organization_selection_token",
]
