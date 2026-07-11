from typing import Annotated

from fastapi import APIRouter, Depends, Response

from app.api.auth_dependencies import get_authentication_service
from app.api.dependencies import get_request_context
from app.api.errors import AUTH_VALIDATION_RESPONSES, UNEXPECTED_ERROR_RESPONSES
from app.api.openapi import AUTHENTICATION_TAG, with_correlation_response_headers
from app.platform.request_context import RequestContext
from app.platform.responses import DataEnvelope, data_envelope
from app.schemas.auth import (
    ActivationRead,
    ActivationRequest,
    AuthTenantRead,
    AuthUserRead,
    LoginRead,
    LoginRequest,
)
from app.services.authentication_service import AuthenticatedUser, AuthenticationService

router = APIRouter(
    prefix="/api/v1/auth",
    tags=[AUTHENTICATION_TAG],
    responses=with_correlation_response_headers({
        **AUTH_VALIDATION_RESPONSES,
        **UNEXPECTED_ERROR_RESPONSES,
    }),
)


@router.post(
    "/login",
    response_model=DataEnvelope[LoginRead],
    summary="Log in with tenant-aware credentials",
    description=(
        "Uses the organization code only as a public discovery selector, then verifies the "
        "password in a separately tenant-bound database session. All credential and account "
        "failures share one generic response."
    ),
    responses=with_correlation_response_headers({200: {}}),
)
async def login(
    payload: LoginRequest,
    response: Response,
    request_context: Annotated[RequestContext, Depends(get_request_context)],
    service: Annotated[AuthenticationService, Depends(get_authentication_service)],
) -> DataEnvelope[LoginRead]:
    result = await service.login(
        tenant_slug=payload.tenant_slug,
        email=payload.email,
        password=payload.password.get_secret_value(),
    )
    _prevent_credential_caching(response)
    return data_envelope(
        LoginRead(
            access_token=result.access_token,
            expires_in=result.expires_in,
            user=_auth_user_read(result.user),
        ),
        request_context,
    )


@router.post(
    "/activate",
    response_model=DataEnvelope[ActivationRead],
    summary="Activate an invited user and set a password",
    description=(
        "Consumes one hashed, expiring activation credential exactly once and stores the new "
        "password only as Argon2id within the same transaction."
    ),
    responses=with_correlation_response_headers({200: {}}),
)
async def activate(
    payload: ActivationRequest,
    response: Response,
    request_context: Annotated[RequestContext, Depends(get_request_context)],
    service: Annotated[AuthenticationService, Depends(get_authentication_service)],
) -> DataEnvelope[ActivationRead]:
    user = await service.activate(
        raw_token=payload.token.get_secret_value(),
        password=payload.password.get_secret_value(),
    )
    _prevent_credential_caching(response)
    return data_envelope(
        ActivationRead(user=_auth_user_read(user)),
        request_context,
    )


def _auth_user_read(user: AuthenticatedUser) -> AuthUserRead:
    return AuthUserRead(
        id=user.id,
        tenant_id=user.tenant_id,
        email=user.email,
        full_name=user.full_name,
        tenant=AuthTenantRead(slug=user.tenant_slug, name=user.tenant_name),
    )


def _prevent_credential_caching(response: Response) -> None:
    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"


__all__ = ["router"]
