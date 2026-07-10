from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_tenant_context
from app.api.openapi import DASHBOARD_TAG
from app.core.tenancy import TenantContext
from app.db.session import get_session
from app.schemas.dashboard import DashboardSummary
from app.services.dashboard_service import DashboardService

router = APIRouter(prefix="/api/v1/dashboard", tags=[DASHBOARD_TAG])


def get_dashboard_service(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> DashboardService:
    return DashboardService(session=session)


@router.get(
    "/summary",
    response_model=DashboardSummary,
    summary="Get tenant dashboard summary",
    description=(
        "Returns tenant-scoped HR operating metrics from the tenant header context, including "
        "active workforce counts, pending leave workload, department distribution, new starters, "
        "and recent activity."
    ),
    response_description="Dashboard summary metrics.",
)
async def dashboard_summary(
    tenant_context: Annotated[TenantContext, Depends(get_tenant_context)],
    service: Annotated[DashboardService, Depends(get_dashboard_service)],
) -> DashboardSummary:
    return await service.get_summary(tenant_context.tenant_id)
