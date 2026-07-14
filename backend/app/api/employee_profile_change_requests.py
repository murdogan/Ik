"""Employee-own and HR decision APIs for P4E personal-profile requests."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth_dependencies import AuthenticatedSession, require_permission
from app.api.dependencies import get_authenticated_tenant_request_context, get_unit_of_work
from app.api.errors import (
    AUTHENTICATION_REQUIRED_RESPONSES,
    AUTHORIZATION_RESPONSES,
    EMPLOYEE_PROFILE_CHANGE_REQUEST_CONFLICT_RESPONSES,
    EMPLOYEE_PROFILE_CHANGE_REQUEST_NOT_FOUND_RESPONSES,
    EMPLOYEE_PROFILE_CHANGE_REQUEST_VALIDATION_RESPONSES,
)
from app.api.openapi import EMPLOYEES_TAG, with_correlation_response_headers
from app.db.session import get_session
from app.models.employee_profile_change_request import EmployeeProfileChangeRequestStatus
from app.platform.db import SqlAlchemyUnitOfWork
from app.platform.pagination import MAX_CURSOR_LENGTH
from app.platform.request_context import RequestContext
from app.platform.responses import (
    DataEnvelope,
    ListEnvelope,
    data_envelope,
    list_envelope,
)
from app.schemas.employee_profile_change_request import (
    PROFILE_CHANGE_REQUEST_LIMIT_DEFAULT,
    PROFILE_CHANGE_REQUEST_LIMIT_MAX,
    EmployeeProfileChangeRequestCreate,
    EmployeeProfileChangeRequestExpectedVersion,
    EmployeeProfileChangeRequestHrDetailRead,
    EmployeeProfileChangeRequestHrSummaryRead,
    EmployeeProfileChangeRequestReject,
    OwnEmployeeProfileChangeRequestRead,
)
from app.services.audit_recorder import SqlAlchemyAuditRecorder
from app.services.employee_profile_change_request_commands import (
    EmployeeProfileChangeRequestCommandHandler,
)
from app.services.employee_profile_change_request_service import (
    EMPLOYEE_READ_TENANT_PERMISSION,
    EMPLOYEE_UPDATE_TENANT_PERMISSION,
    EmployeeProfileChangeRequestService,
)

own_router = APIRouter(
    prefix="/api/v1/me/profile-change-requests",
    tags=[EMPLOYEES_TAG],
    responses=with_correlation_response_headers(
        {
            **AUTHENTICATION_REQUIRED_RESPONSES,
            **AUTHORIZATION_RESPONSES,
            **EMPLOYEE_PROFILE_CHANGE_REQUEST_VALIDATION_RESPONSES,
        }
    ),
)
router = APIRouter(
    prefix="/api/v1/employee-profile-change-requests",
    tags=[EMPLOYEES_TAG],
    responses=with_correlation_response_headers(
        {
            **AUTHENTICATION_REQUIRED_RESPONSES,
            **AUTHORIZATION_RESPONSES,
            **EMPLOYEE_PROFILE_CHANGE_REQUEST_VALIDATION_RESPONSES,
        }
    ),
)


def get_employee_profile_change_request_service(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> EmployeeProfileChangeRequestService:
    return EmployeeProfileChangeRequestService(session)


def get_employee_profile_change_request_command_handler(
    service: Annotated[
        EmployeeProfileChangeRequestService,
        Depends(get_employee_profile_change_request_service),
    ],
    unit_of_work: Annotated[SqlAlchemyUnitOfWork, Depends(get_unit_of_work)],
) -> EmployeeProfileChangeRequestCommandHandler:
    return EmployeeProfileChangeRequestCommandHandler(
        service=service,
        unit_of_work=unit_of_work,
        audit_recorder=SqlAlchemyAuditRecorder(service.session),
    )


@own_router.post(
    "",
    response_model=DataEnvelope[OwnEmployeeProfileChangeRequestRead],
    status_code=status.HTTP_201_CREATED,
    summary="Submit my personal-profile change request",
    description=(
        "Creates one approval request for selected requestable personal fields using only the "
        "authenticated membership's live canonical employee link. The profile is not changed."
    ),
    responses=with_correlation_response_headers(
        {
            status.HTTP_201_CREATED: {},
            **EMPLOYEE_PROFILE_CHANGE_REQUEST_CONFLICT_RESPONSES,
        }
    ),
)
async def submit_own_profile_change_request(
    payload: EmployeeProfileChangeRequestCreate,
    response: Response,
    request_context: Annotated[
        RequestContext,
        Depends(get_authenticated_tenant_request_context),
    ],
    _authorized: Annotated[
        AuthenticatedSession,
        Depends(require_permission("employee:read:own")),
    ],
    handler: Annotated[
        EmployeeProfileChangeRequestCommandHandler,
        Depends(get_employee_profile_change_request_command_handler),
    ],
) -> DataEnvelope[OwnEmployeeProfileChangeRequestRead]:
    _prevent_storage(response)
    result = await handler.submit_own(payload, request_context=request_context)
    return data_envelope(result, request_context)


@own_router.get(
    "",
    response_model=ListEnvelope[OwnEmployeeProfileChangeRequestRead],
    summary="List my personal-profile change requests",
    description=(
        "Returns only requests authored through the authenticated membership's current canonical "
        "employee link, newest first, with own-scope masking."
    ),
    responses=with_correlation_response_headers(
        {status.HTTP_200_OK: {}, **EMPLOYEE_PROFILE_CHANGE_REQUEST_CONFLICT_RESPONSES}
    ),
)
async def list_own_profile_change_requests(
    response: Response,
    request_context: Annotated[
        RequestContext,
        Depends(get_authenticated_tenant_request_context),
    ],
    _authorized: Annotated[
        AuthenticatedSession,
        Depends(require_permission("employee:read:own")),
    ],
    service: Annotated[
        EmployeeProfileChangeRequestService,
        Depends(get_employee_profile_change_request_service),
    ],
    limit: Annotated[
        int,
        Query(ge=1, le=PROFILE_CHANGE_REQUEST_LIMIT_MAX),
    ] = PROFILE_CHANGE_REQUEST_LIMIT_DEFAULT,
    cursor: Annotated[
        str | None,
        Query(min_length=1, max_length=MAX_CURSOR_LENGTH),
    ] = None,
) -> ListEnvelope[OwnEmployeeProfileChangeRequestRead]:
    _prevent_storage(response)
    actor_user_id = _actor_id(request_context)
    page = await service.list_own(
        tenant_id=request_context.require_tenant().tenant_id,
        membership_id=request_context.require_membership(),
        actor_user_id=actor_user_id,
        limit=limit,
        cursor=cursor,
    )
    return list_envelope(
        page.items,
        request_context,
        limit=limit,
        next_cursor=page.next_cursor,
    )


@own_router.get(
    "/{request_id}",
    response_model=DataEnvelope[OwnEmployeeProfileChangeRequestRead],
    summary="Read my personal-profile change request",
    responses=with_correlation_response_headers(
        {
            status.HTTP_200_OK: {},
            **EMPLOYEE_PROFILE_CHANGE_REQUEST_NOT_FOUND_RESPONSES,
            **EMPLOYEE_PROFILE_CHANGE_REQUEST_CONFLICT_RESPONSES,
        }
    ),
)
async def get_own_profile_change_request(
    request_id: UUID,
    response: Response,
    request_context: Annotated[
        RequestContext,
        Depends(get_authenticated_tenant_request_context),
    ],
    _authorized: Annotated[
        AuthenticatedSession,
        Depends(require_permission("employee:read:own")),
    ],
    service: Annotated[
        EmployeeProfileChangeRequestService,
        Depends(get_employee_profile_change_request_service),
    ],
) -> DataEnvelope[OwnEmployeeProfileChangeRequestRead]:
    _prevent_storage(response)
    result = await service.get_own(
        tenant_id=request_context.require_tenant().tenant_id,
        membership_id=request_context.require_membership(),
        actor_user_id=_actor_id(request_context),
        request_id=request_id,
    )
    return data_envelope(result, request_context)


@own_router.post(
    "/{request_id}/cancel",
    response_model=DataEnvelope[OwnEmployeeProfileChangeRequestRead],
    summary="Cancel my submitted personal-profile change request",
    responses=with_correlation_response_headers(
        {
            status.HTTP_200_OK: {},
            **EMPLOYEE_PROFILE_CHANGE_REQUEST_NOT_FOUND_RESPONSES,
            **EMPLOYEE_PROFILE_CHANGE_REQUEST_CONFLICT_RESPONSES,
        }
    ),
)
async def cancel_own_profile_change_request(
    request_id: UUID,
    payload: EmployeeProfileChangeRequestExpectedVersion,
    response: Response,
    request_context: Annotated[
        RequestContext,
        Depends(get_authenticated_tenant_request_context),
    ],
    _authorized: Annotated[
        AuthenticatedSession,
        Depends(require_permission("employee:read:own")),
    ],
    handler: Annotated[
        EmployeeProfileChangeRequestCommandHandler,
        Depends(get_employee_profile_change_request_command_handler),
    ],
) -> DataEnvelope[OwnEmployeeProfileChangeRequestRead]:
    _prevent_storage(response)
    result = await handler.cancel_own(
        request_id,
        payload,
        request_context=request_context,
    )
    return data_envelope(result, request_context)


@router.get(
    "",
    response_model=ListEnvelope[EmployeeProfileChangeRequestHrSummaryRead],
    summary="List the tenant personal-profile decision queue",
    description=(
        "Returns a bounded tenant queue with no proposed personal values. The default is submitted "
        "requests ordered oldest first. Both tenant employee read and update grants are required."
    ),
    responses=with_correlation_response_headers({status.HTTP_200_OK: {}}),
)
async def list_hr_profile_change_requests(
    response: Response,
    request_context: Annotated[
        RequestContext,
        Depends(get_authenticated_tenant_request_context),
    ],
    authorized: Annotated[
        AuthenticatedSession,
        Depends(require_permission(EMPLOYEE_READ_TENANT_PERMISSION)),
    ],
    _authorized_update: Annotated[
        AuthenticatedSession,
        Depends(require_permission(EMPLOYEE_UPDATE_TENANT_PERMISSION)),
    ],
    service: Annotated[
        EmployeeProfileChangeRequestService,
        Depends(get_employee_profile_change_request_service),
    ],
    status_filter: Annotated[
        EmployeeProfileChangeRequestStatus,
        Query(alias="status"),
    ] = EmployeeProfileChangeRequestStatus.SUBMITTED,
    limit: Annotated[
        int,
        Query(ge=1, le=PROFILE_CHANGE_REQUEST_LIMIT_MAX),
    ] = PROFILE_CHANGE_REQUEST_LIMIT_DEFAULT,
    cursor: Annotated[
        str | None,
        Query(min_length=1, max_length=MAX_CURSOR_LENGTH),
    ] = None,
) -> ListEnvelope[EmployeeProfileChangeRequestHrSummaryRead]:
    _prevent_storage(response)
    page = await service.list_hr(
        tenant_id=request_context.require_tenant().tenant_id,
        granted_permissions=authorized.user.permissions,
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


@router.get(
    "/{request_id}",
    response_model=DataEnvelope[EmployeeProfileChangeRequestHrDetailRead],
    summary="Read a tenant personal-profile change request",
    responses=with_correlation_response_headers(
        {status.HTTP_200_OK: {}, **EMPLOYEE_PROFILE_CHANGE_REQUEST_NOT_FOUND_RESPONSES}
    ),
)
async def get_hr_profile_change_request(
    request_id: UUID,
    response: Response,
    request_context: Annotated[
        RequestContext,
        Depends(get_authenticated_tenant_request_context),
    ],
    authorized: Annotated[
        AuthenticatedSession,
        Depends(require_permission(EMPLOYEE_READ_TENANT_PERMISSION)),
    ],
    _authorized_update: Annotated[
        AuthenticatedSession,
        Depends(require_permission(EMPLOYEE_UPDATE_TENANT_PERMISSION)),
    ],
    service: Annotated[
        EmployeeProfileChangeRequestService,
        Depends(get_employee_profile_change_request_service),
    ],
) -> DataEnvelope[EmployeeProfileChangeRequestHrDetailRead]:
    _prevent_storage(response)
    result = await service.get_hr(
        tenant_id=request_context.require_tenant().tenant_id,
        granted_permissions=authorized.user.permissions,
        request_id=request_id,
    )
    return data_envelope(result, request_context)


@router.post(
    "/{request_id}/approve",
    response_model=DataEnvelope[EmployeeProfileChangeRequestHrDetailRead],
    summary="Approve a submitted personal-profile change request",
    responses=with_correlation_response_headers(
        {
            status.HTTP_200_OK: {},
            **EMPLOYEE_PROFILE_CHANGE_REQUEST_NOT_FOUND_RESPONSES,
            **EMPLOYEE_PROFILE_CHANGE_REQUEST_CONFLICT_RESPONSES,
        }
    ),
)
async def approve_hr_profile_change_request(
    request_id: UUID,
    payload: EmployeeProfileChangeRequestExpectedVersion,
    response: Response,
    request_context: Annotated[
        RequestContext,
        Depends(get_authenticated_tenant_request_context),
    ],
    authorized: Annotated[
        AuthenticatedSession,
        Depends(require_permission(EMPLOYEE_READ_TENANT_PERMISSION)),
    ],
    _authorized_update: Annotated[
        AuthenticatedSession,
        Depends(require_permission(EMPLOYEE_UPDATE_TENANT_PERMISSION)),
    ],
    handler: Annotated[
        EmployeeProfileChangeRequestCommandHandler,
        Depends(get_employee_profile_change_request_command_handler),
    ],
) -> DataEnvelope[EmployeeProfileChangeRequestHrDetailRead]:
    _prevent_storage(response)
    result = await handler.approve(
        request_id,
        payload,
        request_context=request_context,
        granted_permissions=authorized.user.permissions,
    )
    return data_envelope(result, request_context)


@router.post(
    "/{request_id}/reject",
    response_model=DataEnvelope[EmployeeProfileChangeRequestHrDetailRead],
    summary="Reject a submitted personal-profile change request",
    responses=with_correlation_response_headers(
        {
            status.HTTP_200_OK: {},
            **EMPLOYEE_PROFILE_CHANGE_REQUEST_NOT_FOUND_RESPONSES,
            **EMPLOYEE_PROFILE_CHANGE_REQUEST_CONFLICT_RESPONSES,
        }
    ),
)
async def reject_hr_profile_change_request(
    request_id: UUID,
    payload: EmployeeProfileChangeRequestReject,
    response: Response,
    request_context: Annotated[
        RequestContext,
        Depends(get_authenticated_tenant_request_context),
    ],
    authorized: Annotated[
        AuthenticatedSession,
        Depends(require_permission(EMPLOYEE_READ_TENANT_PERMISSION)),
    ],
    _authorized_update: Annotated[
        AuthenticatedSession,
        Depends(require_permission(EMPLOYEE_UPDATE_TENANT_PERMISSION)),
    ],
    handler: Annotated[
        EmployeeProfileChangeRequestCommandHandler,
        Depends(get_employee_profile_change_request_command_handler),
    ],
) -> DataEnvelope[EmployeeProfileChangeRequestHrDetailRead]:
    _prevent_storage(response)
    result = await handler.reject(
        request_id,
        payload,
        request_context=request_context,
        granted_permissions=authorized.user.permissions,
    )
    return data_envelope(result, request_context)


def _actor_id(request_context: RequestContext) -> UUID:
    if request_context.actor_id is None:
        raise RuntimeError("Profile-change request context is missing its actor")
    return request_context.actor_id


def _prevent_storage(response: Response) -> None:
    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"


__all__ = ["own_router", "router"]
