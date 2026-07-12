from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

import pytest
from alembic import command as alembic_command
from alembic.config import Config
from app.models.user import UserStatus
from app.schemas.user_administration import UserListCursor, UserListPagination
from app.services.user_administration_service import _user_list_statement
from sqlalchemy import text
from sqlalchemy.engine import URL
from sqlalchemy.ext.asyncio import AsyncConnection, create_async_engine
from sqlalchemy.pool import NullPool

pytestmark = pytest.mark.postgres

ROOT = Path(__file__).resolve().parents[3]
ALEMBIC_INI = ROOT / "alembic.ini"
TENANT_ID = UUID("c1000000-0000-4000-8000-000000000001")
USER_COUNT = 5_000
EXPECTED_INDEXES = {
    "ix_users_email_normalized_trgm",
    "ix_users_full_name_trgm",
    "ix_users_tenant_created_at_id",
    "ix_users_tenant_status_created_at_id",
}


@pytest.fixture
def f2c_postgres_database(postgres_database_url: URL) -> URL:
    alembic_command.upgrade(_alembic_config(postgres_database_url), "head")
    return postgres_database_url


def test_user_admin_search_and_cursor_indexes_are_present_and_used(
    f2c_postgres_database: URL,
) -> None:
    evidence = asyncio.run(_capture_index_evidence(f2c_postgres_database))
    print(f"F2C_USER_INDEX_EVIDENCE={json.dumps(evidence, sort_keys=True)}")

    assert set(evidence["catalog"]) == EXPECTED_INDEXES
    assert "gin_trgm_ops" in evidence["catalog"]["ix_users_email_normalized_trgm"]
    assert "gin_trgm_ops" in evidence["catalog"]["ix_users_full_name_trgm"]
    assert {
        "ix_users_email_normalized_trgm",
        "ix_users_full_name_trgm",
    } <= set(evidence["search_indexes"])
    assert "ix_users_tenant_status_created_at_id" in evidence["cursor_indexes"]
    assert evidence["search_rows"] == 1
    assert evidence["cursor_rows"] == 26


def _alembic_config(database_url: URL) -> Config:
    config = Config(str(ALEMBIC_INI))
    config.set_main_option(
        "sqlalchemy.url",
        database_url.render_as_string(hide_password=False).replace("%", "%%"),
    )
    return config


async def _capture_index_evidence(database_url: URL) -> dict[str, object]:
    engine = create_async_engine(database_url, poolclass=NullPool)
    try:
        async with engine.begin() as connection:
            await _seed_users(connection)

        async with engine.connect() as maintenance_connection:
            maintenance_connection = await maintenance_connection.execution_options(
                isolation_level="AUTOCOMMIT"
            )
            await maintenance_connection.execute(text("vacuum (analyze) users"))

        async with engine.begin() as connection:
            catalog = {
                row["indexname"]: row["indexdef"]
                for row in (
                    await connection.execute(
                        text(
                            "select indexname, indexdef from pg_indexes "
                            "where schemaname = current_schema() "
                            "and indexname = any(:index_names)"
                        ),
                        {"index_names": sorted(EXPECTED_INDEXES)},
                    )
                ).mappings()
            }
            search_plan = await _explain_statement(
                connection,
                _user_list_statement(
                    TENANT_ID,
                    UserListPagination(search="marker04242", limit=25),
                    dialect_name="postgresql",
                ).limit(26),
            )
            cursor_plan = await _explain_statement(
                connection,
                _user_list_statement(
                    TENANT_ID,
                    UserListPagination(
                        status=UserStatus.INVITED,
                        limit=25,
                        cursor=UserListCursor(
                            created_at=datetime(2026, 7, 1, 11, 18, 20, tzinfo=UTC),
                            id=UUID("c2000000-0000-4000-8000-000000002500"),
                            status=UserStatus.INVITED.value,
                        ),
                    ),
                    dialect_name="postgresql",
                ).limit(26),
            )
    finally:
        await engine.dispose()

    return {
        "catalog": catalog,
        "search_indexes": sorted(_index_names(search_plan["Plan"])),
        "search_rows": int(search_plan["Plan"]["Actual Rows"]),
        "cursor_indexes": sorted(_index_names(cursor_plan["Plan"])),
        "cursor_rows": int(cursor_plan["Plan"]["Actual Rows"]),
    }


async def _seed_users(connection: AsyncConnection) -> None:
    await connection.execute(
        text(
            "insert into tenants ("
            "id, slug, name, status, plan_code, data_region, locale, timezone"
            ") values ("
            ":tenant_id, 'f2c-indexes', 'F2C Indexes', 'active', 'core', "
            "'tr-1', 'en-US', 'UTC'"
            ")"
        ),
        {"tenant_id": TENANT_ID},
    )
    await connection.execute(
        text(
            "insert into users ("
            "id, tenant_id, email, full_name, status, created_at, updated_at"
            ") select "
            "('c2000000-0000-4000-8000-' || lpad(gs::text, 12, '0'))::uuid, "
            ":tenant_id, "
            "'marker' || lpad(gs::text, 5, '0') || '@f2c.test', "
            "'Marker' || lpad(gs::text, 5, '0'), "
            "case when gs % 2 = 0 then 'invited' else 'disabled' end, "
            "timestamptz '2026-07-01 12:00:00+00' - gs * interval '1 second', "
            "timestamptz '2026-07-01 12:00:00+00' - gs * interval '1 second' "
            "from generate_series(1, :user_count) as gs"
        ),
        {"tenant_id": TENANT_ID, "user_count": USER_COUNT},
    )


async def _explain_statement(
    connection: AsyncConnection,
    statement,
) -> dict[str, object]:
    compiled = statement.compile(
        dialect=connection.dialect,
        compile_kwargs={"literal_binds": True},
    )
    payload = await connection.scalar(text(f"EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) {compiled}"))
    if isinstance(payload, str):
        payload = json.loads(payload)
    assert isinstance(payload, list) and len(payload) == 1
    return payload[0]


def _index_names(plan: object) -> set[str]:
    if not isinstance(plan, dict):
        return set()
    names = set()
    index_name = plan.get("Index Name")
    if isinstance(index_name, str):
        names.add(index_name)
    for child in plan.get("Plans", []):
        names.update(_index_names(child))
    return names
