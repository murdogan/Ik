from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from alembic import command as alembic_command
from alembic.config import Config
from app.api.errors import application_error_to_api_error
from app.models.employee import Employee
from app.platform.db import (
    PersistenceConcurrencyError,
    SqlAlchemyUnitOfWork,
    configure_tenant_database_access,
)
from app.schemas.employee import EmployeeCreate
from app.services.employee_commands import EmployeeCommandHandler
from app.services.employee_service import DuplicateEmployeeNumberError, EmployeeService
from sqlalchemy import func, select, text
from sqlalchemy.engine import URL
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

pytestmark = pytest.mark.postgres

ROOT = Path(__file__).resolve().parents[3]
ALEMBIC_INI = ROOT / "alembic.ini"


@pytest.fixture
def p0c_migrated_postgres_database(postgres_database_url: URL) -> URL:
    alembic_command.upgrade(_alembic_config(postgres_database_url), "head")
    return postgres_database_url


def test_concurrent_employee_unique_violation_has_stable_conflict_mapping(
    p0c_migrated_postgres_database: URL,
) -> None:
    asyncio.run(_assert_concurrent_employee_conflict(p0c_migrated_postgres_database))


def test_postgresql_lock_concurrency_error_has_stable_conflict_mapping(
    p0c_migrated_postgres_database: URL,
) -> None:
    asyncio.run(_assert_lock_conflict_mapping(p0c_migrated_postgres_database))


async def _assert_concurrent_employee_conflict(database_url: URL) -> None:
    engine = create_async_engine(database_url, poolclass=NullPool)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    tenant_id = uuid4()
    employee_number = f"P0C-{uuid4().hex}"
    barrier = _AvailabilityBarrier()
    try:
        await _insert_tenant(engine, tenant_id)

        async def create_employee() -> object:
            async with session_factory() as session:
                configure_tenant_database_access(session, tenant_id)
                service = _BarrierEmployeeService(session, barrier)
                handler = EmployeeCommandHandler(
                    service=service,
                    unit_of_work=SqlAlchemyUnitOfWork(session),
                )
                return await handler.create_employee(
                    tenant_id,
                    EmployeeCreate(
                        employee_number=employee_number,
                        first_name="Concurrent",
                        last_name="Employee",
                        employment_start_date=date(2026, 7, 10),
                    ),
                )

        outcomes = await asyncio.gather(
            create_employee(),
            create_employee(),
            return_exceptions=True,
        )

        successes = [outcome for outcome in outcomes if not isinstance(outcome, BaseException)]
        failures = [outcome for outcome in outcomes if isinstance(outcome, BaseException)]
        assert len(successes) == 1
        assert len(failures) == 1
        assert isinstance(failures[0], DuplicateEmployeeNumberError)

        api_error = application_error_to_api_error(failures[0])
        assert api_error.status_code == 409
        assert api_error.code == "employee_number_conflict"
        assert api_error.message == "Employee number already exists for this tenant"

        async with session_factory() as verification_session:
            row_count = await verification_session.scalar(
                select(func.count())
                .select_from(Employee)
                .where(Employee.tenant_id == tenant_id)
                .where(Employee.employee_number == employee_number)
            )
        assert row_count == 1
    finally:
        await engine.dispose()


async def _assert_lock_conflict_mapping(database_url: URL) -> None:
    engine = create_async_engine(database_url, poolclass=NullPool)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    tenant_id = uuid4()
    try:
        await _insert_tenant(engine, tenant_id)
        async with session_factory() as locking_session:
            async with locking_session.begin():
                await locking_session.execute(
                    text("select id from tenants where id = :tenant_id for update"),
                    {"tenant_id": tenant_id},
                )

                async with session_factory() as conflicting_session:
                    configure_tenant_database_access(conflicting_session, tenant_id)
                    unit_of_work = SqlAlchemyUnitOfWork(conflicting_session)

                    async def acquire_locked_row() -> None:
                        await conflicting_session.execute(text("set local lock_timeout = '100ms'"))
                        await conflicting_session.execute(
                            text("select id from tenants where id = :tenant_id for update"),
                            {"tenant_id": tenant_id},
                        )

                    with pytest.raises(PersistenceConcurrencyError) as error:
                        await unit_of_work.execute(acquire_locked_row)

                    assert error.value.sqlstate == "55P03"
                    assert conflicting_session.in_transaction() is False
                    api_error = application_error_to_api_error(error.value)
                    assert api_error.status_code == 409
                    assert api_error.code == "concurrent_write_conflict"
                    assert api_error.message == (
                        "The request conflicted with another write; retry the request"
                    )
    finally:
        await engine.dispose()


@dataclass(slots=True)
class _AvailabilityBarrier:
    arrivals: int = 0
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    ready: asyncio.Event = field(default_factory=asyncio.Event)

    async def wait(self) -> None:
        async with self.lock:
            self.arrivals += 1
            if self.arrivals == 2:
                self.ready.set()
        await asyncio.wait_for(self.ready.wait(), timeout=5)


class _BarrierEmployeeService(EmployeeService):
    def __init__(self, session: AsyncSession, barrier: _AvailabilityBarrier) -> None:
        super().__init__(session)
        self.barrier = barrier

    async def _ensure_employee_number_available(
        self,
        tenant_id: UUID,
        employee_number: str,
        exclude_employee_id: UUID | None = None,
    ) -> None:
        await super()._ensure_employee_number_available(
            tenant_id,
            employee_number,
            exclude_employee_id,
        )
        await self.barrier.wait()


async def _insert_tenant(engine, tenant_id: UUID) -> None:
    async with engine.begin() as connection:
        await connection.execute(
            text(
                "insert into tenants ("
                "id, slug, name, status, plan_code, data_region, locale, timezone"
                ") values ("
                ":id, :slug, 'P0C tenant', 'active', 'core', 'tr-1', "
                "'tr-TR', 'Europe/Istanbul'"
                ")"
            ),
            {"id": tenant_id, "slug": f"p0c-{uuid4().hex}"},
        )


def _alembic_config(database_url: URL) -> Config:
    config = Config(str(ALEMBIC_INI))
    config.set_main_option(
        "sqlalchemy.url",
        database_url.render_as_string(hide_password=False).replace("%", "%%"),
    )
    return config
