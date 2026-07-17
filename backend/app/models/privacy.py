"""Tenant privacy notices, consent evidence, and retention-policy metadata."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
    true,
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class PrivacyNoticeKind(StrEnum):
    EMPLOYEE = "employee"


class PrivacyNoticeStatus(StrEnum):
    DRAFT = "draft"
    PUBLISHED = "published"
    SUPERSEDED = "superseded"


class PrivacyConsentAction(StrEnum):
    GRANT = "grant"
    WITHDRAW = "withdraw"


class RetentionDataCategory(StrEnum):
    EMPLOYEE_RECORDS = "employee_records"
    EMPLOYEE_DOCUMENTS = "employee_documents"
    LEAVE_REQUESTS = "leave_requests"
    AUDIT_EVENTS = "audit_events"


class RetentionAnchor(StrEnum):
    EMPLOYMENT_END_DATE = "employment_end_date"
    ARCHIVED_AT = "archived_at"
    CREATED_AT = "created_at"
    OCCURRED_AT = "occurred_at"


class RetentionAction(StrEnum):
    REVIEW = "review"
    DELETE = "delete"
    ANONYMIZE = "anonymize"


class RetentionPolicyStatus(StrEnum):
    DRAFT = "draft"
    ACTIVE = "active"
    INACTIVE = "inactive"


def _postgresql_regex_check(expression: str, *, name: str) -> CheckConstraint:
    """Keep PostgreSQL regex invariants without breaking SQLite metadata creation."""

    return CheckConstraint(expression, name=name).ddl_if(dialect="postgresql")


class PrivacyNotice(Base, TimestampMixin):
    """One editable draft or immutable published employee-notice version."""

    __tablename__ = "privacy_notices"
    __table_args__ = (
        CheckConstraint("kind = 'employee'", name="ck_privacy_notices_kind"),
        CheckConstraint(
            "status in ('draft','published','superseded')",
            name="ck_privacy_notices_status",
        ),
        CheckConstraint(
            "length(trim(locale)) > 0",
            name="ck_privacy_notices_locale_not_blank",
        ),
        CheckConstraint(
            "notice_version > 0",
            name="ck_privacy_notices_notice_version_positive",
        ),
        CheckConstraint("revision > 0", name="ck_privacy_notices_revision_positive"),
        CheckConstraint(
            "length(trim(title)) > 0",
            name="ck_privacy_notices_title_not_blank",
        ),
        CheckConstraint(
            "length(trim(body)) > 0 and length(body) <= 20000",
            name="ck_privacy_notices_body_length",
        ),
        _postgresql_regex_check(
            "content_hash ~ '^[0-9a-f]{64}$'",
            name="ck_privacy_notices_content_hash",
        ),
        CheckConstraint(
            "(status = 'draft' and published_by_user_id is null and published_at is null) or "
            "(status in ('published','superseded') and published_by_user_id is not null "
            "and published_at is not null)",
            name="ck_privacy_notices_lifecycle",
        ),
        UniqueConstraint(
            "tenant_id",
            "id",
            name="uq_privacy_notices_tenant_id_id",
        ),
        UniqueConstraint(
            "tenant_id",
            "kind",
            "notice_version",
            name="uq_privacy_notices_tenant_kind_version",
        ),
        UniqueConstraint(
            "tenant_id",
            "id",
            "notice_version",
            "content_hash",
            name="uq_privacy_notices_tenant_id_version_hash",
        ),
        ForeignKeyConstraint(
            ("tenant_id", "created_by_user_id"),
            ("users.tenant_id", "users.id"),
            name="fk_privacy_notices_tenant_creator",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ("tenant_id", "published_by_user_id"),
            ("users.tenant_id", "users.id"),
            name="fk_privacy_notices_tenant_publisher",
            ondelete="RESTRICT",
        ),
        Index(
            "uq_privacy_notices_tenant_kind_published",
            "tenant_id",
            "kind",
            unique=True,
            postgresql_where=text("status = 'published'"),
            sqlite_where=text("status = 'published'"),
        ),
        Index(
            "ix_privacy_notices_tenant_status_created",
            "tenant_id",
            "status",
            "created_at",
            "id",
        ),
        {"implicit_returning": False},
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey(
            "tenants.id",
            name="fk_privacy_notices_tenant",
            ondelete="CASCADE",
        ),
        nullable=False,
    )
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    locale: Mapped[str] = mapped_column(String(16), nullable=False)
    notice_version: Mapped[int] = mapped_column(Integer, nullable=False)
    revision: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
        server_default=text("1"),
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default=PrivacyNoticeStatus.DRAFT.value,
        server_default=PrivacyNoticeStatus.DRAFT.value,
    )
    created_by_user_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    published_by_user_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), nullable=True
    )
    published_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    __mapper_args__ = {"version_id_col": revision}


class PrivacyNoticeAcknowledgement(Base):
    """Append-only evidence binding an actor to an exact published notice."""

    __tablename__ = "privacy_notice_acknowledgements"
    __table_args__ = (
        CheckConstraint(
            "notice_version > 0",
            name="ck_privacy_notice_acknowledgements_version_positive",
        ),
        _postgresql_regex_check(
            "notice_content_hash ~ '^[0-9a-f]{64}$'",
            name="ck_privacy_notice_acknowledgements_notice_hash",
        ),
        _postgresql_regex_check(
            "evidence_request_sha256 ~ '^[0-9a-f]{64}$'",
            name="ck_privacy_notice_acknowledgements_request_hash",
        ),
        _postgresql_regex_check(
            "evidence_session_sha256 is null or "
            "evidence_session_sha256 ~ '^[0-9a-f]{64}$'",
            name="ck_privacy_notice_acknowledgements_session_hash",
        ),
        UniqueConstraint(
            "tenant_id",
            "id",
            name="uq_privacy_notice_acknowledgements_tenant_id_id",
        ),
        UniqueConstraint(
            "tenant_id",
            "notice_id",
            "user_id",
            name="uq_privacy_notice_acknowledgements_tenant_notice_user",
        ),
        ForeignKeyConstraint(
            ("tenant_id", "notice_id", "notice_version", "notice_content_hash"),
            (
                "privacy_notices.tenant_id",
                "privacy_notices.id",
                "privacy_notices.notice_version",
                "privacy_notices.content_hash",
            ),
            name="fk_privacy_notice_acknowledgements_exact_notice",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ("tenant_id", "user_id"),
            ("users.tenant_id", "users.id"),
            name="fk_privacy_notice_acknowledgements_tenant_user",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ("tenant_id", "membership_id"),
            ("tenant_memberships.tenant_id", "tenant_memberships.id"),
            name="fk_privacy_notice_acknowledgements_tenant_membership",
            ondelete="RESTRICT",
        ),
        Index(
            "ix_privacy_notice_acknowledgements_own_history",
            "tenant_id",
            "user_id",
            "acknowledged_at",
            "id",
        ),
        Index(
            "ix_privacy_notice_acknowledgements_notice_coverage",
            "tenant_id",
            "notice_id",
            "acknowledged_at",
            "id",
        ),
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey(
            "tenants.id",
            name="fk_privacy_notice_acknowledgements_tenant",
            ondelete="CASCADE",
        ),
        nullable=False,
    )
    notice_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    notice_version: Mapped[int] = mapped_column(Integer, nullable=False)
    notice_content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    user_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    membership_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    acknowledged_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    evidence_request_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    evidence_session_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)


class PrivacyConsentPurpose(Base):
    """Immutable tenant-local definition of one optional processing purpose version."""

    __tablename__ = "privacy_consent_purposes"
    __table_args__ = (
        _postgresql_regex_check(
            "code ~ '^[a-z][a-z0-9_]{0,63}$'",
            name="ck_privacy_consent_purposes_code",
        ),
        CheckConstraint(
            "version > 0",
            name="ck_privacy_consent_purposes_version_positive",
        ),
        CheckConstraint(
            "length(trim(title)) > 0",
            name="ck_privacy_consent_purposes_title_not_blank",
        ),
        CheckConstraint(
            "length(trim(description)) > 0",
            name="ck_privacy_consent_purposes_description_not_blank",
        ),
        UniqueConstraint(
            "tenant_id",
            "id",
            name="uq_privacy_consent_purposes_tenant_id_id",
        ),
        UniqueConstraint(
            "tenant_id",
            "id",
            "version",
            name="uq_privacy_consent_purposes_tenant_id_version",
        ),
        UniqueConstraint(
            "tenant_id",
            "code",
            "version",
            name="uq_privacy_consent_purposes_tenant_code_version",
        ),
        Index(
            "uq_privacy_consent_purposes_tenant_code_active",
            "tenant_id",
            "code",
            unique=True,
            postgresql_where=text("is_active"),
            sqlite_where=text("is_active = 1"),
        ),
        Index(
            "ix_privacy_consent_purposes_tenant_active",
            "tenant_id",
            "is_active",
            "code",
            "version",
        ),
        {"implicit_returning": False},
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey(
            "tenants.id",
            name="fk_privacy_consent_purposes_tenant",
            ondelete="CASCADE",
        ),
        nullable=False,
    )
    code: Mapped[str] = mapped_column(String(64), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(String(1000), nullable=False)
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default=true(),
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class PrivacyConsentState(Base, TimestampMixin):
    """Lockable current state backed by immutable consent-transition events."""

    __tablename__ = "privacy_consent_states"
    __table_args__ = (
        CheckConstraint(
            "version > 0",
            name="ck_privacy_consent_states_version_positive",
        ),
        UniqueConstraint(
            "tenant_id",
            "id",
            name="uq_privacy_consent_states_tenant_id_id",
        ),
        UniqueConstraint(
            "tenant_id",
            "purpose_id",
            "user_id",
            name="uq_privacy_consent_states_tenant_purpose_user",
        ),
        ForeignKeyConstraint(
            ("tenant_id", "purpose_id"),
            ("privacy_consent_purposes.tenant_id", "privacy_consent_purposes.id"),
            name="fk_privacy_consent_states_tenant_purpose",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ("tenant_id", "user_id"),
            ("users.tenant_id", "users.id"),
            name="fk_privacy_consent_states_tenant_user",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ("tenant_id", "membership_id"),
            ("tenant_memberships.tenant_id", "tenant_memberships.id"),
            name="fk_privacy_consent_states_tenant_membership",
            ondelete="RESTRICT",
        ),
        Index(
            "ix_privacy_consent_states_own",
            "tenant_id",
            "user_id",
            "purpose_id",
        ),
        {"implicit_returning": False},
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey(
            "tenants.id",
            name="fk_privacy_consent_states_tenant",
            ondelete="CASCADE",
        ),
        nullable=False,
    )
    purpose_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    user_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    membership_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    granted: Mapped[bool] = mapped_column(Boolean, nullable=False)
    version: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
        server_default=text("1"),
    )

    __mapper_args__ = {"version_id_col": version}


class PrivacyConsentEvent(Base):
    """Append-only grant or withdrawal transition for an optional purpose."""

    __tablename__ = "privacy_consent_events"
    __table_args__ = (
        CheckConstraint(
            "purpose_version > 0",
            name="ck_privacy_consent_events_purpose_version_positive",
        ),
        CheckConstraint(
            "action in ('grant','withdraw')",
            name="ck_privacy_consent_events_action",
        ),
        UniqueConstraint(
            "tenant_id",
            "id",
            name="uq_privacy_consent_events_tenant_id_id",
        ),
        ForeignKeyConstraint(
            ("tenant_id", "purpose_id", "purpose_version"),
            (
                "privacy_consent_purposes.tenant_id",
                "privacy_consent_purposes.id",
                "privacy_consent_purposes.version",
            ),
            name="fk_privacy_consent_events_exact_purpose",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ("tenant_id", "user_id"),
            ("users.tenant_id", "users.id"),
            name="fk_privacy_consent_events_tenant_user",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ("tenant_id", "membership_id"),
            ("tenant_memberships.tenant_id", "tenant_memberships.id"),
            name="fk_privacy_consent_events_tenant_membership",
            ondelete="RESTRICT",
        ),
        Index(
            "ix_privacy_consent_events_own_history",
            "tenant_id",
            "user_id",
            "occurred_at",
            "id",
        ),
        Index(
            "ix_privacy_consent_events_purpose_history",
            "tenant_id",
            "purpose_id",
            "occurred_at",
            "id",
        ),
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey(
            "tenants.id",
            name="fk_privacy_consent_events_tenant",
            ondelete="CASCADE",
        ),
        nullable=False,
    )
    purpose_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    purpose_version: Mapped[int] = mapped_column(Integer, nullable=False)
    user_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    membership_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    action: Mapped[str] = mapped_column(String(16), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class RetentionPolicy(Base, TimestampMixin):
    """Non-destructive tenant retention-policy metadata for dry-run inventory."""

    __tablename__ = "retention_policies"
    __table_args__ = (
        CheckConstraint(
            "data_category in "
            "('employee_records','employee_documents','leave_requests','audit_events')",
            name="ck_retention_policies_data_category",
        ),
        CheckConstraint(
            "length(trim(legal_basis_note)) > 0",
            name="ck_retention_policies_legal_basis_not_blank",
        ),
        CheckConstraint(
            "retention_days between 1 and 36500",
            name="ck_retention_policies_retention_days",
        ),
        CheckConstraint(
            "anchor in ('employment_end_date','archived_at','created_at','occurred_at')",
            name="ck_retention_policies_anchor",
        ),
        CheckConstraint(
            "(data_category = 'employee_records' and anchor = 'employment_end_date') or "
            "(data_category = 'employee_documents' and anchor = 'archived_at') or "
            "(data_category = 'leave_requests' and anchor = 'created_at') or "
            "(data_category = 'audit_events' and anchor = 'occurred_at')",
            name="ck_retention_policies_category_anchor",
        ),
        CheckConstraint(
            "action in ('review','delete','anonymize')",
            name="ck_retention_policies_action",
        ),
        CheckConstraint(
            "status in ('draft','active','inactive')",
            name="ck_retention_policies_status",
        ),
        CheckConstraint(
            "version > 0",
            name="ck_retention_policies_version_positive",
        ),
        UniqueConstraint(
            "tenant_id",
            "id",
            name="uq_retention_policies_tenant_id_id",
        ),
        UniqueConstraint(
            "tenant_id",
            "data_category",
            name="uq_retention_policies_tenant_category",
        ),
        ForeignKeyConstraint(
            ("tenant_id", "created_by_user_id"),
            ("users.tenant_id", "users.id"),
            name="fk_retention_policies_tenant_creator",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ("tenant_id", "updated_by_user_id"),
            ("users.tenant_id", "users.id"),
            name="fk_retention_policies_tenant_updater",
            ondelete="RESTRICT",
        ),
        Index(
            "ix_retention_policies_tenant_status_category",
            "tenant_id",
            "status",
            "data_category",
        ),
        {"implicit_returning": False},
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey(
            "tenants.id",
            name="fk_retention_policies_tenant",
            ondelete="CASCADE",
        ),
        nullable=False,
    )
    data_category: Mapped[str] = mapped_column(String(32), nullable=False)
    legal_basis_note: Mapped[str] = mapped_column(String(1000), nullable=False)
    retention_days: Mapped[int] = mapped_column(Integer, nullable=False)
    anchor: Mapped[str] = mapped_column(String(32), nullable=False)
    action: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default=RetentionPolicyStatus.DRAFT.value,
        server_default=RetentionPolicyStatus.DRAFT.value,
    )
    version: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
        server_default=text("1"),
    )
    created_by_user_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    updated_by_user_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)

    __mapper_args__ = {"version_id_col": version}


__all__ = [
    "PrivacyConsentAction",
    "PrivacyConsentEvent",
    "PrivacyConsentPurpose",
    "PrivacyConsentState",
    "PrivacyNotice",
    "PrivacyNoticeAcknowledgement",
    "PrivacyNoticeKind",
    "PrivacyNoticeStatus",
    "RetentionAction",
    "RetentionAnchor",
    "RetentionDataCategory",
    "RetentionPolicy",
    "RetentionPolicyStatus",
]
