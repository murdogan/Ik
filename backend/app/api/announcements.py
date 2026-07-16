"""HR announcement management and snapshotted recipient APIs."""

from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth_dependencies import (
    AuthenticatedSession,
    require_any_permission,
    require_permission,
)
from app.api.dependencies import (
    get_authenticated_tenant_request_context,
    get_command_idempotency_service,
    get_idempotency_key,
    get_unit_of_work,
)
from app.api.openapi import ANNOUNCEMENTS_TAG
from app.db.session import get_session
from app.models.announcement import AnnouncementStatus
from app.platform.db import SqlAlchemyUnitOfWork
from app.platform.pagination import MAX_CURSOR_LENGTH
from app.platform.request_context import RequestContext
from app.platform.responses import DataEnvelope, ListEnvelope, data_envelope, list_envelope
from app.schemas.announcement import (
    ANNOUNCEMENT_LIST_DEFAULT_LIMIT,
    ANNOUNCEMENT_LIST_MAX_LIMIT,
    AnnouncementCreate,
    AnnouncementDetailRead,
    AnnouncementSummaryRead,
    AnnouncementTargetOptionsRead,
    AnnouncementUpdate,
    AnnouncementVersionAction,
)
from app.services.announcement_commands import AnnouncementCommandHandler
from app.services.announcement_service import AnnouncementService
from app.services.command_idempotency import CommandIdempotencyService
from app.services.phase7_access import Phase7AccessDeniedError

router = APIRouter(prefix="/api/v1/announcements", tags=[ANNOUNCEMENTS_TAG])


def get_service(session: Annotated[AsyncSession, Depends(get_session)]) -> AnnouncementService:
    return AnnouncementService(session)


def get_handler(
    service: Annotated[AnnouncementService, Depends(get_service)],
    unit_of_work: Annotated[SqlAlchemyUnitOfWork, Depends(get_unit_of_work)],
    idempotency: Annotated[
        CommandIdempotencyService, Depends(get_command_idempotency_service)
    ],
) -> AnnouncementCommandHandler:
    return AnnouncementCommandHandler(service, unit_of_work, idempotency)


@router.get("", response_model=ListEnvelope[AnnouncementSummaryRead])
async def list_announcements(
    response: Response,
    request_context: Annotated[
        RequestContext, Depends(get_authenticated_tenant_request_context)
    ],
    authorized: Annotated[
        AuthenticatedSession,
        Depends(require_any_permission("announcement:read:own", "announcement:manage:tenant")),
    ],
    service: Annotated[AnnouncementService, Depends(get_service)],
    scope: Annotated[Literal["own", "manage"], Query()] = "own",
    status_filter: Annotated[AnnouncementStatus | None, Query(alias="status")] = None,
    limit: Annotated[
        int, Query(ge=1, le=ANNOUNCEMENT_LIST_MAX_LIMIT)
    ] = ANNOUNCEMENT_LIST_DEFAULT_LIMIT,
    cursor: Annotated[str | None, Query(max_length=MAX_CURSOR_LENGTH)] = None,
) -> ListEnvelope[AnnouncementSummaryRead]:
    _authorize_scope(authorized, scope)
    _no_store(response)
    page = await service.list_page(
        tenant_id=request_context.require_tenant().tenant_id,
        actor_id=_actor_id(request_context),
        manage=scope == "manage",
        status=status_filter,
        limit=limit,
        cursor=cursor,
    )
    return list_envelope(
        page.items,
        request_context,
        limit=limit,
        next_cursor=page.next_cursor,
    )


@router.post(
    "",
    response_model=DataEnvelope[AnnouncementDetailRead],
    status_code=status.HTTP_201_CREATED,
)
async def create_announcement(
    payload: AnnouncementCreate,
    response: Response,
    request_context: Annotated[
        RequestContext, Depends(get_authenticated_tenant_request_context)
    ],
    _authorized: Annotated[
        AuthenticatedSession, Depends(require_permission("announcement:manage:tenant"))
    ],
    handler: Annotated[AnnouncementCommandHandler, Depends(get_handler)],
    idempotency_key: Annotated[str | None, Depends(get_idempotency_key)],
) -> DataEnvelope[AnnouncementDetailRead]:
    _no_store(response)
    result = await handler.create(
        context=request_context,
        payload=payload,
        idempotency_key=idempotency_key,
    )
    return data_envelope(result, request_context)


@router.get("/target-options", response_model=DataEnvelope[AnnouncementTargetOptionsRead])
async def get_announcement_target_options(
    response: Response,
    request_context: Annotated[
        RequestContext, Depends(get_authenticated_tenant_request_context)
    ],
    _authorized: Annotated[
        AuthenticatedSession, Depends(require_permission("announcement:manage:tenant"))
    ],
    service: Annotated[AnnouncementService, Depends(get_service)],
) -> DataEnvelope[AnnouncementTargetOptionsRead]:
    _no_store(response)
    result = await service.target_options(
        tenant_id=request_context.require_tenant().tenant_id
    )
    return data_envelope(result, request_context)


@router.get("/{announcement_id}", response_model=DataEnvelope[AnnouncementDetailRead])
async def get_announcement(
    announcement_id: UUID,
    response: Response,
    request_context: Annotated[
        RequestContext, Depends(get_authenticated_tenant_request_context)
    ],
    authorized: Annotated[
        AuthenticatedSession,
        Depends(require_any_permission("announcement:read:own", "announcement:manage:tenant")),
    ],
    service: Annotated[AnnouncementService, Depends(get_service)],
    scope: Annotated[Literal["own", "manage"], Query()] = "own",
) -> DataEnvelope[AnnouncementDetailRead]:
    _authorize_scope(authorized, scope)
    _no_store(response)
    result = await service.get(
        tenant_id=request_context.require_tenant().tenant_id,
        actor_id=_actor_id(request_context),
        announcement_id=announcement_id,
        manage=scope == "manage",
    )
    return data_envelope(result, request_context)


@router.patch("/{announcement_id}", response_model=DataEnvelope[AnnouncementDetailRead])
async def update_announcement(
    announcement_id: UUID,
    payload: AnnouncementUpdate,
    response: Response,
    request_context: Annotated[
        RequestContext, Depends(get_authenticated_tenant_request_context)
    ],
    _authorized: Annotated[
        AuthenticatedSession, Depends(require_permission("announcement:manage:tenant"))
    ],
    handler: Annotated[AnnouncementCommandHandler, Depends(get_handler)],
    idempotency_key: Annotated[str | None, Depends(get_idempotency_key)],
) -> DataEnvelope[AnnouncementDetailRead]:
    _no_store(response)
    result = await handler.update(
        context=request_context,
        announcement_id=announcement_id,
        payload=payload,
        idempotency_key=idempotency_key,
    )
    return data_envelope(result, request_context)


@router.post("/{announcement_id}/publish", response_model=DataEnvelope[AnnouncementDetailRead])
async def publish_announcement(
    announcement_id: UUID,
    payload: AnnouncementVersionAction,
    response: Response,
    request_context: Annotated[
        RequestContext, Depends(get_authenticated_tenant_request_context)
    ],
    _authorized: Annotated[
        AuthenticatedSession, Depends(require_permission("announcement:manage:tenant"))
    ],
    handler: Annotated[AnnouncementCommandHandler, Depends(get_handler)],
    idempotency_key: Annotated[str | None, Depends(get_idempotency_key)],
) -> DataEnvelope[AnnouncementDetailRead]:
    return await _action(
        announcement_id=announcement_id,
        payload=payload,
        response=response,
        request_context=request_context,
        handler=handler,
        action="publish",
        idempotency_key=idempotency_key,
    )


@router.post("/{announcement_id}/archive", response_model=DataEnvelope[AnnouncementDetailRead])
async def archive_announcement(
    announcement_id: UUID,
    payload: AnnouncementVersionAction,
    response: Response,
    request_context: Annotated[
        RequestContext, Depends(get_authenticated_tenant_request_context)
    ],
    _authorized: Annotated[
        AuthenticatedSession, Depends(require_permission("announcement:manage:tenant"))
    ],
    handler: Annotated[AnnouncementCommandHandler, Depends(get_handler)],
    idempotency_key: Annotated[str | None, Depends(get_idempotency_key)],
) -> DataEnvelope[AnnouncementDetailRead]:
    return await _action(
        announcement_id=announcement_id,
        payload=payload,
        response=response,
        request_context=request_context,
        handler=handler,
        action="archive",
        idempotency_key=idempotency_key,
    )


@router.post("/{announcement_id}/read", response_model=DataEnvelope[AnnouncementDetailRead])
async def read_announcement(
    announcement_id: UUID,
    payload: AnnouncementVersionAction,
    response: Response,
    request_context: Annotated[
        RequestContext, Depends(get_authenticated_tenant_request_context)
    ],
    _authorized: Annotated[
        AuthenticatedSession, Depends(require_permission("announcement:read:own"))
    ],
    handler: Annotated[AnnouncementCommandHandler, Depends(get_handler)],
    idempotency_key: Annotated[str | None, Depends(get_idempotency_key)],
) -> DataEnvelope[AnnouncementDetailRead]:
    return await _action(
        announcement_id=announcement_id,
        payload=payload,
        response=response,
        request_context=request_context,
        handler=handler,
        action="read",
        idempotency_key=idempotency_key,
    )


@router.post("/{announcement_id}/ack", response_model=DataEnvelope[AnnouncementDetailRead])
async def acknowledge_announcement(
    announcement_id: UUID,
    payload: AnnouncementVersionAction,
    response: Response,
    request_context: Annotated[
        RequestContext, Depends(get_authenticated_tenant_request_context)
    ],
    _authorized: Annotated[
        AuthenticatedSession, Depends(require_permission("announcement:read:own"))
    ],
    handler: Annotated[AnnouncementCommandHandler, Depends(get_handler)],
    idempotency_key: Annotated[str | None, Depends(get_idempotency_key)],
) -> DataEnvelope[AnnouncementDetailRead]:
    return await _action(
        announcement_id=announcement_id,
        payload=payload,
        response=response,
        request_context=request_context,
        handler=handler,
        action="ack",
        idempotency_key=idempotency_key,
    )


async def _action(
    *,
    announcement_id: UUID,
    payload: AnnouncementVersionAction,
    response: Response,
    request_context: RequestContext,
    handler: AnnouncementCommandHandler,
    action: str,
    idempotency_key: str | None,
) -> DataEnvelope[AnnouncementDetailRead]:
    _no_store(response)
    result = await handler.version_action(
        context=request_context,
        announcement_id=announcement_id,
        expected_version=payload.expected_version,
        action=action,
        idempotency_key=idempotency_key,
    )
    return data_envelope(result, request_context)


def _authorize_scope(authorized: AuthenticatedSession, scope: str) -> None:
    required = (
        "announcement:manage:tenant" if scope == "manage" else "announcement:read:own"
    )
    if required not in authorized.user.permissions:
        raise Phase7AccessDeniedError


def _actor_id(context: RequestContext) -> UUID:
    if context.actor_id is None:
        raise RuntimeError("Announcement request requires an actor")
    return context.actor_id


def _no_store(response: Response) -> None:
    response.headers["Cache-Control"] = "no-store"


__all__ = ["router"]
