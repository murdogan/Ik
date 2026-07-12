"""Opaque, one-use credentials for post-password organization selection."""

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


def issue_organization_selection_token() -> OrganizationSelectionTokenMaterial:
    transaction_id = uuid4()
    raw_token = (
        f"{ORGANIZATION_SELECTION_TOKEN_VERSION}.{transaction_id}.{token_urlsafe(48)}"
    )
    return OrganizationSelectionTokenMaterial(
        raw_token=raw_token,
        token_hash=hash_organization_selection_token(raw_token),
        transaction_id=transaction_id,
    )


def hash_organization_selection_token(raw_token: str) -> str:
    return sha256(raw_token.encode("utf-8")).hexdigest()


__all__ = [
    "OrganizationSelectionTokenMaterial",
    "hash_organization_selection_token",
    "issue_organization_selection_token",
]
