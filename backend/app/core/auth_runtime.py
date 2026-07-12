"""Application-owned composition for password and session credential adapters."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from secrets import token_bytes

from app.core.config import Settings
from app.platform.identity import AccessTokenCodec, PasswordManager
from app.services.authentication_rate_limit_service import (
    AuthenticationRateLimitKeyHasher,
    AuthenticationRateLimitPolicy,
)

AUTH_RUNTIME_STATE_KEY = "auth_runtime"


@dataclass(frozen=True, slots=True)
class AuthRuntime:
    access_tokens: AccessTokenCodec
    password_manager: PasswordManager
    refresh_ttl: timedelta
    organization_selection_ttl: timedelta
    rate_limit_key_hasher: AuthenticationRateLimitKeyHasher
    rate_limit_policy: AuthenticationRateLimitPolicy
    refresh_cookie: RefreshCookiePolicy


@dataclass(frozen=True, slots=True)
class RefreshCookiePolicy:
    """Host-only browser policy; production uses the enforced ``__Host-`` contract."""

    name: str
    secure: bool
    path: str = "/"
    same_site: str = "lax"


def create_auth_runtime(settings: Settings) -> AuthRuntime:
    configured_key = settings.auth_signing_key
    if configured_key is None:
        if settings.environment in {"staging", "prod"}:
            raise RuntimeError(
                "IK_AUTH_SIGNING_KEY is required in staging and production"
            )
        signing_key = token_bytes(48)
    else:
        signing_key = configured_key.get_secret_value().encode("utf-8")

    if settings.environment in {"staging", "prod"} and not settings.frontend_base_url.startswith(
        "https://"
    ):
        raise RuntimeError("IK_FRONTEND_BASE_URL must use HTTPS in staging and production")

    secure_cookie = settings.environment in {"staging", "prod"}
    return AuthRuntime(
        access_tokens=AccessTokenCodec(
            signing_key,
            ttl=timedelta(minutes=settings.auth_access_token_ttl_minutes),
        ),
        password_manager=PasswordManager(
            max_concurrent_operations=settings.auth_argon2_max_concurrency
        ),
        refresh_ttl=timedelta(days=settings.auth_refresh_token_ttl_days),
        organization_selection_ttl=timedelta(
            minutes=settings.auth_organization_selection_ttl_minutes
        ),
        rate_limit_key_hasher=AuthenticationRateLimitKeyHasher(
            signing_key + b"/authentication-rate-limit"
        ),
        rate_limit_policy=AuthenticationRateLimitPolicy(
            window=timedelta(
                seconds=settings.auth_login_rate_limit_window_seconds
            ),
            source_attempts=settings.auth_login_rate_limit_source_attempts,
            identity_attempts=settings.auth_login_rate_limit_identity_attempts,
        ),
        refresh_cookie=RefreshCookiePolicy(
            name="__Host-wf_refresh" if secure_cookie else "wf_refresh",
            secure=secure_cookie,
        ),
    )


__all__ = [
    "AUTH_RUNTIME_STATE_KEY",
    "AuthRuntime",
    "RefreshCookiePolicy",
    "create_auth_runtime",
]
