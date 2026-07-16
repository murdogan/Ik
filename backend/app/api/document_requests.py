"""Employee own and explicit HR document-request APIs."""

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
from app.api.openapi import REQUESTS_TAG
from app.db.session import get_session
from app.models.document_request import EmployeeDocumentRequestStatus
from app.platform.db import SqlAlchemyUnitOfWork
from app.platform.pagination import MAX_CURSOR_LENGTH
from app.platform.request_context import RequestContext
from app.platform.responses import DataEnvelope, ListEnvelope, data_envelope, list_envelope
from app.schemas.document_request import (
    DOCUMENT_REQUEST_LIST_DEFAULT_LIMIT,
    DOCUMENT_REQUEST_LIST_MAX_LIMIT,
    EmployeeDocumentRequestCreate,
    EmployeeDocumentRequestDecision,
    EmployeeDocumentRequestRead,
)
from app.services.command_idempotency import CommandIdempotencyService
from app.services.document_request_commands import DocumentRequestCommandHandler
from app.services.document_request_service import DocumentRequestService
from app.services.phase7_access import Phase7AccessDeniedError

router = APIRouter(prefix="/api/v1/document-requests", tags=[REQUESTS_TAG])


def get_service(session: Annotated[AsyncSession, Depends(get_session)]) -> DocumentRequestService:
    return DocumentRequestService(session)


def get_handler(
    service: Annotated[DocumentRequestService, Depends(get_service)],
    unit_of_work: Annotated[SqlAlchemyUnitOfWork, Depends(get_unit_of_work)],
    idempotency: Annotated[
        CommandIdempotencyService, Depends(get_command_idempotency_service)
    ],
) -> DocumentRequestCommandHandler:
    return DocumentRequestCommandHandler(service, unit_of_work, idempotency)


@router.get("", response_model=ListEnvelope[EmployeeDocumentRequestRead])
async def list_document_requests(
    response: Response,
    request_context: Annotated[
        RequestContext, Depends(get_authenticated_tenant_request_context)
    ],
    authorized: Annotated[
        AuthenticatedSession,
        Depends(
            require_any_permission(
                "document_request:read:own", "document_request:manage:tenant"
            )
        ),
    ],
    service: Annotated[DocumentRequestService, Depends(get_service)],
    scope: Annotated[Literal["own", "hr"], Query()] = "own",
    status_filter: Annotated[
        EmployeeDocumentRequestStatus | None, Query(alias="status")
    ] = None,
    limit: Annotated[
        int, Query(ge=1, le=DOCUMENT_REQUEST_LIST_MAX_LIMIT)
    ] = DOCUMENT_REQUEST_LIST_DEFAULT_LIMIT,
    cursor: Annotated[str | None, Query(max_length=MAX_CURSOR_LENGTH)] = None,
) -> ListEnvelope[EmployeeDocumentRequestRead]:
    _authorize_scope(authorized, scope)
    _no_store(response)
    page = await service.list_page(
        tenant_id=request_context.require_tenant().tenant_id,
        actor_id=_actor_id(request_context),
        own=scope == "own",
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
    response_model=DataEnvelope[EmployeeDocumentRequestRead],
    status_code=status.HTTP_201_CREATED,
)
async def create_document_request(
    payload: EmployeeDocumentRequestCreate,
    response: Response,
    request_context: Annotated[
        RequestContext, Depends(get_authenticated_tenant_request_context)
    ],
    _authorized: Annotated[
        AuthenticatedSession, Depends(require_permission("document_request:create:own"))
    ],
    handler: Annotated[DocumentRequestCommandHandler, Depends(get_handler)],
    idempotency_key: Annotated[str | None, Depends(get_idempotency_key)],
) -> DataEnvelope[EmployeeDocumentRequestRead]:
    _no_store(response)
    result = await handler.create(
        request_context=request_context,
        payload=payload,
        idempotency_key=idempotency_key,
    )
    return data_envelope(result, request_context)


@router.get("/{request_id}", response_model=DataEnvelope[EmployeeDocumentRequestRead])
async def get_document_request(
    request_id: UUID,
    response: Response,
    request_context: Annotated[
        RequestContext, Depends(get_authenticated_tenant_request_context)
    ],
    authorized: Annotated[
        AuthenticatedSession,
        Depends(
            require_any_permission(
                "document_request:read:own", "document_request:manage:tenant"
            )
        ),
    ],
    service: Annotated[DocumentRequestService, Depends(get_service)],
    scope: Annotated[Literal["own", "hr"], Query()] = "own",
) -> DataEnvelope[EmployeeDocumentRequestRead]:
    _authorize_scope(authorized, scope)
    _no_store(response)
    result = await service.get(
        tenant_id=request_context.require_tenant().tenant_id,
        actor_id=_actor_id(request_context),
        request_id=request_id,
        own=scope == "own",
    )
    return data_envelope(result, request_context)


@router.post("/{request_id}/resolve", response_model=DataEnvelope[EmployeeDocumentRequestRead])
async def resolve_document_request(
    request_id: UUID,
    payload: EmployeeDocumentRequestDecision,
    response: Response,
    request_context: Annotated[
        RequestContext, Depends(get_authenticated_tenant_request_context)
    ],
    _authorized: Annotated[
        AuthenticatedSession, Depends(require_permission("document_request:manage:tenant"))
    ],
    handler: Annotated[DocumentRequestCommandHandler, Depends(get_handler)],
    idempotency_key: Annotated[str | None, Depends(get_idempotency_key)],
) -> DataEnvelope[EmployeeDocumentRequestRead]:
    return await _decide(
        request_id=request_id,
        payload=payload,
        response=response,
        request_context=request_context,
        handler=handler,
        decision=EmployeeDocumentRequestStatus.RESOLVED,
        idempotency_key=idempotency_key,
    )


@router.post("/{request_id}/reject", response_model=DataEnvelope[EmployeeDocumentRequestRead])
async def reject_document_request(
    request_id: UUID,
    payload: EmployeeDocumentRequestDecision,
    response: Response,
    request_context: Annotated[
        RequestContext, Depends(get_authenticated_tenant_request_context)
    ],
    _authorized: Annotated[
        AuthenticatedSession, Depends(require_permission("document_request:manage:tenant"))
    ],
    handler: Annotated[DocumentRequestCommandHandler, Depends(get_handler)],
    idempotency_key: Annotated[str | None, Depends(get_idempotency_key)],
) -> DataEnvelope[EmployeeDocumentRequestRead]:
    return await _decide(
        request_id=request_id,
        payload=payload,
        response=response,
        request_context=request_context,
        handler=handler,
        decision=EmployeeDocumentRequestStatus.REJECTED,
        idempotency_key=idempotency_key,
    )


async def _decide(
    *,
    request_id: UUID,
    payload: EmployeeDocumentRequestDecision,
    response: Response,
    request_context: RequestContext,
    handler: DocumentRequestCommandHandler,
    decision: EmployeeDocumentRequestStatus,
    idempotency_key: str | None,
) -> DataEnvelope[EmployeeDocumentRequestRead]:
    _no_store(response)
    result = await handler.decide(
        request_context=request_context,
        request_id=request_id,
        decision=decision,
        payload=payload,
        idempotency_key=idempotency_key,
    )
    return data_envelope(result, request_context)


def _authorize_scope(authorized: AuthenticatedSession, scope: str) -> None:
    required = "document_request:manage:tenant" if scope == "hr" else "document_request:read:own"
    if required not in authorized.user.permissions:
        raise Phase7AccessDeniedError


def _actor_id(context: RequestContext) -> UUID:
    if context.actor_id is None:
        raise RuntimeError("Document request requires an actor")
    return context.actor_id


def _no_store(response: Response) -> None:
    response.headers["Cache-Control"] = "no-store"


__all__ = ["router"]
