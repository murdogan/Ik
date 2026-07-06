from app.db.base import Base
from app.models.tenant import Tenant, TenantStatus
from sqlalchemy import CheckConstraint, UniqueConstraint


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
