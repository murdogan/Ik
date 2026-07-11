from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs, urlsplit
from uuid import UUID

from app.core.auth_runtime import AUTH_RUNTIME_STATE_KEY, AuthRuntime
from app.core.config import Settings
from app.db.base import Base
from app.db.session import DATABASE_RUNTIME_STATE_KEY, DatabaseRuntime
from app.main import create_app
from app.models.auth import UserActivationToken
from app.models.tenant import Tenant, TenantStatus
from app.models.user import User, UserStatus
from app.platform.identity import AccessPrincipal, PasswordManager, hash_activation_token
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

TENANT_ID = UUID("11111111-aaaa-4111-8111-111111111111")
OTHER_TENANT_ID = UUID("22222222-bbbb-4222-8222-222222222222")
ADMIN_ID = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")
NON_CAPABLE_USER_ID = UUID("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb")
OTHER_TENANT_ACTIVE_USER_ID = UUID("cccccccc-cccc-4ccc-8ccc-cccccccccccc")
OTHER_TENANT_INVITED_USER_ID = UUID("dddddddd-dddd-4ddd-8ddd-dddddddddddd")

TENANT_SLUG = "wealthy-falcon"
OTHER_TENANT_SLUG = "other-falcon"
ADMIN_EMAIL = "admin@wealthyfalcon.test"
NON_CAPABLE_EMAIL = "employee@wealthyfalcon.test"
ADMIN_PASSWORD = "Admin credential for F2A tests"
NON_CAPABLE_PASSWORD = "Employee credential for F2A tests"
ACTIVATED_PASSWORD = "Activated credential for F2A tests"
OTHER_TENANT_PASSWORD = "Other tenant credential for F2A tests"
OTHER_TENANT_ACTIVE_EMAIL = "active.user@otherfalcon.test"
SHARED_INVITED_EMAIL = "shared.invitee@falcon.test"


@dataclass(slots=True)
class AuthApiHarness:
    app: FastAPI
    client: AsyncClient
    session_factory: async_sessionmaker[AsyncSession]
    password_manager: PasswordManager


@asynccontextmanager
async def _auth_api() -> AsyncIterator[AuthApiHarness]:
    settings = Settings(
        _env_file=None,
        environment="test",
        database_url="sqlite+aiosqlite:///:memory:",
        auth_signing_key="f2a-test-signing-key-material-that-is-not-a-real-secret",
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
        await _seed_auth_fixtures(
            database_runtime.session_factory,
            auth_runtime.password_manager,
        )

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://testserver",
        ) as client:
            yield AuthApiHarness(
                app=app,
                client=client,
                session_factory=database_runtime.session_factory,
                password_manager=auth_runtime.password_manager,
            )


async def _seed_auth_fixtures(
    session_factory: async_sessionmaker[AsyncSession],
    password_manager: PasswordManager,
) -> None:
    async with session_factory.begin() as session:
        session.add_all(
            [
                Tenant(
                    id=TENANT_ID,
                    slug=TENANT_SLUG,
                    name="Wealthy Falcon HR",
                    status=TenantStatus.ACTIVE.value,
                    plan_code="core",
                    data_region="tr-1",
                    locale="en-US",
                    timezone="UTC",
                ),
                Tenant(
                    id=OTHER_TENANT_ID,
                    slug=OTHER_TENANT_SLUG,
                    name="Other Falcon HR",
                    status=TenantStatus.ACTIVE.value,
                    plan_code="core",
                    data_region="tr-1",
                    locale="en-US",
                    timezone="UTC",
                ),
                User(
                    id=ADMIN_ID,
                    tenant_id=TENANT_ID,
                    email=ADMIN_EMAIL,
                    full_name="Invite Capable Admin",
                    status=UserStatus.ACTIVE.value,
                    password_hash=password_manager.hash(ADMIN_PASSWORD),
                    can_invite_users=True,
                ),
                User(
                    id=NON_CAPABLE_USER_ID,
                    tenant_id=TENANT_ID,
                    email=NON_CAPABLE_EMAIL,
                    full_name="Regular Employee",
                    status=UserStatus.ACTIVE.value,
                    password_hash=password_manager.hash(NON_CAPABLE_PASSWORD),
                    can_invite_users=False,
                ),
            ]
        )


async def _login(
    client: AsyncClient,
    *,
    email: str,
    password: str,
    tenant_slug: str = TENANT_SLUG,
) -> tuple[str, object]:
    response = await client.post(
        "/api/v1/auth/login",
        json={
            "tenant_slug": tenant_slug,
            "email": email,
            "password": password,
        },
    )
    assert response.status_code == 200
    assert response.headers["Cache-Control"] == "no-store"
    data = response.json()["data"]
    assert data["token_type"] == "bearer"
    return data["access_token"], response


def _activation_token(activation_url: str) -> str:
    fragment = parse_qs(urlsplit(activation_url).fragment)
    assert set(fragment) == {"token"}
    return fragment["token"][0]


async def test_invite_activate_and_login_end_to_end_with_hashed_single_use_credentials() -> None:
    async with _auth_api() as harness:
        admin_access_token, _ = await _login(
            harness.client,
            email=ADMIN_EMAIL,
            password=ADMIN_PASSWORD,
        )
        invitation = await harness.client.post(
            "/api/v1/users/invitations",
            headers={"Authorization": f"Bearer {admin_access_token}"},
            json={
                "email": " New.User@WealthyFalcon.Test ",
                "full_name": "New User",
            },
        )

        assert invitation.status_code == 201
        assert invitation.headers["Cache-Control"] == "no-store"
        invitation_data = invitation.json()["data"]
        invited_user_id = UUID(invitation_data["user"]["id"])
        assert invitation_data["user"] == {
            "id": str(invited_user_id),
            "email": "new.user@wealthyfalcon.test",
            "full_name": "New User",
            "status": "invited",
        }
        raw_activation_token = _activation_token(invitation_data["activation_url"])

        async with harness.session_factory() as session:
            invited_user = await session.get(User, invited_user_id)
            persisted_activation = await session.scalar(
                select(UserActivationToken).where(UserActivationToken.user_id == invited_user_id)
            )
            assert invited_user is not None
            assert invited_user.tenant_id == TENANT_ID
            assert invited_user.status == UserStatus.INVITED.value
            assert invited_user.password_hash is None
            assert persisted_activation is not None
            assert persisted_activation.tenant_id == TENANT_ID
            assert persisted_activation.token_hash == hash_activation_token(raw_activation_token)
            assert len(persisted_activation.token_hash) == 64
            assert persisted_activation.consumed_at is None

        activation = await harness.client.post(
            "/api/v1/auth/activate",
            json={
                "token": raw_activation_token,
                "password": ACTIVATED_PASSWORD,
            },
        )

        assert activation.status_code == 200
        assert activation.headers["Cache-Control"] == "no-store"
        assert activation.json()["data"]["user"]["id"] == str(invited_user_id)

        async with harness.session_factory() as session:
            activated_user = await session.get(User, invited_user_id)
            consumed_activation = await session.scalar(
                select(UserActivationToken).where(UserActivationToken.user_id == invited_user_id)
            )
            assert activated_user is not None
            assert activated_user.status == UserStatus.ACTIVE.value
            assert activated_user.password_hash is not None
            assert activated_user.password_hash.startswith("$argon2id$")
            assert harness.password_manager.verify(
                ACTIVATED_PASSWORD,
                activated_user.password_hash,
            )
            assert consumed_activation is not None
            assert consumed_activation.consumed_at is not None

        reused_activation = await harness.client.post(
            "/api/v1/auth/activate",
            json={
                "token": raw_activation_token,
                "password": ACTIVATED_PASSWORD,
            },
        )
        assert reused_activation.status_code == 400
        assert reused_activation.json()["error"]["code"] == "activation_invalid"

        user_access_token, login_response = await _login(
            harness.client,
            email="NEW.USER@WEALTHYFALCON.TEST",
            password=ACTIVATED_PASSWORD,
        )
        assert user_access_token
        assert login_response.json()["data"]["user"] == {
            "id": str(invited_user_id),
            "tenant_id": str(TENANT_ID),
            "email": "new.user@wealthyfalcon.test",
            "full_name": "New User",
            "tenant": {
                "slug": TENANT_SLUG,
                "name": "Wealthy Falcon HR",
            },
        }


async def test_invitation_ignores_spoofed_tenant_headers_and_rejects_payload_tenant() -> None:
    async with _auth_api() as harness:
        admin_access_token, _ = await _login(
            harness.client,
            email=ADMIN_EMAIL,
            password=ADMIN_PASSWORD,
        )
        spoofed_headers = {
            "Authorization": f"Bearer {admin_access_token}",
            "X-Tenant-Id": str(OTHER_TENANT_ID),
            "X-Tenant-Slug": OTHER_TENANT_SLUG,
            "X-User-Id": str(NON_CAPABLE_USER_ID),
        }
        header_spoof = await harness.client.post(
            "/api/v1/users/invitations",
            headers=spoofed_headers,
            json={
                "email": "header-spoof@wealthyfalcon.test",
                "full_name": "Header Spoof",
            },
        )

        assert header_spoof.status_code == 201
        header_spoof_user_id = UUID(header_spoof.json()["data"]["user"]["id"])

        payload_spoof = await harness.client.post(
            "/api/v1/users/invitations",
            headers={"Authorization": f"Bearer {admin_access_token}"},
            json={
                "tenant_id": str(OTHER_TENANT_ID),
                "email": "payload-spoof@wealthyfalcon.test",
                "full_name": "Payload Spoof",
            },
        )

        assert payload_spoof.status_code == 422
        assert payload_spoof.json()["error"]["code"] == "auth_validation_error"
        async with harness.session_factory() as session:
            header_spoof_user = await session.get(User, header_spoof_user_id)
            payload_spoof_user = await session.scalar(
                select(User).where(User.email_normalized == "payload-spoof@wealthyfalcon.test")
            )
            assert header_spoof_user is not None
            assert header_spoof_user.tenant_id == TENANT_ID
            assert payload_spoof_user is None


async def test_login_uses_one_generic_error_for_tenant_email_and_password_failures() -> None:
    async with _auth_api() as harness:
        attempts = (
            {
                "tenant_slug": "unknown-organization",
                "email": ADMIN_EMAIL,
                "password": ADMIN_PASSWORD,
            },
            {
                "tenant_slug": TENANT_SLUG,
                "email": "unknown@wealthyfalcon.test",
                "password": ADMIN_PASSWORD,
            },
            {
                "tenant_slug": TENANT_SLUG,
                "email": ADMIN_EMAIL,
                "password": "Credential that must not authenticate",
            },
        )

        error_contracts = []
        for attempt in attempts:
            response = await harness.client.post("/api/v1/auth/login", json=attempt)
            assert response.status_code == 401
            body = response.json()["error"]
            error_contracts.append((body["code"], body["message"], body["details"]))

        assert error_contracts == [error_contracts[0]] * len(attempts)
        assert error_contracts[0][0] == "invalid_credentials"


async def test_application_filters_tenant_for_login_inviter_and_invitation_target() -> None:
    async with _auth_api() as harness:
        async with harness.session_factory.begin() as session:
            session.add_all(
                [
                    User(
                        id=OTHER_TENANT_ACTIVE_USER_ID,
                        tenant_id=OTHER_TENANT_ID,
                        email=OTHER_TENANT_ACTIVE_EMAIL,
                        full_name="Other Tenant Invite Capable User",
                        status=UserStatus.ACTIVE.value,
                        password_hash=harness.password_manager.hash(OTHER_TENANT_PASSWORD),
                        can_invite_users=True,
                    ),
                    User(
                        id=OTHER_TENANT_INVITED_USER_ID,
                        tenant_id=OTHER_TENANT_ID,
                        email=SHARED_INVITED_EMAIL,
                        full_name="Other Tenant Original Invitee",
                        status=UserStatus.INVITED.value,
                        password_hash=None,
                    ),
                ]
            )

        cross_tenant_login = await harness.client.post(
            "/api/v1/auth/login",
            json={
                "tenant_slug": TENANT_SLUG,
                "email": OTHER_TENANT_ACTIVE_EMAIL,
                "password": OTHER_TENANT_PASSWORD,
            },
        )
        assert cross_tenant_login.status_code == 401
        assert cross_tenant_login.json()["error"]["code"] == "invalid_credentials"

        admin_access_token, _ = await _login(
            harness.client,
            email=ADMIN_EMAIL,
            password=ADMIN_PASSWORD,
        )
        invitation = await harness.client.post(
            "/api/v1/users/invitations",
            headers={"Authorization": f"Bearer {admin_access_token}"},
            json={
                "email": SHARED_INVITED_EMAIL,
                "full_name": "Tenant A Invitee",
            },
        )
        assert invitation.status_code == 201
        tenant_a_invitee_id = UUID(invitation.json()["data"]["user"]["id"])
        assert tenant_a_invitee_id != OTHER_TENANT_INVITED_USER_ID

        async with harness.session_factory() as session:
            shared_users = list(
                await session.scalars(
                    select(User).where(User.email_normalized == SHARED_INVITED_EMAIL)
                )
            )
            users_by_tenant = {user.tenant_id: user for user in shared_users}
            assert set(users_by_tenant) == {TENANT_ID, OTHER_TENANT_ID}

            tenant_a_invitee = users_by_tenant[TENANT_ID]
            assert tenant_a_invitee.id == tenant_a_invitee_id
            assert tenant_a_invitee.full_name == "Tenant A Invitee"
            assert tenant_a_invitee.status == UserStatus.INVITED.value
            assert tenant_a_invitee.password_hash is None

            tenant_b_invitee = users_by_tenant[OTHER_TENANT_ID]
            assert tenant_b_invitee.id == OTHER_TENANT_INVITED_USER_ID
            assert tenant_b_invitee.full_name == "Other Tenant Original Invitee"
            assert tenant_b_invitee.status == UserStatus.INVITED.value
            assert tenant_b_invitee.password_hash is None

        auth_runtime = getattr(harness.app.state, AUTH_RUNTIME_STATE_KEY)
        assert isinstance(auth_runtime, AuthRuntime)
        forged_cross_tenant_actor = auth_runtime.access_tokens.issue(
            AccessPrincipal(
                user_id=OTHER_TENANT_ACTIVE_USER_ID,
                tenant_id=TENANT_ID,
                tenant_slug=OTHER_TENANT_SLUG,
            )
        ).token
        forged_invitation = await harness.client.post(
            "/api/v1/users/invitations",
            headers={"Authorization": f"Bearer {forged_cross_tenant_actor}"},
            json={
                "email": "must-not-cross-tenants@wealthyfalcon.test",
                "full_name": "Must Not Cross Tenants",
            },
        )
        assert forged_invitation.status_code == 403
        assert forged_invitation.json()["error"]["code"] == "invitation_access_denied"

        async with harness.session_factory() as session:
            forbidden_user = await session.scalar(
                select(User).where(
                    User.email_normalized == "must-not-cross-tenants@wealthyfalcon.test"
                )
            )
            assert forbidden_user is None


async def test_active_user_without_invitation_capability_is_denied() -> None:
    async with _auth_api() as harness:
        access_token, _ = await _login(
            harness.client,
            email=NON_CAPABLE_EMAIL,
            password=NON_CAPABLE_PASSWORD,
        )
        response = await harness.client.post(
            "/api/v1/users/invitations",
            headers={"Authorization": f"Bearer {access_token}"},
            json={
                "email": "must-not-exist@wealthyfalcon.test",
                "full_name": "Must Not Exist",
            },
        )

        assert response.status_code == 403
        assert response.json()["error"]["code"] == "invitation_access_denied"
        async with harness.session_factory() as session:
            invited_user = await session.scalar(
                select(User).where(User.email_normalized == "must-not-exist@wealthyfalcon.test")
            )
            assert invited_user is None


async def test_expired_activation_is_rejected_without_changing_user_credentials() -> None:
    async with _auth_api() as harness:
        admin_access_token, _ = await _login(
            harness.client,
            email=ADMIN_EMAIL,
            password=ADMIN_PASSWORD,
        )
        invitation = await harness.client.post(
            "/api/v1/users/invitations",
            headers={"Authorization": f"Bearer {admin_access_token}"},
            json={
                "email": "expired@wealthyfalcon.test",
                "full_name": "Expired Invitation",
            },
        )
        assert invitation.status_code == 201
        invited_user_id = UUID(invitation.json()["data"]["user"]["id"])
        raw_activation_token = _activation_token(invitation.json()["data"]["activation_url"])

        now = datetime.now(UTC)
        async with harness.session_factory.begin() as session:
            activation = await session.scalar(
                select(UserActivationToken).where(UserActivationToken.user_id == invited_user_id)
            )
            assert activation is not None
            activation.created_at = now - timedelta(hours=2)
            activation.expires_at = now - timedelta(hours=1)

        response = await harness.client.post(
            "/api/v1/auth/activate",
            json={
                "token": raw_activation_token,
                "password": ACTIVATED_PASSWORD,
            },
        )

        assert response.status_code == 400
        assert response.json()["error"]["code"] == "activation_invalid"
        async with harness.session_factory() as session:
            invited_user = await session.get(User, invited_user_id)
            activation = await session.scalar(
                select(UserActivationToken).where(UserActivationToken.user_id == invited_user_id)
            )
            assert invited_user is not None
            assert invited_user.status == UserStatus.INVITED.value
            assert invited_user.password_hash is None
            assert activation is not None
            assert activation.consumed_at is None
