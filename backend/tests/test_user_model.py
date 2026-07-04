from app.db.base import Base
from app.models.user import User, UserStatus


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
