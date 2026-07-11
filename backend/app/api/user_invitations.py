from typing import Annotated

from fastapi import APIRouter, Depends, Response, status

from app.api.auth_dependencies import (
    get_user_invitation_service,
    require_invitation_principal,
)
from app.api.dependencies import get_request_context
from app.api.errors import (
    AUTH_VALIDATION_RESPONSES,
    AUTHENTICATION_REQUIRED_RESPONSES,
    INVITATION_AUTHORIZATION_RESPONSES,
    INVITATION_CONFLICT_RESPONSES,
    UNEXPECTED_ERROR_RESPONSES,
)
from app.api.openapi import USER_ADMINISTRATION_TAG, with_correlation_response_headers
from app.platform.identity import AccessPrincipal
from app.platform.request_context import RequestContext
from app.platform.responses import DataEnvelope, data_envelope
from app.schemas.auth import InvitationRead, InvitationRequest, InvitationUserRead
from app.services.user_invitation_service import UserInvitationService

router = APIRouter(
    prefix="/api/v1/users",
    tags=[USER_ADMINISTRATION_TAG],
    responses=with_correlation_response_headers({
        **AUTHENTICATION_REQUIRED_RESPONSES,
        **INVITATION_AUTHORIZATION_RESPONSES,
        **AUTH_VALIDATION_RESPONSES,
        **INVITATION_CONFLICT_RESPONSES,
        **UNEXPECTED_ERROR_RESPONSES,
    }),
)


@router.post(
    "/invitations",
    status_code=status.HTTP_201_CREATED,
    response_model=DataEnvelope[InvitationRead],
    summary="Invite a user to the authenticated tenant",
    description=(
        "Derives tenant and actor only from a signed short-lived access credential. The actor "
        "must be active and hold the server-controlled F2A invitation capability; tenant headers "
        "and request payload fields never authorize or select the target tenant."
    ),
    responses=with_correlation_response_headers({201: {}}),
)
async def create_invitation(
    payload: InvitationRequest,
    response: Response,
    principal: Annotated[AccessPrincipal, Depends(require_invitation_principal)],
    request_context: Annotated[RequestContext, Depends(get_request_context)],
    service: Annotated[UserInvitationService, Depends(get_user_invitation_service)],
) -> DataEnvelope[InvitationRead]:
    result = await service.invite(
        principal=principal,
        email=payload.email,
        full_name=payload.full_name,
    )
    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"
    return data_envelope(
        InvitationRead(
            user=InvitationUserRead(
                id=result.user_id,
                email=result.email,
                full_name=result.full_name,
            ),
            activation_url=result.activation_url,
            expires_at=result.expires_at,
        ),
        request_context,
    )


__all__ = ["router"]
