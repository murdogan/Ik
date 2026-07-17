from datetime import UTC, datetime, timedelta
from functools import lru_cache
from re import compile as compile_regex
from typing import Literal
from urllib.parse import urlsplit

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

APP_SETTINGS_STATE_KEY = "settings"
_RELEASE_COMMIT_SHA_PATTERN = compile_regex(r"[0-9a-f]{40}")


class Settings(BaseSettings):
    app_name: str = "IK Platform API"
    app_version: str = "0.1.0"
    environment: Literal["local", "dev", "test", "staging", "prod"] = "local"
    release_commit_sha: str = "development"
    release_build_timestamp: datetime | None = None
    health_readiness_timeout_seconds: float = Field(default=2.0, ge=0.1, le=10.0)
    worker_heartbeat_interval_seconds: float = Field(default=60.0, ge=10.0, le=3600.0)
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
    auth_password_reset_token_ttl_minutes: int = Field(default=15, ge=5, le=60)
    auth_organization_selection_ttl_minutes: int = Field(default=5, ge=1, le=15)
    auth_argon2_max_concurrency: int = Field(default=2, ge=1, le=8)
    auth_login_rate_limit_window_seconds: int = Field(default=300, ge=10, le=3600)
    auth_login_rate_limit_source_attempts: int = Field(default=40, ge=1, le=1000)
    auth_login_rate_limit_identity_attempts: int = Field(default=8, ge=1, le=100)
    frontend_base_url: str = "http://localhost:3000"
    document_storage_backend: Literal["disabled", "s3"] = "disabled"
    document_scanner_backend: Literal["local_clean", "clamav"] = "local_clean"
    document_default_max_size_bytes: int = Field(
        default=20 * 1024 * 1024,
        ge=1,
        le=50 * 1024 * 1024,
    )
    document_upload_ttl_seconds: int = Field(default=300, ge=60, le=900)
    document_download_ttl_seconds: int = Field(default=120, ge=30, le=900)
    document_upload_intent_ttl_minutes: int = Field(default=10, ge=2, le=30)
    document_expiring_window_days: int = Field(default=30, ge=1, le=365)
    s3_internal_endpoint_url: str | None = None
    s3_presign_endpoint_url: str | None = None
    s3_region: str = Field(default="us-east-1", min_length=1, max_length=64)
    s3_bucket: str = Field(default="wealthy-falcon-documents", min_length=3, max_length=63)
    s3_access_key_id: SecretStr | None = None
    s3_secret_access_key: SecretStr | None = None
    s3_session_token: SecretStr | None = None
    s3_addressing_style: Literal["path", "virtual"] = "path"
    s3_connect_timeout_seconds: float = Field(default=5.0, gt=0, le=30)
    s3_read_timeout_seconds: float = Field(default=30.0, gt=0, le=120)
    s3_create_bucket: bool = False
    clamav_host: str | None = None
    clamav_port: int = Field(default=3310, ge=1, le=65_535)
    clamav_connect_timeout_seconds: float = Field(default=5.0, gt=0, le=30)
    clamav_scan_timeout_seconds: float = Field(default=60.0, gt=0, le=300)
    notification_worker_tenant_batch_size: int = Field(default=25, ge=1, le=100)
    notification_worker_event_batch_size: int = Field(default=25, ge=1, le=50)
    notification_worker_delivery_batch_size: int = Field(default=25, ge=1, le=50)
    notification_worker_max_attempts: int = Field(default=5, ge=1, le=10)
    notification_worker_backoff_base_seconds: int = Field(default=30, ge=1, le=3600)
    notification_worker_backoff_max_seconds: int = Field(default=3600, ge=1, le=86_400)
    notification_worker_poll_seconds: float = Field(default=5.0, ge=0.25, le=60.0)
    notification_email_backend: Literal["disabled", "fake"] = "disabled"
    notification_fake_email_failures_before_success: int = Field(default=0, ge=0, le=20)
    reporting_worker_tenant_batch_size: int = Field(default=25, ge=1, le=100)
    reporting_worker_export_batch_size: int = Field(default=5, ge=1, le=20)
    reporting_worker_import_batch_size: int = Field(default=3, ge=1, le=10)
    reporting_worker_max_attempts: int = Field(default=3, ge=1, le=5)
    reporting_worker_poll_seconds: float = Field(default=5.0, ge=0.25, le=60.0)
    reporting_worker_lease_seconds: int = Field(default=900, ge=60, le=3600)
    export_download_ttl_seconds: int = Field(default=300, ge=30, le=300)
    export_artifact_ttl_hours: int = Field(default=24, ge=1, le=24)
    export_max_file_size_bytes: int = Field(
        default=25 * 1024 * 1024,
        ge=1024 * 1024,
        le=50 * 1024 * 1024,
    )

    model_config = SettingsConfigDict(env_prefix="IK_", env_file=".env", extra="ignore")

    @field_validator("release_commit_sha")
    @classmethod
    def validate_release_commit_sha(cls, value: str) -> str:
        if value != "development" and _RELEASE_COMMIT_SHA_PATTERN.fullmatch(value) is None:
            raise ValueError("release_commit_sha must be development or a lowercase commit SHA")
        return value

    @field_validator("release_build_timestamp")
    @classmethod
    def validate_release_build_timestamp(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("release_build_timestamp must include a timezone")
        if value.utcoffset() != timedelta(0):
            raise ValueError("release_build_timestamp must be UTC")
        return value.astimezone(UTC)

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

    @field_validator("s3_internal_endpoint_url", "s3_presign_endpoint_url")
    @classmethod
    def validate_optional_endpoint_url(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.rstrip("/")
        if any(ord(character) < 32 for character in normalized):
            raise ValueError("S3 endpoint contains invalid control characters")
        try:
            parsed = urlsplit(normalized)
            port = parsed.port
        except ValueError as exc:
            raise ValueError("S3 endpoint must be a valid absolute URL") from exc
        if (
            parsed.scheme not in {"http", "https"}
            or parsed.hostname is None
            or parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
            or (port is not None and not 1 <= port <= 65_535)
        ):
            raise ValueError("S3 endpoint must be an absolute HTTP(S) URL")
        return normalized

    @model_validator(mode="after")
    def validate_release_identity(self) -> "Settings":
        if self.environment in {"staging", "prod"} and (
            self.release_commit_sha == "development" or self.release_build_timestamp is None
        ):
            raise ValueError(
                "Staging and production require an immutable commit SHA and build timestamp"
            )
        return self

    @model_validator(mode="after")
    def validate_notification_delivery_mode(self) -> "Settings":
        if self.environment == "prod" and self.notification_email_backend != "disabled":
            raise ValueError("Production notification email requires a real provider adapter")
        if (
            self.notification_email_backend != "fake"
            and self.notification_fake_email_failures_before_success != 0
        ):
            raise ValueError("Fake email failure simulation requires the fake adapter")
        if (
            self.notification_worker_backoff_max_seconds
            < self.notification_worker_backoff_base_seconds
        ):
            raise ValueError("Notification retry maximum must not be below its base delay")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
