import importlib
import pkgutil
from pathlib import Path

import app.models as model_package
from alembic import command as alembic_command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from app.db.base import Base
from sqlalchemy import (
    CheckConstraint,
    ForeignKeyConstraint,
    Table,
    UniqueConstraint,
    create_engine,
    inspect,
    text,
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID

ALEMBIC_INI = Path("alembic.ini")


def _alembic_config(database_url: str | None = None) -> Config:
    config = Config(str(ALEMBIC_INI))
    if database_url is not None:
        config.set_main_option("sqlalchemy.url", database_url)
    return config


def _script_directory() -> ScriptDirectory:
    return ScriptDirectory.from_config(_alembic_config())


def _import_all_model_modules() -> None:
    for module in pkgutil.iter_modules(
        model_package.__path__, f"{model_package.__name__}."
    ):
        importlib.import_module(module.name)


def _current_model_tables() -> dict[str, Table]:
    _import_all_model_modules()
    return {
        mapper.local_table.name: mapper.local_table
        for mapper in Base.registry.mappers
    }


def _model_column_signatures(table: Table) -> dict[str, tuple[bool, bool, bool]]:
    return {
        column.name: (
            column.nullable,
            column.primary_key,
            column.server_default is not None,
        )
        for column in table.columns
    }


def _database_column_signatures(
    columns: list[dict[str, object]],
) -> dict[str, tuple[bool, bool, bool]]:
    return {
        str(column["name"]): (
            bool(column["nullable"]),
            bool(column["primary_key"]),
            column["default"] is not None,
        )
        for column in columns
    }


def _model_index_signatures(table: Table) -> set[tuple[str | None, tuple[str, ...], bool]]:
    return {
        (
            index.name,
            tuple(column.name for column in index.columns),
            bool(index.unique),
        )
        for index in table.indexes
    }


def _database_index_signatures(
    indexes: list[dict[str, object]],
) -> set[tuple[str | None, tuple[str, ...], bool]]:
    return {
        (
            index["name"] if index["name"] is None else str(index["name"]),
            tuple(str(column_name) for column_name in index["column_names"]),
            bool(index["unique"]),
        )
        for index in indexes
    }


def _model_unique_constraint_signatures(
    table: Table,
) -> set[tuple[str | None, tuple[str, ...]]]:
    return {
        (
            constraint.name,
            tuple(column.name for column in constraint.columns),
        )
        for constraint in table.constraints
        if isinstance(constraint, UniqueConstraint)
    }


def _database_unique_constraint_signatures(
    constraints: list[dict[str, object]],
) -> set[tuple[str | None, tuple[str, ...]]]:
    return {
        (
            constraint["name"] if constraint["name"] is None else str(constraint["name"]),
            tuple(str(column_name) for column_name in constraint["column_names"]),
        )
        for constraint in constraints
    }


def _model_foreign_key_signatures(
    table: Table,
) -> set[tuple[tuple[str, ...], str, tuple[str, ...], str | None]]:
    return {
        (
            tuple(element.parent.name for element in constraint.elements),
            constraint.referred_table.name,
            tuple(element.column.name for element in constraint.elements),
            constraint.ondelete,
        )
        for constraint in table.constraints
        if isinstance(constraint, ForeignKeyConstraint)
    }


def _database_foreign_key_signatures(
    foreign_keys: list[dict[str, object]],
) -> set[tuple[tuple[str, ...], str, tuple[str, ...], str | None]]:
    return {
        (
            tuple(str(column_name) for column_name in foreign_key["constrained_columns"]),
            str(foreign_key["referred_table"]),
            tuple(str(column_name) for column_name in foreign_key["referred_columns"]),
            foreign_key["options"].get("ondelete"),
        )
        for foreign_key in foreign_keys
    }


def _model_check_constraint_names(table: Table) -> set[str | None]:
    return {
        constraint.name
        for constraint in table.constraints
        if isinstance(constraint, CheckConstraint)
    }


def _database_check_constraint_names(
    constraints: list[dict[str, object]],
) -> set[str | None]:
    return {
        constraint["name"] if constraint["name"] is None else str(constraint["name"])
        for constraint in constraints
    }


def _compare_type(context, _inspected_column, _metadata_column, _inspected_type, metadata_type):
    if context.dialect.name == "sqlite" and isinstance(metadata_type, PG_UUID):
        return False
    return None


def test_alembic_config_points_to_backend_migrations() -> None:
    config = _alembic_config()

    assert config.get_main_option("script_location") == "backend/alembic"


def test_core_migration_chain_is_linear() -> None:
    script = _script_directory()
    tenant_revision = script.get_revision("0001_create_tenants")
    user_revision = script.get_revision("0002_create_users")
    employee_revision = script.get_revision("0003_create_employees")
    leave_request_revision = script.get_revision("0004_create_leave_requests")
    employee_date_order_revision = script.get_revision("0005_employee_date_order")
    leave_balance_revision = script.get_revision("0006_create_leave_balance_summaries")
    timestamp_revision = script.get_revision("0007_enforce_timestamp_not_null")
    employee_lifecycle_revision = script.get_revision(
        "0008_employee_lifecycle_status_dates"
    )

    assert script.get_heads() == ["0008_employee_lifecycle_status_dates"]
    assert tenant_revision is not None
    assert tenant_revision.down_revision is None
    assert user_revision is not None
    assert user_revision.down_revision == "0001_create_tenants"
    assert employee_revision is not None
    assert employee_revision.down_revision == "0002_create_users"
    assert leave_request_revision is not None
    assert leave_request_revision.down_revision == "0003_create_employees"
    assert employee_date_order_revision is not None
    assert employee_date_order_revision.down_revision == "0004_create_leave_requests"
    assert leave_balance_revision is not None
    assert leave_balance_revision.down_revision == "0005_employee_date_order"
    assert timestamp_revision is not None
    assert timestamp_revision.down_revision == "0006_create_leave_balance_summaries"
    assert employee_lifecycle_revision is not None
    assert employee_lifecycle_revision.down_revision == "0007_enforce_timestamp_not_null"


def test_alembic_upgrade_head_creates_current_model_schema(tmp_path: Path) -> None:
    database_path = tmp_path / "migration-smoke.sqlite3"
    database_url = f"sqlite+aiosqlite:///{database_path}"
    config = _alembic_config(database_url)
    model_tables = _current_model_tables()

    alembic_command.upgrade(config, "head")

    engine = create_engine(f"sqlite:///{database_path}")
    try:
        inspector = inspect(engine)
        migrated_tables = set(inspector.get_table_names())

        assert set(Base.metadata.tables) == set(model_tables)
        assert migrated_tables == set(model_tables) | {"alembic_version"}

        for table in model_tables.values():
            assert _database_column_signatures(
                inspector.get_columns(table.name)
            ) == _model_column_signatures(table)
            assert _database_index_signatures(
                inspector.get_indexes(table.name)
            ) == _model_index_signatures(table)
            assert _database_unique_constraint_signatures(
                inspector.get_unique_constraints(table.name)
            ) == _model_unique_constraint_signatures(table)
            assert _database_foreign_key_signatures(
                inspector.get_foreign_keys(table.name)
            ) == _model_foreign_key_signatures(table)
            assert _database_check_constraint_names(
                inspector.get_check_constraints(table.name)
            ) == _model_check_constraint_names(table)

        with engine.connect() as connection:
            current_revision = connection.execute(
                text("select version_num from alembic_version")
            ).scalar_one()

        assert current_revision == _script_directory().get_current_head()
    finally:
        engine.dispose()


def test_alembic_upgrade_head_has_no_current_model_drift(tmp_path: Path) -> None:
    database_path = tmp_path / "migration-metadata-smoke.sqlite3"
    database_url = f"sqlite+aiosqlite:///{database_path}"
    config = _alembic_config(database_url)

    alembic_command.upgrade(config, "head")

    engine = create_engine(f"sqlite:///{database_path}")
    try:
        with engine.connect() as connection:
            migration_context = MigrationContext.configure(
                connection,
                opts={"compare_type": _compare_type, "target_metadata": Base.metadata},
            )
            schema_diffs = compare_metadata(migration_context, Base.metadata)

        assert schema_diffs == []
    finally:
        engine.dispose()


def test_initial_tenant_migration_exists() -> None:
    migration = Path("backend/alembic/versions/0001_create_tenants.py")

    assert migration.exists()
    text = migration.read_text()
    assert "create_table" in text
    assert "tenants" in text
    assert "ck_tenants_status" in text


def test_initial_user_migration_exists() -> None:
    migration = Path("backend/alembic/versions/0002_create_users.py")

    assert migration.exists()
    text = migration.read_text()
    assert "create_table" in text
    assert "users" in text
    assert "uq_users_tenant_email" in text
    assert "ck_users_status" in text


def test_initial_employee_migration_exists() -> None:
    migration = Path("backend/alembic/versions/0003_create_employees.py")

    assert migration.exists()
    text = migration.read_text()
    assert "create_table" in text
    assert "employees" in text
    assert "uq_employees_tenant_employee_number" in text
    assert "ck_employees_status" in text


def test_initial_leave_request_migration_exists() -> None:
    migration = Path("backend/alembic/versions/0004_create_leave_requests.py")

    assert migration.exists()
    text = migration.read_text()
    assert "create_table" in text
    assert "leave_requests" in text
    assert "ck_leave_requests_status" in text
    assert "ix_leave_requests_tenant_employee_start_date" in text
    assert "ix_leave_requests_tenant_status_created_at" in text


def test_employee_date_order_migration_exists() -> None:
    migration = Path("backend/alembic/versions/0005_employee_date_order.py")

    assert migration.exists()
    text = migration.read_text()
    assert "ck_employees_date_order" in text
    assert "employment_end_date >= employment_start_date" in text


def test_leave_balance_summary_migration_exists() -> None:
    migration = Path("backend/alembic/versions/0006_create_leave_balance_summaries.py")

    assert migration.exists()
    text = migration.read_text()
    assert "create_table" in text
    assert "leave_balance_summaries" in text
    assert "uq_leave_balance_summaries_tenant_employee_type_period" in text
    assert "ix_leave_balance_summaries_tenant_employee_period" in text


def test_timestamp_not_null_migration_exists() -> None:
    migration = Path("backend/alembic/versions/0007_enforce_timestamp_not_null.py")

    assert migration.exists()
    text = migration.read_text()
    assert "TIMESTAMP_TABLES" in text
    assert "created_at" in text
    assert "updated_at" in text
    assert "nullable=False" in text


def test_employee_lifecycle_status_dates_migration_exists() -> None:
    migration = Path(
        "backend/alembic/versions/0008_employee_lifecycle_status_dates.py"
    )

    assert migration.exists()
    text = migration.read_text()
    assert "ck_employees_lifecycle_status_dates" in text
    assert "status = 'terminated'" in text
    assert "employment_end_date is not null" in text


def test_readme_documents_migration_commands() -> None:
    text = Path("README.md").read_text()

    for command in [
        "uv run alembic history",
        "uv run alembic heads",
        "uv run alembic current",
        "uv run alembic upgrade head",
        "uv run alembic revision --autogenerate",
    ]:
        assert command in text
