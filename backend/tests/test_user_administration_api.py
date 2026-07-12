from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from urllib.parse import parse_qs, urlsplit
from uuid import UUID, uuid4

from app.core.auth_runtime import AUTH_RUNTIME_STATE_KEY, AuthRuntime
from app.core.config import Settings
from app.db.base import Base
from app.db.session import DATABASE_RUNTIME_STATE_KEY, DatabaseRuntime
from app.main import create_app
from app.models.auth import RefreshSessionFamily, UserActivationToken
from app.models.tenant import Tenant, TenantStatus
from app.models.user import User, UserStatus
from app.platform.identity import PasswordManager
from app.services.authorization_service import assign_system_role, seed_authorization_catalog
from app.services.identity_projection_service import sync_identity_membership_projection
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import event, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

TENANT_A_ID = UUID("a1000000-0000-4000-8000-000000000001")
TENANT_B_ID = UUID("b1000000-0000-4000-8000-000000000002")
ADMIN_A_ID = UUID("aa000000-0000-4000-8000-000000000001")
USER_A_ID = UUID("ab000000-0000-4000-8000-000000000002")
INVITED_A_ID = UUID("ac000000-0000-4000-8000-000000000003")
PERCENT_A_ID = UUID("ad000000-0000-4000-8000-000000000004")
ADMIN_B_ID = UUID("ba000000-0000-4000-8000-000000000005")
USER_B_ID = UUID("bb000000-0000-4000-8000-000000000006")

ADMIN_A_EMAIL = "admin@tenant-a.test"
USER_A_EMAIL = "regular.user@tenant-a.test"
ADMIN_B_EMAIL = "admin@tenant-b.test"
PASSWORD = "F2C focused API test password"


@dataclass(slots=True)
class UserAdminApiHarness:
    app: FastAPI
    client: AsyncClient
    runtime: DatabaseRuntime
    session_factory: async_sessionmaker[AsyncSession]


@asynccontextmanager
async def _user_admin_api() -> AsyncIterator[UserAdminApiHarness]:
    settings = Settings(
        _env_file=None,
        environment="test",
        database_url="sqlite+aiosqlite:///:memory:",
        auth_signing_key="f2c-test-signing-key-material-that-is-not-a-real-secret",
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
        await _seed_users(runtime.session_factory, auth_runtime.password_manager)

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://testserver",
        ) as client:
            yield UserAdminApiHarness(
                app=app,
                client=client,
                runtime=runtime,
                session_factory=runtime.session_factory,
            )


async def _seed_users(
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
                    slug="tenant-a",
                    name="Tenant A",
                    status=TenantStatus.ACTIVE.value,
                    plan_code="core",
                    data_region="tr-1",
                    locale="en-US",
                    timezone="UTC",
                ),
                Tenant(
                    id=TENANT_B_ID,
                    slug="tenant-b",
                    name="Tenant B",
                    status=TenantStatus.ACTIVE.value,
                    plan_code="core",
                    data_region="tr-1",
                    locale="en-US",
                    timezone="UTC",
                ),
                User(
                    id=ADMIN_A_ID,
                    tenant_id=TENANT_A_ID,
                    email=ADMIN_A_EMAIL,
                    full_name="Tenant A Administrator",
                    status=UserStatus.ACTIVE.value,
                    password_hash=password_hash,
                    can_invite_users=True,
                ),
                User(
                    id=USER_A_ID,
                    tenant_id=TENANT_A_ID,
                    email=USER_A_EMAIL,
                    full_name="Regular Alpha User",
                    status=UserStatus.ACTIVE.value,
                    password_hash=password_hash,
                ),
                User(
                    id=INVITED_A_ID,
                    tenant_id=TENANT_A_ID,
                    email="invited@tenant-a.test",
                    full_name="Invited User",
                    status=UserStatus.INVITED.value,
                    password_hash=None,
                ),
                User(
                    id=PERCENT_A_ID,
                    tenant_id=TENANT_A_ID,
                    email="percent@tenant-a.test",
                    full_name="Percent % User",
                    status=UserStatus.DISABLED.value,
                    password_hash=password_hash,
                ),
                User(
                    id=ADMIN_B_ID,
                    tenant_id=TENANT_B_ID,
                    email=ADMIN_B_EMAIL,
                    full_name="Tenant B Administrator",
                    status=UserStatus.ACTIVE.value,
                    password_hash=password_hash,
                    can_invite_users=True,
                ),
                User(
                    id=USER_B_ID,
                    tenant_id=TENANT_B_ID,
                    email="user@tenant-b.test",
                    full_name="Tenant B User",
                    status=UserStatus.ACTIVE.value,
                    password_hash=password_hash,
                ),
            ]
        )
        await session.flush()
        for tenant_id, user_id, role_code in (
            (TENANT_A_ID, ADMIN_A_ID, "tenant_admin"),
            (TENANT_A_ID, USER_A_ID, "employee"),
            (TENANT_A_ID, INVITED_A_ID, "employee"),
            (TENANT_A_ID, PERCENT_A_ID, "employee"),
            (TENANT_B_ID, ADMIN_B_ID, "tenant_admin"),
            (TENANT_B_ID, USER_B_ID, "employee"),
        ):
            await assign_system_role(
                session,
                tenant_id=tenant_id,
                user_id=user_id,
                role_code=role_code,
            )
        for user_id in (
            ADMIN_A_ID,
            USER_A_ID,
            INVITED_A_ID,
            PERCENT_A_ID,
            ADMIN_B_ID,
            USER_B_ID,
        ):
            user = await session.get(User, user_id)
            assert user is not None
            await sync_identity_membership_projection(session, user)


async def _login(
    client: AsyncClient,
    *,
    email: str,
) -> str:
    response = await client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": PASSWORD},
    )
    assert response.status_code == 200
    return response.json()["data"]["access_token"]


def _authorization(access_token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {access_token}"}


async def test_admin_lists_searches_and_cursor_pages_only_authenticated_tenant_users() -> None:
    async with _user_admin_api() as harness:
        token = await _login(harness.client, email=ADMIN_A_EMAIL)
        headers = {
            **_authorization(token),
            "X-Tenant-Id": str(TENANT_B_ID),
        }

        select_statements: list[str] = []

        def count_selects(_conn, _cursor, statement, _parameters, _context, _many):
            if statement.lstrip().upper().startswith("SELECT"):
                select_statements.append(statement)

        event.listen(harness.runtime.engine.sync_engine, "before_cursor_execute", count_selects)
        try:
            first_page = await harness.client.get(
                "/api/v1/users",
                headers=headers,
                params={"limit": 2},
            )
        finally:
            event.remove(
                harness.runtime.engine.sync_engine,
                "before_cursor_execute",
                count_selects,
            )

        assert first_page.status_code == 200
        assert first_page.headers["Cache-Control"] == "no-store"
        first_body = first_page.json()
        assert len(first_body["data"]) == 2
        assert first_body["meta"]["limit"] == 2
        assert first_body["meta"]["next_cursor"]
        assert len(select_statements) == 4
        assert all(
            set(user)
            == {
                "id",
                "email",
                "full_name",
                "status",
                "roles",
                "permission_version",
                "created_at",
                "updated_at",
            }
            for user in first_body["data"]
        )

        second_page = await harness.client.get(
            "/api/v1/users",
            headers=headers,
            params={"limit": 2, "cursor": first_body["meta"]["next_cursor"]},
        )
        assert second_page.status_code == 200
        all_page_ids = {
            *(user["id"] for user in first_body["data"]),
            *(user["id"] for user in second_page.json()["data"]),
        }
        assert all_page_ids == {
            str(ADMIN_A_ID),
            str(USER_A_ID),
            str(INVITED_A_ID),
            str(PERCENT_A_ID),
        }
        assert str(ADMIN_B_ID) not in all_page_ids
        assert str(USER_B_ID) not in all_page_ids

        searched = await harness.client.get(
            "/api/v1/users",
            headers=headers,
            params={"search": "gular alpha"},
        )
        assert searched.status_code == 200
        assert [user["id"] for user in searched.json()["data"]] == [str(USER_A_ID)]

        literal_wildcard = await harness.client.get(
            "/api/v1/users",
            headers=headers,
            params={"search": "% U"},
        )
        assert literal_wildcard.status_code == 200
        assert [user["id"] for user in literal_wildcard.json()["data"]] == [str(PERCENT_A_ID)]

        invited = await harness.client.get(
            "/api/v1/users",
            headers=headers,
            params={"status": "invited"},
        )
        assert invited.status_code == 200
        assert [user["id"] for user in invited.json()["data"]] == [str(INVITED_A_ID)]

        mismatched_cursor = await harness.client.get(
            "/api/v1/users",
            headers=headers,
            params={
                "limit": 2,
                "cursor": first_body["meta"]["next_cursor"],
                "status": "active",
            },
        )
        assert mismatched_cursor.status_code == 422
        assert mismatched_cursor.json()["error"]["code"] == "user_administration_validation_error"


async def test_detail_update_authorization_and_cross_tenant_targets_fail_closed() -> None:
    async with _user_admin_api() as harness:
        admin_token = await _login(harness.client, email=ADMIN_A_EMAIL)
        user_token = await _login(harness.client, email=USER_A_EMAIL)

        detail = await harness.client.get(
            f"/api/v1/users/{USER_A_ID}",
            headers=_authorization(admin_token),
        )
        assert detail.status_code == 200
        assert detail.json()["data"]["email"] == USER_A_EMAIL

        for method in ("get", "patch"):
            kwargs = {"json": {"full_name": "Cross Tenant Mutation"}} if method == "patch" else {}
            response = await getattr(harness.client, method)(
                f"/api/v1/users/{USER_B_ID}",
                headers=_authorization(admin_token),
                **kwargs,
            )
            assert response.status_code == 404
            assert response.json()["error"]["code"] == "user_not_found"

        missing = await harness.client.get(
            f"/api/v1/users/{uuid4()}",
            headers=_authorization(admin_token),
        )
        assert missing.status_code == 404
        assert missing.json()["error"]["code"] == "user_not_found"

        async with harness.session_factory() as session:
            tenant_b_user = await session.get(User, USER_B_ID)
            assert tenant_b_user is not None
            assert tenant_b_user.full_name == "Tenant B User"

        for method in ("get", "patch"):
            path = "/api/v1/users" if method == "get" else f"/api/v1/users/{USER_A_ID}"
            kwargs = {"json": {"full_name": "Unauthorized"}} if method == "patch" else {}
            denied = await getattr(harness.client, method)(
                path,
                headers=_authorization(user_token),
                **kwargs,
            )
            assert denied.status_code == 403
            assert denied.json()["error"]["code"] == "user_administration_access_denied"

        spoofed_authority = await harness.client.patch(
            f"/api/v1/users/{USER_A_ID}",
            headers=_authorization(admin_token),
            json={
                "full_name": "Spoofed",
                "actor_id": str(ADMIN_B_ID),
                "tenant_id": str(TENANT_B_ID),
                "can_invite_users": True,
            },
        )
        assert spoofed_authority.status_code == 422
        assert spoofed_authority.json()["error"]["code"] == "user_administration_validation_error"


async def test_status_updates_revoke_sessions_and_preserve_activation_invariants() -> None:
    async with _user_admin_api() as harness:
        admin_token = await _login(harness.client, email=ADMIN_A_EMAIL)
        user_token = await _login(harness.client, email=USER_A_EMAIL)

        locked = await harness.client.patch(
            f"/api/v1/users/{USER_A_ID}",
            headers=_authorization(admin_token),
            json={"full_name": "Updated Regular User", "status": "locked"},
        )
        assert locked.status_code == 200
        assert locked.json()["data"]["full_name"] == "Updated Regular User"
        assert locked.json()["data"]["status"] == "locked"

        invalidated_session = await harness.client.get(
            "/api/v1/me",
            headers=_authorization(user_token),
        )
        assert invalidated_session.status_code == 401
        assert invalidated_session.json()["error"]["code"] == "session_invalid"

        async with harness.session_factory() as session:
            families = list(
                await session.scalars(
                    select(RefreshSessionFamily).where(RefreshSessionFamily.user_id == USER_A_ID)
                )
            )
            assert families
            assert all(family.revoked_at is not None for family in families)

        self_disabled = await harness.client.patch(
            f"/api/v1/users/{ADMIN_A_ID}",
            headers=_authorization(admin_token),
            json={"status": "disabled"},
        )
        assert self_disabled.status_code == 409
        assert self_disabled.json()["error"]["code"] == "user_status_conflict"

        impossible_activation = await harness.client.patch(
            f"/api/v1/users/{INVITED_A_ID}",
            headers=_authorization(admin_token),
            json={"status": "active"},
        )
        assert impossible_activation.status_code == 409
        assert impossible_activation.json()["error"]["code"] == "user_status_conflict"

        disabled_invite = await harness.client.patch(
            f"/api/v1/users/{INVITED_A_ID}",
            headers=_authorization(admin_token),
            json={"status": "disabled"},
        )
        assert disabled_invite.status_code == 200
        assert disabled_invite.json()["data"]["status"] == "disabled"

        invitation = await harness.client.post(
            "/api/v1/users/invitations",
            headers=_authorization(admin_token),
            json={"email": "pending@tenant-a.test", "full_name": "Pending Invite"},
        )
        assert invitation.status_code == 201
        invitation_data = invitation.json()["data"]
        invited_user_id = UUID(invitation_data["user"]["id"])
        activation_token = parse_qs(urlsplit(invitation_data["activation_url"]).fragment)["token"][
            0
        ]

        disabled_pending_invite = await harness.client.patch(
            f"/api/v1/users/{invited_user_id}",
            headers=_authorization(admin_token),
            json={"status": "disabled"},
        )
        assert disabled_pending_invite.status_code == 200
        rejected_activation = await harness.client.post(
            "/api/v1/auth/activate",
            json={"token": activation_token, "password": PASSWORD},
        )
        assert rejected_activation.status_code == 400
        assert rejected_activation.json()["error"]["code"] == "activation_invalid"
        async with harness.session_factory() as session:
            activation = await session.scalar(
                select(UserActivationToken).where(UserActivationToken.user_id == invited_user_id)
            )
            assert activation is not None
            assert activation.revoked_at is not None


async def test_user_admin_validation_is_bounded_and_uses_standard_envelope() -> None:
    async with _user_admin_api() as harness:
        token = await _login(harness.client, email=ADMIN_A_EMAIL)
        headers = _authorization(token)
        paths = (
            "/api/v1/users?limit=101",
            "/api/v1/users?limit=1&limit=2",
            "/api/v1/users?offset=1",
            "/api/v1/users?status=unknown",
            "/api/v1/users?search=ab",
            "/api/v1/users?cursor=not-a-cursor",
        )
        for path in paths:
            response = await harness.client.get(path, headers=headers)
            assert response.status_code == 422
            assert response.json()["error"]["code"] == "user_administration_validation_error"

        empty_patch = await harness.client.patch(
            f"/api/v1/users/{USER_A_ID}",
            headers=headers,
            json={},
        )
        assert empty_patch.status_code == 422
        assert empty_patch.json()["error"]["code"] == "user_administration_validation_error"
