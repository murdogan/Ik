"""SQLAlchemy transaction boundary for application commands."""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Protocol, TypeVar

from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.exc import StaleDataError

from app.platform.db.tenant_access import (
    clear_database_command_context,
    require_transaction_database_access,
)
from app.platform.errors.application import ApplicationError

_ResultT = TypeVar("_ResultT")
_CONCURRENCY_SQLSTATES = frozenset({"40001", "40P01", "55P03"})


class UnitOfWork(Protocol):
    """Small command boundary; persistence details stay in the adapter."""

    async def execute(self, operation: Callable[[], Awaitable[_ResultT]]) -> _ResultT: ...


class PersistenceError(ApplicationError):
    """Base for safe, typed persistence failures exposed to the application edge."""


class PersistenceIntegrityError(PersistenceError):
    def __init__(self, *, constraint_name: str | None) -> None:
        super().__init__()
        self.constraint_name = constraint_name


class PersistenceConcurrencyError(PersistenceError):
    def __init__(self, *, sqlstate: str | None) -> None:
        super().__init__()
        self.sqlstate = sqlstate


@dataclass(slots=True)
class SqlAlchemyUnitOfWork:
    """Own exactly one SQLAlchemy transaction for one application command."""

    session: AsyncSession

    async def execute(self, operation: Callable[[], Awaitable[_ResultT]]) -> _ResultT:
        try:
            if self.session.in_transaction():
                raise RuntimeError("Unit of Work requires an idle session")
            try:
                async with self.session.begin():
                    await require_transaction_database_access(self.session)
                    return await operation()
            except Exception as exc:
                translated = translate_persistence_error(exc)
                if translated is None:
                    raise
                raise translated from exc
        finally:
            clear_database_command_context(self.session)


def translate_persistence_error(exc: Exception) -> PersistenceError | None:
    """Translate known SQLAlchemy/DB concurrency and integrity failures without DB text."""

    if isinstance(exc, StaleDataError):
        return PersistenceConcurrencyError(sqlstate=None)
    if isinstance(exc, IntegrityError):
        return PersistenceIntegrityError(constraint_name=constraint_name_from_error(exc))
    if isinstance(exc, DBAPIError):
        sqlstate = sqlstate_from_error(exc)
        if sqlstate in _CONCURRENCY_SQLSTATES:
            return PersistenceConcurrencyError(sqlstate=sqlstate)
    return None


def constraint_name_from_error(exc: BaseException) -> str | None:
    for candidate in _exception_tree(exc):
        constraint_name = getattr(candidate, "constraint_name", None)
        if isinstance(constraint_name, str) and constraint_name:
            return constraint_name
        diagnostics = getattr(candidate, "diag", None)
        constraint_name = getattr(diagnostics, "constraint_name", None)
        if isinstance(constraint_name, str) and constraint_name:
            return constraint_name
    return None


def sqlstate_from_error(exc: BaseException) -> str | None:
    for candidate in _exception_tree(exc):
        for attribute in ("sqlstate", "pgcode"):
            sqlstate = getattr(candidate, attribute, None)
            if isinstance(sqlstate, str) and sqlstate:
                return sqlstate
    return None


def _exception_tree(exc: BaseException) -> list[BaseException]:
    pending = [exc]
    seen: set[int] = set()
    exceptions: list[BaseException] = []
    while pending:
        candidate = pending.pop()
        if id(candidate) in seen:
            continue
        seen.add(id(candidate))
        exceptions.append(candidate)
        for attribute in ("orig", "__cause__", "__context__"):
            nested = getattr(candidate, attribute, None)
            if isinstance(nested, BaseException):
                pending.append(nested)
    return exceptions
