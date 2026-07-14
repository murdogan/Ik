from app.db.base import Base
from app.models.employee_account_link import EmployeeAccountLink
from sqlalchemy import CheckConstraint, ForeignKeyConstraint, UniqueConstraint


def test_employee_account_link_model_is_registered_with_current_link_table() -> None:
    assert EmployeeAccountLink.__tablename__ == "employee_account_links"
    assert "employee_account_links" in Base.metadata.tables
    assert {column.name for column in EmployeeAccountLink.__table__.columns} == {
        "id",
        "tenant_id",
        "employee_id",
        "membership_id",
        "version",
        "created_at",
        "updated_at",
    }


def test_employee_account_link_uses_canonical_membership_without_identity_copies() -> None:
    table = EmployeeAccountLink.__table__

    assert table.columns["membership_id"].nullable is False
    assert {
        "identity_id",
        "legacy_user_id",
        "user_id",
        "email",
        "password_hash",
    }.isdisjoint(column.name for column in table.columns)


def test_employee_account_link_has_tenant_qualified_restrictive_foreign_keys() -> None:
    table = EmployeeAccountLink.__table__
    foreign_keys = {
        constraint.name: (
            tuple(element.parent.name for element in constraint.elements),
            tuple(element.target_fullname for element in constraint.elements),
            constraint.ondelete,
        )
        for constraint in table.constraints
        if isinstance(constraint, ForeignKeyConstraint)
    }

    assert foreign_keys[
        "fk_employee_account_links_tenant_employee_id_employees"
    ] == (
        ("tenant_id", "employee_id"),
        ("employees.tenant_id", "employees.id"),
        "RESTRICT",
    )
    assert foreign_keys[
        "fk_employee_account_links_tenant_membership_id_memberships"
    ] == (
        ("tenant_id", "membership_id"),
        ("tenant_memberships.tenant_id", "tenant_memberships.id"),
        "RESTRICT",
    )

    tenant_foreign_keys = tuple(
        foreign_key
        for foreign_key in table.columns["tenant_id"].foreign_keys
        if foreign_key.target_fullname == "tenants.id"
    )
    assert len(tenant_foreign_keys) == 1
    assert tenant_foreign_keys[0].target_fullname == "tenants.id"
    assert tenant_foreign_keys[0].ondelete == "CASCADE"


def test_employee_account_link_uniqueness_enforces_one_to_one_current_links() -> None:
    unique_constraints = {
        constraint.name: tuple(column.name for column in constraint.columns)
        for constraint in EmployeeAccountLink.__table__.constraints
        if isinstance(constraint, UniqueConstraint)
    }

    assert unique_constraints == {
        "uq_employee_account_links_tenant_id_id": ("tenant_id", "id"),
        "uq_employee_account_links_tenant_employee_id": (
            "tenant_id",
            "employee_id",
        ),
        "uq_employee_account_links_tenant_membership_id": (
            "tenant_id",
            "membership_id",
        ),
    }


def test_employee_account_link_version_is_positive_and_optimistically_locked() -> None:
    table = EmployeeAccountLink.__table__
    version = table.columns["version"]
    checks = {
        constraint.name
        for constraint in table.constraints
        if isinstance(constraint, CheckConstraint)
    }

    assert version.nullable is False
    assert version.server_default is not None
    assert EmployeeAccountLink.__mapper__.version_id_col is version
    assert "ck_employee_account_links_version_positive" in checks
