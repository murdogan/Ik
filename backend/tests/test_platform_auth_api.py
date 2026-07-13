from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from uuid import UUID

import pytest
from app.core.auth_runtime import AUTH_RUNTIME_STATE_KEY, AuthRuntime
from app.core.config import Settings
from app.db.base import Base
from app.db.session import DATABASE_RUNTIME_STATE_KEY, DatabaseRuntime
from app.main import create_app
from app.models.audit import AuditEvent
from app.models.auth import PlatformRefreshSessionFamily
from app.models.identity import Identity, PlatformIdentityRole
from app.models.tenant import Tenant, TenantStatus
from app.models.user import User, UserStatus
from app.platform.authorization import ROLE_PERMISSION_CODES, ROLES_BY_CODE
from app.platform.identity import PasswordManager
from app.services.authorization_service import assign_system_role, seed_authorization_catalog
from app.services.identity_projection_service import sync_identity_membership_projection
from app.services.platform_authentication_service import (
    InvalidPlatformCredentialsError,
    PlatformAuthenticationService,
)
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

TENANT_ID = UUID("d4100000-0000-4000-8000-000000000001")
PLATFORM_ADMIN_ID = UUID("d4200000-0000-4000-8000-000000000001")
TENANT_ONLY_ID = UUID("d4200000-0000-4000-8000-000000000002")
PLATFORM_ADMIN_EMAIL = "platform.admin@wealthyfalcon.test"
TENANT_ONLY_EMAIL = "tenant.only@wealthyfalcon.test"
PLATFORM_ADMIN_PASSWORD = "P3D platform administrator credential"
TENANT_ONLY_PASSWORD = "P3D tenant-only user credential"


@dataclass(slots=True)
class PlatformAuthHarness:
    app: FastAPI
    client: AsyncClient
    session_factory: async_sessionmaker[AsyncSession]
    auth_runtime: AuthRuntime


@asynccontextmanager
async def _platform_auth_api() -> AsyncIterator[PlatformAuthHarness]:
    settings = Settings(
        _env_file=None,
        environment="test",
        database_url="sqlite+aiosqlite:///:memory:",
        auth_signing_key="p3d-test-signing-key-material-that-is-not-a-real-secret",
        frontend_base_url="http://frontend.test",
    )
    app = create_app(settings=settings)
    async with app.router.lifespan_context(app):
        database_runtime = getattr(app.state, DATABASE_RUNTIME_STATE_KEY)
        auth_runtime = getattr(app.state, AUTH_RUNTIME_STATE_KEY)
        assert isinstance(database_runtime, DatabaseRuntime)
        assert isinstance(auth_runtime, AuthRuntime)
        async with database_runtime.engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        await _seed(database_runtime.session_factory, auth_runtime.password_manager)
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://testserver",
        ) as client:
            yield PlatformAuthHarness(
                app=app,
                client=client,
                session_factory=database_runtime.session_factory,
                auth_runtime=auth_runtime,
            )


async def _seed(
    session_factory: async_sessionmaker[AsyncSession],
    password_manager: PasswordManager,
) -> None:
    async with session_factory.begin() as session:
        await seed_authorization_catalog(session)
        session.add(
            Tenant(
                id=TENANT_ID,
                slug="p3d-tenant",
                name="P3D Tenant",
                status=TenantStatus.ACTIVE.value,
                plan_code="core",
                data_region="tr-1",
                locale="en-US",
                timezone="UTC",
            )
        )
        session.add_all(
            [
                User(
                    id=PLATFORM_ADMIN_ID,
                    tenant_id=TENANT_ID,
                    email=PLATFORM_ADMIN_EMAIL,
                    full_name="Platform Administrator",
                    status=UserStatus.ACTIVE.value,
                    password_hash=password_manager.hash(PLATFORM_ADMIN_PASSWORD),
                ),
                User(
                    id=TENANT_ONLY_ID,
                    tenant_id=TENANT_ID,
                    email=TENANT_ONLY_EMAIL,
                    full_name="Tenant User",
                    status=UserStatus.ACTIVE.value,
                    password_hash=password_manager.hash(TENANT_ONLY_PASSWORD),
                ),
            ]
        )
        await session.flush()
        await assign_system_role(
            session,
            tenant_id=TENANT_ID,
            user_id=PLATFORM_ADMIN_ID,
            role_code="tenant_admin",
        )
        await assign_system_role(
            session,
            tenant_id=TENANT_ID,
            user_id=TENANT_ONLY_ID,
            role_code="employee",
        )
        for user_id in (PLATFORM_ADMIN_ID, TENANT_ONLY_ID):
            user = await session.get(User, user_id)
            assert user is not None
            await sync_identity_membership_projection(session, user)
        identity_id = await session.scalar(
            select(Identity.id).where(Identity.email_normalized == PLATFORM_ADMIN_EMAIL)
        )
        assert identity_id == PLATFORM_ADMIN_ID
        super_admin = ROLES_BY_CODE["super_admin"]
        session.add(
            PlatformIdentityRole(
                identity_id=identity_id,
                role_id=super_admin.id,
                role_scope_type="platform",
                active=True,
            )
        )


async def _tenant_login(client: AsyncClient) -> str:
    response = await client.post(
        "/api/v1/auth/login",
        json={"email": PLATFORM_ADMIN_EMAIL, "password": PLATFORM_ADMIN_PASSWORD},
    )
    assert response.status_code == 200
    return response.json()["data"]["access_token"]


async def _platform_login(client: AsyncClient) -> tuple[str, dict[str, object]]:
    response = await client.post(
        "/api/v1/platform/auth/login",
        json={"email": PLATFORM_ADMIN_EMAIL, "password": PLATFORM_ADMIN_PASSWORD},
    )
    assert response.status_code == 200, response.text
    return response.json()["data"]["access_token"], response.json()["data"]


async def test_platform_login_me_refresh_logout_and_realm_audiences_are_separate() -> None:
    async with _platform_auth_api() as harness:
        tenant_token = await _tenant_login(harness.client)
        platform_token, login = await _platform_login(harness.client)

        assert set(login) == {
            "status",
            "access_token",
            "token_type",
            "expires_in",
            "user",
        }
        assert login["status"] == "authenticated"
        user = login["user"]
        assert isinstance(user, dict)
        assert set(user) == {
            "id",
            "email",
            "full_name",
            "workspace_scope",
            "roles",
            "permissions",
            "permission_version",
            "authentication_strength",
        }
        assert user["workspace_scope"] == "platform"
        assert user["authentication_strength"] == "single_factor"
        assert [role["code"] for role in user["roles"]] == ["super_admin"]
        assert user["permissions"] == sorted(ROLE_PERMISSION_CODES["super_admin"])
        assert "tenant" not in user and "tenant_id" not in user
        assert harness.client.cookies.get("wf_refresh")
        assert harness.client.cookies.get("wf_platform_refresh")

        platform_me = await harness.client.get(
            "/api/v1/platform/me",
            headers={"Authorization": f"Bearer {platform_token}"},
        )
        assert platform_me.status_code == 200
        assert platform_me.json()["data"]["user"] == user

        platform_list = await harness.client.get(
            "/api/v1/platform/tenants",
            headers={"Authorization": f"Bearer {platform_token}"},
        )
        assert platform_list.status_code == 200

        tenant_token_on_platform = await harness.client.get(
            "/api/v1/platform/me",
            headers={"Authorization": f"Bearer {tenant_token}"},
        )
        assert tenant_token_on_platform.status_code == 403
        assert tenant_token_on_platform.json()["error"]["code"] == "platform_access_denied"

        platform_token_on_tenant = await harness.client.get(
            "/api/v1/me",
            headers={"Authorization": f"Bearer {platform_token}"},
        )
        assert platform_token_on_tenant.status_code == 401
        assert platform_token_on_tenant.json()["error"]["code"] == "authentication_required"

        old_platform_cookie = harness.client.cookies.get("wf_platform_refresh")
        refreshed = await harness.client.post("/api/v1/platform/auth/refresh")
        assert refreshed.status_code == 200
        refreshed_data = refreshed.json()["data"]
        refreshed_platform_token = refreshed_data["access_token"]
        assert refreshed_platform_token != platform_token
        assert harness.client.cookies.get("wf_platform_refresh") != old_platform_cookie

        tenant_refresh = await harness.client.post("/api/v1/auth/refresh")
        assert tenant_refresh.status_code == 200
        assert tenant_refresh.json()["data"]["user"]["workspace_scope"] == "tenant"

        logout = await harness.client.post(
            "/api/v1/platform/auth/logout",
            headers={"Authorization": f"Bearer {refreshed_platform_token}"},
        )
        assert logout.status_code == 204
        assert harness.client.cookies.get("wf_platform_refresh") is None
        assert harness.client.cookies.get("wf_refresh") is not None

        revoked_me = await harness.client.get(
            "/api/v1/platform/me",
            headers={"Authorization": f"Bearer {refreshed_platform_token}"},
        )
        assert revoked_me.status_code == 401
        tenant_me = await harness.client.get(
            "/api/v1/me",
            headers={
                "Authorization": f"Bearer {tenant_refresh.json()['data']['access_token']}"
            },
        )
        assert tenant_me.status_code == 200

        async with harness.session_factory() as session:
            platform_events = tuple(
                await session.scalars(
                    select(AuditEvent)
                    .where(AuditEvent.event_type.like("platform.%"))
                    .order_by(AuditEvent.occurred_at, AuditEvent.id)
                )
            )
        event_types = {event.event_type for event in platform_events}
        assert {
            "platform.auth.login.succeeded",
            "platform.session.started",
            "platform.session.refreshed",
            "platform.session.revoked",
        } <= event_types
        assert all(event.scope_type == "platform" for event in platform_events)
        assert all(event.tenant_id is None for event in platform_events)
        assert all(event.category == "platform_operations" for event in platform_events)
        serialized = " ".join(str(event.metadata_) for event in platform_events).lower()
        assert "password" not in serialized
        assert "token" not in serialized


async def test_platform_role_is_checked_after_credentials_without_org_selection(
) -> None:
    async with _platform_auth_api() as harness:
        denied = await harness.client.post(
            "/api/v1/platform/auth/login",
            json={"email": TENANT_ONLY_EMAIL, "password": TENANT_ONLY_PASSWORD},
        )
        assert denied.status_code == 403
        assert denied.json()["error"]["code"] == "platform_role_required"
        assert harness.client.cookies.get("wf_platform_refresh") is None
        assert "organizations" not in denied.text
        assert "selection_transaction" not in denied.text

        wrong_password = await harness.client.post(
            "/api/v1/platform/auth/login",
            json={"email": TENANT_ONLY_EMAIL, "password": "wrong platform password"},
        )
        assert wrong_password.status_code == 401
        assert wrong_password.json()["error"]["code"] == "invalid_credentials"

        async with harness.session_factory() as session:
            events = tuple(
                await session.scalars(
                    select(AuditEvent).where(
                        AuditEvent.event_type.in_(
                            ("platform.auth.login.denied", "platform.auth.login.failed")
                        )
                    )
                )
            )
        assert {event.event_type for event in events} == {
            "platform.auth.login.denied",
            "platform.auth.login.failed",
        }
        assert all(event.actor_user_id is None for event in events)
        assert all(event.resource_id is None for event in events)


async def test_platform_login_contract_forbids_tenant_and_organization_selectors() -> None:
    async with _platform_auth_api() as harness:
        for selector in (
            {"tenant_id": str(TENANT_ID)},
            {"organization_code": "p3d-tenant"},
            {"selection_key": str(TENANT_ID)},
        ):
            response = await harness.client.post(
                "/api/v1/platform/auth/login",
                json={
                    "email": PLATFORM_ADMIN_EMAIL,
                    "password": PLATFORM_ADMIN_PASSWORD,
                    **selector,
                },
            )
            assert response.status_code == 422
            assert response.json()["error"]["code"] == "auth_validation_error"
            assert harness.client.cookies.get("wf_platform_refresh") is None


async def test_reset_commit_blocks_in_flight_platform_login_session_start() -> None:
    async with _platform_auth_api() as harness:
        service = PlatformAuthenticationService(
            session_factory=harness.session_factory,
            password_manager=harness.auth_runtime.password_manager,
            access_tokens=harness.auth_runtime.platform_access_tokens,
            refresh_ttl=harness.auth_runtime.refresh_ttl,
        )
        replacement_password = "Replacement P3E platform credential"
        replacement_hash = harness.auth_runtime.password_manager.hash(replacement_password)
        original_start_session = service._sessions.start_session
        reset_committed = False

        async def start_session_after_reset(**kwargs: object):
            nonlocal reset_committed
            if not reset_committed:
                async with harness.session_factory.begin() as session:
                    identity = await session.scalar(
                        select(Identity).where(Identity.email_normalized == PLATFORM_ADMIN_EMAIL)
                    )
                    assert identity is not None
                    identity.password_hash = replacement_hash
                reset_committed = True
            return await original_start_session(**kwargs)

        service._sessions.start_session = start_session_after_reset  # type: ignore[method-assign]

        with pytest.raises(InvalidPlatformCredentialsError):
            await service.login(
                email=PLATFORM_ADMIN_EMAIL,
                password=PLATFORM_ADMIN_PASSWORD,
            )

        async with harness.session_factory() as session:
            families = tuple(await session.scalars(select(PlatformRefreshSessionFamily)))
        assert families == ()

        replacement_login = await service.login(
            email=PLATFORM_ADMIN_EMAIL,
            password=replacement_password,
        )
        assert replacement_login.user.email == PLATFORM_ADMIN_EMAIL


async def test_platform_refresh_reuse_revokes_only_the_platform_family() -> None:
    async with _platform_auth_api() as harness:
        await _tenant_login(harness.client)
        await _platform_login(harness.client)
        old_platform_cookie = harness.client.cookies.get("wf_platform_refresh")
        assert old_platform_cookie is not None

        first_rotation = await harness.client.post("/api/v1/platform/auth/refresh")
        assert first_rotation.status_code == 200
        assert harness.client.cookies.get("wf_platform_refresh") != old_platform_cookie

        async with AsyncClient(
            transport=ASGITransport(app=harness.app),
            base_url="http://testserver",
            cookies={"wf_platform_refresh": old_platform_cookie},
        ) as replay_client:
            replay = await replay_client.post("/api/v1/platform/auth/refresh")
        assert replay.status_code == 401
        assert replay.json()["error"]["code"] == "session_invalid"

        revoked_successor = await harness.client.post("/api/v1/platform/auth/refresh")
        assert revoked_successor.status_code == 401
        assert harness.client.cookies.get("wf_refresh") is not None

        async with harness.session_factory() as session:
            reuse_event = await session.scalar(
                select(AuditEvent).where(
                    AuditEvent.event_type == "platform.session.reuse_detected"
                )
            )
        assert reuse_event is not None
        assert reuse_event.result == "denied"
        assert reuse_event.scope_type == "platform"
