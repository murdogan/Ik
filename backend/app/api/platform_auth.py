"""Dedicated HTTP surface for the tenantless platform authentication realm."""

from datetime import UTC, datetime
from typing import Annotated
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, Request, Response, status

from app.api.auth_dependencies import (
    PlatformAuthenticatedSession,
    get_application_settings,
    get_auth_runtime,
    get_authentication_rate_limit_service,
    get_platform_auth_session_service,
    get_platform_authentication_service,
    require_platform_authenticated_session,
)
from app.api.dependencies import get_request_context
from app.api.errors import (
    AUTH_VALIDATION_RESPONSES,
    AUTHENTICATION_RATE_LIMIT_RESPONSES,
    PLATFORM_AUTHORIZATION_RESPONSES,
    UNEXPECTED_ERROR_RESPONSES,
    authentication_rate_limit_error,
    platform_access_denied_error,
    session_invalid_error,
)
from app.api.openapi import AUTHENTICATION_TAG, with_correlation_response_headers
from app.core.auth_runtime import AuthRuntime, RefreshCookiePolicy
from app.core.config import Settings
from app.platform.audit import AuditContext
from app.platform.errors import api_error_handler
from app.platform.identity import InvalidPlatformAccessTokenError, PlatformAccessPrincipal
from app.platform.request_context import RequestContext
from app.platform.responses import DataEnvelope, data_envelope
from app.schemas.authorization import RoleSummaryRead
from app.schemas.platform_auth import (
    PlatformAuthenticatedLoginRead,
    PlatformAuthUserRead,
    PlatformLoginRead,
    PlatformLoginRequest,
    PlatformMeRead,
)
from app.services.authentication_rate_limit_service import (
    AuthenticationRateLimitExceededError,
    AuthenticationRateLimitService,
)
from app.services.platform_auth_session_service import (
    InvalidPlatformSessionError,
    PlatformAuthenticatedUser,
    PlatformAuthSessionService,
    PlatformSessionGrant,
)
from app.services.platform_authentication_service import PlatformAuthenticationService

router = APIRouter(
    prefix="/api/v1/platform/auth",
    tags=[AUTHENTICATION_TAG],
    responses=with_correlation_response_headers(
        {**AUTH_VALIDATION_RESPONSES, **UNEXPECTED_ERROR_RESPONSES}
    ),
)
me_router = APIRouter(
    prefix="/api/v1/platform",
    tags=[AUTHENTICATION_TAG],
    responses=with_correlation_response_headers(
        {**PLATFORM_AUTHORIZATION_RESPONSES, **UNEXPECTED_ERROR_RESPONSES}
    ),
)


@router.post(
    "/login",
    response_model=DataEnvelope[PlatformAuthenticatedLoginRead],
    summary="Log in to the platform management realm",
    description=(
        "Verifies the global email identity, then requires an active platform role. Tenant "
        "memberships and organization choices are never accepted or returned by this contract."
    ),
    responses=with_correlation_response_headers(
        {200: {}, 403: {}, **AUTHENTICATION_RATE_LIMIT_RESPONSES}
    ),
)
async def platform_login(
    payload: PlatformLoginRequest,
    response: Response,
    request: Request,
    request_context: Annotated[RequestContext, Depends(get_request_context)],
    service: Annotated[
        PlatformAuthenticationService,
        Depends(get_platform_authentication_service),
    ],
    rate_limits: Annotated[
        AuthenticationRateLimitService,
        Depends(get_authentication_rate_limit_service),
    ],
    auth_runtime: Annotated[AuthRuntime, Depends(get_auth_runtime)],
) -> DataEnvelope[PlatformAuthenticatedLoginRead] | Response:
    audit_context = AuditContext.from_request_context(request_context)
    try:
        await rate_limits.consume_login_attempt(
            source_address=_request_source_address(request),
            normalized_email=payload.email,
        )
    except AuthenticationRateLimitExceededError as exc:
        await service.record_login_failure(audit_context)
        error_response = await api_error_handler(request, authentication_rate_limit_error())
        error_response.headers["Retry-After"] = str(exc.retry_after_seconds)
        _prevent_credential_caching(error_response)
        return error_response

    result = await service.login(
        email=payload.email,
        password=payload.password.get_secret_value(),
        audit_context=audit_context,
    )
    _set_refresh_cookie(response, result, auth_runtime.platform_refresh_cookie)
    _prevent_credential_caching(response)
    return data_envelope(
        PlatformAuthenticatedLoginRead(
            access_token=result.access_token,
            expires_in=result.expires_in,
            user=_platform_user_read(result.user),
        ),
        request_context,
    )


@router.post(
    "/refresh",
    response_model=DataEnvelope[PlatformLoginRead],
    summary="Rotate the platform browser refresh credential",
    description=(
        "Consumes only the distinct platform HttpOnly refresh cookie and returns only a "
        "platform-audience access credential."
    ),
    responses=with_correlation_response_headers({200: {}}),
)
async def platform_refresh(
    request: Request,
    response: Response,
    request_context: Annotated[RequestContext, Depends(get_request_context)],
    service: Annotated[
        PlatformAuthSessionService,
        Depends(get_platform_auth_session_service),
    ],
    auth_runtime: Annotated[AuthRuntime, Depends(get_auth_runtime)],
    settings: Annotated[Settings, Depends(get_application_settings)],
) -> DataEnvelope[PlatformLoginRead] | Response:
    _require_trusted_browser_origin(request, settings)
    policy = auth_runtime.platform_refresh_cookie
    raw_token = request.cookies.get(policy.name)
    try:
        if raw_token is None:
            raise InvalidPlatformSessionError()
        result = await service.refresh(
            raw_token,
            audit_context=AuditContext.from_request_context(request_context),
        )
    except InvalidPlatformSessionError:
        error_response = await api_error_handler(request, session_invalid_error())
        _clear_refresh_cookie(error_response, policy)
        _prevent_credential_caching(error_response)
        return error_response
    _set_refresh_cookie(response, result, policy)
    _prevent_credential_caching(response)
    return data_envelope(_platform_login_read(result), request_context)


@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
    summary="Log out of the platform management realm",
    description=(
        "Revokes only platform session families selected by the platform cookie or platform "
        "bearer credential, leaving any separate tenant session untouched."
    ),
    responses=with_correlation_response_headers({204: {}}),
)
async def platform_logout(
    request: Request,
    response: Response,
    request_context: Annotated[RequestContext, Depends(get_request_context)],
    service: Annotated[
        PlatformAuthSessionService,
        Depends(get_platform_auth_session_service),
    ],
    auth_runtime: Annotated[AuthRuntime, Depends(get_auth_runtime)],
    settings: Annotated[Settings, Depends(get_application_settings)],
) -> Response:
    _require_trusted_browser_origin(request, settings)
    policy = auth_runtime.platform_refresh_cookie
    await service.revoke(
        request.cookies.get(policy.name),
        principal=_optional_access_principal(request, auth_runtime),
        audit_context=AuditContext.from_request_context(request_context),
    )
    _clear_refresh_cookie(response, policy)
    _prevent_credential_caching(response)
    response.status_code = status.HTTP_204_NO_CONTENT
    return response


@me_router.get(
    "/me",
    response_model=DataEnvelope[PlatformMeRead],
    summary="Read the authenticated platform principal",
    description=(
        "Validates the platform-audience bearer and its active tenantless server-side session. "
        "The response never contains a tenant or organization selector."
    ),
    responses=with_correlation_response_headers({200: {}}),
)
async def platform_me(
    response: Response,
    authenticated: Annotated[
        PlatformAuthenticatedSession,
        Depends(require_platform_authenticated_session),
    ],
    request_context: Annotated[RequestContext, Depends(get_request_context)],
) -> DataEnvelope[PlatformMeRead]:
    _prevent_credential_caching(response)
    return data_envelope(
        PlatformMeRead(user=_platform_user_read(authenticated.user)),
        request_context,
    )


def _platform_user_read(user: PlatformAuthenticatedUser) -> PlatformAuthUserRead:
    return PlatformAuthUserRead(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        roles=[
            RoleSummaryRead(
                id=role.id,
                code=role.code,
                name=role.name,
                scope_type=role.scope_type,
            )
            for role in user.roles
        ],
        permissions=list(user.permissions),
        permission_version=user.permission_version,
        authentication_strength=user.authentication_strength,
    )


def _platform_login_read(result: PlatformSessionGrant) -> PlatformLoginRead:
    return PlatformLoginRead(
        access_token=result.access_token,
        expires_in=result.expires_in,
        user=_platform_user_read(result.user),
    )


def _request_source_address(request: Request) -> str:
    client = request.client
    if client is None or not client.host:
        return "unknown"
    return client.host[:128]


def _set_refresh_cookie(
    response: Response,
    result: PlatformSessionGrant,
    policy: RefreshCookiePolicy,
) -> None:
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


def _clear_refresh_cookie(response: Response, policy: RefreshCookiePolicy) -> None:
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
) -> PlatformAccessPrincipal | None:
    authorization_values = request.headers.getlist("Authorization")
    if len(authorization_values) != 1:
        return None
    scheme, separator, credential = authorization_values[0].partition(" ")
    if separator != " " or scheme.lower() != "bearer" or not credential or " " in credential:
        return None
    try:
        return auth_runtime.platform_access_tokens.decode(credential)
    except InvalidPlatformAccessTokenError:
        return None


def _require_trusted_browser_origin(request: Request, settings: Settings) -> None:
    if request.headers.get("sec-fetch-site", "").lower() == "cross-site":
        raise platform_access_denied_error()
    origin_values = request.headers.getlist("origin")
    if not origin_values:
        return
    if len(origin_values) != 1:
        raise platform_access_denied_error()
    frontend = urlsplit(settings.frontend_base_url)
    expected_origin = f"{frontend.scheme}://{frontend.netloc}"
    if origin_values[0] != expected_origin:
        raise platform_access_denied_error()


def _prevent_credential_caching(response: Response) -> None:
    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"


__all__ = ["me_router", "router"]
