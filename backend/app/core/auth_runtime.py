"""Application-owned composition for password and short-lived access credential adapters."""

from dataclasses import dataclass
from datetime import timedelta
from secrets import token_bytes

from app.core.config import Settings
from app.platform.identity import AccessTokenCodec, PasswordManager

AUTH_RUNTIME_STATE_KEY = "auth_runtime"


@dataclass(frozen=True, slots=True)
class AuthRuntime:
    access_tokens: AccessTokenCodec
    password_manager: PasswordManager


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

    return AuthRuntime(
        access_tokens=AccessTokenCodec(
            signing_key,
            ttl=timedelta(minutes=settings.auth_access_token_ttl_minutes),
        ),
        password_manager=PasswordManager(
            max_concurrent_operations=settings.auth_argon2_max_concurrency
        ),
    )


__all__ = ["AUTH_RUNTIME_STATE_KEY", "AuthRuntime", "create_auth_runtime"]
