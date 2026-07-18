"""Authenticated tenant setup-readiness API."""

from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth_dependencies import (
    AuthenticatedSession,
    get_application_settings,
    require_permission,
)
from app.api.dependencies import (
    get_authenticated_tenant_request_context,
    get_tenant_feature_service,
)
from app.api.errors import (
    AUTHENTICATION_REQUIRED_RESPONSES,
    AUTHORIZATION_RESPONSES,
    UNEXPECTED_ERROR_RESPONSES,
)
from app.api.openapi import TENANT_SETTINGS_TAG, with_correlation_response_headers
from app.core.config import Settings
from app.db.session import get_session
from app.modules.documents import DOCUMENT_RUNTIME_STATE_KEY, DocumentRuntime
from app.platform.request_context import RequestContext
from app.platform.responses import DataEnvelope, data_envelope
from app.schemas.tenant_readiness import TenantReadinessRead
from app.services.tenant_feature_service import TenantFeatureService
from app.services.tenant_readiness_service import TenantReadinessService

router = APIRouter(
    prefix="/api/v1/tenant",
    tags=[TENANT_SETTINGS_TAG],
    responses=with_correlation_response_headers(
        {
            **AUTHENTICATION_REQUIRED_RESPONSES,
            **AUTHORIZATION_RESPONSES,
            **UNEXPECTED_ERROR_RESPONSES,
        }
    ),
)


def get_document_runtime(request: Request) -> DocumentRuntime:
    runtime = getattr(request.app.state, DOCUMENT_RUNTIME_STATE_KEY, None)
    if not isinstance(runtime, DocumentRuntime):
        raise RuntimeError("Employee document runtime is unavailable")
    return runtime


def get_tenant_readiness_service(
    session: Annotated[AsyncSession, Depends(get_session)],
    feature_service: Annotated[
        TenantFeatureService,
        Depends(get_tenant_feature_service),
    ],
    settings: Annotated[Settings, Depends(get_application_settings)],
    document_runtime: Annotated[DocumentRuntime, Depends(get_document_runtime)],
) -> TenantReadinessService:
    return TenantReadinessService(
        session=session,
        feature_service=feature_service,
        settings=settings,
        document_runtime=document_runtime,
    )


@router.get(
    "/readiness",
    response_model=DataEnvelope[TenantReadinessRead],
    summary="Read tenant setup readiness",
    description=(
        "Returns a fixed, read-only setup checklist for the authenticated tenant. Tenant, "
        "actor, and membership scope come only from the validated live session, and the "
        "projection exposes bounded aggregate facts without resource identities."
    ),
    response_description="Current bounded tenant setup-readiness projection.",
    responses=with_correlation_response_headers({200: {}}),
)
async def get_tenant_readiness(
    response: Response,
    request_context: Annotated[
        RequestContext,
        Depends(get_authenticated_tenant_request_context),
    ],
    _authorized: Annotated[
        AuthenticatedSession,
        Depends(require_permission("organization:update:tenant")),
    ],
    service: Annotated[
        TenantReadinessService,
        Depends(get_tenant_readiness_service),
    ],
) -> DataEnvelope[TenantReadinessRead]:
    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"
    readiness = await service.get(request_context=request_context)
    return data_envelope(readiness, request_context)


__all__ = ["router"]
