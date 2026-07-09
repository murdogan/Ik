from app.db.base import Base
from app.models.employee import Employee, EmployeeStatus
from sqlalchemy import CheckConstraint, UniqueConstraint


def test_employee_model_is_registered_in_metadata() -> None:
    assert "employees" in Base.metadata.tables
    assert Employee.__tablename__ == "employees"


def test_employee_table_has_documented_mvp_columns() -> None:
    columns = Employee.__table__.columns

    for name in [
        "id",
        "tenant_id",
        "employee_number",
        "first_name",
        "last_name",
        "email",
        "department",
        "position",
        "status",
        "employment_start_date",
        "employment_end_date",
        "created_at",
        "updated_at",
    ]:
        assert name in columns


def test_employee_required_columns_match_minimal_record() -> None:
    columns = Employee.__table__.columns

    for name in [
        "id",
        "tenant_id",
        "employee_number",
        "first_name",
        "last_name",
        "status",
        "employment_start_date",
    ]:
        assert columns[name].nullable is False

    for name in ["email", "department", "position", "employment_end_date"]:
        assert columns[name].nullable is True


def test_employee_status_values_match_employment_lifecycle() -> None:
    assert [status.value for status in EmployeeStatus] == [
        "active",
        "on_leave",
        "terminated",
    ]


def test_employee_number_is_unique_within_tenant() -> None:
    unique_constraints = {
        tuple(column.name for column in constraint.columns): constraint.name
        for constraint in Employee.__table__.constraints
        if isinstance(constraint, UniqueConstraint)
    }

    assert unique_constraints[("tenant_id", "employee_number")] == (
        "uq_employees_tenant_employee_number"
    )
    assert Employee.__table__.columns["employee_number"].unique is not True


def test_employee_tenant_foreign_key_cascades_on_tenant_delete() -> None:
    tenant_id = Employee.__table__.columns["tenant_id"]
    foreign_keys = list(tenant_id.foreign_keys)

    assert len(foreign_keys) == 1
    assert foreign_keys[0].target_fullname == "tenants.id"
    assert foreign_keys[0].ondelete == "CASCADE"
    assert tenant_id.index is True


def test_employee_status_check_constraint_is_named() -> None:
    constraint_names = {
        constraint.name
        for constraint in Employee.__table__.constraints
        if isinstance(constraint, CheckConstraint)
    }

    assert "ck_employees_status" in constraint_names


def test_employee_date_order_check_constraint_is_named() -> None:
    constraint_names = {
        constraint.name
        for constraint in Employee.__table__.constraints
        if isinstance(constraint, CheckConstraint)
    }

    assert "ck_employees_date_order" in constraint_names


def test_employee_lifecycle_status_dates_check_constraint_is_named() -> None:
    constraint_names = {
        constraint.name
        for constraint in Employee.__table__.constraints
        if isinstance(constraint, CheckConstraint)
    }

    assert "ck_employees_lifecycle_status_dates" in constraint_names


def test_employee_has_tenant_status_index() -> None:
    indexes = {
        index.name: tuple(column.name for column in index.columns)
        for index in Employee.__table__.indexes
    }

    assert indexes["ix_employees_tenant_status"] == ("tenant_id", "status")
