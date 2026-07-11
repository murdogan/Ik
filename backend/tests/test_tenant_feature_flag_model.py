from app.db.base import Base
from app.models.tenant import Tenant, TenantFeatureFlag
from sqlalchemy import Boolean, CheckConstraint, ForeignKeyConstraint, Integer


def test_tenant_limit_is_nullable_positive_configured_metadata() -> None:
    column = Tenant.__table__.columns["active_employee_limit"]
    checks = {
        constraint.name: str(constraint.sqltext)
        for constraint in Tenant.__table__.constraints
        if isinstance(constraint, CheckConstraint)
    }

    assert isinstance(column.type, Integer)
    assert column.nullable is True
    assert column.default is None
    assert column.server_default is None
    assert checks["ck_tenants_active_employee_limit_positive"] == (
        "active_employee_limit is null or active_employee_limit between 1 and 1000000"
    )


def test_tenant_feature_flag_model_has_fixed_composite_assignment_shape() -> None:
    table = TenantFeatureFlag.__table__

    assert Base.metadata.tables["tenant_feature_flags"] is table
    assert list(table.columns) == [
        table.c.tenant_id,
        table.c.key,
        table.c.enabled,
        table.c.created_at,
        table.c.updated_at,
    ]
    assert [column.name for column in table.primary_key.columns] == ["tenant_id", "key"]
    assert table.c.key.type.length == 32
    assert isinstance(table.c.enabled.type, Boolean)
    assert table.c.enabled.nullable is False
    assert table.c.enabled.default is None


def test_tenant_feature_flag_constraints_are_named_and_tenant_rooted() -> None:
    table = TenantFeatureFlag.__table__
    check_names = {
        constraint.name
        for constraint in table.constraints
        if isinstance(constraint, CheckConstraint)
    }
    foreign_keys = [
        constraint
        for constraint in table.constraints
        if isinstance(constraint, ForeignKeyConstraint)
    ]

    assert check_names == {
        "ck_tenant_feature_flags_enabled",
        "ck_tenant_feature_flags_key",
    }
    assert len(foreign_keys) == 1
    assert foreign_keys[0].name == "fk_tenant_feature_flags_tenant_id_tenants"
    assert foreign_keys[0].ondelete == "CASCADE"
    assert [element.target_fullname for element in foreign_keys[0].elements] == [
        "tenants.id"
    ]
