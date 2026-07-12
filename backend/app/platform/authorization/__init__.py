"""Pure authorization contracts shared by application policy adapters."""

from app.platform.authorization.catalog import (
    PERMISSIONS,
    PERMISSIONS_BY_CODE,
    ROLE_PERMISSION_CODES,
    ROLES,
    ROLES_BY_CODE,
    AuthorizationScope,
    PermissionDefinition,
    PermissionName,
    PermissionTargetType,
    RoleDefinition,
    RoleScopeType,
)
from app.platform.authorization.policy import (
    AuthorizationEffect,
    DenyByDefaultPolicy,
    PolicyDecision,
)

__all__ = [
    "PERMISSIONS",
    "PERMISSIONS_BY_CODE",
    "ROLES",
    "ROLES_BY_CODE",
    "ROLE_PERMISSION_CODES",
    "AuthorizationEffect",
    "AuthorizationScope",
    "DenyByDefaultPolicy",
    "PermissionDefinition",
    "PermissionName",
    "PermissionTargetType",
    "PolicyDecision",
    "RoleDefinition",
    "RoleScopeType",
]
