"""Versioned employee import template, private upload, status, and commit APIs."""

from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, Response, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.datastructures import UploadFile
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.formparsers import MultiPartException

from app.api.auth_dependencies import (
    AuthenticatedSession,
    get_database_runtime,
    require_permission,
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
from app.api.openapi import IMPORTS_TAG, with_correlation_response_headers
from app.db.session import DatabaseRuntime, get_session
from app.modules.documents import DOCUMENT_RUNTIME_STATE_KEY, DocumentRuntime
from app.modules.reporting.spreadsheets import (
    employee_import_template_csv,
    employee_import_template_xlsx,
)
from app.platform.pagination import MAX_CURSOR_LENGTH
from app.platform.request_context import RequestContext
from app.platform.responses import DataEnvelope, data_envelope
from app.schemas.employee_import import (
    EMPLOYEE_IMPORT_ISSUE_DEFAULT_LIMIT,
    EMPLOYEE_IMPORT_ISSUE_MAX_LIMIT,
    EMPLOYEE_IMPORT_MAX_BYTES,
    EMPLOYEE_IMPORT_MAX_REQUEST_BYTES,
    EMPLOYEE_IMPORT_TEMPLATE_VERSION,
    EmployeeImportCommitRead,
    EmployeeImportRead,
)
from app.services.employee_import_service import EmployeeImportService
from app.services.reporting_access import (
    EMPLOYEE_IMPORT_PERMISSION,
    ReportingValidationError,
    require_reporting_feature,
)

router = APIRouter(
    prefix="/api/v1/employees/imports",
    tags=[IMPORTS_TAG],
    responses=with_correlation_response_headers(
        {**AUTHENTICATION_REQUIRED_RESPONSES, **AUTHORIZATION_RESPONSES}
    ),
)


def get_document_runtime(request: Request) -> DocumentRuntime:
    runtime = getattr(request.app.state, DOCUMENT_RUNTIME_STATE_KEY, None)
    if not isinstance(runtime, DocumentRuntime):
        raise RuntimeError("Private object runtime is unavailable")
    return runtime


def get_employee_import_service(
    database_runtime: Annotated[DatabaseRuntime, Depends(get_database_runtime)],
    document_runtime: Annotated[DocumentRuntime, Depends(get_document_runtime)],
) -> EmployeeImportService:
    return EmployeeImportService(
        session_factory=database_runtime.session_factory,
        storage=document_runtime.storage,
    )


@router.get("/template")
async def download_employee_import_template(
    request_context: Annotated[
        RequestContext, Depends(get_authenticated_tenant_request_context)
    ],
    _authorized: Annotated[
        AuthenticatedSession, Depends(require_permission(EMPLOYEE_IMPORT_PERMISSION))
    ],
    session: Annotated[AsyncSession, Depends(get_session)],
    format: Annotated[Literal["csv", "xlsx"], Query()] = "xlsx",
    version: Annotated[Literal["1"], Query()] = EMPLOYEE_IMPORT_TEMPLATE_VERSION,
) -> StreamingResponse:
    del version
    async with session.begin():
        await require_reporting_feature(
            session,
            tenant_id=request_context.require_tenant().tenant_id,
        )
    if format == "csv":
        payload = employee_import_template_csv()
        media_type = "text/csv; charset=utf-8"
    else:
        payload = employee_import_template_xlsx()
        media_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    headers = {
        "Cache-Control": "no-store",
        "Pragma": "no-cache",
        "Content-Disposition": f'attachment; filename="employee-import-v1.{format}"',
        "X-Content-Type-Options": "nosniff",
    }
    return StreamingResponse(iter([payload]), media_type=media_type, headers=headers)


@router.post(
    "",
    response_model=DataEnvelope[EmployeeImportRead],
    status_code=status.HTTP_202_ACCEPTED,
    openapi_extra={
        "requestBody": {
            "required": True,
            "content": {
                "multipart/form-data": {
                    "schema": {
                        "type": "object",
                        "required": ["file"],
                        "properties": {"file": {"type": "string", "format": "binary"}},
                        "additionalProperties": False,
                    }
                }
            },
        }
    },
)
async def upload_employee_import(
    request: Request,
    response: Response,
    request_context: Annotated[
        RequestContext, Depends(get_authenticated_tenant_request_context)
    ],
    _authorized: Annotated[
        AuthenticatedSession, Depends(require_permission(EMPLOYEE_IMPORT_PERMISSION))
    ],
    service: Annotated[EmployeeImportService, Depends(get_employee_import_service)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> DataEnvelope[EmployeeImportRead]:
    async with session.begin():
        await require_reporting_feature(
            session,
            tenant_id=request_context.require_tenant().tenant_id,
            write=True,
        )
    try:
        form = await request.form(
            max_files=1,
            max_fields=0,
            max_part_size=EMPLOYEE_IMPORT_MAX_REQUEST_BYTES,
        )
    except (MultiPartException, StarletteHTTPException) as exc:
        raise ReportingValidationError() from exc
    if set(form) != {"file"} or len(form.getlist("file")) != 1:
        raise ReportingValidationError()
    file = form.get("file")
    if not isinstance(file, UploadFile):
        raise ReportingValidationError()
    filename = file.filename or ""
    content_type = file.content_type or "application/octet-stream"
    try:
        with tempfile.TemporaryDirectory(prefix="wf-employee-import-upload-") as directory:
            path = Path(directory) / "upload"
            size_bytes = await _stream_upload(file, path)
            record = await service.create_import(
                request_context=request_context,
                source=path,
                original_filename=filename,
                content_type=content_type,
                size_bytes=size_bytes,
            )
    finally:
        await file.close()
    _prevent_storage(response)
    return data_envelope(record, request_context)


@router.get("/{import_id}", response_model=DataEnvelope[EmployeeImportRead])
async def get_employee_import(
    import_id: UUID,
    response: Response,
    request_context: Annotated[
        RequestContext, Depends(get_authenticated_tenant_request_context)
    ],
    _authorized: Annotated[
        AuthenticatedSession, Depends(require_permission(EMPLOYEE_IMPORT_PERMISSION))
    ],
    service: Annotated[EmployeeImportService, Depends(get_employee_import_service)],
    issue_limit: Annotated[
        int, Query(ge=1, le=EMPLOYEE_IMPORT_ISSUE_MAX_LIMIT)
    ] = EMPLOYEE_IMPORT_ISSUE_DEFAULT_LIMIT,
    issue_cursor: Annotated[
        str | None, Query(min_length=1, max_length=MAX_CURSOR_LENGTH)
    ] = None,
) -> DataEnvelope[EmployeeImportRead]:
    _prevent_storage(response)
    record = await service.get_import(
        request_context=request_context,
        import_id=import_id,
        issue_limit=issue_limit,
        issue_cursor=issue_cursor,
    )
    return data_envelope(record, request_context)


@router.post(
    "/{import_id}/commit",
    response_model=DataEnvelope[EmployeeImportCommitRead],
)
async def commit_employee_import(
    import_id: UUID,
    response: Response,
    request_context: Annotated[
        RequestContext, Depends(get_authenticated_tenant_request_context)
    ],
    _authorized: Annotated[
        AuthenticatedSession, Depends(require_permission(EMPLOYEE_IMPORT_PERMISSION))
    ],
    service: Annotated[EmployeeImportService, Depends(get_employee_import_service)],
    idempotency_key: Annotated[str | None, Depends(get_idempotency_key)],
) -> DataEnvelope[EmployeeImportCommitRead]:
    if idempotency_key is None:
        raise idempotency_key_invalid_error()
    _prevent_storage(response)
    result = await service.commit_import(
        request_context=request_context,
        import_id=import_id,
        idempotency_key=idempotency_key,
    )
    return data_envelope(result, request_context)


async def _stream_upload(file: UploadFile, destination: Path) -> int:
    size_bytes = 0
    with destination.open("xb") as handle:
        while True:
            chunk = await file.read(128 * 1024)
            if not chunk:
                break
            size_bytes += len(chunk)
            if size_bytes > EMPLOYEE_IMPORT_MAX_BYTES:
                raise ReportingValidationError()
            await asyncio.to_thread(handle.write, chunk)
    if size_bytes == 0:
        raise ReportingValidationError()
    return size_bytes


def _prevent_storage(response: Response) -> None:
    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"


__all__ = ["router"]
