"""Authenticated tenant-admin user reads and allowlisted updates."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import and_, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.auth import RefreshSessionFamily, UserActivationToken
from app.models.tenant import Tenant, TenantStatus
from app.models.user import User, UserStatus
from app.platform.db import SqlAlchemyUnitOfWork, configure_tenant_database_access
from app.platform.errors.application import ApplicationError
from app.platform.pagination import CursorPage
from app.platform.request_context import RequestContext
from app.schemas.user_administration import (
    UserAdministrationUpdate,
    UserListCursor,
    UserListPagination,
)

_ADMINISTRABLE_TENANT_STATUSES = frozenset({TenantStatus.TRIAL.value, TenantStatus.ACTIVE.value})


class UserAdministrationAccessDeniedError(ApplicationError):
    pass


class UserAdministrationUserNotFoundError(ApplicationError):
    pass


class UserAdministrationStatusConflictError(ApplicationError):
    pass


@dataclass(frozen=True, slots=True)
class UserAdministrationRecord:
    id: UUID
    email: str
    full_name: str
    status: str
    created_at: datetime
    updated_at: datetime


class UserAdministrationService:
    """Constant-query user administration scoped only by authenticated context."""

    def __init__(
        self,
        *,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        self._session_factory = session_factory

    async def list_users(
        self,
        *,
        request_context: RequestContext,
        pagination: UserListPagination,
    ) -> CursorPage[UserAdministrationRecord]:
        tenant_id, _actor_id = _scope_from_context(request_context)
        async with self._session_factory() as session:
            configure_tenant_database_access(session, tenant_id)
            async with session.begin():
                await _authorize_tenant_admin(
                    session,
                    tenant_id=tenant_id,
                    actor_id=_actor_id,
                    tenant_slug=request_context.require_tenant().slug,
                )
                dialect_name = session.get_bind().dialect.name
                statement = _user_list_statement(
                    tenant_id,
                    pagination,
                    dialect_name=dialect_name,
                )
                rows = list((await session.execute(statement.limit(pagination.limit + 1))).all())

        items = [_record_from_row(row) for row in rows[: pagination.limit]]
        next_cursor = None
        if len(rows) > pagination.limit:
            last_item = items[-1]
            created_at = last_item.created_at
            if created_at.tzinfo is None:
                created_at = created_at.replace(tzinfo=UTC)
            next_cursor = UserListCursor(
                created_at=created_at,
                id=last_item.id,
                search=pagination.search.lower() if pagination.search is not None else "",
                status=pagination.status.value if pagination.status is not None else "",
            ).to_token()
        return CursorPage(items=items, next_cursor=next_cursor)

    async def get_user(
        self,
        *,
        request_context: RequestContext,
        user_id: UUID,
    ) -> UserAdministrationRecord:
        tenant_id, actor_id = _scope_from_context(request_context)
        async with self._session_factory() as session:
            configure_tenant_database_access(session, tenant_id)
            async with session.begin():
                await _authorize_tenant_admin(
                    session,
                    tenant_id=tenant_id,
                    actor_id=actor_id,
                    tenant_slug=request_context.require_tenant().slug,
                )
                row = (
                    await session.execute(
                        _user_projection().where(
                            User.tenant_id == tenant_id,
                            User.id == user_id,
                        )
                    )
                ).one_or_none()
        if row is None:
            raise UserAdministrationUserNotFoundError()
        return _record_from_row(row)

    async def update_user(
        self,
        *,
        request_context: RequestContext,
        user_id: UUID,
        update: UserAdministrationUpdate,
    ) -> UserAdministrationRecord:
        tenant_id, actor_id = _scope_from_context(request_context)
        async with self._session_factory() as session:
            configure_tenant_database_access(session, tenant_id)
            unit_of_work = SqlAlchemyUnitOfWork(session)

            async def operation() -> UserAdministrationRecord:
                await _authorize_tenant_admin(
                    session,
                    tenant_id=tenant_id,
                    actor_id=actor_id,
                    tenant_slug=request_context.require_tenant().slug,
                )
                user = await session.scalar(
                    select(User)
                    .where(
                        User.tenant_id == tenant_id,
                        User.id == user_id,
                    )
                    .with_for_update()
                )
                if user is None:
                    raise UserAdministrationUserNotFoundError()

                if "status" in update.model_fields_set:
                    assert update.status is not None
                    _validate_status_change(
                        user,
                        update.status,
                        actor_id=actor_id,
                    )
                    user.status = update.status.value
                    await _revoke_credentials_for_status(
                        session,
                        user=user,
                        status=update.status,
                    )
                if "full_name" in update.model_fields_set:
                    assert update.full_name is not None
                    user.full_name = update.full_name
                user.updated_at = datetime.now(UTC)
                await session.flush()
                await session.refresh(user)
                return _record_from_user(user)

            return await unit_of_work.execute(operation)


def _scope_from_context(request_context: RequestContext) -> tuple[UUID, UUID]:
    tenant_id = request_context.require_tenant().tenant_id
    actor_id = request_context.actor_id
    if actor_id is None:
        raise UserAdministrationAccessDeniedError()
    return tenant_id, actor_id


async def _authorize_tenant_admin(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    actor_id: UUID,
    tenant_slug: str,
) -> None:
    row = (
        await session.execute(
            select(User.status, User.can_invite_users, Tenant.status, Tenant.slug)
            .join(Tenant, Tenant.id == User.tenant_id)
            .where(
                User.tenant_id == tenant_id,
                User.id == actor_id,
                Tenant.id == tenant_id,
            )
        )
    ).one_or_none()
    if row is None:
        raise UserAdministrationAccessDeniedError()
    user_status, can_invite_users, tenant_status, persisted_tenant_slug = row
    if (
        user_status != UserStatus.ACTIVE.value
        or not can_invite_users
        or tenant_status not in _ADMINISTRABLE_TENANT_STATUSES
        or persisted_tenant_slug != tenant_slug
    ):
        raise UserAdministrationAccessDeniedError()


def _validate_status_change(
    user: User,
    status: UserStatus,
    *,
    actor_id: UUID,
) -> None:
    if (
        user.id == actor_id
        and status in {UserStatus.LOCKED, UserStatus.DISABLED}
        and user.status != status.value
    ):
        raise UserAdministrationStatusConflictError(
            "The authenticated administrator cannot lock or disable their own account"
        )
    if status in {UserStatus.ACTIVE, UserStatus.LOCKED} and user.password_hash is None:
        raise UserAdministrationStatusConflictError(
            "An unactivated user cannot be made active or locked"
        )
    if status == UserStatus.INVITED and user.password_hash is not None:
        raise UserAdministrationStatusConflictError(
            "An activated user cannot return to invited status"
        )


async def _revoke_credentials_for_status(
    session: AsyncSession,
    *,
    user: User,
    status: UserStatus,
) -> None:
    if status not in {UserStatus.LOCKED, UserStatus.DISABLED}:
        return
    now = datetime.now(UTC)
    await session.execute(
        update(RefreshSessionFamily)
        .where(
            RefreshSessionFamily.tenant_id == user.tenant_id,
            RefreshSessionFamily.user_id == user.id,
            RefreshSessionFamily.revoked_at.is_(None),
        )
        .values(revoked_at=now)
    )
    if status == UserStatus.DISABLED:
        await session.execute(
            update(UserActivationToken)
            .where(
                UserActivationToken.tenant_id == user.tenant_id,
                UserActivationToken.user_id == user.id,
                UserActivationToken.consumed_at.is_(None),
                UserActivationToken.revoked_at.is_(None),
            )
            .values(revoked_at=now)
        )


def _user_projection():
    return select(
        User.id,
        User.email,
        User.full_name,
        User.status,
        User.created_at,
        User.updated_at,
    )


def _user_list_statement(
    tenant_id: UUID,
    pagination: UserListPagination,
    *,
    dialect_name: str,
):
    statement = _user_projection().where(User.tenant_id == tenant_id)
    if pagination.status is not None:
        statement = statement.where(User.status == pagination.status.value)
    if pagination.search is not None:
        search_pattern = f"%{_escape_like(pagination.search.lower())}%"
        statement = statement.where(
            or_(
                User.email_normalized.ilike(search_pattern, escape="\\"),
                User.full_name.ilike(search_pattern, escape="\\"),
            )
        )
    if pagination.cursor is not None:
        statement = statement.where(
            _cursor_predicate(
                pagination.cursor,
                dialect_name=dialect_name,
            )
        )
    return statement.order_by(*_user_ordering(dialect_name))


def _user_ordering(dialect_name: str):
    created_at_key = (
        func.julianday(User.created_at) if dialect_name == "sqlite" else User.created_at
    )
    return created_at_key.desc(), User.id.desc()


def _cursor_predicate(cursor: UserListCursor, *, dialect_name: str):
    if dialect_name == "sqlite":
        created_at_key = func.julianday(User.created_at)
        cursor_created_at_key = func.julianday(cursor.created_at)
    else:
        created_at_key = User.created_at
        cursor_created_at_key = cursor.created_at
    return or_(
        created_at_key < cursor_created_at_key,
        and_(
            created_at_key == cursor_created_at_key,
            User.id < cursor.id,
        ),
    )


def _record_from_row(row: object) -> UserAdministrationRecord:
    mapping = row._mapping  # type: ignore[attr-defined]
    return UserAdministrationRecord(
        id=mapping["id"],
        email=mapping["email"],
        full_name=mapping["full_name"],
        status=mapping["status"],
        created_at=mapping["created_at"],
        updated_at=mapping["updated_at"],
    )


def _record_from_user(user: User) -> UserAdministrationRecord:
    return UserAdministrationRecord(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        status=user.status,
        created_at=user.created_at,  # type: ignore[arg-type]
        updated_at=user.updated_at,  # type: ignore[arg-type]
    )


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


__all__ = [
    "UserAdministrationAccessDeniedError",
    "UserAdministrationRecord",
    "UserAdministrationService",
    "UserAdministrationStatusConflictError",
    "UserAdministrationUserNotFoundError",
]
