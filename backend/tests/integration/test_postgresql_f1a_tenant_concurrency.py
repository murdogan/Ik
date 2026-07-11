from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from alembic import command as alembic_command
from alembic.config import Config
from app.api.errors import application_error_to_api_error
from app.models.tenant import Tenant, TenantSettings
from app.platform.db import PersistenceConcurrencyError, SqlAlchemyUnitOfWork
from app.schemas.tenant import (
    TenantPlatformCreate,
    TenantPlatformUpdate,
    TenantSettingsUpdate,
)
from app.services.tenant_commands import TenantCommandHandler
from app.services.tenant_service import (
    DuplicateTenantSlugError,
    TenantLifecycleConflictError,
    TenantService,
)
from sqlalchemy import func, select, text
from sqlalchemy.engine import URL
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

pytestmark = pytest.mark.postgres

ROOT = Path(__file__).resolve().parents[3]
ALEMBIC_INI = ROOT / "alembic.ini"


@pytest.fixture
def f1a_migrated_postgres_database(postgres_database_url: URL) -> URL:
    alembic_command.upgrade(_alembic_config(postgres_database_url), "head")
    return postgres_database_url


def test_concurrent_same_slug_provisioning_has_one_atomic_winner(
    f1a_migrated_postgres_database: URL,
) -> None:
    asyncio.run(_assert_same_slug_provisioning_race(f1a_migrated_postgres_database))


def test_lifecycle_update_lock_serializes_against_committed_status(
    f1a_migrated_postgres_database: URL,
) -> None:
    asyncio.run(_assert_lifecycle_lock_serialization(f1a_migrated_postgres_database))


def test_settings_update_lock_prevents_lost_partial_updates(
    f1a_migrated_postgres_database: URL,
) -> None:
    asyncio.run(_assert_settings_lock_serialization(f1a_migrated_postgres_database))


async def _assert_same_slug_provisioning_race(database_url: URL) -> None:
    engine = create_async_engine(database_url, poolclass=NullPool)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    barrier = _AvailabilityBarrier()
    slug = f"f1a-concurrent-{uuid4().hex}"
    payload = TenantPlatformCreate(slug=slug, name="Concurrent Tenant")
    try:
        async def provision() -> object:
            async with session_factory() as session:
                handler = TenantCommandHandler(
                    service=_BarrierTenantService(session, barrier),
                    unit_of_work=SqlAlchemyUnitOfWork(session),
                )
                return await handler.create_tenant(payload)

        outcomes = await asyncio.wait_for(
            asyncio.gather(provision(), provision(), return_exceptions=True),
            timeout=10,
        )
        successes = [outcome for outcome in outcomes if not isinstance(outcome, BaseException)]
        failures = [outcome for outcome in outcomes if isinstance(outcome, BaseException)]

        assert len(successes) == 1
        assert len(failures) == 1
        assert isinstance(failures[0], DuplicateTenantSlugError)
        api_error = application_error_to_api_error(failures[0])
        assert api_error.status_code == 409
        assert api_error.code == "tenant_slug_conflict"

        winner = successes[0]
        assert isinstance(winner, Tenant)
        async with session_factory() as session:
            tenant_count = await session.scalar(
                select(func.count()).select_from(Tenant).where(Tenant.slug == slug)
            )
            settings_count = await session.scalar(
                select(func.count())
                .select_from(TenantSettings)
                .where(TenantSettings.tenant_id == winner.id)
            )
        assert tenant_count == 1
        assert settings_count == 1
    finally:
        await engine.dispose()


async def _assert_lifecycle_lock_serialization(database_url: URL) -> None:
    engine = create_async_engine(database_url, poolclass=NullPool)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    tenant_id = uuid4()
    try:
        await _insert_tenant_with_settings(engine, tenant_id)
        async with session_factory() as locking_session:
            async with locking_session.begin():
                locked = await TenantService(locking_session).update_tenant(
                    tenant_id,
                    TenantPlatformUpdate(status="offboarding"),
                )
                assert locked.status == "offboarding"

                async with session_factory() as competing_session:
                    handler = TenantCommandHandler(
                        service=_LockTimeoutTenantService(competing_session),
                        unit_of_work=SqlAlchemyUnitOfWork(competing_session),
                    )
                    with pytest.raises(PersistenceConcurrencyError) as lock_error:
                        await handler.update_tenant(
                            tenant_id,
                            TenantPlatformUpdate(status="suspended"),
                        )
                    assert lock_error.value.sqlstate == "55P03"

        async with session_factory() as retry_session:
            retry_handler = TenantCommandHandler(
                service=TenantService(retry_session),
                unit_of_work=SqlAlchemyUnitOfWork(retry_session),
            )
            with pytest.raises(TenantLifecycleConflictError):
                await retry_handler.update_tenant(
                    tenant_id,
                    TenantPlatformUpdate(status="suspended"),
                )

        async with session_factory() as verification_session:
            persisted = await verification_session.get(Tenant, tenant_id)
            assert persisted is not None
            assert persisted.status == "offboarding"
    finally:
        await engine.dispose()


async def _assert_settings_lock_serialization(database_url: URL) -> None:
    engine = create_async_engine(database_url, poolclass=NullPool)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    tenant_id = uuid4()
    try:
        await _insert_tenant_with_settings(engine, tenant_id)
        async with session_factory() as locking_session:
            async with locking_session.begin():
                first = await TenantService(locking_session).update_tenant_settings(
                    tenant_id,
                    TenantSettingsUpdate(week_start_day="sunday"),
                )
                assert first.week_start_day == "sunday"

                async with session_factory() as competing_session:
                    handler = TenantCommandHandler(
                        service=_LockTimeoutTenantService(competing_session),
                        unit_of_work=SqlAlchemyUnitOfWork(competing_session),
                    )
                    with pytest.raises(PersistenceConcurrencyError) as lock_error:
                        await handler.update_tenant_settings(
                            tenant_id,
                            TenantSettingsUpdate(date_format="YYYY-MM-DD"),
                        )
                    assert lock_error.value.sqlstate == "55P03"

        async with session_factory() as retry_session:
            retry_handler = TenantCommandHandler(
                service=TenantService(retry_session),
                unit_of_work=SqlAlchemyUnitOfWork(retry_session),
            )
            retried = await retry_handler.update_tenant_settings(
                tenant_id,
                TenantSettingsUpdate(date_format="YYYY-MM-DD"),
            )
            assert retried.week_start_day == "sunday"
            assert retried.date_format == "YYYY-MM-DD"
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


class _BarrierTenantService(TenantService):
    def __init__(self, session: AsyncSession, barrier: _AvailabilityBarrier) -> None:
        super().__init__(session)
        self.barrier = barrier

    async def _ensure_tenant_slug_available(self, slug: str) -> None:
        await super()._ensure_tenant_slug_available(slug)
        await self.barrier.wait()


class _LockTimeoutTenantService(TenantService):
    async def _get_tenant_for_update(self, tenant_id: UUID) -> Tenant:
        await self.session.execute(text("set local lock_timeout = '100ms'"))
        return await super()._get_tenant_for_update(tenant_id)


async def _insert_tenant_with_settings(engine, tenant_id: UUID) -> None:
    async with engine.begin() as connection:
        await connection.execute(
            text(
                "insert into tenants ("
                "id, slug, name, status, plan_code, data_region, locale, timezone"
                ") values ("
                ":id, :slug, 'F1A concurrency tenant', 'active', 'core', 'tr-1', "
                "'tr-TR', 'Europe/Istanbul'"
                ")"
            ),
            {"id": tenant_id, "slug": f"f1a-concurrency-{uuid4().hex}"},
        )
        await connection.execute(
            text(
                "insert into tenant_settings ("
                "tenant_id, week_start_day, date_format, time_format"
                ") values ("
                ":tenant_id, 'monday', 'DD.MM.YYYY', '24h'"
                ")"
            ),
            {"tenant_id": tenant_id},
        )


def _alembic_config(database_url: URL) -> Config:
    config = Config(str(ALEMBIC_INI))
    config.set_main_option(
        "sqlalchemy.url",
        database_url.render_as_string(hide_password=False).replace("%", "%%"),
    )
    return config
