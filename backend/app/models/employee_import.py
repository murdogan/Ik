"""Private employee-import jobs, immutable normalized rows, and safe issues."""

from __future__ import annotations

from datetime import date, datetime
from enum import StrEnum
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class EmployeeImportStatus(StrEnum):
    QUEUED = "queued"
    PROCESSING = "processing"
    RETRY = "retry"
    READY = "ready"
    INVALID = "invalid"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    EXPIRED = "expired"


class EmployeeImportScanResult(StrEnum):
    PENDING = "pending"
    CLEAN = "clean"
    INFECTED = "infected"
    ERROR = "error"


class EmployeeImport(Base):
    __tablename__ = "employee_imports"
    __table_args__ = (
        CheckConstraint(
            "status in "
            "('queued','processing','retry','ready','invalid','succeeded','failed','expired')",
            name="ck_employee_imports_status",
        ),
        CheckConstraint("file_format in ('csv','xlsx')", name="ck_employee_imports_format"),
        CheckConstraint(
            "template_version = '1'",
            name="ck_employee_imports_template_version",
        ),
        CheckConstraint(
            "scan_result in ('pending','clean','infected','error')",
            name="ck_employee_imports_scan_result",
        ),
        CheckConstraint(
            "failure_code is null or failure_code in "
            "('infected_file','invalid_file','row_limit_exceeded','scanner_unavailable',"
            "'storage_unavailable','worker_failure')",
            name="ck_employee_imports_failure_code",
        ),
        CheckConstraint(
            "size_bytes > 0 and size_bytes <= 10485760",
            name="ck_employee_imports_size",
        ),
        CheckConstraint("length(source_sha256) = 64", name="ck_employee_imports_sha256"),
        CheckConstraint(
            "row_count >= 0 and row_count <= 10000 and error_count >= 0 "
            "and warning_count >= 0 and committed_count >= 0 and committed_count <= 10000",
            name="ck_employee_imports_counts",
        ),
        CheckConstraint(
            "attempt_count >= 0 and attempt_count <= 10",
            name="ck_employee_imports_attempt_count",
        ),
        CheckConstraint(
            "validation_fingerprint is null or length(validation_fingerprint) = 64",
            name="ck_employee_imports_validation_fingerprint",
        ),
        CheckConstraint(
            "(status = 'ready' and scan_result = 'clean' and error_count = 0 "
            "and validation_fingerprint is not null) or status <> 'ready'",
            name="ck_employee_imports_ready",
        ),
        CheckConstraint(
            "(status = 'succeeded' and committed_at is not null and committed_count = row_count) "
            "or (status <> 'succeeded' and committed_at is null and committed_count = 0)",
            name="ck_employee_imports_commit",
        ),
        CheckConstraint(
            "(status = 'processing' and lease_expires_at is not null) or "
            "(status <> 'processing' and lease_expires_at is null)",
            name="ck_employee_imports_lease_state",
        ),
        CheckConstraint(
            "(status in ('queued','retry') and next_attempt_at is not null) or "
            "(status not in ('queued','retry') and next_attempt_at is null)",
            name="ck_employee_imports_schedule_state",
        ),
        CheckConstraint(
            "(status in ('retry','failed') and failure_code is not null) or "
            "(status in ('queued','processing','ready','succeeded') and failure_code is null) or "
            "status in ('invalid','expired')",
            name="ck_employee_imports_failure_state",
        ),
        CheckConstraint(
            "status not in ('ready','succeeded') or "
            "(scan_result = 'clean' and row_count > 0 and error_count = 0 and "
            "validated_at is not null and validation_fingerprint is not null)",
            name="ck_employee_imports_validated_state",
        ),
        CheckConstraint(
            "expires_at > created_at and "
            "(source_deleted_at is null or source_deleted_at >= expires_at)",
            name="ck_employee_imports_expiry",
        ),
        UniqueConstraint("tenant_id", "id", name="uq_employee_imports_tenant_id_id"),
        ForeignKeyConstraint(
            ("tenant_id", "requested_by_user_id"),
            ("users.tenant_id", "users.id"),
            name="fk_employee_imports_tenant_requester",
            ondelete="RESTRICT",
        ),
        Index(
            "ix_employee_imports_tenant_requester_created",
            "tenant_id",
            "requested_by_user_id",
            "created_at",
            "id",
        ),
        Index(
            "ix_employee_imports_tenant_claim",
            "tenant_id",
            "status",
            "next_attempt_at",
            "created_at",
            "id",
        ),
        Index(
            "ix_employee_imports_tenant_source_expiry",
            "tenant_id",
            "expires_at",
            "id",
            postgresql_where=text("source_deleted_at IS NULL"),
        ),
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("tenants.id", name="fk_employee_imports_tenant", ondelete="CASCADE"),
        nullable=False,
    )
    requested_by_user_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    template_version: Mapped[str] = mapped_column(String(16), nullable=False)
    file_format: Mapped[str] = mapped_column(String(8), nullable=False)
    content_type: Mapped[str] = mapped_column(String(128), nullable=False)
    object_key: Mapped[str] = mapped_column(String(500), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    source_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    scan_result: Mapped[str] = mapped_column(String(16), nullable=False)
    scanner_provider: Mapped[str | None] = mapped_column(String(64))
    validation_fingerprint: Mapped[str | None] = mapped_column(String(64))
    row_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    error_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    warning_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    committed_count: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    attempt_count: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    failure_code: Mapped[str | None] = mapped_column(String(64))
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    validated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    committed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    source_deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )


class EmployeeImportRow(Base):
    __tablename__ = "employee_import_rows"
    __table_args__ = (
        CheckConstraint("row_number >= 2 and row_number <= 10001", name="ck_import_rows_number"),
        CheckConstraint(
            "status in ('active','on_leave')", name="ck_import_rows_status"
        ),
        CheckConstraint(
            "employment_end_date is null",
            name="ck_import_rows_end_date",
        ),
        ForeignKeyConstraint(
            ("tenant_id", "import_id"),
            ("employee_imports.tenant_id", "employee_imports.id"),
            name="fk_employee_import_rows_import",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ("tenant_id", "legal_entity_id"),
            ("legal_entities.tenant_id", "legal_entities.id"),
            name="fk_employee_import_rows_legal_entity",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ("tenant_id", "branch_id"),
            ("branches.tenant_id", "branches.id"),
            name="fk_employee_import_rows_branch",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ("tenant_id", "department_id"),
            ("departments.tenant_id", "departments.id"),
            name="fk_employee_import_rows_department",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ("tenant_id", "position_id"),
            ("positions.tenant_id", "positions.id"),
            name="fk_employee_import_rows_position",
            ondelete="RESTRICT",
        ),
        UniqueConstraint("tenant_id", "import_id", "row_number", name="uq_import_rows_number"),
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("tenants.id", name="fk_employee_import_rows_tenant", ondelete="CASCADE"),
        nullable=False,
    )
    import_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    row_number: Mapped[int] = mapped_column(Integer, nullable=False)
    employee_number: Mapped[str] = mapped_column(String(64), nullable=False)
    employee_number_normalized: Mapped[str] = mapped_column(String(64), nullable=False)
    first_name: Mapped[str] = mapped_column(Text, nullable=False)
    last_name: Mapped[str] = mapped_column(Text, nullable=False)
    work_email: Mapped[str | None] = mapped_column(String(320))
    work_email_normalized: Mapped[str | None] = mapped_column(String(320))
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    employment_start_date: Mapped[date] = mapped_column(Date, nullable=False)
    employment_end_date: Mapped[date | None] = mapped_column(Date)
    legal_entity_code: Mapped[str] = mapped_column(String(32), nullable=False)
    branch_code: Mapped[str] = mapped_column(String(32), nullable=False)
    department_code: Mapped[str] = mapped_column(String(32), nullable=False)
    position_code: Mapped[str] = mapped_column(String(32), nullable=False)
    legal_entity_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    branch_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    department_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    position_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)


class EmployeeImportIssue(Base):
    __tablename__ = "employee_import_issues"
    __table_args__ = (
        CheckConstraint("row_number >= 1 and row_number <= 10001", name="ck_import_issues_row"),
        CheckConstraint("severity in ('error','warning')", name="ck_import_issues_severity"),
        ForeignKeyConstraint(
            ("tenant_id", "import_id"),
            ("employee_imports.tenant_id", "employee_imports.id"),
            name="fk_employee_import_issues_import",
            ondelete="CASCADE",
        ),
        UniqueConstraint(
            "tenant_id",
            "import_id",
            "row_number",
            "code",
            "field",
            name="uq_employee_import_issues_deterministic",
        ),
        Index(
            "ix_employee_import_issues_import_cursor",
            "tenant_id",
            "import_id",
            "row_number",
            "id",
        ),
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("tenants.id", name="fk_employee_import_issues_tenant", ondelete="CASCADE"),
        nullable=False,
    )
    import_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    row_number: Mapped[int] = mapped_column(Integer, nullable=False)
    severity: Mapped[str] = mapped_column(String(16), nullable=False)
    code: Mapped[str] = mapped_column(String(64), nullable=False)
    field: Mapped[str | None] = mapped_column(String(64))
    message: Mapped[str] = mapped_column(String(240), nullable=False)


__all__ = [
    "EmployeeImport",
    "EmployeeImportIssue",
    "EmployeeImportRow",
    "EmployeeImportScanResult",
    "EmployeeImportStatus",
]
