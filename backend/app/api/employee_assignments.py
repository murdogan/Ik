"""Authenticated employee-assignment history and derived manager-team contracts."""

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
    EMPLOYEE_ASSIGNMENT_AUTHORIZATION_RESPONSES,
    EMPLOYEE_ASSIGNMENT_CONFLICT_RESPONSES,
    EMPLOYEE_ASSIGNMENT_NOT_FOUND_RESPONSES,
    EMPLOYEE_ASSIGNMENT_VALIDATION_RESPONSES,
    TENANT_CLOSED_RESPONSES,
    TENANT_NOT_READY_RESPONSES,
    TENANT_SETTINGS_WRITE_LOCKED_RESPONSES,
    UNEXPECTED_ERROR_RESPONSES,
    employee_assignment_validation_error,
)
from app.api.openapi import ORGANIZATION_TAG, with_correlation_response_headers
from app.db.session import DatabaseRuntime
from app.platform.pagination import MAX_CURSOR_LENGTH, InvalidCursorError
from app.platform.request_context import RequestContext
from app.platform.responses import DataEnvelope, ListEnvelope, data_envelope, list_envelope
from app.schemas.employee_assignment import (
    ASSIGNMENT_LIST_DEFAULT_LIMIT,
    ASSIGNMENT_LIST_MAX_LIMIT,
    ASSIGNMENT_OPTIONS_DEFAULT_LIMIT,
    ASSIGNMENT_OPTIONS_MAX_LIMIT,
    EmployeeAssignmentChange,
    EmployeeAssignmentCreate,
    EmployeeAssignmentListCursor,
    EmployeeAssignmentListPagination,
    EmployeeAssignmentOptionsRead,
    EmployeeAssignmentRead,
    TeamListCursor,
    TeamListPagination,
    TeamMemberRead,
)
from app.services.employee_assignment_service import (
    EMPLOYEE_ASSIGNMENT_READ_PERMISSION,
    EMPLOYEE_ASSIGNMENT_UPDATE_PERMISSION,
    EMPLOYEE_TEAM_READ_PERMISSION,
    EmployeeAssignmentAccessDeniedError,
    EmployeeAssignmentService,
)

_COMMON_RESPONSES = with_correlation_response_headers(
    {
        **AUTHENTICATION_REQUIRED_RESPONSES,
        **EMPLOYEE_ASSIGNMENT_AUTHORIZATION_RESPONSES,
        **EMPLOYEE_ASSIGNMENT_VALIDATION_RESPONSES,
        **EMPLOYEE_ASSIGNMENT_NOT_FOUND_RESPONSES,
        **TENANT_CLOSED_RESPONSES,
        **TENANT_NOT_READY_RESPONSES,
        **UNEXPECTED_ERROR_RESPONSES,
    }
)

assignments_router = APIRouter(
    prefix="/api/v1/employee-assignments",
    tags=[ORGANIZATION_TAG],
    responses=_COMMON_RESPONSES,
)
teams_router = APIRouter(
    prefix="/api/v1/teams",
    tags=[ORGANIZATION_TAG],
    responses=_COMMON_RESPONSES,
)


def get_employee_assignment_service(
    runtime: Annotated[DatabaseRuntime, Depends(get_database_runtime)],
) -> EmployeeAssignmentService:
    return EmployeeAssignmentService(session_factory=runtime.session_factory)


def get_assignment_list_pagination(
    request: Request,
    limit: Annotated[
        int,
        Query(ge=1, le=ASSIGNMENT_LIST_MAX_LIMIT),
    ] = ASSIGNMENT_LIST_DEFAULT_LIMIT,
    cursor: Annotated[
        str | None,
        Query(min_length=1, max_length=MAX_CURSOR_LENGTH),
    ] = None,
    employee_id: Annotated[UUID | None, Query()] = None,
    include_history: Annotated[bool, Query()] = False,
) -> EmployeeAssignmentListPagination:
    allowed_keys = {"limit", "cursor", "employee_id", "include_history"}
    if any(key not in allowed_keys for key in request.query_params) or any(
        len(request.query_params.getlist(key)) > 1 for key in allowed_keys
    ):
        raise employee_assignment_validation_error()
    try:
        decoded = (
            EmployeeAssignmentListCursor.from_token(cursor)
            if cursor is not None
            else None
        )
        pagination = EmployeeAssignmentListPagination(
            limit=limit,
            cursor=decoded,
            employee_id=employee_id,
            include_history=include_history,
        )
        if not pagination.cursor_matches_filters():
            raise ValueError("Assignment cursor does not match active filters")
        return pagination
    except (InvalidCursorError, ValidationError, ValueError) as exc:
        raise employee_assignment_validation_error() from exc


def get_team_list_pagination(
    request: Request,
    limit: Annotated[
        int,
        Query(ge=1, le=ASSIGNMENT_LIST_MAX_LIMIT),
    ] = ASSIGNMENT_LIST_DEFAULT_LIMIT,
    cursor: Annotated[
        str | None,
        Query(min_length=1, max_length=MAX_CURSOR_LENGTH),
    ] = None,
) -> TeamListPagination:
    allowed_keys = {"limit", "cursor"}
    if any(key not in allowed_keys for key in request.query_params) or any(
        len(request.query_params.getlist(key)) > 1 for key in allowed_keys
    ):
        raise employee_assignment_validation_error()
    try:
        decoded = TeamListCursor.from_token(cursor) if cursor is not None else None
        return TeamListPagination(limit=limit, cursor=decoded)
    except (InvalidCursorError, ValidationError, ValueError) as exc:
        raise employee_assignment_validation_error() from exc


@assignments_router.get(
    "",
    response_model=ListEnvelope[EmployeeAssignmentRead],
    summary="List current-tenant employee assignments",
    description=(
        "Returns effective current assignments by default. HR can request retained history or "
        "filter one employee; every row includes resolved organization labels so archived "
        "references remain understandable without follow-up queries."
    ),
)
async def list_employee_assignments(
    response: Response,
    request_context: Annotated[
        RequestContext,
        Depends(get_authenticated_request_context),
    ],
    service: Annotated[
        EmployeeAssignmentService,
        Depends(get_employee_assignment_service),
    ],
    authorized: Annotated[
        AuthenticatedSession,
        Depends(
            require_permission(
                EMPLOYEE_ASSIGNMENT_READ_PERMISSION,
                denied_error=EmployeeAssignmentAccessDeniedError,
            )
        ),
    ],
    pagination: Annotated[
        EmployeeAssignmentListPagination,
        Depends(get_assignment_list_pagination),
    ],
) -> ListEnvelope[EmployeeAssignmentRead]:
    _prevent_storage(response)
    page = await service.list_assignments(
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


@assignments_router.get(
    "/options",
    response_model=DataEnvelope[EmployeeAssignmentOptionsRead],
    summary="List bounded assignment form options",
    description=(
        "Returns searchable active employee choices and active users who hold team-read "
        "capability. Employee search never narrows the manager choices. This narrow HR-only "
        "surface avoids exposing the tenant user-administration directory."
    ),
)
async def get_employee_assignment_options(
    response: Response,
    request_context: Annotated[
        RequestContext,
        Depends(get_authenticated_request_context),
    ],
    service: Annotated[
        EmployeeAssignmentService,
        Depends(get_employee_assignment_service),
    ],
    authorized: Annotated[
        AuthenticatedSession,
        Depends(
            require_permission(
                EMPLOYEE_ASSIGNMENT_UPDATE_PERMISSION,
                denied_error=EmployeeAssignmentAccessDeniedError,
            )
        ),
    ],
    search: Annotated[
        str | None,
        Query(
            min_length=1,
            max_length=100,
            description="Employee number, name, or email contains search.",
        ),
    ] = None,
    limit: Annotated[
        int,
        Query(ge=1, le=ASSIGNMENT_OPTIONS_MAX_LIMIT),
    ] = ASSIGNMENT_OPTIONS_DEFAULT_LIMIT,
) -> DataEnvelope[EmployeeAssignmentOptionsRead]:
    _prevent_storage(response)
    options = await service.assignment_options(
        request_context=request_context,
        search=search.strip() if search is not None else None,
        limit=limit,
        granted_permissions=authorized.user.permissions,
    )
    return data_envelope(options, request_context)


@assignments_router.post(
    "",
    response_model=DataEnvelope[EmployeeAssignmentRead],
    status_code=status.HTTP_201_CREATED,
    summary="Create an employee's first structured assignment",
    description=(
        "Creates the first effective assignment after atomically validating active tenant-owned "
        "organization references and reporting-manager capability."
    ),
    responses=with_correlation_response_headers(
        {
            status.HTTP_201_CREATED: {},
            **EMPLOYEE_ASSIGNMENT_CONFLICT_RESPONSES,
            **TENANT_SETTINGS_WRITE_LOCKED_RESPONSES,
        }
    ),
)
async def create_employee_assignment(
    payload: EmployeeAssignmentCreate,
    response: Response,
    request_context: Annotated[
        RequestContext,
        Depends(get_authenticated_request_context),
    ],
    service: Annotated[
        EmployeeAssignmentService,
        Depends(get_employee_assignment_service),
    ],
    authorized: Annotated[
        AuthenticatedSession,
        Depends(
            require_permission(
                EMPLOYEE_ASSIGNMENT_UPDATE_PERMISSION,
                denied_error=EmployeeAssignmentAccessDeniedError,
            )
        ),
    ],
) -> DataEnvelope[EmployeeAssignmentRead]:
    _prevent_storage(response)
    assignment = await service.create_assignment(
        request_context=request_context,
        payload=payload,
        granted_permissions=authorized.user.permissions,
    )
    return data_envelope(assignment, request_context)


@assignments_router.get(
    "/{assignment_id}",
    response_model=DataEnvelope[EmployeeAssignmentRead],
    summary="Read one current or historical employee assignment",
    description=(
        "Reads one retained assignment only within the authenticated tenant and HR employee "
        "scope. Missing and cross-tenant identifiers share the same not-found response."
    ),
)
async def get_employee_assignment(
    assignment_id: UUID,
    response: Response,
    request_context: Annotated[
        RequestContext,
        Depends(get_authenticated_request_context),
    ],
    service: Annotated[
        EmployeeAssignmentService,
        Depends(get_employee_assignment_service),
    ],
    authorized: Annotated[
        AuthenticatedSession,
        Depends(
            require_permission(
                EMPLOYEE_ASSIGNMENT_READ_PERMISSION,
                denied_error=EmployeeAssignmentAccessDeniedError,
            )
        ),
    ],
) -> DataEnvelope[EmployeeAssignmentRead]:
    _prevent_storage(response)
    assignment = await service.get_assignment(
        request_context=request_context,
        assignment_id=assignment_id,
        granted_permissions=authorized.user.permissions,
    )
    return data_envelope(assignment, request_context)


@assignments_router.patch(
    "/{assignment_id}",
    response_model=DataEnvelope[EmployeeAssignmentRead],
    summary="Append an effective employee-assignment change",
    description=(
        "Closes the open assignment at the successor's exclusive effective boundary and appends "
        "a new immutable history row. Assignment and reporting-line audit writes commit or roll "
        "back with the same transaction."
    ),
    responses=with_correlation_response_headers(
        {
            status.HTTP_200_OK: {},
            **EMPLOYEE_ASSIGNMENT_CONFLICT_RESPONSES,
            **TENANT_SETTINGS_WRITE_LOCKED_RESPONSES,
        }
    ),
)
async def change_employee_assignment(
    assignment_id: UUID,
    payload: EmployeeAssignmentChange,
    response: Response,
    request_context: Annotated[
        RequestContext,
        Depends(get_authenticated_request_context),
    ],
    service: Annotated[
        EmployeeAssignmentService,
        Depends(get_employee_assignment_service),
    ],
    authorized: Annotated[
        AuthenticatedSession,
        Depends(
            require_permission(
                EMPLOYEE_ASSIGNMENT_UPDATE_PERMISSION,
                denied_error=EmployeeAssignmentAccessDeniedError,
            )
        ),
    ],
) -> DataEnvelope[EmployeeAssignmentRead]:
    _prevent_storage(response)
    successor = await service.change_assignment(
        request_context=request_context,
        assignment_id=assignment_id,
        payload=payload,
        granted_permissions=authorized.user.permissions,
    )
    return data_envelope(successor, request_context)


@teams_router.get(
    "/me",
    response_model=ListEnvelope[TeamMemberRead],
    summary="List the authenticated manager's derived direct team",
    description=(
        "Returns only active employees whose currently effective structured assignment names the "
        "authenticated user as reporting manager. Legacy department or position text never "
        "expands this scope."
    ),
)
async def get_my_team(
    response: Response,
    request_context: Annotated[
        RequestContext,
        Depends(get_authenticated_request_context),
    ],
    service: Annotated[
        EmployeeAssignmentService,
        Depends(get_employee_assignment_service),
    ],
    authorized: Annotated[
        AuthenticatedSession,
        Depends(
            require_permission(
                EMPLOYEE_TEAM_READ_PERMISSION,
                denied_error=EmployeeAssignmentAccessDeniedError,
            )
        ),
    ],
    pagination: Annotated[TeamListPagination, Depends(get_team_list_pagination)],
) -> ListEnvelope[TeamMemberRead]:
    _prevent_storage(response)
    page = await service.my_team(
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


def _prevent_storage(response: Response) -> None:
    response.headers["Cache-Control"] = "no-store"


__all__ = ["assignments_router", "teams_router"]
