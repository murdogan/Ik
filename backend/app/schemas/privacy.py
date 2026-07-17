"""Strict request and response contracts for the tenant privacy surfaces."""

from __future__ import annotations

from typing import Self
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models.privacy import (
    PrivacyConsentAction,
    PrivacyNoticeKind,
    PrivacyNoticeStatus,
    RetentionAction,
    RetentionAnchor,
    RetentionDataCategory,
    RetentionPolicyStatus,
)

PRIVACY_NOTICE_LIST_DEFAULT_LIMIT = 30
PRIVACY_NOTICE_LIST_MAX_LIMIT = 100
PRIVACY_CONSENT_PURPOSE_LIMIT = 20
PRIVACY_CONSENT_HISTORY_LIMIT = 50
RETENTION_POLICY_LIMIT = 20

PRIVACY_TITLE_MAX_LENGTH = 200
PRIVACY_BODY_MAX_LENGTH = 20_000
PRIVACY_LOCALE_MAX_LENGTH = 16
PRIVACY_LEGAL_BASIS_MAX_LENGTH = 1_000

_ANCHOR_BY_CATEGORY = {
    RetentionDataCategory.EMPLOYEE_RECORDS: RetentionAnchor.EMPLOYMENT_END_DATE,
    RetentionDataCategory.EMPLOYEE_DOCUMENTS: RetentionAnchor.ARCHIVED_AT,
    RetentionDataCategory.LEAVE_REQUESTS: RetentionAnchor.CREATED_AT,
    RetentionDataCategory.AUDIT_EVENTS: RetentionAnchor.OCCURRED_AT,
}


def _single_line_text(value: str) -> str:
    normalized = " ".join(value.split())
    if not normalized or any(ord(character) < 32 for character in normalized):
        raise ValueError("A non-empty single-line plain-text value is required")
    return normalized


def _plain_text(value: str) -> str:
    normalized = "\n".join(
        line.rstrip() for line in value.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    ).strip()
    if not normalized or any(
        ord(character) < 32 and character not in {"\n", "\t"}
        for character in normalized
    ):
        raise ValueError("A non-empty plain-text value is required")
    return normalized


def _locale(value: str) -> str:
    parts = value.strip().replace("_", "-").split("-")
    if (
        len(parts) not in {1, 2}
        or not parts[0].isalpha()
        or len(parts[0]) not in {2, 3}
        or (
            len(parts) == 2
            and (not parts[1].isalpha() or len(parts[1]) not in {2, 4})
        )
    ):
        raise ValueError("Locale must be a language tag such as tr-TR")
    language = parts[0].lower()
    return language if len(parts) == 1 else f"{language}-{parts[1].upper()}"


def _nonzero_uuid(value: UUID) -> UUID:
    if value.int == 0:
        raise ValueError("Identifier must be non-zero")
    return value


class PrivacyNoticeCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    title: str = Field(min_length=1, max_length=PRIVACY_TITLE_MAX_LENGTH)
    body: str = Field(min_length=1, max_length=PRIVACY_BODY_MAX_LENGTH)
    locale: str = Field(min_length=2, max_length=PRIVACY_LOCALE_MAX_LENGTH)

    _validate_title = field_validator("title")(_single_line_text)
    _validate_body = field_validator("body")(_plain_text)
    _validate_locale = field_validator("locale")(_locale)


class PrivacyNoticeUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    expected_revision: int = Field(ge=1)
    title: str | None = Field(default=None, min_length=1, max_length=PRIVACY_TITLE_MAX_LENGTH)
    body: str | None = Field(default=None, min_length=1, max_length=PRIVACY_BODY_MAX_LENGTH)
    locale: str | None = Field(default=None, min_length=2, max_length=PRIVACY_LOCALE_MAX_LENGTH)

    @field_validator("title")
    @classmethod
    def validate_title(cls, value: str | None) -> str | None:
        return None if value is None else _single_line_text(value)

    @field_validator("body")
    @classmethod
    def validate_body(cls, value: str | None) -> str | None:
        return None if value is None else _plain_text(value)

    @field_validator("locale")
    @classmethod
    def validate_locale(cls, value: str | None) -> str | None:
        return None if value is None else _locale(value)

    @model_validator(mode="after")
    def require_update(self) -> Self:
        changed = self.model_fields_set - {"expected_revision"}
        if not changed or any(getattr(self, field_name) is None for field_name in changed):
            raise ValueError("At least one non-null notice field must be provided")
        return self


class PrivacyNoticePublish(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_revision: int = Field(ge=1)


class PrivacyNoticeAcknowledge(BaseModel):
    model_config = ConfigDict(extra="forbid")

    notice_id: UUID
    notice_content_hash: str = Field(pattern=r"^[0-9a-f]{64}$")

    _validate_notice_id = field_validator("notice_id")(_nonzero_uuid)


class PrivacyNoticeVersionRead(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: UUID
    notice_kind: PrivacyNoticeKind
    locale: str = Field(min_length=2, max_length=PRIVACY_LOCALE_MAX_LENGTH)
    notice_version: int = Field(ge=1)
    revision: int = Field(ge=1)
    title: str = Field(min_length=1, max_length=PRIVACY_TITLE_MAX_LENGTH)
    content_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    status: PrivacyNoticeStatus
    published_at: AwareDatetime | None
    created_at: AwareDatetime
    updated_at: AwareDatetime


class PrivacyNoticeSummaryRead(PrivacyNoticeVersionRead):
    acknowledged_count: int = Field(ge=0)
    eligible_count: int = Field(ge=0)

    @model_validator(mode="after")
    def require_bounded_coverage(self) -> Self:
        if self.acknowledged_count > self.eligible_count:
            raise ValueError("Acknowledged coverage cannot exceed the eligible population")
        return self


class PrivacyNoticeDetailRead(PrivacyNoticeSummaryRead):
    body: str = Field(min_length=1, max_length=PRIVACY_BODY_MAX_LENGTH)


class EmployeePrivacyNoticeDetailRead(PrivacyNoticeVersionRead):
    body: str = Field(min_length=1, max_length=PRIVACY_BODY_MAX_LENGTH)


class EmployeePrivacyNoticeRead(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    notice: EmployeePrivacyNoticeDetailRead | None
    acknowledged_at: AwareDatetime | None

    @model_validator(mode="after")
    def require_notice_for_acknowledgement(self) -> Self:
        if self.notice is None and self.acknowledged_at is not None:
            raise ValueError("An acknowledgement must include its notice")
        return self


class ConsentTransitionRequest(BaseModel):
    """An explicit JSON object with no caller-controlled consent fields."""

    model_config = ConfigDict(extra="forbid")


class ConsentEventRead(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: UUID
    action: PrivacyConsentAction
    purpose_version: int = Field(ge=1)
    occurred_at: AwareDatetime


class ConsentPurposeStateRead(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: UUID
    code: str = Field(min_length=1, max_length=64, pattern=r"^[a-z][a-z0-9_]{0,63}$")
    version: int = Field(ge=1)
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(min_length=1, max_length=1_000)
    is_active: bool
    granted: bool
    state_version: int = Field(ge=0)
    updated_at: AwareDatetime | None
    history: list[ConsentEventRead] = Field(max_length=PRIVACY_CONSENT_HISTORY_LIMIT)


class ConsentCenterRead(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    purposes: list[ConsentPurposeStateRead] = Field(max_length=PRIVACY_CONSENT_PURPOSE_LIMIT)


class RetentionPolicyCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    data_category: RetentionDataCategory
    legal_basis_note: str = Field(min_length=1, max_length=PRIVACY_LEGAL_BASIS_MAX_LENGTH)
    retention_days: int = Field(ge=1, le=36_500)
    anchor: RetentionAnchor
    action: RetentionAction
    status: RetentionPolicyStatus = RetentionPolicyStatus.DRAFT

    _validate_basis = field_validator("legal_basis_note")(_plain_text)

    @model_validator(mode="after")
    def require_category_anchor(self) -> Self:
        if _ANCHOR_BY_CATEGORY[self.data_category] is not self.anchor:
            raise ValueError("Retention anchor does not match the data category")
        return self


class RetentionPolicyUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    expected_version: int = Field(ge=1)
    data_category: RetentionDataCategory | None = None
    legal_basis_note: str | None = Field(
        default=None,
        min_length=1,
        max_length=PRIVACY_LEGAL_BASIS_MAX_LENGTH,
    )
    retention_days: int | None = Field(default=None, ge=1, le=36_500)
    anchor: RetentionAnchor | None = None
    action: RetentionAction | None = None
    status: RetentionPolicyStatus | None = None

    @field_validator("legal_basis_note")
    @classmethod
    def validate_basis(cls, value: str | None) -> str | None:
        return None if value is None else _plain_text(value)

    @model_validator(mode="after")
    def require_update(self) -> Self:
        changed = self.model_fields_set - {"expected_version"}
        if not changed or any(getattr(self, field_name) is None for field_name in changed):
            raise ValueError("At least one non-null retention-policy field must be provided")
        if self.data_category is not None and self.anchor is not None:
            if _ANCHOR_BY_CATEGORY[self.data_category] is not self.anchor:
                raise ValueError("Retention anchor does not match the data category")
        return self


class RetentionPolicyRead(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: UUID
    data_category: RetentionDataCategory
    legal_basis_note: str = Field(min_length=1, max_length=PRIVACY_LEGAL_BASIS_MAX_LENGTH)
    retention_days: int = Field(ge=1, le=36_500)
    anchor: RetentionAnchor
    action: RetentionAction
    status: RetentionPolicyStatus
    version: int = Field(ge=1)
    created_at: AwareDatetime
    updated_at: AwareDatetime


class RetentionDryRunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    policy_ids: list[UUID] = Field(default_factory=list, max_length=RETENTION_POLICY_LIMIT)

    @field_validator("policy_ids")
    @classmethod
    def validate_policy_ids(cls, value: list[UUID]) -> list[UUID]:
        if len(value) != len(set(value)) or any(identifier.int == 0 for identifier in value):
            raise ValueError("Retention policy identifiers must be unique and non-zero")
        return value


class RetentionDryRunItemRead(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    policy_id: UUID
    data_category: RetentionDataCategory
    retention_days: int = Field(ge=1, le=36_500)
    anchor: RetentionAnchor
    action: RetentionAction
    status: RetentionPolicyStatus
    policy_version: int = Field(ge=1)
    cutoff_at: AwareDatetime
    count: int = Field(ge=0)


class RetentionDryRunRead(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    as_of: AwareDatetime
    items: list[RetentionDryRunItemRead] = Field(max_length=RETENTION_POLICY_LIMIT)


__all__ = [
    "ConsentCenterRead",
    "ConsentEventRead",
    "ConsentPurposeStateRead",
    "ConsentTransitionRequest",
    "EmployeePrivacyNoticeDetailRead",
    "EmployeePrivacyNoticeRead",
    "PRIVACY_CONSENT_HISTORY_LIMIT",
    "PRIVACY_CONSENT_PURPOSE_LIMIT",
    "PRIVACY_NOTICE_LIST_DEFAULT_LIMIT",
    "PRIVACY_NOTICE_LIST_MAX_LIMIT",
    "PrivacyNoticeAcknowledge",
    "PrivacyNoticeCreate",
    "PrivacyNoticeDetailRead",
    "PrivacyNoticePublish",
    "PrivacyNoticeSummaryRead",
    "PrivacyNoticeUpdate",
    "RETENTION_POLICY_LIMIT",
    "RetentionDryRunItemRead",
    "RetentionDryRunRead",
    "RetentionDryRunRequest",
    "RetentionPolicyCreate",
    "RetentionPolicyRead",
    "RetentionPolicyUpdate",
]
