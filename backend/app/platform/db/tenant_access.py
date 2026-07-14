"""Transaction-local PostgreSQL capability and tenant binding.

The application login is expected to be an unprivileged ``NOINHERIT`` gateway that may
``SET ROLE`` to exactly one of the capability roles below.  The role and tenant GUC are
always local to the active transaction, so returning a connection to the pool cannot retain
any access path.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from uuid import UUID

from sqlalchemy import event, text
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.platform.request_context import is_valid_request_id, is_valid_trace_id

TENANT_APPLICATION_ROLE = "wealthy_falcon_app"
PLATFORM_APPLICATION_ROLE = "wealthy_falcon_platform"
AUTHENTICATION_APPLICATION_ROLE = "wealthy_falcon_authentication"

_DATABASE_ACCESS_CONTEXT_KEY = "wealthy_falcon.database_access_context"
_DATABASE_ACCESS_RESOLVER_KEY = "wealthy_falcon.database_access_resolver"
_DATABASE_COMMAND_CONTEXT_KEY = "wealthy_falcon.database_command_context"
DATABASE_ACCESS_CONTEXT_STATE_KEY = "database_access_context"
MANAGED_DATABASE_SESSION_KEY = "wealthy_falcon.managed_database_session"


class DatabaseAccessPath(StrEnum):
    """Mutually exclusive database capabilities available to HTTP request sessions."""

    TENANT = "tenant"
    PLATFORM = "platform"
    AUTHENTICATION = "authentication"


class DatabaseCommandIntent(StrEnum):
    """Closed database commands whose trusted context is bound before runtime role entry."""

    P4E_SUBMIT = "p4e_submit"
    P4E_CANCEL = "p4e_cancel"
    P4E_APPROVE = "p4e_approve"
    P4E_REJECT = "p4e_reject"
    P4B_PERSONAL_UPDATE = "p4b_personal_update"


@dataclass(frozen=True, slots=True)
class DatabaseAccessContext:
    """Validated access capability to apply whenever a session starts a transaction."""

    path: DatabaseAccessPath
    tenant_id: UUID | None = None
    actor_id: UUID | None = None
    membership_id: UUID | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.path, DatabaseAccessPath):
            raise TypeError("path must be a DatabaseAccessPath")
        if self.path is DatabaseAccessPath.TENANT:
            if not isinstance(self.tenant_id, UUID) or self.tenant_id.int == 0:
                raise ValueError("tenant database access requires a non-zero UUID")
            has_actor = self.actor_id is not None
            has_membership = self.membership_id is not None
            if has_actor != has_membership:
                raise ValueError(
                    "tenant database access must carry actor and membership IDs together"
                )
            for field_name in ("actor_id", "membership_id"):
                value = getattr(self, field_name)
                if value is not None and (not isinstance(value, UUID) or value.int == 0):
                    raise ValueError(f"tenant database access {field_name} must be a non-zero UUID")
        elif any(
            value is not None for value in (self.tenant_id, self.actor_id, self.membership_id)
        ):
            raise ValueError("non-tenant database access cannot carry tenant actor context")


@dataclass(frozen=True, slots=True)
class DatabaseCommandContext:
    """One immutable, transaction-scoped command capability for a tenant request."""

    tenant_id: UUID
    actor_user_id: UUID
    membership_id: UUID
    intent: DatabaseCommandIntent
    target_id: UUID
    audit_event_id: UUID
    correlation_request_id: str
    trace_id: str
    session_id: UUID | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.intent, DatabaseCommandIntent):
            raise TypeError("intent must be a DatabaseCommandIntent")
        for field_name in (
            "tenant_id",
            "actor_user_id",
            "membership_id",
            "target_id",
            "audit_event_id",
        ):
            value = getattr(self, field_name)
            if not isinstance(value, UUID) or value.int == 0:
                raise ValueError(f"database command {field_name} must be a non-zero UUID")
        if self.session_id is not None and (
            not isinstance(self.session_id, UUID) or self.session_id.int == 0
        ):
            raise ValueError("database command session_id must be a non-zero UUID when present")

        if not is_valid_request_id(self.correlation_request_id):
            raise ValueError("database command correlation_request_id is invalid")
        if not is_valid_trace_id(self.trace_id):
            raise ValueError("database command trace_id is invalid")


class MissingDatabaseAccessContextError(RuntimeError):
    """Raised before PostgreSQL work when no explicit request access path was selected."""


def configure_tenant_database_access(
    session: AsyncSession,
    tenant_id: UUID,
    *,
    actor_id: UUID | None = None,
    membership_id: UUID | None = None,
) -> None:
    """Make every transaction on ``session`` use the normal tenant application role."""

    _configure_database_access(
        session,
        DatabaseAccessContext(
            path=DatabaseAccessPath.TENANT,
            tenant_id=tenant_id,
            actor_id=actor_id,
            membership_id=membership_id,
        ),
    )


def configure_platform_database_access(session: AsyncSession) -> None:
    """Make every transaction on ``session`` use the metadata-only platform role."""

    _configure_database_access(
        session,
        DatabaseAccessContext(path=DatabaseAccessPath.PLATFORM),
    )


def configure_authentication_database_access(session: AsyncSession) -> None:
    """Use the global-identity capability without gaining platform or HR access."""

    _configure_database_access(
        session,
        DatabaseAccessContext(path=DatabaseAccessPath.AUTHENTICATION),
    )


def database_access_context(session: AsyncSession) -> DatabaseAccessContext | None:
    """Return the immutable access context currently attached to a session."""

    return _resolved_database_access_context(session.sync_session)


def configure_database_command_context(
    session: AsyncSession,
    context: DatabaseCommandContext,
) -> None:
    """Attach one trusted command to the next root transaction on ``session``."""

    if not isinstance(context, DatabaseCommandContext):
        raise TypeError("context must be a DatabaseCommandContext")
    existing = database_command_context(session)
    if existing == context:
        return
    if existing is not None:
        raise RuntimeError("Database command context is immutable until the Unit of Work ends")
    if session.in_transaction():
        raise RuntimeError("Database command context must be configured before a transaction")

    access = database_access_context(session)
    if access is None or access.path is not DatabaseAccessPath.TENANT:
        raise RuntimeError("Database command context requires tenant database access")
    if (
        access.tenant_id != context.tenant_id
        or access.actor_id != context.actor_user_id
        or access.membership_id != context.membership_id
    ):
        raise RuntimeError("Database command context does not match tenant database access")
    session.sync_session.info[_DATABASE_COMMAND_CONTEXT_KEY] = context


def database_command_context(session: AsyncSession) -> DatabaseCommandContext | None:
    """Return the command capability waiting to bind to the next root transaction."""

    context = session.sync_session.info.get(_DATABASE_COMMAND_CONTEXT_KEY)
    if context is None:
        return None
    if not isinstance(context, DatabaseCommandContext):  # pragma: no cover - internal invariant
        raise RuntimeError("Database command context is corrupt")
    return context


def clear_database_command_context(session: AsyncSession) -> None:
    """Forget a completed command so the session can safely serve another Unit of Work."""

    session.sync_session.info.pop(_DATABASE_COMMAND_CONTEXT_KEY, None)


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
    transaction: object,
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

    command_context = session.info.get(_DATABASE_COMMAND_CONTEXT_KEY)
    if command_context is not None:
        if not isinstance(
            command_context, DatabaseCommandContext
        ):  # pragma: no cover - internal invariant
            raise RuntimeError("Database command context is corrupt")
        if context.path is not DatabaseAccessPath.TENANT or (
            context.tenant_id != command_context.tenant_id
            or context.actor_id != command_context.actor_user_id
            or context.membership_id != command_context.membership_id
        ):
            raise RuntimeError("Database command context does not match transaction access")
        if getattr(transaction, "parent", None) is None:
            _bind_database_command(connection, command_context)

    role = {
        DatabaseAccessPath.TENANT: TENANT_APPLICATION_ROLE,
        DatabaseAccessPath.PLATFORM: PLATFORM_APPLICATION_ROLE,
        DatabaseAccessPath.AUTHENTICATION: AUTHENTICATION_APPLICATION_ROLE,
    }[context.path]
    _set_local_role(connection, role)
    if context.path is DatabaseAccessPath.TENANT:
        tenant_id = context.tenant_id
        if tenant_id is None:  # pragma: no cover - dataclass invariant
            raise RuntimeError("Tenant database access context is missing tenant_id")
        # UUID validation at construction makes this literal safe. PostgreSQL SET has no bind
        # parameter form; LOCAL guarantees automatic reset at commit or rollback.
        connection.exec_driver_sql(f"SET LOCAL app.tenant_id = '{tenant_id}'")
        if context.actor_id is not None and context.membership_id is not None:
            connection.exec_driver_sql(f"SET LOCAL app.actor_id = '{context.actor_id}'")
            connection.exec_driver_sql(f"SET LOCAL app.membership_id = '{context.membership_id}'")


def _bind_database_command(connection: Connection, context: DatabaseCommandContext) -> None:
    connection.execute(
        text(
            """
            SELECT p4e_command.bind_database_command(
                CAST(:tenant_id AS uuid),
                CAST(:actor_user_id AS uuid),
                CAST(:membership_id AS uuid),
                CAST(:intent AS character varying),
                CAST(:target_id AS uuid),
                CAST(:audit_event_id AS uuid),
                CAST(:correlation_request_id AS character varying),
                CAST(:trace_id AS character varying),
                CAST(:session_id AS uuid)
            )
            """
        ),
        {
            "tenant_id": context.tenant_id,
            "actor_user_id": context.actor_user_id,
            "membership_id": context.membership_id,
            "intent": context.intent.value,
            "target_id": context.target_id,
            "audit_event_id": context.audit_event_id,
            "correlation_request_id": context.correlation_request_id,
            "trace_id": context.trace_id,
            "session_id": context.session_id,
        },
    )


def _set_local_role(connection: Connection, role: str) -> None:
    quoted_role = connection.dialect.identifier_preparer.quote(role)
    connection.exec_driver_sql(f"SET LOCAL ROLE {quoted_role}")


__all__ = [
    "AUTHENTICATION_APPLICATION_ROLE",
    "DatabaseAccessContext",
    "DatabaseCommandContext",
    "DatabaseCommandIntent",
    "DATABASE_ACCESS_CONTEXT_STATE_KEY",
    "DatabaseAccessPath",
    "MANAGED_DATABASE_SESSION_KEY",
    "MissingDatabaseAccessContextError",
    "PLATFORM_APPLICATION_ROLE",
    "TENANT_APPLICATION_ROLE",
    "attach_database_access_resolver",
    "configure_authentication_database_access",
    "configure_database_command_context",
    "configure_platform_database_access",
    "configure_tenant_database_access",
    "clear_database_command_context",
    "database_access_context",
    "database_command_context",
    "require_transaction_database_access",
]
