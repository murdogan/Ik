from datetime import UTC, datetime
from typing import Annotated
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, Request, Response, status

from app.api.auth_dependencies import (
    AuthenticatedSession,
    get_application_settings,
    get_auth_runtime,
    get_auth_session_service,
    get_authentication_rate_limit_service,
    get_authentication_service,
    get_password_recovery_service,
    require_authenticated_session,
)
from app.api.dependencies import get_request_context
from app.api.errors import (
    AUTH_VALIDATION_RESPONSES,
    AUTHENTICATION_RATE_LIMIT_RESPONSES,
    AUTHENTICATION_REQUIRED_RESPONSES,
    UNEXPECTED_ERROR_RESPONSES,
    authentication_rate_limit_error,
    authentication_required_error,
    session_invalid_error,
)
from app.api.openapi import AUTHENTICATION_TAG, with_correlation_response_headers
from app.core.auth_runtime import AuthRuntime
from app.core.config import Settings
from app.platform.audit import AuditContext
from app.platform.errors import api_error_handler
from app.platform.identity import AccessPrincipal, InvalidAccessTokenError
from app.platform.request_context import RequestContext
from app.platform.responses import DataEnvelope, data_envelope
from app.schemas.auth import (
    ActivationRead,
    ActivationRequest,
    AuthenticatedLoginRead,
    AuthTenantRead,
    AuthUserRead,
    LoginOutcomeRead,
    LoginRead,
    LoginRequest,
    MeRead,
    OrganizationChoiceRead,
    OrganizationSelectionRead,
    OrganizationSelectionRequest,
    OrganizationSwitchRequest,
    PasswordResetAcceptedRead,
    PasswordResetCompletedRead,
    PasswordResetConfirmRequest,
    PasswordResetStartRequest,
)
from app.schemas.authorization import RoleSummaryRead
from app.services.auth_session_service import AuthSessionService, InvalidSessionError, SessionGrant
from app.services.authentication_rate_limit_service import (
    AuthenticationRateLimitExceededError,
    AuthenticationRateLimitService,
)
from app.services.authentication_service import (
    AuthenticatedUser,
    AuthenticationService,
    OrganizationSelectionRequired,
)
from app.services.password_recovery_service import PasswordRecoveryService

router = APIRouter(
    prefix="/api/v1/auth",
    tags=[AUTHENTICATION_TAG],
    responses=with_correlation_response_headers(
        {
            **AUTH_VALIDATION_RESPONSES,
            **UNEXPECTED_ERROR_RESPONSES,
        }
    ),
)
me_router = APIRouter(
    prefix="/api/v1",
    tags=[AUTHENTICATION_TAG],
    responses=with_correlation_response_headers(
        {
            **AUTHENTICATION_REQUIRED_RESPONSES,
            **UNEXPECTED_ERROR_RESPONSES,
        }
    ),
)


@router.post(
    "/login",
    response_model=DataEnvelope[LoginOutcomeRead],
    summary="Log in with a global email identity",
    description=(
        "Verifies email and password before discovering active organization memberships. One "
        "membership starts a tenant-bound session; multiple memberships return only safe display "
        "metadata and a short-lived selection transaction."
    ),
    responses=with_correlation_response_headers({200: {}, **AUTHENTICATION_RATE_LIMIT_RESPONSES}),
)
async def login(
    payload: LoginRequest,
    response: Response,
    request: Request,
    request_context: Annotated[RequestContext, Depends(get_request_context)],
    service: Annotated[AuthenticationService, Depends(get_authentication_service)],
    auth_runtime: Annotated[AuthRuntime, Depends(get_auth_runtime)],
    rate_limits: Annotated[
        AuthenticationRateLimitService,
        Depends(get_authentication_rate_limit_service),
    ],
) -> DataEnvelope[LoginOutcomeRead] | Response:
    audit_context = AuditContext.from_request_context(request_context)
    try:
        await rate_limits.consume_login_attempt(
            source_address=_request_source_address(request),
            normalized_email=payload.email,
        )
    except AuthenticationRateLimitExceededError as exc:
        await service.record_global_login_failure(audit_context)
        error_response = await api_error_handler(
            request,
            authentication_rate_limit_error(),
        )
        error_response.headers["Retry-After"] = str(exc.retry_after_seconds)
        _prevent_credential_caching(error_response)
        return error_response
    result = await service.login(
        email=payload.email,
        password=payload.password.get_secret_value(),
        audit_context=audit_context,
    )
    _prevent_credential_caching(response)
    if isinstance(result, OrganizationSelectionRequired):
        return data_envelope(
            OrganizationSelectionRead(
                status="organization_selection_required",
                selection_transaction=result.selection_transaction,
                expires_in=result.expires_in,
                organizations=[
                    OrganizationChoiceRead(
                        selection_key=choice.selection_key,
                        display_name=choice.display_name,
                    )
                    for choice in result.organizations
                ],
            ),
            request_context,
        )
    _set_refresh_cookie(response, result, auth_runtime)
    return data_envelope(
        AuthenticatedLoginRead(
            status="authenticated",
            access_token=result.access_token,
            expires_in=result.expires_in,
            user=_auth_user_read(result.user),
        ),
        request_context,
    )


@router.post(
    "/select-organization",
    response_model=DataEnvelope[AuthenticatedLoginRead],
    summary="Select an organization after identity verification",
    description=(
        "Consumes a short-lived, one-use organization-selection credential and opaque "
        "choice, then starts a session bound to the selected active membership and tenant."
    ),
    responses=with_correlation_response_headers({200: {}, 400: {}}),
)
async def select_organization(
    payload: OrganizationSelectionRequest,
    response: Response,
    request: Request,
    request_context: Annotated[RequestContext, Depends(get_request_context)],
    service: Annotated[AuthenticationService, Depends(get_authentication_service)],
    auth_runtime: Annotated[AuthRuntime, Depends(get_auth_runtime)],
    settings: Annotated[Settings, Depends(get_application_settings)],
) -> DataEnvelope[AuthenticatedLoginRead]:
    _require_trusted_browser_origin(request, settings)
    result = await service.select_organization(
        raw_token=payload.selection_transaction.get_secret_value(),
        selection_key=payload.selection_key,
        audit_context=AuditContext.from_request_context(request_context),
    )
    _set_refresh_cookie(response, result, auth_runtime)
    _prevent_credential_caching(response)
    return data_envelope(
        AuthenticatedLoginRead(
            status="authenticated",
            access_token=result.access_token,
            expires_in=result.expires_in,
            user=_auth_user_read(result.user),
        ),
        request_context,
    )


@router.post(
    "/organization-selection",
    response_model=DataEnvelope[OrganizationSelectionRead],
    summary="Prepare a controlled organization switch",
    description=(
        "Derives the global identity from the validated membership-bound session, returns "
        "opaque choices for its other active memberships, and revokes the previous tenant "
        "session before the switch continues. No caller tenant context is accepted."
    ),
    responses=with_correlation_response_headers({200: {}, 409: {}}),
)
async def prepare_organization_switch(
    response: Response,
    request: Request,
    authenticated: Annotated[
        AuthenticatedSession,
        Depends(require_authenticated_session),
    ],
    request_context: Annotated[RequestContext, Depends(get_request_context)],
    authentication: Annotated[
        AuthenticationService,
        Depends(get_authentication_service),
    ],
    sessions: Annotated[AuthSessionService, Depends(get_auth_session_service)],
    auth_runtime: Annotated[AuthRuntime, Depends(get_auth_runtime)],
    settings: Annotated[Settings, Depends(get_application_settings)],
    _payload: OrganizationSwitchRequest | None = None,
) -> DataEnvelope[OrganizationSelectionRead]:
    _require_trusted_browser_origin(request, settings)
    principal = authenticated.principal
    result = await authentication.prepare_organization_switch(
        tenant_id=principal.tenant_id,
        membership_id=principal.membership_id,
        user_id=principal.user_id,
    )
    revoked = await sessions.revoke_for_organization_switch(
        principal,
        audit_context=AuditContext.from_request_context(request_context),
    )
    if not revoked:
        raise InvalidSessionError()
    await sessions.revoke(
        request.cookies.get(auth_runtime.refresh_cookie.name),
        audit_context=AuditContext.from_request_context(request_context),
        revocation_reason="organization_switch",
    )
    _clear_refresh_cookie(response, auth_runtime)
    _prevent_credential_caching(response)
    return data_envelope(
        OrganizationSelectionRead(
            status="organization_selection_required",
            selection_transaction=result.selection_transaction,
            expires_in=result.expires_in,
            organizations=[
                OrganizationChoiceRead(
                    selection_key=choice.selection_key,
                    display_name=choice.display_name,
                )
                for choice in result.organizations
            ],
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
        result = await service.refresh(
            raw_token,
            audit_context=AuditContext.from_request_context(request_context),
        )
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
    request_context: Annotated[RequestContext, Depends(get_request_context)],
    service: Annotated[AuthSessionService, Depends(get_auth_session_service)],
    auth_runtime: Annotated[AuthRuntime, Depends(get_auth_runtime)],
    settings: Annotated[Settings, Depends(get_application_settings)],
) -> Response:
    _require_trusted_browser_origin(request, settings)
    await service.revoke(
        request.cookies.get(auth_runtime.refresh_cookie.name),
        principal=_optional_access_principal(request, auth_runtime),
        audit_context=AuditContext.from_request_context(request_context),
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
    summary="Complete an invitation",
    description=(
        "Consumes one hashed, expiring activation credential exactly once. A new identity "
        "establishes its Argon2id password; an existing active identity proves its current "
        "password and activates only the pending tenant membership without replacing it."
    ),
    responses=with_correlation_response_headers({200: {}, **AUTHENTICATION_RATE_LIMIT_RESPONSES}),
)
async def activate(
    payload: ActivationRequest,
    response: Response,
    request: Request,
    request_context: Annotated[RequestContext, Depends(get_request_context)],
    service: Annotated[AuthenticationService, Depends(get_authentication_service)],
    rate_limits: Annotated[
        AuthenticationRateLimitService,
        Depends(get_authentication_rate_limit_service),
    ],
) -> DataEnvelope[ActivationRead] | Response:
    try:
        await rate_limits.consume_activation_attempt(
            source_address=_request_source_address(request),
            raw_token=payload.token.get_secret_value(),
        )
    except AuthenticationRateLimitExceededError as exc:
        return await _authentication_rate_limit_response(request, exc)
    user = await service.activate(
        raw_token=payload.token.get_secret_value(),
        password=payload.password.get_secret_value(),
        audit_context=AuditContext.from_request_context(request_context),
    )
    _prevent_credential_caching(response)
    return data_envelope(
        ActivationRead(user=_auth_user_read(user)),
        request_context,
    )


@router.post(
    "/password-reset/request",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=DataEnvelope[PasswordResetAcceptedRead],
    summary="Request a password reset",
    description=(
        "Always returns the same accepted response and discloses no account or organization "
        "metadata. Eligible identities receive a separate hashed, expiring recovery credential "
        "through the configured delivery adapter."
    ),
    responses=with_correlation_response_headers({202: {}, **AUTHENTICATION_RATE_LIMIT_RESPONSES}),
)
async def request_password_reset(
    payload: PasswordResetStartRequest,
    response: Response,
    request: Request,
    request_context: Annotated[RequestContext, Depends(get_request_context)],
    service: Annotated[
        PasswordRecoveryService,
        Depends(get_password_recovery_service),
    ],
    rate_limits: Annotated[
        AuthenticationRateLimitService,
        Depends(get_authentication_rate_limit_service),
    ],
) -> DataEnvelope[PasswordResetAcceptedRead] | Response:
    try:
        await rate_limits.consume_password_reset_attempt(
            source_address=_request_source_address(request),
            normalized_email=payload.email,
        )
    except AuthenticationRateLimitExceededError as exc:
        return await _authentication_rate_limit_response(request, exc)
    await service.request_reset(
        email=payload.email,
        audit_context=AuditContext.from_request_context(request_context),
    )
    _prevent_credential_caching(response)
    return data_envelope(PasswordResetAcceptedRead(), request_context)


@router.post(
    "/password-reset/confirm",
    response_model=DataEnvelope[PasswordResetCompletedRead],
    summary="Complete a password reset",
    description=(
        "Consumes one hashed, expiring recovery credential exactly once, replaces the global "
        "Argon2id credential, and revokes outstanding tenant, platform, and organization-selection "
        "sessions."
    ),
    responses=with_correlation_response_headers(
        {200: {}, 400: {}, **AUTHENTICATION_RATE_LIMIT_RESPONSES}
    ),
)
async def confirm_password_reset(
    payload: PasswordResetConfirmRequest,
    response: Response,
    request: Request,
    request_context: Annotated[RequestContext, Depends(get_request_context)],
    service: Annotated[
        PasswordRecoveryService,
        Depends(get_password_recovery_service),
    ],
    rate_limits: Annotated[
        AuthenticationRateLimitService,
        Depends(get_authentication_rate_limit_service),
    ],
) -> DataEnvelope[PasswordResetCompletedRead] | Response:
    try:
        await rate_limits.consume_password_reset_confirmation(
            source_address=_request_source_address(request),
            raw_token=payload.token.get_secret_value(),
        )
    except AuthenticationRateLimitExceededError as exc:
        return await _authentication_rate_limit_response(request, exc)
    await service.confirm_reset(
        raw_token=payload.token.get_secret_value(),
        password=payload.password.get_secret_value(),
        audit_context=AuditContext.from_request_context(request_context),
    )
    _prevent_credential_caching(response)
    return data_envelope(PasswordResetCompletedRead(), request_context)


def _auth_user_read(user: AuthenticatedUser) -> AuthUserRead:
    return AuthUserRead(
        id=user.id,
        tenant_id=user.tenant_id,
        email=user.email,
        full_name=user.full_name,
        tenant=AuthTenantRead(slug=user.tenant_slug, name=user.tenant_name),
        workspace_scope=user.workspace_scope,
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
    )


def _login_read(result: SessionGrant) -> LoginRead:
    return LoginRead(
        access_token=result.access_token,
        expires_in=result.expires_in,
        user=_auth_user_read(result.user),
    )


def _request_source_address(request: Request) -> str:
    client = request.client
    if client is None or not client.host:
        return "unknown"
    return client.host[:128]


async def _authentication_rate_limit_response(
    request: Request,
    exc: AuthenticationRateLimitExceededError,
) -> Response:
    error_response = await api_error_handler(
        request,
        authentication_rate_limit_error(),
    )
    error_response.headers["Retry-After"] = str(exc.retry_after_seconds)
    _prevent_credential_caching(error_response)
    return error_response


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
