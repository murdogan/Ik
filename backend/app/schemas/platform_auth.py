"""HTTP contracts for the tenantless platform authentication realm."""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.auth import LoginRequest
from app.schemas.authorization import RoleSummaryRead


class PlatformLoginRequest(LoginRequest):
    """Email/password only; tenant and organization selectors are forbidden."""


class PlatformAuthUserRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    email: str
    full_name: str | None = None
    workspace_scope: Literal["platform"] = "platform"
    roles: list[RoleSummaryRead]
    permissions: list[str]
    permission_version: int = Field(ge=1)
    authentication_strength: Literal["single_factor", "multi_factor", "step_up"]


class PlatformLoginRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    access_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in: int = Field(gt=0)
    user: PlatformAuthUserRead


class PlatformAuthenticatedLoginRead(PlatformLoginRead):
    status: Literal["authenticated"] = "authenticated"


class PlatformMeRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user: PlatformAuthUserRead


__all__ = [
    "PlatformAuthenticatedLoginRead",
    "PlatformAuthUserRead",
    "PlatformLoginRead",
    "PlatformLoginRequest",
    "PlatformMeRead",
]
