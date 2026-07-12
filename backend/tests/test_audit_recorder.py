from __future__ import annotations

from collections.abc import AsyncIterator
from uuid import UUID

import pytest
from app.db.base import Base
from app.models.audit import AuditEvent
from app.models.tenant import Tenant, TenantStatus
from app.models.user import User, UserStatus
from app.platform.audit import (
    AuditActorType,
    AuditCategory,
    AuditContext,
    AuditDataClassification,
    AuditEventDraft,
    AuditEventType,
    AuditScopeType,
    AuditVisibilityClass,
)
from app.platform.db import SqlAlchemyUnitOfWork, configure_tenant_database_access
from app.services.audit_recorder import SqlAlchemyAuditRecorder
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

TENANT_ID = UUID("a1000000-0000-4000-8000-000000000001")
ACTOR_ID = UUID("a2000000-0000-4000-8000-000000000001")
TARGET_ID = UUID("a2000000-0000-4000-8000-000000000002")


@pytest.fixture
async def audit_sessions() -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    async with sessions.begin() as session:
        session.add(
            Tenant(
                id=TENANT_ID,
                slug="audit-recorder",
                name="Audit Recorder Tenant",
                status=TenantStatus.ACTIVE.value,
                plan_code="core",
                data_region="tr-1",
                locale="en-US",
                timezone="UTC",
            )
        )
    try:
        yield sessions
    finally:
        await engine.dispose()


async def test_recorder_stores_only_allowlisted_redacted_metadata(
    audit_sessions: async_sessionmaker[AsyncSession],
) -> None:
    async with audit_sessions() as session:
        configure_tenant_database_access(session, TENANT_ID)
        recorder = SqlAlchemyAuditRecorder(session)

        async def operation() -> None:
            await recorder.record(
                AuditEventDraft(
                    scope_type=AuditScopeType.TENANT,
                    tenant_id=TENANT_ID,
                    actor_type=AuditActorType.USER,
                    actor_user_id=ACTOR_ID,
                    event_type=AuditEventType.ROLES_REPLACED,
                    category=AuditCategory.TENANT_ADMIN,
                    resource_type="user",
                    resource_id=TARGET_ID,
                    action="replace_roles",
                    context=AuditContext(
                        request_id="req-audit-redaction-001",
                        trace_id="0123456789abcdef0123456789abcdef",
                        ip_address="203.0.113.77",
                        user_agent=(
                            "Mozilla/5.0 sensitive fingerprint Chrome/140.0.0.0 "
                            "Cookie/private"
                        ),
                    ),
                    changed_fields=("roles", "permission_version", "password_hash"),
                    metadata={
                        "before_role_codes": ["employee"],
                        "after_role_codes": ["auditor"],
                        "permission_version": 2,
                        "password": "NeverPersistThisPassword",
                        "refresh_token": "NeverPersistThisToken",
                        "cookie": "NeverPersistThisCookie",
                        "employee_payload": {"salary": 999_999},
                        "before_data": {"email": "private@example.test"},
                    },
                    data_classification=AuditDataClassification.TENANT_ADMINISTRATION,
                    visibility_class=AuditVisibilityClass.TENANT_ADMIN,
                )
            )

        await SqlAlchemyUnitOfWork(session).execute(operation)

    async with audit_sessions() as session:
        event = await session.scalar(select(AuditEvent))
    assert event is not None
    assert event.changed_fields == ["permission_version", "roles"]
    assert event.metadata_ == {
        "after_role_codes": ["auditor"],
        "before_role_codes": ["employee"],
        "permission_version": 2,
    }
    assert event.before_data == {}
    assert event.after_data == {}
    assert event.ip_address == "203.0.113.0"
    assert event.user_agent == "Chrome"
    persisted_text = repr(event.metadata_).lower()
    for forbidden in (
        "neverpersist",
        "password",
        "token",
        "cookie",
        "salary",
        "private@example.test",
    ):
        assert forbidden not in persisted_text


async def test_audit_failure_rolls_back_the_domain_write(
    audit_sessions: async_sessionmaker[AsyncSession],
) -> None:
    async with audit_sessions() as session:
        configure_tenant_database_access(session, TENANT_ID)
        recorder = SqlAlchemyAuditRecorder(session)

        async def operation() -> None:
            session.add(
                User(
                    id=TARGET_ID,
                    tenant_id=TENANT_ID,
                    email="rollback@example.test",
                    full_name="Must Roll Back",
                    status=UserStatus.INVITED.value,
                    password_hash=None,
                )
            )
            await session.flush()
            await recorder.record(
                AuditEventDraft(
                    scope_type=AuditScopeType.TENANT,
                    tenant_id=TENANT_ID,
                    actor_type=AuditActorType.USER,
                    actor_user_id=ACTOR_ID,
                    event_type=AuditEventType.INVITATION_CREATED,
                    category=AuditCategory.TENANT_ADMIN,
                    resource_type="user",
                    resource_id=TARGET_ID,
                    action="invite",
                    context=AuditContext(
                        request_id="private@example.test",
                        trace_id="0123456789abcdef0123456789abcdef",
                    ),
                )
            )

        with pytest.raises(ValueError, match="request_id"):
            await SqlAlchemyUnitOfWork(session).execute(operation)

    async with audit_sessions() as session:
        assert await session.get(User, TARGET_ID) is None
        assert await session.scalar(select(AuditEvent.id)) is None
