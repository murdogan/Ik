from functools import lru_cache
from typing import Literal
from urllib.parse import urlsplit

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

APP_SETTINGS_STATE_KEY = "settings"


class Settings(BaseSettings):
    app_name: str = "IK Platform API"
    app_version: str = "0.1.0"
    environment: Literal["local", "dev", "test", "staging", "prod"] = "local"
    database_url: str = "postgresql+asyncpg://ik:ik@localhost:5432/ik"
    database_pool_size: int = Field(default=5, ge=1)
    database_max_overflow: int = Field(default=10, ge=0)
    database_pool_timeout_seconds: float = Field(default=30.0, gt=0)
    database_pool_recycle_seconds: int = Field(default=1800, ge=0)
    database_connect_timeout_seconds: float = Field(default=10.0, gt=0)
    database_statement_timeout_ms: int = Field(default=30_000, ge=0)
    database_idle_transaction_timeout_ms: int = Field(default=60_000, ge=0)
    auth_signing_key: SecretStr | None = None
    auth_access_token_ttl_minutes: int = Field(default=15, ge=1, le=60)
    auth_refresh_token_ttl_days: int = Field(default=14, ge=7, le=30)
    auth_activation_token_ttl_hours: int = Field(default=48, ge=1, le=168)
    auth_organization_selection_ttl_minutes: int = Field(default=5, ge=1, le=15)
    auth_argon2_max_concurrency: int = Field(default=2, ge=1, le=8)
    auth_login_rate_limit_window_seconds: int = Field(default=300, ge=10, le=3600)
    auth_login_rate_limit_source_attempts: int = Field(default=40, ge=1, le=1000)
    auth_login_rate_limit_identity_attempts: int = Field(default=8, ge=1, le=100)
    frontend_base_url: str = "http://localhost:3000"

    model_config = SettingsConfigDict(env_prefix="IK_", env_file=".env", extra="ignore")

    @field_validator("frontend_base_url")
    @classmethod
    def validate_frontend_base_url(cls, value: str) -> str:
        normalized = value.rstrip("/")
        if any(ord(character) < 32 for character in normalized):
            raise ValueError("frontend_base_url contains invalid control characters")
        try:
            parsed = urlsplit(normalized)
            port = parsed.port
        except ValueError as exc:
            raise ValueError("frontend_base_url must be a valid absolute URL") from exc
        if (
            parsed.scheme not in {"http", "https"}
            or parsed.hostname is None
            or parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
            or (port is not None and not 1 <= port <= 65_535)
        ):
            raise ValueError("frontend_base_url must be an absolute HTTP(S) URL")
        return normalized


@lru_cache
def get_settings() -> Settings:
    return Settings()
