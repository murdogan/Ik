from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_tenant_context, get_unit_of_work
from app.api.errors import EMPLOYEE_COMMAND_CONFLICT_RESPONSES, EMPLOYEE_VALIDATION_RESPONSES
from app.api.openapi import EMPLOYEES_TAG
from app.db.session import get_session
from app.models.employee import EmployeeStatus
from app.platform.db import SqlAlchemyUnitOfWork
from app.platform.tenancy import TenantContext
from app.schemas.employee import (
    EMPLOYEE_LIST_DEFAULT_LIMIT,
    EMPLOYEE_LIST_MAX_LIMIT,
    EmployeeCreate,
    EmployeeListFilters,
    EmployeeListPagination,
    EmployeeRead,
    EmployeeUpdate,
)
from app.services.employee_commands import EmployeeCommandHandler
from app.services.employee_service import EmployeeService

router = APIRouter(
    prefix="/api/v1/employees",
    tags=[EMPLOYEES_TAG],
    responses=EMPLOYEE_VALIDATION_RESPONSES,
)


def get_employee_service(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> EmployeeService:
    return EmployeeService(session=session)


def get_employee_command_handler(
    service: Annotated[EmployeeService, Depends(get_employee_service)],
    unit_of_work: Annotated[SqlAlchemyUnitOfWork, Depends(get_unit_of_work)],
) -> EmployeeCommandHandler:
    return EmployeeCommandHandler(service=service, unit_of_work=unit_of_work)


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
                "Case-insensitive search over employee_number and email within the tenant."
            ),
            max_length=320,
        ),
    ] = None,
) -> EmployeeListFilters:
    return EmployeeListFilters(department=department, status=status_filter, q=q)


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
            description=(
                "Number of matching tenant employees to skip before returning results."
            ),
        ),
    ] = 0,
) -> EmployeeListPagination:
    return EmployeeListPagination(limit=limit, offset=offset)


@router.get(
    "",
    response_model=list[EmployeeRead],
    summary="List tenant employees",
    description=(
        "Lists employee directory records for the current tenant from the tenant header context. "
        "Optional filters cover department, lifecycle status, and employee number or email "
        "search; tenant isolation is applied before bounded limit/offset pagination."
    ),
    response_description="Employee list.",
)
async def list_employees(
    tenant_context: Annotated[TenantContext, Depends(get_tenant_context)],
    service: Annotated[EmployeeService, Depends(get_employee_service)],
    filters: Annotated[EmployeeListFilters, Depends(get_employee_list_filters)],
    pagination: Annotated[EmployeeListPagination, Depends(get_employee_list_pagination)],
) -> list[EmployeeRead]:
    return await service.list_employees(tenant_context.tenant_id, filters, pagination)


@router.post(
    "",
    response_model=EmployeeRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create tenant employee",
    description=(
        "Creates an employee master-data record in the current tenant from the tenant header "
        "context. Employee numbers must remain unique within that tenant, and lifecycle date "
        "rules are enforced before persistence."
    ),
    response_description="Created employee record.",
    responses=EMPLOYEE_COMMAND_CONFLICT_RESPONSES,
)
async def create_employee(
    payload: EmployeeCreate,
    tenant_context: Annotated[TenantContext, Depends(get_tenant_context)],
    command_handler: Annotated[
        EmployeeCommandHandler,
        Depends(get_employee_command_handler),
    ],
) -> EmployeeRead:
    return await command_handler.create_employee(tenant_context.tenant_id, payload)


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
    tenant_context: Annotated[TenantContext, Depends(get_tenant_context)],
    service: Annotated[EmployeeService, Depends(get_employee_service)],
) -> EmployeeRead:
    return await service.get_employee(tenant_context.tenant_id, employee_id)


@router.patch(
    "/{employee_id}",
    response_model=EmployeeRead,
    summary="Update tenant employee",
    description=(
        "Partially updates an employee master-data record in the current tenant while preserving "
        "tenant isolation, employee number uniqueness, and employment lifecycle date rules."
    ),
    response_description="Updated employee record.",
    responses=EMPLOYEE_COMMAND_CONFLICT_RESPONSES,
)
async def update_employee(
    employee_id: UUID,
    payload: EmployeeUpdate,
    tenant_context: Annotated[TenantContext, Depends(get_tenant_context)],
    command_handler: Annotated[
        EmployeeCommandHandler,
        Depends(get_employee_command_handler),
    ],
) -> EmployeeRead:
    return await command_handler.update_employee(
        tenant_context.tenant_id,
        employee_id,
        payload,
    )


@router.delete(
    "/{employee_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete tenant employee",
    description=(
        "Deletes an employee record by id only when it belongs to the current tenant. Employee "
        "IDs from other tenants return the same not-found envelope as missing records."
    ),
    response_description="Employee deletion completed.",
    responses=EMPLOYEE_COMMAND_CONFLICT_RESPONSES,
)
async def delete_employee(
    employee_id: UUID,
    tenant_context: Annotated[TenantContext, Depends(get_tenant_context)],
    command_handler: Annotated[
        EmployeeCommandHandler,
        Depends(get_employee_command_handler),
    ],
) -> Response:
    await command_handler.delete_employee(tenant_context.tenant_id, employee_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
