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
from app.platform.authorization import PERMISSIONS, ROLE_PERMISSION_CODES, ROLES
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

_P3A_TENANT_A_ID = "a1000000000040008000000000000001"
_P3A_TENANT_B_ID = "a1000000000040008000000000000002"
_P3A_CANONICAL_USER_ID = "a2000000000040008000000000000001"
_P3A_SECOND_USER_ID = "a2000000000040008000000000000002"
_P3A_SHARED_EMAIL_NORMALIZED = "shared.identity@p3a.test"
_P3A_PASSWORD_HASH = "$argon2id$v=19$m=65536,t=3,p=4$cDNhLXRlc3Q$credential-a"
_P3A_OTHER_PASSWORD_HASH = (
    "$argon2id$v=19$m=65536,t=3,p=4$cDNhLXRlc3Q$credential-b"
)


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


def _run_alembic_f2d_downgrade_offline_subprocess() -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "alembic",
            "downgrade",
            "0019_f2d_rbac:0018_f2c_user_administration",
            "--sql",
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )


def _run_alembic_p3a_upgrade_offline_subprocess() -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "alembic",
            "upgrade",
            "0021_f2f_user_insert_grant:0022_p3a_identity_memberships",
            "--sql",
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )


def _run_alembic_p3a_downgrade_offline_subprocess() -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "alembic",
            "downgrade",
            "0022_p3a_identity_memberships:0021_f2f_user_insert_grant",
            "--sql",
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )


def _run_alembic_p3b_upgrade_offline_subprocess() -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "alembic",
            "upgrade",
            "0022_p3a_identity_memberships:0023_p3b_email_first_login",
            "--sql",
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )


def _run_alembic_p3g_upgrade_offline_subprocess() -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "alembic",
            "upgrade",
            "0027_p3f_legal_entities_branches:0028_p3g_department_hierarchy",
            "--sql",
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )


def _run_alembic_p3g_downgrade_offline_subprocess() -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "alembic",
            "downgrade",
            "0028_p3g_department_hierarchy:0027_p3f_legal_entities_branches",
            "--sql",
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )


def _run_alembic_p3h_upgrade_offline_subprocess() -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "alembic",
            "upgrade",
            "0028_p3g_department_hierarchy:0029_p3h_position_catalog",
            "--sql",
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )


def _run_alembic_p3h_downgrade_offline_subprocess() -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "alembic",
            "downgrade",
            "0029_p3h_position_catalog:0028_p3g_department_hierarchy",
            "--sql",
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )


def _run_alembic_p3i_upgrade_offline_subprocess() -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "alembic",
            "upgrade",
            "0029_p3h_position_catalog:0030_p3i_employee_assignments",
            "--sql",
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )


def _run_alembic_p3i_downgrade_offline_subprocess() -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "alembic",
            "downgrade",
            "0030_p3i_employee_assignments:0029_p3h_position_catalog",
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
    f2b_session_revision = script.get_revision("0017_f2b_secure_sessions")
    f2c_user_administration_revision = script.get_revision(
        "0018_f2c_user_administration"
    )
    f2d_rbac_revision = script.get_revision("0019_f2d_rbac")
    f2e_audit_revision = script.get_revision("0020_f2e_audit_events")
    f2f_user_insert_grant_revision = script.get_revision(
        "0021_f2f_user_insert_grant"
    )
    p3a_identity_memberships_revision = script.get_revision(
        "0022_p3a_identity_memberships"
    )
    p3b_email_first_login_revision = script.get_revision(
        "0023_p3b_email_first_login"
    )
    p3c_organization_selection_revision = script.get_revision(
        "0024_p3c_organization_selection"
    )
    p3d_platform_authentication_revision = script.get_revision(
        "0025_p3d_platform_authentication"
    )
    p3e_identity_checkpoint_revision = script.get_revision(
        "0026_p3e_identity_checkpoint"
    )
    p3f_organization_revision = script.get_revision(
        "0027_p3f_legal_entities_branches"
    )
    p3g_department_revision = script.get_revision(
        "0028_p3g_department_hierarchy"
    )
    p3h_position_revision = script.get_revision("0029_p3h_position_catalog")
    p3i_assignment_revision = script.get_revision("0030_p3i_employee_assignments")
    p3k_auth_boundary_revision = script.get_revision(
        "0031_p3k_legacy_tenant_auth_boundary"
    )

    assert script.get_heads() == ["0031_p3k_legacy_tenant_auth_boundary"]
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
    assert f2b_session_revision is not None
    assert f2b_session_revision.down_revision == "0016_f2a_identity_activation"
    assert f2c_user_administration_revision is not None
    assert f2c_user_administration_revision.down_revision == "0017_f2b_secure_sessions"
    assert f2d_rbac_revision is not None
    assert f2d_rbac_revision.down_revision == "0018_f2c_user_administration"
    assert f2e_audit_revision is not None
    assert f2e_audit_revision.down_revision == "0019_f2d_rbac"
    assert f2f_user_insert_grant_revision is not None
    assert f2f_user_insert_grant_revision.down_revision == "0020_f2e_audit_events"
    assert p3a_identity_memberships_revision is not None
    assert p3a_identity_memberships_revision.down_revision == (
        "0021_f2f_user_insert_grant"
    )
    assert p3b_email_first_login_revision is not None
    assert p3b_email_first_login_revision.down_revision == (
        "0022_p3a_identity_memberships"
    )
    assert p3c_organization_selection_revision is not None
    assert p3c_organization_selection_revision.down_revision == (
        "0023_p3b_email_first_login"
    )
    assert p3d_platform_authentication_revision is not None
    assert p3d_platform_authentication_revision.down_revision == (
        "0024_p3c_organization_selection"
    )
    assert p3e_identity_checkpoint_revision is not None
    assert p3e_identity_checkpoint_revision.down_revision == (
        "0025_p3d_platform_authentication"
    )
    assert p3f_organization_revision is not None
    assert p3f_organization_revision.down_revision == (
        "0026_p3e_identity_checkpoint"
    )
    assert p3g_department_revision is not None
    assert p3g_department_revision.down_revision == (
        "0027_p3f_legal_entities_branches"
    )
    assert p3h_position_revision is not None
    assert p3h_position_revision.down_revision == "0028_p3g_department_hierarchy"
    assert p3i_assignment_revision is not None
    assert p3i_assignment_revision.down_revision == "0029_p3h_position_catalog"
    assert p3k_auth_boundary_revision is not None
    assert p3k_auth_boundary_revision.down_revision == "0030_p3i_employee_assignments"


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


def test_sqlite_p3i_backfills_legacy_employee_strings_without_contracting_them(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "migration-p3i-legacy-backfill.sqlite3"
    database_url = f"sqlite+aiosqlite:///{database_path}"
    config = _alembic_config(database_url)
    alembic_command.upgrade(config, "0029_p3h_position_catalog")
    engine = create_engine(f"sqlite:///{database_path}")
    tenant_id = "d1000000000040008000000000000001"
    department_id = "d2000000000040008000000000000001"
    position_id = "d3000000000040008000000000000001"
    employee_ids = tuple(
        f"d400000000004000800000000000000{suffix}" for suffix in range(1, 5)
    )
    try:
        with engine.begin() as connection:
            connection.execute(
                text(
                    "insert into tenants ("
                    "id, slug, name, status, plan_code, data_region, locale, timezone, "
                    "created_at, updated_at"
                    ") values ("
                    ":id, 'p3i-backfill', 'P3I Backfill', 'active', 'core', 'tr-1', "
                    "'tr-TR', 'Europe/Istanbul', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP"
                    ")"
                ),
                {"id": tenant_id},
            )
            connection.execute(
                text(
                    "insert into legal_entities ("
                    "id, tenant_id, code, name, registered_name, timezone, status, is_default, "
                    "created_at, updated_at"
                    ") values ("
                    ":id, :id, 'DEFAULT', 'P3I Backfill', 'P3I Backfill', "
                    "'Europe/Istanbul', 'active', true, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP"
                    ")"
                ),
                {"id": tenant_id},
            )
            connection.execute(
                text(
                    "insert into departments ("
                    "id, tenant_id, parent_id, code, name, status, archived_at, "
                    "created_at, updated_at"
                    ") values ("
                    ":id, :tenant_id, null, 'ENG', 'Engineering', 'active', null, "
                    "CURRENT_TIMESTAMP, CURRENT_TIMESTAMP"
                    ")"
                ),
                {"id": department_id, "tenant_id": tenant_id},
            )
            connection.execute(
                text(
                    "insert into positions ("
                    "id, tenant_id, code, title, status, archived_at, created_at, updated_at"
                    ") values ("
                    ":id, :tenant_id, 'DEV', 'Developer', 'active', null, "
                    "CURRENT_TIMESTAMP, CURRENT_TIMESTAMP"
                    ")"
                ),
                {"id": position_id, "tenant_id": tenant_id},
            )
            connection.execute(
                text(
                    "insert into employees ("
                    "id, tenant_id, employee_number, first_name, last_name, department, "
                    "position, status, employment_start_date, employment_end_date, archived_at"
                    ", created_at, updated_at"
                    ") values "
                    "(:active_id, :tenant_id, 'P3I-001', 'Ada', 'Active', "
                    "' engineering ', ' developer ', 'active', '2025-01-01', null, null, "
                    "CURRENT_TIMESTAMP, CURRENT_TIMESTAMP), "
                    "(:leave_id, :tenant_id, 'P3I-002', 'Bora', 'Leave', "
                    "null, '  ', 'on_leave', '2025-02-01', null, null, "
                    "CURRENT_TIMESTAMP, CURRENT_TIMESTAMP), "
                    "(:terminated_id, :tenant_id, 'P3I-003', 'Cem', 'Terminated', "
                    "'ENGINEERING', 'Developer', 'terminated', '2025-03-01', "
                    "'2026-06-30', null, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP), "
                    "(:archived_id, :tenant_id, 'P3I-004', 'Derya', 'Archived', "
                    "'People', 'Partner', 'active', '2025-04-01', null, CURRENT_TIMESTAMP, "
                    "CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
                ),
                {
                    "tenant_id": tenant_id,
                    "active_id": employee_ids[0],
                    "leave_id": employee_ids[1],
                    "terminated_id": employee_ids[2],
                    "archived_id": employee_ids[3],
                },
            )

        alembic_command.upgrade(config, "head")

        with engine.connect() as connection:
            assignments = connection.execute(
                text(
                    "select employee.employee_number, department.id, department.name, "
                    "position.id, position.title, assignment.effective_from, "
                    "assignment.effective_to, employee.department, employee.position "
                    "from employee_assignments as assignment "
                    "join employees as employee on employee.tenant_id = assignment.tenant_id "
                    "and employee.id = assignment.employee_id "
                    "join departments as department "
                    "on department.tenant_id = assignment.tenant_id "
                    "and department.id = assignment.department_id "
                    "join positions as position on position.tenant_id = assignment.tenant_id "
                    "and position.id = assignment.position_id "
                    "order by employee.employee_number"
                )
            ).all()
            branch = connection.execute(
                text(
                    "select code, name, status, legal_entity_id from branches "
                    "where tenant_id = :tenant_id"
                ),
                {"tenant_id": tenant_id},
            ).one()

        assert len(assignments) == 4
        assert assignments[0] == (
            "P3I-001",
            department_id,
            "Engineering",
            position_id,
            "Developer",
            "2025-01-01",
            None,
            " engineering ",
            " developer ",
        )
        assert assignments[1][2:5:2] == ("Unspecified", "Unspecified")
        assert assignments[2][1] == department_id
        assert assignments[2][3] == position_id
        assert assignments[2][6] == "2026-07-01"
        assert assignments[3][2:5:2] == ("People", "Partner")
        assert branch == ("LEGACY", "Legacy / Unspecified", "active", tenant_id)
    finally:
        engine.dispose()


def test_alembic_offline_sql_renders_p0d_preflight_and_expand_contract() -> None:
    result = _run_alembic_upgrade_head_offline_subprocess()

    assert result.returncode == 0, result.stderr or result.stdout
    assert "tenant relational integrity preflight failed" in result.stdout
    assert "CREATE UNIQUE INDEX CONCURRENTLY" in result.stdout
    assert "NOT VALID" in result.stdout
    assert "VALIDATE CONSTRAINT" in result.stdout
    f2d_backfill = result.stdout.index("insert into user_roles")
    assert result.stdout.rfind(
        'ALTER TABLE "users" NO FORCE ROW LEVEL SECURITY',
        0,
        f2d_backfill,
    ) >= 0
    assert result.stdout.index(
        'ALTER TABLE "users" FORCE ROW LEVEL SECURITY',
        f2d_backfill,
    ) > f2d_backfill


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


def test_alembic_offline_f2d_downgrade_renders_authorization_preflight() -> None:
    result = _run_alembic_f2d_downgrade_offline_subprocess()

    assert result.returncode == 0, result.stderr or result.stdout
    assert "DO $f2d_rbac_downgrade_preflight$" in result.stdout
    assert "F2D downgrade preflight failed" in result.stdout


def test_alembic_offline_p3a_upgrade_renders_backfill_guards_before_writes() -> None:
    result = _run_alembic_p3a_upgrade_offline_subprocess()

    assert result.returncode == 0, result.stderr or result.stdout
    assert "DO $p3a_identity_backfill_preflight$" in result.stdout
    assert "P3A identity backfill preflight failed" in result.stdout
    assert (
        "conflicting_password_identities=%, blank_normalized_emails=%"
        in result.stdout
    )
    assert "DO $p3a_identity_backfill_verification$" in result.stdout
    assert "P3A identity backfill verification failed" in result.stdout
    preflight_position = result.stdout.index("DO $p3a_identity_backfill_preflight$")
    identity_table_position = result.stdout.index("CREATE TABLE identities")
    identity_backfill_position = result.stdout.index("insert into identities")
    verification_position = result.stdout.index(
        "DO $p3a_identity_backfill_verification$"
    )
    assert preflight_position < identity_table_position < identity_backfill_position
    assert identity_backfill_position < verification_position
    assert "insert into tenant_memberships" in result.stdout
    assert "insert into membership_roles" in result.stdout


def test_alembic_offline_p3a_downgrade_guards_projection_before_drops() -> None:
    result = _run_alembic_p3a_downgrade_offline_subprocess()

    assert result.returncode == 0, result.stderr or result.stdout
    assert "DO $p3a_downgrade_preflight$" in result.stdout
    assert (
        "P3A downgrade preflight failed: identity_drift=%," in result.stdout
    )
    preflight_position = result.stdout.index("DO $p3a_downgrade_preflight$")
    first_drop_position = result.stdout.index("DROP TABLE membership_roles")
    assert preflight_position < first_drop_position
    assert result.stdout.index("DROP TABLE tenant_memberships") > first_drop_position
    assert result.stdout.index("DROP TABLE identities") > first_drop_position


def test_alembic_offline_p3b_renders_narrow_authentication_boundary() -> None:
    result = _run_alembic_p3b_upgrade_offline_subprocess()

    assert result.returncode == 0, result.stderr or result.stdout
    assert "CREATE TABLE organization_selection_transactions" in result.stdout
    assert "CREATE TABLE organization_selection_choices" in result.stdout
    assert "CREATE TABLE authentication_rate_limit_buckets" in result.stdout
    assert 'CREATE ROLE "wealthy_falcon_authentication"' in result.stdout
    assert 'CREATE POLICY "authentication_identity_read"' in result.stdout
    assert (
        'REVOKE ALL PRIVILEGES ON ALL TABLES IN SCHEMA "public" '
        'FROM "wealthy_falcon_authentication"'
        in result.stdout
    )
    assert "DO $p3b_revoke_stale_authentication_columns$" in result.stdout
    assert (
        'GRANT SELECT ("id", "email_normalized", "status", "password_hash") '
        'ON TABLE "identities" TO "wealthy_falcon_authentication"'
        in result.stdout
    )
    assert (
        'GRANT SELECT ("id", "tenant_id", "identity_id", "legacy_user_id", "status") '
        'ON TABLE "tenant_memberships" TO "wealthy_falcon_authentication"'
        in result.stdout
    )
    assert "metadata = '{\"failure_reason\":\"authentication_failed\"}'::jsonb" in (
        result.stdout
    )
    assert (
        'GRANT INSERT ON TABLE "organization_selection_transactions" '
        'TO "wealthy_falcon_authentication"'
    ) in result.stdout
    assert (
        'REVOKE ALL PRIVILEGES ON TABLE "organization_selection_transactions" '
        'FROM "wealthy_falcon_app"'
    ) in result.stdout
    assert "CREATE FUNCTION public.sync_current_tenant_identity_membership" in result.stdout
    assert "SECURITY DEFINER" in result.stdout
    assert 'OWNER TO "wealthy_falcon_identity_projection"' in result.stdout


def test_alembic_offline_p3g_renders_department_integrity_rls_and_acl() -> None:
    result = _run_alembic_p3g_upgrade_offline_subprocess()

    assert result.returncode == 0, result.stderr or result.stdout
    assert "CREATE TABLE department_hierarchy_write_fences" in result.stdout
    assert "ck_department_hierarchy_write_fences_version" in result.stdout
    assert (
        'ALTER TABLE "department_hierarchy_write_fences" ENABLE ROW LEVEL SECURITY'
        in result.stdout
    )
    assert (
        'ALTER TABLE "department_hierarchy_write_fences" FORCE ROW LEVEL SECURITY'
        in result.stdout
    )
    assert (
        'GRANT SELECT, INSERT ON TABLE "department_hierarchy_write_fences" '
        'TO "wealthy_falcon_app"'
    ) in result.stdout
    assert (
        'GRANT UPDATE ("version") ON TABLE "department_hierarchy_write_fences" '
        'TO "wealthy_falcon_app"'
    ) in result.stdout
    assert "CREATE TABLE departments" in result.stdout
    for constraint_name in (
        "ck_departments_status",
        "ck_departments_archive_state",
        "ck_departments_parent_not_self",
        "uq_departments_tenant_code_normalized",
        "fk_departments_tenant_parent_id_departments",
    ):
        assert constraint_name in result.stdout
    assert 'ALTER TABLE "departments" ENABLE ROW LEVEL SECURITY' in result.stdout
    assert 'ALTER TABLE "departments" FORCE ROW LEVEL SECURITY' in result.stdout
    assert (
        'CREATE POLICY "tenant_isolation_app" ON "departments" '
        'AS PERMISSIVE FOR ALL TO "wealthy_falcon_app"'
    ) in result.stdout
    assert (
        'GRANT SELECT, INSERT ON TABLE "departments" TO "wealthy_falcon_app"'
        in result.stdout
    )
    assert (
        'GRANT UPDATE ("name", "parent_id", "status", "archived_at", "updated_at") '
        'ON TABLE "departments" TO "wealthy_falcon_app"'
    ) in result.stdout
    assert "CREATE FUNCTION public.enforce_department_hierarchy_integrity()" in (
        result.stdout
    )
    assert "SELECT tenants.id INTO locked_tenant_id" in result.stdout
    assert "INSERT INTO public.department_hierarchy_write_fences AS fence" in result.stdout
    assert "DO UPDATE SET version = fence.version + 1" in result.stdout
    assert "WITH RECURSIVE ancestors(id, parent_id)" in result.stdout
    assert "CONSTRAINT = 'ck_departments_acyclic'" in result.stdout
    assert "CREATE FUNCTION public.validate_department_hierarchy_acyclic()" in (
        result.stdout
    )
    assert result.stdout.count("REFERENCING NEW TABLE AS new_departments") == 2
    assert "WITH RECURSIVE hierarchy_walk(" in result.stdout
    assert "GRANT DELETE" not in result.stdout


def test_alembic_offline_p3g_downgrade_guards_retained_history() -> None:
    result = _run_alembic_p3g_downgrade_offline_subprocess()

    assert result.returncode == 0, result.stderr or result.stdout
    assert "DO $p3g_downgrade_preflight$" in result.stdout
    assert "P3G downgrade preflight failed" in result.stdout
    preflight_position = result.stdout.index("DO $p3g_downgrade_preflight$")
    first_drop_position = result.stdout.index(
        "DROP TRIGGER IF EXISTS trg_departments_acyclic_after_update"
    )
    assert preflight_position < first_drop_position
    assert "DROP FUNCTION IF EXISTS public.validate_department_hierarchy_acyclic()" in (
        result.stdout
    )
    assert "DROP TABLE departments" in result.stdout
    assert "DROP TABLE department_hierarchy_write_fences" in result.stdout


def test_alembic_offline_p3h_renders_position_indexes_rls_acl_and_trigger() -> None:
    result = _run_alembic_p3h_upgrade_offline_subprocess()

    assert result.returncode == 0, result.stderr or result.stdout
    assert "CREATE TABLE positions" in result.stdout
    for constraint_name in (
        "ck_positions_status",
        "ck_positions_archive_state",
        "ck_positions_code_normalized_not_empty",
        "ck_positions_title_normalized_not_empty",
        "uq_positions_tenant_id_id",
        "uq_positions_tenant_code_normalized",
        "fk_positions_tenant_id_tenants",
    ):
        assert constraint_name in result.stdout
    for index_name in (
        "ix_positions_tenant_code_cursor",
        "ix_positions_tenant_status_code_cursor",
        "ix_positions_code_normalized_trgm",
        "ix_positions_title_normalized_trgm",
    ):
        assert index_name in result.stdout
    assert "gin_trgm_ops" in result.stdout
    assert 'ALTER TABLE "positions" ENABLE ROW LEVEL SECURITY' in result.stdout
    assert 'ALTER TABLE "positions" FORCE ROW LEVEL SECURITY' in result.stdout
    assert (
        'CREATE POLICY "tenant_isolation_app" ON "positions" '
        'AS PERMISSIVE FOR ALL TO "wealthy_falcon_app"'
    ) in result.stdout
    assert (
        'GRANT SELECT, INSERT ON TABLE "positions" TO "wealthy_falcon_app"'
        in result.stdout
    )
    assert (
        'GRANT UPDATE ("title", "status", "archived_at", "updated_at") '
        'ON TABLE "positions" TO "wealthy_falcon_app"'
    ) in result.stdout
    assert "CREATE FUNCTION public.enforce_position_catalog_integrity()" in (
        result.stdout
    )
    assert "CONSTRAINT = 'ck_positions_immutable_identity_code'" in result.stdout
    assert "CONSTRAINT = 'ck_positions_archived_terminal'" in result.stdout
    assert "GRANT DELETE" not in result.stdout


def test_alembic_offline_p3h_downgrade_guards_retained_position_history() -> None:
    result = _run_alembic_p3h_downgrade_offline_subprocess()

    assert result.returncode == 0, result.stderr or result.stdout
    assert "DO $p3h_downgrade_preflight$" in result.stdout
    assert "P3H downgrade preflight failed" in result.stdout
    preflight_position = result.stdout.index("DO $p3h_downgrade_preflight$")
    trigger_drop_position = result.stdout.index(
        "DROP TRIGGER IF EXISTS trg_positions_catalog_integrity"
    )
    assert preflight_position < trigger_drop_position
    assert "DROP FUNCTION IF EXISTS public.enforce_position_catalog_integrity()" in (
        result.stdout
    )
    assert "DROP TABLE positions" in result.stdout


def test_alembic_offline_p3i_renders_assignment_backfill_rls_acl_and_trigger() -> None:
    result = _run_alembic_p3i_upgrade_offline_subprocess()

    assert result.returncode == 0, result.stderr or result.stdout
    assert "CREATE TABLE employee_assignments" in result.stdout
    for constraint_name in (
        "ck_employee_assignments_effective_range",
        "fk_employee_assignments_tenant_employee_id_employees",
        "fk_employee_assignments_tenant_legal_entity_id_legal_entities",
        "fk_employee_assignments_tenant_branch_id_branches",
        "fk_employee_assignments_tenant_department_id_departments",
        "fk_employee_assignments_tenant_position_id_positions",
        "uq_employee_assignments_tenant_supersedes_assignment_id",
    ):
        assert constraint_name in result.stdout
    assert "INSERT INTO public.employee_assignments" in result.stdout
    assert "P3I legacy employee backfill" in result.stdout
    assert (
        'ALTER TABLE "employee_assignments" ENABLE ROW LEVEL SECURITY'
        in result.stdout
    )
    assert (
        'ALTER TABLE "employee_assignments" FORCE ROW LEVEL SECURITY'
        in result.stdout
    )
    assert (
        'GRANT SELECT, INSERT ON TABLE "employee_assignments" '
        'TO "wealthy_falcon_app"'
    ) in result.stdout
    assert (
        'GRANT UPDATE ("effective_to", "updated_at") '
        'ON TABLE "employee_assignments" TO "wealthy_falcon_app"'
    ) in result.stdout
    assert "CREATE FUNCTION public.enforce_employee_assignment_integrity()" in (
        result.stdout
    )
    assert "current_user <> 'wealthy_falcon_app'" in result.stdout
    assert "CONSTRAINT = 'ck_employee_assignments_runtime_insert_open'" in (
        result.stdout
    )
    assert "GRANT DELETE" not in result.stdout


def test_alembic_offline_p3i_downgrade_guards_retained_assignment_history() -> None:
    result = _run_alembic_p3i_downgrade_offline_subprocess()

    assert result.returncode == 0, result.stderr or result.stdout
    assert "DO $p3i_downgrade_preflight$" in result.stdout
    assert "P3I downgrade preflight failed" in result.stdout
    preflight_position = result.stdout.index("DO $p3i_downgrade_preflight$")
    trigger_drop_position = result.stdout.index(
        "DROP TRIGGER IF EXISTS trg_employee_assignments_integrity"
    )
    assert preflight_position < trigger_drop_position
    assert (
        "DROP FUNCTION IF EXISTS public.enforce_employee_assignment_integrity()"
        in result.stdout
    )
    assert "DROP TABLE employee_assignments" in result.stdout


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


def test_sqlite_f2d_seeds_catalog_and_backfills_legacy_user_roles(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "migration-f2d-rbac-backfill.sqlite3"
    database_url = f"sqlite+aiosqlite:///{database_path}"
    config = _alembic_config(database_url)
    tenant_id = "d1000000000040008000000000000001"
    admin_id = "d1100000000040008000000000000001"
    employee_id = "d1100000000040008000000000000002"

    alembic_command.upgrade(config, "0018_f2c_user_administration")
    engine = create_engine(f"sqlite:///{database_path}")
    try:
        with engine.begin() as connection:
            connection.execute(
                text(
                    "insert into tenants ("
                    "id, slug, name, status, plan_code, data_region, locale, timezone, "
                    "created_at, updated_at"
                    ") values ("
                    ":id, 'f2d-backfill', 'F2D Backfill', 'active', 'core', 'tr-1', "
                    "'en-US', 'UTC', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP"
                    ")"
                ),
                {"id": tenant_id},
            )
            connection.execute(
                text(
                    "insert into users ("
                    "id, tenant_id, email, full_name, status, can_invite_users, "
                    "created_at, updated_at"
                    ") values ("
                    ":admin_id, :tenant_id, 'admin@f2d.test', 'Legacy Admin', 'active', true, "
                    "CURRENT_TIMESTAMP, CURRENT_TIMESTAMP"
                    "), ("
                    ":employee_id, :tenant_id, 'employee@f2d.test', 'Legacy Employee', "
                    "'active', false, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP"
                    ")"
                ),
                {
                    "tenant_id": tenant_id,
                    "admin_id": admin_id,
                    "employee_id": employee_id,
                },
            )

        alembic_command.upgrade(config, "head")

        with engine.connect() as connection:
            persisted_roles = set(
                connection.execute(text("select code, scope_type from roles")).tuples()
            )
            persisted_permissions = set(
                connection.scalars(text("select code from permissions"))
            )
            persisted_grants: dict[str, set[str]] = {}
            for role_code, permission_code in connection.execute(
                text(
                    "select roles.code, permissions.code "
                    "from role_permissions "
                    "join roles on roles.id = role_permissions.role_id "
                    "join permissions on permissions.id = role_permissions.permission_id"
                )
            ).tuples():
                persisted_grants.setdefault(role_code, set()).add(permission_code)
            assignments = dict(
                list(
                    connection.execute(
                        text(
                            "select users.email, roles.code from user_roles "
                            "join users on users.tenant_id = user_roles.tenant_id "
                            "and users.id = user_roles.user_id "
                            "join roles on roles.id = user_roles.role_id "
                            "where user_roles.active = true"
                        )
                    ).tuples()
                )
            )
            permission_versions = set(
                connection.scalars(text("select permission_version from users"))
            )

        assert persisted_roles == {
            (role.code, role.scope_type.value) for role in ROLES
        }
        assert persisted_permissions == {permission.code for permission in PERMISSIONS}
        assert persisted_grants == {
            role_code: set(permission_codes)
            for role_code, permission_codes in ROLE_PERMISSION_CODES.items()
        }
        assert assignments == {
            "admin@f2d.test": "tenant_admin",
            "employee@f2d.test": "employee",
        }
        assert permission_versions == {1}

        # Return to F2D while the P3A projection is still reproducible. The assertions below
        # intentionally create legacy authorization drift and exercise F2D's own downgrade guard.
        alembic_command.downgrade(config, "0019_f2d_rbac")

        with pytest.raises(IntegrityError):
            with engine.begin() as connection:
                connection.execute(text("update users set permission_version = 0"))

        with engine.begin() as connection:
            connection.execute(
                text(
                    "update users set permission_version = 2 "
                    "where email = 'employee@f2d.test'"
                )
            )
        with pytest.raises(
            RuntimeError,
            match="F2D downgrade preflight failed: changed_authorization_users=1",
        ):
            alembic_command.downgrade(config, "0018_f2c_user_administration")
        with engine.connect() as connection:
            assert connection.scalar(text("select version_num from alembic_version")) == (
                "0019_f2d_rbac"
            )

        with engine.begin() as connection:
            connection.execute(
                text(
                    "update users set permission_version = 1 "
                    "where email = 'employee@f2d.test'"
                )
            )
        alembic_command.downgrade(config, "0018_f2c_user_administration")
        assert "user_roles" not in inspect(engine).get_table_names()
    finally:
        engine.dispose()


def _seed_p3a_legacy_multi_membership_fixture(
    engine,
    *,
    second_password_hash: str | None = None,
) -> None:
    with engine.begin() as connection:
        connection.execute(
            text(
                "insert into tenants ("
                "id, slug, name, status, plan_code, data_region, locale, timezone, "
                "created_at, updated_at"
                ") values ("
                ":tenant_a_id, 'p3a-tenant-a', 'P3A Tenant A', 'active', 'core', "
                "'tr-1', 'en-US', 'UTC', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP"
                "), ("
                ":tenant_b_id, 'p3a-tenant-b', 'P3A Tenant B', 'active', 'core', "
                "'tr-1', 'en-US', 'UTC', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP"
                ")"
            ),
            {
                "tenant_a_id": _P3A_TENANT_A_ID,
                "tenant_b_id": _P3A_TENANT_B_ID,
            },
        )
        connection.execute(
            text(
                "insert into users ("
                "id, tenant_id, email, full_name, status, password_hash, "
                "can_invite_users, permission_version, created_at, updated_at"
                ") values ("
                ":canonical_id, :tenant_a_id, ' Shared.Identity@P3A.Test ', "
                "'Canonical Tenant Admin', 'active', :password_hash, true, 2, "
                "'2026-07-01 09:00:00', '2026-07-01 10:00:00'"
                "), ("
                ":second_id, :tenant_b_id, 'shared.identity@p3a.test', "
                "'Second Tenant Employee', :second_status, :second_password_hash, false, 3, "
                "'2026-07-02 09:00:00', '2026-07-03 10:00:00'"
                ")"
            ),
            {
                "canonical_id": _P3A_CANONICAL_USER_ID,
                "second_id": _P3A_SECOND_USER_ID,
                "tenant_a_id": _P3A_TENANT_A_ID,
                "tenant_b_id": _P3A_TENANT_B_ID,
                "password_hash": _P3A_PASSWORD_HASH,
                "second_password_hash": second_password_hash,
                "second_status": "active" if second_password_hash else "invited",
            },
        )
        role_ids = dict(
            list(
                connection.execute(
                    text(
                        "select code, id from roles "
                        "where code in ('tenant_admin', 'employee')"
                    )
                ).tuples()
            )
        )
        connection.execute(
            text(
                "insert into user_roles ("
                "tenant_id, user_id, role_id, role_scope_type, active, created_at, updated_at"
                ") values ("
                ":tenant_a_id, :canonical_id, :tenant_admin_id, 'tenant', true, "
                "'2026-07-01 09:00:00', '2026-07-01 10:00:00'"
                "), ("
                ":tenant_b_id, :second_id, :employee_id, 'tenant', true, "
                "'2026-07-02 09:00:00', '2026-07-03 10:00:00'"
                ")"
            ),
            {
                "tenant_a_id": _P3A_TENANT_A_ID,
                "tenant_b_id": _P3A_TENANT_B_ID,
                "canonical_id": _P3A_CANONICAL_USER_ID,
                "second_id": _P3A_SECOND_USER_ID,
                "tenant_admin_id": role_ids["tenant_admin"],
                "employee_id": role_ids["employee"],
            },
        )


def _p3a_projection_snapshot(connection) -> dict[str, tuple[tuple[object, ...], ...]]:
    return {
        "identities": tuple(
            connection.execute(
                text(
                    "select id, email, email_normalized, status, password_hash, "
                    "created_at, updated_at from identities order by id"
                )
            ).tuples()
        ),
        "memberships": tuple(
            connection.execute(
                text(
                    "select id, tenant_id, identity_id, legacy_user_id, full_name, status, "
                    "permission_version, created_at, updated_at "
                    "from tenant_memberships order by tenant_id, id"
                )
            ).tuples()
        ),
        "roles": tuple(
            connection.execute(
                text(
                    "select membership_roles.tenant_id, membership_roles.membership_id, "
                    "roles.code, membership_roles.active, membership_roles.created_at, "
                    "membership_roles.updated_at from membership_roles "
                    "join roles on roles.id = membership_roles.role_id "
                    "order by membership_roles.tenant_id, membership_roles.membership_id, "
                    "roles.code"
                )
            ).tuples()
        ),
    }


def test_sqlite_p3a_backfills_one_identity_two_memberships_and_copies_roles(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "migration-p3a-multi-membership.sqlite3"
    database_url = f"sqlite+aiosqlite:///{database_path}"
    config = _alembic_config(database_url)
    alembic_command.upgrade(config, "0021_f2f_user_insert_grant")
    engine = create_engine(f"sqlite:///{database_path}")
    try:
        _seed_p3a_legacy_multi_membership_fixture(engine)

        alembic_command.upgrade(config, "head")

        with engine.connect() as connection:
            snapshot = _p3a_projection_snapshot(connection)
            legacy_users = tuple(
                connection.execute(
                    text(
                        "select id, tenant_id, status, password_hash, permission_version "
                        "from users order by id"
                    )
                ).tuples()
            )

        assert snapshot["identities"] == (
            (
                _P3A_CANONICAL_USER_ID,
                " Shared.Identity@P3A.Test ",
                _P3A_SHARED_EMAIL_NORMALIZED,
                "active",
                _P3A_PASSWORD_HASH,
                "2026-07-01 09:00:00",
                "2026-07-03 10:00:00",
            ),
        )
        assert snapshot["memberships"] == (
            (
                _P3A_CANONICAL_USER_ID,
                _P3A_TENANT_A_ID,
                _P3A_CANONICAL_USER_ID,
                _P3A_CANONICAL_USER_ID,
                "Canonical Tenant Admin",
                "active",
                2,
                "2026-07-01 09:00:00",
                "2026-07-01 10:00:00",
            ),
            (
                _P3A_SECOND_USER_ID,
                _P3A_TENANT_B_ID,
                _P3A_CANONICAL_USER_ID,
                _P3A_SECOND_USER_ID,
                "Second Tenant Employee",
                "invited",
                3,
                "2026-07-02 09:00:00",
                "2026-07-03 10:00:00",
            ),
        )
        assert tuple((row[0], row[1], row[2], row[3]) for row in snapshot["roles"]) == (
            (_P3A_TENANT_A_ID, _P3A_CANONICAL_USER_ID, "tenant_admin", 1),
            (_P3A_TENANT_B_ID, _P3A_SECOND_USER_ID, "employee", 1),
        )
        assert legacy_users == (
            (
                _P3A_CANONICAL_USER_ID,
                _P3A_TENANT_A_ID,
                "active",
                _P3A_PASSWORD_HASH,
                2,
            ),
            (_P3A_SECOND_USER_ID, _P3A_TENANT_B_ID, "invited", None, 3),
        )
    finally:
        engine.dispose()


def test_sqlite_p3a_demo_admin_legacy_id_survives_as_identity_and_membership(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "migration-p3a-demo-admin.sqlite3"
    database_url = f"sqlite+aiosqlite:///{database_path}"
    config = _alembic_config(database_url)
    demo_tenant_id = "f1000000000040008000000000000001"
    demo_admin_id = "f2000000000040008000000000000001"
    alembic_command.upgrade(config, "0021_f2f_user_insert_grant")
    engine = create_engine(f"sqlite:///{database_path}")
    try:
        with engine.begin() as connection:
            connection.execute(
                text(
                    "insert into tenants ("
                    "id, slug, name, status, plan_code, data_region, locale, timezone, "
                    "created_at, updated_at"
                    ") values ("
                    ":tenant_id, 'wealthy-falcon-demo', 'Wealthy Falcon HR Demo', "
                    "'active', 'core', 'tr-1', 'en-US', 'Europe/Istanbul', "
                    "CURRENT_TIMESTAMP, CURRENT_TIMESTAMP"
                    ")"
                ),
                {"tenant_id": demo_tenant_id},
            )
            connection.execute(
                text(
                    "insert into users ("
                    "id, tenant_id, email, full_name, status, password_hash, "
                    "can_invite_users, permission_version, created_at, updated_at"
                    ") values ("
                    ":admin_id, :tenant_id, 'admin@wealthyfalcon.demo', 'Maya Stone', "
                    "'active', null, true, 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP"
                    ")"
                ),
                {"admin_id": demo_admin_id, "tenant_id": demo_tenant_id},
            )

        alembic_command.upgrade(config, "head")

        with engine.connect() as connection:
            identity = connection.execute(
                text(
                    "select id, email, status, password_hash from identities "
                    "where id = :admin_id"
                ),
                {"admin_id": demo_admin_id},
            ).one()
            membership = connection.execute(
                text(
                    "select id, tenant_id, identity_id, legacy_user_id, full_name, status "
                    "from tenant_memberships where id = :admin_id"
                ),
                {"admin_id": demo_admin_id},
            ).one()
            legacy_user_id = connection.scalar(
                text("select id from users where id = :admin_id"),
                {"admin_id": demo_admin_id},
            )

        assert identity == (
            demo_admin_id,
            "admin@wealthyfalcon.demo",
            "pending",
            None,
        )
        assert membership == (
            demo_admin_id,
            demo_tenant_id,
            demo_admin_id,
            demo_admin_id,
            "Maya Stone",
            "active",
        )
        assert legacy_user_id == demo_admin_id
    finally:
        engine.dispose()


def test_sqlite_p3a_enforces_global_identity_and_tenant_membership_uniqueness(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "migration-p3a-uniqueness.sqlite3"
    database_url = f"sqlite+aiosqlite:///{database_path}"
    config = _alembic_config(database_url)
    alembic_command.upgrade(config, "0021_f2f_user_insert_grant")
    engine = create_engine(f"sqlite:///{database_path}")
    try:
        _seed_p3a_legacy_multi_membership_fixture(engine)
        alembic_command.upgrade(config, "head")

        fresh_engine = create_engine(f"sqlite:///{database_path}")
        try:
            fresh_inspector = inspect(fresh_engine)
            identity_unique_constraints = {
                constraint["name"]
                for constraint in fresh_inspector.get_unique_constraints("identities")
            }
            membership_unique_constraints = {
                constraint["name"]
                for constraint in fresh_inspector.get_unique_constraints(
                    "tenant_memberships"
                )
            }
        finally:
            fresh_engine.dispose()
        assert identity_unique_constraints == {"uq_identities_email_normalized"}
        assert membership_unique_constraints == {
            "uq_tenant_memberships_tenant_id_id",
            "uq_tenant_memberships_tenant_identity",
            "uq_tenant_memberships_tenant_legacy_user",
        }

        for invalid_identity_update in (
            "update identities set password_hash = null "
            "where id = :identity_id",
            "update identities set status = 'pending' "
            "where id = :identity_id",
        ):
            with pytest.raises(IntegrityError):
                with engine.begin() as connection:
                    connection.execute(
                        text(invalid_identity_update),
                        {"identity_id": _P3A_CANONICAL_USER_ID},
                    )

        for invalid_membership_update in (
            "update tenant_memberships set permission_version = 0 "
            "where id = :membership_id",
            "update tenant_memberships set status = 'suspended' "
            "where id = :membership_id",
        ):
            with pytest.raises(IntegrityError):
                with engine.begin() as connection:
                    connection.execute(
                        text(invalid_membership_update),
                        {"membership_id": _P3A_CANONICAL_USER_ID},
                    )

        with pytest.raises(IntegrityError):
            with engine.begin() as connection:
                connection.execute(
                    text(
                        "insert into identities (id, email, status) values ("
                        "'a2000000000040008000000000000099', "
                        "' SHARED.IDENTITY@P3A.TEST ', 'pending'"
                        ")"
                    )
                )

        duplicate_membership_id = "a2000000000040008000000000000098"
        with pytest.raises(IntegrityError):
            with engine.begin() as connection:
                connection.execute(
                    text(
                        "insert into users ("
                        "id, tenant_id, email, full_name, status, permission_version, "
                        "created_at, updated_at"
                        ") values ("
                        ":id, :tenant_id, 'other-membership@p3a.test', "
                        "'Other Membership', 'invited', 1, "
                        "CURRENT_TIMESTAMP, CURRENT_TIMESTAMP"
                        ")"
                    ),
                    {
                        "id": duplicate_membership_id,
                        "tenant_id": _P3A_TENANT_A_ID,
                    },
                )
                connection.execute(
                    text(
                        "insert into tenant_memberships ("
                        "id, tenant_id, identity_id, legacy_user_id, full_name, status, "
                        "permission_version"
                        ") values ("
                        ":id, :tenant_id, :identity_id, :id, 'Other Membership', "
                        "'invited', 1"
                        ")"
                    ),
                    {
                        "id": duplicate_membership_id,
                        "tenant_id": _P3A_TENANT_A_ID,
                        "identity_id": _P3A_CANONICAL_USER_ID,
                    },
                )
    finally:
        engine.dispose()


def test_sqlite_p3a_conflicting_passwords_refuse_atomically(tmp_path: Path) -> None:
    database_path = tmp_path / "migration-p3a-password-conflict.sqlite3"
    database_url = f"sqlite+aiosqlite:///{database_path}"
    config = _alembic_config(database_url)
    alembic_command.upgrade(config, "0021_f2f_user_insert_grant")
    engine = create_engine(f"sqlite:///{database_path}")
    try:
        _seed_p3a_legacy_multi_membership_fixture(
            engine,
            second_password_hash=_P3A_OTHER_PASSWORD_HASH,
        )

        with pytest.raises(
            RuntimeError,
            match=(
                "P3A identity backfill preflight failed: "
                "conflicting_password_identities=1, blank_normalized_emails=0"
            ),
        ):
            alembic_command.upgrade(config, "head")

        with engine.connect() as connection:
            revision = connection.scalar(text("select version_num from alembic_version"))
            hashes = tuple(
                connection.scalars(text("select password_hash from users order by id"))
            )
        assert revision == "0021_f2f_user_insert_grant"
        assert not {
            "identities",
            "tenant_memberships",
            "membership_roles",
        } & set(inspect(engine).get_table_names())
        assert hashes == (_P3A_PASSWORD_HASH, _P3A_OTHER_PASSWORD_HASH)
    finally:
        engine.dispose()


def test_sqlite_p3a_downgrade_refuses_new_legacy_password_conflict(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "migration-p3a-downgrade-password-conflict.sqlite3"
    database_url = f"sqlite+aiosqlite:///{database_path}"
    config = _alembic_config(database_url)
    alembic_command.upgrade(config, "0021_f2f_user_insert_grant")
    engine = create_engine(f"sqlite:///{database_path}")
    try:
        _seed_p3a_legacy_multi_membership_fixture(engine)
        alembic_command.upgrade(config, "head")
        with engine.begin() as connection:
            connection.execute(
                text(
                    "update users set password_hash = :password_hash "
                    "where id = :user_id"
                ),
                {
                    "password_hash": "$argon2id$v=19$m=65536,t=3,p=4$000$lower",
                    "user_id": _P3A_SECOND_USER_ID,
                },
            )

        with pytest.raises(
            RuntimeError,
            match=(
                "P3A downgrade preflight failed: identity_drift=0, "
                "membership_drift=0, role_drift=0, "
                "conflicting_password_identities=1, blank_normalized_emails=0"
            ),
        ):
            alembic_command.downgrade(config, "0021_f2f_user_insert_grant")

        with engine.connect() as connection:
            assert connection.scalar(text("select version_num from alembic_version")) == (
                "0022_p3a_identity_memberships"
            )

        with engine.begin() as connection:
            connection.execute(
                text("update users set password_hash = null where id = :user_id"),
                {"user_id": _P3A_SECOND_USER_ID},
            )
        alembic_command.downgrade(config, "0021_f2f_user_insert_grant")
    finally:
        engine.dispose()


def test_sqlite_p3a_safe_downgrade_reupgrade_is_deterministic(tmp_path: Path) -> None:
    database_path = tmp_path / "migration-p3a-safe-round-trip.sqlite3"
    database_url = f"sqlite+aiosqlite:///{database_path}"
    config = _alembic_config(database_url)
    alembic_command.upgrade(config, "0021_f2f_user_insert_grant")
    engine = create_engine(f"sqlite:///{database_path}")
    try:
        _seed_p3a_legacy_multi_membership_fixture(engine)
        alembic_command.upgrade(config, "head")
        with engine.connect() as connection:
            first_projection = _p3a_projection_snapshot(connection)

        alembic_command.downgrade(config, "0021_f2f_user_insert_grant")
        assert not {
            "identities",
            "tenant_memberships",
            "membership_roles",
        } & set(inspect(engine).get_table_names())
        with engine.connect() as connection:
            assert connection.scalar(text("select count(*) from users")) == 2
            assert connection.scalar(text("select count(*) from user_roles")) == 2

        alembic_command.upgrade(config, "head")
        with engine.connect() as connection:
            second_projection = _p3a_projection_snapshot(connection)
            revision = connection.scalar(text("select version_num from alembic_version"))

        assert second_projection == first_projection
        assert revision == "0031_p3k_legacy_tenant_auth_boundary"
    finally:
        engine.dispose()


def test_sqlite_p3a_downgrade_refuses_drift_until_projection_is_repaired(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "migration-p3a-downgrade-guard.sqlite3"
    database_url = f"sqlite+aiosqlite:///{database_path}"
    config = _alembic_config(database_url)
    alembic_command.upgrade(config, "0021_f2f_user_insert_grant")
    engine = create_engine(f"sqlite:///{database_path}")
    try:
        _seed_p3a_legacy_multi_membership_fixture(engine)
        alembic_command.upgrade(config, "head")
        with engine.begin() as connection:
            connection.execute(
                text(
                    "update tenant_memberships set full_name = 'Canonical Membership Drift' "
                    "where id = :membership_id"
                ),
                {"membership_id": _P3A_CANONICAL_USER_ID},
            )

        with pytest.raises(
            RuntimeError,
            match=(
                "P3A downgrade preflight failed: identity_drift=0, "
                "membership_drift=1, role_drift=0"
            ),
        ):
            alembic_command.downgrade(config, "0021_f2f_user_insert_grant")

        with engine.connect() as connection:
            assert connection.scalar(text("select version_num from alembic_version")) == (
                "0022_p3a_identity_memberships"
            )
            assert connection.scalar(
                text(
                    "select full_name from tenant_memberships where id = :membership_id"
                ),
                {"membership_id": _P3A_CANONICAL_USER_ID},
            ) == "Canonical Membership Drift"

        with engine.begin() as connection:
            connection.execute(
                text(
                    "update tenant_memberships set full_name = ("
                    "select users.full_name from users "
                    "where users.id = tenant_memberships.legacy_user_id "
                    "and users.tenant_id = tenant_memberships.tenant_id"
                    ") where id = :membership_id"
                ),
                {"membership_id": _P3A_CANONICAL_USER_ID},
            )
        alembic_command.downgrade(config, "0021_f2f_user_insert_grant")
        assert "tenant_memberships" not in inspect(engine).get_table_names()
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
            connection.execute(
                text(
                    "insert into legal_entities ("
                    "id, tenant_id, code, name, registered_name, timezone, status, "
                    "is_default, created_at, updated_at"
                    ") values ("
                    ":tenant_id, :tenant_id, 'DEFAULT', 'Settings Guard', "
                    "'Settings Guard', 'Europe/Istanbul', 'active', true, "
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
                    "insert into legal_entities ("
                    "id, tenant_id, code, name, registered_name, timezone, status, "
                    "is_default, created_at, updated_at"
                    ") values ("
                    ":tenant_id, :tenant_id, 'DEFAULT', 'P0E Guard', 'P0E Guard', "
                    "'Europe/Istanbul', 'active', true, CURRENT_TIMESTAMP, "
                    "CURRENT_TIMESTAMP"
                    ")"
                ),
                {"tenant_id": tenant_id},
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


def test_sqlite_p3f_backfill_preserves_historical_unbounded_tenant_name(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "migration-p3f-long-tenant-name.sqlite3"
    database_url = f"sqlite+aiosqlite:///{database_path}"
    config = _alembic_config(database_url)
    alembic_command.upgrade(config, "0026_p3e_identity_checkpoint")
    engine = create_engine(f"sqlite:///{database_path}")
    tenant_id = "cf000000000040008000000000000001"
    tenant_name = "Historical tenant " + ("x" * 300)
    try:
        with engine.begin() as connection:
            connection.execute(
                text(
                    "insert into tenants ("
                    "id, slug, name, status, plan_code, data_region, locale, timezone, "
                    "created_at, updated_at"
                    ") values ("
                    ":id, 'p3f-long-name', :name, 'active', 'core', 'tr-1', "
                    "'en-US', 'Europe/Istanbul', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
                ),
                {"id": tenant_id, "name": tenant_name},
            )

        alembic_command.upgrade(config, "head")
        with engine.connect() as connection:
            default_entity = connection.execute(
                text(
                    "select name, registered_name from legal_entities "
                    "where tenant_id = :tenant_id and is_default = true"
                ),
                {"tenant_id": tenant_id},
            ).one()
        assert default_entity == (tenant_name, tenant_name)

        alembic_command.downgrade(config, "0026_p3e_identity_checkpoint")
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
