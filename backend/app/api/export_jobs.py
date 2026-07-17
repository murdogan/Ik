"""Asynchronous private report export job APIs."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request, Response, status

from app.api.auth_dependencies import (
    AuthenticatedSession,
    get_application_settings,
    get_database_runtime,
    require_any_permission,
)
from app.api.dependencies import (
    get_authenticated_tenant_request_context,
    get_idempotency_key,
)
from app.api.errors import (
    AUTHENTICATION_REQUIRED_RESPONSES,
    AUTHORIZATION_RESPONSES,
    idempotency_key_invalid_error,
)
from app.api.openapi import EXPORTS_TAG, with_correlation_response_headers
from app.core.config import Settings
from app.db.session import DatabaseRuntime
from app.modules.documents import DOCUMENT_RUNTIME_STATE_KEY, DocumentRuntime
from app.platform.request_context import RequestContext
from app.platform.responses import DataEnvelope, data_envelope
from app.schemas.reporting import ExportDownloadIntentRead, ExportJobCreate, ExportJobRead
from app.services.export_job_service import ExportJobService
from app.services.reporting_access import (
    REPORT_EXPORT_TEAM_PERMISSION,
    REPORT_EXPORT_TENANT_PERMISSION,
)

router = APIRouter(
    prefix="/api/v1/export-jobs",
    tags=[EXPORTS_TAG],
    responses=with_correlation_response_headers(
        {**AUTHENTICATION_REQUIRED_RESPONSES, **AUTHORIZATION_RESPONSES}
    ),
)


def get_document_runtime(request: Request) -> DocumentRuntime:
    runtime = getattr(request.app.state, DOCUMENT_RUNTIME_STATE_KEY, None)
    if not isinstance(runtime, DocumentRuntime):
        raise RuntimeError("Private object runtime is unavailable")
    return runtime


def get_export_job_service(
    database_runtime: Annotated[DatabaseRuntime, Depends(get_database_runtime)],
    document_runtime: Annotated[DocumentRuntime, Depends(get_document_runtime)],
    settings: Annotated[Settings, Depends(get_application_settings)],
) -> ExportJobService:
    return ExportJobService(
        session_factory=database_runtime.session_factory,
        storage=document_runtime.storage,
        settings=settings,
    )


@router.post(
    "",
    response_model=DataEnvelope[ExportJobRead],
    status_code=status.HTTP_202_ACCEPTED,
)
async def create_export_job(
    payload: ExportJobCreate,
    response: Response,
    request_context: Annotated[
        RequestContext, Depends(get_authenticated_tenant_request_context)
    ],
    authorized: Annotated[
        AuthenticatedSession,
        Depends(
            require_any_permission(
                REPORT_EXPORT_TENANT_PERMISSION,
                REPORT_EXPORT_TEAM_PERMISSION,
            )
        ),
    ],
    service: Annotated[ExportJobService, Depends(get_export_job_service)],
    idempotency_key: Annotated[str | None, Depends(get_idempotency_key)],
) -> DataEnvelope[ExportJobRead]:
    if idempotency_key is None:
        raise idempotency_key_invalid_error()
    _prevent_storage(response)
    job = await service.create_job(
        request_context=request_context,
        permissions=authorized.user.permissions,
        payload=payload,
        idempotency_key=idempotency_key,
    )
    return data_envelope(job, request_context)


@router.get("/{job_id}", response_model=DataEnvelope[ExportJobRead])
async def get_export_job(
    job_id: UUID,
    response: Response,
    request_context: Annotated[
        RequestContext, Depends(get_authenticated_tenant_request_context)
    ],
    _authorized: Annotated[
        AuthenticatedSession,
        Depends(
            require_any_permission(
                REPORT_EXPORT_TENANT_PERMISSION,
                REPORT_EXPORT_TEAM_PERMISSION,
            )
        ),
    ],
    service: Annotated[ExportJobService, Depends(get_export_job_service)],
) -> DataEnvelope[ExportJobRead]:
    _prevent_storage(response)
    return data_envelope(
        await service.get_job(request_context=request_context, job_id=job_id),
        request_context,
    )


@router.post("/{job_id}/cancel", response_model=DataEnvelope[ExportJobRead])
async def cancel_export_job(
    job_id: UUID,
    response: Response,
    request_context: Annotated[
        RequestContext, Depends(get_authenticated_tenant_request_context)
    ],
    _authorized: Annotated[
        AuthenticatedSession,
        Depends(
            require_any_permission(
                REPORT_EXPORT_TENANT_PERMISSION,
                REPORT_EXPORT_TEAM_PERMISSION,
            )
        ),
    ],
    service: Annotated[ExportJobService, Depends(get_export_job_service)],
) -> DataEnvelope[ExportJobRead]:
    _prevent_storage(response)
    return data_envelope(
        await service.cancel_job(request_context=request_context, job_id=job_id),
        request_context,
    )


@router.post(
    "/{job_id}/download-intents",
    response_model=DataEnvelope[ExportDownloadIntentRead],
    status_code=status.HTTP_201_CREATED,
)
async def create_export_download_intent(
    job_id: UUID,
    response: Response,
    request_context: Annotated[
        RequestContext, Depends(get_authenticated_tenant_request_context)
    ],
    authorized: Annotated[
        AuthenticatedSession,
        Depends(
            require_any_permission(
                REPORT_EXPORT_TENANT_PERMISSION,
                REPORT_EXPORT_TEAM_PERMISSION,
            )
        ),
    ],
    service: Annotated[ExportJobService, Depends(get_export_job_service)],
) -> DataEnvelope[ExportDownloadIntentRead]:
    _prevent_storage(response)
    grant = await service.create_download_intent(
        request_context=request_context,
        permissions=authorized.user.permissions,
        job_id=job_id,
    )
    return data_envelope(grant, request_context)


def _prevent_storage(response: Response) -> None:
    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"


__all__ = ["router"]
