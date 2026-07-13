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
from app.services.employee_service import (
    DuplicateEmployeeNumberError,
    DuplicateWorkEmailError,
    EmployeeService,
)
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


def test_concurrent_employee_work_email_violation_has_stable_conflict_mapping(
    p0c_migrated_postgres_database: URL,
) -> None:
    asyncio.run(_assert_concurrent_work_email_conflict(p0c_migrated_postgres_database))


def test_postgresql_lock_concurrency_error_has_stable_conflict_mapping(
    p0c_migrated_postgres_database: URL,
) -> None:
    asyncio.run(_assert_lock_conflict_mapping(p0c_migrated_postgres_database))


def test_concurrent_employee_mapper_versions_have_stable_conflict_mapping(
    p0c_migrated_postgres_database: URL,
) -> None:
    asyncio.run(_assert_employee_mapper_version_conflict(p0c_migrated_postgres_database))


async def _assert_concurrent_employee_conflict(database_url: URL) -> None:
    engine = create_async_engine(database_url, poolclass=NullPool)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    tenant_id = uuid4()
    employee_number = f"P0C-{uuid4().hex}"
    barrier = _AvailabilityBarrier()
    try:
        await _insert_tenant(engine, tenant_id)

        async def create_employee(candidate_number: str) -> object:
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
                        employee_number=candidate_number,
                        first_name="Concurrent",
                        last_name="Employee",
                        employment_start_date=date(2026, 7, 10),
                    ),
                )

        outcomes = await asyncio.gather(
            create_employee(employee_number.upper()),
            create_employee(employee_number.lower()),
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
                .where(Employee.employee_number_normalized == employee_number.lower())
            )
        assert row_count == 1
    finally:
        await engine.dispose()


async def _assert_concurrent_work_email_conflict(database_url: URL) -> None:
    engine = create_async_engine(database_url, poolclass=NullPool)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    tenant_id = uuid4()
    work_email = f"p4a-{uuid4().hex}@example.test"
    barrier = _AvailabilityBarrier()
    try:
        await _insert_tenant(engine, tenant_id)

        async def create_employee(candidate_number: str, candidate_email: str) -> object:
            async with session_factory() as session:
                configure_tenant_database_access(session, tenant_id)
                handler = EmployeeCommandHandler(
                    service=_WorkEmailBarrierEmployeeService(session, barrier),
                    unit_of_work=SqlAlchemyUnitOfWork(session),
                )
                return await handler.create_employee(
                    tenant_id,
                    EmployeeCreate(
                        employee_number=candidate_number,
                        first_name="Concurrent",
                        last_name="Email",
                        email=candidate_email,
                        employment_start_date=date(2026, 7, 10),
                    ),
                )

        outcomes = await asyncio.gather(
            create_employee(f"P4A-{uuid4().hex}", work_email.upper()),
            create_employee(f"P4A-{uuid4().hex}", work_email.lower()),
            return_exceptions=True,
        )

        successes = [outcome for outcome in outcomes if not isinstance(outcome, BaseException)]
        failures = [outcome for outcome in outcomes if isinstance(outcome, BaseException)]
        assert len(successes) == 1
        assert len(failures) == 1
        assert isinstance(failures[0], DuplicateWorkEmailError)

        api_error = application_error_to_api_error(failures[0])
        assert api_error.status_code == 409
        assert api_error.code == "employee_work_email_conflict"
        assert api_error.message == "Work email already exists for this tenant"

        async with session_factory() as verification_session:
            row_count = await verification_session.scalar(
                select(func.count())
                .select_from(Employee)
                .where(Employee.tenant_id == tenant_id)
                .where(Employee.email_normalized == work_email.lower())
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


async def _assert_employee_mapper_version_conflict(database_url: URL) -> None:
    engine = create_async_engine(database_url, poolclass=NullPool)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    tenant_id = uuid4()
    barrier = _AvailabilityBarrier()
    try:
        await _insert_tenant(engine, tenant_id)
        async with session_factory() as session:
            configure_tenant_database_access(session, tenant_id)
            created = await EmployeeCommandHandler(
                service=EmployeeService(session),
                unit_of_work=SqlAlchemyUnitOfWork(session),
            ).create_employee(
                tenant_id,
                EmployeeCreate(
                    employee_number=f"P4A-VERSION-{uuid4().hex}",
                    first_name="Concurrent",
                    last_name="Version",
                    employment_start_date=date(2026, 7, 10),
                ),
            )
            employee_id = created.id

        async def update_position(position: str) -> None:
            async with session_factory() as session:
                configure_tenant_database_access(session, tenant_id)
                unit_of_work = SqlAlchemyUnitOfWork(session)

                async def operation() -> None:
                    employee = await session.scalar(
                        select(Employee)
                        .where(Employee.tenant_id == tenant_id)
                        .where(Employee.id == employee_id)
                    )
                    assert employee is not None
                    assert employee.version == 1
                    await barrier.wait()
                    employee.position = position
                    await session.flush()

                await unit_of_work.execute(operation)

        outcomes = await asyncio.gather(
            update_position("Version A"),
            update_position("Version B"),
            return_exceptions=True,
        )
        failures = [outcome for outcome in outcomes if isinstance(outcome, BaseException)]
        assert len(failures) == 1
        assert isinstance(failures[0], PersistenceConcurrencyError)
        api_error = application_error_to_api_error(failures[0])
        assert api_error.status_code == 409
        assert api_error.code == "concurrent_write_conflict"

        async with session_factory() as session:
            configure_tenant_database_access(session, tenant_id)
            persisted = await session.scalar(
                select(Employee)
                .where(Employee.tenant_id == tenant_id)
                .where(Employee.id == employee_id)
            )
            assert persisted is not None
            assert persisted.version == 2
            assert persisted.position in {"Version A", "Version B"}
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


class _WorkEmailBarrierEmployeeService(EmployeeService):
    def __init__(self, session: AsyncSession, barrier: _AvailabilityBarrier) -> None:
        super().__init__(session)
        self.barrier = barrier

    async def _ensure_work_email_available(
        self,
        tenant_id: UUID,
        work_email: str,
        exclude_employee_id: UUID | None = None,
    ) -> None:
        await super()._ensure_work_email_available(
            tenant_id,
            work_email,
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
