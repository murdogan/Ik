import asyncio
from logging.config import fileConfig
from typing import Any

from alembic import context
from alembic.ddl.postgresql import PostgresqlImpl
from app.db.base import Base
from app.models import (  # noqa: F401
    AuditEvent,
    AuthenticationRateLimitBucket,
    CommandIdempotency,
    DocumentType,
    Employee,
    EmployeeAccountLink,
    EmployeeDocument,
    EmployeeDocumentUploadIntent,
    EmployeeEmploymentProfile,
    EmployeePersonalProfile,
    EmployeeProfileChangeRequest,
    HolidayCalendar,
    HolidayEntry,
    Identity,
    LeaveBalanceLedger,
    LeaveBalanceSummary,
    LeavePolicy,
    LeaveRequest,
    LeaveRequestDay,
    LeaveRequestTimeline,
    LeaveType,
    MembershipRole,
    OrganizationSelectionChoice,
    OrganizationSelectionTransaction,
    OutboxEvent,
    RefreshSessionFamily,
    RefreshSessionToken,
    Tenant,
    TenantMembership,
    TenantSettings,
    User,
    UserActivationToken,
)
from sqlalchemy import String, pool
from sqlalchemy.ext.asyncio import async_engine_from_config
from sqlalchemy.sql.schema import Table


class ApplicationPostgresqlImpl(PostgresqlImpl):
    """Keep published migration identifiers intact beyond Alembic's 32-char default."""

    __dialect__ = "postgresql"

    def version_table_impl(
        self,
        *,
        version_table: str,
        version_table_schema: str | None,
        version_table_pk: bool,
        **kwargs: Any,
    ) -> Table:
        table = super().version_table_impl(
            version_table=version_table,
            version_table_schema=version_table_schema,
            version_table_pk=version_table_pk,
            **kwargs,
        )
        table.c.version_num.type = String(128)
        return table


config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        transaction_per_migration=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        transaction_per_migration=True,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    try:
        async with connectable.connect() as connection:
            await connection.run_sync(do_run_migrations)
    finally:
        await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
