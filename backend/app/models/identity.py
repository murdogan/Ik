"""Global credential identities and tenant membership persistence."""

from enum import StrEnum
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Computed,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    true,
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin
from app.platform.authorization import RoleScopeType


class IdentityStatus(StrEnum):
    """Credential-wide state independent from any one tenant membership."""

    PENDING = "pending"
    ACTIVE = "active"
    LOCKED = "locked"
    DISABLED = "disabled"


class MembershipStatus(StrEnum):
    """Tenant-local access state retained from the legacy user contract."""

    INVITED = "invited"
    ACTIVE = "active"
    LOCKED = "locked"
    DISABLED = "disabled"


class Identity(Base, TimestampMixin):
    """One globally unique email/password credential."""

    __tablename__ = "identities"
    __table_args__ = (
        CheckConstraint(
            "status in ('pending','active','locked','disabled')",
            name="ck_identities_status",
        ),
        CheckConstraint(
            "length(email_normalized) > 0",
            name="ck_identities_email_normalized_not_empty",
        ),
        CheckConstraint(
            "(status = 'pending' and password_hash is null) or "
            "(status in ('active','locked') and password_hash is not null) or "
            "status = 'disabled'",
            name="ck_identities_password_ownership",
        ),
        CheckConstraint(
            "platform_permission_version >= 1",
            name="ck_identities_platform_permission_version_positive",
        ),
        UniqueConstraint(
            "email_normalized",
            name="uq_identities_email_normalized",
        ),
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    email_normalized: Mapped[str] = mapped_column(
        String(320),
        Computed("lower(ltrim(rtrim(email)))", persisted=True),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default=IdentityStatus.PENDING.value,
        server_default=IdentityStatus.PENDING.value,
    )
    password_hash: Mapped[str | None] = mapped_column(Text, nullable=True)
    platform_permission_version: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
        server_default="1",
    )


class TenantMembership(Base, TimestampMixin):
    """One identity's tenant-local access, display name, and permission version."""

    __tablename__ = "tenant_memberships"
    __table_args__ = (
        CheckConstraint(
            "status in ('invited','active','locked','disabled')",
            name="ck_tenant_memberships_status",
        ),
        CheckConstraint(
            "permission_version >= 1",
            name="ck_tenant_memberships_permission_version_positive",
        ),
        UniqueConstraint(
            "tenant_id",
            "id",
            name="uq_tenant_memberships_tenant_id_id",
        ),
        UniqueConstraint(
            "tenant_id",
            "identity_id",
            name="uq_tenant_memberships_tenant_identity",
        ),
        UniqueConstraint(
            "tenant_id",
            "legacy_user_id",
            name="uq_tenant_memberships_tenant_legacy_user",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "legacy_user_id"],
            ["users.tenant_id", "users.id"],
            name="fk_tenant_memberships_tenant_legacy_user_id_users",
            ondelete="RESTRICT",
        ),
        Index(
            "ix_tenant_memberships_identity_id",
            "identity_id",
        ),
        Index(
            "ix_tenant_memberships_tenant_status_created_at_id",
            "tenant_id",
            "status",
            "created_at",
            "id",
        ),
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey(
            "tenants.id",
            name="fk_tenant_memberships_tenant_id_tenants",
            ondelete="CASCADE",
        ),
        nullable=False,
    )
    identity_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey(
            "identities.id",
            name="fk_tenant_memberships_identity_id_identities",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )
    legacy_user_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        nullable=False,
    )
    full_name: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default=MembershipStatus.INVITED.value,
        server_default=MembershipStatus.INVITED.value,
    )
    permission_version: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
        server_default="1",
    )


class PlatformIdentityRole(Base, TimestampMixin):
    """Platform-scoped role assignment owned by a global credential identity."""

    __tablename__ = "platform_identity_roles"
    __table_args__ = (
        CheckConstraint(
            "role_scope_type = 'platform'",
            name="ck_platform_identity_roles_platform_scope",
        ),
        CheckConstraint(
            "active in (false, true)",
            name="ck_platform_identity_roles_active",
        ),
        ForeignKeyConstraint(
            ["role_id", "role_scope_type"],
            ["roles.id", "roles.scope_type"],
            name="fk_platform_identity_roles_role_id_scope_roles",
            ondelete="RESTRICT",
        ),
        Index(
            "ix_platform_identity_roles_identity_active",
            "identity_id",
            "active",
        ),
    )

    identity_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey(
            "identities.id",
            name="fk_platform_identity_roles_identity_id_identities",
            ondelete="CASCADE",
        ),
        primary_key=True,
    )
    role_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    role_scope_type: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default=RoleScopeType.PLATFORM.value,
        server_default=RoleScopeType.PLATFORM.value,
    )
    active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default=true(),
    )


class MembershipRole(Base, TimestampMixin):
    """Tenant-qualified role assignment for a canonical membership."""

    __tablename__ = "membership_roles"
    __table_args__ = (
        CheckConstraint(
            "role_scope_type = 'tenant'",
            name="ck_membership_roles_tenant_role_scope",
        ),
        CheckConstraint(
            "active in (false, true)",
            name="ck_membership_roles_active",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "membership_id"],
            ["tenant_memberships.tenant_id", "tenant_memberships.id"],
            name="fk_membership_roles_tenant_membership_id_memberships",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["role_id", "role_scope_type"],
            ["roles.id", "roles.scope_type"],
            name="fk_membership_roles_role_id_scope_roles",
            ondelete="RESTRICT",
        ),
        Index(
            "ix_membership_roles_tenant_membership_active",
            "tenant_id",
            "membership_id",
            "active",
        ),
    )

    tenant_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    membership_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    role_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    role_scope_type: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default=RoleScopeType.TENANT.value,
        server_default=RoleScopeType.TENANT.value,
    )
    active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default=true(),
    )


__all__ = [
    "Identity",
    "IdentityStatus",
    "MembershipRole",
    "MembershipStatus",
    "PlatformIdentityRole",
    "TenantMembership",
]
