from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "IK Platform API"
    app_version: str = "0.1.0"
    environment: Literal["local", "dev", "staging", "prod"] = "local"

    model_config = SettingsConfigDict(env_prefix="IK_", env_file=".env", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()
