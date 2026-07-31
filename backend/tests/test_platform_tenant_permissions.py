from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

import pytest
from app.api.auth_dependencies import (
    PlatformAuthenticatedSession,
    require_platform_authenticated_session,
    require_platform_permission,
)
from app.api.dependencies import (
    get_platform_tenant_query_service,
    get_tenant_command_handler,
    get_tenant_feature_service,
)
from app.core.auth_runtime import AUTH_RUNTIME_STATE_KEY, AuthRuntime
from app.core.config import Settings
from app.main import create_app
from app.modules.core.domain.feature_flags import FeatureFlagKey
from app.platform.identity import AccessPrincipal, PlatformAccessPrincipal
from app.platform.pagination import CursorPage
from app.platform.request_context import AuthenticationStrength
from app.services.platform_auth_session_service import PlatformAuthenticatedUser
from app.services.platform_tenant_queries import PlatformTenantMetadata
from app.services.tenant_feature_service import TenantFeatureSnapshot
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient, Response

TENANT_ID = UUID("c1000000-0000-4000-8000-000000000001")
IDENTITY_ID = UUID("c2000000-0000-4000-8000-000000000001")
MEMBERSHIP_ID = UUID("c2000000-0000-4000-8000-000000000002")
SESSION_FAMILY_ID = UUID("c3000000-0000-4000-8000-000000000001")

PLATFORM_OPERATION_PERMISSIONS = frozenset(
    {
        "tenant:create:platform",
        "tenant:read:platform",
        "tenant:update:platform",
        "feature:read:platform",
        "feature:update:platform",
    }
)


@dataclass(frozen=True, slots=True)
class PlatformOperationCase:
    method: str
    path: str
    payload: dict[str, Any] | None
    required_permission: str
    service_call: str
    success_status: int


PLATFORM_OPERATION_CASES = (
    PlatformOperationCase(
        method="POST",
        path="/api/v1/platform/tenants",
        payload={
            "slug": "permission-test",
            "name": "Permission Test",
            "initial_admin": {
                "full_name": "Permission Test Admin",
                "email": "permission-test-admin@example.test",
            },
        },
        required_permission="tenant:create:platform",
        service_call="create_tenant",
        success_status=201,
    ),
    PlatformOperationCase(
        method="GET",
        path="/api/v1/platform/tenants",
        payload=None,
        required_permission="tenant:read:platform",
        service_call="list_tenant_page",
        success_status=200,
    ),
    PlatformOperationCase(
        method="GET",
        path=f"/api/v1/platform/tenants/{TENANT_ID}",
        payload=None,
        required_permission="tenant:read:platform",
        service_call="get_tenant",
        success_status=200,
    ),
    PlatformOperationCase(
        method="PATCH",
        path=f"/api/v1/platform/tenants/{TENANT_ID}",
        payload={"name": "Permission Test Updated"},
        required_permission="tenant:update:platform",
        service_call="update_tenant",
        success_status=200,
    ),
    PlatformOperationCase(
        method="POST",
        path=f"/api/v1/platform/tenants/{TENANT_ID}/initial-admin-invitation/resend",
        payload=None,
        required_permission="tenant:update:platform",
        service_call="reissue_initial_admin_invitation",
        success_status=202,
    ),
    PlatformOperationCase(
        method="PATCH",
        path=f"/api/v1/platform/tenants/{TENANT_ID}/initial-admin-invitation",
        payload={
            "full_name": "Corrected Initial Admin",
            "email": "corrected.initial.admin@example.test",
        },
        required_permission="tenant:update:platform",
        service_call="correct_initial_admin_invitation",
        success_status=202,
    ),
    PlatformOperationCase(
        method="GET",
        path=f"/api/v1/platform/tenants/{TENANT_ID}/features",
        payload=None,
        required_permission="feature:read:platform",
        service_call="get_tenant_features",
        success_status=200,
    ),
    PlatformOperationCase(
        method="PATCH",
        path=f"/api/v1/platform/tenants/{TENANT_ID}/features",
        payload={"features": [{"key": "employees", "enabled": False}]},
        required_permission="feature:update:platform",
        service_call="update_tenant_features",
        success_status=200,
    ),
)


class PlatformOperationProbe:
    def __init__(self) -> None:
        self.calls: list[str] = []
        self.tenant = PlatformTenantMetadata(
            id=TENANT_ID,
            slug="permission-test",
            name="Permission Test",
            status="active",
            plan_code="core",
            data_region="tr-1",
            locale="tr-TR",
            timezone="Europe/Istanbul",
            active_employee_limit=None,
            created_at=datetime(2026, 7, 28),
            updated_at=datetime(2026, 7, 28),
        )
        self.features = (
            TenantFeatureSnapshot(
                key=FeatureFlagKey.EMPLOYEES,
                enabled=True,
                source="default",
            ),
        )

    async def create_tenant(self, *_args: object, **_kwargs: object) -> PlatformTenantMetadata:
        self.calls.append("create_tenant")
        return self.tenant

    async def list_tenant_page(self, *_args: object, **_kwargs: object):
        self.calls.append("list_tenant_page")
        return CursorPage(items=[self.tenant], next_cursor=None)

    async def get_tenant(self, *_args: object, **_kwargs: object) -> PlatformTenantMetadata:
        self.calls.append("get_tenant")
        return self.tenant

    async def update_tenant(self, *_args: object, **_kwargs: object) -> PlatformTenantMetadata:
        self.calls.append("update_tenant")
        return self.tenant

    async def reissue_initial_admin_invitation(
        self,
        *_args: object,
        **_kwargs: object,
    ) -> None:
        self.calls.append("reissue_initial_admin_invitation")

    async def correct_initial_admin_invitation(
        self,
        *_args: object,
        **_kwargs: object,
    ) -> None:
        self.calls.append("correct_initial_admin_invitation")

    async def get_tenant_features(
        self,
        *_args: object,
        **_kwargs: object,
    ) -> tuple[TenantFeatureSnapshot, ...]:
        self.calls.append("get_tenant_features")
        return self.features

    async def update_tenant_features(
        self,
        *_args: object,
        **_kwargs: object,
    ) -> tuple[TenantFeatureSnapshot, ...]:
        self.calls.append("update_tenant_features")
        return self.features


def _authenticated_session(
    permissions: tuple[str, ...],
) -> PlatformAuthenticatedSession:
    principal = PlatformAccessPrincipal(
        identity_id=IDENTITY_ID,
        session_family_id=SESSION_FAMILY_ID,
        permission_version=1,
        authentication_strength=AuthenticationStrength.SINGLE_FACTOR,
    )
    return PlatformAuthenticatedSession(
        principal=principal,
        user=PlatformAuthenticatedUser(
            id=IDENTITY_ID,
            email="permission.test@wealthyfalcon.test",
            full_name="Permission Test",
            workspace_scope="platform",
            roles=(),
            permissions=permissions,
            permission_version=principal.permission_version,
            authentication_strength=principal.authentication_strength,
        ),
    )


def _permission_test_app(
    *,
    permissions: tuple[str, ...],
    probe: PlatformOperationProbe,
    session_calls: list[None],
) -> FastAPI:
    app = create_app()
    authenticated = _authenticated_session(permissions)

    async def provide_authenticated_session() -> PlatformAuthenticatedSession:
        session_calls.append(None)
        return authenticated

    app.dependency_overrides[require_platform_authenticated_session] = provide_authenticated_session
    app.dependency_overrides[get_platform_tenant_query_service] = lambda: probe
    app.dependency_overrides[get_tenant_feature_service] = lambda: probe
    app.dependency_overrides[get_tenant_command_handler] = lambda: probe
    return app


def _assert_platform_denial(response: Response) -> None:
    assert response.status_code == 403
    assert response.json() == {
        "error": {
            "code": "platform_access_denied",
            "message": "A valid platform access credential is required",
            "details": None,
            "correlation_id": response.headers["X-Request-Id"],
        }
    }


@pytest.mark.parametrize("case", PLATFORM_OPERATION_CASES, ids=lambda case: case.service_call)
async def test_platform_tenant_operation_accepts_exact_live_permission_once(
    case: PlatformOperationCase,
) -> None:
    probe = PlatformOperationProbe()
    session_calls: list[None] = []
    app = _permission_test_app(
        permissions=(case.required_permission,),
        probe=probe,
        session_calls=session_calls,
    )

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.request(case.method, case.path, json=case.payload)

    assert response.status_code == case.success_status, response.text
    assert probe.calls == [case.service_call]
    assert session_calls == [None]
    if case.service_call == "list_tenant_page":
        assert response.json()["data"][0]["created_at"] == "2026-07-28T00:00:00Z"
    elif case.service_call in {"create_tenant", "get_tenant", "update_tenant"}:
        assert response.json()["data"]["created_at"] == "2026-07-28T00:00:00Z"
    elif case.service_call in {
        "correct_initial_admin_invitation",
        "reissue_initial_admin_invitation",
    }:
        assert response.json()["data"] == {"status": "invitation_prepared"}
    else:
        assert response.json()["data"] == {
            "features": [{"key": "employees", "enabled": True, "source": "default"}]
        }


@pytest.mark.parametrize("case", PLATFORM_OPERATION_CASES, ids=lambda case: case.service_call)
async def test_platform_tenant_operation_denies_missing_or_wrong_permission_before_service(
    case: PlatformOperationCase,
) -> None:
    probe = PlatformOperationProbe()
    session_calls: list[None] = []
    wrong_grants = tuple(sorted(PLATFORM_OPERATION_PERMISSIONS - {case.required_permission})) + (
        case.required_permission.removesuffix(":platform"),
        case.required_permission.replace(":platform", ":tenant"),
        f"{case.required_permission}:extra",
    )
    app = _permission_test_app(
        permissions=wrong_grants,
        probe=probe,
        session_calls=session_calls,
    )

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.request(
            case.method,
            case.path,
            json=case.payload,
            headers={"X-Platform-Permissions": case.required_permission},
        )

    _assert_platform_denial(response)
    assert probe.calls == []
    assert session_calls == [None]


async def test_tenant_realm_bearer_cannot_access_platform_tenant_route() -> None:
    settings = Settings(
        _env_file=None,
        environment="test",
        database_url="sqlite+aiosqlite:///:memory:",
        auth_signing_key="permission-test-signing-key-material-that-is-not-a-real-secret",
        frontend_base_url="http://frontend.test",
    )
    app = create_app(settings=settings)
    probe = PlatformOperationProbe()
    app.dependency_overrides[get_platform_tenant_query_service] = lambda: probe

    async with app.router.lifespan_context(app):
        auth_runtime = getattr(app.state, AUTH_RUNTIME_STATE_KEY)
        assert isinstance(auth_runtime, AuthRuntime)
        tenant_token = auth_runtime.access_tokens.issue(
            AccessPrincipal(
                user_id=IDENTITY_ID,
                tenant_id=TENANT_ID,
                membership_id=MEMBERSHIP_ID,
                tenant_slug="permission-test",
                session_family_id=SESSION_FAMILY_ID,
                permission_version=1,
            )
        ).token
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://testserver",
        ) as client:
            response = await client.get(
                "/api/v1/platform/tenants",
                headers={"Authorization": f"Bearer {tenant_token}"},
            )

    _assert_platform_denial(response)
    assert probe.calls == []


def test_platform_permission_dependency_rejects_unknown_code_at_construction() -> None:
    with pytest.raises(ValueError, match="Unknown permission code: tenant:delete:platform"):
        require_platform_permission("tenant:delete:platform")


def test_platform_permission_dependency_rejects_known_tenant_code_at_construction() -> None:
    with pytest.raises(ValueError, match="Permission is not platform-scoped: tenant:read:tenant"):
        require_platform_permission("tenant:read:tenant")
