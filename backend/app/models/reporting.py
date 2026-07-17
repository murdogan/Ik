"""Tenant-scoped report export jobs and bounded download intents."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

from sqlalchemy import (
    JSON,
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

_REPORT_JSON = JSON().with_variant(JSONB(), "postgresql")


class ReportType(StrEnum):
    EMPLOYEES = "employees"
    LEAVES = "leaves"
    MISSING_DOCUMENTS = "missing_documents"


class ReportScope(StrEnum):
    TENANT = "tenant"
    TEAM = "team"


class ExportFormat(StrEnum):
    CSV = "csv"
    XLSX = "xlsx"


class ExportJobStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    RETRY = "retry"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"
    EXPIRED = "expired"


class ReportExportJob(Base):
    __tablename__ = "report_export_jobs"
    __table_args__ = (
        CheckConstraint(
            "report_type in ('employees','leaves','missing_documents')",
            name="ck_report_export_jobs_report_type",
        ),
        CheckConstraint("format in ('csv','xlsx')", name="ck_report_export_jobs_format"),
        CheckConstraint(
            "status in ('queued','running','retry','succeeded','failed','cancelled','expired')",
            name="ck_report_export_jobs_status",
        ),
        CheckConstraint(
            "failure_code is null or failure_code in "
            "('authorization_revoked','file_too_large','row_limit_exceeded',"
            "'storage_unavailable','worker_failure')",
            name="ck_report_export_jobs_failure_code",
        ),
        CheckConstraint(
            "request_scope in ('tenant','team') and "
            "((request_scope = 'team' and request_scope_user_id is not null) or "
            "(request_scope = 'tenant' and request_scope_user_id is null))",
            name="ck_report_export_jobs_request_scope",
        ),
        CheckConstraint(
            "request_scope_user_id is null or request_scope_user_id = requested_by_user_id",
            name="ck_report_export_jobs_request_scope_owner",
        ),
        CheckConstraint(
            "generated_scope is null or generated_scope in ('tenant','team')",
            name="ck_report_export_jobs_generated_scope",
        ),
        CheckConstraint(
            "generated_scope is null or "
            "((generated_scope = 'team' and generated_scope_user_id is not null) or "
            "(generated_scope = 'tenant' and generated_scope_user_id is null))",
            name="ck_report_export_jobs_generated_scope_user",
        ),
        CheckConstraint(
            "generated_scope_user_id is null or generated_scope_user_id = requested_by_user_id",
            name="ck_report_export_jobs_generated_scope_owner",
        ),
        CheckConstraint(
            "attempt_count >= 0 and attempt_count <= 10",
            name="ck_report_export_jobs_attempt_count",
        ),
        CheckConstraint(
            "row_count is null or (row_count >= 0 and row_count <= 10000)",
            name="ck_report_export_jobs_row_count",
        ),
        CheckConstraint(
            "size_bytes is null or size_bytes > 0",
            name="ck_report_export_jobs_size_bytes",
        ),
        CheckConstraint(
            "artifact_sha256 is null or length(artifact_sha256) = 64",
            name="ck_report_export_jobs_sha256",
        ),
        CheckConstraint(
            "(status in ('succeeded','expired') and artifact_object_key is not null "
            "and artifact_sha256 is not null and artifact_content_type is not null "
            "and size_bytes is not null "
            "and row_count is not null and available_at is not null and expires_at is not null "
            "and expires_at > available_at and generated_scope is not null "
            "and generated_fields is not null and field_classifications is not null "
            "and failure_code is null) or "
            "(status not in ('succeeded','expired') and artifact_object_key is null "
            "and artifact_sha256 is null and artifact_content_type is null "
            "and size_bytes is null and row_count is null and available_at is null "
            "and expires_at is null and generated_scope is null "
            "and generated_scope_user_id is null and generated_fields is null "
            "and field_classifications is null)",
            name="ck_report_export_jobs_artifact_state",
        ),
        CheckConstraint(
            "generated_scope is null or request_scope = 'tenant' or generated_scope = 'team'",
            name="ck_report_export_jobs_scope_reduction",
        ),
        CheckConstraint(
            "(status in ('retry','failed') and failure_code is not null) or "
            "(status not in ('retry','failed') and failure_code is null)",
            name="ck_report_export_jobs_failure_state",
        ),
        CheckConstraint(
            "(status = 'running' and lease_expires_at is not null) or "
            "(status <> 'running' and lease_expires_at is null)",
            name="ck_report_export_jobs_lease_state",
        ),
        CheckConstraint(
            "(status in ('queued','retry') and next_attempt_at is not null) or "
            "(status not in ('queued','retry') and next_attempt_at is null)",
            name="ck_report_export_jobs_schedule_state",
        ),
        CheckConstraint(
            "(status = 'cancelled' and cancel_requested_at is not null) or "
            "(status <> 'cancelled' and cancel_requested_at is null)",
            name="ck_report_export_jobs_cancellation_state",
        ),
        UniqueConstraint("tenant_id", "id", name="uq_report_export_jobs_tenant_id_id"),
        ForeignKeyConstraint(
            ("tenant_id", "requested_by_user_id"),
            ("users.tenant_id", "users.id"),
            name="fk_report_export_jobs_tenant_requester",
            ondelete="RESTRICT",
        ),
        Index(
            "ix_report_export_jobs_tenant_requester_created",
            "tenant_id",
            "requested_by_user_id",
            "status",
            "created_at",
            "id",
        ),
        Index(
            "ix_report_export_jobs_tenant_claim",
            "tenant_id",
            "status",
            "next_attempt_at",
            "created_at",
            "id",
        ),
        Index(
            "ix_report_export_jobs_tenant_expiry",
            "tenant_id",
            "status",
            "expires_at",
            "id",
        ),
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("tenants.id", name="fk_report_export_jobs_tenant", ondelete="CASCADE"),
        nullable=False,
    )
    requested_by_user_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    report_type: Mapped[str] = mapped_column(String(32), nullable=False)
    format: Mapped[str] = mapped_column(String(8), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    request_scope: Mapped[str] = mapped_column(String(16), nullable=False)
    request_scope_user_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True))
    fields_snapshot: Mapped[list[str]] = mapped_column(_REPORT_JSON, nullable=False)
    filters_snapshot: Mapped[dict[str, Any]] = mapped_column(_REPORT_JSON, nullable=False)
    generated_scope: Mapped[str | None] = mapped_column(String(16))
    generated_scope_user_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True))
    generated_fields: Mapped[list[str] | None] = mapped_column(_REPORT_JSON)
    field_classifications: Mapped[list[str] | None] = mapped_column(_REPORT_JSON)
    artifact_object_key: Mapped[str | None] = mapped_column(String(500))
    artifact_sha256: Mapped[str | None] = mapped_column(String(64))
    artifact_content_type: Mapped[str | None] = mapped_column(String(128))
    size_bytes: Mapped[int | None] = mapped_column(BigInteger)
    row_count: Mapped[int | None] = mapped_column(Integer)
    attempt_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    failure_code: Mapped[str | None] = mapped_column(String(64))
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancel_requested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    available_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )


class ReportExportDownloadIntent(Base):
    __tablename__ = "report_export_download_intents"
    __table_args__ = (
        CheckConstraint(
            "expires_at > created_at",
            name="ck_report_export_download_intents_expiry",
        ),
        ForeignKeyConstraint(
            ("tenant_id", "export_job_id"),
            ("report_export_jobs.tenant_id", "report_export_jobs.id"),
            name="fk_report_export_download_intents_job",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ("tenant_id", "issued_to_user_id"),
            ("users.tenant_id", "users.id"),
            name="fk_report_export_download_intents_user",
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "tenant_id", "id", name="uq_report_export_download_intents_tenant_id_id"
        ),
        Index(
            "ix_report_export_download_intents_job_created",
            "tenant_id",
            "export_job_id",
            "created_at",
            "id",
        ),
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey(
            "tenants.id",
            name="fk_report_export_download_intents_tenant",
            ondelete="CASCADE",
        ),
        nullable=False,
    )
    export_job_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    issued_to_user_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )


__all__ = [
    "ExportFormat",
    "ExportJobStatus",
    "ReportExportDownloadIntent",
    "ReportExportJob",
    "ReportScope",
    "ReportType",
]
