from app.db.base import Base
from app.models.leave_request import LeaveRequest, LeaveRequestStatus
from sqlalchemy import CheckConstraint


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
    foreign_keys = list(tenant_id.foreign_keys)

    assert len(foreign_keys) == 1
    assert foreign_keys[0].target_fullname == "tenants.id"
    assert foreign_keys[0].ondelete == "CASCADE"
    assert tenant_id.index is True


def test_leave_request_employee_foreign_key_cascades_on_employee_delete() -> None:
    employee_id = LeaveRequest.__table__.columns["employee_id"]
    foreign_keys = list(employee_id.foreign_keys)

    assert len(foreign_keys) == 1
    assert foreign_keys[0].target_fullname == "employees.id"
    assert foreign_keys[0].ondelete == "CASCADE"


def test_leave_request_user_foreign_keys_reference_users() -> None:
    requested_by = LeaveRequest.__table__.columns["requested_by_user_id"]
    decided_by = LeaveRequest.__table__.columns["decided_by_user_id"]

    requested_by_foreign_keys = list(requested_by.foreign_keys)
    decided_by_foreign_keys = list(decided_by.foreign_keys)

    assert len(requested_by_foreign_keys) == 1
    assert requested_by_foreign_keys[0].target_fullname == "users.id"
    assert len(decided_by_foreign_keys) == 1
    assert decided_by_foreign_keys[0].target_fullname == "users.id"


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
