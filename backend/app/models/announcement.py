"""Tenant announcements, immutable targeting, and publication recipient snapshots."""

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
    false,
    text,
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class AnnouncementStatus(StrEnum):
    DRAFT = "draft"
    PUBLISHED = "published"
    ARCHIVED = "archived"


class Announcement(Base, TimestampMixin):
    __tablename__ = "announcements"
    __table_args__ = (
        CheckConstraint(
            "status in ('draft','published','archived')",
            name="ck_announcements_status",
        ),
        CheckConstraint("length(trim(title)) > 0", name="ck_announcements_title_not_blank"),
        CheckConstraint("length(trim(body)) > 0", name="ck_announcements_body_not_blank"),
        CheckConstraint("length(body) <= 10000", name="ck_announcements_body_length"),
        CheckConstraint("version > 0", name="ck_announcements_version_positive"),
        CheckConstraint(
            "(status = 'draft' and published_at is null and published_by_user_id is null "
            "and archived_at is null and archived_by_user_id is null) or "
            "(status = 'published' and published_at is not null "
            "and published_by_user_id is not null and archived_at is null "
            "and archived_by_user_id is null) or "
            "(status = 'archived' and published_at is not null "
            "and published_by_user_id is not null and archived_at is not null "
            "and archived_by_user_id is not null and archived_at >= published_at)",
            name="ck_announcements_lifecycle",
        ),
        UniqueConstraint("tenant_id", "id", name="uq_announcements_tenant_id_id"),
        ForeignKeyConstraint(
            ("tenant_id", "created_by_user_id"),
            ("users.tenant_id", "users.id"),
            name="fk_announcements_tenant_created_by_user",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ("tenant_id", "published_by_user_id"),
            ("users.tenant_id", "users.id"),
            name="fk_announcements_tenant_published_by_user",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ("tenant_id", "archived_by_user_id"),
            ("users.tenant_id", "users.id"),
            name="fk_announcements_tenant_archived_by_user",
            ondelete="RESTRICT",
        ),
        Index(
            "ix_announcements_tenant_status_created",
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
        ForeignKey("tenants.id", name="fk_announcements_tenant", ondelete="CASCADE"),
        nullable=False,
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    is_critical: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=false()
    )
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default=AnnouncementStatus.DRAFT.value
    )
    version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default=text("1")
    )
    created_by_user_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    published_by_user_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), nullable=True
    )
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    archived_by_user_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), nullable=True
    )
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __mapper_args__ = {"version_id_col": version}


class AnnouncementRoleTarget(Base):
    __tablename__ = "announcement_role_targets"
    __table_args__ = (
        ForeignKeyConstraint(
            ("tenant_id", "announcement_id"),
            ("announcements.tenant_id", "announcements.id"),
            name="fk_announcement_role_targets_tenant_announcement",
            ondelete="CASCADE",
        ),
        Index(
            "ix_announcement_role_targets_tenant_role",
            "tenant_id",
            "role_id",
            "announcement_id",
        ),
    )

    tenant_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    announcement_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    role_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("roles.id", name="fk_announcement_role_targets_role", ondelete="RESTRICT"),
        primary_key=True,
    )


class AnnouncementDepartmentTarget(Base):
    __tablename__ = "announcement_department_targets"
    __table_args__ = (
        ForeignKeyConstraint(
            ("tenant_id", "announcement_id"),
            ("announcements.tenant_id", "announcements.id"),
            name="fk_announcement_department_targets_tenant_announcement",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ("tenant_id", "department_id"),
            ("departments.tenant_id", "departments.id"),
            name="fk_announcement_department_targets_tenant_department",
            ondelete="RESTRICT",
        ),
        Index(
            "ix_announcement_department_targets_tenant_department",
            "tenant_id",
            "department_id",
            "announcement_id",
        ),
    )

    tenant_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    announcement_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    department_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)


class AnnouncementBranchTarget(Base):
    __tablename__ = "announcement_branch_targets"
    __table_args__ = (
        ForeignKeyConstraint(
            ("tenant_id", "announcement_id"),
            ("announcements.tenant_id", "announcements.id"),
            name="fk_announcement_branch_targets_tenant_announcement",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ("tenant_id", "branch_id"),
            ("branches.tenant_id", "branches.id"),
            name="fk_announcement_branch_targets_tenant_branch",
            ondelete="RESTRICT",
        ),
        Index(
            "ix_announcement_branch_targets_tenant_branch",
            "tenant_id",
            "branch_id",
            "announcement_id",
        ),
    )

    tenant_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    announcement_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    branch_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)


class AnnouncementRecipient(Base):
    """Publication-time visibility fact; recipient identity never follows later role changes."""

    __tablename__ = "announcement_recipients"
    __table_args__ = (
        CheckConstraint("version > 0", name="ck_announcement_recipients_version_positive"),
        CheckConstraint(
            "acknowledged_at is null or "
            "(read_at is not null and acknowledged_at >= read_at)",
            name="ck_announcement_recipients_ack_requires_read",
        ),
        ForeignKeyConstraint(
            ("tenant_id", "announcement_id"),
            ("announcements.tenant_id", "announcements.id"),
            name="fk_announcement_recipients_tenant_announcement",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ("tenant_id", "recipient_user_id"),
            ("users.tenant_id", "users.id"),
            name="fk_announcement_recipients_tenant_user",
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "tenant_id",
            "announcement_id",
            "recipient_user_id",
            name="uq_announcement_recipients_snapshot",
        ),
        Index(
            "ix_announcement_recipients_user_published",
            "tenant_id",
            "recipient_user_id",
            "published_at",
            "announcement_id",
        ),
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    announcement_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    recipient_user_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default=text("1")
    )

    __mapper_args__ = {"version_id_col": version}


__all__ = [
    "Announcement",
    "AnnouncementBranchTarget",
    "AnnouncementDepartmentTarget",
    "AnnouncementRecipient",
    "AnnouncementRoleTarget",
    "AnnouncementStatus",
]
