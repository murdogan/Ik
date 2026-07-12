"""Tenant and platform audit explorer read surfaces."""

from __future__ import annotations

from datetime import UTC
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, Response, status
from pydantic import ValidationError

from app.api.auth_dependencies import (
    AuthenticatedSession,
    get_authenticated_request_context,
    get_database_runtime,
    require_permission,
)
from app.api.dependencies import get_platform_request_context
from app.api.errors import (
    AUTHENTICATION_REQUIRED_RESPONSES,
    AUTHORIZATION_RESPONSES,
    PLATFORM_AUTHORIZATION_RESPONSES,
    UNEXPECTED_ERROR_RESPONSES,
    audit_pagination_validation_error,
)
from app.api.openapi import (
    AUDIT_TAG,
    PLATFORM_AUDIT_TAG,
    PLATFORM_PRINCIPAL_OPENAPI,
    with_correlation_response_headers,
)
from app.db.session import DatabaseRuntime
from app.models.audit import AuditEvent
from app.platform.audit import AuditCategory, AuditResult, AuditScopeType
from app.platform.pagination import MAX_CURSOR_LENGTH, InvalidCursorError
from app.platform.request_context import RequestContext
from app.platform.responses import DataEnvelope, ListEnvelope, data_envelope, list_envelope
from app.schemas.audit import (
    AUDIT_EVENT_TYPE_MAX_LENGTH,
    AUDIT_LIST_DEFAULT_LIMIT,
    AUDIT_LIST_MAX_LIMIT,
    AuditEventRead,
    AuditListCursor,
    AuditListPagination,
)
from app.services.audit_query_service import AuditQueryService

tenant_router = APIRouter(
    prefix="/api/v1/audit-events",
    tags=[AUDIT_TAG],
    responses=with_correlation_response_headers(
        {
            **AUTHENTICATION_REQUIRED_RESPONSES,
            **AUTHORIZATION_RESPONSES,
            **UNEXPECTED_ERROR_RESPONSES,
        }
    ),
)
platform_router = APIRouter(
    prefix="/api/v1/platform/audit-events",
    tags=[PLATFORM_AUDIT_TAG],
    dependencies=[Depends(get_platform_request_context)],
    responses=with_correlation_response_headers(
        {**PLATFORM_AUTHORIZATION_RESPONSES, **UNEXPECTED_ERROR_RESPONSES}
    ),
)


def get_audit_query_service(
    runtime: Annotated[DatabaseRuntime, Depends(get_database_runtime)],
) -> AuditQueryService:
    return AuditQueryService(session_factory=runtime.session_factory)


def get_tenant_audit_pagination(
    request: Request,
    limit: Annotated[int, Query(ge=1, le=AUDIT_LIST_MAX_LIMIT)] = AUDIT_LIST_DEFAULT_LIMIT,
    cursor: Annotated[str | None, Query(min_length=1, max_length=MAX_CURSOR_LENGTH)] = None,
    category: AuditCategory | None = None,
    event_type: Annotated[
        str | None,
        Query(min_length=3, max_length=AUDIT_EVENT_TYPE_MAX_LENGTH),
    ] = None,
    result: AuditResult | None = None,
) -> AuditListPagination:
    return _pagination(
        request,
        scope_type=AuditScopeType.TENANT,
        limit=limit,
        cursor=cursor,
        category=category,
        event_type=event_type,
        result=result,
    )


def get_platform_audit_pagination(
    request: Request,
    limit: Annotated[int, Query(ge=1, le=AUDIT_LIST_MAX_LIMIT)] = AUDIT_LIST_DEFAULT_LIMIT,
    cursor: Annotated[str | None, Query(min_length=1, max_length=MAX_CURSOR_LENGTH)] = None,
    category: AuditCategory | None = None,
    event_type: Annotated[
        str | None,
        Query(min_length=3, max_length=AUDIT_EVENT_TYPE_MAX_LENGTH),
    ] = None,
    result: AuditResult | None = None,
) -> AuditListPagination:
    return _pagination(
        request,
        scope_type=AuditScopeType.PLATFORM,
        limit=limit,
        cursor=cursor,
        category=category,
        event_type=event_type,
        result=result,
    )


@tenant_router.get(
    "",
    response_model=ListEnvelope[AuditEventRead],
    summary="List authorized tenant audit events",
    description=(
        "Returns a bounded, redacted cursor page from only the authenticated tenant and the "
        "categories visible to the actor's audit role."
    ),
    responses=with_correlation_response_headers({status.HTTP_200_OK: {}}),
)
async def list_tenant_audit_events(
    response: Response,
    request_context: Annotated[RequestContext, Depends(get_authenticated_request_context)],
    authorized: Annotated[
        AuthenticatedSession,
        Depends(require_permission("audit:read:tenant")),
    ],
    pagination: Annotated[AuditListPagination, Depends(get_tenant_audit_pagination)],
    service: Annotated[AuditQueryService, Depends(get_audit_query_service)],
) -> ListEnvelope[AuditEventRead]:
    _prevent_storage(response)
    page = await service.list_tenant_events(
        tenant_id=request_context.require_tenant().tenant_id,
        role_codes=tuple(role.code for role in authorized.user.roles),
        pagination=pagination,
    )
    return list_envelope(
        [_event_read(event) for event in page.items],
        request_context,
        limit=pagination.limit,
        next_cursor=page.next_cursor,
    )


@tenant_router.get(
    "/{event_id}",
    response_model=DataEnvelope[AuditEventRead],
    summary="Read one authorized tenant audit event",
    description=(
        "Returns one redacted event only when its tenant and category are visible to the "
        "authenticated actor; hidden and cross-tenant IDs share the not-found response."
    ),
    responses=with_correlation_response_headers({status.HTTP_200_OK: {}}),
)
async def get_tenant_audit_event(
    event_id: UUID,
    response: Response,
    request_context: Annotated[RequestContext, Depends(get_authenticated_request_context)],
    authorized: Annotated[
        AuthenticatedSession,
        Depends(require_permission("audit:read:tenant")),
    ],
    service: Annotated[AuditQueryService, Depends(get_audit_query_service)],
) -> DataEnvelope[AuditEventRead]:
    _prevent_storage(response)
    event = await service.get_tenant_event(
        tenant_id=request_context.require_tenant().tenant_id,
        role_codes=tuple(role.code for role in authorized.user.roles),
        event_id=event_id,
    )
    return data_envelope(_event_read(event), request_context)


@platform_router.get(
    "",
    openapi_extra=PLATFORM_PRINCIPAL_OPENAPI,
    response_model=ListEnvelope[AuditEventRead],
    summary="List platform-only audit events",
    description=(
        "Returns only redacted platform operations through the existing trusted platform "
        "principal boundary; tenant security and HR events are never selected."
    ),
    responses=with_correlation_response_headers({status.HTTP_200_OK: {}}),
)
async def list_platform_audit_events(
    response: Response,
    request_context: Annotated[RequestContext, Depends(get_platform_request_context)],
    pagination: Annotated[AuditListPagination, Depends(get_platform_audit_pagination)],
    service: Annotated[AuditQueryService, Depends(get_audit_query_service)],
) -> ListEnvelope[AuditEventRead]:
    _prevent_storage(response)
    page = await service.list_platform_events(pagination=pagination)
    return list_envelope(
        [_event_read(event) for event in page.items],
        request_context,
        limit=pagination.limit,
        next_cursor=page.next_cursor,
    )


def _pagination(
    request: Request,
    *,
    scope_type: AuditScopeType,
    limit: int,
    cursor: str | None,
    category: AuditCategory | None,
    event_type: str | None,
    result: AuditResult | None,
) -> AuditListPagination:
    bounded_keys = ("limit", "cursor", "category", "event_type", "result")
    if "offset" in request.query_params or any(
        len(request.query_params.getlist(key)) > 1 for key in bounded_keys
    ):
        raise audit_pagination_validation_error()
    try:
        pagination = AuditListPagination(
            limit=limit,
            cursor=AuditListCursor.from_token(cursor) if cursor else None,
            scope_type=scope_type,
            category=category,
            event_type=event_type,
            result=result,
        )
    except (InvalidCursorError, ValidationError, ValueError) as exc:
        raise audit_pagination_validation_error() from exc
    if not pagination.cursor_matches_filters():
        raise audit_pagination_validation_error()
    return pagination


def _event_read(event: AuditEvent) -> AuditEventRead:
    occurred_at = event.occurred_at
    if occurred_at.tzinfo is None or occurred_at.utcoffset() is None:
        occurred_at = occurred_at.replace(tzinfo=UTC)
    return AuditEventRead(
        id=event.id,
        occurred_at=occurred_at,
        scope_type=event.scope_type,
        tenant_id=event.tenant_id,
        actor_type=event.actor_type,
        actor_user_id=event.actor_user_id,
        impersonator_user_id=event.impersonator_user_id,
        event_type=event.event_type,
        category=event.category,
        severity=event.severity,
        resource_type=event.resource_type,
        resource_id=event.resource_id,
        action=event.action,
        result=event.result,
        request_id=event.request_id,
        trace_id=event.trace_id,
        session_id=event.session_id,
        ip_address=event.ip_address,
        user_agent=event.user_agent,
        reason=event.reason,
        support_ticket_id=event.support_ticket_id,
        changed_fields=list(event.changed_fields),
        before_data=dict(event.before_data),
        after_data=dict(event.after_data),
        metadata=dict(event.metadata_),
        data_classification=event.data_classification,
        visibility_class=event.visibility_class,
    )


def _prevent_storage(response: Response) -> None:
    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"


__all__ = ["platform_router", "tenant_router"]
