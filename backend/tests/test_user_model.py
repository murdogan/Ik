from app.db.base import Base
from app.models.user import User, UserStatus
from sqlalchemy import CheckConstraint, UniqueConstraint


def test_user_model_is_registered_in_metadata() -> None:
    assert "users" in Base.metadata.tables
    assert User.__tablename__ == "users"


def test_user_table_has_required_columns() -> None:
    columns = User.__table__.columns

    for name in [
        "id",
        "tenant_id",
        "email",
        "full_name",
        "status",
        "password_hash",
        "created_at",
        "updated_at",
    ]:
        assert name in columns


def test_user_status_values_match_auth_lifecycle() -> None:
    assert [status.value for status in UserStatus] == [
        "invited",
        "active",
        "locked",
        "disabled",
    ]


def test_user_email_is_unique_within_tenant() -> None:
    unique_constraints = {
        tuple(column.name for column in constraint.columns): constraint.name
        for constraint in User.__table__.constraints
        if isinstance(constraint, UniqueConstraint)
    }

    assert unique_constraints[("tenant_id", "email")] == "uq_users_tenant_email"
    assert User.__table__.columns["email"].unique is not True


def test_user_tenant_foreign_key_cascades_on_tenant_delete() -> None:
    tenant_id = User.__table__.columns["tenant_id"]
    foreign_keys = list(tenant_id.foreign_keys)

    assert len(foreign_keys) == 1
    assert foreign_keys[0].target_fullname == "tenants.id"
    assert foreign_keys[0].ondelete == "CASCADE"
    assert tenant_id.index is True


def test_user_status_check_constraint_is_named() -> None:
    constraint_names = {
        constraint.name
        for constraint in User.__table__.constraints
        if isinstance(constraint, CheckConstraint)
    }

    assert "ck_users_status" in constraint_names
