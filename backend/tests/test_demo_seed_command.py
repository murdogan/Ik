import asyncio
import os
import subprocess
import sys
from pathlib import Path

import app.models  # noqa: F401
from app.db.base import Base
from sqlalchemy import create_engine, text
from sqlalchemy.ext.asyncio import create_async_engine

ROOT = Path(__file__).resolve().parents[2]
SEED_SCRIPT = ROOT / "scripts" / "seed_demo_data.py"


def test_demo_seed_command_runs_twice_against_local_db(tmp_path: Path) -> None:
    database_path = tmp_path / "demo-seed-command.sqlite3"
    async_database_url = f"sqlite+aiosqlite:///{database_path}"

    asyncio.run(_create_model_schema(async_database_url))

    first_run = _run_seed_command(async_database_url, environment="local")
    second_run = _run_seed_command(async_database_url, environment="local")

    for result in [first_run, second_run]:
        assert result.returncode == 0
        assert result.stderr == ""
        assert "DEMO_SEED_OK tenants=2 users=5 employees=8 leave_requests=5" in result.stdout
        assert "f1000000-0000-4000-8000-000000000001" in result.stdout
        assert "f1000000-0000-4000-8000-000000000002" in result.stdout

    engine = create_engine(f"sqlite:///{database_path}")
    try:
        with engine.connect() as connection:
            assert _count_table(connection, "tenants") == 2
            assert _count_table(connection, "users") == 5
            assert _count_table(connection, "employees") == 8
            assert _count_table(connection, "leave_requests") == 5
    finally:
        engine.dispose()


def test_demo_seed_command_refuses_staging_environment() -> None:
    result = _run_seed_command("sqlite+aiosqlite:///:memory:", environment="staging")

    assert result.returncode == 2
    assert result.stdout == ""
    assert (
        "DEMO_SEED_REFUSED environment='staging' allowed_environments=local,dev"
        in result.stderr
    )


def test_demo_seed_command_refuses_non_local_database_url() -> None:
    result = _run_seed_command(
        "postgresql+asyncpg://ik:ik@db.example.com:5432/ik",
        environment="local",
    )

    assert result.returncode == 2
    assert result.stdout == ""
    assert (
        "DEMO_SEED_REFUSED database_url_not_local "
        "host='db.example.com' allowed_hosts=127.0.0.1,::1,localhost"
    ) in result.stderr


def _run_seed_command(database_url: str, *, environment: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["IK_ENVIRONMENT"] = environment

    return subprocess.run(
        [
            sys.executable,
            str(SEED_SCRIPT),
            "--database-url",
            database_url,
        ],
        cwd=ROOT,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )


async def _create_model_schema(database_url: str) -> None:
    engine = create_async_engine(database_url)
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
    finally:
        await engine.dispose()


def _count_table(connection, table_name: str) -> int:
    return int(connection.execute(text(f"select count(*) from {table_name}")).scalar_one())
