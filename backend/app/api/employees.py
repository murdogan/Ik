from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response, status
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth_dependencies import AuthenticatedSession, require_permission
from app.api.compatibility import phase0_plain_cursor_list
from app.api.dependencies import (
    get_authenticated_tenant_request_context,
    get_command_idempotency_service,
    get_idempotency_key,
    get_unit_of_work,
)
from app.api.errors import (
    AUTHENTICATION_REQUIRED_RESPONSES,
    AUTHORIZATION_RESPONSES,
    EMPLOYEE_COMMAND_CONFLICT_RESPONSES,
    EMPLOYEE_VALIDATION_RESPONSES,
    IDEMPOTENCY_KEY_INVALID_RESPONSES,
    IDEMPOTENT_EMPLOYEE_COMMAND_CONFLICT_RESPONSES,
    employee_pagination_validation_error,
)
from app.api.openapi import EMPLOYEES_TAG
from app.db.session import get_session
from app.models.employee import EmployeeStatus
from app.platform.db import SqlAlchemyUnitOfWork
from app.platform.pagination import MAX_CURSOR_LENGTH, NEXT_CURSOR_HEADER, InvalidCursorError
from app.platform.request_context import RequestContext
from app.schemas.employee import (
    EMPLOYEE_LIST_DEFAULT_LIMIT,
    EMPLOYEE_LIST_MAX_LIMIT,
    EmployeeArchive,
    EmployeeCreate,
    EmployeeLifecycleRead,
    EmployeeLifecycleTransition,
    EmployeeListCursor,
    EmployeeListFilters,
    EmployeeListPagination,
    EmployeeRead,
    EmployeeUpdate,
)
from app.services.audit_recorder import SqlAlchemyAuditRecorder
from app.services.command_idempotency import CommandIdempotencyService
from app.services.employee_commands import EmployeeCommandHandler
from app.services.employee_service import EmployeeService

router = APIRouter(
    prefix="/api/v1/employees",
    tags=[EMPLOYEES_TAG],
    responses={
        **AUTHENTICATION_REQUIRED_RESPONSES,
        **AUTHORIZATION_RESPONSES,
        **EMPLOYEE_VALIDATION_RESPONSES,
    },
)


def get_employee_service(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> EmployeeService:
    return EmployeeService(session=session)


def get_employee_command_handler(
    service: Annotated[EmployeeService, Depends(get_employee_service)],
    unit_of_work: Annotated[SqlAlchemyUnitOfWork, Depends(get_unit_of_work)],
    idempotency: Annotated[
        CommandIdempotencyService,
        Depends(get_command_idempotency_service),
    ],
) -> EmployeeCommandHandler:
    return EmployeeCommandHandler(
        service=service,
        unit_of_work=unit_of_work,
        idempotency=idempotency,
        audit_recorder=SqlAlchemyAuditRecorder(service.session),
    )


def get_employee_list_filters(
    department: Annotated[
        str | None,
        Query(
            description=(
                "Filters to an exact department value within the tenant. Case-insensitive."
            ),
        ),
    ] = None,
    status_filter: Annotated[
        EmployeeStatus | None,
        Query(alias="status", description="Filters by employment lifecycle status."),
    ] = None,
    q: Annotated[
        str | None,
        Query(
            description=(
                "Case-insensitive search over employee number, full name, and work email "
                "within the tenant."
            ),
            max_length=320,
        ),
    ] = None,
    legal_entity_id: Annotated[
        UUID | None,
        Query(description="Filters by the currently effective legal entity."),
    ] = None,
    branch_id: Annotated[
        UUID | None,
        Query(description="Filters by the currently effective branch."),
    ] = None,
    department_id: Annotated[
        UUID | None,
        Query(description="Filters by the currently effective structured department."),
    ] = None,
    position_id: Annotated[
        UUID | None,
        Query(description="Filters by the currently effective structured position."),
    ] = None,
) -> EmployeeListFilters:
    return EmployeeListFilters(
        department=department,
        status=status_filter,
        q=q,
        legal_entity_id=legal_entity_id,
        branch_id=branch_id,
        department_id=department_id,
        position_id=position_id,
    )


def get_employee_list_pagination(
    limit: Annotated[
        int,
        Query(
            ge=1,
            le=EMPLOYEE_LIST_MAX_LIMIT,
            description=(
                "Maximum employees to return for this tenant. Bounded to protect large lists."
            ),
        ),
    ] = EMPLOYEE_LIST_DEFAULT_LIMIT,
    offset: Annotated[
        int,
        Query(
            ge=0,
            deprecated=True,
            description=(
                "Compatibility path: number of matching tenant employees to skip. Prefer the "
                "cursor returned in X-Next-Cursor for growing lists."
            ),
        ),
    ] = 0,
    cursor: Annotated[
        str | None,
        Query(
            min_length=1,
            max_length=MAX_CURSOR_LENGTH,
            description=(
                "Optional opaque keyset cursor returned in X-Next-Cursor. It takes precedence "
                "over the offset compatibility path and must be used with offset=0."
            ),
        ),
    ] = None,
) -> EmployeeListPagination:
    try:
        decoded_cursor = EmployeeListCursor.from_token(cursor) if cursor is not None else None
    except (InvalidCursorError, ValidationError) as exc:
        raise employee_pagination_validation_error() from exc
    if decoded_cursor is not None and offset != 0:
        raise employee_pagination_validation_error()
    return EmployeeListPagination(limit=limit, offset=offset, cursor=decoded_cursor)


@router.get(
    "",
    response_model=list[EmployeeRead],
    summary="List tenant employees",
    description=(
        "Lists employee directory records for the authenticated tenant session. "
        "Optional filters cover lifecycle status, full-text identity search, preserved legacy "
        "department text, and the currently effective legal entity, branch, department, and "
        "position; tenant isolation is applied before bounded keyset pagination. The bounded "
        "limit/offset path remains available for compatibility."
    ),
    response_description="Employee list.",
    responses={
        status.HTTP_200_OK: {
            "headers": {
                NEXT_CURSOR_HEADER: {
                    "description": (
                        "Opaque cursor for the next deterministic page, when one exists."
                    ),
                    "schema": {"type": "string"},
                }
            }
        }
    },
)
async def list_employees(
    response: Response,
    request_context: Annotated[
        RequestContext,
        Depends(get_authenticated_tenant_request_context),
    ],
    _authorized: Annotated[
        AuthenticatedSession,
        Depends(require_permission("employee:read:tenant")),
    ],
    service: Annotated[EmployeeService, Depends(get_employee_service)],
    filters: Annotated[EmployeeListFilters, Depends(get_employee_list_filters)],
    pagination: Annotated[EmployeeListPagination, Depends(get_employee_list_pagination)],
) -> list[EmployeeRead]:
    page = await service.list_employee_page(
        request_context.require_tenant().tenant_id,
        filters,
        pagination,
    )
    return phase0_plain_cursor_list(response, page)


@router.post(
    "",
    response_model=EmployeeRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create tenant employee",
    description=(
        "Creates an employee master-data record in the authenticated tenant session. Employee "
        "numbers and non-null work emails are normalized and must remain unique within that "
        "tenant; multiple null work emails are allowed and blank values are rejected. Lifecycle "
        "checks ensure lifecycle date rules are enforced before persistence. An optional "
        "X-Idempotency-Key replays the "
        "first successful response for an equivalent retry in this tenant."
    ),
    response_description="Created employee record.",
    responses={
        **IDEMPOTENT_EMPLOYEE_COMMAND_CONFLICT_RESPONSES,
        **IDEMPOTENCY_KEY_INVALID_RESPONSES,
    },
)
async def create_employee(
    payload: EmployeeCreate,
    request_context: Annotated[
        RequestContext,
        Depends(get_authenticated_tenant_request_context),
    ],
    _authorized: Annotated[
        AuthenticatedSession,
        Depends(require_permission("employee:update:tenant")),
    ],
    command_handler: Annotated[
        EmployeeCommandHandler,
        Depends(get_employee_command_handler),
    ],
    idempotency_key: Annotated[str | None, Depends(get_idempotency_key)],
) -> EmployeeRead:
    return await command_handler.create_employee(
        request_context.require_tenant().tenant_id,
        payload,
        idempotency_key,
        request_context=request_context,
    )


@router.get(
    "/{employee_id}",
    response_model=EmployeeRead,
    summary="Read tenant employee",
    description=(
        "Reads one employee profile only when it belongs to the current tenant. Employee IDs from "
        "other tenants return the same not-found envelope as missing records."
    ),
    response_description="Employee record.",
)
async def get_employee(
    employee_id: UUID,
    request_context: Annotated[
        RequestContext,
        Depends(get_authenticated_tenant_request_context),
    ],
    _authorized: Annotated[
        AuthenticatedSession,
        Depends(require_permission("employee:read:tenant")),
    ],
    service: Annotated[EmployeeService, Depends(get_employee_service)],
) -> EmployeeRead:
    return await service.get_employee_read(
        request_context.require_tenant().tenant_id,
        employee_id,
    )


@router.patch(
    "/{employee_id}",
    response_model=EmployeeRead,
    summary="Update tenant employee",
    description=(
        "Partially updates an employee master-data record in the current tenant while preserving "
        "tenant isolation, normalized employee number/work-email uniqueness, and employment "
        "lifecycle date rules. Clients may send the last-read version for optimistic conflict "
        "detection; omitting it preserves the existing compatible patch contract."
    ),
    response_description="Updated employee record.",
    responses=EMPLOYEE_COMMAND_CONFLICT_RESPONSES,
)
async def update_employee(
    employee_id: UUID,
    payload: EmployeeUpdate,
    request_context: Annotated[
        RequestContext,
        Depends(get_authenticated_tenant_request_context),
    ],
    _authorized: Annotated[
        AuthenticatedSession,
        Depends(require_permission("employee:update:tenant")),
    ],
    command_handler: Annotated[
        EmployeeCommandHandler,
        Depends(get_employee_command_handler),
    ],
) -> EmployeeRead:
    return await command_handler.update_employee(
        request_context.require_tenant().tenant_id,
        employee_id,
        payload,
        request_context=request_context,
    )


@router.post(
    "/{employee_id}/lifecycle-transitions",
    response_model=EmployeeLifecycleRead,
    summary="Transition employee lifecycle",
    description=(
        "Performs the explicit active, on-leave, or terminal transition for one tenant employee. "
        "Termination requires an optimistic employee version, effective date, and allowlisted "
        "reason code; it atomically closes the open assignment, disables only the linked tenant "
        "membership, revokes that membership's active refresh families, and retains history."
    ),
    response_description="Current employee lifecycle state.",
    responses=EMPLOYEE_COMMAND_CONFLICT_RESPONSES,
)
async def transition_employee_lifecycle(
    employee_id: UUID,
    payload: EmployeeLifecycleTransition,
    request_context: Annotated[
        RequestContext,
        Depends(get_authenticated_tenant_request_context),
    ],
    _authorized: Annotated[
        AuthenticatedSession,
        Depends(require_permission("employee:update:tenant")),
    ],
    command_handler: Annotated[
        EmployeeCommandHandler,
        Depends(get_employee_command_handler),
    ],
) -> EmployeeLifecycleRead:
    return await command_handler.transition_employee_lifecycle(
        request_context.require_tenant().tenant_id,
        employee_id,
        payload,
        request_context=request_context,
    )


@router.post(
    "/{employee_id}/archive",
    response_model=EmployeeLifecycleRead,
    summary="Archive a terminated employee",
    description=(
        "Soft-archives a terminated employee while retaining employee, profile, account-link, "
        "assignment, and audit history. The action is idempotent after a successful archive and "
        "the retained Employee 360 record remains available by direct URL to authorized HR users."
    ),
    response_description="Archived employee lifecycle state.",
    responses=EMPLOYEE_COMMAND_CONFLICT_RESPONSES,
)
async def archive_employee(
    employee_id: UUID,
    payload: EmployeeArchive,
    request_context: Annotated[
        RequestContext,
        Depends(get_authenticated_tenant_request_context),
    ],
    _authorized: Annotated[
        AuthenticatedSession,
        Depends(require_permission("employee:update:tenant")),
    ],
    command_handler: Annotated[
        EmployeeCommandHandler,
        Depends(get_employee_command_handler),
    ],
) -> EmployeeLifecycleRead:
    return await command_handler.archive_employee(
        request_context.require_tenant().tenant_id,
        employee_id,
        payload,
        request_context=request_context,
    )


@router.delete(
    "/{employee_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Archive tenant employee (deprecated compatibility action)",
    deprecated=True,
    description=(
        "Compatibility alias for soft archive. Archive is allowed only after termination; the "
        "record and all dependent history remain retained, normal directory projections hide it, "
        "and authorized HR users can still read Employee 360 by direct URL. Prefer POST on the "
        "explicit /archive action with an expected version."
    ),
    response_description="Employee archive completed.",
    responses=EMPLOYEE_COMMAND_CONFLICT_RESPONSES,
)
async def delete_employee(
    employee_id: UUID,
    request_context: Annotated[
        RequestContext,
        Depends(get_authenticated_tenant_request_context),
    ],
    _authorized: Annotated[
        AuthenticatedSession,
        Depends(require_permission("employee:update:tenant")),
    ],
    command_handler: Annotated[
        EmployeeCommandHandler,
        Depends(get_employee_command_handler),
    ],
) -> Response:
    await command_handler.delete_employee(
        request_context.require_tenant().tenant_id,
        employee_id,
        request_context=request_context,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
