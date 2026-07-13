"""Tenant-owned reusable position/job-title catalog persistence."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    Computed,
    DateTime,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class PositionStatus(StrEnum):
    ACTIVE = "active"
    ARCHIVED = "archived"


class Position(Base, TimestampMixin):
    """A reusable tenant job title retained as immutable history after archival."""

    __tablename__ = "positions"
    __table_args__ = (
        CheckConstraint(
            "status in ('active','archived')",
            name="ck_positions_status",
        ),
        CheckConstraint(
            "length(code_normalized) > 0",
            name="ck_positions_code_normalized_not_empty",
        ),
        CheckConstraint(
            "length(title_normalized) > 0",
            name="ck_positions_title_normalized_not_empty",
        ),
        CheckConstraint(
            "(status = 'active' and archived_at is null) or "
            "(status = 'archived' and archived_at is not null)",
            name="ck_positions_archive_state",
        ),
        UniqueConstraint(
            "tenant_id",
            "id",
            name="uq_positions_tenant_id_id",
        ),
        UniqueConstraint(
            "tenant_id",
            "code_normalized",
            name="uq_positions_tenant_code_normalized",
        ),
        Index(
            "ix_positions_tenant_code_cursor",
            "tenant_id",
            "code_normalized",
            "id",
        ),
        Index(
            "ix_positions_tenant_status_code_cursor",
            "tenant_id",
            "status",
            "code_normalized",
            "id",
        ),
        Index(
            "ix_positions_code_normalized_trgm",
            "code_normalized",
            postgresql_using="gin",
            postgresql_ops={"code_normalized": "gin_trgm_ops"},
        ),
        Index(
            "ix_positions_title_normalized_trgm",
            "title_normalized",
            postgresql_using="gin",
            postgresql_ops={"title_normalized": "gin_trgm_ops"},
        ),
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey(
            "tenants.id",
            name="fk_positions_tenant_id_tenants",
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
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    title_normalized: Mapped[str] = mapped_column(
        String(200),
        Computed("lower(ltrim(rtrim(title)))", persisted=True),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default=PositionStatus.ACTIVE.value,
        server_default=PositionStatus.ACTIVE.value,
    )
    archived_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )


__all__ = ["Position", "PositionStatus"]
