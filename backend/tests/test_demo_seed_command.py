import asyncio
import importlib.util
import os
import subprocess
import sys
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import app.models  # noqa: F401
from app.db.base import Base
from app.platform.identity import hash_activation_token
from sqlalchemy import create_engine, text
from sqlalchemy.ext.asyncio import create_async_engine

ROOT = Path(__file__).resolve().parents[2]
SEED_SCRIPT = ROOT / "scripts" / "seed_demo_data.py"
_SEED_SCRIPT_SPEC = importlib.util.spec_from_file_location("seed_demo_data_script", SEED_SCRIPT)
assert _SEED_SCRIPT_SPEC is not None
assert _SEED_SCRIPT_SPEC.loader is not None
_SEED_SCRIPT_MODULE = importlib.util.module_from_spec(_SEED_SCRIPT_SPEC)
_SEED_SCRIPT_SPEC.loader.exec_module(_SEED_SCRIPT_MODULE)
_ensure_local_database_url = _SEED_SCRIPT_MODULE._ensure_local_database_url


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


def test_demo_seed_command_prints_labeled_hashed_local_activation_paths(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "demo-auth-command.sqlite3"
    async_database_url = f"sqlite+aiosqlite:///{database_path}"
    asyncio.run(_create_model_schema(async_database_url))

    result = _run_seed_command(
        async_database_url,
        environment="local",
        auth_demo=True,
    )

    assert result.returncode == 0
    activation_lines = [
        line
        for line in result.stdout.splitlines()
        if line.startswith("DEMO_AUTH_ACTIVATION_URL ")
    ]
    assert len(activation_lines) == 2
    activation_urls: dict[str, str] = {}
    for line in activation_lines:
        user_field, url_field = line.removeprefix(
            "DEMO_AUTH_ACTIVATION_URL "
        ).split(" ", maxsplit=1)
        activation_urls[user_field.removeprefix("user=")] = url_field.removeprefix(
            "url="
        )
    assert tuple(activation_urls) == ("wf_admin", "wf_manager")
    tokens = {
        user_key: parse_qs(urlsplit(activation_url).fragment)["token"][0]
        for user_key, activation_url in activation_urls.items()
    }
    assert tokens["wf_admin"] != tokens["wf_manager"]

    engine = create_engine(f"sqlite:///{database_path}")
    try:
        with engine.connect() as connection:
            admin = connection.execute(
                text(
                    "select status, password_hash, can_invite_users from users "
                    "where full_name = 'Maya Stone'"
                )
            ).one()
            manager = connection.execute(
                text(
                    "select status, password_hash, can_invite_users from users "
                    "where full_name = 'Leila Morgan'"
                )
            ).one()
            identities = dict(
                connection.execute(
                    text(
                        "select email_normalized, status || ':' || "
                        "case when password_hash is null then 'none' else 'set' end "
                        "from identities where email_normalized in "
                        "('admin@wealthyfalcon.demo', 'manager@wealthyfalcon.demo')"
                    )
                ).all()
            )
            membership_statuses = dict(
                connection.execute(
                    text(
                        "select users.full_name, tenant_memberships.status "
                        "from tenant_memberships join users "
                        "on users.tenant_id = tenant_memberships.tenant_id "
                        "and users.id = tenant_memberships.legacy_user_id "
                        "where users.full_name in "
                        "('Maya Stone', 'Arda Blake', 'Leila Morgan')"
                    )
                ).all()
            )
            platform_role = connection.execute(
                text(
                    "select roles.code, platform_identity_roles.active "
                    "from platform_identity_roles join roles "
                    "on roles.id = platform_identity_roles.role_id"
                )
            ).one()
            admin_roles = {
                row[0]
                for row in connection.execute(
                    text(
                        "select roles.code from user_roles join roles "
                        "on roles.id = user_roles.role_id "
                        "where user_roles.user_id = "
                        "(select id from users where full_name = 'Maya Stone') "
                        "and user_roles.active = true"
                    )
                ).all()
            }
            membership_count = connection.scalar(
                text(
                    "select count(*) from tenant_memberships where identity_id = "
                    "(select id from identities where "
                    "email_normalized = 'admin@wealthyfalcon.demo')"
                )
            )
            token_hashes = dict(
                connection.execute(
                    text(
                        "select users.full_name, user_activation_tokens.token_hash "
                        "from user_activation_tokens join users "
                        "on users.tenant_id = user_activation_tokens.tenant_id "
                        "and users.id = user_activation_tokens.user_id "
                        "where user_activation_tokens.consumed_at is null "
                        "and user_activation_tokens.revoked_at is null"
                    )
                ).all()
            )
        assert admin == ("invited", None, True)
        assert manager == ("invited", None, False)
        assert identities == {
            "admin@wealthyfalcon.demo": "pending:none",
            "manager@wealthyfalcon.demo": "pending:none",
        }
        assert membership_statuses == {
            "Maya Stone": "invited",
            "Arda Blake": "active",
            "Leila Morgan": "invited",
        }
        assert platform_role == ("super_admin", True)
        assert admin_roles == {"tenant_admin", "hr_specialist"}
        assert membership_count == 2
        assert token_hashes == {
            "Maya Stone": hash_activation_token(tokens["wf_admin"]),
            "Leila Morgan": hash_activation_token(tokens["wf_manager"]),
        }
        for token in tokens.values():
            assert token not in token_hashes.values()
    finally:
        engine.dispose()


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


def test_demo_seed_local_database_url_guard_accepts_case_insensitive_localhost() -> None:
    _ensure_local_database_url("postgresql+asyncpg://ik:ik@LOCALHOST:5432/ik")


def _run_seed_command(
    database_url: str,
    *,
    environment: str,
    auth_demo: bool = False,
) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["IK_ENVIRONMENT"] = environment

    arguments = [
        sys.executable,
        str(SEED_SCRIPT),
        "--database-url",
        database_url,
    ]
    if auth_demo:
        arguments.append("--auth-demo")

    return subprocess.run(
        arguments,
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
