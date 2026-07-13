"""Authenticated bounded organization-chart traversal."""

from __future__ import annotations

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
from app.api.errors import (
    AUTHENTICATION_REQUIRED_RESPONSES,
    ORGANIZATION_AUTHORIZATION_RESPONSES,
    ORGANIZATION_FEATURE_UNAVAILABLE_RESPONSES,
    ORGANIZATION_VALIDATION_RESPONSES,
    TENANT_CLOSED_RESPONSES,
    TENANT_NOT_READY_RESPONSES,
    UNEXPECTED_ERROR_RESPONSES,
    organization_pagination_validation_error,
)
from app.api.openapi import ORGANIZATION_TAG, with_correlation_response_headers
from app.db.session import DatabaseRuntime
from app.platform.pagination import MAX_CURSOR_LENGTH, InvalidCursorError
from app.platform.request_context import RequestContext
from app.platform.responses import ListEnvelope, list_envelope
from app.schemas.org_chart import (
    ORG_CHART_DEFAULT_LIMIT,
    ORG_CHART_MAX_LIMIT,
    OrgChartCursor,
    OrgChartNodeRead,
    OrgChartPagination,
)
from app.services.org_chart_service import OrganizationChartService
from app.services.organization_access import (
    ORGANIZATION_READ_PERMISSION,
    OrganizationAccessDeniedError,
)

_COMMON_RESPONSES = with_correlation_response_headers(
    {
        **AUTHENTICATION_REQUIRED_RESPONSES,
        **ORGANIZATION_AUTHORIZATION_RESPONSES,
        **ORGANIZATION_FEATURE_UNAVAILABLE_RESPONSES,
        **ORGANIZATION_VALIDATION_RESPONSES,
        **TENANT_CLOSED_RESPONSES,
        **TENANT_NOT_READY_RESPONSES,
        **UNEXPECTED_ERROR_RESPONSES,
    }
)

router = APIRouter(
    prefix="/api/v1/org-chart",
    tags=[ORGANIZATION_TAG],
    responses=_COMMON_RESPONSES,
)


def get_org_chart_service(
    runtime: Annotated[DatabaseRuntime, Depends(get_database_runtime)],
) -> OrganizationChartService:
    return OrganizationChartService(session_factory=runtime.session_factory)


def get_org_chart_pagination(
    request: Request,
    limit: Annotated[
        int,
        Query(
            ge=1,
            le=ORG_CHART_MAX_LIMIT,
            description="Maximum people returned in this one-level chart page.",
        ),
    ] = ORG_CHART_DEFAULT_LIMIT,
    cursor: Annotated[
        str | None,
        Query(
            min_length=1,
            max_length=MAX_CURSOR_LENGTH,
            description="Opaque continuation cursor bound to this reporting level.",
        ),
    ] = None,
    root: Annotated[
        bool | None,
        Query(
            description=(
                "Explicitly request tenant reporting roots. It may be omitted for the same "
                "root behavior and cannot be combined with parent_id."
            )
        ),
    ] = None,
    parent_id: Annotated[
        UUID | None,
        Query(
            description=(
                "Manager User identifier whose direct reports should be expanded. Use the "
                "user_id returned by an expandable node."
            )
        ),
    ] = None,
    parent: Annotated[
        UUID | None,
        Query(
            description=(
                "Alias of parent_id for clients using the root/parent traversal vocabulary."
            )
        ),
    ] = None,
) -> OrgChartPagination:
    allowed_keys = {"limit", "cursor", "root", "parent_id", "parent"}
    if any(key not in allowed_keys for key in request.query_params) or any(
        len(request.query_params.getlist(key)) > 1 for key in allowed_keys
    ):
        raise organization_pagination_validation_error()
    if (
        root is False
        or (parent_id is not None and parent is not None)
        or (root is not None and (parent_id is not None or parent is not None))
    ):
        raise organization_pagination_validation_error()
    resolved_parent_id = parent_id if parent_id is not None else parent
    try:
        decoded = OrgChartCursor.from_token(cursor) if cursor is not None else None
        pagination = OrgChartPagination(
            limit=limit,
            cursor=decoded,
            parent_id=resolved_parent_id,
        )
        if not pagination.cursor_matches_level():
            raise ValueError("Organization-chart cursor does not match reporting level")
        return pagination
    except (InvalidCursorError, ValidationError, ValueError) as exc:
        raise organization_pagination_validation_error() from exc


@router.get(
    "",
    response_model=ListEnvelope[OrgChartNodeRead],
    summary="Expand one bounded organization-chart level",
    description=(
        "Returns only tenant reporting roots when parent_id is omitted, or one manager's direct "
        "reports when parent_id is supplied. Every node contains its resolved organization "
        "labels and a has_children hint, so clients never need per-node reads and descendants "
        "are not downloaded until explicitly expanded."
    ),
    responses=with_correlation_response_headers({status.HTTP_200_OK: {}}),
)
async def list_org_chart_level(
    response: Response,
    request_context: Annotated[
        RequestContext,
        Depends(get_authenticated_request_context),
    ],
    service: Annotated[OrganizationChartService, Depends(get_org_chart_service)],
    authorized: Annotated[
        AuthenticatedSession,
        Depends(
            require_permission(
                ORGANIZATION_READ_PERMISSION,
                denied_error=OrganizationAccessDeniedError,
            )
        ),
    ],
    pagination: Annotated[OrgChartPagination, Depends(get_org_chart_pagination)],
) -> ListEnvelope[OrgChartNodeRead]:
    response.headers["Cache-Control"] = "no-store"
    page = await service.list_level(
        request_context=request_context,
        pagination=pagination,
        granted_permissions=authorized.user.permissions,
    )
    return list_envelope(
        page.items,
        request_context,
        limit=pagination.limit,
        next_cursor=page.next_cursor,
    )


__all__ = ["router"]
