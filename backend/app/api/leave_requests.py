from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_tenant_context, get_unit_of_work
from app.api.errors import (
    LEAVE_REQUEST_DECISION_CONFLICT_RESPONSES,
    LEAVE_REQUEST_PERSISTENCE_CONFLICT_RESPONSES,
    LEAVE_REQUEST_VALIDATION_RESPONSES,
    leave_request_date_range_error,
)
from app.api.openapi import LEAVE_REQUESTS_TAG
from app.core.error_messages import LEAVE_REQUEST_FILTER_END_DATE_ON_OR_AFTER_START_DATE_MESSAGE
from app.db.session import get_session
from app.models.leave_request import LeaveRequestStatus
from app.platform.db import SqlAlchemyUnitOfWork
from app.platform.tenancy import TenantContext
from app.schemas.date_fields import DateOnly
from app.schemas.leave_request import (
    LEAVE_REQUEST_LIST_DEFAULT_LIMIT,
    LEAVE_REQUEST_LIST_MAX_LIMIT,
    LeaveRequestCreate,
    LeaveRequestDecision,
    LeaveRequestListFilters,
    LeaveRequestListPagination,
    LeaveRequestRead,
)
from app.services.leave_request_commands import LeaveRequestCommandHandler
from app.services.leave_request_service import LeaveRequestService

router = APIRouter(
    prefix="/api/v1/leave-requests",
    tags=[LEAVE_REQUESTS_TAG],
    responses=LEAVE_REQUEST_VALIDATION_RESPONSES,
)


def get_leave_request_service(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> LeaveRequestService:
    return LeaveRequestService(session=session)


def get_leave_request_command_handler(
    service: Annotated[LeaveRequestService, Depends(get_leave_request_service)],
    unit_of_work: Annotated[SqlAlchemyUnitOfWork, Depends(get_unit_of_work)],
) -> LeaveRequestCommandHandler:
    return LeaveRequestCommandHandler(service=service, unit_of_work=unit_of_work)


def get_leave_request_list_filters(
    status_filter: Annotated[
        LeaveRequestStatus | None,
        Query(alias="status", description="Filters by leave request workflow status."),
    ] = None,
    employee_id: Annotated[
        UUID | None,
        Query(description="Filters to leave requests for one employee in the current tenant."),
    ] = None,
    start_date: Annotated[
        DateOnly | None,
        Query(description="Inclusive start of the leave date window to overlap."),
    ] = None,
    end_date: Annotated[
        DateOnly | None,
        Query(description="Inclusive end of the leave date window to overlap."),
    ] = None,
) -> LeaveRequestListFilters:
    if start_date is not None and end_date is not None and end_date < start_date:
        raise leave_request_date_range_error(
            LEAVE_REQUEST_FILTER_END_DATE_ON_OR_AFTER_START_DATE_MESSAGE
        )
    return LeaveRequestListFilters(
        status=status_filter,
        employee_id=employee_id,
        start_date=start_date,
        end_date=end_date,
    )


def get_leave_request_list_pagination(
    limit: Annotated[
        int,
        Query(
            ge=1,
            le=LEAVE_REQUEST_LIST_MAX_LIMIT,
            description=(
                "Maximum leave requests to return for this tenant. Bounded to protect large "
                "lists."
            ),
        ),
    ] = LEAVE_REQUEST_LIST_DEFAULT_LIMIT,
    offset: Annotated[
        int,
        Query(
            ge=0,
            description=(
                "Number of matching tenant leave requests to skip before returning results."
            ),
        ),
    ] = 0,
) -> LeaveRequestListPagination:
    return LeaveRequestListPagination(limit=limit, offset=offset)


@router.get(
    "",
    response_model=list[LeaveRequestRead],
    summary="List tenant leave requests",
    description=(
        "Lists leave request review records for the current tenant from the tenant header "
        "context. Optional filters cover workflow status, employee, and overlapping date "
        "windows; tenant isolation is applied before bounded limit/offset pagination."
    ),
    response_description="Leave request list.",
)
async def list_leave_requests(
    tenant_context: Annotated[TenantContext, Depends(get_tenant_context)],
    service: Annotated[LeaveRequestService, Depends(get_leave_request_service)],
    filters: Annotated[LeaveRequestListFilters, Depends(get_leave_request_list_filters)],
    pagination: Annotated[LeaveRequestListPagination, Depends(get_leave_request_list_pagination)],
) -> list[LeaveRequestRead]:
    return await service.list_leave_requests(tenant_context.tenant_id, filters, pagination)


@router.post(
    "",
    response_model=LeaveRequestRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create tenant leave request",
    description=(
        "Creates a pending leave request in the current tenant. The employee and requesting user "
        "must both belong to the tenant from the request headers, and leave dates must be "
        "ordered before persistence."
    ),
    response_description="Created leave request record.",
    responses=LEAVE_REQUEST_PERSISTENCE_CONFLICT_RESPONSES,
)
async def create_leave_request(
    payload: LeaveRequestCreate,
    tenant_context: Annotated[TenantContext, Depends(get_tenant_context)],
    command_handler: Annotated[
        LeaveRequestCommandHandler,
        Depends(get_leave_request_command_handler),
    ],
) -> LeaveRequestRead:
    return await command_handler.create_leave_request(tenant_context.tenant_id, payload)


@router.post(
    "/{leave_request_id}/approve",
    response_model=LeaveRequestRead,
    summary="Approve pending leave request",
    description=(
        "Approves a pending leave request in the current tenant and records the supplied "
        "decision metadata. Leave request IDs from other tenants return the same not-found "
        "envelope as missing records."
    ),
    response_description="Approved leave request record.",
    responses=LEAVE_REQUEST_DECISION_CONFLICT_RESPONSES,
)
async def approve_leave_request(
    leave_request_id: UUID,
    payload: LeaveRequestDecision,
    tenant_context: Annotated[TenantContext, Depends(get_tenant_context)],
    command_handler: Annotated[
        LeaveRequestCommandHandler,
        Depends(get_leave_request_command_handler),
    ],
) -> LeaveRequestRead:
    return await command_handler.approve_leave_request(
        tenant_context.tenant_id,
        leave_request_id,
        payload,
    )


@router.post(
    "/{leave_request_id}/reject",
    response_model=LeaveRequestRead,
    summary="Reject pending leave request",
    description=(
        "Rejects a pending leave request in the current tenant and records the supplied decision "
        "metadata. Leave request IDs from other tenants return the same not-found envelope as "
        "missing records."
    ),
    response_description="Rejected leave request record.",
    responses=LEAVE_REQUEST_DECISION_CONFLICT_RESPONSES,
)
async def reject_leave_request(
    leave_request_id: UUID,
    payload: LeaveRequestDecision,
    tenant_context: Annotated[TenantContext, Depends(get_tenant_context)],
    command_handler: Annotated[
        LeaveRequestCommandHandler,
        Depends(get_leave_request_command_handler),
    ],
) -> LeaveRequestRead:
    return await command_handler.reject_leave_request(
        tenant_context.tenant_id,
        leave_request_id,
        payload,
    )


@router.post(
    "/{leave_request_id}/cancel",
    response_model=LeaveRequestRead,
    summary="Cancel pending leave request",
    description=(
        "Cancels a pending leave request in the current tenant and records the supplied decision "
        "metadata. Leave request IDs from other tenants return the same not-found envelope as "
        "missing records."
    ),
    response_description="Cancelled leave request record.",
    responses=LEAVE_REQUEST_DECISION_CONFLICT_RESPONSES,
)
async def cancel_leave_request(
    leave_request_id: UUID,
    payload: LeaveRequestDecision,
    tenant_context: Annotated[TenantContext, Depends(get_tenant_context)],
    command_handler: Annotated[
        LeaveRequestCommandHandler,
        Depends(get_leave_request_command_handler),
    ],
) -> LeaveRequestRead:
    return await command_handler.cancel_leave_request(
        tenant_context.tenant_id,
        leave_request_id,
        payload,
    )
