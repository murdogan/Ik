"""Employee privacy center and tenant compliance workspace APIs."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth_dependencies import (
    AuthenticatedSession,
    require_any_permission,
    require_permission,
)
from app.api.dependencies import (
    get_authenticated_tenant_request_context,
    get_command_idempotency_service,
    get_idempotency_key,
    get_unit_of_work,
)
from app.api.errors import AUTHENTICATION_REQUIRED_RESPONSES, AUTHORIZATION_RESPONSES
from app.api.openapi import PRIVACY_TAG, with_correlation_response_headers
from app.db.session import get_session
from app.models.privacy import PrivacyConsentAction
from app.platform.db import SqlAlchemyUnitOfWork
from app.platform.request_context import RequestContext
from app.platform.responses import DataEnvelope, data_envelope
from app.schemas.privacy import (
    PRIVACY_NOTICE_LIST_DEFAULT_LIMIT,
    PRIVACY_NOTICE_LIST_MAX_LIMIT,
    ConsentCenterRead,
    ConsentPurposeStateRead,
    ConsentTransitionRequest,
    EmployeePrivacyNoticeRead,
    PrivacyNoticeAcknowledge,
    PrivacyNoticeCreate,
    PrivacyNoticeDetailRead,
    PrivacyNoticePublish,
    PrivacyNoticeSummaryRead,
    PrivacyNoticeUpdate,
    RetentionDryRunRead,
    RetentionDryRunRequest,
    RetentionPolicyCreate,
    RetentionPolicyRead,
    RetentionPolicyUpdate,
)
from app.services.command_idempotency import CommandIdempotencyService
from app.services.privacy_commands import PrivacyCommandHandler
from app.services.privacy_service import PrivacyService

router = APIRouter(
    prefix="/api/v1/privacy",
    tags=[PRIVACY_TAG],
    responses=with_correlation_response_headers(
        {
            **AUTHENTICATION_REQUIRED_RESPONSES,
            **AUTHORIZATION_RESPONSES,
        }
    ),
)


def get_privacy_service(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> PrivacyService:
    return PrivacyService(session)


def get_privacy_command_handler(
    service: Annotated[PrivacyService, Depends(get_privacy_service)],
    unit_of_work: Annotated[SqlAlchemyUnitOfWork, Depends(get_unit_of_work)],
    idempotency: Annotated[
        CommandIdempotencyService,
        Depends(get_command_idempotency_service),
    ],
) -> PrivacyCommandHandler:
    return PrivacyCommandHandler(
        service=service,
        unit_of_work=unit_of_work,
        idempotency=idempotency,
    )


@router.get(
    "/notice",
    response_model=DataEnvelope[EmployeePrivacyNoticeRead],
    summary="Read my current employee privacy notice",
)
async def get_current_privacy_notice(
    response: Response,
    request_context: Annotated[
        RequestContext,
        Depends(get_authenticated_tenant_request_context),
    ],
    _authorized: Annotated[
        AuthenticatedSession,
        Depends(require_permission("privacy_notice:read:own")),
    ],
    service: Annotated[PrivacyService, Depends(get_privacy_service)],
) -> DataEnvelope[EmployeePrivacyNoticeRead]:
    _prevent_storage(response)
    result = await service.current_employee_notice(request_context=request_context)
    return data_envelope(result, request_context)


@router.post(
    "/notice/acknowledge",
    response_model=DataEnvelope[EmployeePrivacyNoticeRead],
    summary="Acknowledge an exact employee privacy notice version",
)
async def acknowledge_privacy_notice(
    payload: PrivacyNoticeAcknowledge,
    response: Response,
    request_context: Annotated[
        RequestContext,
        Depends(get_authenticated_tenant_request_context),
    ],
    _authorized: Annotated[
        AuthenticatedSession,
        Depends(require_permission("privacy_notice:acknowledge:own")),
    ],
    handler: Annotated[PrivacyCommandHandler, Depends(get_privacy_command_handler)],
    idempotency_key: Annotated[str | None, Depends(get_idempotency_key)],
) -> DataEnvelope[EmployeePrivacyNoticeRead]:
    _prevent_storage(response)
    result = await handler.acknowledge_notice(
        context=request_context,
        payload=payload,
        idempotency_key=idempotency_key,
    )
    return data_envelope(result, request_context)


@router.get(
    "/consents",
    response_model=DataEnvelope[ConsentCenterRead],
    summary="Read my optional-purpose consent state and history",
)
async def get_consent_center(
    response: Response,
    request_context: Annotated[
        RequestContext,
        Depends(get_authenticated_tenant_request_context),
    ],
    _authorized: Annotated[
        AuthenticatedSession,
        Depends(require_permission("privacy_consent:manage:own")),
    ],
    service: Annotated[PrivacyService, Depends(get_privacy_service)],
) -> DataEnvelope[ConsentCenterRead]:
    _prevent_storage(response)
    result = await service.consent_center(request_context=request_context)
    return data_envelope(result, request_context)


@router.post(
    "/consents/{purpose_id}/grant",
    response_model=DataEnvelope[ConsentPurposeStateRead],
    summary="Grant one optional-purpose consent",
)
async def grant_consent(
    purpose_id: UUID,
    _payload: ConsentTransitionRequest,
    response: Response,
    request_context: Annotated[
        RequestContext,
        Depends(get_authenticated_tenant_request_context),
    ],
    _authorized: Annotated[
        AuthenticatedSession,
        Depends(require_permission("privacy_consent:manage:own")),
    ],
    handler: Annotated[PrivacyCommandHandler, Depends(get_privacy_command_handler)],
    idempotency_key: Annotated[str | None, Depends(get_idempotency_key)],
) -> DataEnvelope[ConsentPurposeStateRead]:
    return await _transition_consent(
        purpose_id=purpose_id,
        action=PrivacyConsentAction.GRANT,
        response=response,
        request_context=request_context,
        handler=handler,
        idempotency_key=idempotency_key,
    )


@router.post(
    "/consents/{purpose_id}/withdraw",
    response_model=DataEnvelope[ConsentPurposeStateRead],
    summary="Withdraw one optional-purpose consent",
)
async def withdraw_consent(
    purpose_id: UUID,
    _payload: ConsentTransitionRequest,
    response: Response,
    request_context: Annotated[
        RequestContext,
        Depends(get_authenticated_tenant_request_context),
    ],
    _authorized: Annotated[
        AuthenticatedSession,
        Depends(require_permission("privacy_consent:manage:own")),
    ],
    handler: Annotated[PrivacyCommandHandler, Depends(get_privacy_command_handler)],
    idempotency_key: Annotated[str | None, Depends(get_idempotency_key)],
) -> DataEnvelope[ConsentPurposeStateRead]:
    return await _transition_consent(
        purpose_id=purpose_id,
        action=PrivacyConsentAction.WITHDRAW,
        response=response,
        request_context=request_context,
        handler=handler,
        idempotency_key=idempotency_key,
    )


@router.get(
    "/manage/notices",
    response_model=DataEnvelope[list[PrivacyNoticeSummaryRead]],
    summary="List bounded employee privacy notice versions",
)
async def list_managed_privacy_notices(
    response: Response,
    request_context: Annotated[
        RequestContext,
        Depends(get_authenticated_tenant_request_context),
    ],
    _authorized: Annotated[
        AuthenticatedSession,
        Depends(
            require_any_permission(
                "privacy_compliance:read:tenant",
                "privacy_notice:manage:tenant",
            )
        ),
    ],
    service: Annotated[PrivacyService, Depends(get_privacy_service)],
    limit: Annotated[
        int,
        Query(ge=1, le=PRIVACY_NOTICE_LIST_MAX_LIMIT),
    ] = PRIVACY_NOTICE_LIST_DEFAULT_LIMIT,
) -> DataEnvelope[list[PrivacyNoticeSummaryRead]]:
    _prevent_storage(response)
    result = await service.list_notices(
        tenant_id=request_context.require_tenant().tenant_id,
        limit=limit,
    )
    return data_envelope(result, request_context)


@router.post(
    "/manage/notices",
    response_model=DataEnvelope[PrivacyNoticeDetailRead],
    status_code=status.HTTP_201_CREATED,
    summary="Create an employee privacy notice draft",
)
async def create_managed_privacy_notice(
    payload: PrivacyNoticeCreate,
    response: Response,
    request_context: Annotated[
        RequestContext,
        Depends(get_authenticated_tenant_request_context),
    ],
    _authorized: Annotated[
        AuthenticatedSession,
        Depends(require_permission("privacy_notice:manage:tenant")),
    ],
    handler: Annotated[PrivacyCommandHandler, Depends(get_privacy_command_handler)],
    idempotency_key: Annotated[str | None, Depends(get_idempotency_key)],
) -> DataEnvelope[PrivacyNoticeDetailRead]:
    _prevent_storage(response)
    result = await handler.create_notice(
        context=request_context,
        payload=payload,
        idempotency_key=idempotency_key,
    )
    return data_envelope(result, request_context)


@router.get(
    "/manage/notices/{notice_id}",
    response_model=DataEnvelope[PrivacyNoticeDetailRead],
    summary="Read one employee privacy notice version",
)
async def get_managed_privacy_notice(
    notice_id: UUID,
    response: Response,
    request_context: Annotated[
        RequestContext,
        Depends(get_authenticated_tenant_request_context),
    ],
    _authorized: Annotated[
        AuthenticatedSession,
        Depends(
            require_any_permission(
                "privacy_compliance:read:tenant",
                "privacy_notice:manage:tenant",
            )
        ),
    ],
    service: Annotated[PrivacyService, Depends(get_privacy_service)],
) -> DataEnvelope[PrivacyNoticeDetailRead]:
    _prevent_storage(response)
    result = await service.get_notice(
        tenant_id=request_context.require_tenant().tenant_id,
        notice_id=notice_id,
    )
    return data_envelope(result, request_context)


@router.patch(
    "/manage/notices/{notice_id}",
    response_model=DataEnvelope[PrivacyNoticeDetailRead],
    summary="Edit an employee privacy notice draft",
)
async def update_managed_privacy_notice(
    notice_id: UUID,
    payload: PrivacyNoticeUpdate,
    response: Response,
    request_context: Annotated[
        RequestContext,
        Depends(get_authenticated_tenant_request_context),
    ],
    _authorized: Annotated[
        AuthenticatedSession,
        Depends(require_permission("privacy_notice:manage:tenant")),
    ],
    handler: Annotated[PrivacyCommandHandler, Depends(get_privacy_command_handler)],
    idempotency_key: Annotated[str | None, Depends(get_idempotency_key)],
) -> DataEnvelope[PrivacyNoticeDetailRead]:
    _prevent_storage(response)
    result = await handler.update_notice(
        context=request_context,
        notice_id=notice_id,
        payload=payload,
        idempotency_key=idempotency_key,
    )
    return data_envelope(result, request_context)


@router.post(
    "/manage/notices/{notice_id}/publish",
    response_model=DataEnvelope[PrivacyNoticeDetailRead],
    summary="Publish an immutable employee privacy notice version",
)
async def publish_managed_privacy_notice(
    notice_id: UUID,
    payload: PrivacyNoticePublish,
    response: Response,
    request_context: Annotated[
        RequestContext,
        Depends(get_authenticated_tenant_request_context),
    ],
    _authorized: Annotated[
        AuthenticatedSession,
        Depends(require_permission("privacy_notice:manage:tenant")),
    ],
    handler: Annotated[PrivacyCommandHandler, Depends(get_privacy_command_handler)],
    idempotency_key: Annotated[str | None, Depends(get_idempotency_key)],
) -> DataEnvelope[PrivacyNoticeDetailRead]:
    _prevent_storage(response)
    result = await handler.publish_notice(
        context=request_context,
        notice_id=notice_id,
        payload=payload,
        idempotency_key=idempotency_key,
    )
    return data_envelope(result, request_context)


@router.get(
    "/manage/retention-policies",
    response_model=DataEnvelope[list[RetentionPolicyRead]],
    summary="List bounded retention-policy metadata",
)
async def list_retention_policies(
    response: Response,
    request_context: Annotated[
        RequestContext,
        Depends(get_authenticated_tenant_request_context),
    ],
    _authorized: Annotated[
        AuthenticatedSession,
        Depends(
            require_any_permission(
                "privacy_compliance:read:tenant",
                "retention_policy:manage:tenant",
            )
        ),
    ],
    service: Annotated[PrivacyService, Depends(get_privacy_service)],
) -> DataEnvelope[list[RetentionPolicyRead]]:
    _prevent_storage(response)
    result = await service.list_retention_policies(
        tenant_id=request_context.require_tenant().tenant_id
    )
    return data_envelope(result, request_context)


@router.post(
    "/manage/retention-policies",
    response_model=DataEnvelope[RetentionPolicyRead],
    status_code=status.HTTP_201_CREATED,
    summary="Create retention-policy metadata",
)
async def create_retention_policy(
    payload: RetentionPolicyCreate,
    response: Response,
    request_context: Annotated[
        RequestContext,
        Depends(get_authenticated_tenant_request_context),
    ],
    _authorized: Annotated[
        AuthenticatedSession,
        Depends(require_permission("retention_policy:manage:tenant")),
    ],
    handler: Annotated[PrivacyCommandHandler, Depends(get_privacy_command_handler)],
    idempotency_key: Annotated[str | None, Depends(get_idempotency_key)],
) -> DataEnvelope[RetentionPolicyRead]:
    _prevent_storage(response)
    result = await handler.create_retention_policy(
        context=request_context,
        payload=payload,
        idempotency_key=idempotency_key,
    )
    return data_envelope(result, request_context)


@router.patch(
    "/manage/retention-policies/{policy_id}",
    response_model=DataEnvelope[RetentionPolicyRead],
    summary="Update retention-policy metadata",
)
async def update_retention_policy(
    policy_id: UUID,
    payload: RetentionPolicyUpdate,
    response: Response,
    request_context: Annotated[
        RequestContext,
        Depends(get_authenticated_tenant_request_context),
    ],
    _authorized: Annotated[
        AuthenticatedSession,
        Depends(require_permission("retention_policy:manage:tenant")),
    ],
    handler: Annotated[PrivacyCommandHandler, Depends(get_privacy_command_handler)],
    idempotency_key: Annotated[str | None, Depends(get_idempotency_key)],
) -> DataEnvelope[RetentionPolicyRead]:
    _prevent_storage(response)
    result = await handler.update_retention_policy(
        context=request_context,
        policy_id=policy_id,
        payload=payload,
        idempotency_key=idempotency_key,
    )
    return data_envelope(result, request_context)


@router.post(
    "/manage/retention-policies/dry-run",
    response_model=DataEnvelope[RetentionDryRunRead],
    summary="Run a count-only retention inventory",
)
async def dry_run_retention_policies(
    payload: RetentionDryRunRequest,
    response: Response,
    request_context: Annotated[
        RequestContext,
        Depends(get_authenticated_tenant_request_context),
    ],
    _authorized: Annotated[
        AuthenticatedSession,
        Depends(require_permission("retention_policy:manage:tenant")),
    ],
    handler: Annotated[PrivacyCommandHandler, Depends(get_privacy_command_handler)],
) -> DataEnvelope[RetentionDryRunRead]:
    _prevent_storage(response)
    result = await handler.retention_dry_run(
        context=request_context,
        payload=payload,
    )
    return data_envelope(result, request_context)


async def _transition_consent(
    *,
    purpose_id: UUID,
    action: PrivacyConsentAction,
    response: Response,
    request_context: RequestContext,
    handler: PrivacyCommandHandler,
    idempotency_key: str | None,
) -> DataEnvelope[ConsentPurposeStateRead]:
    _prevent_storage(response)
    result = await handler.transition_consent(
        context=request_context,
        purpose_id=purpose_id,
        action=action,
        idempotency_key=idempotency_key,
    )
    return data_envelope(result, request_context)


def _prevent_storage(response: Response) -> None:
    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"


__all__ = ["router"]
