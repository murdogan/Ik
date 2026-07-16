"""Fixed unified request projection API."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth_dependencies import AuthenticatedSession, require_any_permission
from app.api.dependencies import get_authenticated_tenant_request_context
from app.api.openapi import REQUESTS_TAG
from app.db.session import get_session
from app.platform.pagination import MAX_CURSOR_LENGTH
from app.platform.request_context import RequestContext
from app.platform.responses import DataEnvelope, ListEnvelope, data_envelope, list_envelope
from app.schemas.request_projection import (
    REQUEST_LIST_DEFAULT_LIMIT,
    REQUEST_LIST_MAX_LIMIT,
    UnifiedRequestKind,
    UnifiedRequestRead,
)
from app.services.request_projection_service import RequestProjectionService

router = APIRouter(prefix="/api/v1/requests", tags=[REQUESTS_TAG])


def get_service(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> RequestProjectionService:
    return RequestProjectionService(session)


@router.get("", response_model=ListEnvelope[UnifiedRequestRead])
async def list_requests(
    response: Response,
    request_context: Annotated[
        RequestContext, Depends(get_authenticated_tenant_request_context)
    ],
    authorized: Annotated[
        AuthenticatedSession,
        Depends(
            require_any_permission(
                "request:read:own", "request:read:team", "request:read:tenant"
            )
        ),
    ],
    service: Annotated[RequestProjectionService, Depends(get_service)],
    kind: Annotated[UnifiedRequestKind | None, Query()] = None,
    status_filter: Annotated[str | None, Query(alias="status", max_length=32)] = None,
    limit: Annotated[
        int, Query(ge=1, le=REQUEST_LIST_MAX_LIMIT)
    ] = REQUEST_LIST_DEFAULT_LIMIT,
    cursor: Annotated[str | None, Query(max_length=MAX_CURSOR_LENGTH)] = None,
) -> ListEnvelope[UnifiedRequestRead]:
    _no_store(response)
    page = await service.list_page(
        tenant_id=request_context.require_tenant().tenant_id,
        actor_id=_actor_id(request_context),
        membership_id=request_context.require_membership(),
        permissions=authorized.user.permissions,
        limit=limit,
        cursor=cursor,
        kind=kind,
        status=status_filter,
    )
    return list_envelope(
        page.items,
        request_context,
        limit=limit,
        next_cursor=page.next_cursor,
    )


@router.get("/{request_id}", response_model=DataEnvelope[UnifiedRequestRead])
async def get_request(
    request_id: UUID,
    response: Response,
    request_context: Annotated[
        RequestContext, Depends(get_authenticated_tenant_request_context)
    ],
    authorized: Annotated[
        AuthenticatedSession,
        Depends(
            require_any_permission(
                "request:read:own", "request:read:team", "request:read:tenant"
            )
        ),
    ],
    service: Annotated[RequestProjectionService, Depends(get_service)],
) -> DataEnvelope[UnifiedRequestRead]:
    _no_store(response)
    result = await service.get(
        tenant_id=request_context.require_tenant().tenant_id,
        actor_id=_actor_id(request_context),
        membership_id=request_context.require_membership(),
        permissions=authorized.user.permissions,
        request_id=request_id,
    )
    return data_envelope(result, request_context)


def _actor_id(context: RequestContext) -> UUID:
    if context.actor_id is None:
        raise RuntimeError("Request projection requires an actor")
    return context.actor_id


def _no_store(response: Response) -> None:
    response.headers["Cache-Control"] = "no-store"


__all__ = ["router"]
