from app.db.base import Base
from app.models.identity import (
    Identity,
    IdentityStatus,
    MembershipRole,
    MembershipStatus,
    PlatformIdentityRole,
    TenantMembership,
)
from sqlalchemy import CheckConstraint, ForeignKeyConstraint, UniqueConstraint


def test_identity_and_membership_models_are_registered() -> None:
    assert {
        "identities",
        "tenant_memberships",
        "membership_roles",
        "platform_identity_roles",
    } <= set(Base.metadata.tables)


def test_identity_statuses_and_global_credential_constraints_are_explicit() -> None:
    assert [status.value for status in IdentityStatus] == [
        "pending",
        "active",
        "locked",
        "disabled",
    ]
    assert tuple(Identity.__table__.columns) == (
        Identity.__table__.c.id,
        Identity.__table__.c.email,
        Identity.__table__.c.email_normalized,
        Identity.__table__.c.status,
        Identity.__table__.c.password_hash,
        Identity.__table__.c.platform_permission_version,
        Identity.__table__.c.created_at,
        Identity.__table__.c.updated_at,
    )

    normalized = Identity.__table__.c.email_normalized
    assert normalized.computed is not None
    assert str(normalized.computed.sqltext) == "lower(ltrim(rtrim(email)))"
    assert normalized.computed.persisted is True

    unique_constraints = _unique_constraints(Identity)
    assert unique_constraints == {
        ("email_normalized",): "uq_identities_email_normalized",
    }
    checks = _check_constraints(Identity)
    assert set(checks) == {
        "ck_identities_status",
        "ck_identities_email_normalized_not_empty",
        "ck_identities_password_ownership",
        "ck_identities_platform_permission_version_positive",
    }
    assert "status = 'pending' and password_hash is null" in checks[
        "ck_identities_password_ownership"
    ]
    assert "status in ('active','locked') and password_hash is not null" in checks[
        "ck_identities_password_ownership"
    ]


def test_platform_roles_are_global_identity_assignments_with_platform_scope() -> None:
    assert tuple(
        column.name for column in PlatformIdentityRole.__table__.primary_key.columns
    ) == ("identity_id", "role_id")
    assert set(_check_constraints(PlatformIdentityRole)) == {
        "ck_platform_identity_roles_platform_scope",
        "ck_platform_identity_roles_active",
    }
    assert _foreign_keys(PlatformIdentityRole) == {
        "fk_platform_identity_roles_identity_id_identities": (
            ("identity_id",),
            ("identities.id",),
            "CASCADE",
        ),
        "fk_platform_identity_roles_role_id_scope_roles": (
            ("role_id", "role_scope_type"),
            ("roles.id", "roles.scope_type"),
            "RESTRICT",
        ),
    }
    assert _indexes(PlatformIdentityRole) == {
        "ix_platform_identity_roles_identity_active": ("identity_id", "active")
    }


def test_tenant_membership_preserves_legacy_state_with_tenant_safe_keys() -> None:
    assert [status.value for status in MembershipStatus] == [
        "invited",
        "active",
        "locked",
        "disabled",
    ]
    assert tuple(column.name for column in TenantMembership.__table__.columns) == (
        "id",
        "tenant_id",
        "identity_id",
        "legacy_user_id",
        "full_name",
        "status",
        "permission_version",
        "created_at",
        "updated_at",
    )
    assert _unique_constraints(TenantMembership) == {
        ("tenant_id", "id"): "uq_tenant_memberships_tenant_id_id",
        ("tenant_id", "identity_id"): "uq_tenant_memberships_tenant_identity",
        ("tenant_id", "legacy_user_id"): "uq_tenant_memberships_tenant_legacy_user",
    }
    assert set(_check_constraints(TenantMembership)) == {
        "ck_tenant_memberships_status",
        "ck_tenant_memberships_permission_version_positive",
    }
    assert _foreign_keys(TenantMembership) == {
        "fk_tenant_memberships_tenant_id_tenants": (
            ("tenant_id",),
            ("tenants.id",),
            "CASCADE",
        ),
        "fk_tenant_memberships_identity_id_identities": (
            ("identity_id",),
            ("identities.id",),
            "RESTRICT",
        ),
        "fk_tenant_memberships_tenant_legacy_user_id_users": (
            ("tenant_id", "legacy_user_id"),
            ("users.tenant_id", "users.id"),
            "RESTRICT",
        ),
    }
    assert _indexes(TenantMembership) == {
        "ix_tenant_memberships_identity_id": ("identity_id",),
        "ix_tenant_memberships_tenant_status_created_at_id": (
            "tenant_id",
            "status",
            "created_at",
            "id",
        ),
    }


def test_membership_roles_are_qualified_by_tenant_and_tenant_role_scope() -> None:
    assert tuple(column.name for column in MembershipRole.__table__.primary_key.columns) == (
        "tenant_id",
        "membership_id",
        "role_id",
    )
    assert set(_check_constraints(MembershipRole)) == {
        "ck_membership_roles_tenant_role_scope",
        "ck_membership_roles_active",
    }
    assert _foreign_keys(MembershipRole) == {
        "fk_membership_roles_tenant_membership_id_memberships": (
            ("tenant_id", "membership_id"),
            ("tenant_memberships.tenant_id", "tenant_memberships.id"),
            "CASCADE",
        ),
        "fk_membership_roles_role_id_scope_roles": (
            ("role_id", "role_scope_type"),
            ("roles.id", "roles.scope_type"),
            "RESTRICT",
        ),
    }
    assert _indexes(MembershipRole) == {
        "ix_membership_roles_tenant_membership_active": (
            "tenant_id",
            "membership_id",
            "active",
        ),
    }


def _unique_constraints(model: type) -> dict[tuple[str, ...], str | None]:
    return {
        tuple(column.name for column in constraint.columns): constraint.name
        for constraint in model.__table__.constraints
        if isinstance(constraint, UniqueConstraint)
    }


def _check_constraints(model: type) -> dict[str | None, str]:
    return {
        constraint.name: str(constraint.sqltext)
        for constraint in model.__table__.constraints
        if isinstance(constraint, CheckConstraint)
    }


def _foreign_keys(
    model: type,
) -> dict[str | None, tuple[tuple[str, ...], tuple[str, ...], str | None]]:
    return {
        constraint.name: (
            tuple(constraint.column_keys),
            tuple(element.target_fullname for element in constraint.elements),
            constraint.ondelete,
        )
        for constraint in model.__table__.constraints
        if isinstance(constraint, ForeignKeyConstraint)
    }


def _indexes(model: type) -> dict[str | None, tuple[str, ...]]:
    return {
        index.name: tuple(expression.name for expression in index.expressions)
        for index in model.__table__.indexes
    }
