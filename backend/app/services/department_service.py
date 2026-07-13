"""Bounded department hierarchy reads and audited tenant commands."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import and_, exists, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import aliased

from app.models.department import Department, DepartmentStatus
from app.platform.audit import (
    AuditActorType,
    AuditCategory,
    AuditContext,
    AuditDataClassification,
    AuditEventDraft,
    AuditEventType,
    AuditRecorder,
    AuditScopeType,
    AuditVisibilityClass,
)
from app.platform.db import (
    SqlAlchemyUnitOfWork,
    configure_tenant_database_access,
    constraint_name_from_error,
)
from app.platform.errors.application import ApplicationError
from app.platform.pagination import CursorPage
from app.platform.request_context import RequestContext
from app.schemas.department import (
    DepartmentCreate,
    DepartmentListPagination,
    DepartmentTreePagination,
    DepartmentUpdate,
)
from app.services.audit_recorder import SqlAlchemyAuditRecorder
from app.services.organization_access import (
    ORGANIZATION_READ_PERMISSION,
    ORGANIZATION_UPDATE_PERMISSION,
    organization_scope_from_context,
    require_organization_permission,
    require_organization_tenant_access,
)

DEPARTMENT_CODE_UNIQUE_CONSTRAINT = "uq_departments_tenant_code_normalized"
DEPARTMENT_PARENT_FOREIGN_KEY = "fk_departments_tenant_parent_id_departments"
DEPARTMENT_CYCLE_CONSTRAINTS = frozenset(
    {"ck_departments_acyclic", "ck_departments_parent_not_self"}
)
DEPARTMENT_ACTIVE_PARENT_CONSTRAINT = "ck_departments_active_parent"
DEPARTMENT_ACTIVE_CHILDREN_CONSTRAINT = "ck_departments_no_active_children"
DEPARTMENT_ARCHIVED_TERMINAL_CONSTRAINT = "ck_departments_archived_terminal"


class DepartmentNotFoundError(ApplicationError):
    pass


class DuplicateDepartmentCodeError(ApplicationError):
    pass


class DepartmentConflictError(ApplicationError):
    pass


class DepartmentCycleError(DepartmentConflictError):
    pass


class DepartmentLifecycleConflictError(DepartmentConflictError):
    pass


@dataclass(frozen=True, slots=True)
class DepartmentView:
    department: Department
    has_children: bool


class DepartmentService:
    """Manage one tenant's adjacency list without ever materializing the full tree."""

    def __init__(
        self,
        *,
        session_factory: async_sessionmaker[AsyncSession],
        audit_recorder_factory: Callable[[AsyncSession], AuditRecorder] = (SqlAlchemyAuditRecorder),
    ) -> None:
        self._session_factory = session_factory
        self._audit_recorder_factory = audit_recorder_factory

    async def list_departments(
        self,
        *,
        request_context: RequestContext,
        pagination: DepartmentListPagination,
        granted_permissions: tuple[str, ...],
    ) -> CursorPage[DepartmentView]:
        tenant_id, _actor_id = organization_scope_from_context(request_context)
        require_organization_permission(
            granted_permissions,
            ORGANIZATION_READ_PERMISSION,
        )
        async with self._session_factory() as session:
            configure_tenant_database_access(session, tenant_id)
            async with session.begin():
                await require_organization_tenant_access(
                    session,
                    tenant_id,
                    write=False,
                )
                statement = _department_view_statement(
                    tenant_id=tenant_id,
                    active_children_only=False,
                )
                if pagination.status is not None:
                    statement = statement.where(Department.status == pagination.status.value)
                if pagination.cursor is not None:
                    statement = statement.where(
                        _after_cursor(
                            code=pagination.cursor.code,
                            department_id=pagination.cursor.id,
                        )
                    )
                rows = list(
                    (
                        await session.execute(
                            statement.order_by(
                                Department.code_normalized.asc(),
                                Department.id.asc(),
                            ).limit(pagination.limit + 1)
                        )
                    ).all()
                )
        views = [_view_from_row(row) for row in rows[: pagination.limit]]
        next_cursor = None
        if len(rows) > pagination.limit:
            last = views[-1].department
            next_cursor = pagination.next_cursor(
                code=last.code_normalized,
                department_id=last.id,
            )
        return CursorPage(items=views, next_cursor=next_cursor)

    async def list_tree_level(
        self,
        *,
        request_context: RequestContext,
        pagination: DepartmentTreePagination,
        granted_permissions: tuple[str, ...],
    ) -> CursorPage[DepartmentView]:
        tenant_id, _actor_id = organization_scope_from_context(request_context)
        require_organization_permission(
            granted_permissions,
            ORGANIZATION_READ_PERMISSION,
        )
        async with self._session_factory() as session:
            configure_tenant_database_access(session, tenant_id)
            async with session.begin():
                await require_organization_tenant_access(
                    session,
                    tenant_id,
                    write=False,
                )
                if (
                    pagination.parent_id is not None
                    and await _department(
                        session,
                        tenant_id=tenant_id,
                        department_id=pagination.parent_id,
                    )
                    is None
                ):
                    raise DepartmentNotFoundError()

                statement = _department_view_statement(
                    tenant_id=tenant_id,
                    active_children_only=not pagination.include_archived,
                )
                if pagination.parent_id is None:
                    statement = statement.where(Department.parent_id.is_(None))
                else:
                    statement = statement.where(Department.parent_id == pagination.parent_id)
                if not pagination.include_archived:
                    statement = statement.where(Department.status == DepartmentStatus.ACTIVE.value)
                if pagination.cursor is not None:
                    statement = statement.where(
                        _after_cursor(
                            code=pagination.cursor.code,
                            department_id=pagination.cursor.id,
                        )
                    )
                rows = list(
                    (
                        await session.execute(
                            statement.order_by(
                                Department.code_normalized.asc(),
                                Department.id.asc(),
                            ).limit(pagination.limit + 1)
                        )
                    ).all()
                )
        views = [_view_from_row(row) for row in rows[: pagination.limit]]
        next_cursor = None
        if len(rows) > pagination.limit:
            last = views[-1].department
            next_cursor = pagination.next_cursor(
                code=last.code_normalized,
                department_id=last.id,
            )
        return CursorPage(items=views, next_cursor=next_cursor)

    async def get_department(
        self,
        *,
        request_context: RequestContext,
        department_id: UUID,
        granted_permissions: tuple[str, ...],
    ) -> DepartmentView:
        tenant_id, _actor_id = organization_scope_from_context(request_context)
        require_organization_permission(
            granted_permissions,
            ORGANIZATION_READ_PERMISSION,
        )
        async with self._session_factory() as session:
            configure_tenant_database_access(session, tenant_id)
            async with session.begin():
                await require_organization_tenant_access(
                    session,
                    tenant_id,
                    write=False,
                )
                view = await _department_view(
                    session,
                    tenant_id=tenant_id,
                    department_id=department_id,
                    active_children_only=False,
                )
        if view is None:
            raise DepartmentNotFoundError()
        return view

    async def require_assignable_department(
        self,
        *,
        request_context: RequestContext,
        department_id: UUID,
        granted_permissions: tuple[str, ...],
    ) -> Department:
        """Resolve an active department for a future new-assignment command."""

        tenant_id, _actor_id = organization_scope_from_context(request_context)
        require_organization_permission(
            granted_permissions,
            ORGANIZATION_READ_PERMISSION,
        )
        async with self._session_factory() as session:
            configure_tenant_database_access(session, tenant_id)
            async with session.begin():
                await require_organization_tenant_access(
                    session,
                    tenant_id,
                    write=False,
                )
                department = await _department(
                    session,
                    tenant_id=tenant_id,
                    department_id=department_id,
                )
        if department is None:
            raise DepartmentNotFoundError()
        if department.status != DepartmentStatus.ACTIVE.value or department.archived_at is not None:
            raise DepartmentLifecycleConflictError(
                "Archived departments cannot accept new assignments"
            )
        return department

    async def create_department(
        self,
        *,
        request_context: RequestContext,
        payload: DepartmentCreate,
        granted_permissions: tuple[str, ...],
        audit_context: AuditContext | None = None,
    ) -> DepartmentView:
        tenant_id, actor_id = organization_scope_from_context(request_context)
        require_organization_permission(
            granted_permissions,
            ORGANIZATION_UPDATE_PERMISSION,
        )
        async with self._session_factory() as session:
            configure_tenant_database_access(session, tenant_id)
            unit_of_work = SqlAlchemyUnitOfWork(session)

            async def operation() -> DepartmentView:
                await require_organization_tenant_access(
                    session,
                    tenant_id,
                    write=True,
                )
                await _require_code_available(
                    session,
                    tenant_id=tenant_id,
                    code=payload.code,
                )
                if payload.parent_id is not None:
                    await _require_active_parent(
                        session,
                        tenant_id=tenant_id,
                        parent_id=payload.parent_id,
                    )
                department = Department(
                    id=uuid4(),
                    tenant_id=tenant_id,
                    parent_id=payload.parent_id,
                    code=payload.code,
                    name=payload.name,
                    status=DepartmentStatus.ACTIVE.value,
                    archived_at=None,
                )
                session.add(department)
                await _flush_department_write(session)
                await session.refresh(department)
                await self._record_event(
                    session,
                    request_context=request_context,
                    audit_context=audit_context,
                    actor_id=actor_id,
                    event_type=AuditEventType.DEPARTMENT_CREATED,
                    resource_id=department.id,
                    action="create",
                    changed_fields=("parent_id", "code", "name", "status"),
                )
                return DepartmentView(department=department, has_children=False)

            return await unit_of_work.execute(operation)

    async def update_department(
        self,
        *,
        request_context: RequestContext,
        department_id: UUID,
        payload: DepartmentUpdate,
        granted_permissions: tuple[str, ...],
        audit_context: AuditContext | None = None,
    ) -> DepartmentView:
        tenant_id, actor_id = organization_scope_from_context(request_context)
        require_organization_permission(
            granted_permissions,
            ORGANIZATION_UPDATE_PERMISSION,
        )
        async with self._session_factory() as session:
            configure_tenant_database_access(session, tenant_id)
            unit_of_work = SqlAlchemyUnitOfWork(session)

            async def operation() -> DepartmentView:
                await require_organization_tenant_access(
                    session,
                    tenant_id,
                    write=True,
                )
                department = await _department(
                    session,
                    tenant_id=tenant_id,
                    department_id=department_id,
                    for_update=True,
                )
                if department is None:
                    raise DepartmentNotFoundError()
                if department.status == DepartmentStatus.ARCHIVED.value:
                    raise DepartmentLifecycleConflictError(
                        "Archived departments are historical and cannot be updated"
                    )

                changed_fields: list[str] = []
                if "name" in payload.model_fields_set and payload.name != department.name:
                    department.name = payload.name
                    changed_fields.append("name")
                if (
                    "parent_id" in payload.model_fields_set
                    and payload.parent_id != department.parent_id
                ):
                    if payload.parent_id is not None:
                        await _require_active_parent(
                            session,
                            tenant_id=tenant_id,
                            parent_id=payload.parent_id,
                        )
                        if await _would_create_cycle(
                            session,
                            tenant_id=tenant_id,
                            department_id=department.id,
                            parent_id=payload.parent_id,
                        ):
                            raise DepartmentCycleError(
                                "A department cannot be moved beneath itself or its descendants"
                            )
                    department.parent_id = payload.parent_id
                    changed_fields.append("parent_id")

                if changed_fields:
                    department.updated_at = datetime.now(UTC)
                    await _flush_department_write(session)
                    await session.refresh(department)
                    await self._record_event(
                        session,
                        request_context=request_context,
                        audit_context=audit_context,
                        actor_id=actor_id,
                        event_type=AuditEventType.DEPARTMENT_UPDATED,
                        resource_id=department.id,
                        action="update",
                        changed_fields=tuple(sorted(changed_fields)),
                    )
                return DepartmentView(
                    department=department,
                    has_children=await _has_children(
                        session,
                        tenant_id=tenant_id,
                        department_id=department.id,
                        active_only=False,
                    ),
                )

            return await unit_of_work.execute(operation)

    async def archive_department(
        self,
        *,
        request_context: RequestContext,
        department_id: UUID,
        granted_permissions: tuple[str, ...],
        audit_context: AuditContext | None = None,
    ) -> DepartmentView:
        tenant_id, actor_id = organization_scope_from_context(request_context)
        require_organization_permission(
            granted_permissions,
            ORGANIZATION_UPDATE_PERMISSION,
        )
        async with self._session_factory() as session:
            configure_tenant_database_access(session, tenant_id)
            unit_of_work = SqlAlchemyUnitOfWork(session)

            async def operation() -> DepartmentView:
                await require_organization_tenant_access(
                    session,
                    tenant_id,
                    write=True,
                )
                department = await _department(
                    session,
                    tenant_id=tenant_id,
                    department_id=department_id,
                    for_update=True,
                )
                if department is None:
                    raise DepartmentNotFoundError()
                has_children = await _has_children(
                    session,
                    tenant_id=tenant_id,
                    department_id=department.id,
                    active_only=False,
                )
                if department.status == DepartmentStatus.ARCHIVED.value:
                    return DepartmentView(
                        department=department,
                        has_children=has_children,
                    )
                if await _has_children(
                    session,
                    tenant_id=tenant_id,
                    department_id=department.id,
                    active_only=True,
                ):
                    raise DepartmentLifecycleConflictError(
                        "A department with active children cannot be archived"
                    )

                department.status = DepartmentStatus.ARCHIVED.value
                department.archived_at = datetime.now(UTC)
                department.updated_at = department.archived_at
                await _flush_department_write(session)
                await session.refresh(department)
                await self._record_event(
                    session,
                    request_context=request_context,
                    audit_context=audit_context,
                    actor_id=actor_id,
                    event_type=AuditEventType.DEPARTMENT_ARCHIVED,
                    resource_id=department.id,
                    action="archive",
                    changed_fields=("status", "archived_at"),
                    metadata={
                        "before_status": DepartmentStatus.ACTIVE.value,
                        "after_status": DepartmentStatus.ARCHIVED.value,
                    },
                )
                return DepartmentView(
                    department=department,
                    has_children=has_children,
                )

            return await unit_of_work.execute(operation)

    async def _record_event(
        self,
        session: AsyncSession,
        *,
        request_context: RequestContext,
        audit_context: AuditContext | None,
        actor_id: UUID,
        event_type: AuditEventType,
        resource_id: UUID,
        action: str,
        changed_fields: tuple[str, ...],
        metadata: dict[str, object] | None = None,
    ) -> None:
        await self._audit_recorder_factory(session).record(
            AuditEventDraft(
                scope_type=AuditScopeType.TENANT,
                tenant_id=request_context.require_tenant().tenant_id,
                actor_type=AuditActorType.USER,
                actor_user_id=actor_id,
                event_type=event_type,
                category=AuditCategory.HR_OPERATIONS,
                resource_type="department",
                resource_id=resource_id,
                action=action,
                context=audit_context or AuditContext.from_request_context(request_context),
                session_id=request_context.session_id,
                changed_fields=changed_fields,
                metadata=metadata or {},
                data_classification=AuditDataClassification.HR_METADATA,
                visibility_class=AuditVisibilityClass.HR_OPERATIONS,
            )
        )


def _department_view_statement(
    *,
    tenant_id: UUID,
    active_children_only: bool,
):
    child = aliased(Department)
    child_predicates = [
        child.tenant_id == Department.tenant_id,
        child.parent_id == Department.id,
    ]
    if active_children_only:
        child_predicates.append(child.status == DepartmentStatus.ACTIVE.value)
    has_children = exists().where(*child_predicates).label("has_children")
    return select(Department, has_children).where(Department.tenant_id == tenant_id)


async def _department_view(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    department_id: UUID,
    active_children_only: bool,
) -> DepartmentView | None:
    row = (
        await session.execute(
            _department_view_statement(
                tenant_id=tenant_id,
                active_children_only=active_children_only,
            ).where(Department.id == department_id)
        )
    ).one_or_none()
    return _view_from_row(row) if row is not None else None


def _view_from_row(row: object) -> DepartmentView:
    department, has_children = row
    return DepartmentView(
        department=department,
        has_children=bool(has_children),
    )


def _after_cursor(*, code: str, department_id: UUID):
    return or_(
        Department.code_normalized > code,
        and_(
            Department.code_normalized == code,
            Department.id > department_id,
        ),
    )


async def _department(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    department_id: UUID,
    for_update: bool = False,
) -> Department | None:
    statement = select(Department).where(
        Department.tenant_id == tenant_id,
        Department.id == department_id,
    )
    if for_update:
        statement = statement.with_for_update()
    return await session.scalar(statement)


async def _require_active_parent(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    parent_id: UUID,
) -> Department:
    parent = await _department(
        session,
        tenant_id=tenant_id,
        department_id=parent_id,
    )
    if parent is None:
        raise DepartmentNotFoundError()
    if parent.status != DepartmentStatus.ACTIVE.value:
        raise DepartmentLifecycleConflictError(
            "Active departments can only be placed under an active parent"
        )
    return parent


async def _would_create_cycle(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    department_id: UUID,
    parent_id: UUID,
) -> bool:
    if parent_id == department_id:
        return True

    ancestors = (
        select(
            Department.id.label("id"),
            Department.parent_id.label("parent_id"),
        )
        .where(
            Department.tenant_id == tenant_id,
            Department.id == parent_id,
        )
        .cte("department_ancestors", recursive=True)
    )
    ancestor_department = aliased(Department)
    ancestors = ancestors.union(
        select(
            ancestor_department.id,
            ancestor_department.parent_id,
        ).where(
            ancestor_department.tenant_id == tenant_id,
            ancestor_department.id == ancestors.c.parent_id,
        )
    )
    return bool(await session.scalar(select(exists().where(ancestors.c.id == department_id))))


async def _has_children(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    department_id: UUID,
    active_only: bool,
) -> bool:
    predicates = [
        Department.tenant_id == tenant_id,
        Department.parent_id == department_id,
    ]
    if active_only:
        predicates.append(Department.status == DepartmentStatus.ACTIVE.value)
    return bool(await session.scalar(select(exists().where(*predicates))))


async def _require_code_available(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    code: str,
) -> None:
    if await session.scalar(
        select(Department.id).where(
            Department.tenant_id == tenant_id,
            Department.code_normalized == code.strip().lower(),
        )
    ):
        raise DuplicateDepartmentCodeError()


async def _flush_department_write(session: AsyncSession) -> None:
    try:
        await session.flush()
    except IntegrityError as exc:
        constraint_name = constraint_name_from_error(exc)
        error_text = str(exc.orig)
        if (
            constraint_name == DEPARTMENT_CODE_UNIQUE_CONSTRAINT
            or "departments.tenant_id, departments.code_normalized" in error_text
        ):
            raise DuplicateDepartmentCodeError() from exc
        if constraint_name in DEPARTMENT_CYCLE_CONSTRAINTS:
            raise DepartmentCycleError(
                "A department cannot be moved beneath itself or its descendants"
            ) from exc
        if constraint_name == DEPARTMENT_ACTIVE_PARENT_CONSTRAINT:
            raise DepartmentLifecycleConflictError(
                "Active departments can only be placed under an active parent"
            ) from exc
        if constraint_name == DEPARTMENT_ACTIVE_CHILDREN_CONSTRAINT:
            raise DepartmentLifecycleConflictError(
                "A department with active children cannot be archived"
            ) from exc
        if constraint_name == DEPARTMENT_ARCHIVED_TERMINAL_CONSTRAINT:
            raise DepartmentLifecycleConflictError(
                "Archived departments are historical and cannot be updated"
            ) from exc
        if (
            constraint_name == DEPARTMENT_PARENT_FOREIGN_KEY
            or "departments" in error_text
            and "FOREIGN KEY" in error_text.upper()
        ):
            raise DepartmentNotFoundError() from exc
        raise


__all__ = [
    "DEPARTMENT_ACTIVE_CHILDREN_CONSTRAINT",
    "DEPARTMENT_ACTIVE_PARENT_CONSTRAINT",
    "DEPARTMENT_ARCHIVED_TERMINAL_CONSTRAINT",
    "DEPARTMENT_CODE_UNIQUE_CONSTRAINT",
    "DEPARTMENT_CYCLE_CONSTRAINTS",
    "DEPARTMENT_PARENT_FOREIGN_KEY",
    "DepartmentConflictError",
    "DepartmentCycleError",
    "DepartmentLifecycleConflictError",
    "DepartmentNotFoundError",
    "DepartmentService",
    "DepartmentView",
    "DuplicateDepartmentCodeError",
]
