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

from app.schemas.authorization import RoleSummaryRead

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


class PasswordResetStartRequest(_AuthPayload):
    email: EmailValue

    @field_validator("email")
    @classmethod
    def canonicalize_email(cls, value: str) -> str:
        return normalize_email(value)


class PasswordResetConfirmRequest(_AuthPayload):
    token: SecretStr
    password: SecretStr

    @field_validator("token")
    @classmethod
    def validate_token_length(cls, value: SecretStr) -> SecretStr:
        if not 1 <= len(value.get_secret_value()) <= 160:
            raise ValueError("Password-reset token length is invalid")
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
    workspace_scope: Literal["platform", "tenant"]
    roles: list[RoleSummaryRead]
    permissions: list[str]
    permission_version: int = Field(ge=1)


class LoginRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    access_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in: int = Field(gt=0)
    user: AuthUserRead


class AuthenticatedLoginRead(LoginRead):
    status: Literal["authenticated"]


class OrganizationChoiceRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    selection_key: UUID
    display_name: Annotated[str, StringConstraints(min_length=1, max_length=200)]


class OrganizationSelectionRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["organization_selection_required"]
    selection_transaction: Annotated[
        str,
        StringConstraints(min_length=80, max_length=160),
    ]
    expires_in: int = Field(gt=0, le=900)
    organizations: list[OrganizationChoiceRead] = Field(min_length=1)


class OrganizationSelectionRequest(_AuthPayload):
    selection_transaction: SecretStr
    selection_key: UUID

    @field_validator("selection_transaction")
    @classmethod
    def validate_selection_transaction(cls, value: SecretStr) -> SecretStr:
        if not 80 <= len(value.get_secret_value()) <= 160:
            raise ValueError("Organization selection transaction is invalid")
        return value


class OrganizationSwitchRequest(_AuthPayload):
    """Explicitly empty body contract; caller tenant context is forbidden."""


LoginOutcomeRead = Annotated[
    AuthenticatedLoginRead | OrganizationSelectionRead,
    Field(discriminator="status"),
]


class ActivationRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user: AuthUserRead


class PasswordResetAcceptedRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["accepted"] = "accepted"


class PasswordResetCompletedRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["completed"] = "completed"


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
    "AuthenticatedLoginRead",
    "InvitationRead",
    "InvitationRequest",
    "InvitationUserRead",
    "LoginRead",
    "LoginOutcomeRead",
    "LoginRequest",
    "MeRead",
    "OrganizationChoiceRead",
    "OrganizationSelectionRead",
    "OrganizationSelectionRequest",
    "OrganizationSwitchRequest",
    "PasswordResetAcceptedRead",
    "PasswordResetCompletedRead",
    "PasswordResetConfirmRequest",
    "PasswordResetStartRequest",
    "normalize_email",
]
