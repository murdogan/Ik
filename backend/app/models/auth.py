"""Authentication persistence models."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
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


class UserActivationToken(Base, TimestampMixin):
    """SHA-256-hashed, expiring activation credential for one tenant user."""

    __tablename__ = "user_activation_tokens"
    __table_args__ = (
        CheckConstraint(
            "length(token_hash) = 64",
            name="ck_user_activation_tokens_hash_length",
        ),
        CheckConstraint(
            "expires_at > created_at",
            name="ck_user_activation_tokens_expiry_order",
        ),
        CheckConstraint(
            "consumed_at is null or consumed_at >= created_at",
            name="ck_user_activation_tokens_consumed_order",
        ),
        CheckConstraint(
            "revoked_at is null or revoked_at >= created_at",
            name="ck_user_activation_tokens_revoked_order",
        ),
        CheckConstraint(
            "consumed_at is null or revoked_at is null",
            name="ck_user_activation_tokens_terminal_state",
        ),
        UniqueConstraint(
            "token_hash",
            name="uq_user_activation_tokens_token_hash",
        ),
        Index(
            "ix_user_activation_tokens_tenant_user_expires_at",
            "tenant_id",
            "user_id",
            "expires_at",
        ),
        Index(
            "ix_user_activation_tokens_expires_at",
            "expires_at",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "user_id"],
            ["users.tenant_id", "users.id"],
            name="fk_user_activation_tokens_tenant_user_id_users",
            ondelete="CASCADE",
        ),
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey(
            "tenants.id",
            name="fk_user_activation_tokens_tenant_id_tenants",
            ondelete="CASCADE",
        ),
        nullable=False,
    )
    user_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    consumed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
