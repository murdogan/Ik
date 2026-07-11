"""Database transaction capabilities; runtime wiring remains at the compatibility path."""

from app.platform.db.tenant_access import (
    DatabaseAccessContext,
    DatabaseAccessPath,
    MissingDatabaseAccessContextError,
    attach_database_access_resolver,
    configure_platform_database_access,
    configure_tenant_database_access,
    database_access_context,
)
from app.platform.db.unit_of_work import (
    PersistenceConcurrencyError,
    PersistenceError,
    PersistenceIntegrityError,
    SqlAlchemyUnitOfWork,
    UnitOfWork,
    constraint_name_from_error,
    sqlstate_from_error,
    translate_persistence_error,
)

__all__ = [
    "DatabaseAccessContext",
    "DatabaseAccessPath",
    "MissingDatabaseAccessContextError",
    "PersistenceConcurrencyError",
    "PersistenceError",
    "PersistenceIntegrityError",
    "SqlAlchemyUnitOfWork",
    "UnitOfWork",
    "attach_database_access_resolver",
    "configure_platform_database_access",
    "configure_tenant_database_access",
    "constraint_name_from_error",
    "database_access_context",
    "sqlstate_from_error",
    "translate_persistence_error",
]
