"""Authenticated tenant position-catalog HTTP contracts."""

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
    ORGANIZATION_VALIDATION_RESPONSES,
    POSITION_CONFLICT_RESPONSES,
    POSITION_NOT_FOUND_RESPONSES,
    TENANT_CLOSED_RESPONSES,
    TENANT_NOT_READY_RESPONSES,
    TENANT_SETTINGS_WRITE_LOCKED_RESPONSES,
    UNEXPECTED_ERROR_RESPONSES,
    organization_pagination_validation_error,
)
from app.api.openapi import ORGANIZATION_TAG, with_correlation_response_headers
from app.db.session import DatabaseRuntime
from app.models.position import Position, PositionStatus
from app.platform.pagination import MAX_CURSOR_LENGTH, InvalidCursorError
from app.platform.request_context import RequestContext
from app.platform.responses import DataEnvelope, ListEnvelope, data_envelope, list_envelope
from app.schemas.position import (
    POSITION_LIST_DEFAULT_LIMIT,
    POSITION_LIST_MAX_LIMIT,
    POSITION_SEARCH_MAX_LENGTH,
    POSITION_SEARCH_MIN_LENGTH,
    PositionCreate,
    PositionListCursor,
    PositionListPagination,
    PositionRead,
    PositionUpdate,
)
from app.services.organization_access import (
    ORGANIZATION_READ_PERMISSION,
    ORGANIZATION_UPDATE_PERMISSION,
    OrganizationAccessDeniedError,
)
from app.services.position_service import PositionService

_COMMON_RESPONSES = with_correlation_response_headers(
    {
        **AUTHENTICATION_REQUIRED_RESPONSES,
        **ORGANIZATION_AUTHORIZATION_RESPONSES,
        **ORGANIZATION_VALIDATION_RESPONSES,
        **POSITION_NOT_FOUND_RESPONSES,
        **TENANT_CLOSED_RESPONSES,
        **TENANT_NOT_READY_RESPONSES,
        **UNEXPECTED_ERROR_RESPONSES,
    }
)

router = APIRouter(
    prefix="/api/v1/positions",
    tags=[ORGANIZATION_TAG],
    responses=_COMMON_RESPONSES,
)


def get_position_service(
    runtime: Annotated[DatabaseRuntime, Depends(get_database_runtime)],
) -> PositionService:
    return PositionService(session_factory=runtime.session_factory)


def get_position_list_pagination(
    request: Request,
    limit: Annotated[
        int,
        Query(
            ge=1,
            le=POSITION_LIST_MAX_LIMIT,
            description="Maximum positions in this bounded cursor page.",
        ),
    ] = POSITION_LIST_DEFAULT_LIMIT,
    cursor: Annotated[
        str | None,
        Query(
            min_length=1,
            max_length=MAX_CURSOR_LENGTH,
            description="Opaque continuation cursor bound to status and search filters.",
        ),
    ] = None,
    position_status: Annotated[
        PositionStatus | None,
        Query(alias="status", description="Optional exact position lifecycle filter."),
    ] = None,
    search: Annotated[
        str | None,
        Query(
            min_length=POSITION_SEARCH_MIN_LENGTH,
            max_length=POSITION_SEARCH_MAX_LENGTH,
            description=(
                "Case-insensitive code or title search. One- or two-character values are "
                "exact stable-code lookups; longer contains search must include at least "
                "three consecutive letters or numbers so index lookup stays bounded."
            ),
        ),
    ] = None,
) -> PositionListPagination:
    bounded_keys = ("limit", "cursor", "status", "search")
    if "offset" in request.query_params or any(
        len(request.query_params.getlist(key)) > 1 for key in bounded_keys
    ):
        raise organization_pagination_validation_error()
    try:
        decoded = PositionListCursor.from_token(cursor) if cursor is not None else None
        pagination = PositionListPagination(
            limit=limit,
            cursor=decoded,
            status=position_status,
            search=search,
        )
        if not pagination.cursor_matches_filters():
            raise ValueError("Position cursor does not match active filters")
        return pagination
    except (InvalidCursorError, ValidationError, ValueError) as exc:
        raise organization_pagination_validation_error() from exc


@router.get(
    "",
    response_model=ListEnvelope[PositionRead],
    summary="Search current-tenant positions",
    description=(
        "Returns a bounded stable-code cursor page of reusable current-tenant job titles. "
        "Lifecycle and case-insensitive code/title search filters are bound into the cursor."
    ),
    responses=with_correlation_response_headers({status.HTTP_200_OK: {}}),
)
async def list_positions(
    response: Response,
    request_context: Annotated[
        RequestContext,
        Depends(get_authenticated_request_context),
    ],
    service: Annotated[PositionService, Depends(get_position_service)],
    authorized: Annotated[
        AuthenticatedSession,
        Depends(
            require_permission(
                ORGANIZATION_READ_PERMISSION,
                denied_error=OrganizationAccessDeniedError,
            )
        ),
    ],
    pagination: Annotated[
        PositionListPagination,
        Depends(get_position_list_pagination),
    ],
) -> ListEnvelope[PositionRead]:
    _prevent_storage(response)
    page = await service.list_positions(
        request_context=request_context,
        pagination=pagination,
        granted_permissions=authorized.user.permissions,
    )
    return list_envelope(
        [_position_read(position) for position in page.items],
        request_context,
        limit=pagination.limit,
        next_cursor=page.next_cursor,
    )


@router.post(
    "",
    response_model=DataEnvelope[PositionRead],
    status_code=status.HTTP_201_CREATED,
    summary="Create a current-tenant position",
    description=(
        "Creates an active reusable job title with a tenant-unique stable code. Tenant scope, "
        "organization RBAC, lifecycle availability, and the audit write are enforced."
    ),
    responses=with_correlation_response_headers(
        {
            status.HTTP_201_CREATED: {},
            **POSITION_CONFLICT_RESPONSES,
            **TENANT_SETTINGS_WRITE_LOCKED_RESPONSES,
        }
    ),
)
async def create_position(
    payload: PositionCreate,
    response: Response,
    request_context: Annotated[
        RequestContext,
        Depends(get_authenticated_request_context),
    ],
    service: Annotated[PositionService, Depends(get_position_service)],
    authorized: Annotated[
        AuthenticatedSession,
        Depends(
            require_permission(
                ORGANIZATION_UPDATE_PERMISSION,
                denied_error=OrganizationAccessDeniedError,
            )
        ),
    ],
) -> DataEnvelope[PositionRead]:
    _prevent_storage(response)
    position = await service.create_position(
        request_context=request_context,
        payload=payload,
        granted_permissions=authorized.user.permissions,
    )
    return data_envelope(_position_read(position), request_context)


@router.get(
    "/{position_id}",
    response_model=DataEnvelope[PositionRead],
    summary="Read a current-tenant position",
    description=(
        "Reads active or archived job-title history only within the authenticated tenant. "
        "Missing and cross-tenant identifiers share the same not-found contract."
    ),
    responses=with_correlation_response_headers(
        {status.HTTP_200_OK: {}, **POSITION_NOT_FOUND_RESPONSES}
    ),
)
async def get_position(
    position_id: UUID,
    response: Response,
    request_context: Annotated[
        RequestContext,
        Depends(get_authenticated_request_context),
    ],
    service: Annotated[PositionService, Depends(get_position_service)],
    authorized: Annotated[
        AuthenticatedSession,
        Depends(
            require_permission(
                ORGANIZATION_READ_PERMISSION,
                denied_error=OrganizationAccessDeniedError,
            )
        ),
    ],
) -> DataEnvelope[PositionRead]:
    _prevent_storage(response)
    position = await service.get_position(
        request_context=request_context,
        position_id=position_id,
        granted_permissions=authorized.user.permissions,
    )
    return data_envelope(_position_read(position), request_context)


@router.patch(
    "/{position_id}",
    response_model=DataEnvelope[PositionRead],
    summary="Update a current-tenant position title",
    description=(
        "Updates the display title while preserving the stable position code. Archived "
        "positions are immutable historical catalog records."
    ),
    responses=with_correlation_response_headers(
        {
            status.HTTP_200_OK: {},
            **POSITION_NOT_FOUND_RESPONSES,
            **POSITION_CONFLICT_RESPONSES,
            **TENANT_SETTINGS_WRITE_LOCKED_RESPONSES,
        }
    ),
)
async def update_position(
    position_id: UUID,
    payload: PositionUpdate,
    response: Response,
    request_context: Annotated[
        RequestContext,
        Depends(get_authenticated_request_context),
    ],
    service: Annotated[PositionService, Depends(get_position_service)],
    authorized: Annotated[
        AuthenticatedSession,
        Depends(
            require_permission(
                ORGANIZATION_UPDATE_PERMISSION,
                denied_error=OrganizationAccessDeniedError,
            )
        ),
    ],
) -> DataEnvelope[PositionRead]:
    _prevent_storage(response)
    position = await service.update_position(
        request_context=request_context,
        position_id=position_id,
        payload=payload,
        granted_permissions=authorized.user.permissions,
    )
    return data_envelope(_position_read(position), request_context)


@router.delete(
    "/{position_id}",
    response_model=DataEnvelope[PositionRead],
    summary="Archive a current-tenant position",
    description=(
        "Archives instead of deleting. The stable code and job-title history remain readable, "
        "and the position can no longer be used by new employee assignments."
    ),
    responses=with_correlation_response_headers(
        {
            status.HTTP_200_OK: {},
            **POSITION_NOT_FOUND_RESPONSES,
            **POSITION_CONFLICT_RESPONSES,
            **TENANT_SETTINGS_WRITE_LOCKED_RESPONSES,
        }
    ),
)
async def archive_position(
    position_id: UUID,
    response: Response,
    request_context: Annotated[
        RequestContext,
        Depends(get_authenticated_request_context),
    ],
    service: Annotated[PositionService, Depends(get_position_service)],
    authorized: Annotated[
        AuthenticatedSession,
        Depends(
            require_permission(
                ORGANIZATION_UPDATE_PERMISSION,
                denied_error=OrganizationAccessDeniedError,
            )
        ),
    ],
) -> DataEnvelope[PositionRead]:
    _prevent_storage(response)
    position = await service.archive_position(
        request_context=request_context,
        position_id=position_id,
        granted_permissions=authorized.user.permissions,
    )
    return data_envelope(_position_read(position), request_context)


def _position_read(position: Position) -> PositionRead:
    return PositionRead(
        id=position.id,
        code=position.code,
        title=position.title,
        status=PositionStatus(position.status),
        archived_at=position.archived_at,
        accepts_new_assignments=(
            position.status == PositionStatus.ACTIVE.value and position.archived_at is None
        ),
        created_at=position.created_at,
        updated_at=position.updated_at,
    )


def _prevent_storage(response: Response) -> None:
    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"


__all__ = ["get_position_list_pagination", "get_position_service", "router"]
