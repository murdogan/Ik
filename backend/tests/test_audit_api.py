from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from app.api.dependencies import get_platform_principal
from app.core.auth_runtime import AUTH_RUNTIME_STATE_KEY, AuthRuntime
from app.core.config import Settings
from app.db.base import Base
from app.db.session import DATABASE_RUNTIME_STATE_KEY, DatabaseRuntime
from app.main import create_app
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
from app.platform.principals import PlatformPrincipal
from app.services.audit_recorder import SqlAlchemyAuditRecorder
from app.services.authorization_service import assign_system_role, seed_authorization_catalog
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

TENANT_A_ID = UUID("b1000000-0000-4000-8000-000000000001")
TENANT_B_ID = UUID("b1000000-0000-4000-8000-000000000002")
ADMIN_ID = UUID("b2000000-0000-4000-8000-000000000001")
EMPLOYEE_ID = UUID("b2000000-0000-4000-8000-000000000002")
TENANT_A_EVENT_ID = UUID("b3000000-0000-4000-8000-000000000001")
TENANT_B_EVENT_ID = UUID("b3000000-0000-4000-8000-000000000002")
PLATFORM_EVENT_ID = UUID("b3000000-0000-4000-8000-000000000003")
PASSWORD = "F2E audit API test credential"


@dataclass(slots=True)
class AuditApiHarness:
    app: FastAPI
    client: AsyncClient
    session_factory: async_sessionmaker[AsyncSession]


@asynccontextmanager
async def _audit_api() -> AsyncIterator[AuditApiHarness]:
    app = create_app(
        settings=Settings(
            _env_file=None,
            environment="test",
            database_url="sqlite+aiosqlite:///:memory:",
            auth_signing_key="f2e-audit-signing-material-that-is-not-a-real-secret",
            frontend_base_url="http://frontend.test",
        )
    )
    async with app.router.lifespan_context(app):
        runtime = getattr(app.state, DATABASE_RUNTIME_STATE_KEY)
        auth_runtime = getattr(app.state, AUTH_RUNTIME_STATE_KEY)
        assert isinstance(runtime, DatabaseRuntime)
        assert isinstance(auth_runtime, AuthRuntime)
        async with runtime.engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        await _seed(runtime.session_factory, auth_runtime)
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://testserver",
        ) as client:
            yield AuditApiHarness(app=app, client=client, session_factory=runtime.session_factory)


async def _seed(
    sessions: async_sessionmaker[AsyncSession],
    auth_runtime: AuthRuntime,
) -> None:
    password_hash = auth_runtime.password_manager.hash(PASSWORD)
    async with sessions.begin() as session:
        await seed_authorization_catalog(session)
        session.add_all(
            [
                Tenant(
                    id=TENANT_A_ID,
                    slug="audit-a",
                    name="Audit Tenant A",
                    status=TenantStatus.ACTIVE.value,
                    plan_code="core",
                    data_region="tr-1",
                    locale="en-US",
                    timezone="UTC",
                ),
                Tenant(
                    id=TENANT_B_ID,
                    slug="audit-b",
                    name="Audit Tenant B",
                    status=TenantStatus.ACTIVE.value,
                    plan_code="core",
                    data_region="tr-1",
                    locale="en-US",
                    timezone="UTC",
                ),
                User(
                    id=ADMIN_ID,
                    tenant_id=TENANT_A_ID,
                    email="admin@audit-a.test",
                    full_name="Audit Administrator",
                    status=UserStatus.ACTIVE.value,
                    password_hash=password_hash,
                ),
                User(
                    id=EMPLOYEE_ID,
                    tenant_id=TENANT_A_ID,
                    email="employee@audit-a.test",
                    full_name="Audit Employee",
                    status=UserStatus.ACTIVE.value,
                    password_hash=password_hash,
                ),
            ]
        )
        await session.flush()
        await assign_system_role(
            session,
            tenant_id=TENANT_A_ID,
            user_id=ADMIN_ID,
            role_code="tenant_admin",
        )
        await assign_system_role(
            session,
            tenant_id=TENANT_A_ID,
            user_id=EMPLOYEE_ID,
            role_code="employee",
        )
        recorder = SqlAlchemyAuditRecorder(session)
        await recorder.record(
            _event(
                event_id=TENANT_A_EVENT_ID,
                scope_type=AuditScopeType.TENANT,
                tenant_id=TENANT_A_ID,
                event_type=AuditEventType.INVITATION_CREATED,
                category=AuditCategory.TENANT_ADMIN,
                actor_user_id=ADMIN_ID,
                resource_id=EMPLOYEE_ID,
                occurred_at=datetime(2026, 7, 12, 9, 2, tzinfo=UTC),
            )
        )
        await recorder.record(
            _event(
                event_id=TENANT_B_EVENT_ID,
                scope_type=AuditScopeType.TENANT,
                tenant_id=TENANT_B_ID,
                event_type=AuditEventType.ROLES_REPLACED,
                category=AuditCategory.TENANT_ADMIN,
                actor_user_id=None,
                resource_id=None,
                occurred_at=datetime(2026, 7, 12, 9, 1, tzinfo=UTC),
            )
        )
        await recorder.record(
            _event(
                event_id=PLATFORM_EVENT_ID,
                scope_type=AuditScopeType.PLATFORM,
                tenant_id=None,
                event_type=AuditEventType.PLATFORM_TENANT_CREATED,
                category=AuditCategory.PLATFORM_OPERATIONS,
                actor_user_id=None,
                resource_id=TENANT_B_ID,
                occurred_at=datetime(2026, 7, 12, 9, 0, tzinfo=UTC),
            )
        )


def _event(
    *,
    event_id: UUID,
    scope_type: AuditScopeType,
    tenant_id: UUID | None,
    event_type: AuditEventType,
    category: AuditCategory,
    actor_user_id: UUID | None,
    resource_id: UUID | None,
    occurred_at: datetime,
) -> AuditEventDraft:
    is_platform = scope_type is AuditScopeType.PLATFORM
    return AuditEventDraft(
        id=event_id,
        occurred_at=occurred_at,
        scope_type=scope_type,
        tenant_id=tenant_id,
        actor_type=(AuditActorType.PLATFORM_ADMIN if is_platform else AuditActorType.USER),
        actor_user_id=actor_user_id,
        event_type=event_type,
        category=category,
        resource_type="tenant" if is_platform else "user",
        resource_id=resource_id,
        action="create" if is_platform else "change",
        context=AuditContext(
            request_id=f"req-{event_id.hex}",
            trace_id=event_id.hex,
        ),
        data_classification=(
            AuditDataClassification.PLATFORM_METADATA
            if is_platform
            else AuditDataClassification.TENANT_ADMINISTRATION
        ),
        visibility_class=(
            AuditVisibilityClass.PLATFORM_OPS
            if is_platform
            else AuditVisibilityClass.TENANT_ADMIN
        ),
    )


async def _login(client: AsyncClient, email: str) -> str:
    response = await client.post(
        "/api/v1/auth/login",
        json={"tenant_slug": "audit-a", "email": email, "password": PASSWORD},
    )
    assert response.status_code == 200
    return response.json()["data"]["access_token"]


def _authorization(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def test_tenant_admin_lists_details_and_pages_only_own_redacted_events() -> None:
    async with _audit_api() as harness:
        access_token = await _login(harness.client, "admin@audit-a.test")
        headers = _authorization(access_token)

        first = await harness.client.get(
            "/api/v1/audit-events?limit=1",
            headers=headers,
        )
        assert first.status_code == 200
        assert first.headers["Cache-Control"] == "no-store"
        body = first.json()
        assert len(body["data"]) == 1
        assert body["data"][0]["scope_type"] == "tenant"
        assert body["data"][0]["tenant_id"] == str(TENANT_A_ID)
        assert body["meta"]["next_cursor"]

        second = await harness.client.get(
            "/api/v1/audit-events",
            params={"limit": 1, "cursor": body["meta"]["next_cursor"]},
            headers=headers,
        )
        assert second.status_code == 200
        assert second.json()["data"]
        assert all(
            event["tenant_id"] == str(TENANT_A_ID)
            for event in second.json()["data"]
        )

        detail = await harness.client.get(
            f"/api/v1/audit-events/{TENANT_A_EVENT_ID}",
            headers=headers,
        )
        assert detail.status_code == 200
        assert detail.json()["data"]["id"] == str(TENANT_A_EVENT_ID)
        serialized = detail.text.lower()
        assert "password" not in serialized
        assert "token" not in serialized
        assert "cookie" not in serialized

        cross_tenant = await harness.client.get(
            f"/api/v1/audit-events/{TENANT_B_EVENT_ID}",
            headers=headers,
        )
        assert cross_tenant.status_code == 404
        assert cross_tenant.json()["error"]["code"] == "audit_event_not_found"


async def test_employee_is_denied_tenant_and_platform_audit_surfaces() -> None:
    async with _audit_api() as harness:
        access_token = await _login(harness.client, "employee@audit-a.test")
        headers = _authorization(access_token)

        tenant_response = await harness.client.get("/api/v1/audit-events", headers=headers)
        detail_response = await harness.client.get(
            f"/api/v1/audit-events/{TENANT_A_EVENT_ID}",
            headers=headers,
        )
        platform_response = await harness.client.get(
            "/api/v1/platform/audit-events",
            headers=headers,
        )

        assert tenant_response.status_code == 403
        assert detail_response.status_code == 403
        assert platform_response.status_code == 403
        assert tenant_response.json()["error"]["code"] == "authorization_denied"
        assert platform_response.json()["error"]["code"] == "platform_access_denied"


async def test_trusted_platform_principal_sees_only_platform_events() -> None:
    async with _audit_api() as harness:
        harness.app.dependency_overrides[get_platform_principal] = lambda: PlatformPrincipal(
            source="f2e-audit-api-test"
        )
        response = await harness.client.get("/api/v1/platform/audit-events")

        assert response.status_code == 200
        events = response.json()["data"]
        assert [event["id"] for event in events] == [str(PLATFORM_EVENT_ID)]
        assert all(event["scope_type"] == "platform" for event in events)
        assert all(event["tenant_id"] is None for event in events)
