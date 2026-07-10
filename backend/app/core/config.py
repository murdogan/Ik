from functools import lru_cache
from typing import Literal

from pydantic import Field
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

    model_config = SettingsConfigDict(env_prefix="IK_", env_file=".env", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()
