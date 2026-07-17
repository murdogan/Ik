from typing import Annotated

from fastapi import APIRouter, Depends, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth_dependencies import AuthenticatedSession, require_any_permission
from app.api.dependencies import get_authenticated_tenant_request_context
from app.api.errors import AUTHENTICATION_REQUIRED_RESPONSES, AUTHORIZATION_RESPONSES
from app.api.openapi import DASHBOARD_TAG
from app.db.session import get_session
from app.platform.request_context import RequestContext
from app.schemas.dashboard import DashboardSummary
from app.services.dashboard_service import DashboardService

router = APIRouter(
    prefix="/api/v1/dashboard",
    tags=[DASHBOARD_TAG],
    responses={
        **AUTHENTICATION_REQUIRED_RESPONSES,
        **AUTHORIZATION_RESPONSES,
    },
)


def get_dashboard_service(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> DashboardService:
    return DashboardService(session=session)


@router.get(
    "/summary",
    response_model=DashboardSummary,
    summary="Read tenant dashboard summary",
    description=(
        "Reads HR operating metrics for the authenticated tenant session, "
        "including active workforce counts, pending leave workload, department distribution, "
        "new starters, and recent activity."
    ),
    response_description="Dashboard summary metrics.",
)
async def dashboard_summary(
    response: Response,
    request_context: Annotated[
        RequestContext,
        Depends(get_authenticated_tenant_request_context),
    ],
    authorized: Annotated[
        AuthenticatedSession,
        Depends(
            require_any_permission(
                "dashboard:read:tenant",
                "dashboard:read:team",
                "dashboard:read:own",
            )
        ),
    ],
    service: Annotated[DashboardService, Depends(get_dashboard_service)],
) -> DashboardSummary:
    if request_context.actor_id is None:
        raise RuntimeError("Dashboard actor context is unavailable")
    summary = await service.get_summary(
        request_context.require_tenant().tenant_id,
        actor_id=request_context.actor_id,
        permissions=authorized.user.permissions,
    )
    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"
    return summary
