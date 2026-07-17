"""Strict public process health response contracts."""

from __future__ import annotations

from datetime import timedelta
from typing import Literal, Self

from pydantic import AwareDatetime, BaseModel, ConfigDict, field_validator, model_validator


class HealthLiveRead(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    status: Literal["ok"]
    service: str
    version: str
    commit_sha: str
    build_timestamp: AwareDatetime | None

    @field_validator("build_timestamp")
    @classmethod
    def require_utc_build_timestamp(cls, value: AwareDatetime | None) -> AwareDatetime | None:
        if value is not None and value.utcoffset() != timedelta(0):
            raise ValueError("Health build timestamp must be UTC")
        return value


class HealthReadinessComponentsRead(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    database: Literal["ready", "unavailable"]


class HealthReadinessRead(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    status: Literal["ready", "unavailable"]
    service: str
    version: str
    commit_sha: str
    build_timestamp: AwareDatetime | None
    components: HealthReadinessComponentsRead

    @field_validator("build_timestamp")
    @classmethod
    def require_utc_build_timestamp(cls, value: AwareDatetime | None) -> AwareDatetime | None:
        if value is not None and value.utcoffset() != timedelta(0):
            raise ValueError("Health build timestamp must be UTC")
        return value

    @model_validator(mode="after")
    def require_consistent_readiness(self) -> Self:
        if self.status != self.components.database:
            raise ValueError("Health readiness status must match the database component")
        return self


__all__ = [
    "HealthLiveRead",
    "HealthReadinessComponentsRead",
    "HealthReadinessRead",
]
