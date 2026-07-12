"""Public RBAC catalog and exact role-assignment contracts."""

from __future__ import annotations

from typing import Literal, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class RoleSummaryRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    code: str
    name: str
    scope_type: Literal["platform", "tenant"]


class RoleRead(RoleSummaryRead):
    description: str
    permissions: list[str]


class PermissionRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    code: str
    resource: str
    action: str
    scope: Literal["own", "team", "department", "branch", "tenant", "platform"]
    description: str


class UserRoleReplace(BaseModel):
    """The complete desired tenant-role set for one user."""

    model_config = ConfigDict(extra="forbid")

    role_ids: list[UUID] = Field(max_length=8)

    @model_validator(mode="after")
    def reject_duplicate_roles(self) -> Self:
        if len(set(self.role_ids)) != len(self.role_ids):
            raise ValueError("Role IDs must be unique")
        return self


__all__ = [
    "PermissionRead",
    "RoleRead",
    "RoleSummaryRead",
    "UserRoleReplace",
]
