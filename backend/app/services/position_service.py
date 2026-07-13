"""Bounded position-catalog reads and audited tenant commands."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import and_, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.position import Position, PositionStatus
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
from app.schemas.position import (
    PositionCreate,
    PositionListPagination,
    PositionUpdate,
    position_search_uses_exact_code,
)
from app.services.audit_recorder import SqlAlchemyAuditRecorder
from app.services.organization_access import (
    ORGANIZATION_READ_PERMISSION,
    ORGANIZATION_UPDATE_PERMISSION,
    organization_scope_from_context,
    require_organization_permission,
    require_organization_tenant_access,
)

POSITION_CODE_UNIQUE_CONSTRAINT = "uq_positions_tenant_code_normalized"


class PositionNotFoundError(ApplicationError):
    pass


class DuplicatePositionCodeError(ApplicationError):
    pass


class PositionConflictError(ApplicationError):
    pass


class PositionLifecycleConflictError(PositionConflictError):
    pass


class PositionService:
    """Manage one tenant's reusable position titles without assignment-planning scope."""

    def __init__(
        self,
        *,
        session_factory: async_sessionmaker[AsyncSession],
        audit_recorder_factory: Callable[[AsyncSession], AuditRecorder] = (SqlAlchemyAuditRecorder),
    ) -> None:
        self._session_factory = session_factory
        self._audit_recorder_factory = audit_recorder_factory

    async def list_positions(
        self,
        *,
        request_context: RequestContext,
        pagination: PositionListPagination,
        granted_permissions: tuple[str, ...],
    ) -> CursorPage[Position]:
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
                statement = select(Position).where(Position.tenant_id == tenant_id)
                if pagination.status is not None:
                    statement = statement.where(Position.status == pagination.status.value)
                if pagination.search is not None:
                    statement = statement.where(
                        _position_search_predicate(pagination.search)
                    )
                if pagination.cursor is not None:
                    statement = statement.where(
                        _after_cursor(
                            code=pagination.cursor.code,
                            position_id=pagination.cursor.id,
                        )
                    )
                rows = list(
                    await session.scalars(
                        statement.order_by(
                            Position.code_normalized.asc(),
                            Position.id.asc(),
                        ).limit(pagination.limit + 1)
                    )
                )
        items = rows[: pagination.limit]
        next_cursor = None
        if len(rows) > pagination.limit:
            last = items[-1]
            next_cursor = pagination.next_cursor(
                code=last.code_normalized,
                position_id=last.id,
            )
        return CursorPage(items=items, next_cursor=next_cursor)

    async def get_position(
        self,
        *,
        request_context: RequestContext,
        position_id: UUID,
        granted_permissions: tuple[str, ...],
    ) -> Position:
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
                position = await _position(
                    session,
                    tenant_id=tenant_id,
                    position_id=position_id,
                )
        if position is None:
            raise PositionNotFoundError()
        return position

    async def require_assignable_position(
        self,
        *,
        request_context: RequestContext,
        position_id: UUID,
        granted_permissions: tuple[str, ...],
    ) -> Position:
        """Resolve an active position for a future new-assignment command."""

        position = await self.get_position(
            request_context=request_context,
            position_id=position_id,
            granted_permissions=granted_permissions,
        )
        if position.status != PositionStatus.ACTIVE.value or position.archived_at is not None:
            raise PositionLifecycleConflictError("Archived positions cannot accept new assignments")
        return position

    async def create_position(
        self,
        *,
        request_context: RequestContext,
        payload: PositionCreate,
        granted_permissions: tuple[str, ...],
        audit_context: AuditContext | None = None,
    ) -> Position:
        tenant_id, actor_id = organization_scope_from_context(request_context)
        require_organization_permission(
            granted_permissions,
            ORGANIZATION_UPDATE_PERMISSION,
        )
        async with self._session_factory() as session:
            configure_tenant_database_access(session, tenant_id)
            unit_of_work = SqlAlchemyUnitOfWork(session)

            async def operation() -> Position:
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
                position = Position(
                    id=uuid4(),
                    tenant_id=tenant_id,
                    code=payload.code,
                    title=payload.title,
                    status=PositionStatus.ACTIVE.value,
                    archived_at=None,
                )
                session.add(position)
                await _flush_position_write(session)
                await session.refresh(position)
                await self._record_event(
                    session,
                    request_context=request_context,
                    audit_context=audit_context,
                    actor_id=actor_id,
                    event_type=AuditEventType.POSITION_CREATED,
                    resource_id=position.id,
                    action="create",
                    changed_fields=("code", "title", "status"),
                )
                return position

            return await unit_of_work.execute(operation)

    async def update_position(
        self,
        *,
        request_context: RequestContext,
        position_id: UUID,
        payload: PositionUpdate,
        granted_permissions: tuple[str, ...],
        audit_context: AuditContext | None = None,
    ) -> Position:
        tenant_id, actor_id = organization_scope_from_context(request_context)
        require_organization_permission(
            granted_permissions,
            ORGANIZATION_UPDATE_PERMISSION,
        )
        async with self._session_factory() as session:
            configure_tenant_database_access(session, tenant_id)
            unit_of_work = SqlAlchemyUnitOfWork(session)

            async def operation() -> Position:
                await require_organization_tenant_access(
                    session,
                    tenant_id,
                    write=True,
                )
                position = await _position(
                    session,
                    tenant_id=tenant_id,
                    position_id=position_id,
                    for_update=True,
                )
                if position is None:
                    raise PositionNotFoundError()
                if position.status == PositionStatus.ARCHIVED.value:
                    raise PositionLifecycleConflictError(
                        "Archived positions are historical and cannot be updated"
                    )

                if "title" in payload.model_fields_set and payload.title != position.title:
                    position.title = payload.title
                    position.updated_at = datetime.now(UTC)
                    await _flush_position_write(session)
                    await session.refresh(position)
                    await self._record_event(
                        session,
                        request_context=request_context,
                        audit_context=audit_context,
                        actor_id=actor_id,
                        event_type=AuditEventType.POSITION_UPDATED,
                        resource_id=position.id,
                        action="update",
                        changed_fields=("title",),
                    )
                return position

            return await unit_of_work.execute(operation)

    async def archive_position(
        self,
        *,
        request_context: RequestContext,
        position_id: UUID,
        granted_permissions: tuple[str, ...],
        audit_context: AuditContext | None = None,
    ) -> Position:
        tenant_id, actor_id = organization_scope_from_context(request_context)
        require_organization_permission(
            granted_permissions,
            ORGANIZATION_UPDATE_PERMISSION,
        )
        async with self._session_factory() as session:
            configure_tenant_database_access(session, tenant_id)
            unit_of_work = SqlAlchemyUnitOfWork(session)

            async def operation() -> Position:
                await require_organization_tenant_access(
                    session,
                    tenant_id,
                    write=True,
                )
                position = await _position(
                    session,
                    tenant_id=tenant_id,
                    position_id=position_id,
                    for_update=True,
                )
                if position is None:
                    raise PositionNotFoundError()
                if position.status == PositionStatus.ARCHIVED.value:
                    return position

                position.status = PositionStatus.ARCHIVED.value
                position.archived_at = datetime.now(UTC)
                position.updated_at = position.archived_at
                await _flush_position_write(session)
                await session.refresh(position)
                await self._record_event(
                    session,
                    request_context=request_context,
                    audit_context=audit_context,
                    actor_id=actor_id,
                    event_type=AuditEventType.POSITION_ARCHIVED,
                    resource_id=position.id,
                    action="archive",
                    changed_fields=("status", "archived_at"),
                    metadata={
                        "before_status": PositionStatus.ACTIVE.value,
                        "after_status": PositionStatus.ARCHIVED.value,
                    },
                )
                return position

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
                resource_type="position",
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


async def _position(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    position_id: UUID,
    for_update: bool = False,
) -> Position | None:
    statement = select(Position).where(
        Position.tenant_id == tenant_id,
        Position.id == position_id,
    )
    if for_update:
        statement = statement.with_for_update()
    return await session.scalar(statement)


async def _require_code_available(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    code: str,
) -> None:
    if await session.scalar(
        select(Position.id).where(
            Position.tenant_id == tenant_id,
            Position.code_normalized == func.lower(code),
        )
    ):
        raise DuplicatePositionCodeError()


async def _flush_position_write(session: AsyncSession) -> None:
    try:
        await session.flush()
    except IntegrityError as exc:
        constraint_name = constraint_name_from_error(exc)
        if (
            constraint_name == POSITION_CODE_UNIQUE_CONSTRAINT
            or "positions.tenant_id, positions.code_normalized" in str(exc.orig)
        ):
            raise DuplicatePositionCodeError() from exc
        raise


def _after_cursor(*, code: str, position_id: UUID):
    return or_(
        Position.code_normalized > code,
        and_(
            Position.code_normalized == code,
            Position.id > position_id,
        ),
    )


def _literal_contains_pattern(value: str) -> str:
    escaped = value.replace("/", "//").replace("%", "/%").replace("_", "/_")
    return f"%{escaped}%"


def _position_search_predicate(value: str):
    if position_search_uses_exact_code(value):
        return Position.code_normalized == func.lower(value.upper())

    code_pattern = _literal_contains_pattern(value.upper())
    title_pattern = _literal_contains_pattern(value)
    return or_(
        Position.code_normalized.like(
            func.lower(code_pattern),
            escape="/",
        ),
        Position.title_normalized.like(
            func.lower(title_pattern),
            escape="/",
        ),
    )


__all__ = [
    "POSITION_CODE_UNIQUE_CONSTRAINT",
    "DuplicatePositionCodeError",
    "PositionConflictError",
    "PositionLifecycleConflictError",
    "PositionNotFoundError",
    "PositionService",
]
