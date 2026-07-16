"""Employee self-service home projection API."""

from typing import Annotated

from fastapi import APIRouter, Depends, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth_dependencies import AuthenticatedSession, require_permission
from app.api.dependencies import get_authenticated_tenant_request_context
from app.api.openapi import SELF_SERVICE_TAG
from app.db.session import get_session
from app.platform.request_context import RequestContext
from app.platform.responses import DataEnvelope, data_envelope
from app.schemas.self_service import SelfServiceHomeRead
from app.services.self_service_home_service import SelfServiceHomeService

router = APIRouter(prefix="/api/v1/self-service", tags=[SELF_SERVICE_TAG])


def get_service(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> SelfServiceHomeService:
    return SelfServiceHomeService(session)


@router.get("/home", response_model=DataEnvelope[SelfServiceHomeRead])
async def get_self_service_home(
    response: Response,
    request_context: Annotated[
        RequestContext, Depends(get_authenticated_tenant_request_context)
    ],
    _authorized: Annotated[
        AuthenticatedSession, Depends(require_permission("self_service:read:own"))
    ],
    service: Annotated[SelfServiceHomeService, Depends(get_service)],
) -> DataEnvelope[SelfServiceHomeRead]:
    response.headers["Cache-Control"] = "no-store"
    return data_envelope(await service.get(request_context=request_context), request_context)


__all__ = ["router"]
