"""Role- and scope-aware fixed report preview APIs."""

from __future__ import annotations

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, Response
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth_dependencies import AuthenticatedSession, require_any_permission
from app.api.dependencies import get_authenticated_tenant_request_context
from app.api.errors import AUTHENTICATION_REQUIRED_RESPONSES, AUTHORIZATION_RESPONSES
from app.api.openapi import REPORTS_TAG, with_correlation_response_headers
from app.db.session import get_session
from app.models.reporting import ReportType
from app.platform.pagination import MAX_CURSOR_LENGTH
from app.platform.request_context import RequestContext
from app.schemas.reporting import (
    REPORT_DEFAULT_LIMIT,
    REPORT_MAX_LIMIT,
    DocumentChecklistReportStatus,
    DocumentReportEnvelope,
    DocumentReportFilters,
    EmployeeReportEnvelope,
    EmployeeReportFilters,
    LeaveReportEnvelope,
    LeaveReportFilters,
    ReportPageMeta,
)
from app.services.report_service import ReportService
from app.services.reporting_access import (
    REPORT_READ_TEAM_PERMISSION,
    REPORT_READ_TENANT_PERMISSION,
    ReportingValidationError,
    allowed_report_fields,
    require_reporting_feature,
    resolve_report_authorization,
)

router = APIRouter(
    prefix="/api/v1/reports",
    tags=[REPORTS_TAG],
    responses=with_correlation_response_headers(
        {**AUTHENTICATION_REQUIRED_RESPONSES, **AUTHORIZATION_RESPONSES}
    ),
)


def get_report_service(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> ReportService:
    return ReportService(session=session)


@router.get("/employees", response_model=EmployeeReportEnvelope)
async def employee_report(
    request: Request,
    response: Response,
    request_context: Annotated[
        RequestContext, Depends(get_authenticated_tenant_request_context)
    ],
    authorized: Annotated[
        AuthenticatedSession,
        Depends(require_any_permission(REPORT_READ_TENANT_PERMISSION, REPORT_READ_TEAM_PERMISSION)),
    ],
    service: Annotated[ReportService, Depends(get_report_service)],
    limit: Annotated[int, Query(ge=1, le=REPORT_MAX_LIMIT)] = REPORT_DEFAULT_LIMIT,
    cursor: Annotated[str | None, Query(min_length=1, max_length=MAX_CURSOR_LENGTH)] = None,
    q: Annotated[str | None, Query(min_length=1, max_length=200)] = None,
    status: Annotated[str | None, Query()] = None,
    employment_start_from: Annotated[date | None, Query()] = None,
    employment_start_to: Annotated[date | None, Query()] = None,
    legal_entity_code: Annotated[str | None, Query(min_length=1, max_length=32)] = None,
    branch_code: Annotated[str | None, Query(min_length=1, max_length=32)] = None,
    department_code: Annotated[str | None, Query(min_length=1, max_length=32)] = None,
    position_code: Annotated[str | None, Query(min_length=1, max_length=32)] = None,
) -> EmployeeReportEnvelope:
    _enforce_query_shape(
        request,
        {
            "limit",
            "cursor",
            "q",
            "status",
            "employment_start_from",
            "employment_start_to",
            "legal_entity_code",
            "branch_code",
            "department_code",
            "position_code",
        },
    )
    try:
        filters = EmployeeReportFilters(
            q=q,
            status=status,
            employment_start_from=employment_start_from,
            employment_start_to=employment_start_to,
            legal_entity_code=legal_entity_code,
            branch_code=branch_code,
            department_code=department_code,
            position_code=position_code,
        )
    except ValidationError as exc:
        raise ReportingValidationError() from exc
    tenant_id = request_context.require_tenant().tenant_id
    authorization = resolve_report_authorization(
        permissions=authorized.user.permissions,
        actor_id=_actor_id(request_context),
        require_export=False,
    )
    fields = allowed_report_fields(ReportType.EMPLOYEES, authorized.user.permissions)
    await require_reporting_feature(service.session, tenant_id=tenant_id)
    page = await service.employee_report(
        tenant_id=tenant_id,
        authorization=authorization,
        fields=fields,
        filters=filters,
        limit=limit,
        cursor=cursor,
    )
    _prevent_storage(response)
    return EmployeeReportEnvelope(
        data=page.items,
        meta=ReportPageMeta.from_context(
            request_context,
            limit=limit,
            next_cursor=page.next_cursor,
            scope=authorization.scope,
            fields=list(fields),
        ),
    )


@router.get("/leaves", response_model=LeaveReportEnvelope)
async def leave_report(
    request: Request,
    response: Response,
    request_context: Annotated[
        RequestContext, Depends(get_authenticated_tenant_request_context)
    ],
    authorized: Annotated[
        AuthenticatedSession,
        Depends(require_any_permission(REPORT_READ_TENANT_PERMISSION, REPORT_READ_TEAM_PERMISSION)),
    ],
    service: Annotated[ReportService, Depends(get_report_service)],
    limit: Annotated[int, Query(ge=1, le=REPORT_MAX_LIMIT)] = REPORT_DEFAULT_LIMIT,
    cursor: Annotated[str | None, Query(min_length=1, max_length=MAX_CURSOR_LENGTH)] = None,
    status: Annotated[str | None, Query()] = None,
    start_from: Annotated[date | None, Query()] = None,
    start_to: Annotated[date | None, Query()] = None,
    leave_type_code: Annotated[str | None, Query(min_length=1, max_length=64)] = None,
) -> LeaveReportEnvelope:
    _enforce_query_shape(
        request, {"limit", "cursor", "status", "start_from", "start_to", "leave_type_code"}
    )
    try:
        filters = LeaveReportFilters(
            status=status,
            start_from=start_from,
            start_to=start_to,
            leave_type_code=leave_type_code,
        )
    except ValidationError as exc:
        raise ReportingValidationError() from exc
    tenant_id = request_context.require_tenant().tenant_id
    authorization = resolve_report_authorization(
        permissions=authorized.user.permissions,
        actor_id=_actor_id(request_context),
        require_export=False,
    )
    fields = allowed_report_fields(ReportType.LEAVES, authorized.user.permissions)
    await require_reporting_feature(service.session, tenant_id=tenant_id)
    page = await service.leave_report(
        tenant_id=tenant_id,
        authorization=authorization,
        fields=fields,
        filters=filters,
        limit=limit,
        cursor=cursor,
    )
    _prevent_storage(response)
    return LeaveReportEnvelope(
        data=page.items,
        meta=ReportPageMeta.from_context(
            request_context,
            limit=limit,
            next_cursor=page.next_cursor,
            scope=authorization.scope,
            fields=list(fields),
        ),
    )


@router.get("/documents/missing", response_model=DocumentReportEnvelope)
async def missing_document_report(
    request: Request,
    response: Response,
    request_context: Annotated[
        RequestContext, Depends(get_authenticated_tenant_request_context)
    ],
    authorized: Annotated[
        AuthenticatedSession,
        Depends(require_any_permission(REPORT_READ_TENANT_PERMISSION, REPORT_READ_TEAM_PERMISSION)),
    ],
    service: Annotated[ReportService, Depends(get_report_service)],
    limit: Annotated[int, Query(ge=1, le=REPORT_MAX_LIMIT)] = REPORT_DEFAULT_LIMIT,
    cursor: Annotated[str | None, Query(min_length=1, max_length=MAX_CURSOR_LENGTH)] = None,
    status: Annotated[list[DocumentChecklistReportStatus] | None, Query()] = None,
    document_type_code: Annotated[str | None, Query(min_length=1, max_length=64)] = None,
    expires_before: Annotated[date | None, Query()] = None,
) -> DocumentReportEnvelope:
    _enforce_query_shape(
        request,
        {"limit", "cursor", "status", "document_type_code", "expires_before"},
        repeated={"status"},
    )
    try:
        filters = DocumentReportFilters(
            statuses=status or list(DocumentChecklistReportStatus),
            document_type_code=document_type_code,
            expires_before=expires_before,
        )
    except ValidationError as exc:
        raise ReportingValidationError() from exc
    tenant_id = request_context.require_tenant().tenant_id
    authorization = resolve_report_authorization(
        permissions=authorized.user.permissions,
        actor_id=_actor_id(request_context),
        require_export=False,
    )
    fields = allowed_report_fields(ReportType.MISSING_DOCUMENTS, authorized.user.permissions)
    await require_reporting_feature(service.session, tenant_id=tenant_id)
    page = await service.document_report(
        tenant_id=tenant_id,
        authorization=authorization,
        fields=fields,
        filters=filters,
        limit=limit,
        cursor=cursor,
    )
    _prevent_storage(response)
    return DocumentReportEnvelope(
        data=page.items,
        meta=ReportPageMeta.from_context(
            request_context,
            limit=limit,
            next_cursor=page.next_cursor,
            scope=authorization.scope,
            fields=list(fields),
        ),
    )


def _actor_id(context: RequestContext):
    if context.actor_id is None:
        raise ReportingValidationError()
    return context.actor_id


def _enforce_query_shape(
    request: Request, allowed: set[str], *, repeated: set[str] | None = None
) -> None:
    repeated = repeated or set()
    if any(key not in allowed for key in request.query_params):
        raise ReportingValidationError()
    if any(
        len(request.query_params.getlist(key)) > 1 for key in allowed if key not in repeated
    ):
        raise ReportingValidationError()


def _prevent_storage(response: Response) -> None:
    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"


__all__ = ["router"]
