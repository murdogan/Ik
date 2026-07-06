from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory

ALEMBIC_INI = Path("alembic.ini")


def _script_directory() -> ScriptDirectory:
    return ScriptDirectory.from_config(Config(str(ALEMBIC_INI)))


def test_alembic_config_points_to_backend_migrations() -> None:
    config = Config(str(ALEMBIC_INI))

    assert config.get_main_option("script_location") == "backend/alembic"


def test_tenant_user_migration_chain_is_linear() -> None:
    script = _script_directory()
    tenant_revision = script.get_revision("0001_create_tenants")
    user_revision = script.get_revision("0002_create_users")

    assert script.get_heads() == ["0002_create_users"]
    assert tenant_revision is not None
    assert tenant_revision.down_revision is None
    assert user_revision is not None
    assert user_revision.down_revision == "0001_create_tenants"


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
