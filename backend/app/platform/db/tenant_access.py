"""Transaction-local PostgreSQL capability and tenant binding.

The application login is expected to be an unprivileged ``NOINHERIT`` gateway that may
``SET ROLE`` to exactly one of the two capability roles below.  The role and tenant GUC are
always local to the active transaction, so returning a connection to the pool cannot retain
either access path.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from uuid import UUID

from sqlalchemy import event
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

TENANT_APPLICATION_ROLE = "wealthy_falcon_app"
PLATFORM_APPLICATION_ROLE = "wealthy_falcon_platform"

_DATABASE_ACCESS_CONTEXT_KEY = "wealthy_falcon.database_access_context"
_DATABASE_ACCESS_RESOLVER_KEY = "wealthy_falcon.database_access_resolver"
DATABASE_ACCESS_CONTEXT_STATE_KEY = "database_access_context"
MANAGED_DATABASE_SESSION_KEY = "wealthy_falcon.managed_database_session"


class DatabaseAccessPath(StrEnum):
    """Mutually exclusive database capabilities available to HTTP request sessions."""

    TENANT = "tenant"
    PLATFORM = "platform"


@dataclass(frozen=True, slots=True)
class DatabaseAccessContext:
    """Validated access capability to apply whenever a session starts a transaction."""

    path: DatabaseAccessPath
    tenant_id: UUID | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.path, DatabaseAccessPath):
            raise TypeError("path must be a DatabaseAccessPath")
        if self.path is DatabaseAccessPath.TENANT:
            if not isinstance(self.tenant_id, UUID) or self.tenant_id.int == 0:
                raise ValueError("tenant database access requires a non-zero UUID")
        elif self.tenant_id is not None:
            raise ValueError("platform database access cannot carry a tenant ID")


class MissingDatabaseAccessContextError(RuntimeError):
    """Raised before PostgreSQL work when no explicit request access path was selected."""


def configure_tenant_database_access(session: AsyncSession, tenant_id: UUID) -> None:
    """Make every transaction on ``session`` use the normal tenant application role."""

    _configure_database_access(
        session,
        DatabaseAccessContext(path=DatabaseAccessPath.TENANT, tenant_id=tenant_id),
    )


def configure_platform_database_access(session: AsyncSession) -> None:
    """Make every transaction on ``session`` use the metadata-only platform role."""

    _configure_database_access(
        session,
        DatabaseAccessContext(path=DatabaseAccessPath.PLATFORM),
    )


def database_access_context(session: AsyncSession) -> DatabaseAccessContext | None:
    """Return the immutable access context currently attached to a session."""

    return _resolved_database_access_context(session.sync_session)


def attach_database_access_resolver(
    session: AsyncSession,
    resolver: Callable[[], DatabaseAccessContext | None],
) -> None:
    """Resolve request access lazily when the session's first transaction begins."""

    if session.in_transaction():
        raise RuntimeError("Database access resolver must be attached before a transaction starts")
    session.sync_session.info[_DATABASE_ACCESS_RESOLVER_KEY] = resolver


def _resolved_database_access_context(
    session: Session,
) -> DatabaseAccessContext | None:
    context = session.info.get(_DATABASE_ACCESS_CONTEXT_KEY)
    if context is None:
        resolver = session.info.get(_DATABASE_ACCESS_RESOLVER_KEY)
        if resolver is not None:
            if not callable(resolver):  # pragma: no cover - internal invariant
                raise RuntimeError("Database access resolver is corrupt")
            context = resolver()
            if context is not None:
                session.info[_DATABASE_ACCESS_CONTEXT_KEY] = context
    if context is None:
        return None
    if not isinstance(context, DatabaseAccessContext):  # pragma: no cover - internal invariant
        raise RuntimeError("Database access context is corrupt")
    return context


async def require_transaction_database_access(session: AsyncSession) -> None:
    """Materialize a PostgreSQL UoW transaction only after an access path is configured.

    SQLite deliberately remains a no-op so the fast compatibility suite can exercise service
    and transaction behavior. PostgreSQL is the enforcement boundary and therefore fails closed.
    Calling ``connection()`` causes SQLAlchemy's ``after_begin`` hook below to issue the local
    role and tenant statements before the command operation can execute.
    """

    if session.get_bind().dialect.name != "postgresql":
        return
    if database_access_context(session) is None:
        raise MissingDatabaseAccessContextError(
            "PostgreSQL Unit of Work requires an explicit tenant or platform access path"
        )
    await session.connection()


def _configure_database_access(
    session: AsyncSession,
    context: DatabaseAccessContext,
) -> None:
    existing = database_access_context(session)
    if existing == context:
        return
    if existing is not None:
        raise RuntimeError("Database access path is immutable for the session lifetime")
    if session.in_transaction():
        raise RuntimeError("Database access must be configured before a transaction starts")
    session.sync_session.info[_DATABASE_ACCESS_CONTEXT_KEY] = context


@event.listens_for(Session, "after_begin")
def _bind_transaction_database_access(
    session: Session,
    _transaction: object,
    connection: Connection,
) -> None:
    if connection.dialect.name != "postgresql":
        return

    context = _resolved_database_access_context(session)
    if context is None:
        if not session.info.get(MANAGED_DATABASE_SESSION_KEY, False):
            return
        # Managed runtime sessions without request context still assume the normal role.  With
        # no tenant GUC, every forced RLS policy evaluates false rather than inheriting owner or
        # pool state.
        _set_local_role(connection, TENANT_APPLICATION_ROLE)
        return
    if not isinstance(context, DatabaseAccessContext):  # pragma: no cover - internal invariant
        raise RuntimeError("Database access context is corrupt")

    role = (
        TENANT_APPLICATION_ROLE
        if context.path is DatabaseAccessPath.TENANT
        else PLATFORM_APPLICATION_ROLE
    )
    _set_local_role(connection, role)
    if context.path is DatabaseAccessPath.TENANT:
        tenant_id = context.tenant_id
        if tenant_id is None:  # pragma: no cover - dataclass invariant
            raise RuntimeError("Tenant database access context is missing tenant_id")
        # UUID validation at construction makes this literal safe. PostgreSQL SET has no bind
        # parameter form; LOCAL guarantees automatic reset at commit or rollback.
        connection.exec_driver_sql(f"SET LOCAL app.tenant_id = '{tenant_id}'")


def _set_local_role(connection: Connection, role: str) -> None:
    quoted_role = connection.dialect.identifier_preparer.quote(role)
    connection.exec_driver_sql(f"SET LOCAL ROLE {quoted_role}")


__all__ = [
    "DatabaseAccessContext",
    "DATABASE_ACCESS_CONTEXT_STATE_KEY",
    "DatabaseAccessPath",
    "MANAGED_DATABASE_SESSION_KEY",
    "MissingDatabaseAccessContextError",
    "PLATFORM_APPLICATION_ROLE",
    "TENANT_APPLICATION_ROLE",
    "attach_database_access_resolver",
    "configure_platform_database_access",
    "configure_tenant_database_access",
    "database_access_context",
    "require_transaction_database_access",
]
