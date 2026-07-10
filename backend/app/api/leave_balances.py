from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_tenant_context
from app.api.errors import LEAVE_BALANCE_VALIDATION_RESPONSES, employee_not_found_error
from app.api.openapi import LEAVE_BALANCES_TAG
from app.core.tenancy import TenantContext
from app.db.session import get_session
from app.schemas.leave_balance_summary import LeaveBalanceSummaryRead
from app.services.leave_balance_service import (
    LeaveBalanceEmployeeNotFoundError,
    LeaveBalanceService,
)

router = APIRouter(
    prefix="/api/v1/employees",
    tags=[LEAVE_BALANCES_TAG],
    responses=LEAVE_BALANCE_VALIDATION_RESPONSES,
)


def get_leave_balance_service(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> LeaveBalanceService:
    return LeaveBalanceService(session=session)


@router.get(
    "/{employee_id}/leave-balances",
    response_model=list[LeaveBalanceSummaryRead],
    summary="List employee leave balance summaries",
    description=(
        "Lists stored manual leave balance summary rows for one employee in the current tenant. "
        "This read-only placeholder does not calculate accruals, synthesize rows from leave "
        "requests, or call external integrations."
    ),
    response_description="Employee leave balance summary list.",
)
async def list_employee_leave_balances(
    employee_id: UUID,
    tenant_context: Annotated[TenantContext, Depends(get_tenant_context)],
    service: Annotated[LeaveBalanceService, Depends(get_leave_balance_service)],
    period_year: Annotated[
        int | None,
        Query(
            ge=1900,
            le=2200,
            description="Filters balance summaries to a single period year.",
        ),
    ] = None,
) -> list[LeaveBalanceSummaryRead]:
    try:
        return await service.list_employee_balance_summaries(
            tenant_context.tenant_id,
            employee_id,
            period_year,
        )
    except LeaveBalanceEmployeeNotFoundError as exc:
        raise employee_not_found_error() from exc
