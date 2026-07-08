from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_tenant_context
from app.core.tenancy import TenantContext
from app.db.session import get_session
from app.schemas.dashboard import DashboardSummary
from app.services.dashboard_service import DashboardService

router = APIRouter(prefix="/api/v1/dashboard", tags=["dashboard"])


def get_dashboard_service(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> DashboardService:
    return DashboardService(session=session)


@router.get("/summary", response_model=DashboardSummary)
async def dashboard_summary(
    tenant_context: Annotated[TenantContext, Depends(get_tenant_context)],
    service: Annotated[DashboardService, Depends(get_dashboard_service)],
) -> DashboardSummary:
    return await service.get_summary(tenant_context.tenant_id)
