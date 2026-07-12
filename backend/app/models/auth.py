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


class RefreshSessionFamily(Base, TimestampMixin):
    """Server-side lifetime and revocation state shared by rotated credentials."""

    __tablename__ = "refresh_session_families"
    __table_args__ = (
        CheckConstraint(
            "expires_at > created_at",
            name="ck_refresh_session_families_expiry_order",
        ),
        CheckConstraint(
            "revoked_at is null or revoked_at >= created_at",
            name="ck_refresh_session_families_revoked_order",
        ),
        UniqueConstraint(
            "tenant_id",
            "id",
            name="uq_refresh_session_families_tenant_id_id",
        ),
        Index(
            "ix_refresh_session_families_tenant_user_expires_at",
            "tenant_id",
            "user_id",
            "expires_at",
        ),
        Index(
            "ix_refresh_session_families_tenant_membership_expires_at",
            "tenant_id",
            "membership_id",
            "expires_at",
        ),
        Index(
            "ix_refresh_session_families_expires_at",
            "expires_at",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "user_id"],
            ["users.tenant_id", "users.id"],
            name="fk_refresh_session_families_tenant_user_id_users",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "membership_id"],
            ["tenant_memberships.tenant_id", "tenant_memberships.id"],
            name="fk_refresh_session_families_tenant_membership_id_memberships",
            ondelete="CASCADE",
        ),
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey(
            "tenants.id",
            name="fk_refresh_session_families_tenant_id_tenants",
            ondelete="CASCADE",
        ),
        nullable=False,
    )
    user_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    membership_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )


class RefreshSessionToken(Base, TimestampMixin):
    """Hashed refresh-token history retained for rotation reuse detection."""

    __tablename__ = "refresh_session_tokens"
    __table_args__ = (
        CheckConstraint(
            "length(token_hash) = 64",
            name="ck_refresh_session_tokens_hash_length",
        ),
        CheckConstraint(
            "consumed_at is null or consumed_at >= created_at",
            name="ck_refresh_session_tokens_consumed_order",
        ),
        UniqueConstraint(
            "token_hash",
            name="uq_refresh_session_tokens_token_hash",
        ),
        Index(
            "ix_refresh_session_tokens_tenant_family_created_at",
            "tenant_id",
            "family_id",
            "created_at",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "family_id"],
            ["refresh_session_families.tenant_id", "refresh_session_families.id"],
            name="fk_refresh_session_tokens_tenant_family_id_families",
            ondelete="CASCADE",
        ),
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey(
            "tenants.id",
            name="fk_refresh_session_tokens_tenant_id_tenants",
            ondelete="CASCADE",
        ),
        nullable=False,
    )
    family_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    consumed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )


class OrganizationSelectionTransaction(Base, TimestampMixin):
    """Hashed, expiring, one-use continuation issued after identity authentication."""

    __tablename__ = "organization_selection_transactions"
    __table_args__ = (
        CheckConstraint(
            "length(token_hash) = 64",
            name="ck_organization_selection_transactions_hash_length",
        ),
        CheckConstraint(
            "expires_at > created_at",
            name="ck_organization_selection_transactions_expiry_order",
        ),
        CheckConstraint(
            "consumed_at is null or consumed_at >= created_at",
            name="ck_organization_selection_transactions_consumed_order",
        ),
        UniqueConstraint(
            "token_hash",
            name="uq_organization_selection_transactions_token_hash",
        ),
        Index(
            "ix_organization_selection_transactions_identity_expires_at",
            "identity_id",
            "expires_at",
        ),
        Index(
            "ix_organization_selection_transactions_expires_at",
            "expires_at",
        ),
        {"implicit_returning": False},
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    identity_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey(
            "identities.id",
            name="fk_organization_selection_transactions_identity_id_identities",
            ondelete="CASCADE",
        ),
        nullable=False,
    )
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    consumed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )


class OrganizationSelectionChoice(Base):
    """Opaque option mapped to one eligible tenant inside a selection transaction."""

    __tablename__ = "organization_selection_choices"
    __table_args__ = (
        ForeignKeyConstraint(
            ["transaction_id"],
            ["organization_selection_transactions.id"],
            name="fk_organization_selection_choices_transaction_id_transactions",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name="fk_organization_selection_choices_tenant_id_tenants",
            ondelete="CASCADE",
        ),
        UniqueConstraint(
            "transaction_id",
            "tenant_id",
            name="uq_organization_selection_choices_transaction_tenant",
        ),
    )

    selection_key: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    transaction_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    tenant_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)


class AuthenticationRateLimitBucket(Base):
    """PII-free fixed-window counter shared by authentication workers."""

    __tablename__ = "authentication_rate_limit_buckets"
    __table_args__ = (
        CheckConstraint(
            "length(bucket_key_hash) = 64",
            name="ck_authentication_rate_limit_buckets_hash_length",
        ),
        CheckConstraint(
            "scope in ('login_source','login_identity')",
            name="ck_authentication_rate_limit_buckets_scope",
        ),
        CheckConstraint(
            "attempt_count >= 1",
            name="ck_authentication_rate_limit_buckets_attempt_count_positive",
        ),
        CheckConstraint(
            "expires_at > window_started_at",
            name="ck_authentication_rate_limit_buckets_expiry_order",
        ),
        Index(
            "ix_authentication_rate_limit_buckets_expires_at",
            "expires_at",
        ),
    )

    bucket_key_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    scope: Mapped[str] = mapped_column(String(32), nullable=False)
    window_started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    attempt_count: Mapped[int] = mapped_column(nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
