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
        "department_normalized",
        "position",
        "status",
        "employment_start_date",
        "employment_end_date",
        "archived_at",
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

    for name in [
        "email",
        "department",
        "department_normalized",
        "position",
        "employment_end_date",
        "archived_at",
    ]:
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


def test_employee_has_normalized_tenant_uniqueness_for_number_and_work_email() -> None:
    columns = Employee.__table__.columns
    indexes = {index.name: index for index in Employee.__table__.indexes}
    check_names = {
        constraint.name
        for constraint in Employee.__table__.constraints
        if isinstance(constraint, CheckConstraint)
    }

    assert columns["employee_number_normalized"].computed is not None
    assert columns["employee_number_normalized"].nullable is False
    assert columns["email_normalized"].computed is not None
    assert columns["email_normalized"].nullable is True
    assert tuple(
        column.name
        for column in indexes["uq_employees_tenant_employee_number_normalized"].columns
    ) == ("tenant_id", "employee_number_normalized")
    assert indexes["uq_employees_tenant_employee_number_normalized"].unique is True
    assert tuple(
        column.name
        for column in indexes["uq_employees_tenant_email_normalized"].columns
    ) == ("tenant_id", "email_normalized")
    assert indexes["uq_employees_tenant_email_normalized"].unique is True
    assert "ck_employees_employee_number_not_blank" in check_names
    assert "ck_employees_email_not_blank" in check_names


def test_employee_has_positive_optimistic_version_column() -> None:
    columns = Employee.__table__.columns
    check_names = {
        constraint.name
        for constraint in Employee.__table__.constraints
        if isinstance(constraint, CheckConstraint)
    }

    assert columns["version"].nullable is False
    assert columns["version"].server_default is not None
    assert Employee.__mapper__.version_id_col is columns["version"]
    assert "ck_employees_version_positive" in check_names


def test_employee_has_tenant_id_candidate_key_for_tenant_owned_children() -> None:
    unique_constraints = {
        tuple(column.name for column in constraint.columns): constraint.name
        for constraint in Employee.__table__.constraints
        if isinstance(constraint, UniqueConstraint)
    }

    assert unique_constraints[("tenant_id", "id")] == "uq_employees_tenant_id_id"


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


def test_employee_has_tenant_archive_index() -> None:
    indexes = {
        index.name: tuple(column.name for column in index.columns)
        for index in Employee.__table__.indexes
    }

    assert indexes["ix_employees_tenant_archived_at"] == (
        "tenant_id",
        "archived_at",
    )


def test_employee_has_immutable_partial_directory_cursor_indexes() -> None:
    indexes = {index.name: index for index in Employee.__table__.indexes}
    directory_index = indexes["ix_employees_tenant_directory_cursor"]
    status_directory_index = indexes[
        "ix_employees_tenant_status_directory_cursor"
    ]

    assert tuple(column.name for column in directory_index.columns) == (
        "tenant_id",
        "created_at",
        "id",
    )
    assert tuple(column.name for column in status_directory_index.columns) == (
        "tenant_id",
        "status",
        "created_at",
        "id",
    )
    for index in (directory_index, status_directory_index):
        assert str(index.dialect_options["postgresql"]["where"]) == (
            "archived_at IS NULL"
        )
        assert str(index.dialect_options["sqlite"]["where"]) == "archived_at IS NULL"


def test_employee_has_postgresql_search_indexes() -> None:
    indexes = {index.name: index for index in Employee.__table__.indexes}

    assert tuple(
        column.name for column in indexes["ix_employees_employee_number_trgm"].columns
    ) == ("employee_number",)
    assert tuple(column.name for column in indexes["ix_employees_email_trgm"].columns) == (
        "email",
    )
    assert tuple(
        column.name
        for column in indexes["ix_employees_tenant_department_normalized"].columns
    ) == ("tenant_id", "department_normalized")
    assert (
        indexes["ix_employees_employee_number_trgm"].dialect_options["postgresql"]["using"]
        == "gin"
    )
