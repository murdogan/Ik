"""Tenant-owned employee document policy, object metadata, and upload intents."""

from __future__ import annotations

from datetime import date, datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

from sqlalchemy import (
    JSON,
    BigInteger,
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
    false,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin

_DOCUMENT_JSON = JSON().with_variant(JSONB(), "postgresql")


class DocumentSensitivity(StrEnum):
    STANDARD = "standard"
    SENSITIVE = "sensitive"
    HIGHLY_SENSITIVE = "highly_sensitive"


class DocumentExpiryMode(StrEnum):
    NONE = "none"
    OPTIONAL = "optional"
    REQUIRED = "required"


class DocumentProcessingState(StrEnum):
    PENDING_UPLOAD = "pending_upload"
    PENDING_SCAN = "pending_scan"
    AVAILABLE = "available"
    INFECTED = "infected"
    SCAN_ERROR = "scan_error"
    REJECTED = "rejected"


class DocumentUploadIntentStatus(StrEnum):
    ACTIVE = "active"
    FINALIZED = "finalized"
    REJECTED = "rejected"
    EXPIRED = "expired"


class DocumentScanResult(StrEnum):
    CLEAN = "clean"
    INFECTED = "infected"
    ERROR = "error"


class DocumentType(Base, TimestampMixin):
    """One tenant policy for a bounded class of employee document."""

    __tablename__ = "document_types"
    __table_args__ = (
        CheckConstraint("length(trim(code)) > 0", name="ck_document_types_code_not_blank"),
        CheckConstraint("length(trim(name)) > 0", name="ck_document_types_name_not_blank"),
        CheckConstraint(
            "sensitivity in ('standard','sensitive','highly_sensitive')",
            name="ck_document_types_sensitivity",
        ),
        CheckConstraint(
            "expiry_mode in ('none','optional','required')",
            name="ck_document_types_expiry_mode",
        ),
        CheckConstraint(
            "max_size_bytes between 1 and 52428800",
            name="ck_document_types_max_size",
        ),
        CheckConstraint("version > 0", name="ck_document_types_version_positive"),
        UniqueConstraint("tenant_id", "id", name="uq_document_types_tenant_id_id"),
        UniqueConstraint("tenant_id", "code", name="uq_document_types_tenant_code"),
        Index("ix_document_types_tenant_archived", "tenant_id", "archived_at", "code"),
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey(
            "tenants.id",
            name="fk_document_types_tenant_id_tenants",
            ondelete="CASCADE",
        ),
        nullable=False,
    )
    code: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    required: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default=false(),
    )
    employee_visible: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=false()
    )
    sensitivity: Mapped[str] = mapped_column(String(32), nullable=False)
    expiry_mode: Mapped[str] = mapped_column(String(16), nullable=False)
    allowed_mime_types: Mapped[list[str]] = mapped_column(_DOCUMENT_JSON, nullable=False)
    allowed_extensions: Mapped[list[str]] = mapped_column(_DOCUMENT_JSON, nullable=False)
    max_size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default=text("1")
    )
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __mapper_args__ = {"version_id_col": version}


class EmployeeDocument(Base, TimestampMixin):
    """Safe metadata for one immutable object owned by an employee record."""

    __tablename__ = "employee_documents"
    __table_args__ = (
        CheckConstraint(
            "processing_state in "
            "('pending_upload','pending_scan','available','infected','scan_error','rejected')",
            name="ck_employee_documents_processing_state",
        ),
        CheckConstraint(
            "scan_result is null or scan_result in ('clean','infected','error')",
            name="ck_employee_documents_scan_result",
        ),
        CheckConstraint(
            "normalized_extension in ('pdf','jpg','jpeg','png')",
            name="ck_employee_documents_extension",
        ),
        CheckConstraint("size_bytes between 1 and 52428800", name="ck_employee_documents_size"),
        CheckConstraint("version > 0", name="ck_employee_documents_version_positive"),
        CheckConstraint(
            "expires_on is null or issued_on is null or expires_on >= issued_on",
            name="ck_employee_documents_date_order",
        ),
        CheckConstraint(
            "(processing_state = 'pending_upload' and finalized_at is null and sha256 is null) "
            "or (processing_state = 'rejected') "
            "or (processing_state in ('pending_scan','available','infected','scan_error') "
            "and finalized_at is not null and sha256 is not null)",
            name="ck_employee_documents_finalization_state",
        ),
        CheckConstraint(
            "(processing_state in ('available','infected','scan_error') and scanned_at is not null "
            "and scan_result is not null) or "
            "(processing_state not in ('available','infected','scan_error') "
            "and scanned_at is null and scan_result is null)",
            name="ck_employee_documents_scan_state",
        ),
        UniqueConstraint("tenant_id", "id", name="uq_employee_documents_tenant_id_id"),
        UniqueConstraint(
            "tenant_id",
            "employee_id",
            "id",
            name="uq_employee_documents_tenant_employee_id",
        ),
        UniqueConstraint("object_key", name="uq_employee_documents_object_key"),
        ForeignKeyConstraint(
            ("tenant_id", "employee_id"),
            ("employees.tenant_id", "employees.id"),
            name="fk_employee_documents_tenant_employee_employees",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ("tenant_id", "document_type_id"),
            ("document_types.tenant_id", "document_types.id"),
            name="fk_employee_documents_tenant_type_document_types",
            ondelete="RESTRICT",
        ),
        Index(
            "ix_employee_documents_tenant_employee_state",
            "tenant_id",
            "employee_id",
            "processing_state",
            "archived_at",
        ),
        Index(
            "ix_employee_documents_tenant_employee_type_expiry",
            "tenant_id",
            "employee_id",
            "document_type_id",
            "expires_on",
        ),
        Index(
            "ix_employee_documents_own_available",
            "tenant_id",
            "employee_id",
            "employee_visible",
            "processing_state",
        ),
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey(
            "tenants.id",
            name="fk_employee_documents_tenant_id_tenants",
            ondelete="CASCADE",
        ),
        nullable=False,
    )
    employee_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    document_type_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    object_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False, unique=True)
    object_key: Mapped[str] = mapped_column(Text, nullable=False)
    display_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    normalized_extension: Mapped[str] = mapped_column(String(8), nullable=False)
    declared_content_type: Mapped[str] = mapped_column(String(100), nullable=False)
    stored_content_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    issued_on: Mapped[date | None] = mapped_column(nullable=True)
    expires_on: Mapped[date | None] = mapped_column(nullable=True)
    employee_visible: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=false()
    )
    processing_state: Mapped[str] = mapped_column(String(32), nullable=False)
    finalized_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    scanned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    scan_result: Mapped[str | None] = mapped_column(String(16), nullable=True)
    scanner_provider: Mapped[str | None] = mapped_column(String(32), nullable=True)
    scanner_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    scan_error_code: Mapped[str | None] = mapped_column(String(32), nullable=True)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default=text("1")
    )

    __mapper_args__ = {"version_id_col": version}


class EmployeeDocumentUploadIntent(Base, TimestampMixin):
    """Short-lived, actor-bound authorization for one staging object upload."""

    __tablename__ = "employee_document_upload_intents"
    __table_args__ = (
        CheckConstraint(
            "status in ('active','finalized','rejected','expired')",
            name="ck_employee_document_upload_intents_status",
        ),
        CheckConstraint(
            "expected_size_bytes between 1 and 52428800",
            name="ck_employee_document_upload_intents_size",
        ),
        CheckConstraint(
            "expected_extension in ('pdf','jpg','jpeg','png')",
            name="ck_employee_document_upload_intents_extension",
        ),
        CheckConstraint(
            "(status = 'finalized' and finalized_at is not null) or "
            "(status <> 'finalized' and finalized_at is null)",
            name="ck_employee_document_upload_intents_finalized_state",
        ),
        UniqueConstraint(
            "tenant_id", "id", name="uq_employee_document_upload_intents_tenant_id_id"
        ),
        UniqueConstraint(
            "upload_object_key", name="uq_employee_document_upload_intents_object_key"
        ),
        ForeignKeyConstraint(
            ("tenant_id", "document_id"),
            ("employee_documents.tenant_id", "employee_documents.id"),
            name="fk_employee_document_upload_intents_tenant_document",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ("tenant_id", "initiated_by_user_id"),
            ("users.tenant_id", "users.id"),
            name="fk_employee_document_upload_intents_tenant_user",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ("tenant_id", "initiated_by_membership_id"),
            ("tenant_memberships.tenant_id", "tenant_memberships.id"),
            name="fk_employee_document_upload_intents_tenant_membership",
            ondelete="RESTRICT",
        ),
        Index(
            "ix_employee_document_upload_intents_tenant_document_status",
            "tenant_id",
            "document_id",
            "status",
        ),
        Index(
            "ix_employee_document_upload_intents_expiry",
            "tenant_id",
            "status",
            "expires_at",
        ),
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey(
            "tenants.id",
            name="fk_employee_document_upload_intents_tenant_id_tenants",
            ondelete="CASCADE",
        ),
        nullable=False,
    )
    document_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    initiated_by_user_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    initiated_by_membership_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    upload_object_key: Mapped[str] = mapped_column(Text, nullable=False)
    expected_content_type: Mapped[str] = mapped_column(String(100), nullable=False)
    expected_size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    expected_extension: Mapped[str] = mapped_column(String(8), nullable=False)
    expected_metadata: Mapped[dict[str, Any]] = mapped_column(_DOCUMENT_JSON, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finalized_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


__all__ = [
    "DocumentExpiryMode",
    "DocumentProcessingState",
    "DocumentScanResult",
    "DocumentSensitivity",
    "DocumentType",
    "DocumentUploadIntentStatus",
    "EmployeeDocument",
    "EmployeeDocumentUploadIntent",
]
