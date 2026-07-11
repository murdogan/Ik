from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_phase0_tenant_request_context
from app.api.openapi import DASHBOARD_TAG
from app.db.session import get_session
from app.platform.request_context import RequestContext
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
    summary="Read tenant dashboard summary",
    description=(
        "Reads HR operating metrics for the current tenant from the tenant header context, "
        "including active workforce counts, pending leave workload, department distribution, "
        "new starters, and recent activity."
    ),
    response_description="Dashboard summary metrics.",
)
async def dashboard_summary(
    request_context: Annotated[
        RequestContext,
        Depends(get_phase0_tenant_request_context),
    ],
    service: Annotated[DashboardService, Depends(get_dashboard_service)],
) -> DashboardSummary:
    return await service.get_summary(request_context.require_tenant().tenant_id)
