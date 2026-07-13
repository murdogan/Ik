"""Authenticated tenant department hierarchy HTTP contracts."""

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
    DEPARTMENT_CONFLICT_RESPONSES,
    DEPARTMENT_NOT_FOUND_RESPONSES,
    ORGANIZATION_AUTHORIZATION_RESPONSES,
    ORGANIZATION_VALIDATION_RESPONSES,
    TENANT_CLOSED_RESPONSES,
    TENANT_NOT_READY_RESPONSES,
    TENANT_SETTINGS_WRITE_LOCKED_RESPONSES,
    UNEXPECTED_ERROR_RESPONSES,
    organization_pagination_validation_error,
)
from app.api.openapi import ORGANIZATION_TAG, with_correlation_response_headers
from app.db.session import DatabaseRuntime
from app.models.department import DepartmentStatus
from app.platform.pagination import MAX_CURSOR_LENGTH, InvalidCursorError
from app.platform.request_context import RequestContext
from app.platform.responses import (
    DataEnvelope,
    ListEnvelope,
    data_envelope,
    list_envelope,
)
from app.schemas.department import (
    DEPARTMENT_LIST_DEFAULT_LIMIT,
    DEPARTMENT_LIST_MAX_LIMIT,
    DepartmentCreate,
    DepartmentListCursor,
    DepartmentListPagination,
    DepartmentRead,
    DepartmentTreeCursor,
    DepartmentTreePagination,
    DepartmentUpdate,
)
from app.services.department_service import DepartmentService, DepartmentView
from app.services.organization_access import (
    ORGANIZATION_READ_PERMISSION,
    ORGANIZATION_UPDATE_PERMISSION,
    OrganizationAccessDeniedError,
)

_COMMON_RESPONSES = with_correlation_response_headers(
    {
        **AUTHENTICATION_REQUIRED_RESPONSES,
        **ORGANIZATION_AUTHORIZATION_RESPONSES,
        **ORGANIZATION_VALIDATION_RESPONSES,
        **DEPARTMENT_NOT_FOUND_RESPONSES,
        **TENANT_CLOSED_RESPONSES,
        **TENANT_NOT_READY_RESPONSES,
        **UNEXPECTED_ERROR_RESPONSES,
    }
)

router = APIRouter(
    prefix="/api/v1/departments",
    tags=[ORGANIZATION_TAG],
    responses=_COMMON_RESPONSES,
)


def get_department_service(
    runtime: Annotated[DatabaseRuntime, Depends(get_database_runtime)],
) -> DepartmentService:
    return DepartmentService(session_factory=runtime.session_factory)


def get_department_list_pagination(
    request: Request,
    limit: Annotated[
        int,
        Query(
            ge=1,
            le=DEPARTMENT_LIST_MAX_LIMIT,
            description="Maximum departments in this bounded cursor page.",
        ),
    ] = DEPARTMENT_LIST_DEFAULT_LIMIT,
    cursor: Annotated[
        str | None,
        Query(
            min_length=1,
            max_length=MAX_CURSOR_LENGTH,
            description="Opaque continuation cursor from meta.next_cursor.",
        ),
    ] = None,
    department_status: Annotated[
        DepartmentStatus | None,
        Query(alias="status", description="Optional exact department lifecycle filter."),
    ] = None,
) -> DepartmentListPagination:
    bounded_keys = ("limit", "cursor", "status")
    if "offset" in request.query_params or any(
        len(request.query_params.getlist(key)) > 1 for key in bounded_keys
    ):
        raise organization_pagination_validation_error()
    try:
        decoded = DepartmentListCursor.from_token(cursor) if cursor is not None else None
        pagination = DepartmentListPagination(
            limit=limit,
            cursor=decoded,
            status=department_status,
        )
        if not pagination.cursor_matches_filters():
            raise ValueError("Department cursor does not match active filters")
        return pagination
    except (InvalidCursorError, ValidationError, ValueError) as exc:
        raise organization_pagination_validation_error() from exc


def get_department_tree_pagination(
    request: Request,
    limit: Annotated[
        int,
        Query(
            ge=1,
            le=DEPARTMENT_LIST_MAX_LIMIT,
            description="Maximum sibling departments in this lazy tree page.",
        ),
    ] = DEPARTMENT_LIST_DEFAULT_LIMIT,
    cursor: Annotated[
        str | None,
        Query(
            min_length=1,
            max_length=MAX_CURSOR_LENGTH,
            description="Opaque continuation cursor bound to this tree level.",
        ),
    ] = None,
    parent_id: Annotated[
        UUID | None,
        Query(description="Parent to expand; omit to read root departments."),
    ] = None,
    include_archived: Annotated[
        bool,
        Query(description="Include archived historical nodes in this one-level page."),
    ] = False,
) -> DepartmentTreePagination:
    bounded_keys = ("limit", "cursor", "parent_id", "include_archived")
    if "offset" in request.query_params or any(
        len(request.query_params.getlist(key)) > 1 for key in bounded_keys
    ):
        raise organization_pagination_validation_error()
    try:
        decoded = DepartmentTreeCursor.from_token(cursor) if cursor is not None else None
        pagination = DepartmentTreePagination(
            limit=limit,
            cursor=decoded,
            parent_id=parent_id,
            include_archived=include_archived,
        )
        if not pagination.cursor_matches_filters():
            raise ValueError("Department tree cursor does not match active filters")
        return pagination
    except (InvalidCursorError, ValidationError, ValueError) as exc:
        raise organization_pagination_validation_error() from exc


@router.get(
    "",
    response_model=ListEnvelope[DepartmentRead],
    summary="List current-tenant departments",
    description=(
        "Returns a bounded stable-code cursor page of active and archived current-tenant "
        "departments, with an optional lifecycle filter. It never materializes the full tree."
    ),
    responses=with_correlation_response_headers({status.HTTP_200_OK: {}}),
)
async def list_departments(
    response: Response,
    request_context: Annotated[
        RequestContext,
        Depends(get_authenticated_request_context),
    ],
    service: Annotated[DepartmentService, Depends(get_department_service)],
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
        DepartmentListPagination,
        Depends(get_department_list_pagination),
    ],
) -> ListEnvelope[DepartmentRead]:
    _prevent_storage(response)
    page = await service.list_departments(
        request_context=request_context,
        pagination=pagination,
        granted_permissions=authorized.user.permissions,
    )
    return list_envelope(
        [_department_read(view) for view in page.items],
        request_context,
        limit=pagination.limit,
        next_cursor=page.next_cursor,
    )


@router.post(
    "",
    response_model=DataEnvelope[DepartmentRead],
    status_code=status.HTTP_201_CREATED,
    summary="Create a current-tenant department",
    description=(
        "Creates an active root or child department with a tenant-unique stable code. An active "
        "parent, tenant scope, RBAC permission, cycle invariant, and audit write are enforced."
    ),
    responses=with_correlation_response_headers(
        {
            status.HTTP_201_CREATED: {},
            **DEPARTMENT_CONFLICT_RESPONSES,
            **TENANT_SETTINGS_WRITE_LOCKED_RESPONSES,
        }
    ),
)
async def create_department(
    payload: DepartmentCreate,
    response: Response,
    request_context: Annotated[
        RequestContext,
        Depends(get_authenticated_request_context),
    ],
    service: Annotated[DepartmentService, Depends(get_department_service)],
    authorized: Annotated[
        AuthenticatedSession,
        Depends(
            require_permission(
                ORGANIZATION_UPDATE_PERMISSION,
                denied_error=OrganizationAccessDeniedError,
            )
        ),
    ],
) -> DataEnvelope[DepartmentRead]:
    _prevent_storage(response)
    view = await service.create_department(
        request_context=request_context,
        payload=payload,
        granted_permissions=authorized.user.permissions,
    )
    return data_envelope(_department_read(view), request_context)


# This fixed route must be registered before /{department_id}; it is a lazy one-level expansion,
# never an unbounded recursively nested tenant tree.
@router.get(
    "/tree",
    response_model=ListEnvelope[DepartmentRead],
    summary="Expand one bounded department tree level",
    description=(
        "Returns only root siblings when parent_id is omitted or one direct child level when it "
        "is supplied. Every page is capped and cursor-bound to parent and archive filters."
    ),
    responses=with_correlation_response_headers(
        {status.HTTP_200_OK: {}, **DEPARTMENT_NOT_FOUND_RESPONSES}
    ),
)
async def list_department_tree_level(
    response: Response,
    request_context: Annotated[
        RequestContext,
        Depends(get_authenticated_request_context),
    ],
    service: Annotated[DepartmentService, Depends(get_department_service)],
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
        DepartmentTreePagination,
        Depends(get_department_tree_pagination),
    ],
) -> ListEnvelope[DepartmentRead]:
    _prevent_storage(response)
    page = await service.list_tree_level(
        request_context=request_context,
        pagination=pagination,
        granted_permissions=authorized.user.permissions,
    )
    return list_envelope(
        [_department_read(view) for view in page.items],
        request_context,
        limit=pagination.limit,
        next_cursor=page.next_cursor,
    )


@router.get(
    "/{department_id}",
    response_model=DataEnvelope[DepartmentRead],
    summary="Read a current-tenant department",
    description=(
        "Reads an active or archived department only within the authenticated tenant. Archived "
        "rows retain their stable code and parent link for history."
    ),
    responses=with_correlation_response_headers(
        {status.HTTP_200_OK: {}, **DEPARTMENT_NOT_FOUND_RESPONSES}
    ),
)
async def get_department(
    department_id: UUID,
    response: Response,
    request_context: Annotated[
        RequestContext,
        Depends(get_authenticated_request_context),
    ],
    service: Annotated[DepartmentService, Depends(get_department_service)],
    authorized: Annotated[
        AuthenticatedSession,
        Depends(
            require_permission(
                ORGANIZATION_READ_PERMISSION,
                denied_error=OrganizationAccessDeniedError,
            )
        ),
    ],
) -> DataEnvelope[DepartmentRead]:
    _prevent_storage(response)
    view = await service.get_department(
        request_context=request_context,
        department_id=department_id,
        granted_permissions=authorized.user.permissions,
    )
    return data_envelope(_department_read(view), request_context)


@router.patch(
    "/{department_id}",
    response_model=DataEnvelope[DepartmentRead],
    summary="Rename or safely move an active department",
    description=(
        "Updates only the name and parent relation. Explicit null parent_id moves the department "
        "to the root; the stable code is immutable and archived departments are terminal."
    ),
    responses=with_correlation_response_headers(
        {
            status.HTTP_200_OK: {},
            **DEPARTMENT_NOT_FOUND_RESPONSES,
            **DEPARTMENT_CONFLICT_RESPONSES,
            **TENANT_SETTINGS_WRITE_LOCKED_RESPONSES,
        }
    ),
)
async def update_department(
    department_id: UUID,
    payload: DepartmentUpdate,
    response: Response,
    request_context: Annotated[
        RequestContext,
        Depends(get_authenticated_request_context),
    ],
    service: Annotated[DepartmentService, Depends(get_department_service)],
    authorized: Annotated[
        AuthenticatedSession,
        Depends(
            require_permission(
                ORGANIZATION_UPDATE_PERMISSION,
                denied_error=OrganizationAccessDeniedError,
            )
        ),
    ],
) -> DataEnvelope[DepartmentRead]:
    _prevent_storage(response)
    view = await service.update_department(
        request_context=request_context,
        department_id=department_id,
        payload=payload,
        granted_permissions=authorized.user.permissions,
    )
    return data_envelope(_department_read(view), request_context)


@router.delete(
    "/{department_id}",
    response_model=DataEnvelope[DepartmentRead],
    summary="Archive an unused current-tenant department",
    description=(
        "Archives instead of deleting. Departments with active children cannot be archived; "
        "successful archival is idempotent and preserves the stable code and hierarchy history."
    ),
    responses=with_correlation_response_headers(
        {
            status.HTTP_200_OK: {},
            **DEPARTMENT_NOT_FOUND_RESPONSES,
            **DEPARTMENT_CONFLICT_RESPONSES,
            **TENANT_SETTINGS_WRITE_LOCKED_RESPONSES,
        }
    ),
)
async def archive_department(
    department_id: UUID,
    response: Response,
    request_context: Annotated[
        RequestContext,
        Depends(get_authenticated_request_context),
    ],
    service: Annotated[DepartmentService, Depends(get_department_service)],
    authorized: Annotated[
        AuthenticatedSession,
        Depends(
            require_permission(
                ORGANIZATION_UPDATE_PERMISSION,
                denied_error=OrganizationAccessDeniedError,
            )
        ),
    ],
) -> DataEnvelope[DepartmentRead]:
    _prevent_storage(response)
    view = await service.archive_department(
        request_context=request_context,
        department_id=department_id,
        granted_permissions=authorized.user.permissions,
    )
    return data_envelope(_department_read(view), request_context)


def _department_read(view: DepartmentView) -> DepartmentRead:
    department = view.department
    return DepartmentRead(
        id=department.id,
        parent_id=department.parent_id,
        code=department.code,
        name=department.name,
        status=DepartmentStatus(department.status),
        archived_at=department.archived_at,
        has_children=view.has_children,
        accepts_new_assignments=(
            department.status == DepartmentStatus.ACTIVE.value and department.archived_at is None
        ),
        created_at=department.created_at,
        updated_at=department.updated_at,
    )


def _prevent_storage(response: Response) -> None:
    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"


__all__ = ["router"]
