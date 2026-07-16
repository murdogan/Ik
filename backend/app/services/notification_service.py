"""Bounded current-user notification inbox reads and idempotent consumption commands."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import and_, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.notification import Notification
from app.modules.core.domain.feature_flags import FeatureFlagKey
from app.platform.pagination import InvalidCursorError, decode_cursor, encode_cursor
from app.schemas.notification import (
    NOTIFICATION_READ_ALL_LIMIT,
    NotificationListRead,
    NotificationRead,
    NotificationReadAllResult,
)
from app.services.phase7_access import (
    Phase7NotFoundError,
    Phase7ValidationError,
    Phase7VersionConflictError,
    require_phase7_feature,
)

_CURSOR_RESOURCE = "notifications_v1"
_UNREAD_COUNT_LIMIT = 10_000


class NotificationService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_page(
        self,
        *,
        tenant_id: UUID,
        actor_id: UUID,
        limit: int,
        cursor: str | None,
        unread_only: bool,
    ) -> NotificationListRead:
        await self._require_feature(tenant_id)
        cursor_values = _decode_cursor(cursor, unread_only=unread_only)
        statement = select(Notification).where(
            Notification.tenant_id == tenant_id,
            Notification.recipient_user_id == actor_id,
        )
        if unread_only:
            statement = statement.where(Notification.read_at.is_(None))
        if cursor_values is not None:
            created_at, notification_id = cursor_values
            statement = statement.where(
                or_(
                    Notification.created_at < created_at,
                    and_(
                        Notification.created_at == created_at,
                        Notification.id < notification_id,
                    ),
                )
            )
        records = list(
            await self.session.scalars(
                statement.order_by(Notification.created_at.desc(), Notification.id.desc()).limit(
                    limit + 1
                )
            )
        )
        next_cursor = None
        if len(records) > limit:
            last = records[limit - 1]
            next_cursor = encode_cursor(
                _CURSOR_RESOURCE,
                {
                    "created_at": _aware(last.created_at).isoformat(),
                    "id": str(last.id),
                    "unread": "1" if unread_only else "0",
                },
            )
        unread_rows = (
            select(Notification.id)
            .where(
                Notification.tenant_id == tenant_id,
                Notification.recipient_user_id == actor_id,
                Notification.read_at.is_(None),
            )
            .limit(_UNREAD_COUNT_LIMIT)
            .subquery()
        )
        unread_count = int(
            await self.session.scalar(
                select(func.count()).select_from(unread_rows)
            )
            or 0
        )
        return NotificationListRead(
            items=[_read(record) for record in records[:limit]],
            next_cursor=next_cursor,
            unread_count=unread_count,
        )

    async def mark_read(
        self,
        *,
        tenant_id: UUID,
        actor_id: UUID,
        notification_id: UUID,
        expected_version: int,
    ) -> NotificationRead:
        await self._require_feature(tenant_id)
        notification = await self.session.scalar(
            select(Notification)
            .where(
                Notification.tenant_id == tenant_id,
                Notification.id == notification_id,
                Notification.recipient_user_id == actor_id,
            )
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if notification is None:
            raise Phase7NotFoundError
        if notification.read_at is None:
            if notification.version != expected_version:
                raise Phase7VersionConflictError
            notification.read_at = datetime.now(UTC)
            await self.session.flush()
        return _read(notification)

    async def read_all(
        self,
        *,
        tenant_id: UUID,
        actor_id: UUID,
    ) -> NotificationReadAllResult:
        await self._require_feature(tenant_id)
        identifiers = list(
            await self.session.scalars(
                select(Notification.id)
                .where(
                    Notification.tenant_id == tenant_id,
                    Notification.recipient_user_id == actor_id,
                    Notification.read_at.is_(None),
                )
                .order_by(Notification.created_at, Notification.id)
                .limit(NOTIFICATION_READ_ALL_LIMIT)
                .with_for_update(skip_locked=True)
            )
        )
        if identifiers:
            await self.session.execute(
                update(Notification)
                .where(
                    Notification.tenant_id == tenant_id,
                    Notification.recipient_user_id == actor_id,
                    Notification.id.in_(identifiers),
                    Notification.read_at.is_(None),
                )
                .values(read_at=datetime.now(UTC), version=Notification.version + 1)
            )
        has_more = (
            await self.session.scalar(
                select(Notification.id).where(
                    Notification.tenant_id == tenant_id,
                    Notification.recipient_user_id == actor_id,
                    Notification.read_at.is_(None),
                )
            )
            is not None
        )
        return NotificationReadAllResult(
            id=actor_id,
            updated_count=len(identifiers),
            has_more=has_more,
        )

    async def _require_feature(self, tenant_id: UUID) -> None:
        await require_phase7_feature(
            self.session,
            tenant_id=tenant_id,
            feature=FeatureFlagKey.NOTIFICATIONS,
        )


def _decode_cursor(token: str | None, *, unread_only: bool) -> tuple[datetime, UUID] | None:
    if token is None:
        return None
    try:
        values = decode_cursor(token, expected_resource=_CURSOR_RESOURCE)
        if set(values) != {"created_at", "id", "unread"}:
            raise InvalidCursorError
        if values["unread"] != ("1" if unread_only else "0"):
            raise InvalidCursorError
        created_at = datetime.fromisoformat(values["created_at"])
        if created_at.tzinfo is None or created_at.utcoffset() is None:
            raise InvalidCursorError
        return created_at, UUID(values["id"])
    except (InvalidCursorError, ValueError) as exc:
        raise Phase7ValidationError("The notification cursor is invalid") from exc


def _read(notification: Notification) -> NotificationRead:
    return NotificationRead(
        id=notification.id,
        notification_type=notification.notification_type,
        title=notification.title,
        body=notification.body,
        portal_path=notification.portal_path,
        read_at=_aware(notification.read_at) if notification.read_at is not None else None,
        version=notification.version,
        created_at=_aware(notification.created_at),
    )


def _aware(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


__all__ = ["NotificationService"]
