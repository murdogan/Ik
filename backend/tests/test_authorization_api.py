from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from uuid import UUID

from app.core.auth_runtime import AUTH_RUNTIME_STATE_KEY, AuthRuntime
from app.core.config import Settings
from app.db.base import Base
from app.db.session import DATABASE_RUNTIME_STATE_KEY, DatabaseRuntime
from app.main import create_app
from app.models.tenant import Tenant, TenantStatus
from app.models.user import User, UserStatus
from app.platform.authorization import PERMISSIONS, ROLES, ROLES_BY_CODE
from app.platform.identity import PasswordManager
from app.services.authorization_service import (
    assign_system_role,
    load_authorization_snapshot,
    seed_authorization_catalog,
)
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

TENANT_A_ID = UUID("d4100000-0000-4000-8000-000000000001")
TENANT_B_ID = UUID("d4100000-0000-4000-8000-000000000002")
ADMIN_ID = UUID("d4200000-0000-4000-8000-000000000001")
EMPLOYEE_ID = UUID("d4200000-0000-4000-8000-000000000002")
OTHER_TENANT_USER_ID = UUID("d4200000-0000-4000-8000-000000000003")

ADMIN_EMAIL = "admin@authorization-a.test"
EMPLOYEE_EMAIL = "employee@authorization-a.test"
PASSWORD = "F2D authorization API test password"


@dataclass(slots=True)
class AuthorizationApiHarness:
    app: FastAPI
    client: AsyncClient
    session_factory: async_sessionmaker[AsyncSession]


@asynccontextmanager
async def _authorization_api() -> AsyncIterator[AuthorizationApiHarness]:
    settings = Settings(
        _env_file=None,
        environment="test",
        database_url="sqlite+aiosqlite:///:memory:",
        auth_signing_key="f2d-test-signing-key-material-that-is-not-a-real-secret",
        frontend_base_url="http://frontend.test",
    )
    app = create_app(settings=settings)
    async with app.router.lifespan_context(app):
        runtime = getattr(app.state, DATABASE_RUNTIME_STATE_KEY)
        auth_runtime = getattr(app.state, AUTH_RUNTIME_STATE_KEY)
        assert isinstance(runtime, DatabaseRuntime)
        assert isinstance(auth_runtime, AuthRuntime)
        async with runtime.engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        await _seed_authorization_fixtures(
            runtime.session_factory,
            auth_runtime.password_manager,
        )

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://testserver",
        ) as client:
            yield AuthorizationApiHarness(
                app=app,
                client=client,
                session_factory=runtime.session_factory,
            )


async def _seed_authorization_fixtures(
    session_factory: async_sessionmaker[AsyncSession],
    passwords: PasswordManager,
) -> None:
    password_hash = passwords.hash(PASSWORD)
    async with session_factory.begin() as session:
        await seed_authorization_catalog(session)
        session.add_all(
            [
                Tenant(
                    id=TENANT_A_ID,
                    slug="authorization-a",
                    name="Authorization Tenant A",
                    status=TenantStatus.ACTIVE.value,
                    plan_code="core",
                    data_region="tr-1",
                    locale="en-US",
                    timezone="UTC",
                ),
                Tenant(
                    id=TENANT_B_ID,
                    slug="authorization-b",
                    name="Authorization Tenant B",
                    status=TenantStatus.ACTIVE.value,
                    plan_code="core",
                    data_region="tr-1",
                    locale="en-US",
                    timezone="UTC",
                ),
                User(
                    id=ADMIN_ID,
                    tenant_id=TENANT_A_ID,
                    email=ADMIN_EMAIL,
                    full_name="Tenant Administrator",
                    status=UserStatus.ACTIVE.value,
                    password_hash=password_hash,
                    can_invite_users=True,
                ),
                User(
                    id=EMPLOYEE_ID,
                    tenant_id=TENANT_A_ID,
                    email=EMPLOYEE_EMAIL,
                    full_name="Tenant Employee",
                    status=UserStatus.ACTIVE.value,
                    password_hash=password_hash,
                ),
                User(
                    id=OTHER_TENANT_USER_ID,
                    tenant_id=TENANT_B_ID,
                    email="employee@authorization-b.test",
                    full_name="Other Tenant Employee",
                    status=UserStatus.ACTIVE.value,
                    password_hash=password_hash,
                ),
            ]
        )
        await session.flush()
        for tenant_id, user_id, role_code in (
            (TENANT_A_ID, ADMIN_ID, "tenant_admin"),
            (TENANT_A_ID, EMPLOYEE_ID, "employee"),
            (TENANT_B_ID, OTHER_TENANT_USER_ID, "employee"),
        ):
            await assign_system_role(
                session,
                tenant_id=tenant_id,
                user_id=user_id,
                role_code=role_code,
            )


async def _login(client: AsyncClient, *, email: str) -> tuple[str, dict[str, object]]:
    response = await client.post(
        "/api/v1/auth/login",
        json={
            "tenant_slug": "authorization-a",
            "email": email,
            "password": PASSWORD,
        },
    )
    assert response.status_code == 200
    data = response.json()["data"]
    return data["access_token"], data["user"]


def _authorization(access_token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {access_token}"}


async def test_tenant_admin_reads_only_tenant_role_and_permission_catalogs() -> None:
    async with _authorization_api() as harness:
        access_token, user = await _login(harness.client, email=ADMIN_EMAIL)
        headers = _authorization(access_token)

        assert [role["code"] for role in user["roles"]] == ["tenant_admin"]
        assert user["workspace_scope"] == "tenant"

        roles_response = await harness.client.get("/api/v1/roles", headers=headers)
        permissions_response = await harness.client.get(
            "/api/v1/permissions",
            headers=headers,
        )

        assert roles_response.status_code == 200
        assert roles_response.headers["Cache-Control"] == "no-store"
        roles = roles_response.json()["data"]
        assert {role["code"] for role in roles} == {
            role.code for role in ROLES if role.scope_type.value == "tenant"
        }
        assert all(role["scope_type"] == "tenant" for role in roles)
        assert "super_admin" not in {role["code"] for role in roles}
        tenant_admin = next(role for role in roles if role["code"] == "tenant_admin")
        assert {
            "user:read:tenant",
            "user:invite:tenant",
            "role:read:tenant",
            "role:assign:tenant",
            "permission:read:tenant",
        } <= set(tenant_admin["permissions"])
        assert not any(
            permission.startswith(("employee:", "leave:"))
            or permission.endswith(":platform")
            for permission in tenant_admin["permissions"]
        )

        platform_denied = await harness.client.get(
            "/api/v1/platform/tenants",
            headers=headers,
        )
        assert platform_denied.status_code == 403
        assert platform_denied.json()["error"]["code"] == "platform_access_denied"

        assert permissions_response.status_code == 200
        assert permissions_response.headers["Cache-Control"] == "no-store"
        permissions = permissions_response.json()["data"]
        assert {permission["code"] for permission in permissions} == {
            permission.code
            for permission in PERMISSIONS
            if permission.name.target != "platform"
        }
        assert all(permission["scope"] != "platform" for permission in permissions)


async def test_employee_is_denied_every_tenant_administration_surface() -> None:
    async with _authorization_api() as harness:
        access_token, user = await _login(harness.client, email=EMPLOYEE_EMAIL)
        headers = _authorization(access_token)
        employee_role_id = ROLES_BY_CODE["employee"].id

        assert [role["code"] for role in user["roles"]] == ["employee"]

        attempts = (
            (
                await harness.client.get("/api/v1/users", headers=headers),
                "user_administration_access_denied",
            ),
            (
                await harness.client.post(
                    "/api/v1/users/invitations",
                    headers=headers,
                    json={"email": "denied@test.example", "full_name": "Denied Invite"},
                ),
                "invitation_access_denied",
            ),
            (
                await harness.client.get("/api/v1/roles", headers=headers),
                "authorization_denied",
            ),
            (
                await harness.client.get("/api/v1/permissions", headers=headers),
                "authorization_denied",
            ),
            (
                await harness.client.put(
                    f"/api/v1/users/{EMPLOYEE_ID}/roles",
                    headers=headers,
                    json={"role_ids": [str(employee_role_id)]},
                ),
                "user_administration_access_denied",
            ),
        )

        for response, expected_code in attempts:
            assert response.status_code == 403
            assert response.json()["error"]["code"] == expected_code


async def test_reinvitation_preserves_an_exact_role_replacement() -> None:
    async with _authorization_api() as harness:
        admin_access, _admin = await _login(harness.client, email=ADMIN_EMAIL)
        headers = _authorization(admin_access)
        invitation_payload = {
            "email": "pending.reinvite@authorization-a.test",
            "full_name": "Pending Reinvite",
        }

        invited = await harness.client.post(
            "/api/v1/users/invitations",
            headers=headers,
            json=invitation_payload,
        )
        assert invited.status_code == 201
        invited_user_id = invited.json()["data"]["user"]["id"]

        replaced = await harness.client.put(
            f"/api/v1/users/{invited_user_id}/roles",
            headers=headers,
            json={"role_ids": [str(ROLES_BY_CODE["auditor"].id)]},
        )
        assert replaced.status_code == 200
        assert [role["code"] for role in replaced.json()["data"]["roles"]] == [
            "auditor"
        ]

        reinvited = await harness.client.post(
            "/api/v1/users/invitations",
            headers=headers,
            json=invitation_payload,
        )
        assert reinvited.status_code == 201
        detail = await harness.client.get(
            f"/api/v1/users/{invited_user_id}",
            headers=headers,
        )
        assert detail.status_code == 200
        assert [role["code"] for role in detail.json()["data"]["roles"]] == ["auditor"]
        assert detail.json()["data"]["permission_version"] == 2


async def test_role_replacement_is_exact_idempotent_isolated_and_invalidates_access() -> None:
    async with _authorization_api() as harness:
        async with AsyncClient(
            transport=ASGITransport(app=harness.app),
            base_url="http://testserver",
        ) as employee_client:
            old_employee_access, old_employee = await _login(
                employee_client,
                email=EMPLOYEE_EMAIL,
            )
            admin_access, _admin = await _login(harness.client, email=ADMIN_EMAIL)
            admin_headers = _authorization(admin_access)
            employee_role_id = ROLES_BY_CODE["employee"].id
            tenant_admin_role_id = ROLES_BY_CODE["tenant_admin"].id
            platform_role_id = ROLES_BY_CODE["super_admin"].id

            assert old_employee["permission_version"] == 1
            assert [role["code"] for role in old_employee["roles"]] == ["employee"]

            platform_rejected = await harness.client.put(
                f"/api/v1/users/{EMPLOYEE_ID}/roles",
                headers=admin_headers,
                json={"role_ids": [str(platform_role_id)]},
            )
            assert platform_rejected.status_code == 422
            assert platform_rejected.json()["error"]["code"] == "role_assignment_invalid"

            cross_tenant = await harness.client.put(
                f"/api/v1/users/{OTHER_TENANT_USER_ID}/roles",
                headers=admin_headers,
                json={"role_ids": [str(tenant_admin_role_id)]},
            )
            assert cross_tenant.status_code == 404
            assert cross_tenant.json()["error"]["code"] == "user_not_found"

            replaced = await harness.client.put(
                f"/api/v1/users/{EMPLOYEE_ID}/roles",
                headers=admin_headers,
                json={"role_ids": [str(tenant_admin_role_id)]},
            )
            assert replaced.status_code == 200
            replacement = replaced.json()["data"]
            assert [role["code"] for role in replacement["roles"]] == ["tenant_admin"]
            assert replacement["permission_version"] == 2

            idempotent = await harness.client.put(
                f"/api/v1/users/{EMPLOYEE_ID}/roles",
                headers=admin_headers,
                json={"role_ids": [str(tenant_admin_role_id)]},
            )
            assert idempotent.status_code == 200
            assert [role["code"] for role in idempotent.json()["data"]["roles"]] == [
                "tenant_admin"
            ]
            assert idempotent.json()["data"]["permission_version"] == 2

            async with harness.session_factory() as session:
                employee = await session.get(User, EMPLOYEE_ID)
                other_user = await session.get(User, OTHER_TENANT_USER_ID)
                employee_authorization = await load_authorization_snapshot(
                    session,
                    tenant_id=TENANT_A_ID,
                    user_id=EMPLOYEE_ID,
                )
                other_authorization = await load_authorization_snapshot(
                    session,
                    tenant_id=TENANT_B_ID,
                    user_id=OTHER_TENANT_USER_ID,
                )
            assert employee is not None
            assert employee.permission_version == 2
            assert [role.code for role in employee_authorization.roles] == ["tenant_admin"]
            assert other_user is not None
            assert other_user.permission_version == 1
            assert [role.code for role in other_authorization.roles] == ["employee"]

            old_me = await employee_client.get(
                "/api/v1/me",
                headers=_authorization(old_employee_access),
            )
            assert old_me.status_code == 401
            assert old_me.json()["error"]["code"] == "session_invalid"

            refreshed = await employee_client.post("/api/v1/auth/refresh")
            assert refreshed.status_code == 200
            refreshed_data = refreshed.json()["data"]
            refreshed_user = refreshed_data["user"]
            assert refreshed_user["permission_version"] == 2
            assert [role["code"] for role in refreshed_user["roles"]] == ["tenant_admin"]
            assert "role:assign:tenant" in refreshed_user["permissions"]

            refreshed_me = await employee_client.get(
                "/api/v1/me",
                headers=_authorization(refreshed_data["access_token"]),
            )
            assert refreshed_me.status_code == 200
            assert refreshed_me.json()["data"]["user"] == refreshed_user

            # Exact replacement deactivated rather than retained the previous employee role.
            assert employee_role_id not in {
                role.id for role in employee_authorization.roles
            }
