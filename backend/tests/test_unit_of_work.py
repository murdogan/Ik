from collections.abc import AsyncIterator

import pytest
from app.api.errors import application_error_to_api_error
from app.platform.db import (
    PersistenceConcurrencyError,
    PersistenceIntegrityError,
    SqlAlchemyUnitOfWork,
    translate_persistence_error,
)
from sqlalchemy import Column, Integer, MetaData, String, Table, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import registry
from sqlalchemy.orm.exc import StaleDataError
from sqlalchemy.pool import StaticPool

_probe_registry = registry(metadata=MetaData())
_commit_probe_table = Table(
    "p0c_commit_probe",
    _probe_registry.metadata,
    Column("id", Integer, primary_key=True),
    Column("value", String(64), nullable=False, unique=True),
)


class _CommitProbe:
    pass


_probe_registry.map_imperatively(_CommitProbe, _commit_probe_table)


@pytest.fixture
async def probe_sessions() -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as connection:
        await connection.execute(
            text(
                "create table p0c_uow_probe ("
                "id integer primary key, value varchar(64) not null unique)"
            )
        )
        await connection.execute(
            text("insert into p0c_uow_probe (id, value) values (1, 'persisted')")
        )
        await connection.run_sync(_probe_registry.metadata.create_all)
        await connection.execute(
            _commit_probe_table.insert().values(id=1, value="persisted")
        )

    try:
        yield async_sessionmaker(engine, expire_on_commit=False)
    finally:
        await engine.dispose()


async def test_unit_of_work_rolls_back_all_writes_and_types_integrity_failure(
    probe_sessions: async_sessionmaker[AsyncSession],
) -> None:
    async with probe_sessions() as session:
        unit_of_work = SqlAlchemyUnitOfWork(session)

        async def operation() -> None:
            await session.execute(
                text("insert into p0c_uow_probe (id, value) values (2, 'must-roll-back')")
            )
            await session.execute(
                text("insert into p0c_uow_probe (id, value) values (3, 'persisted')")
            )

        with pytest.raises(PersistenceIntegrityError) as error:
            await unit_of_work.execute(operation)

        assert error.value.constraint_name is None
        assert session.in_transaction() is False

    async with probe_sessions() as verification_session:
        rows = list(
            await verification_session.execute(
                text("select id, value from p0c_uow_probe order by id")
            )
        )
    assert rows == [(1, "persisted")]

    api_error = application_error_to_api_error(error.value)
    assert api_error.status_code == 409
    assert api_error.code == "data_integrity_conflict"
    assert api_error.message == "The request conflicts with persisted data"


async def test_unit_of_work_rolls_back_and_types_orm_concurrency_failure(
    probe_sessions: async_sessionmaker[AsyncSession],
) -> None:
    async with probe_sessions() as session:
        unit_of_work = SqlAlchemyUnitOfWork(session)

        async def operation() -> None:
            await session.execute(
                text("insert into p0c_uow_probe (id, value) values (2, 'must-roll-back')")
            )
            raise StaleDataError("database details must not reach the response")

        with pytest.raises(PersistenceConcurrencyError) as error:
            await unit_of_work.execute(operation)

        assert error.value.sqlstate is None
        assert session.in_transaction() is False

    async with probe_sessions() as verification_session:
        row_count = await verification_session.scalar(
            text("select count(*) from p0c_uow_probe")
        )
    assert row_count == 1

    api_error = application_error_to_api_error(error.value)
    assert api_error.status_code == 409
    assert api_error.code == "concurrent_write_conflict"
    assert api_error.message == "The request conflicted with another write; retry the request"
    assert "database details" not in api_error.message


async def test_unit_of_work_translates_commit_time_integrity_error_and_recovers_session(
    probe_sessions: async_sessionmaker[AsyncSession],
) -> None:
    async with probe_sessions() as session:
        unit_of_work = SqlAlchemyUnitOfWork(session)

        async def operation() -> None:
            session.add(_CommitProbe(id=2, value="persisted"))

        with pytest.raises(PersistenceIntegrityError):
            await unit_of_work.execute(operation)

        assert session.in_transaction() is False
        row_count = await session.scalar(text("select count(*) from p0c_commit_probe"))
        assert row_count == 1
        await session.rollback()

    async with probe_sessions() as verification_session:
        row_count = await verification_session.scalar(
            text("select count(*) from p0c_commit_probe")
        )
    assert row_count == 1


def test_postgresql_serialization_sqlstate_translates_without_database_text() -> None:
    original = _DatabaseSerializationFailure("sensitive database text")
    error = OperationalError("sensitive statement", {}, original)

    translated = translate_persistence_error(error)

    assert isinstance(translated, PersistenceConcurrencyError)
    assert translated.sqlstate == "40001"
    assert str(translated) == ""


async def test_unit_of_work_rejects_implicit_nesting(
    probe_sessions: async_sessionmaker[AsyncSession],
) -> None:
    async with probe_sessions() as session:
        await session.scalar(text("select count(*) from p0c_uow_probe"))

        with pytest.raises(RuntimeError, match="requires an idle session"):
            await SqlAlchemyUnitOfWork(session).execute(_completed_operation)


class _DatabaseSerializationFailure(Exception):
    sqlstate = "40001"


async def _completed_operation() -> None:
    return None
