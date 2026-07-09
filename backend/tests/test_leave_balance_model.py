from uuid import UUID

from app.db.base import Base
from app.models.leave_balance_summary import LeaveBalanceSummary
from sqlalchemy import CheckConstraint, UniqueConstraint


def test_leave_balance_summary_model_is_registered_in_metadata() -> None:
    assert "leave_balance_summaries" in Base.metadata.tables
    assert LeaveBalanceSummary.__tablename__ == "leave_balance_summaries"


def test_leave_balance_summary_table_has_placeholder_columns() -> None:
    columns = LeaveBalanceSummary.__table__.columns

    for name in [
        "id",
        "tenant_id",
        "employee_id",
        "leave_type",
        "period_year",
        "opening_balance_days",
        "used_days",
        "planned_days",
        "created_at",
        "updated_at",
    ]:
        assert name in columns


def test_leave_balance_summary_required_columns_match_manual_summary_record() -> None:
    columns = LeaveBalanceSummary.__table__.columns

    for name in [
        "id",
        "tenant_id",
        "employee_id",
        "leave_type",
        "period_year",
        "opening_balance_days",
        "used_days",
        "planned_days",
    ]:
        assert columns[name].nullable is False


def test_leave_balance_summary_foreign_keys_are_tenant_scoped_and_cascading() -> None:
    tenant_id = LeaveBalanceSummary.__table__.columns["tenant_id"]
    employee_id = LeaveBalanceSummary.__table__.columns["employee_id"]
    tenant_foreign_keys = list(tenant_id.foreign_keys)
    employee_foreign_keys = list(employee_id.foreign_keys)

    assert len(tenant_foreign_keys) == 1
    assert tenant_foreign_keys[0].target_fullname == "tenants.id"
    assert tenant_foreign_keys[0].ondelete == "CASCADE"
    assert tenant_id.index is True
    assert len(employee_foreign_keys) == 1
    assert employee_foreign_keys[0].target_fullname == "employees.id"
    assert employee_foreign_keys[0].ondelete == "CASCADE"


def test_leave_balance_summary_constraints_are_named() -> None:
    check_constraint_names = {
        constraint.name
        for constraint in LeaveBalanceSummary.__table__.constraints
        if isinstance(constraint, CheckConstraint)
    }
    unique_constraint_names = {
        constraint.name
        for constraint in LeaveBalanceSummary.__table__.constraints
        if isinstance(constraint, UniqueConstraint)
    }

    assert "ck_leave_balance_summaries_period_year" in check_constraint_names
    assert "ck_leave_balance_summaries_opening_non_negative" in check_constraint_names
    assert "ck_leave_balance_summaries_used_non_negative" in check_constraint_names
    assert "ck_leave_balance_summaries_planned_non_negative" in check_constraint_names
    assert (
        "uq_leave_balance_summaries_tenant_employee_type_period"
        in unique_constraint_names
    )


def test_leave_balance_summary_has_tenant_scoped_lookup_index() -> None:
    indexes = {
        index.name: tuple(column.name for column in index.columns)
        for index in LeaveBalanceSummary.__table__.indexes
    }

    assert indexes["ix_leave_balance_summaries_tenant_employee_period"] == (
        "tenant_id",
        "employee_id",
        "period_year",
    )


def test_leave_balance_summary_remaining_days_is_derived_from_placeholder_values() -> None:
    summary = LeaveBalanceSummary(
        id=UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"),
        tenant_id=UUID("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"),
        employee_id=UUID("cccccccc-cccc-4ccc-8ccc-cccccccccccc"),
        leave_type="annual",
        period_year=2026,
        opening_balance_days=14.0,
        used_days=3.5,
        planned_days=1.0,
    )

    assert summary.remaining_days == 9.5
