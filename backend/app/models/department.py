"""Tenant-owned department hierarchy persistence."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    Computed,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class DepartmentStatus(StrEnum):
    ACTIVE = "active"
    ARCHIVED = "archived"


class Department(Base, TimestampMixin):
    """An adjacency-list node retained with its parent link after archival."""

    __tablename__ = "departments"
    __table_args__ = (
        CheckConstraint(
            "status in ('active','archived')",
            name="ck_departments_status",
        ),
        CheckConstraint(
            "length(code_normalized) > 0",
            name="ck_departments_code_normalized_not_empty",
        ),
        CheckConstraint(
            "parent_id is null or parent_id <> id",
            name="ck_departments_parent_not_self",
        ),
        CheckConstraint(
            "(status = 'active' and archived_at is null) or "
            "(status = 'archived' and archived_at is not null)",
            name="ck_departments_archive_state",
        ),
        UniqueConstraint(
            "tenant_id",
            "id",
            name="uq_departments_tenant_id_id",
        ),
        UniqueConstraint(
            "tenant_id",
            "code_normalized",
            name="uq_departments_tenant_code_normalized",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "parent_id"],
            ["departments.tenant_id", "departments.id"],
            name="fk_departments_tenant_parent_id_departments",
            ondelete="RESTRICT",
        ),
        Index(
            "ix_departments_tenant_status_code",
            "tenant_id",
            "status",
            "code_normalized",
            "id",
        ),
        Index(
            "ix_departments_tenant_parent_status_code",
            "tenant_id",
            "parent_id",
            "status",
            "code_normalized",
            "id",
        ),
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey(
            "tenants.id",
            name="fk_departments_tenant_id_tenants",
            ondelete="CASCADE",
        ),
        nullable=False,
    )
    parent_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    code: Mapped[str] = mapped_column(String(32), nullable=False)
    code_normalized: Mapped[str] = mapped_column(
        String(32),
        Computed("lower(ltrim(rtrim(code)))", persisted=True),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default=DepartmentStatus.ACTIVE.value,
        server_default=DepartmentStatus.ACTIVE.value,
    )
    archived_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )


__all__ = ["Department", "DepartmentStatus"]
