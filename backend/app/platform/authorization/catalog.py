"""Immutable system-role and permission catalog.

This module deliberately uses only the Python standard library. Persistence adapters may project
the definitions into a database, while policy code can use the same stable codes without gaining a
dependency on SQLAlchemy or an application service.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from re import fullmatch
from types import MappingProxyType
from uuid import UUID

_TOKEN_PATTERN = r"[a-z][a-z0-9_]*"


class RoleScopeType(StrEnum):
    PLATFORM = "platform"
    TENANT = "tenant"


class AuthorizationScope(StrEnum):
    OWN = "own"
    TEAM = "team"
    DEPARTMENT = "department"
    BRANCH = "branch"
    TENANT = "tenant"
    PLATFORM = "platform"


class PermissionTargetType(StrEnum):
    SCOPE = "scope"
    FIELD = "field"


@dataclass(frozen=True, slots=True)
class PermissionName:
    resource: str
    action: str
    target: str
    target_type: PermissionTargetType

    def __post_init__(self) -> None:
        for field_name in ("resource", "action", "target"):
            value = getattr(self, field_name)
            if not isinstance(value, str) or fullmatch(_TOKEN_PATTERN, value) is None:
                raise ValueError(f"Permission {field_name} must be a lowercase identifier")
        if not isinstance(self.target_type, PermissionTargetType):
            raise TypeError("Permission target_type must be a PermissionTargetType")
        if self.target_type is PermissionTargetType.SCOPE:
            try:
                AuthorizationScope(self.target)
            except ValueError as exc:
                raise ValueError("Permission scope is not a supported scope primitive") from exc

    @property
    def code(self) -> str:
        return f"{self.resource}:{self.action}:{self.target}"

    @property
    def scope(self) -> AuthorizationScope | None:
        if self.target_type is PermissionTargetType.FIELD:
            return None
        return AuthorizationScope(self.target)

    @classmethod
    def parse(cls, code: str) -> PermissionName:
        if not isinstance(code, str):
            raise TypeError("Permission code must be a string")
        parts = code.split(":")
        if len(parts) != 3:
            raise ValueError("Permission code must contain resource, action, and target")
        resource, action, target = parts
        target_type = (
            PermissionTargetType.SCOPE
            if target in AuthorizationScope
            else PermissionTargetType.FIELD
        )
        return cls(
            resource=resource,
            action=action,
            target=target,
            target_type=target_type,
        )


@dataclass(frozen=True, slots=True)
class RoleDefinition:
    id: UUID
    code: str
    name: str
    description: str
    scope_type: RoleScopeType

    def __post_init__(self) -> None:
        if not isinstance(self.id, UUID) or self.id.int == 0:
            raise ValueError("Role id must be a non-zero UUID")
        if fullmatch(_TOKEN_PATTERN, self.code) is None:
            raise ValueError("Role code must be a lowercase identifier")
        if not self.name.strip() or not self.description.strip():
            raise ValueError("Role name and description are required")
        if not isinstance(self.scope_type, RoleScopeType):
            raise TypeError("Role scope_type must be a RoleScopeType")


@dataclass(frozen=True, slots=True)
class PermissionDefinition:
    id: UUID
    name: PermissionName
    description: str

    def __post_init__(self) -> None:
        if not isinstance(self.id, UUID) or self.id.int == 0:
            raise ValueError("Permission id must be a non-zero UUID")
        if not isinstance(self.name, PermissionName):
            raise TypeError("Permission name must be a PermissionName")
        if not self.description.strip():
            raise ValueError("Permission description is required")

    @property
    def code(self) -> str:
        return self.name.code


def _role(
    ordinal: int,
    code: str,
    name: str,
    description: str,
    scope_type: RoleScopeType,
) -> RoleDefinition:
    return RoleDefinition(
        id=UUID(f"d2000000-0000-4000-8000-{ordinal:012d}"),
        code=code,
        name=name,
        description=description,
        scope_type=scope_type,
    )


ROLES: tuple[RoleDefinition, ...] = (
    _role(
        1,
        "super_admin",
        "Platform super admin",
        "Operates platform tenant metadata without implicit customer HR access.",
        RoleScopeType.PLATFORM,
    ),
    _role(
        2,
        "tenant_admin",
        "Tenant admin",
        "Administers tenant settings, users, roles, and application access.",
        RoleScopeType.TENANT,
    ),
    _role(
        3,
        "hr_director",
        "HR director",
        "Leads tenant-wide HR operations and compliance visibility.",
        RoleScopeType.TENANT,
    ),
    _role(
        4,
        "hr_specialist",
        "HR specialist",
        "Runs day-to-day HR operations within granted organizational scopes.",
        RoleScopeType.TENANT,
    ),
    _role(
        5,
        "it_admin",
        "IT admin",
        "Manages tenant identity and session operations without HR-data access.",
        RoleScopeType.TENANT,
    ),
    _role(
        6,
        "auditor",
        "Auditor",
        "Reads authorized tenant audit history without mutation privileges.",
        RoleScopeType.TENANT,
    ),
    _role(
        7,
        "manager",
        "Manager",
        "Reads team information and handles team leave approvals.",
        RoleScopeType.TENANT,
    ),
    _role(
        8,
        "employee",
        "Employee",
        "Uses employee self-service within own-data scope.",
        RoleScopeType.TENANT,
    ),
)


def _permission(
    ordinal: int,
    code: str,
    description: str,
) -> PermissionDefinition:
    return PermissionDefinition(
        id=UUID(f"d3000000-0000-4000-8000-{ordinal:012d}"),
        name=PermissionName.parse(code),
        description=description,
    )


PERMISSIONS: tuple[PermissionDefinition, ...] = (
    _permission(1, "tenant:read:tenant", "Read current-tenant metadata."),
    _permission(2, "tenant:update:tenant", "Update allowlisted current-tenant settings."),
    _permission(3, "dashboard:read:tenant", "Read tenant-wide dashboard summaries."),
    _permission(4, "dashboard:read:own", "Read the current user's dashboard."),
    _permission(5, "user:read:tenant", "Read users in the current tenant."),
    _permission(6, "user:update:tenant", "Update users in the current tenant."),
    _permission(7, "user:invite:tenant", "Invite users to the current tenant."),
    _permission(8, "role:read:tenant", "Read tenant-assignable roles."),
    _permission(9, "role:assign:tenant", "Replace a tenant user's role assignments."),
    _permission(10, "permission:read:tenant", "Read the tenant permission catalog."),
    _permission(11, "session:manage:tenant", "Manage user sessions in the current tenant."),
    _permission(12, "employee:read:own", "Read the current user's employee record."),
    _permission(13, "employee:read:team", "Read employee records in the current user's team."),
    _permission(14, "employee:read:department", "Read employee records in scope departments."),
    _permission(15, "employee:read:branch", "Read employee records in scope branches."),
    _permission(16, "employee:read:tenant", "Read employee records across the current tenant."),
    _permission(17, "employee:update:tenant", "Update employee records across the tenant."),
    _permission(18, "leave:read:own", "Read the current user's leave records."),
    _permission(19, "leave:read:team", "Read leave records in the current user's team."),
    _permission(20, "leave:read:department", "Read leave records in scope departments."),
    _permission(21, "leave:read:branch", "Read leave records in scope branches."),
    _permission(22, "leave:read:tenant", "Read leave records across the current tenant."),
    _permission(23, "leave:approve:team", "Approve leave requests in the current user's team."),
    _permission(24, "audit:read:tenant", "Read authorized audit history in the tenant."),
    _permission(25, "tenant:read:platform", "Read platform-safe tenant metadata."),
    _permission(26, "tenant:create:platform", "Provision a tenant through platform operations."),
    _permission(27, "tenant:update:platform", "Update platform-safe tenant metadata."),
    _permission(28, "feature:read:platform", "Read platform feature rollout metadata."),
    _permission(29, "feature:update:platform", "Update platform feature rollout metadata."),
    _permission(30, "audit:read:platform", "Read platform operations audit history."),
    _permission(31, "organization:read:tenant", "Read current-tenant organization settings."),
    _permission(32, "organization:update:tenant", "Manage current-tenant organization settings."),
    _permission(33, "leave:manage:tenant", "Manage leave requests across the current tenant."),
    _permission(34, "document_type:manage:tenant", "Manage tenant employee-document types."),
    _permission(
        35,
        "employee_document:manage:tenant",
        "Manage employee document metadata and private content across the tenant.",
    ),
    _permission(
        36,
        "employee_document:read:own",
        "Read clean employee-visible documents linked to the current membership.",
    ),
    _permission(37, "leave:create:own", "Create leave requests for the current employee."),
    _permission(38, "leave:cancel:own", "Cancel the current employee's leave requests."),
    _permission(
        39,
        "leave:adjust:tenant",
        "Record reason-backed leave balance adjustments across the current tenant.",
    ),
    _permission(
        40,
        "employee_document:upload:own",
        "Upload employee documents linked to the current membership.",
    ),
    _permission(41, "request:read:own", "Read the current employee's fixed request projection."),
    _permission(42, "request:read:team", "Read team leave requests in the fixed projection."),
    _permission(43, "request:read:tenant", "Read the tenant HR request projection."),
    _permission(44, "document_request:create:own", "Request an HR-produced document."),
    _permission(45, "document_request:read:own", "Read own HR document requests."),
    _permission(46, "document_request:manage:tenant", "Resolve tenant document requests."),
    _permission(47, "announcement:read:own", "Read announcements snapshotted for this user."),
    _permission(48, "announcement:manage:tenant", "Manage and publish tenant announcements."),
    _permission(49, "notification:read:own", "Read and consume the current user's inbox."),
    _permission(50, "self_service:read:own", "Read the employee self-service home."),
)


# Explicit grants are intentionally exact. In particular, role names never imply privileges and
# the tenant administrator receives no employee, leave, session-management, or platform permission.
ROLE_PERMISSION_CODES = MappingProxyType(
    {
        "super_admin": frozenset(
            {
                "tenant:read:platform",
                "tenant:create:platform",
                "tenant:update:platform",
                "feature:read:platform",
                "feature:update:platform",
                "audit:read:platform",
            }
        ),
        "tenant_admin": frozenset(
            {
                "tenant:read:tenant",
                "tenant:update:tenant",
                "dashboard:read:tenant",
                "dashboard:read:own",
                "user:read:tenant",
                "user:update:tenant",
                "user:invite:tenant",
                "role:read:tenant",
                "role:assign:tenant",
                "permission:read:tenant",
                "audit:read:tenant",
                "organization:read:tenant",
                "organization:update:tenant",
            }
        ),
        "hr_director": frozenset(
            {
                "dashboard:read:tenant",
                "dashboard:read:own",
                "employee:read:own",
                "employee:read:team",
                "employee:read:department",
                "employee:read:branch",
                "employee:read:tenant",
                "employee:update:tenant",
                "leave:read:own",
                "leave:read:team",
                "leave:read:department",
                "leave:read:branch",
                "leave:read:tenant",
                "leave:manage:tenant",
                "leave:create:own",
                "leave:cancel:own",
                "leave:adjust:tenant",
                "audit:read:tenant",
                "organization:read:tenant",
                "organization:update:tenant",
                "document_type:manage:tenant",
                "employee_document:manage:tenant",
                "employee_document:read:own",
                "employee_document:upload:own",
                "request:read:own",
                "request:read:tenant",
                "document_request:create:own",
                "document_request:read:own",
                "document_request:manage:tenant",
                "announcement:read:own",
                "announcement:manage:tenant",
                "notification:read:own",
                "self_service:read:own",
            }
        ),
        "hr_specialist": frozenset(
            {
                "dashboard:read:tenant",
                "dashboard:read:own",
                "employee:read:own",
                "employee:read:department",
                "employee:read:branch",
                "employee:read:tenant",
                "employee:update:tenant",
                "leave:read:own",
                "leave:read:department",
                "leave:read:branch",
                "leave:read:tenant",
                "leave:manage:tenant",
                "leave:create:own",
                "leave:cancel:own",
                "leave:adjust:tenant",
                "organization:read:tenant",
                "organization:update:tenant",
                "document_type:manage:tenant",
                "employee_document:manage:tenant",
                "employee_document:read:own",
                "employee_document:upload:own",
                "request:read:own",
                "request:read:tenant",
                "document_request:create:own",
                "document_request:read:own",
                "document_request:manage:tenant",
                "announcement:read:own",
                "announcement:manage:tenant",
                "notification:read:own",
                "self_service:read:own",
            }
        ),
        "it_admin": frozenset(
            {
                "dashboard:read:own",
                "user:read:tenant",
                "session:manage:tenant",
                "audit:read:tenant",
            }
        ),
        "auditor": frozenset(
            {
                "dashboard:read:own",
                "audit:read:tenant",
                "organization:read:tenant",
            }
        ),
        "manager": frozenset(
            {
                "dashboard:read:own",
                "employee:read:own",
                "employee:read:team",
                "leave:read:own",
                "leave:read:team",
                "leave:approve:team",
                "leave:create:own",
                "leave:cancel:own",
                "employee_document:read:own",
                "employee_document:upload:own",
                "request:read:own",
                "request:read:team",
                "document_request:create:own",
                "document_request:read:own",
                "announcement:read:own",
                "notification:read:own",
                "self_service:read:own",
            }
        ),
        "employee": frozenset(
            {
                "dashboard:read:own",
                "employee:read:own",
                "leave:read:own",
                "leave:create:own",
                "leave:cancel:own",
                "employee_document:read:own",
                "employee_document:upload:own",
                "request:read:own",
                "document_request:create:own",
                "document_request:read:own",
                "announcement:read:own",
                "notification:read:own",
                "self_service:read:own",
            }
        ),
    }
)

ROLES_BY_CODE = MappingProxyType({role.code: role for role in ROLES})
PERMISSIONS_BY_CODE = MappingProxyType(
    {permission.code: permission for permission in PERMISSIONS}
)

if set(ROLE_PERMISSION_CODES) != set(ROLES_BY_CODE):  # pragma: no cover - import invariant
    raise RuntimeError("Every seeded role must have one explicit permission grant set")
if any(
    permission_code not in PERMISSIONS_BY_CODE
    for grants in ROLE_PERMISSION_CODES.values()
    for permission_code in grants
):  # pragma: no cover - import invariant
    raise RuntimeError("Role grants must reference the seeded permission catalog")


__all__ = [
    "PERMISSIONS",
    "PERMISSIONS_BY_CODE",
    "ROLES",
    "ROLES_BY_CODE",
    "ROLE_PERMISSION_CODES",
    "AuthorizationScope",
    "PermissionDefinition",
    "PermissionName",
    "PermissionTargetType",
    "RoleDefinition",
    "RoleScopeType",
]
