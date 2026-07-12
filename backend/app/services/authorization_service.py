"""RBAC catalog reads, authorization snapshots, and atomic role replacement."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.authorization import Permission, Role, RolePermission, UserRole
from app.models.user import User
from app.platform.audit import (
    AuditActorType,
    AuditCategory,
    AuditContext,
    AuditDataClassification,
    AuditEventDraft,
    AuditEventType,
    AuditRecorder,
    AuditResult,
    AuditScopeType,
    AuditVisibilityClass,
)
from app.platform.authorization import (
    PERMISSIONS,
    PERMISSIONS_BY_CODE,
    ROLE_PERMISSION_CODES,
    ROLES,
    ROLES_BY_CODE,
)
from app.platform.db import SqlAlchemyUnitOfWork, configure_tenant_database_access
from app.platform.errors.application import ApplicationError
from app.services.audit_recorder import SqlAlchemyAuditRecorder
from app.services.identity_projection_service import sync_existing_membership_projection


class AuthorizationAccessDeniedError(ApplicationError):
    pass


class RoleAssignmentInvalidError(ApplicationError):
    pass


class RoleAssignmentConflictError(ApplicationError):
    pass


class RoleAssignmentUserNotFoundError(ApplicationError):
    pass


@dataclass(frozen=True, slots=True)
class AssignedRole:
    id: UUID
    code: str
    name: str
    scope_type: str


@dataclass(frozen=True, slots=True)
class AuthorizationSnapshot:
    roles: tuple[AssignedRole, ...]
    permissions: tuple[str, ...]
    workspace_scope: str


@dataclass(frozen=True, slots=True)
class PermissionCatalogRecord:
    id: UUID
    code: str
    resource: str
    action: str
    scope: str
    description: str


@dataclass(frozen=True, slots=True)
class RoleCatalogRecord:
    id: UUID
    code: str
    name: str
    description: str
    scope_type: str
    permissions: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class RoleReplacementRecord:
    id: UUID
    email: str
    full_name: str
    status: str
    roles: tuple[AssignedRole, ...]
    permission_version: int
    created_at: datetime
    updated_at: datetime


async def load_authorization_snapshot(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    user_id: UUID,
) -> AuthorizationSnapshot:
    rows = (
        await session.execute(
            select(Role, Permission.code)
            .join(
                UserRole,
                (UserRole.role_id == Role.id) & (UserRole.role_scope_type == Role.scope_type),
            )
            .outerjoin(RolePermission, RolePermission.role_id == Role.id)
            .outerjoin(Permission, Permission.id == RolePermission.permission_id)
            .where(
                UserRole.tenant_id == tenant_id,
                UserRole.user_id == user_id,
                UserRole.active.is_(True),
            )
            .order_by(Role.code, Permission.code)
        )
    ).all()

    roles_by_id: dict[UUID, AssignedRole] = {}
    permission_codes: set[str] = set()
    scope_types: set[str] = set()
    for role, permission_code in rows:
        roles_by_id[role.id] = AssignedRole(
            id=role.id,
            code=role.code,
            name=role.name,
            scope_type=role.scope_type,
        )
        scope_types.add(role.scope_type)
        if permission_code is not None:
            permission_codes.add(permission_code)

    # A mixed platform/tenant subject is an invalid authority state and receives no permissions.
    if len(scope_types) > 1:
        return AuthorizationSnapshot(
            roles=tuple(sorted(roles_by_id.values(), key=lambda role: role.code)),
            permissions=(),
            workspace_scope="tenant",
        )
    workspace_scope = "platform" if scope_types == {"platform"} else "tenant"
    return AuthorizationSnapshot(
        roles=tuple(sorted(roles_by_id.values(), key=lambda role: role.code)),
        permissions=tuple(sorted(permission_codes)),
        workspace_scope=workspace_scope,
    )


async def load_assigned_roles(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    user_ids: tuple[UUID, ...],
) -> dict[UUID, tuple[AssignedRole, ...]]:
    if not user_ids:
        return {}
    rows = (
        await session.execute(
            select(UserRole.user_id, Role)
            .join(
                Role,
                (Role.id == UserRole.role_id) & (Role.scope_type == UserRole.role_scope_type),
            )
            .where(
                UserRole.tenant_id == tenant_id,
                UserRole.user_id.in_(user_ids),
                UserRole.active.is_(True),
            )
            .order_by(UserRole.user_id, Role.code)
        )
    ).all()
    grouped: dict[UUID, list[AssignedRole]] = {user_id: [] for user_id in user_ids}
    for user_id, role in rows:
        grouped[user_id].append(
            AssignedRole(
                id=role.id,
                code=role.code,
                name=role.name,
                scope_type=role.scope_type,
            )
        )
    return {user_id: tuple(roles) for user_id, roles in grouped.items()}


class AuthorizationService:
    def __init__(
        self,
        *,
        session_factory: async_sessionmaker[AsyncSession],
        audit_recorder_factory: Callable[[AsyncSession], AuditRecorder] = SqlAlchemyAuditRecorder,
    ) -> None:
        self._session_factory = session_factory
        self._audit_recorder_factory = audit_recorder_factory

    async def list_tenant_roles(
        self,
        *,
        tenant_id: UUID,
    ) -> tuple[RoleCatalogRecord, ...]:
        async with self._session_factory() as session:
            configure_tenant_database_access(session, tenant_id)
            async with session.begin():
                rows = (
                    await session.execute(
                        select(Role, Permission.code)
                        .outerjoin(RolePermission, RolePermission.role_id == Role.id)
                        .outerjoin(Permission, Permission.id == RolePermission.permission_id)
                        .where(Role.scope_type == "tenant")
                        .order_by(Role.code, Permission.code)
                    )
                ).all()
        return _role_catalog_records(rows)

    async def list_tenant_permissions(
        self,
        *,
        tenant_id: UUID,
    ) -> tuple[PermissionCatalogRecord, ...]:
        async with self._session_factory() as session:
            configure_tenant_database_access(session, tenant_id)
            async with session.begin():
                permissions = tuple(
                    await session.scalars(
                        select(Permission)
                        .where(Permission.target != "platform")
                        .order_by(Permission.code)
                    )
                )
        return tuple(
            PermissionCatalogRecord(
                id=permission.id,
                code=permission.code,
                resource=permission.resource,
                action=permission.action,
                scope=permission.target,
                description=permission.description,
            )
            for permission in permissions
        )

    async def replace_user_roles(
        self,
        *,
        tenant_id: UUID,
        actor_id: UUID,
        user_id: UUID,
        role_ids: tuple[UUID, ...],
        actor_session_id: UUID | None = None,
        audit_context: AuditContext | None = None,
    ) -> RoleReplacementRecord:
        context = audit_context or AuditContext.internal()
        desired_ids = frozenset(role_ids)
        async with self._session_factory() as session:
            configure_tenant_database_access(session, tenant_id)
            unit_of_work = SqlAlchemyUnitOfWork(session)

            async def operation() -> RoleReplacementRecord:
                user = await session.scalar(
                    select(User)
                    .where(User.tenant_id == tenant_id, User.id == user_id)
                    .with_for_update()
                )
                if user is None:
                    raise RoleAssignmentUserNotFoundError()

                roles = (
                    tuple(
                        await session.scalars(
                            select(Role)
                            .where(Role.id.in_(desired_ids), Role.scope_type == "tenant")
                            .order_by(Role.code)
                        )
                    )
                    if desired_ids
                    else ()
                )
                if {role.id for role in roles} != desired_ids:
                    raise RoleAssignmentInvalidError()
                if user_id == actor_id and not any(role.code == "tenant_admin" for role in roles):
                    raise RoleAssignmentConflictError(
                        "The authenticated administrator cannot remove their own tenant-admin role"
                    )

                assignments = tuple(
                    await session.scalars(
                        select(UserRole)
                        .where(
                            UserRole.tenant_id == tenant_id,
                            UserRole.user_id == user_id,
                        )
                        .with_for_update()
                    )
                )
                before_snapshot = await load_authorization_snapshot(
                    session,
                    tenant_id=tenant_id,
                    user_id=user_id,
                )
                current_ids = {
                    assignment.role_id for assignment in assignments if assignment.active
                }
                roles_changed = current_ids != desired_ids
                if roles_changed:
                    by_role_id = {assignment.role_id: assignment for assignment in assignments}
                    for assignment in assignments:
                        assignment.active = assignment.role_id in desired_ids
                    for role in roles:
                        if role.id not in by_role_id:
                            session.add(
                                UserRole(
                                    tenant_id=tenant_id,
                                    user_id=user_id,
                                    role_id=role.id,
                                    role_scope_type="tenant",
                                    active=True,
                                )
                            )
                    user.permission_version += 1
                    user.updated_at = datetime.now(UTC)
                    await session.flush()
                    await session.refresh(user)
                    await sync_existing_membership_projection(session, user)

                snapshot = await load_authorization_snapshot(
                    session,
                    tenant_id=tenant_id,
                    user_id=user_id,
                )
                if roles_changed:
                    await self._audit_recorder_factory(session).record(
                        AuditEventDraft(
                            scope_type=AuditScopeType.TENANT,
                            tenant_id=tenant_id,
                            actor_type=AuditActorType.USER,
                            actor_user_id=actor_id,
                            event_type=AuditEventType.ROLES_REPLACED,
                            category=AuditCategory.TENANT_ADMIN,
                            resource_type="user",
                            resource_id=user_id,
                            action="replace_roles",
                            result=AuditResult.SUCCESS,
                            context=context,
                            session_id=actor_session_id,
                            changed_fields=("roles", "permission_version"),
                            metadata={
                                "before_role_codes": tuple(
                                    role.code for role in before_snapshot.roles
                                ),
                                "after_role_codes": tuple(role.code for role in snapshot.roles),
                                "permission_version": user.permission_version,
                            },
                            data_classification=AuditDataClassification.TENANT_ADMINISTRATION,
                            visibility_class=AuditVisibilityClass.TENANT_ADMIN,
                        )
                    )
                return RoleReplacementRecord(
                    id=user.id,
                    email=user.email,
                    full_name=user.full_name,
                    status=user.status,
                    roles=snapshot.roles,
                    permission_version=user.permission_version,
                    created_at=user.created_at,  # type: ignore[arg-type]
                    updated_at=user.updated_at,  # type: ignore[arg-type]
                )

            return await unit_of_work.execute(operation)


async def seed_authorization_catalog(session: AsyncSession) -> None:
    """Idempotently seed the immutable catalog for local/create-all bootstrap paths."""

    for definition in ROLES:
        role = await session.get(Role, definition.id)
        if role is None:
            session.add(
                Role(
                    id=definition.id,
                    code=definition.code,
                    name=definition.name,
                    description=definition.description,
                    scope_type=definition.scope_type.value,
                    system_role=True,
                )
            )
    for definition in PERMISSIONS:
        permission = await session.get(Permission, definition.id)
        if permission is None:
            session.add(
                Permission(
                    id=definition.id,
                    code=definition.code,
                    resource=definition.name.resource,
                    action=definition.name.action,
                    target=definition.name.target,
                    target_type=definition.name.target_type.value,
                    description=definition.description,
                )
            )
    await session.flush()

    existing_pairs = set(
        (await session.execute(select(RolePermission.role_id, RolePermission.permission_id))).all()
    )
    for role_code, permission_codes in ROLE_PERMISSION_CODES.items():
        role_id = ROLES_BY_CODE[role_code].id
        for permission_code in permission_codes:
            pair = (role_id, PERMISSIONS_BY_CODE[permission_code].id)
            if pair not in existing_pairs:
                session.add(RolePermission(role_id=pair[0], permission_id=pair[1]))
    await session.flush()


async def assign_system_role(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    user_id: UUID,
    role_code: str,
) -> None:
    definition = ROLES_BY_CODE.get(role_code)
    if definition is None or definition.scope_type.value != "tenant":
        raise ValueError("Only a known tenant role can be assigned to a tenant user")
    assignment = await session.get(UserRole, (tenant_id, user_id, definition.id))
    if assignment is None:
        session.add(
            UserRole(
                tenant_id=tenant_id,
                user_id=user_id,
                role_id=definition.id,
                role_scope_type="tenant",
                active=True,
            )
        )
    else:
        assignment.active = True
    await session.flush()


def _role_catalog_records(rows: list[object]) -> tuple[RoleCatalogRecord, ...]:
    grouped: dict[UUID, tuple[Role, list[str]]] = {}
    for row in rows:
        role, permission_code = row
        if role.id not in grouped:
            grouped[role.id] = (role, [])
        if permission_code is not None:
            grouped[role.id][1].append(permission_code)
    return tuple(
        RoleCatalogRecord(
            id=role.id,
            code=role.code,
            name=role.name,
            description=role.description,
            scope_type=role.scope_type,
            permissions=tuple(permission_codes),
        )
        for role, permission_codes in grouped.values()
    )


__all__ = [
    "AssignedRole",
    "AuthorizationAccessDeniedError",
    "AuthorizationService",
    "AuthorizationSnapshot",
    "PermissionCatalogRecord",
    "RoleAssignmentConflictError",
    "RoleAssignmentInvalidError",
    "RoleAssignmentUserNotFoundError",
    "RoleCatalogRecord",
    "RoleReplacementRecord",
    "assign_system_role",
    "load_assigned_roles",
    "load_authorization_snapshot",
    "seed_authorization_catalog",
]
