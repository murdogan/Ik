from pathlib import Path

import app.models  # noqa: F401
from alembic import command as alembic_command
from alembic.config import Config
from alembic.script import ScriptDirectory
from app.db.base import Base
from sqlalchemy import create_engine, inspect, text

ALEMBIC_INI = Path("alembic.ini")


def _alembic_config(database_url: str | None = None) -> Config:
    config = Config(str(ALEMBIC_INI))
    if database_url is not None:
        config.set_main_option("sqlalchemy.url", database_url)
    return config


def _script_directory() -> ScriptDirectory:
    return ScriptDirectory.from_config(_alembic_config())


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

    assert script.get_heads() == ["0005_employee_date_order"]
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


def test_alembic_upgrade_head_creates_current_model_schema(tmp_path: Path) -> None:
    database_path = tmp_path / "migration-smoke.sqlite3"
    database_url = f"sqlite+aiosqlite:///{database_path}"
    config = _alembic_config(database_url)

    alembic_command.upgrade(config, "head")

    engine = create_engine(f"sqlite:///{database_path}")
    try:
        inspector = inspect(engine)
        migrated_tables = set(inspector.get_table_names())

        assert set(Base.metadata.tables) <= migrated_tables

        for table in Base.metadata.sorted_tables:
            migrated_columns = {column["name"] for column in inspector.get_columns(table.name)}
            model_columns = {column.name for column in table.columns}

            assert model_columns <= migrated_columns

        with engine.connect() as connection:
            current_revision = connection.execute(
                text("select version_num from alembic_version")
            ).scalar_one()

        assert current_revision == _script_directory().get_current_head()
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
