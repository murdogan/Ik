from app.db.base import Base
from app.models.employee_profile import (
    EmployeeEmploymentProfile,
    EmployeePersonalProfile,
)
from sqlalchemy import CheckConstraint, ForeignKeyConstraint, UniqueConstraint


def test_employee_profile_models_are_registered_with_focused_table_names() -> None:
    assert EmployeePersonalProfile.__tablename__ == "employee_profiles"
    assert EmployeeEmploymentProfile.__tablename__ == "employee_employments"
    assert {"employee_profiles", "employee_employments"} <= set(Base.metadata.tables)


def test_personal_profile_has_only_the_approved_p4b_fields() -> None:
    assert {column.name for column in EmployeePersonalProfile.__table__.columns} == {
        "id",
        "tenant_id",
        "employee_id",
        "preferred_name",
        "birth_date",
        "phone",
        "version",
        "created_at",
        "updated_at",
    }


def test_employment_profile_has_only_the_approved_p4b_fields() -> None:
    assert {column.name for column in EmployeeEmploymentProfile.__table__.columns} == {
        "id",
        "tenant_id",
        "employee_id",
        "contract_type",
        "work_type",
        "version",
        "created_at",
        "updated_at",
    }


def test_profiles_are_one_to_one_tenant_owned_employee_children() -> None:
    for model in (EmployeePersonalProfile, EmployeeEmploymentProfile):
        table = model.__table__
        unique_column_sets = {
            tuple(column.name for column in constraint.columns)
            for constraint in table.constraints
            if isinstance(constraint, UniqueConstraint)
        }
        composite_foreign_keys = [
            constraint
            for constraint in table.constraints
            if isinstance(constraint, ForeignKeyConstraint)
            and tuple(element.parent.name for element in constraint.elements)
            == ("tenant_id", "employee_id")
        ]

        assert ("tenant_id", "employee_id") in unique_column_sets
        assert ("tenant_id", "id") in unique_column_sets
        assert len(composite_foreign_keys) == 1
        assert tuple(element.target_fullname for element in composite_foreign_keys[0].elements) == (
            "employees.tenant_id",
            "employees.id",
        )
        assert composite_foreign_keys[0].ondelete == "RESTRICT"

        tenant_foreign_keys = [
            foreign_key
            for foreign_key in table.columns["tenant_id"].foreign_keys
            if foreign_key.target_fullname == "tenants.id"
        ]
        assert len(tenant_foreign_keys) == 1
        assert tenant_foreign_keys[0].target_fullname == "tenants.id"
        assert tenant_foreign_keys[0].ondelete == "CASCADE"


def test_profile_versions_are_positive_and_are_sqlalchemy_optimistic_locks() -> None:
    for model in (EmployeePersonalProfile, EmployeeEmploymentProfile):
        version = model.__table__.columns["version"]
        check_names = {
            constraint.name
            for constraint in model.__table__.constraints
            if isinstance(constraint, CheckConstraint)
        }

        assert version.nullable is False
        assert version.server_default is not None
        assert model.__mapper__.version_id_col is version
        assert any(name and "version_positive" in name for name in check_names)


def test_employment_enums_are_narrow_nullable_mvp_codes() -> None:
    table = EmployeeEmploymentProfile.__table__
    check_sql = " ".join(
        str(constraint.sqltext)
        for constraint in table.constraints
        if isinstance(constraint, CheckConstraint)
    )

    assert "indefinite" in check_sql
    assert "fixed_term" in check_sql
    assert "full_time" in check_sql
    assert "part_time" in check_sql
    assert table.columns["contract_type"].nullable is True
    assert table.columns["work_type"].nullable is True


def test_profile_tables_never_duplicate_core_lifecycle_or_forbidden_data() -> None:
    forbidden = {
        "employee_number",
        "first_name",
        "last_name",
        "email",
        "employment_start_date",
        "employment_end_date",
        "status",
        "gender",
        "marital_status",
        "nationality",
        "national_id",
        "tckn",
        "passport",
        "iban",
        "salary",
        "address",
        "emergency_contact",
        "document",
    }

    for model in (EmployeePersonalProfile, EmployeeEmploymentProfile):
        assert forbidden.isdisjoint(column.name for column in model.__table__.columns)
