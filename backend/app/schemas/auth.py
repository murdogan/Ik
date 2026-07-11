from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    SecretStr,
    StrictStr,
    StringConstraints,
    field_validator,
)

from app.schemas.tenant import TenantSlug

EmailValue = Annotated[
    StrictStr,
    StringConstraints(strip_whitespace=True, min_length=3, max_length=320),
]
FullNameValue = Annotated[
    StrictStr,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=200),
]


def normalize_email(value: str) -> str:
    normalized = value.strip().lower()
    if (
        normalized.count("@") != 1
        or any(character.isspace() for character in normalized)
        or normalized.startswith("@")
        or normalized.endswith("@")
    ):
        raise ValueError("A valid email address is required")
    return normalized


class _AuthPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")


class LoginRequest(_AuthPayload):
    tenant_slug: TenantSlug
    email: EmailValue
    password: SecretStr

    @field_validator("email")
    @classmethod
    def canonicalize_email(cls, value: str) -> str:
        return normalize_email(value)

    @field_validator("password")
    @classmethod
    def validate_password_length(cls, value: SecretStr) -> SecretStr:
        if not 1 <= len(value.get_secret_value()) <= 128:
            raise ValueError("Password length is invalid")
        return value


class ActivationRequest(_AuthPayload):
    token: SecretStr
    password: SecretStr

    @field_validator("token")
    @classmethod
    def validate_token_length(cls, value: SecretStr) -> SecretStr:
        if not 1 <= len(value.get_secret_value()) <= 160:
            raise ValueError("Activation token length is invalid")
        return value

    @field_validator("password")
    @classmethod
    def validate_password_policy(cls, value: SecretStr) -> SecretStr:
        password = value.get_secret_value()
        if not 12 <= len(password) <= 128:
            raise ValueError("Password must be between 12 and 128 characters")
        if password.isspace():
            raise ValueError("Password cannot contain only whitespace")
        return value


class InvitationRequest(_AuthPayload):
    email: EmailValue
    full_name: FullNameValue

    @field_validator("email")
    @classmethod
    def canonicalize_email(cls, value: str) -> str:
        return normalize_email(value)


class AuthTenantRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    slug: str
    name: str


class AuthUserRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    tenant_id: UUID
    email: str
    full_name: str
    tenant: AuthTenantRead


class LoginRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    access_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in: int = Field(gt=0)
    user: AuthUserRead


class ActivationRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user: AuthUserRead


class MeRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user: AuthUserRead


class InvitationUserRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    email: str
    full_name: str
    status: Literal["invited"] = "invited"


class InvitationRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user: InvitationUserRead
    activation_url: str
    expires_at: datetime


__all__ = [
    "ActivationRead",
    "ActivationRequest",
    "AuthTenantRead",
    "AuthUserRead",
    "InvitationRead",
    "InvitationRequest",
    "InvitationUserRead",
    "LoginRead",
    "LoginRequest",
    "MeRead",
    "normalize_email",
]
