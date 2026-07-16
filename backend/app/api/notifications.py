"""Current-user notification inbox APIs."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth_dependencies import AuthenticatedSession, require_permission
from app.api.dependencies import get_authenticated_tenant_request_context, get_unit_of_work
from app.api.openapi import NOTIFICATIONS_TAG
from app.db.session import get_session
from app.platform.db import SqlAlchemyUnitOfWork
from app.platform.pagination import MAX_CURSOR_LENGTH
from app.platform.request_context import RequestContext
from app.platform.responses import DataEnvelope, data_envelope
from app.schemas.notification import (
    NOTIFICATION_LIST_DEFAULT_LIMIT,
    NOTIFICATION_LIST_MAX_LIMIT,
    NotificationListRead,
    NotificationMarkRead,
    NotificationRead,
    NotificationReadAllResult,
)
from app.services.notification_service import NotificationService

router = APIRouter(prefix="/api/v1/notifications", tags=[NOTIFICATIONS_TAG])


def get_service(session: Annotated[AsyncSession, Depends(get_session)]) -> NotificationService:
    return NotificationService(session)


@router.get("", response_model=DataEnvelope[NotificationListRead])
async def list_notifications(
    response: Response,
    request_context: Annotated[
        RequestContext, Depends(get_authenticated_tenant_request_context)
    ],
    _authorized: Annotated[
        AuthenticatedSession, Depends(require_permission("notification:read:own"))
    ],
    service: Annotated[NotificationService, Depends(get_service)],
    limit: Annotated[
        int, Query(ge=1, le=NOTIFICATION_LIST_MAX_LIMIT)
    ] = NOTIFICATION_LIST_DEFAULT_LIMIT,
    cursor: Annotated[str | None, Query(max_length=MAX_CURSOR_LENGTH)] = None,
    unread_only: Annotated[bool, Query()] = False,
) -> DataEnvelope[NotificationListRead]:
    _no_store(response)
    result = await service.list_page(
        tenant_id=request_context.require_tenant().tenant_id,
        actor_id=_actor_id(request_context),
        limit=limit,
        cursor=cursor,
        unread_only=unread_only,
    )
    return data_envelope(result, request_context)


@router.post("/read-all", response_model=DataEnvelope[NotificationReadAllResult])
async def read_all_notifications(
    response: Response,
    request_context: Annotated[
        RequestContext, Depends(get_authenticated_tenant_request_context)
    ],
    _authorized: Annotated[
        AuthenticatedSession, Depends(require_permission("notification:read:own"))
    ],
    service: Annotated[NotificationService, Depends(get_service)],
    unit_of_work: Annotated[SqlAlchemyUnitOfWork, Depends(get_unit_of_work)],
) -> DataEnvelope[NotificationReadAllResult]:
    _no_store(response)
    result = await unit_of_work.execute(
        lambda: service.read_all(
            tenant_id=request_context.require_tenant().tenant_id,
            actor_id=_actor_id(request_context),
        )
    )
    return data_envelope(result, request_context)


@router.post("/{notification_id}/read", response_model=DataEnvelope[NotificationRead])
async def read_notification(
    notification_id: UUID,
    payload: NotificationMarkRead,
    response: Response,
    request_context: Annotated[
        RequestContext, Depends(get_authenticated_tenant_request_context)
    ],
    _authorized: Annotated[
        AuthenticatedSession, Depends(require_permission("notification:read:own"))
    ],
    service: Annotated[NotificationService, Depends(get_service)],
    unit_of_work: Annotated[SqlAlchemyUnitOfWork, Depends(get_unit_of_work)],
) -> DataEnvelope[NotificationRead]:
    _no_store(response)
    result = await unit_of_work.execute(
        lambda: service.mark_read(
            tenant_id=request_context.require_tenant().tenant_id,
            actor_id=_actor_id(request_context),
            notification_id=notification_id,
            expected_version=payload.expected_version,
        )
    )
    return data_envelope(result, request_context)


def _actor_id(context: RequestContext) -> UUID:
    if context.actor_id is None:
        raise RuntimeError("Notification request requires an actor")
    return context.actor_id


def _no_store(response: Response) -> None:
    response.headers["Cache-Control"] = "no-store"


__all__ = ["router"]
