"""RBAC catalog and tenant-owned user-role assignment persistence."""

from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    String,
    Text,
    UniqueConstraint,
    true,
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin
from app.platform.authorization import PermissionTargetType, RoleScopeType


class Role(Base, TimestampMixin):
    __tablename__ = "roles"
    __table_args__ = (
        CheckConstraint(
            "scope_type in ('platform','tenant')",
            name="ck_roles_scope_type",
        ),
        UniqueConstraint("code", name="uq_roles_code"),
        UniqueConstraint("id", "scope_type", name="uq_roles_id_scope_type"),
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    code: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    scope_type: Mapped[str] = mapped_column(String(16), nullable=False)
    system_role: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default=true(),
    )


class Permission(Base, TimestampMixin):
    __tablename__ = "permissions"
    __table_args__ = (
        CheckConstraint(
            "target_type in ('scope','field')",
            name="ck_permissions_target_type",
        ),
        CheckConstraint(
            "target_type <> 'scope' or "
            "target in ('own','team','department','branch','tenant','platform')",
            name="ck_permissions_scope_target",
        ),
        UniqueConstraint("code", name="uq_permissions_code"),
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    code: Mapped[str] = mapped_column(String(160), nullable=False)
    resource: Mapped[str] = mapped_column(String(64), nullable=False)
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    target: Mapped[str] = mapped_column(String(64), nullable=False)
    target_type: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default=PermissionTargetType.SCOPE.value,
    )
    description: Mapped[str] = mapped_column(Text, nullable=False)


class RolePermission(Base):
    __tablename__ = "role_permissions"

    role_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey(
            "roles.id",
            name="fk_role_permissions_role_id_roles",
            ondelete="CASCADE",
        ),
        primary_key=True,
    )
    permission_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey(
            "permissions.id",
            name="fk_role_permissions_permission_id_permissions",
            ondelete="CASCADE",
        ),
        primary_key=True,
    )


class UserRole(Base, TimestampMixin):
    __tablename__ = "user_roles"
    __table_args__ = (
        CheckConstraint(
            "role_scope_type = 'tenant'",
            name="ck_user_roles_tenant_role_scope",
        ),
        CheckConstraint(
            "active in (false, true)",
            name="ck_user_roles_active",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "user_id"],
            ["users.tenant_id", "users.id"],
            name="fk_user_roles_tenant_user_id_users",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["role_id", "role_scope_type"],
            ["roles.id", "roles.scope_type"],
            name="fk_user_roles_role_id_scope_roles",
            ondelete="RESTRICT",
        ),
        Index(
            "ix_user_roles_tenant_user_active",
            "tenant_id",
            "user_id",
            "active",
        ),
    )

    tenant_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    user_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
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


__all__ = ["Permission", "Role", "RolePermission", "UserRole"]
