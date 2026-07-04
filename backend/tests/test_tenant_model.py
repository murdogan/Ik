from app.db.base import Base
from app.models.tenant import Tenant, TenantStatus


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
