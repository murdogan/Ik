"""Database transaction capabilities; runtime wiring remains at the compatibility path."""

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
    "PersistenceConcurrencyError",
    "PersistenceError",
    "PersistenceIntegrityError",
    "SqlAlchemyUnitOfWork",
    "UnitOfWork",
    "constraint_name_from_error",
    "sqlstate_from_error",
    "translate_persistence_error",
]
