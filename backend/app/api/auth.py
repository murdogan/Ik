from datetime import UTC, datetime
from typing import Annotated
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, Request, Response, status

from app.api.auth_dependencies import (
    AuthenticatedSession,
    get_application_settings,
    get_auth_runtime,
    get_auth_session_service,
    get_authentication_service,
    require_authenticated_session,
)
from app.api.dependencies import get_request_context
from app.api.errors import (
    AUTH_VALIDATION_RESPONSES,
    AUTHENTICATION_REQUIRED_RESPONSES,
    UNEXPECTED_ERROR_RESPONSES,
    authentication_required_error,
    session_invalid_error,
)
from app.api.openapi import AUTHENTICATION_TAG, with_correlation_response_headers
from app.core.auth_runtime import AuthRuntime
from app.core.config import Settings
from app.platform.errors import api_error_handler
from app.platform.identity import AccessPrincipal, InvalidAccessTokenError
from app.platform.request_context import RequestContext
from app.platform.responses import DataEnvelope, data_envelope
from app.schemas.auth import (
    ActivationRead,
    ActivationRequest,
    AuthTenantRead,
    AuthUserRead,
    LoginRead,
    LoginRequest,
    MeRead,
)
from app.services.auth_session_service import AuthSessionService, InvalidSessionError, SessionGrant
from app.services.authentication_service import AuthenticatedUser, AuthenticationService

router = APIRouter(
    prefix="/api/v1/auth",
    tags=[AUTHENTICATION_TAG],
    responses=with_correlation_response_headers({
        **AUTH_VALIDATION_RESPONSES,
        **UNEXPECTED_ERROR_RESPONSES,
    }),
)
me_router = APIRouter(
    prefix="/api/v1",
    tags=[AUTHENTICATION_TAG],
    responses=with_correlation_response_headers({
        **AUTHENTICATION_REQUIRED_RESPONSES,
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
    auth_runtime: Annotated[AuthRuntime, Depends(get_auth_runtime)],
) -> DataEnvelope[LoginRead]:
    result = await service.login(
        tenant_slug=payload.tenant_slug,
        email=payload.email,
        password=payload.password.get_secret_value(),
    )
    _set_refresh_cookie(response, result, auth_runtime)
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
    "/refresh",
    response_model=DataEnvelope[LoginRead],
    summary="Rotate the browser refresh credential",
    description=(
        "Consumes the HttpOnly refresh cookie exactly once, rotates its hashed server-side "
        "credential, and returns a new short-lived access credential. Reuse revokes the entire "
        "session family."
    ),
    responses=with_correlation_response_headers({200: {}}),
)
async def refresh(
    request: Request,
    response: Response,
    request_context: Annotated[RequestContext, Depends(get_request_context)],
    service: Annotated[AuthSessionService, Depends(get_auth_session_service)],
    auth_runtime: Annotated[AuthRuntime, Depends(get_auth_runtime)],
    settings: Annotated[Settings, Depends(get_application_settings)],
) -> DataEnvelope[LoginRead] | Response:
    _require_trusted_browser_origin(request, settings)
    raw_token = request.cookies.get(auth_runtime.refresh_cookie.name)
    try:
        if raw_token is None:
            raise InvalidSessionError()
        result = await service.refresh(raw_token)
    except InvalidSessionError:
        error_response = await api_error_handler(request, session_invalid_error())
        _clear_refresh_cookie(error_response, auth_runtime)
        _prevent_credential_caching(error_response)
        return error_response
    _set_refresh_cookie(response, result, auth_runtime)
    _prevent_credential_caching(response)
    return data_envelope(_login_read(result), request_context)


@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
    summary="Log out and revoke the browser session",
    description=(
        "Idempotently revokes session families selected by the HttpOnly cookie or a valid "
        "short-lived bearer credential, then clears the browser credential."
    ),
    responses=with_correlation_response_headers({204: {}}),
)
async def logout(
    request: Request,
    response: Response,
    service: Annotated[AuthSessionService, Depends(get_auth_session_service)],
    auth_runtime: Annotated[AuthRuntime, Depends(get_auth_runtime)],
    settings: Annotated[Settings, Depends(get_application_settings)],
) -> Response:
    _require_trusted_browser_origin(request, settings)
    await service.revoke(
        request.cookies.get(auth_runtime.refresh_cookie.name),
        principal=_optional_access_principal(request, auth_runtime),
    )
    _clear_refresh_cookie(response, auth_runtime)
    _prevent_credential_caching(response)
    response.status_code = status.HTTP_204_NO_CONTENT
    return response


@me_router.get(
    "/me",
    response_model=DataEnvelope[MeRead],
    summary="Read the authenticated user and tenant",
    description=(
        "Validates both the short-lived bearer credential and its active server-side session. "
        "Caller-supplied tenant headers never select this identity."
    ),
    responses=with_correlation_response_headers({200: {}}),
)
async def me(
    response: Response,
    authenticated: Annotated[
        AuthenticatedSession,
        Depends(require_authenticated_session),
    ],
    request_context: Annotated[RequestContext, Depends(get_request_context)],
) -> DataEnvelope[MeRead]:
    _prevent_credential_caching(response)
    return data_envelope(
        MeRead(user=_auth_user_read(authenticated.user)),
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


def _login_read(result: SessionGrant) -> LoginRead:
    return LoginRead(
        access_token=result.access_token,
        expires_in=result.expires_in,
        user=_auth_user_read(result.user),
    )


def _set_refresh_cookie(
    response: Response,
    result: SessionGrant,
    auth_runtime: AuthRuntime,
) -> None:
    policy = auth_runtime.refresh_cookie
    remaining_seconds = max(
        1,
        int((result.refresh_expires_at - datetime.now(UTC)).total_seconds()),
    )
    response.set_cookie(
        key=policy.name,
        value=result.refresh_token,
        max_age=remaining_seconds,
        expires=result.refresh_expires_at,
        path=policy.path,
        secure=policy.secure,
        httponly=True,
        samesite=policy.same_site,
    )


def _clear_refresh_cookie(response: Response, auth_runtime: AuthRuntime) -> None:
    policy = auth_runtime.refresh_cookie
    response.delete_cookie(
        policy.name,
        path=policy.path,
        secure=policy.secure,
        httponly=True,
        samesite=policy.same_site,
    )


def _optional_access_principal(
    request: Request,
    auth_runtime: AuthRuntime,
) -> AccessPrincipal | None:
    authorization_values = request.headers.getlist("Authorization")
    if len(authorization_values) != 1:
        return None
    scheme, separator, credential = authorization_values[0].partition(" ")
    if separator != " " or scheme.lower() != "bearer" or not credential or " " in credential:
        return None
    try:
        return auth_runtime.access_tokens.decode(credential)
    except InvalidAccessTokenError:
        return None


def _require_trusted_browser_origin(request: Request, settings: Settings) -> None:
    if request.headers.get("sec-fetch-site", "").lower() == "cross-site":
        raise authentication_required_error()
    origin_values = request.headers.getlist("origin")
    if not origin_values:
        return
    if len(origin_values) != 1:
        raise authentication_required_error()
    frontend = urlsplit(settings.frontend_base_url)
    expected_origin = f"{frontend.scheme}://{frontend.netloc}"
    if origin_values[0] != expected_origin:
        raise authentication_required_error()


def _prevent_credential_caching(response: Response) -> None:
    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"


__all__ = ["me_router", "router"]
