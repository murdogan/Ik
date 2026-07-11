from app.db.base import Base
from app.models.tenant import (
    Tenant,
    TenantDateFormat,
    TenantSettings,
    TenantStatus,
    TenantTimeFormat,
    TenantWeekStartDay,
)
from sqlalchemy import CheckConstraint, ForeignKeyConstraint, UniqueConstraint


def test_tenant_model_is_registered_in_metadata() -> None:
    assert "tenants" in Base.metadata.tables
    assert Tenant.__tablename__ == "tenants"


def test_tenant_table_has_required_columns() -> None:
    columns = Tenant.__table__.columns

    for name in [
        "id",
        "slug",
        "name",
        "status",
        "plan_code",
        "data_region",
        "locale",
        "timezone",
        "created_at",
        "updated_at",
    ]:
        assert name in columns


def test_tenant_status_values_match_lifecycle() -> None:
    assert [status.value for status in TenantStatus] == [
        "provisioning",
        "trial",
        "active",
        "suspended",
        "offboarding",
        "closed",
    ]


def test_tenant_slug_is_unique_and_indexed() -> None:
    slug = Tenant.__table__.columns["slug"]
    unique_columns = {
        tuple(column.name for column in constraint.columns)
        for constraint in Tenant.__table__.constraints
        if isinstance(constraint, UniqueConstraint)
    }

    assert slug.index is True
    assert ("slug",) in unique_columns


def test_tenant_status_check_constraint_is_named() -> None:
    constraint_names = {
        constraint.name
        for constraint in Tenant.__table__.constraints
        if isinstance(constraint, CheckConstraint)
    }

    assert "ck_tenants_status" in constraint_names


def test_tenant_settings_model_is_registered_with_fixed_columns() -> None:
    assert Base.metadata.tables["tenant_settings"] is TenantSettings.__table__
    assert list(TenantSettings.__table__.columns.keys()) == [
        "tenant_id",
        "week_start_day",
        "date_format",
        "time_format",
        "created_at",
        "updated_at",
    ]
    assert [column.name for column in TenantSettings.__table__.primary_key.columns] == [
        "tenant_id"
    ]


def test_tenant_settings_defaults_match_typed_catalog() -> None:
    columns = TenantSettings.__table__.columns

    assert columns["week_start_day"].default.arg == TenantWeekStartDay.MONDAY.value
    assert str(columns["week_start_day"].server_default.arg) == "monday"
    assert columns["date_format"].default.arg == TenantDateFormat.DAY_MONTH_YEAR.value
    assert str(columns["date_format"].server_default.arg) == "DD.MM.YYYY"
    assert columns["time_format"].default.arg == TenantTimeFormat.HOUR_24.value
    assert str(columns["time_format"].server_default.arg) == "24h"


def test_tenant_settings_constraints_are_named_and_tenant_rooted() -> None:
    table = TenantSettings.__table__
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
        "ck_tenant_settings_week_start_day",
        "ck_tenant_settings_date_format",
        "ck_tenant_settings_time_format",
    }
    assert len(foreign_keys) == 1
    assert foreign_keys[0].name == "fk_tenant_settings_tenant_id_tenants"
    assert foreign_keys[0].ondelete == "CASCADE"
    assert [element.target_fullname for element in foreign_keys[0].elements] == [
        "tenants.id"
    ]
