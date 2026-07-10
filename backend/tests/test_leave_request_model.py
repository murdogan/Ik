from app.db.base import Base
from app.models.leave_request import LeaveRequest, LeaveRequestStatus
from sqlalchemy import CheckConstraint, ForeignKeyConstraint


def test_leave_request_model_is_registered_in_metadata() -> None:
    assert "leave_requests" in Base.metadata.tables
    assert LeaveRequest.__tablename__ == "leave_requests"


def test_leave_request_table_has_documented_mvp_columns() -> None:
    columns = LeaveRequest.__table__.columns

    for name in [
        "id",
        "tenant_id",
        "employee_id",
        "leave_type",
        "start_date",
        "end_date",
        "status",
        "requested_by_user_id",
        "decided_by_user_id",
        "decision_note",
        "created_at",
        "updated_at",
    ]:
        assert name in columns


def test_leave_request_required_columns_match_minimal_record() -> None:
    columns = LeaveRequest.__table__.columns

    for name in [
        "id",
        "tenant_id",
        "employee_id",
        "leave_type",
        "start_date",
        "end_date",
        "status",
        "requested_by_user_id",
    ]:
        assert columns[name].nullable is False

    for name in ["decided_by_user_id", "decision_note"]:
        assert columns[name].nullable is True


def test_leave_request_status_values_match_approval_lifecycle() -> None:
    assert [status.value for status in LeaveRequestStatus] == [
        "pending",
        "approved",
        "rejected",
        "cancelled",
    ]


def test_leave_request_tenant_foreign_key_cascades_on_tenant_delete() -> None:
    tenant_id = LeaveRequest.__table__.columns["tenant_id"]
    foreign_keys = [
        foreign_key
        for foreign_key in tenant_id.foreign_keys
        if foreign_key.target_fullname == "tenants.id"
    ]

    assert len(foreign_keys) == 1
    assert foreign_keys[0].target_fullname == "tenants.id"
    assert foreign_keys[0].ondelete == "CASCADE"
    assert tenant_id.index is True


def test_leave_request_tenant_owned_foreign_keys_include_tenant_id() -> None:
    foreign_keys = {
        constraint.name: (
            tuple(element.parent.name for element in constraint.elements),
            constraint.referred_table.name,
            tuple(element.column.name for element in constraint.elements),
            constraint.ondelete,
        )
        for constraint in LeaveRequest.__table__.constraints
        if isinstance(constraint, ForeignKeyConstraint) and constraint.name is not None
    }

    assert foreign_keys["fk_leave_requests_tenant_employee_id_employees"] == (
        ("tenant_id", "employee_id"),
        "employees",
        ("tenant_id", "id"),
        "CASCADE",
    )
    assert foreign_keys["fk_leave_requests_tenant_requested_by_user_id_users"] == (
        ("tenant_id", "requested_by_user_id"),
        "users",
        ("tenant_id", "id"),
        None,
    )
    assert foreign_keys["fk_leave_requests_tenant_decided_by_user_id_users"] == (
        ("tenant_id", "decided_by_user_id"),
        "users",
        ("tenant_id", "id"),
        None,
    )


def test_leave_request_check_constraints_are_named() -> None:
    constraint_names = {
        constraint.name
        for constraint in LeaveRequest.__table__.constraints
        if isinstance(constraint, CheckConstraint)
    }

    assert "ck_leave_requests_status" in constraint_names
    assert "ck_leave_requests_date_order" in constraint_names


def test_leave_request_has_tenant_scoped_query_indexes() -> None:
    indexes = {
        index.name: tuple(column.name for column in index.columns)
        for index in LeaveRequest.__table__.indexes
    }

    assert indexes["ix_leave_requests_tenant_employee_start_date"] == (
        "tenant_id",
        "employee_id",
        "start_date",
    )
    assert indexes["ix_leave_requests_tenant_status_created_at"] == (
        "tenant_id",
        "status",
        "created_at",
    )
