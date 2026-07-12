from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

from app.api.auth_dependencies import (
    AuthenticatedSession,
    require_access_principal,
    require_authenticated_session,
)
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
from app.platform.authorization import ROLE_PERMISSION_CODES, ROLES_BY_CODE
from app.platform.identity import AccessPrincipal
from app.platform.principals import PlatformPrincipal
from app.services.audit_recorder import SqlAlchemyAuditRecorder
from app.services.auth_session_service import AuthenticatedUser
from app.services.authorization_service import (
    AssignedRole,
    assign_system_role,
    seed_authorization_catalog,
)
from app.services.identity_projection_service import sync_identity_membership_projection
from fastapi import Depends, FastAPI
from httpx import ASGITransport, AsyncClient
from httpx import Response as HttpxResponse
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

TENANT_A_ID = UUID("b1000000-0000-4000-8000-000000000001")
TENANT_B_ID = UUID("b1000000-0000-4000-8000-000000000002")
PLATFORM_IDENTITY_TENANT_ID = UUID("b1000000-0000-4000-8000-000000000003")
ADMIN_ID = UUID("b2000000-0000-4000-8000-000000000001")
EMPLOYEE_ID = UUID("b2000000-0000-4000-8000-000000000002")
OTHER_TENANT_USER_ID = UUID("b2000000-0000-4000-8000-000000000003")
HR_DIRECTOR_ID = UUID("b2000000-0000-4000-8000-000000000004")
HR_SPECIALIST_ID = UUID("b2000000-0000-4000-8000-000000000005")
IT_ADMIN_ID = UUID("b2000000-0000-4000-8000-000000000006")
AUDITOR_ID = UUID("b2000000-0000-4000-8000-000000000007")
MANAGER_ID = UUID("b2000000-0000-4000-8000-000000000008")
SUPER_ADMIN_ID = UUID("b2000000-0000-4000-8000-000000000009")
SUPER_ADMIN_SESSION_ID = UUID("b4000000-0000-4000-8000-000000000001")
TENANT_ADMIN_EVENT_ID = UUID("b3000000-0000-4000-8000-000000000001")
TENANT_B_EVENT_ID = UUID("b3000000-0000-4000-8000-000000000002")
PLATFORM_EVENT_ID = UUID("b3000000-0000-4000-8000-000000000003")
TENANT_SECURITY_EVENT_ID = UUID("b3000000-0000-4000-8000-000000000004")
HR_OPERATIONS_EVENT_ID = UUID("b3000000-0000-4000-8000-000000000005")
PASSWORD = "F2E audit API test credential"

TENANT_ROLE_USERS = (
    ("tenant_admin", ADMIN_ID, "admin@audit-a.test"),
    ("hr_director", HR_DIRECTOR_ID, "hr-director@audit-a.test"),
    ("hr_specialist", HR_SPECIALIST_ID, "hr-specialist@audit-a.test"),
    ("it_admin", IT_ADMIN_ID, "it-admin@audit-a.test"),
    ("auditor", AUDITOR_ID, "auditor@audit-a.test"),
    ("manager", MANAGER_ID, "manager@audit-a.test"),
    ("employee", EMPLOYEE_ID, "employee@audit-a.test"),
)


@dataclass(slots=True)
class AuditApiHarness:
    app: FastAPI
    client: AsyncClient
    session_factory: async_sessionmaker[AsyncSession]


@dataclass(frozen=True, slots=True)
class EndpointCase:
    name: str
    method: str
    path: str
    allowed_roles: frozenset[str]
    denied_error: str
    success_status: int = 200
    payload: dict[str, object] | None = None


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
                Tenant(
                    id=PLATFORM_IDENTITY_TENANT_ID,
                    slug="platform-identity",
                    name="Internal Platform Identity",
                    status=TenantStatus.ACTIVE.value,
                    plan_code="core",
                    data_region="tr-1",
                    locale="en-US",
                    timezone="UTC",
                ),
                *(
                    User(
                        id=user_id,
                        tenant_id=TENANT_A_ID,
                        email=email,
                        full_name=role_code.replace("_", " ").title(),
                        status=UserStatus.ACTIVE.value,
                        password_hash=password_hash,
                    )
                    for role_code, user_id, email in TENANT_ROLE_USERS
                ),
                User(
                    id=OTHER_TENANT_USER_ID,
                    tenant_id=TENANT_B_ID,
                    email="employee@audit-b.test",
                    full_name="Other Tenant Employee",
                    status=UserStatus.ACTIVE.value,
                    password_hash=password_hash,
                ),
            ]
        )
        await session.flush()
        for role_code, user_id, _email in TENANT_ROLE_USERS:
            await assign_system_role(
                session,
                tenant_id=TENANT_A_ID,
                user_id=user_id,
                role_code=role_code,
            )
        await assign_system_role(
            session,
            tenant_id=TENANT_B_ID,
            user_id=OTHER_TENANT_USER_ID,
            role_code="employee",
        )
        for user_id in (
            *(user_id for _role_code, user_id, _email in TENANT_ROLE_USERS),
            OTHER_TENANT_USER_ID,
        ):
            user = await session.get(User, user_id)
            assert user is not None
            await sync_identity_membership_projection(session, user)
        recorder = SqlAlchemyAuditRecorder(session)
        await recorder.record(
            _event(
                event_id=TENANT_ADMIN_EVENT_ID,
                scope_type=AuditScopeType.TENANT,
                tenant_id=TENANT_A_ID,
                event_type=AuditEventType.INVITATION_CREATED,
                category=AuditCategory.TENANT_ADMIN,
                actor_user_id=ADMIN_ID,
                resource_id=EMPLOYEE_ID,
                occurred_at=datetime(2026, 7, 12, 9, 5, tzinfo=UTC),
            )
        )
        await recorder.record(
            _event(
                event_id=TENANT_SECURITY_EVENT_ID,
                scope_type=AuditScopeType.TENANT,
                tenant_id=TENANT_A_ID,
                event_type=AuditEventType.LOGIN_FAILED,
                category=AuditCategory.TENANT_SECURITY,
                actor_user_id=None,
                resource_id=None,
                occurred_at=datetime(2026, 7, 12, 9, 4, tzinfo=UTC),
            )
        )
        await recorder.record(
            _event(
                event_id=HR_OPERATIONS_EVENT_ID,
                scope_type=AuditScopeType.TENANT,
                tenant_id=TENANT_A_ID,
                event_type=AuditEventType.USER_STATUS_CHANGED,
                category=AuditCategory.HR_OPERATIONS,
                actor_user_id=HR_DIRECTOR_ID,
                resource_id=EMPLOYEE_ID,
                occurred_at=datetime(2026, 7, 12, 9, 3, tzinfo=UTC),
            )
        )
        await recorder.record(
            _event(
                event_id=TENANT_B_EVENT_ID,
                scope_type=AuditScopeType.TENANT,
                tenant_id=TENANT_B_ID,
                event_type=AuditEventType.ROLES_REPLACED,
                category=AuditCategory.TENANT_ADMIN,
                actor_user_id=OTHER_TENANT_USER_ID,
                resource_id=OTHER_TENANT_USER_ID,
                occurred_at=datetime(2026, 7, 12, 9, 2, tzinfo=UTC),
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
                occurred_at=datetime(2026, 7, 12, 9, 1, tzinfo=UTC),
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
    if is_platform != (category is AuditCategory.PLATFORM_OPERATIONS):
        raise AssertionError("Fixture audit scope and category must agree")
    semantics: dict[
        AuditCategory,
        tuple[AuditDataClassification, AuditVisibilityClass],
    ] = {
        AuditCategory.PLATFORM_OPERATIONS: (
            AuditDataClassification.PLATFORM_METADATA,
            AuditVisibilityClass.PLATFORM_OPS,
        ),
        AuditCategory.TENANT_ADMIN: (
            AuditDataClassification.TENANT_ADMINISTRATION,
            AuditVisibilityClass.TENANT_ADMIN,
        ),
        AuditCategory.TENANT_SECURITY: (
            AuditDataClassification.SECURITY_METADATA,
            AuditVisibilityClass.TENANT_SECURITY,
        ),
        AuditCategory.HR_OPERATIONS: (
            AuditDataClassification.HR_METADATA,
            AuditVisibilityClass.HR_OPERATIONS,
        ),
    }
    event_shapes = {
        AuditEventType.INVITATION_CREATED: ("user", "invite"),
        AuditEventType.LOGIN_FAILED: ("authentication", "login"),
        AuditEventType.USER_STATUS_CHANGED: ("user", "change_status"),
        AuditEventType.ROLES_REPLACED: ("user", "replace_roles"),
        AuditEventType.PLATFORM_TENANT_CREATED: ("tenant", "create"),
    }
    data_classification, visibility_class = semantics[category]
    resource_type, action = event_shapes[event_type]
    return AuditEventDraft(
        id=event_id,
        occurred_at=occurred_at,
        scope_type=scope_type,
        tenant_id=tenant_id,
        actor_type=(AuditActorType.PLATFORM_ADMIN if is_platform else AuditActorType.USER),
        actor_user_id=actor_user_id,
        event_type=event_type,
        category=category,
        resource_type=resource_type,
        resource_id=resource_id,
        action=action,
        context=AuditContext(
            request_id=f"req-{event_id.hex}",
            trace_id=event_id.hex,
        ),
        data_classification=data_classification,
        visibility_class=visibility_class,
    )


async def _login(client: AsyncClient, email: str) -> str:
    response = await client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": PASSWORD},
    )
    assert response.status_code == 200
    return response.json()["data"]["access_token"]


def _authorization(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _assert_endpoint_cases(
    client: AsyncClient,
    *,
    role_code: str,
    headers: dict[str, str],
    cases: tuple[EndpointCase, ...],
) -> dict[str, HttpxResponse]:
    responses: dict[str, HttpxResponse] = {}
    for case in cases:
        request_kwargs = {} if case.payload is None else {"json": case.payload}
        response = await client.request(
            case.method,
            case.path,
            headers=headers,
            **request_kwargs,
        )
        allowed = role_code in case.allowed_roles
        expected_status = case.success_status if allowed else 403
        assert response.status_code == expected_status, (
            f"{role_code}/{case.name}: {case.method} {case.path} returned "
            f"{response.status_code}: {response.text}"
        )
        if not allowed:
            assert response.json()["error"]["code"] == case.denied_error, (
                role_code,
                case.name,
            )
        responses[case.name] = response
    return responses


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
            f"/api/v1/audit-events/{TENANT_ADMIN_EVENT_ID}",
            headers=headers,
        )
        assert detail.status_code == 200
        assert detail.json()["data"]["id"] == str(TENANT_ADMIN_EVENT_ID)
        serialized = detail.text.lower()
        assert "password" not in serialized
        assert "token" not in serialized
        assert "cookie" not in serialized


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


async def test_f2f_role_scope_endpoint_security_matrix() -> None:
    """Exercise each tenant role at HTTP boundaries without repeating payload contracts."""

    async with _audit_api() as harness:
        access_tokens = {
            role_code: await _login(harness.client, email)
            for role_code, _user_id, email in TENANT_ROLE_USERS
        }
        employee_role_id = str(ROLES_BY_CODE["employee"].id)
        tenant_admins = frozenset({"tenant_admin"})
        user_readers = frozenset({"tenant_admin", "it_admin"})
        audit_readers = frozenset(
            {"tenant_admin", "it_admin", "hr_director", "auditor"}
        )
        endpoint_cases = (
            EndpointCase(
                "user list",
                "GET",
                "/api/v1/users",
                user_readers,
                "user_administration_access_denied",
            ),
            EndpointCase(
                "user detail",
                "GET",
                f"/api/v1/users/{EMPLOYEE_ID}",
                user_readers,
                "user_administration_access_denied",
            ),
            EndpointCase(
                "user update",
                "PATCH",
                f"/api/v1/users/{EMPLOYEE_ID}",
                tenant_admins,
                "user_administration_access_denied",
                payload={"full_name": "Matrix Employee"},
            ),
            EndpointCase(
                "user invitation",
                "POST",
                "/api/v1/users/invitations",
                tenant_admins,
                "invitation_access_denied",
                success_status=201,
                payload={
                    "email": "matrix-invite@audit-a.test",
                    "full_name": "Matrix Invite",
                },
            ),
            EndpointCase(
                "role catalog",
                "GET",
                "/api/v1/roles",
                tenant_admins,
                "authorization_denied",
            ),
            EndpointCase(
                "permission catalog",
                "GET",
                "/api/v1/permissions",
                tenant_admins,
                "authorization_denied",
            ),
            EndpointCase(
                "role assignment",
                "PUT",
                f"/api/v1/users/{EMPLOYEE_ID}/roles",
                tenant_admins,
                "user_administration_access_denied",
                payload={"role_ids": [employee_role_id]},
            ),
            EndpointCase(
                "tenant audit list",
                "GET",
                "/api/v1/audit-events",
                audit_readers,
                "authorization_denied",
            ),
        )

        role_responses = {
            role_code: await _assert_endpoint_cases(
                harness.client,
                role_code=role_code,
                headers=_authorization(access_token),
                cases=endpoint_cases,
            )
            for role_code, access_token in access_tokens.items()
        }

        audit_visibility = {
            "tenant_admin": frozenset(
                {AuditCategory.TENANT_ADMIN, AuditCategory.TENANT_SECURITY}
            ),
            "it_admin": frozenset({AuditCategory.TENANT_SECURITY}),
            "auditor": frozenset(
                {
                    AuditCategory.TENANT_ADMIN,
                    AuditCategory.TENANT_SECURITY,
                    AuditCategory.HR_OPERATIONS,
                }
            ),
            "hr_director": frozenset({AuditCategory.HR_OPERATIONS}),
        }
        seeded_event_ids = {
            AuditCategory.TENANT_ADMIN: TENANT_ADMIN_EVENT_ID,
            AuditCategory.TENANT_SECURITY: TENANT_SECURITY_EVENT_ID,
            AuditCategory.HR_OPERATIONS: HR_OPERATIONS_EVENT_ID,
        }
        for role_code, visible_categories in audit_visibility.items():
            listed_events = role_responses[role_code]["tenant audit list"].json()["data"]
            listed_ids = {event["id"] for event in listed_events}
            assert {event["category"] for event in listed_events} == {
                category.value for category in visible_categories
            }
            assert {
                str(seeded_event_ids[category]) for category in visible_categories
            } <= listed_ids
            assert {
                str(event_id)
                for category, event_id in seeded_event_ids.items()
                if category not in visible_categories
            }.isdisjoint(listed_ids)

        event_by_category = tuple(seeded_event_ids.items())
        for role_code, access_token in access_tokens.items():
            visible_categories = audit_visibility.get(role_code)
            for category, event_id in event_by_category:
                response = await harness.client.get(
                    f"/api/v1/audit-events/{event_id}",
                    headers=_authorization(access_token),
                )
                if visible_categories is None:
                    assert response.status_code == 403, (role_code, category, response.text)
                    assert response.json()["error"]["code"] == "authorization_denied"
                elif category in visible_categories:
                    assert response.status_code == 200, (role_code, category, response.text)
                    assert response.json()["data"]["id"] == str(event_id)
                else:
                    assert response.status_code == 404, (role_code, category, response.text)
                    assert response.json()["error"]["code"] == "audit_event_not_found"

        admin_responses = role_responses["tenant_admin"]
        listed_user_ids = {
            user["id"] for user in admin_responses["user list"].json()["data"]
        }
        assert str(OTHER_TENANT_USER_ID) not in listed_user_ids
        listed_audit_ids = {
            event["id"]
            for event in admin_responses["tenant audit list"].json()["data"]
        }
        assert str(TENANT_B_EVENT_ID) not in listed_audit_ids
        assert str(PLATFORM_EVENT_ID) not in listed_audit_ids

        admin_headers = _authorization(access_tokens["tenant_admin"])
        cross_tenant_cases = (
            ("GET", f"/api/v1/users/{OTHER_TENANT_USER_ID}", None, "user_not_found"),
            (
                "PATCH",
                f"/api/v1/users/{OTHER_TENANT_USER_ID}",
                {"full_name": "Must Not Cross Tenants"},
                "user_not_found",
            ),
            (
                "PUT",
                f"/api/v1/users/{OTHER_TENANT_USER_ID}/roles",
                {"role_ids": [employee_role_id]},
                "user_not_found",
            ),
            (
                "GET",
                f"/api/v1/audit-events/{TENANT_B_EVENT_ID}",
                None,
                "audit_event_not_found",
            ),
        )
        for method, path, payload, expected_error in cross_tenant_cases:
            request_kwargs = {} if payload is None else {"json": payload}
            response = await harness.client.request(
                method,
                path,
                headers=admin_headers,
                **request_kwargs,
            )
            assert response.status_code == 404, (method, path, response.text)
            assert response.json()["error"]["code"] == expected_error

        for role_code, access_token in access_tokens.items():
            platform_denied = await harness.client.get(
                "/api/v1/platform/audit-events",
                headers=_authorization(access_token),
            )
            assert platform_denied.status_code == 403, role_code
            assert platform_denied.json()["error"]["code"] == "platform_access_denied"

        auth_runtime = getattr(harness.app.state, AUTH_RUNTIME_STATE_KEY)
        assert isinstance(auth_runtime, AuthRuntime)
        super_admin_principal = AccessPrincipal(
            user_id=SUPER_ADMIN_ID,
            tenant_id=PLATFORM_IDENTITY_TENANT_ID,
            membership_id=SUPER_ADMIN_ID,
            tenant_slug="platform-identity",
            session_family_id=SUPER_ADMIN_SESSION_ID,
        )
        super_admin_role = ROLES_BY_CODE["super_admin"]
        super_admin_user = AuthenticatedUser(
            id=SUPER_ADMIN_ID,
            tenant_id=PLATFORM_IDENTITY_TENANT_ID,
            membership_id=SUPER_ADMIN_ID,
            email="super-admin@platform.test",
            full_name="Platform Super Admin",
            tenant_slug="platform-identity",
            tenant_name="Internal Platform Identity",
            workspace_scope="platform",
            roles=(
                AssignedRole(
                    id=super_admin_role.id,
                    code=super_admin_role.code,
                    name=super_admin_role.name,
                    scope_type=super_admin_role.scope_type.value,
                ),
            ),
            permissions=tuple(sorted(ROLE_PERMISSION_CODES["super_admin"])),
            permission_version=1,
        )

        async def resolve_super_admin_bearer(
            principal: Annotated[
                AccessPrincipal,
                Depends(require_access_principal),
            ],
        ) -> AuthenticatedSession:
            # Preserve signed-bearer parsing while supplying the not-yet-wired platform session
            # adapter's resolved subject.
            assert principal == super_admin_principal
            return AuthenticatedSession(principal=principal, user=super_admin_user)

        harness.app.dependency_overrides[
            require_authenticated_session
        ] = resolve_super_admin_bearer
        super_admin_token = auth_runtime.access_tokens.issue(super_admin_principal).token
        super_admin_headers = _authorization(super_admin_token)
        super_admin_tenant_denied = await harness.client.get(
            "/api/v1/audit-events",
            headers=super_admin_headers,
        )
        assert super_admin_tenant_denied.status_code == 403
        assert (
            super_admin_tenant_denied.json()["error"]["code"]
            == "authorization_denied"
        )
        super_admin_platform_denied = await harness.client.get(
            "/api/v1/platform/audit-events",
            headers=super_admin_headers,
        )
        assert super_admin_platform_denied.status_code == 403
        assert (
            super_admin_platform_denied.json()["error"]["code"]
            == "platform_access_denied"
        )
        harness.app.dependency_overrides.pop(require_authenticated_session)

        harness.app.dependency_overrides[get_platform_principal] = lambda: PlatformPrincipal(
            source="f2f-security-matrix"
        )
        platform_response = await harness.client.get("/api/v1/platform/audit-events")
        assert platform_response.status_code == 200
        assert [event["id"] for event in platform_response.json()["data"]] == [
            str(PLATFORM_EVENT_ID)
        ]
