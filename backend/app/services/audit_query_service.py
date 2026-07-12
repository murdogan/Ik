"""Cursor-based, scope-separated audit read service."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.audit import AuditEvent
from app.platform.audit import AuditCategory, AuditScopeType
from app.platform.db import configure_platform_database_access, configure_tenant_database_access
from app.platform.errors.application import ApplicationError
from app.platform.pagination import CursorPage
from app.schemas.audit import AuditListPagination


class AuditAccessDeniedError(ApplicationError):
    pass


class AuditEventNotFoundError(ApplicationError):
    pass


_TENANT_CATEGORY_VISIBILITY: dict[str, frozenset[AuditCategory]] = {
    "tenant_admin": frozenset(
        {AuditCategory.TENANT_ADMIN, AuditCategory.TENANT_SECURITY}
    ),
    "it_admin": frozenset({AuditCategory.TENANT_SECURITY}),
    "auditor": frozenset(
        {
            AuditCategory.TENANT_ADMIN,
            AuditCategory.TENANT_SECURITY,
            AuditCategory.HR_OPERATIONS,
        }
    ),
    "hr_director": frozenset({AuditCategory.HR_OPERATIONS}),
}


class AuditQueryService:
    def __init__(self, *, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def list_tenant_events(
        self,
        *,
        tenant_id: UUID,
        role_codes: tuple[str, ...],
        pagination: AuditListPagination,
    ) -> CursorPage[AuditEvent]:
        if pagination.scope_type is not AuditScopeType.TENANT:
            raise AuditAccessDeniedError()
        categories = _visible_tenant_categories(role_codes)
        async with self._session_factory() as session:
            configure_tenant_database_access(session, tenant_id)
            async with session.begin():
                rows = list(
                    await session.scalars(
                        _list_statement(
                            tenant_id=tenant_id,
                            categories=categories,
                            pagination=pagination,
                            dialect_name=session.get_bind().dialect.name,
                        ).limit(pagination.limit + 1)
                    )
                )
        return _page(rows, pagination)

    async def get_tenant_event(
        self,
        *,
        tenant_id: UUID,
        role_codes: tuple[str, ...],
        event_id: UUID,
    ) -> AuditEvent:
        categories = _visible_tenant_categories(role_codes)
        async with self._session_factory() as session:
            configure_tenant_database_access(session, tenant_id)
            async with session.begin():
                event = await session.scalar(
                    select(AuditEvent).where(
                        AuditEvent.id == event_id,
                        AuditEvent.scope_type == AuditScopeType.TENANT.value,
                        AuditEvent.tenant_id == tenant_id,
                        AuditEvent.category.in_(category.value for category in categories),
                    )
                )
        if event is None:
            raise AuditEventNotFoundError()
        return event

    async def list_platform_events(
        self,
        *,
        pagination: AuditListPagination,
    ) -> CursorPage[AuditEvent]:
        if pagination.scope_type is not AuditScopeType.PLATFORM:
            raise AuditAccessDeniedError()
        async with self._session_factory() as session:
            configure_platform_database_access(session)
            async with session.begin():
                rows = list(
                    await session.scalars(
                        _list_statement(
                            tenant_id=None,
                            categories=frozenset({AuditCategory.PLATFORM_OPERATIONS}),
                            pagination=pagination,
                            dialect_name=session.get_bind().dialect.name,
                        ).limit(pagination.limit + 1)
                    )
                )
        return _page(rows, pagination)


def _visible_tenant_categories(role_codes: tuple[str, ...]) -> frozenset[AuditCategory]:
    categories = frozenset(
        category
        for role_code in role_codes
        for category in _TENANT_CATEGORY_VISIBILITY.get(role_code, ())
    )
    if not categories:
        raise AuditAccessDeniedError()
    return categories


def _list_statement(
    *,
    tenant_id: UUID | None,
    categories: frozenset[AuditCategory],
    pagination: AuditListPagination,
    dialect_name: str,
):
    statement = select(AuditEvent).where(
        AuditEvent.scope_type == pagination.scope_type.value,
        AuditEvent.category.in_(category.value for category in categories),
    )
    if tenant_id is None:
        statement = statement.where(AuditEvent.tenant_id.is_(None))
    else:
        statement = statement.where(AuditEvent.tenant_id == tenant_id)
    if pagination.category is not None:
        if pagination.category not in categories:
            return statement.where(False)
        statement = statement.where(AuditEvent.category == pagination.category.value)
    if pagination.event_type is not None:
        statement = statement.where(AuditEvent.event_type == pagination.event_type)
    if pagination.result is not None:
        statement = statement.where(AuditEvent.result == pagination.result.value)
    if pagination.cursor is not None:
        statement = statement.where(
            _cursor_predicate(
                pagination.cursor.occurred_at,
                pagination.cursor.id,
                dialect_name=dialect_name,
            )
        )
    return statement.order_by(*_ordering(dialect_name))


def _ordering(dialect_name: str):
    occurred_at_key = (
        func.julianday(AuditEvent.occurred_at)
        if dialect_name == "sqlite"
        else AuditEvent.occurred_at
    )
    return occurred_at_key.desc(), AuditEvent.id.desc()


def _cursor_predicate(
    occurred_at: datetime,
    event_id: UUID,
    *,
    dialect_name: str,
):
    if dialect_name == "sqlite":
        occurred_at_key = func.julianday(AuditEvent.occurred_at)
        cursor_key = func.julianday(occurred_at)
    else:
        occurred_at_key = AuditEvent.occurred_at
        cursor_key = occurred_at
    return or_(
        occurred_at_key < cursor_key,
        and_(occurred_at_key == cursor_key, AuditEvent.id < event_id),
    )


def _page(
    rows: list[AuditEvent],
    pagination: AuditListPagination,
) -> CursorPage[AuditEvent]:
    items = rows[: pagination.limit]
    next_cursor = None
    if len(rows) > pagination.limit:
        last_item = items[-1]
        next_cursor = pagination.next_cursor(
            occurred_at=_as_utc(last_item.occurred_at),
            event_id=last_item.id,
        )
    return CursorPage(items=items, next_cursor=next_cursor)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


__all__ = [
    "AuditAccessDeniedError",
    "AuditEventNotFoundError",
    "AuditQueryService",
]
