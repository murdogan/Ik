"""Tenant-owned legal-entity and branch/location persistence."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Computed,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    String,
    Text,
    UniqueConstraint,
    false,
    text,
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class LegalEntityStatus(StrEnum):
    ACTIVE = "active"
    INACTIVE = "inactive"


class BranchStatus(StrEnum):
    ACTIVE = "active"
    ARCHIVED = "archived"


class LegalEntity(Base, TimestampMixin):
    """A future-compatible tenant legal entity; simple tenants receive one default row."""

    __tablename__ = "legal_entities"
    __table_args__ = (
        CheckConstraint(
            "status in ('active','inactive')",
            name="ck_legal_entities_status",
        ),
        CheckConstraint(
            "length(code_normalized) > 0",
            name="ck_legal_entities_code_normalized_not_empty",
        ),
        CheckConstraint(
            "is_default = false or status = 'active'",
            name="ck_legal_entities_default_active",
        ),
        UniqueConstraint(
            "tenant_id",
            "id",
            name="uq_legal_entities_tenant_id_id",
        ),
        UniqueConstraint(
            "tenant_id",
            "code_normalized",
            name="uq_legal_entities_tenant_code_normalized",
        ),
        Index(
            "uq_legal_entities_tenant_default",
            "tenant_id",
            unique=True,
            postgresql_where=text("is_default = true"),
            sqlite_where=text("is_default = 1"),
        ),
        Index(
            "ix_legal_entities_tenant_status_code",
            "tenant_id",
            "status",
            "code_normalized",
        ),
        {"implicit_returning": False},
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey(
            "tenants.id",
            name="fk_legal_entities_tenant_id_tenants",
            ondelete="CASCADE",
        ),
        nullable=False,
    )
    code: Mapped[str] = mapped_column(String(32), nullable=False)
    code_normalized: Mapped[str] = mapped_column(
        String(32),
        Computed("lower(ltrim(rtrim(code)))", persisted=True),
        nullable=False,
    )
    # Defaults are backfilled from the historical unbounded tenant name column. HTTP writes are
    # still bounded by the organization schemas without risking migration-time truncation.
    name: Mapped[str] = mapped_column(Text, nullable=False)
    registered_name: Mapped[str] = mapped_column(Text, nullable=False)
    country_code: Mapped[str | None] = mapped_column(String(2), nullable=True)
    tax_number: Mapped[str | None] = mapped_column(String(64), nullable=True)
    timezone: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default=LegalEntityStatus.ACTIVE.value,
        server_default=LegalEntityStatus.ACTIVE.value,
    )
    is_default: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default=false(),
    )


class Branch(Base, TimestampMixin):
    """A tenant branch/location retained after archival for historical references."""

    __tablename__ = "branches"
    __table_args__ = (
        CheckConstraint(
            "status in ('active','archived')",
            name="ck_branches_status",
        ),
        CheckConstraint(
            "length(code_normalized) > 0",
            name="ck_branches_code_normalized_not_empty",
        ),
        CheckConstraint(
            "(status = 'active' and archived_at is null) or "
            "(status = 'archived' and archived_at is not null)",
            name="ck_branches_archive_state",
        ),
        UniqueConstraint(
            "tenant_id",
            "id",
            name="uq_branches_tenant_id_id",
        ),
        UniqueConstraint(
            "tenant_id",
            "code_normalized",
            name="uq_branches_tenant_code_normalized",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "legal_entity_id"],
            ["legal_entities.tenant_id", "legal_entities.id"],
            name="fk_branches_tenant_legal_entity_id_legal_entities",
            ondelete="RESTRICT",
        ),
        Index(
            "ix_branches_tenant_status_code",
            "tenant_id",
            "status",
            "code_normalized",
        ),
        Index(
            "ix_branches_tenant_legal_entity_status",
            "tenant_id",
            "legal_entity_id",
            "status",
        ),
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    legal_entity_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    code: Mapped[str] = mapped_column(String(32), nullable=False)
    code_normalized: Mapped[str] = mapped_column(
        String(32),
        Computed("lower(ltrim(rtrim(code)))", persisted=True),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    timezone: Mapped[str] = mapped_column(String(64), nullable=False)
    country_code: Mapped[str | None] = mapped_column(String(2), nullable=True)
    city: Mapped[str | None] = mapped_column(String(120), nullable=True)
    address: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default=BranchStatus.ACTIVE.value,
        server_default=BranchStatus.ACTIVE.value,
    )
    archived_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )


__all__ = [
    "Branch",
    "BranchStatus",
    "LegalEntity",
    "LegalEntityStatus",
]
