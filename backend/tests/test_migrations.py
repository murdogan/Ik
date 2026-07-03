from pathlib import Path


def test_initial_tenant_migration_exists() -> None:
    migration = Path("backend/alembic/versions/0001_create_tenants.py")

    assert migration.exists()
    text = migration.read_text()
    assert "create_table" in text
    assert "tenants" in text
    assert "ck_tenants_status" in text
