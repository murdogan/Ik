import importlib
import pkgutil
import subprocess
import sys
from pathlib import Path

import app.models as model_package
import pytest
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
from sqlalchemy.exc import IntegrityError

ROOT = Path(__file__).resolve().parents[2]
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
            column["default"] is not None or column.get("computed") is not None,
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


def _assert_database_matches_current_model_schema(database_path: Path) -> None:
    model_tables = _current_model_tables()

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


def _run_alembic_upgrade_head_subprocess(
    database_url: str,
) -> subprocess.CompletedProcess[str]:
    command = (
        "from alembic import command\n"
        "from alembic.config import Config\n"
        "from sys import argv\n"
        "config = Config('alembic.ini')\n"
        "config.set_main_option('sqlalchemy.url', argv[1])\n"
        "command.upgrade(config, 'head')\n"
    )
    return subprocess.run(
        [sys.executable, "-c", command, database_url],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )


def _run_alembic_upgrade_head_offline_subprocess() -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head", "--sql"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )


def _run_alembic_p0e_downgrade_offline_subprocess() -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "alembic",
            "downgrade",
            (
                "0011_p0e_concurrency_idempotency_archive:"
                "0010_contract_tenant_relational_integrity"
            ),
            "--sql",
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )


def _run_alembic_f1a_downgrade_offline_subprocess() -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "alembic",
            "downgrade",
            "0013_tenant_settings:0012_p0f_query_performance",
            "--sql",
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )


def _run_alembic_f1c_upgrade_offline_subprocess() -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "alembic",
            "upgrade",
            "0013_tenant_settings:0014_f1c_postgresql_rls",
            "--sql",
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )


def _run_alembic_f1c_downgrade_offline_subprocess() -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "alembic",
            "downgrade",
            "0014_f1c_postgresql_rls:0013_tenant_settings",
            "--sql",
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )


def _run_alembic_f1d_upgrade_offline_subprocess() -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "alembic",
            "upgrade",
            "0014_f1c_postgresql_rls:0015_f1d_feature_flags",
            "--sql",
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )


def _run_alembic_f1d_downgrade_offline_subprocess() -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "alembic",
            "downgrade",
            "0015_f1d_feature_flags:0014_f1c_postgresql_rls",
            "--sql",
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )


def test_alembic_config_points_to_backend_migrations() -> None:
    config = _alembic_config()

    assert config.get_main_option("script_location") == "backend/alembic"


def test_alembic_uses_one_transaction_per_expand_contract_revision() -> None:
    env_text = Path("backend/alembic/env.py").read_text()

    assert env_text.count("transaction_per_migration=True") == 2


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
    tenant_integrity_expand_revision = script.get_revision(
        "0009_expand_tenant_relational_integrity"
    )
    tenant_integrity_contract_revision = script.get_revision(
        "0010_contract_tenant_relational_integrity"
    )
    p0e_revision = script.get_revision("0011_p0e_concurrency_idempotency_archive")
    p0f_revision = script.get_revision("0012_p0f_query_performance")
    tenant_settings_revision = script.get_revision("0013_tenant_settings")
    f1c_rls_revision = script.get_revision("0014_f1c_postgresql_rls")
    f1d_feature_revision = script.get_revision("0015_f1d_feature_flags")
    f2a_identity_revision = script.get_revision("0016_f2a_identity_activation")

    assert script.get_heads() == ["0016_f2a_identity_activation"]
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
    assert tenant_integrity_expand_revision is not None
    assert tenant_integrity_expand_revision.down_revision == (
        "0008_employee_lifecycle_status_dates"
    )
    assert tenant_integrity_contract_revision is not None
    assert tenant_integrity_contract_revision.down_revision == (
        "0009_expand_tenant_relational_integrity"
    )
    assert p0e_revision is not None
    assert p0e_revision.down_revision == "0010_contract_tenant_relational_integrity"
    assert p0f_revision is not None
    assert p0f_revision.down_revision == "0011_p0e_concurrency_idempotency_archive"
    assert tenant_settings_revision is not None
    assert tenant_settings_revision.down_revision == "0012_p0f_query_performance"
    assert f1c_rls_revision is not None
    assert f1c_rls_revision.down_revision == "0013_tenant_settings"
    assert f1d_feature_revision is not None
    assert f1d_feature_revision.down_revision == "0014_f1c_postgresql_rls"
    assert f2a_identity_revision is not None
    assert f2a_identity_revision.down_revision == "0015_f1d_feature_flags"


def test_alembic_upgrade_head_creates_current_model_schema(tmp_path: Path) -> None:
    database_path = tmp_path / "migration-smoke.sqlite3"
    database_url = f"sqlite+aiosqlite:///{database_path}"
    config = _alembic_config(database_url)

    alembic_command.upgrade(config, "head")

    _assert_database_matches_current_model_schema(database_path)


def test_alembic_upgrade_head_subprocess_creates_current_model_schema(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "migration-subprocess-smoke.sqlite3"
    database_url = f"sqlite+aiosqlite:///{database_path}"

    result = _run_alembic_upgrade_head_subprocess(database_url)

    assert result.returncode == 0, result.stderr or result.stdout
    _assert_database_matches_current_model_schema(database_path)


def test_alembic_offline_sql_renders_p0d_preflight_and_expand_contract() -> None:
    result = _run_alembic_upgrade_head_offline_subprocess()

    assert result.returncode == 0, result.stderr or result.stdout
    assert "tenant relational integrity preflight failed" in result.stdout
    assert "CREATE UNIQUE INDEX CONCURRENTLY" in result.stdout
    assert "NOT VALID" in result.stdout
    assert "VALIDATE CONSTRAINT" in result.stdout


def test_alembic_offline_p0e_downgrade_renders_retention_preflight() -> None:
    result = _run_alembic_p0e_downgrade_offline_subprocess()

    assert result.returncode == 0, result.stderr or result.stdout
    assert "DO $p0e_downgrade_preflight$" in result.stdout
    assert "P0E downgrade preflight failed" in result.stdout


def test_alembic_offline_f1a_downgrade_renders_settings_preflight() -> None:
    result = _run_alembic_f1a_downgrade_offline_subprocess()

    assert result.returncode == 0, result.stderr or result.stdout
    assert "DO $f1a_downgrade_preflight$" in result.stdout
    assert "F1A downgrade preflight failed" in result.stdout


def test_alembic_offline_f1c_upgrade_renders_roles_rls_policies_and_grants() -> None:
    result = _run_alembic_f1c_upgrade_offline_subprocess()

    assert result.returncode == 0, result.stderr or result.stdout
    for role_name in ("wealthy_falcon_app", "wealthy_falcon_platform"):
        assert f'CREATE ROLE "{role_name}"' in result.stdout
        assert f'ALTER ROLE "{role_name}"' in result.stdout
        assert "NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE" in result.stdout
        assert "NOINHERIT NOBYPASSRLS" in result.stdout
        assert (
            f"F1C role membership preflight failed: capability role {role_name}"
            in result.stdout
        )
    for table_name in (
        "tenants",
        "users",
        "employees",
        "leave_requests",
        "leave_balance_summaries",
        "command_idempotency",
        "tenant_settings",
    ):
        assert f'ALTER TABLE "{table_name}" ENABLE ROW LEVEL SECURITY' in result.stdout
        assert f'ALTER TABLE "{table_name}" FORCE ROW LEVEL SECURITY' in result.stdout
        assert f'ON "{table_name}" AS PERMISSIVE FOR ALL' in result.stdout
    assert "nullif(current_setting('app.tenant_id', true), '')::uuid" in result.stdout
    assert 'TO "wealthy_falcon_app"' in result.stdout
    assert result.stdout.count('TO "wealthy_falcon_platform" USING (true)') == 1
    assert (
        'ON "tenant_settings" AS PERMISSIVE FOR INSERT '
        'TO "wealthy_falcon_platform" WITH CHECK (true)'
    ) in result.stdout
    assert 'REVOKE ALL PRIVILEGES ON TABLE "employees" FROM "wealthy_falcon_platform"' in (
        result.stdout
    )
    assert (
        'REVOKE ALL PRIVILEGES ("id", "tenant_id", "employee_number"'
        in result.stdout
    )
    assert 'REVOKE ALL PRIVILEGES ON SCHEMA "public" FROM "wealthy_falcon_app"' in result.stdout
    assert 'GRANT SELECT, INSERT, UPDATE ON TABLE "employees"' in result.stdout
    assert 'GRANT SELECT ON TABLE "tenants" TO "wealthy_falcon_app"' in result.stdout
    assert (
        'GRANT UPDATE ("locale", "timezone", "updated_at") ON TABLE "tenants" '
        'TO "wealthy_falcon_app"'
    ) in result.stdout
    assert (
        'GRANT INSERT ON TABLE "tenant_settings" TO "wealthy_falcon_platform"'
        in result.stdout
    )
    assert "GRANT DELETE" not in result.stdout


def test_alembic_offline_f1c_downgrade_removes_local_security_without_dropping_roles() -> None:
    result = _run_alembic_f1c_downgrade_offline_subprocess()

    assert result.returncode == 0, result.stderr or result.stdout
    assert 'DROP POLICY IF EXISTS "tenant_isolation_app"' in result.stdout
    assert 'DROP POLICY IF EXISTS "platform_operations"' in result.stdout
    assert 'DROP POLICY IF EXISTS "platform_provision_settings"' in result.stdout
    assert "NO FORCE ROW LEVEL SECURITY" in result.stdout
    assert "DISABLE ROW LEVEL SECURITY" in result.stdout
    assert 'REVOKE USAGE ON SCHEMA "public"' in result.stdout
    assert "DROP ROLE" not in result.stdout


def test_alembic_offline_f1d_upgrade_renders_feature_rls_and_narrow_grants() -> None:
    result = _run_alembic_f1d_upgrade_offline_subprocess()

    assert result.returncode == 0, result.stderr or result.stdout
    assert "ADD COLUMN active_employee_limit INTEGER" in result.stdout
    assert "ck_tenants_active_employee_limit_positive" in result.stdout
    assert "active_employee_limit between 1 and 1000000" in result.stdout
    assert "CREATE TABLE tenant_feature_flags" in result.stdout
    assert "ck_tenant_feature_flags_key" in result.stdout
    assert "ck_tenant_feature_flags_enabled" in result.stdout
    assert result.stdout.count("insert into tenant_feature_flags") == 7
    assert (
        'REVOKE ALL PRIVILEGES ON TABLE "tenant_feature_flags" FROM PUBLIC'
        in result.stdout
    )
    assert (
        'REVOKE ALL PRIVILEGES ON TABLE "tenant_feature_flags" '
        'FROM "wealthy_falcon_app"'
    ) in result.stdout
    assert (
        'REVOKE ALL PRIVILEGES ON TABLE "tenant_feature_flags" '
        'FROM "wealthy_falcon_platform"'
    ) in result.stdout
    assert 'ALTER TABLE "tenants" NO FORCE ROW LEVEL SECURITY' in result.stdout
    assert 'ALTER TABLE "tenants" DISABLE ROW LEVEL SECURITY' in result.stdout
    assert 'ALTER TABLE "tenants" ENABLE ROW LEVEL SECURITY' in result.stdout
    assert 'ALTER TABLE "tenants" FORCE ROW LEVEL SECURITY' in result.stdout
    assert 'ALTER TABLE "tenant_feature_flags" ENABLE ROW LEVEL SECURITY' in result.stdout
    assert 'ALTER TABLE "tenant_feature_flags" FORCE ROW LEVEL SECURITY' in result.stdout
    assert (
        'ON "tenant_feature_flags" AS PERMISSIVE FOR ALL TO "wealthy_falcon_app"'
        in result.stdout
    )
    assert (
        'CREATE POLICY "platform_feature_operations" ON "tenant_feature_flags"'
        in result.stdout
    )
    assert (
        'GRANT SELECT ON TABLE "tenant_feature_flags" TO "wealthy_falcon_app"'
        in result.stdout
    )
    assert (
        'GRANT SELECT, INSERT, UPDATE ON TABLE "tenant_feature_flags" '
        'TO "wealthy_falcon_platform"'
    ) in result.stdout
    assert "GRANT DELETE" not in result.stdout


def test_alembic_offline_f1d_downgrade_guards_state_and_removes_local_security() -> None:
    result = _run_alembic_f1d_downgrade_offline_subprocess()

    assert result.returncode == 0, result.stderr or result.stdout
    assert "DO $f1d_downgrade_preflight$" in result.stdout
    assert "F1D downgrade preflight failed" in result.stdout
    assert 'ALTER TABLE "tenant_feature_flags" NO FORCE ROW LEVEL SECURITY' in result.stdout
    assert 'ALTER TABLE "tenant_feature_flags" DISABLE ROW LEVEL SECURITY' in result.stdout
    assert 'ALTER TABLE "tenants" NO FORCE ROW LEVEL SECURITY' in result.stdout
    assert 'ALTER TABLE "tenants" DISABLE ROW LEVEL SECURITY' in result.stdout
    assert 'ALTER TABLE "tenants" ENABLE ROW LEVEL SECURITY' in result.stdout
    assert 'ALTER TABLE "tenants" FORCE ROW LEVEL SECURITY' in result.stdout
    assert (
        'REVOKE SELECT, INSERT, UPDATE ON TABLE "tenant_feature_flags" '
        'FROM "wealthy_falcon_platform"'
    ) in result.stdout
    assert 'DROP POLICY IF EXISTS "platform_feature_operations"' in result.stdout
    assert 'DROP POLICY IF EXISTS "tenant_isolation_app"' in result.stdout
    assert "DROP TABLE tenant_feature_flags" in result.stdout
    assert "DROP COLUMN active_employee_limit" in result.stdout


def test_alembic_upgrade_head_has_no_current_model_drift(tmp_path: Path) -> None:
    database_path = tmp_path / "migration-metadata-smoke.sqlite3"
    database_url = f"sqlite+aiosqlite:///{database_path}"
    config = _alembic_config(database_url)
    _current_model_tables()

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


def test_sqlite_f1c_security_migration_is_a_schema_noop(tmp_path: Path) -> None:
    database_path = tmp_path / "migration-f1c-sqlite-noop.sqlite3"
    database_url = f"sqlite+aiosqlite:///{database_path}"
    config = _alembic_config(database_url)
    alembic_command.upgrade(config, "0013_tenant_settings")

    engine = create_engine(f"sqlite:///{database_path}")
    try:
        before_tables = set(inspect(engine).get_table_names())

        alembic_command.upgrade(config, "0014_f1c_postgresql_rls")

        assert set(inspect(engine).get_table_names()) == before_tables
        with engine.connect() as connection:
            assert connection.scalar(text("select version_num from alembic_version")) == (
                "0014_f1c_postgresql_rls"
            )

        alembic_command.downgrade(config, "0013_tenant_settings")

        assert set(inspect(engine).get_table_names()) == before_tables
    finally:
        engine.dispose()


def test_sqlite_f1d_feature_defaults_limits_and_constraints_round_trip(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "migration-f1d-round-trip.sqlite3"
    database_url = f"sqlite+aiosqlite:///{database_path}"
    config = _alembic_config(database_url)
    tenant_id = "11111111aaaa41118111111111111111"
    alembic_command.upgrade(config, "0014_f1c_postgresql_rls")

    engine = create_engine(f"sqlite:///{database_path}")
    try:
        with engine.begin() as connection:
            connection.execute(
                text(
                    "insert into tenants ("
                    "id, slug, name, status, plan_code, data_region, locale, timezone, "
                    "created_at, updated_at"
                    ") values ("
                    ":id, 'f1d-backfill', 'F1D Backfill', 'active', 'core', 'tr-1', "
                    "'tr-TR', 'Europe/Istanbul', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP"
                    ")"
                ),
                {"id": tenant_id},
            )

        alembic_command.upgrade(config, "head")
        with engine.connect() as connection:
            feature_rows = dict(
                list(
                    connection.execute(
                        text(
                            "select key, enabled from tenant_feature_flags "
                            "where tenant_id = :tenant_id"
                        ),
                        {"tenant_id": tenant_id},
                    ).tuples()
                )
            )
            configured_limit = connection.scalar(
                text(
                    "select active_employee_limit from tenants where id = :tenant_id"
                ),
                {"tenant_id": tenant_id},
            )

        assert feature_rows == {
            "organization": 0,
            "employees": 1,
            "documents": 0,
            "leave": 1,
            "self_service": 0,
            "reporting": 1,
            "notifications": 0,
        }
        assert configured_limit is None
        assert "tenant_feature_flags" in inspect(engine).get_table_names()
        assert "active_employee_limit" in {
            column["name"] for column in inspect(engine).get_columns("tenants")
        }

        with pytest.raises(IntegrityError):
            with engine.begin() as connection:
                connection.execute(
                    text(
                        "insert into tenant_feature_flags ("
                        "tenant_id, key, enabled, created_at, updated_at"
                        ") values ("
                        ":tenant_id, 'payroll', false, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP"
                        ")"
                    ),
                    {"tenant_id": tenant_id},
                )
        with pytest.raises(IntegrityError):
            with engine.begin() as connection:
                connection.execute(
                    text(
                        "update tenant_feature_flags set enabled = 2 "
                        "where tenant_id = :tenant_id and key = 'organization'"
                    ),
                    {"tenant_id": tenant_id},
                )
        for invalid_limit in (0, 1_000_001):
            with pytest.raises(IntegrityError):
                with engine.begin() as connection:
                    connection.execute(
                        text(
                            "update tenants set active_employee_limit = :limit "
                            "where id = :tenant_id"
                        ),
                        {"limit": invalid_limit, "tenant_id": tenant_id},
                    )

        alembic_command.downgrade(config, "0014_f1c_postgresql_rls")
        assert "tenant_feature_flags" not in inspect(engine).get_table_names()
        assert "active_employee_limit" not in {
            column["name"] for column in inspect(engine).get_columns("tenants")
        }

        alembic_command.upgrade(config, "head")
        with engine.connect() as connection:
            assert connection.scalar(
                text(
                    "select count(*) from tenant_feature_flags "
                    "where tenant_id = :tenant_id"
                ),
                {"tenant_id": tenant_id},
            ) == len(feature_rows)
    finally:
        engine.dispose()


@pytest.mark.parametrize(
    ("retained_write", "expected_counts", "remediation"),
    [
        (
            "update tenant_feature_flags set enabled = true "
            "where key = 'organization'",
            "feature_overrides=1, configured_active_employee_limits=0",
            "update tenant_feature_flags set enabled = false "
            "where key = 'organization'",
        ),
        (
            "update tenants set active_employee_limit = 250",
            "feature_overrides=0, configured_active_employee_limits=1",
            "update tenants set active_employee_limit = null",
        ),
    ],
)
def test_sqlite_f1d_downgrade_refuses_rollout_or_limit_state(
    tmp_path: Path,
    retained_write: str,
    expected_counts: str,
    remediation: str,
) -> None:
    database_path = tmp_path / "migration-f1d-retention-guard.sqlite3"
    database_url = f"sqlite+aiosqlite:///{database_path}"
    config = _alembic_config(database_url)
    tenant_id = "11111111aaaa41118111111111111111"
    alembic_command.upgrade(config, "0014_f1c_postgresql_rls")

    engine = create_engine(f"sqlite:///{database_path}")
    try:
        with engine.begin() as connection:
            connection.execute(
                text(
                    "insert into tenants ("
                    "id, slug, name, status, plan_code, data_region, locale, timezone, "
                    "created_at, updated_at"
                    ") values ("
                    ":id, 'f1d-retained', 'F1D Retained', 'active', 'core', 'tr-1', "
                    "'tr-TR', 'Europe/Istanbul', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP"
                    ")"
                ),
                {"id": tenant_id},
            )
        alembic_command.upgrade(config, "head")
        with engine.begin() as connection:
            connection.execute(text(retained_write))

        with pytest.raises(
            RuntimeError,
            match=f"F1D downgrade preflight failed.*{expected_counts}",
        ):
            alembic_command.downgrade(config, "0014_f1c_postgresql_rls")

        with engine.connect() as connection:
            assert connection.scalar(text("select version_num from alembic_version")) == (
                "0015_f1d_feature_flags"
            )
            assert connection.scalar(
                text("select count(*) from tenant_feature_flags")
            ) == 7

        with engine.begin() as connection:
            connection.execute(text(remediation))
        alembic_command.downgrade(config, "0014_f1c_postgresql_rls")
        assert "tenant_feature_flags" not in inspect(engine).get_table_names()
    finally:
        engine.dispose()


def test_sqlite_p0d_downgrade_reupgrade_preserves_head_schema(tmp_path: Path) -> None:
    database_path = tmp_path / "migration-p0d-round-trip.sqlite3"
    database_url = f"sqlite+aiosqlite:///{database_path}"
    config = _alembic_config(database_url)

    alembic_command.upgrade(config, "head")
    alembic_command.downgrade(config, "0008_employee_lifecycle_status_dates")
    alembic_command.upgrade(config, "head")

    _assert_database_matches_current_model_schema(database_path)


def test_sqlite_tenant_settings_migration_backfills_and_round_trips(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "migration-tenant-settings-round-trip.sqlite3"
    database_url = f"sqlite+aiosqlite:///{database_path}"
    config = _alembic_config(database_url)
    tenant_id = "11111111aaaa41118111111111111111"

    alembic_command.upgrade(config, "0012_p0f_query_performance")
    engine = create_engine(f"sqlite:///{database_path}")
    try:
        with engine.begin() as connection:
            connection.execute(
                text(
                    "insert into tenants ("
                    "id, slug, name, status, plan_code, data_region, locale, timezone, "
                    "created_at, updated_at"
                    ") values ("
                    ":id, 'settings-backfill', 'Settings Backfill', 'active', "
                    "'core', 'tr-1', 'tr-TR', 'Europe/Istanbul', "
                    "CURRENT_TIMESTAMP, CURRENT_TIMESTAMP"
                    ")"
                ),
                {"id": tenant_id},
            )

        alembic_command.upgrade(config, "head")
        with engine.connect() as connection:
            settings = connection.execute(
                text(
                    "select week_start_day, date_format, time_format "
                    "from tenant_settings where tenant_id = :tenant_id"
                ),
                {"tenant_id": tenant_id},
            ).one()
        assert settings == ("monday", "DD.MM.YYYY", "24h")

        alembic_command.downgrade(config, "0012_p0f_query_performance")
        assert "tenant_settings" not in inspect(engine).get_table_names()

        alembic_command.upgrade(config, "head")
        with engine.connect() as connection:
            settings_count = connection.scalar(
                text(
                    "select count(*) from tenant_settings "
                    "where tenant_id = :tenant_id"
                ),
                {"tenant_id": tenant_id},
            )
        assert settings_count == 1
    finally:
        engine.dispose()


def test_tenant_settings_downgrade_refuses_custom_values(tmp_path: Path) -> None:
    database_path = tmp_path / "migration-tenant-settings-retention-guard.sqlite3"
    database_url = f"sqlite+aiosqlite:///{database_path}"
    config = _alembic_config(database_url)
    tenant_id = "11111111aaaa41118111111111111111"
    alembic_command.upgrade(config, "head")

    engine = create_engine(f"sqlite:///{database_path}")
    try:
        with engine.begin() as connection:
            connection.execute(
                text(
                    "insert into tenants ("
                    "id, slug, name, status, plan_code, data_region, locale, timezone, "
                    "created_at, updated_at"
                    ") values ("
                    ":id, 'settings-guard', 'Settings Guard', 'active', 'core', 'tr-1', "
                    "'tr-TR', 'Europe/Istanbul', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP"
                    ")"
                ),
                {"id": tenant_id},
            )
            connection.execute(
                text(
                    "insert into tenant_settings ("
                    "tenant_id, week_start_day, date_format, time_format, "
                    "created_at, updated_at"
                    ") values ("
                    ":tenant_id, 'sunday', 'DD.MM.YYYY', '24h', "
                    "CURRENT_TIMESTAMP, CURRENT_TIMESTAMP"
                    ")"
                ),
                {"tenant_id": tenant_id},
            )

        with pytest.raises(
            RuntimeError,
            match="F1A downgrade preflight failed.*custom_tenant_settings=1",
        ):
            alembic_command.downgrade(config, "0012_p0f_query_performance")

        with engine.connect() as connection:
            revision = connection.scalar(text("select version_num from alembic_version"))
            week_start_day = connection.scalar(
                text(
                    "select week_start_day from tenant_settings "
                    "where tenant_id = :tenant_id"
                ),
                {"tenant_id": tenant_id},
            )
        assert revision == "0013_tenant_settings"
        assert week_start_day == "sunday"
    finally:
        engine.dispose()


def test_p0e_downgrade_refuses_to_discard_retained_state(tmp_path: Path) -> None:
    database_path = tmp_path / "migration-p0e-retention-guard.sqlite3"
    database_url = f"sqlite+aiosqlite:///{database_path}"
    config = _alembic_config(database_url)
    alembic_command.upgrade(config, "head")

    engine = create_engine(f"sqlite:///{database_path}")
    tenant_id = "11111111aaaa41118111111111111111"
    employee_id = "22222222bbbb42228222222222222222"
    receipt_id = "33333333cccc43338333333333333333"
    try:
        with engine.begin() as connection:
            connection.execute(
                text(
                    "insert into tenants ("
                    "id, slug, name, status, plan_code, data_region, locale, timezone, "
                    "created_at, updated_at"
                    ") values ("
                    ":id, 'p0e-guard', 'P0E Guard', 'active', 'core', 'tr-1', "
                    "'tr-TR', 'Europe/Istanbul', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP"
                    ")"
                ),
                {"id": tenant_id},
            )
            connection.execute(
                text(
                    "insert into employees ("
                    "id, tenant_id, employee_number, first_name, last_name, status, "
                    "employment_start_date, archived_at, created_at, updated_at"
                    ") values ("
                    ":id, :tenant_id, 'P0E-GUARD', 'Guard', 'Employee', 'active', "
                    "'2026-07-01', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP"
                    ")"
                ),
                {"id": employee_id, "tenant_id": tenant_id},
            )
            connection.execute(
                text(
                    "insert into command_idempotency ("
                    "id, tenant_id, idempotency_key, command_name, request_fingerprint, "
                    "created_at"
                    ") values ("
                    ":id, :tenant_id, 'guard-key', 'employees.create', :fingerprint, "
                    "CURRENT_TIMESTAMP"
                    ")"
                ),
                {
                    "id": receipt_id,
                    "tenant_id": tenant_id,
                    "fingerprint": "0" * 64,
                },
            )

        with pytest.raises(
            RuntimeError,
            match=(
                "P0E downgrade preflight failed.*archived_employees=1, "
                "command_idempotency=1"
            ),
        ):
            alembic_command.downgrade(
                config,
                "0010_contract_tenant_relational_integrity",
            )

        with engine.connect() as connection:
            revision = connection.scalar(text("select version_num from alembic_version"))
            archived_at = connection.scalar(
                text("select archived_at from employees where id = :id"),
                {"id": employee_id},
            )
            receipt_count = connection.scalar(
                text("select count(*) from command_idempotency")
            )
        assert revision == "0011_p0e_concurrency_idempotency_archive"
        assert archived_at is not None
        assert receipt_count == 1

        with engine.begin() as connection:
            connection.execute(text("delete from command_idempotency"))
            connection.execute(
                text("update employees set archived_at = null where id = :id"),
                {"id": employee_id},
            )
        alembic_command.downgrade(
            config,
            "0010_contract_tenant_relational_integrity",
        )
        with engine.connect() as connection:
            revision = connection.scalar(text("select version_num from alembic_version"))
        assert revision == "0010_contract_tenant_relational_integrity"
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


def test_tenant_relational_integrity_migrations_use_expand_contract_sequence() -> None:
    expand_migration = Path(
        "backend/alembic/versions/0009_expand_tenant_relational_integrity.py"
    )
    contract_migration = Path(
        "backend/alembic/versions/0010_contract_tenant_relational_integrity.py"
    )

    assert expand_migration.exists()
    assert contract_migration.exists()
    expand_text = expand_migration.read_text()
    contract_text = contract_migration.read_text()
    assert "TENANT_RELATIONSHIP_PREFLIGHT_SQL" in expand_text
    assert "CREATE UNIQUE INDEX CONCURRENTLY" in expand_text
    assert "NOT VALID" in expand_text
    assert "0009_expand_tenant_relational_integrity" in contract_text
    assert "VALIDATE CONSTRAINT" in contract_text


def test_p0e_concurrency_idempotency_archive_migration_exists() -> None:
    migration = Path(
        "backend/alembic/versions/0011_p0e_concurrency_idempotency_archive.py"
    )

    assert migration.exists()
    text = migration.read_text()
    assert "command_idempotency" in text
    assert "uq_command_idempotency_tenant_key" in text
    assert "archived_at" in text
    assert 'ondelete="RESTRICT"' in text


def test_p0f_query_performance_migration_exists() -> None:
    migration = Path("backend/alembic/versions/0012_p0f_query_performance.py")

    assert migration.exists()
    text = migration.read_text()
    assert "pg_trgm" in text
    assert "ix_employees_employee_number_trgm" in text
    assert "ix_employees_email_trgm" in text
    assert "department_normalized" in text
    assert "ix_employees_tenant_department_normalized" in text
    assert "ix_leave_requests_tenant_created_cursor" in text


def test_tenant_settings_migration_exists() -> None:
    migration = Path("backend/alembic/versions/0013_tenant_settings.py")

    assert migration.exists()
    text = migration.read_text()
    assert "tenant_settings" in text
    assert "fk_tenant_settings_tenant_id_tenants" in text
    assert "ck_tenant_settings_week_start_day" in text
    assert "ck_tenant_settings_date_format" in text
    assert "ck_tenant_settings_time_format" in text
    assert "CURRENT_TIMESTAMP from tenants" in text


def test_f1c_postgresql_rls_migration_freezes_complete_security_inventory() -> None:
    migration = Path("backend/alembic/versions/0014_f1c_postgresql_rls.py")
    helper = Path("backend/app/platform/db/rls_migration.py")

    assert migration.exists()
    assert helper.exists()
    migration_text = migration.read_text()
    helper_text = helper.read_text()
    for table_name in (
        "users",
        "employees",
        "leave_requests",
        "leave_balance_summaries",
        "command_idempotency",
        "tenant_settings",
    ):
        assert f'"{table_name}"' in migration_text
    assert '"tenants"' in migration_text
    assert "TENANT_OWNED_TABLES" in migration_text
    assert "_ROW_SECURITY_TABLE_COLUMNS" in migration_text
    assert "APPLICATION_TABLE_PRIVILEGES" in migration_text
    assert "APPLICATION_COLUMN_PRIVILEGES" in migration_text
    assert "PLATFORM_TABLE_PRIVILEGES" in migration_text
    assert "TENANT_APPLICATION_ROLE" in migration_text
    assert "PLATFORM_APPLICATION_ROLE" in migration_text
    assert "nullif(current_setting('app.tenant_id', true), '')::uuid" in helper_text


def test_f1d_feature_flag_migration_freezes_catalog_limits_and_security() -> None:
    migration = Path("backend/alembic/versions/0015_f1d_feature_flags.py")

    assert migration.exists()
    migration_text = migration.read_text()
    assert "0014_f1c_postgresql_rls" in migration_text
    assert "tenant_feature_flags" in migration_text
    assert "active_employee_limit" in migration_text
    assert "ck_tenants_active_employee_limit_positive" in migration_text
    assert "ck_tenant_feature_flags_key" in migration_text
    assert "ck_tenant_feature_flags_enabled" in migration_text
    assert "fk_tenant_feature_flags_tenant_id_tenants" in migration_text
    assert "_FEATURE_DEFAULTS" in migration_text
    assert "enable_forced_row_security" in migration_text
    assert "TENANT_APPLICATION_ROLE" in migration_text
    assert "PLATFORM_APPLICATION_ROLE" in migration_text
    assert "F1D downgrade preflight failed" in migration_text


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
