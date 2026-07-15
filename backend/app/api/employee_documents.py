"""Authenticated HR and employee-self document APIs."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, Response, status

from app.api.auth_dependencies import (
    AuthenticatedSession,
    get_application_settings,
    get_database_runtime,
    require_permission,
)
from app.api.dependencies import get_authenticated_tenant_request_context
from app.api.errors import AUTHENTICATION_REQUIRED_RESPONSES, AUTHORIZATION_RESPONSES
from app.api.openapi import DOCUMENTS_TAG, with_correlation_response_headers
from app.core.config import Settings
from app.db.session import DatabaseRuntime
from app.modules.documents import DOCUMENT_RUNTIME_STATE_KEY, DocumentRuntime
from app.platform.request_context import RequestContext
from app.platform.responses import DataEnvelope, data_envelope
from app.schemas.employee_document import (
    DocumentTypeCreate,
    DocumentTypeRead,
    DocumentTypeUpdate,
    EmployeeDocumentDownloadGrantRead,
    EmployeeDocumentFinalize,
    EmployeeDocumentMetadataUpdate,
    EmployeeDocumentRead,
    EmployeeDocumentUploadGrantRead,
    EmployeeDocumentUploadInitiate,
    EmployeeDocumentWorkspaceRead,
    OwnEmployeeDocumentWorkspaceRead,
    VersionedDocumentAction,
)
from app.services.employee_document_service import EmployeeDocumentService

_COMMON_RESPONSES = with_correlation_response_headers(
    {
        **AUTHENTICATION_REQUIRED_RESPONSES,
        **AUTHORIZATION_RESPONSES,
    }
)

document_types_router = APIRouter(
    prefix="/api/v1/document-types",
    tags=[DOCUMENTS_TAG],
    responses=_COMMON_RESPONSES,
)
employee_router = APIRouter(
    prefix="/api/v1/employees",
    tags=[DOCUMENTS_TAG],
    responses=_COMMON_RESPONSES,
)
own_router = APIRouter(
    prefix="/api/v1/me/documents",
    tags=[DOCUMENTS_TAG],
    responses=_COMMON_RESPONSES,
)


def get_document_runtime(request: Request) -> DocumentRuntime:
    runtime = getattr(request.app.state, DOCUMENT_RUNTIME_STATE_KEY, None)
    if not isinstance(runtime, DocumentRuntime):
        raise RuntimeError("Employee document runtime is unavailable")
    return runtime


def get_employee_document_service(
    database_runtime: Annotated[DatabaseRuntime, Depends(get_database_runtime)],
    document_runtime: Annotated[DocumentRuntime, Depends(get_document_runtime)],
    settings: Annotated[Settings, Depends(get_application_settings)],
) -> EmployeeDocumentService:
    return EmployeeDocumentService(
        session_factory=database_runtime.session_factory,
        storage=document_runtime.storage,
        scanner=document_runtime.scanner,
        settings=settings,
    )


@document_types_router.get(
    "",
    response_model=DataEnvelope[list[DocumentTypeRead]],
    summary="List employee document types",
)
async def list_document_types(
    response: Response,
    request_context: Annotated[
        RequestContext,
        Depends(get_authenticated_tenant_request_context),
    ],
    _authorized: Annotated[
        AuthenticatedSession,
        Depends(require_permission("document_type:manage:tenant")),
    ],
    service: Annotated[EmployeeDocumentService, Depends(get_employee_document_service)],
    include_archived: Annotated[bool, Query()] = True,
) -> DataEnvelope[list[DocumentTypeRead]]:
    _prevent_storage(response)
    records = await service.list_document_types(
        tenant_id=request_context.require_tenant().tenant_id,
        include_archived=include_archived,
    )
    return data_envelope(records, request_context)


@document_types_router.post(
    "",
    response_model=DataEnvelope[DocumentTypeRead],
    status_code=status.HTTP_201_CREATED,
    summary="Create an employee document type",
)
async def create_document_type(
    payload: DocumentTypeCreate,
    response: Response,
    request_context: Annotated[
        RequestContext,
        Depends(get_authenticated_tenant_request_context),
    ],
    _authorized: Annotated[
        AuthenticatedSession,
        Depends(require_permission("document_type:manage:tenant")),
    ],
    service: Annotated[EmployeeDocumentService, Depends(get_employee_document_service)],
) -> DataEnvelope[DocumentTypeRead]:
    _prevent_storage(response)
    record = await service.create_document_type(
        tenant_id=request_context.require_tenant().tenant_id,
        payload=payload,
        request_context=request_context,
    )
    return data_envelope(record, request_context)


@document_types_router.patch(
    "/{document_type_id}",
    response_model=DataEnvelope[DocumentTypeRead],
    summary="Update an employee document type",
)
async def update_document_type(
    document_type_id: UUID,
    payload: DocumentTypeUpdate,
    response: Response,
    request_context: Annotated[
        RequestContext,
        Depends(get_authenticated_tenant_request_context),
    ],
    _authorized: Annotated[
        AuthenticatedSession,
        Depends(require_permission("document_type:manage:tenant")),
    ],
    service: Annotated[EmployeeDocumentService, Depends(get_employee_document_service)],
) -> DataEnvelope[DocumentTypeRead]:
    _prevent_storage(response)
    record = await service.update_document_type(
        tenant_id=request_context.require_tenant().tenant_id,
        document_type_id=document_type_id,
        payload=payload,
        request_context=request_context,
    )
    return data_envelope(record, request_context)


@document_types_router.post(
    "/{document_type_id}/archive",
    response_model=DataEnvelope[DocumentTypeRead],
    summary="Archive an employee document type",
)
async def archive_document_type(
    document_type_id: UUID,
    payload: VersionedDocumentAction,
    response: Response,
    request_context: Annotated[
        RequestContext,
        Depends(get_authenticated_tenant_request_context),
    ],
    _authorized: Annotated[
        AuthenticatedSession,
        Depends(require_permission("document_type:manage:tenant")),
    ],
    service: Annotated[EmployeeDocumentService, Depends(get_employee_document_service)],
) -> DataEnvelope[DocumentTypeRead]:
    _prevent_storage(response)
    record = await service.set_document_type_archived(
        tenant_id=request_context.require_tenant().tenant_id,
        document_type_id=document_type_id,
        expected_version=payload.expected_version,
        archived=True,
        request_context=request_context,
    )
    return data_envelope(record, request_context)


@document_types_router.post(
    "/{document_type_id}/unarchive",
    response_model=DataEnvelope[DocumentTypeRead],
    summary="Unarchive an employee document type",
)
async def unarchive_document_type(
    document_type_id: UUID,
    payload: VersionedDocumentAction,
    response: Response,
    request_context: Annotated[
        RequestContext,
        Depends(get_authenticated_tenant_request_context),
    ],
    _authorized: Annotated[
        AuthenticatedSession,
        Depends(require_permission("document_type:manage:tenant")),
    ],
    service: Annotated[EmployeeDocumentService, Depends(get_employee_document_service)],
) -> DataEnvelope[DocumentTypeRead]:
    _prevent_storage(response)
    record = await service.set_document_type_archived(
        tenant_id=request_context.require_tenant().tenant_id,
        document_type_id=document_type_id,
        expected_version=payload.expected_version,
        archived=False,
        request_context=request_context,
    )
    return data_envelope(record, request_context)


@employee_router.get(
    "/{employee_id}/documents",
    response_model=DataEnvelope[EmployeeDocumentWorkspaceRead],
    summary="Read an employee document checklist and document list",
)
async def get_employee_documents(
    employee_id: UUID,
    response: Response,
    request_context: Annotated[
        RequestContext,
        Depends(get_authenticated_tenant_request_context),
    ],
    _authorized: Annotated[
        AuthenticatedSession,
        Depends(require_permission("employee_document:manage:tenant")),
    ],
    service: Annotated[EmployeeDocumentService, Depends(get_employee_document_service)],
) -> DataEnvelope[EmployeeDocumentWorkspaceRead]:
    _prevent_storage(response)
    workspace = await service.get_hr_workspace(
        tenant_id=request_context.require_tenant().tenant_id,
        employee_id=employee_id,
        request_context=request_context,
    )
    return data_envelope(workspace, request_context)


@employee_router.post(
    "/{employee_id}/documents/uploads",
    response_model=DataEnvelope[EmployeeDocumentUploadGrantRead],
    status_code=status.HTTP_201_CREATED,
    summary="Initiate an employee document upload",
)
async def initiate_employee_document_upload(
    employee_id: UUID,
    payload: EmployeeDocumentUploadInitiate,
    response: Response,
    request_context: Annotated[
        RequestContext,
        Depends(get_authenticated_tenant_request_context),
    ],
    _authorized: Annotated[
        AuthenticatedSession,
        Depends(require_permission("employee_document:manage:tenant")),
    ],
    service: Annotated[EmployeeDocumentService, Depends(get_employee_document_service)],
) -> DataEnvelope[EmployeeDocumentUploadGrantRead]:
    _prevent_storage(response)
    grant = await service.initiate_upload(
        tenant_id=request_context.require_tenant().tenant_id,
        employee_id=employee_id,
        payload=payload,
        request_context=request_context,
    )
    return data_envelope(grant, request_context)


@employee_router.post(
    "/{employee_id}/documents/{document_id}/finalize",
    response_model=DataEnvelope[EmployeeDocumentRead],
    summary="Finalize and scan an uploaded employee document",
)
async def finalize_employee_document_upload(
    employee_id: UUID,
    document_id: UUID,
    payload: EmployeeDocumentFinalize,
    response: Response,
    request_context: Annotated[
        RequestContext,
        Depends(get_authenticated_tenant_request_context),
    ],
    _authorized: Annotated[
        AuthenticatedSession,
        Depends(require_permission("employee_document:manage:tenant")),
    ],
    service: Annotated[EmployeeDocumentService, Depends(get_employee_document_service)],
) -> DataEnvelope[EmployeeDocumentRead]:
    _prevent_storage(response)
    document = await service.finalize_upload(
        tenant_id=request_context.require_tenant().tenant_id,
        employee_id=employee_id,
        document_id=document_id,
        upload_intent_id=payload.upload_intent_id,
        request_context=request_context,
    )
    return data_envelope(document, request_context)


@employee_router.patch(
    "/{employee_id}/documents/{document_id}",
    response_model=DataEnvelope[EmployeeDocumentRead],
    summary="Update allowed employee document metadata",
)
async def update_employee_document(
    employee_id: UUID,
    document_id: UUID,
    payload: EmployeeDocumentMetadataUpdate,
    response: Response,
    request_context: Annotated[
        RequestContext,
        Depends(get_authenticated_tenant_request_context),
    ],
    _authorized: Annotated[
        AuthenticatedSession,
        Depends(require_permission("employee_document:manage:tenant")),
    ],
    service: Annotated[EmployeeDocumentService, Depends(get_employee_document_service)],
) -> DataEnvelope[EmployeeDocumentRead]:
    _prevent_storage(response)
    document = await service.update_document_metadata(
        tenant_id=request_context.require_tenant().tenant_id,
        employee_id=employee_id,
        document_id=document_id,
        payload=payload,
        request_context=request_context,
    )
    return data_envelope(document, request_context)


async def _set_employee_document_archived(
    *,
    employee_id: UUID,
    document_id: UUID,
    payload: VersionedDocumentAction,
    archived: bool,
    response: Response,
    request_context: RequestContext,
    service: EmployeeDocumentService,
) -> DataEnvelope[EmployeeDocumentRead]:
    _prevent_storage(response)
    document = await service.set_document_archived(
        tenant_id=request_context.require_tenant().tenant_id,
        employee_id=employee_id,
        document_id=document_id,
        expected_version=payload.expected_version,
        archived=archived,
        request_context=request_context,
    )
    return data_envelope(document, request_context)


@employee_router.post(
    "/{employee_id}/documents/{document_id}/archive",
    response_model=DataEnvelope[EmployeeDocumentRead],
    summary="Archive an employee document",
)
async def archive_employee_document(
    employee_id: UUID,
    document_id: UUID,
    payload: VersionedDocumentAction,
    response: Response,
    request_context: Annotated[
        RequestContext,
        Depends(get_authenticated_tenant_request_context),
    ],
    _authorized: Annotated[
        AuthenticatedSession,
        Depends(require_permission("employee_document:manage:tenant")),
    ],
    service: Annotated[EmployeeDocumentService, Depends(get_employee_document_service)],
) -> DataEnvelope[EmployeeDocumentRead]:
    return await _set_employee_document_archived(
        employee_id=employee_id,
        document_id=document_id,
        payload=payload,
        archived=True,
        response=response,
        request_context=request_context,
        service=service,
    )


@employee_router.post(
    "/{employee_id}/documents/{document_id}/unarchive",
    response_model=DataEnvelope[EmployeeDocumentRead],
    summary="Unarchive an employee document",
)
async def unarchive_employee_document(
    employee_id: UUID,
    document_id: UUID,
    payload: VersionedDocumentAction,
    response: Response,
    request_context: Annotated[
        RequestContext,
        Depends(get_authenticated_tenant_request_context),
    ],
    _authorized: Annotated[
        AuthenticatedSession,
        Depends(require_permission("employee_document:manage:tenant")),
    ],
    service: Annotated[EmployeeDocumentService, Depends(get_employee_document_service)],
) -> DataEnvelope[EmployeeDocumentRead]:
    return await _set_employee_document_archived(
        employee_id=employee_id,
        document_id=document_id,
        payload=payload,
        archived=False,
        response=response,
        request_context=request_context,
        service=service,
    )


@employee_router.post(
    "/{employee_id}/documents/{document_id}/download",
    response_model=DataEnvelope[EmployeeDocumentDownloadGrantRead],
    summary="Issue an HR document download URL",
)
async def download_employee_document(
    employee_id: UUID,
    document_id: UUID,
    response: Response,
    request_context: Annotated[
        RequestContext,
        Depends(get_authenticated_tenant_request_context),
    ],
    _authorized: Annotated[
        AuthenticatedSession,
        Depends(require_permission("employee_document:manage:tenant")),
    ],
    service: Annotated[EmployeeDocumentService, Depends(get_employee_document_service)],
) -> DataEnvelope[EmployeeDocumentDownloadGrantRead]:
    _prevent_storage(response)
    grant = await service.issue_hr_download(
        tenant_id=request_context.require_tenant().tenant_id,
        employee_id=employee_id,
        document_id=document_id,
        request_context=request_context,
    )
    return data_envelope(grant, request_context)


@own_router.get(
    "",
    response_model=DataEnvelope[OwnEmployeeDocumentWorkspaceRead],
    summary="Read own employee-visible documents",
)
async def get_own_documents(
    response: Response,
    request_context: Annotated[
        RequestContext,
        Depends(get_authenticated_tenant_request_context),
    ],
    _authorized: Annotated[
        AuthenticatedSession,
        Depends(require_permission("employee_document:read:own")),
    ],
    service: Annotated[EmployeeDocumentService, Depends(get_employee_document_service)],
) -> DataEnvelope[OwnEmployeeDocumentWorkspaceRead]:
    _prevent_storage(response)
    workspace = await service.get_own_workspace(
        tenant_id=request_context.require_tenant().tenant_id,
        request_context=request_context,
    )
    return data_envelope(workspace, request_context)


@own_router.post(
    "/{document_id}/download",
    response_model=DataEnvelope[EmployeeDocumentDownloadGrantRead],
    summary="Issue an own-document download URL",
)
async def download_own_document(
    document_id: UUID,
    response: Response,
    request_context: Annotated[
        RequestContext,
        Depends(get_authenticated_tenant_request_context),
    ],
    _authorized: Annotated[
        AuthenticatedSession,
        Depends(require_permission("employee_document:read:own")),
    ],
    service: Annotated[EmployeeDocumentService, Depends(get_employee_document_service)],
) -> DataEnvelope[EmployeeDocumentDownloadGrantRead]:
    _prevent_storage(response)
    grant = await service.issue_own_download(
        tenant_id=request_context.require_tenant().tenant_id,
        document_id=document_id,
        request_context=request_context,
    )
    return data_envelope(grant, request_context)


def _prevent_storage(response: Response) -> None:
    response.headers["Cache-Control"] = "no-store"


__all__ = ["document_types_router", "employee_router", "own_router"]
