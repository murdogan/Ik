# ruff: noqa: E402

from __future__ import annotations

import argparse
import asyncio
import re
import sys
from datetime import date, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlsplit
from uuid import UUID, uuid4

ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = ROOT / "backend"
API_IMPLEMENTATION_STATUS_DOC = (
    ROOT / "docs" / "09-uygulama" / "11-api-implementation-status.md"
)
OPENAPI_ENDPOINT_DRAFT_DOC = (
    ROOT / "docs" / "09-uygulama" / "03-openapi-endpoint-taslagi.md"
)
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.api.dependencies import get_platform_principal, get_tenant_principal
from app.core.config import Settings
from app.db.base import Base
from app.db.session import DATABASE_RUNTIME_STATE_KEY
from app.main import create_app
from app.models.employee import EmployeeStatus
from app.models.leave_balance_summary import LeaveBalanceSummary
from app.models.leave_request import LeaveRequestStatus
from app.models.tenant import Tenant, TenantSettings, TenantStatus
from app.models.user import User, UserStatus
from app.platform.identity import PasswordManager
from app.platform.principals import PlatformPrincipal, TenantPrincipal
from httpx import ASGITransport, AsyncClient, Response
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    async_sessionmaker,
)

TENANT_ID = UUID("11111111-aaaa-4111-8111-111111111111")
OTHER_TENANT_ID = UUID("44444444-dddd-4444-8444-444444444444")
REQUESTING_USER_ID = UUID("22222222-bbbb-4222-8222-222222222222")
APPROVER_USER_ID = UUID("33333333-cccc-4333-8333-333333333333")
OTHER_REQUESTING_USER_ID = UUID("55555555-eeee-4555-8555-555555555555")
SMOKE_ADMIN_CREDENTIAL = "Backend smoke admin credential"
SMOKE_ACTIVATED_CREDENTIAL = "Backend smoke activated user credential"
SMOKE_INVITED_EMAIL = "invited.user@wealthyfalcon.test"
TENANT_HEADERS = {
    "X-Tenant-Id": str(TENANT_ID),
    "X-Tenant-Slug": "wealthy-falcon",
}
OTHER_TENANT_HEADERS = {
    "X-Tenant-Id": str(OTHER_TENANT_ID),
    "X-Tenant-Slug": "other-falcon",
}
SPOOFED_IDENTITY_HEADERS = {
    "X-Tenant-Id": str(OTHER_TENANT_ID),
    "X-Tenant-Slug": "other-falcon",
    "X-User-Id": str(OTHER_REQUESTING_USER_ID),
}
PLATFORM_TENANT_FIELDS = {
    "id",
    "slug",
    "name",
    "status",
    "plan_code",
    "data_region",
    "locale",
    "timezone",
    "health",
    "limits",
    "created_at",
    "updated_at",
}
CURRENT_TENANT_FIELDS = {
    "id",
    "slug",
    "name",
    "status",
    "plan_code",
    "locale",
    "timezone",
}
TENANT_SETTINGS_FIELDS = {
    "locale",
    "timezone",
    "week_start_day",
    "date_format",
    "time_format",
}
TENANT_FEATURE_FIELDS = {"features"}
FEATURE_FLAG_ITEM_FIELDS = {"key", "enabled", "source"}
FEATURE_DEFAULTS = {
    "organization": False,
    "employees": True,
    "documents": False,
    "leave": True,
    "self_service": False,
    "reporting": True,
    "notifications": False,
}
FORBIDDEN_HR_FIELDS = {
    "document_body",
    "document_count",
    "document_id",
    "document_key",
    "document_name",
    "document_type",
    "document_url",
    "documents",
    "employee_number",
    "employee_count",
    "employee_id",
    "employees",
    "first_name",
    "last_name",
    "department",
    "position",
    "email",
    "leave_count",
    "leave_type",
    "leave_balance",
    "leave_balances",
    "leave_requests",
    "requested_by_user_id",
    "user_id",
    "users",
}
HTTP_METHODS = {"delete", "get", "patch", "post", "put"}
DOCUMENTED_OPENAPI_OPERATIONS = {
    ("get", "/"),
    ("get", "/health"),
    ("post", "/api/v1/auth/activate"),
    ("post", "/api/v1/auth/login"),
    ("post", "/api/v1/auth/logout"),
    ("post", "/api/v1/auth/refresh"),
    ("get", "/api/v1/me"),
    ("post", "/api/v1/platform/tenants"),
    ("get", "/api/v1/platform/tenants"),
    ("get", "/api/v1/platform/tenants/{tenant_id}"),
    ("patch", "/api/v1/platform/tenants/{tenant_id}"),
    ("get", "/api/v1/platform/tenants/{tenant_id}/features"),
    ("patch", "/api/v1/platform/tenants/{tenant_id}/features"),
    ("get", "/api/v1/tenant"),
    ("get", "/api/v1/tenant/settings"),
    ("patch", "/api/v1/tenant/settings"),
    ("get", "/api/v1/tenant/features"),
    ("get", "/api/v1/dashboard/summary"),
    ("get", "/api/v1/employees"),
    ("post", "/api/v1/employees"),
    ("get", "/api/v1/employees/{employee_id}"),
    ("patch", "/api/v1/employees/{employee_id}"),
    ("delete", "/api/v1/employees/{employee_id}"),
    ("get", "/api/v1/employees/{employee_id}/leave-balances"),
    ("get", "/api/v1/leave-requests"),
    ("post", "/api/v1/leave-requests"),
    ("post", "/api/v1/leave-requests/{leave_request_id}/approve"),
    ("post", "/api/v1/leave-requests/{leave_request_id}/reject"),
    ("post", "/api/v1/leave-requests/{leave_request_id}/cancel"),
    ("post", "/api/v1/users/invitations"),
}
DOCUMENTED_RUNTIME_ENDPOINTS = {
    ("get", "/openapi.json"),
}
DOCUMENTED_SMOKE_ENDPOINTS = DOCUMENTED_OPENAPI_OPERATIONS | DOCUMENTED_RUNTIME_ENDPOINTS
PHASE1_SUCCESS_RESPONSES = {
    ("post", "/api/v1/platform/tenants"): "201",
    ("get", "/api/v1/platform/tenants"): "200",
    ("get", "/api/v1/platform/tenants/{tenant_id}"): "200",
    ("patch", "/api/v1/platform/tenants/{tenant_id}"): "200",
    ("get", "/api/v1/platform/tenants/{tenant_id}/features"): "200",
    ("patch", "/api/v1/platform/tenants/{tenant_id}/features"): "200",
    ("get", "/api/v1/tenant"): "200",
    ("get", "/api/v1/tenant/settings"): "200",
    ("patch", "/api/v1/tenant/settings"): "200",
    ("get", "/api/v1/tenant/features"): "200",
}
PHASE1_REQUIRED_PRINCIPALS = {
    operation: "platform"
    for operation in PHASE1_SUCCESS_RESPONSES
    if operation[1].startswith("/api/v1/platform/")
} | {
    operation: "tenant"
    for operation in PHASE1_SUCCESS_RESPONSES
    if operation[1].startswith("/api/v1/tenant")
}
PHASE0_CURSOR_LIST_PATHS = {
    "/api/v1/employees",
    "/api/v1/leave-requests",
}
RESPONSE_META_FIELDS = {"request_id", "trace_id", "correlation_id"}
PAGE_META_FIELDS = RESPONSE_META_FIELDS | {"limit", "next_cursor"}
CORRELATION_RESPONSE_HEADERS = (
    "X-Request-Id",
    "X-Trace-Id",
    "X-Correlation-Id",
)
REQUEST_ID_PATTERN = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9._-]{0,126}[A-Za-z0-9])?")
TRACE_ID_PATTERN = re.compile(r"[0-9a-f]{32}")
DOCUMENTED_ENDPOINT_TABLES = {
    API_IMPLEMENTATION_STATUS_DOC: "## Completed API Surface",
    OPENAPI_ENDPOINT_DRAFT_DOC: "## 0. Güncel uygulama yüzeyi",
}
EXECUTED_DOCUMENTED_ENDPOINTS: set[tuple[str, str]] = set()


async def main(database_url: str | None = None) -> None:
    EXECUTED_DOCUMENTED_ENDPOINTS.clear()
    if database_url is not None:
        _ensure_disposable_postgresql_database(database_url)
    settings = Settings(
        _env_file=None,
        environment="local",
        database_url=database_url or "sqlite+aiosqlite:///:memory:",
    )
    app = create_app(settings=settings)

    async with app.router.lifespan_context(app):
        runtime = getattr(app.state, DATABASE_RUNTIME_STATE_KEY)
        await _prepare_smoke_database(
            runtime.engine,
            create_schema=database_url is None,
        )
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://backend-smoke.local",
        ) as client:
            await _smoke_correlation_middleware(client)
            await _smoke_principal_default_denials(app, client)
            tenant_principal_scope = _install_test_principal_overrides(app)
            await _smoke_system_endpoints(client)
            _smoke_documented_endpoint_tables()
            await _smoke_auth_endpoints(client)
            provisioned_tenant_id = await _smoke_platform_tenant_endpoints(client)
            tenant_principal_scope["tenant_id"] = provisioned_tenant_id
            await _smoke_current_tenant_endpoints(client, provisioned_tenant_id)
            await _smoke_tenant_header_errors(client)
            primary_employee_id, secondary_employee_id, other_employee_id = (
                await _smoke_employee_endpoints(client)
            )
            leave_request_ids = await _smoke_leave_request_endpoints(
                client,
                primary_employee_id,
                secondary_employee_id,
                other_employee_id,
            )
            await _smoke_leave_balance_endpoint(
                client,
                runtime.engine,
                primary_employee_id,
                secondary_employee_id,
                other_employee_id,
            )
            await _smoke_dashboard_endpoint(
                client,
                other_employee_id=other_employee_id,
                other_tenant_leave_request_id=leave_request_ids["other_tenant"],
            )
            _expect_executed_documented_endpoint_coverage()

    print(
        "BACKEND_SMOKE_OK "
        f"tenant_id={TENANT_ID} "
        f"documented_endpoints={len(DOCUMENTED_SMOKE_ENDPOINTS)} "
        "checked=health,landing,openapi,documented_endpoint_tables,"
        "principal_default_and_opposite_denial,"
        "correlation_middleware,phase1_envelopes,platform_cursor_pagination,platform_tenants,"
        "tenant_settings,tenant_features,platform_limits,feature_rollout,tenant_headers,"
        "phase0_contract_compatibility,"
        "documented_endpoint_runtime_coverage,dashboard_counts,employee_filters,employees,"
        "leave_balances,leave_filters,leave_requests,workflow_transitions,auth"
    )


async def _prepare_smoke_database(
    engine: AsyncEngine,
    *,
    create_schema: bool,
) -> None:
    if create_schema:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

    # Fixture setup is an explicit test-admin path. Runtime request sessions are always reduced
    # to tenant or platform capability roles and must never be reused for cross-tenant seeding.
    bootstrap_sessions = async_sessionmaker(engine, expire_on_commit=False)
    async with bootstrap_sessions() as session:
        session.add_all(
            [
                Tenant(
                    id=TENANT_ID,
                    slug="wealthy-falcon",
                    name="Wealthy Falcon HR",
                    status=TenantStatus.ACTIVE.value,
                    plan_code="core",
                    data_region="tr-1",
                    locale="tr-TR",
                    timezone="Europe/Istanbul",
                ),
                Tenant(
                    id=OTHER_TENANT_ID,
                    slug="other-falcon",
                    name="Other Falcon HR",
                    status=TenantStatus.ACTIVE.value,
                    plan_code="core",
                    data_region="tr-1",
                    locale="tr-TR",
                    timezone="Europe/Istanbul",
                ),
                TenantSettings(tenant_id=TENANT_ID),
                TenantSettings(tenant_id=OTHER_TENANT_ID),
                User(
                    id=REQUESTING_USER_ID,
                    tenant_id=TENANT_ID,
                    email="requester@wealthyfalcon.test",
                    full_name="Requesting User",
                    status=UserStatus.ACTIVE.value,
                    password_hash=PasswordManager().hash(SMOKE_ADMIN_CREDENTIAL),
                    can_invite_users=True,
                ),
                User(
                    id=APPROVER_USER_ID,
                    tenant_id=TENANT_ID,
                    email="approver@wealthyfalcon.test",
                    full_name="Approver User",
                    status=UserStatus.ACTIVE.value,
                ),
                User(
                    id=OTHER_REQUESTING_USER_ID,
                    tenant_id=OTHER_TENANT_ID,
                    email="requester@otherfalcon.test",
                    full_name="Other Requesting User",
                    status=UserStatus.ACTIVE.value,
                ),
            ]
        )
        await session.commit()


async def _smoke_correlation_middleware(client: AsyncClient) -> None:
    generated_response = await client.get("/health")
    _expect_json(generated_response, 200, "GET /health generated correlation IDs")
    generated_request_id, generated_trace_id = _correlation_ids(generated_response)

    explicit_request_id = "req_backend_smoke_f1b_001"
    explicit_trace_id = "0123456789abcdef0123456789abcdef"
    explicit_response = await client.get(
        "/health",
        headers={
            "X-Request-Id": explicit_request_id,
            "X-Trace-Id": explicit_trace_id,
        },
    )
    _expect_json(explicit_response, 200, "GET /health explicit correlation IDs")
    _assert_equal(
        explicit_response.headers["X-Request-Id"],
        explicit_request_id,
        "explicit request ID propagation",
    )
    _assert_equal(
        explicit_response.headers["X-Trace-Id"],
        explicit_trace_id,
        "explicit trace ID propagation",
    )

    pii_request_id = "ada.smoke@wealthyfalcon.test"
    unsafe_correlation_id = "Bearer:smoke-placeholder-not-a-credential"
    malformed_trace_id = "0123456789ABCDEF0123456789ABCDEF"
    auth_placeholder = "Bearer smoke-placeholder-not-a-credential"
    replaced_response = await client.get(
        "/health",
        headers={
            "Authorization": auth_placeholder,
            "X-Request-Id": pii_request_id,
            "X-Correlation-Id": unsafe_correlation_id,
            "X-Trace-Id": malformed_trace_id,
        },
    )
    _expect_json(replaced_response, 200, "GET /health unsafe correlation IDs")
    replaced_request_id, replaced_trace_id = _correlation_ids(replaced_response)
    if replaced_request_id in {pii_request_id, unsafe_correlation_id}:
        raise AssertionError("unsafe or PII request metadata was reflected")
    if replaced_trace_id == malformed_trace_id:
        raise AssertionError("malformed trace metadata was reflected")
    _assert_not_reflected(
        replaced_response,
        {pii_request_id, unsafe_correlation_id, malformed_trace_id, auth_placeholder},
        "unsafe correlation request",
    )

    duplicate_request_ids = ("req_duplicate_one", "req_duplicate_two")
    duplicate_trace_ids = (
        "11111111111111111111111111111111",
        "22222222222222222222222222222222",
    )
    duplicate_response = await client.get(
        "/health",
        headers=[
            ("X-Request-Id", duplicate_request_ids[0]),
            ("X-Request-Id", duplicate_request_ids[1]),
            ("X-Correlation-Id", "corr_duplicate_one"),
            ("X-Correlation-Id", "corr_duplicate_two"),
            ("X-Trace-Id", duplicate_trace_ids[0]),
            ("X-Trace-Id", duplicate_trace_ids[1]),
        ],
    )
    _expect_json(duplicate_response, 200, "GET /health duplicate correlation IDs")
    duplicate_request_id, duplicate_trace_id = _correlation_ids(duplicate_response)
    if duplicate_request_id in {
        *duplicate_request_ids,
        "corr_duplicate_one",
        "corr_duplicate_two",
    }:
        raise AssertionError("ambiguous duplicate request metadata was reflected")
    if duplicate_trace_id in duplicate_trace_ids:
        raise AssertionError("ambiguous duplicate trace metadata was reflected")

    if generated_request_id in {replaced_request_id, duplicate_request_id}:
        raise AssertionError("generated request IDs were unexpectedly reused")
    if generated_trace_id in {replaced_trace_id, duplicate_trace_id}:
        raise AssertionError("generated trace IDs were unexpectedly reused")


async def _smoke_principal_default_denials(app: Any, client: AsyncClient) -> None:
    _expect_phase1_error_code(
        await client.get(
            "/api/v1/platform/tenants",
            headers=SPOOFED_IDENTITY_HEADERS,
        ),
        403,
        "platform_access_denied",
        "GET /api/v1/platform/tenants without injected platform principal",
    )
    _expect_phase1_error_code(
        await client.get(
            "/api/v1/tenant",
            headers=SPOOFED_IDENTITY_HEADERS,
        ),
        403,
        "tenant_access_denied",
        "GET /api/v1/tenant without injected tenant principal",
    )
    _expect_phase1_error_code(
        await client.get(
            f"/api/v1/platform/tenants/{TENANT_ID}/features",
            headers=SPOOFED_IDENTITY_HEADERS,
        ),
        403,
        "platform_access_denied",
        "GET platform tenant features without injected platform principal",
    )
    _expect_phase1_error_code(
        await client.get(
            "/api/v1/tenant/features",
            headers=SPOOFED_IDENTITY_HEADERS,
        ),
        403,
        "tenant_access_denied",
        "GET tenant features without injected tenant principal",
    )

    app.dependency_overrides[get_tenant_principal] = lambda: TenantPrincipal(
        tenant_id=TENANT_ID,
        source="backend-api-smoke-opposite-principal",
    )
    try:
        _expect_phase1_error_code(
            await client.get(f"/api/v1/platform/tenants/{TENANT_ID}/features"),
            403,
            "platform_access_denied",
            "tenant principal must not authorize the platform surface",
        )
    finally:
        app.dependency_overrides.pop(get_tenant_principal, None)

    app.dependency_overrides[get_platform_principal] = lambda: PlatformPrincipal(
        source="backend-api-smoke-opposite-principal"
    )
    try:
        _expect_phase1_error_code(
            await client.get("/api/v1/tenant"),
            403,
            "tenant_access_denied",
            "platform principal must not authorize the tenant surface",
        )
    finally:
        app.dependency_overrides.pop(get_platform_principal, None)


def _install_test_principal_overrides(app: Any) -> dict[str, UUID]:
    tenant_scope = {"tenant_id": TENANT_ID}

    def tenant_principal() -> TenantPrincipal:
        return TenantPrincipal(
            tenant_id=tenant_scope["tenant_id"],
            source="backend-api-smoke",
        )

    app.dependency_overrides[get_platform_principal] = lambda: PlatformPrincipal(
        source="backend-api-smoke"
    )
    app.dependency_overrides[get_tenant_principal] = tenant_principal
    return tenant_scope


async def _smoke_system_endpoints(client: AsyncClient) -> None:
    health = _expect_json(
        await _request_documented(client, "get", "/health"),
        200,
        "GET /health",
    )
    _assert_equal(health["status"], "ok", "health status")
    _assert_equal(health["service"], "IK Platform API", "health service")

    landing = await _request_documented(client, "get", "/")
    _expect_status(landing, 200, "GET /")
    _assert_contains(landing.text, "Wealthy Falcon HR", "landing brand")

    openapi = _expect_json(
        await _request_documented(client, "get", "/openapi.json"),
        200,
        "GET /openapi.json",
    )
    _expect_documented_openapi_operations(openapi)
    _expect_phase1_openapi_contracts(openapi)
    _expect_f2a_openapi_contracts(openapi)


async def _smoke_auth_endpoints(client: AsyncClient) -> None:
    admin_login = _expect_phase1_data(
        await _request_documented(
            client,
            "post",
            "/api/v1/auth/login",
            json={
                "tenant_slug": "wealthy-falcon",
                "email": "requester@wealthyfalcon.test",
                "password": SMOKE_ADMIN_CREDENTIAL,
            },
        ),
        200,
        "POST /api/v1/auth/login for invitation admin",
        {"access_token", "token_type", "expires_in", "user"},
    )
    _assert_equal(admin_login["token_type"], "bearer", "auth login token type")
    _assert_equal(
        admin_login["user"]["tenant_id"],
        str(TENANT_ID),
        "auth login tenant",
    )
    access_token = admin_login["access_token"]
    if not isinstance(access_token, str) or not access_token:
        raise AssertionError("auth login must return a non-empty access credential")

    invitation = _expect_phase1_data(
        await _request_documented(
            client,
            "post",
            "/api/v1/users/invitations",
            headers={
                **SPOOFED_IDENTITY_HEADERS,
                "Authorization": f"Bearer {access_token}",
            },
            json={
                "email": SMOKE_INVITED_EMAIL,
                "full_name": "Invited Smoke User",
            },
        ),
        201,
        "POST /api/v1/users/invitations with spoofed tenant headers",
        {"user", "activation_url", "expires_at"},
    )
    _assert_equal(
        invitation["user"]["email"],
        SMOKE_INVITED_EMAIL,
        "invited user email",
    )
    _assert_equal(invitation["user"]["status"], "invited", "invited user status")

    fragment = parse_qs(urlsplit(invitation["activation_url"]).fragment)
    _assert_equal(set(fragment), {"token"}, "activation URL fragment fields")
    activation_token = fragment["token"][0]
    if not activation_token:
        raise AssertionError("activation URL must contain a non-empty fragment credential")

    activated = _expect_phase1_data(
        await _request_documented(
            client,
            "post",
            "/api/v1/auth/activate",
            json={
                "token": activation_token,
                "password": SMOKE_ACTIVATED_CREDENTIAL,
            },
        ),
        200,
        "POST /api/v1/auth/activate",
        {"user"},
    )
    _assert_equal(
        activated["user"]["tenant_id"],
        str(TENANT_ID),
        "activation ignores spoofed invitation tenant headers",
    )
    _assert_equal(
        activated["user"]["email"],
        SMOKE_INVITED_EMAIL,
        "activated user email",
    )

    _expect_phase1_error_code(
        await _request_documented(
            client,
            "post",
            "/api/v1/auth/activate",
            json={
                "token": activation_token,
                "password": SMOKE_ACTIVATED_CREDENTIAL,
            },
        ),
        400,
        "activation_invalid",
        "POST /api/v1/auth/activate rejects token reuse",
    )

    activated_login = _expect_phase1_data(
        await _request_documented(
            client,
            "post",
            "/api/v1/auth/login",
            json={
                "tenant_slug": "wealthy-falcon",
                "email": SMOKE_INVITED_EMAIL,
                "password": SMOKE_ACTIVATED_CREDENTIAL,
            },
        ),
        200,
        "POST /api/v1/auth/login for activated user",
        {"access_token", "token_type", "expires_in", "user"},
    )
    _assert_equal(
        activated_login["user"]["id"],
        invitation["user"]["id"],
        "activated login user",
    )
    activated_access = activated_login["access_token"]
    current_user = _expect_phase1_data(
        await _request_documented(
            client,
            "get",
            "/api/v1/me",
            headers={"Authorization": f"Bearer {activated_access}"},
        ),
        200,
        "GET /api/v1/me before refresh",
        {"user"},
    )
    _assert_equal(current_user["user"], activated_login["user"], "session current user")

    refreshed = _expect_phase1_data(
        await _request_documented(client, "post", "/api/v1/auth/refresh"),
        200,
        "POST /api/v1/auth/refresh",
        {"access_token", "token_type", "expires_in", "user"},
    )
    _assert_equal(refreshed["user"], activated_login["user"], "refreshed user")
    refreshed_access = refreshed["access_token"]
    _expect_status(
        await _request_documented(client, "post", "/api/v1/auth/logout"),
        204,
        "POST /api/v1/auth/logout",
    )
    _expect_phase1_error_code(
        await client.get(
            "/api/v1/me",
            headers={"Authorization": f"Bearer {refreshed_access}"},
        ),
        401,
        "session_invalid",
        "GET /api/v1/me after logout",
    )
    _expect_phase1_error_code(
        await client.post("/api/v1/auth/refresh"),
        401,
        "session_invalid",
        "POST /api/v1/auth/refresh after logout",
    )


async def _smoke_platform_tenant_endpoints(client: AsyncClient) -> UUID:
    created = _expect_phase1_data(
        await _request_documented(
            client,
            "post",
            "/api/v1/platform/tenants",
            headers=SPOOFED_IDENTITY_HEADERS,
            json={
                "slug": "smoke-provisioned-falcon",
                "name": "Smoke Provisioned Falcon",
                "plan_code": "professional",
                "data_region": "eu-1",
                "locale": "en-US",
                "timezone": "Europe/London",
                "settings": {
                    "week_start_day": "sunday",
                    "date_format": "MM/DD/YYYY",
                    "time_format": "12h",
                },
            },
        ),
        201,
        "POST /api/v1/platform/tenants",
        PLATFORM_TENANT_FIELDS,
    )
    provisioned_tenant_id = UUID(created["id"])
    if provisioned_tenant_id in {TENANT_ID, OTHER_TENANT_ID}:
        raise AssertionError("platform provisioning did not generate a new tenant ID")
    _assert_equal(created["status"], "provisioning", "provisioned tenant status")
    _assert_equal(created["health"], "provisioning", "provisioned tenant health")
    _assert_equal(created["plan_code"], "professional", "provisioned tenant plan")
    _assert_equal(created["data_region"], "eu-1", "provisioned tenant region")
    _assert_equal(
        created["limits"],
        {"active_employees": None},
        "unconfigured provisioned tenant limits",
    )

    default_features = _expect_phase1_data(
        await _request_documented(
            client,
            "get",
            f"/api/v1/platform/tenants/{created['id']}/features",
            documented_path="/api/v1/platform/tenants/{tenant_id}/features",
            headers=SPOOFED_IDENTITY_HEADERS,
        ),
        200,
        "GET /api/v1/platform/tenants/{tenant_id}/features",
        TENANT_FEATURE_FIELDS,
    )
    _assert_feature_flags(default_features, {})

    updated_features = _expect_phase1_data(
        await _request_documented(
            client,
            "patch",
            f"/api/v1/platform/tenants/{created['id']}/features",
            documented_path="/api/v1/platform/tenants/{tenant_id}/features",
            headers=SPOOFED_IDENTITY_HEADERS,
            json={"features": [{"key": "organization", "enabled": True}]},
        ),
        200,
        "PATCH /api/v1/platform/tenants/{tenant_id}/features",
        TENANT_FEATURE_FIELDS,
    )
    _assert_feature_flags(updated_features, {"organization": True})

    first_page_response = await _request_documented(
        client,
        "get",
        "/api/v1/platform/tenants",
        headers={
            **SPOOFED_IDENTITY_HEADERS,
            "X-Request-Id": "req_platform_smoke_page_001",
            "X-Trace-Id": "abcdef0123456789abcdef0123456789",
        },
        params={"limit": 2},
    )
    first_page, next_cursor = _expect_phase1_list(
        first_page_response,
        200,
        "GET /api/v1/platform/tenants first cursor page",
        expected_limit=2,
    )
    if next_cursor is None:
        raise AssertionError("platform tenant first page did not expose a continuation cursor")
    _assert_equal(
        first_page_response.headers["X-Request-Id"],
        "req_platform_smoke_page_001",
        "platform list explicit request ID",
    )
    _assert_equal(
        first_page_response.headers["X-Trace-Id"],
        "abcdef0123456789abcdef0123456789",
        "platform list explicit trace ID",
    )

    second_page, terminal_cursor = _expect_phase1_list(
        await client.get(
            "/api/v1/platform/tenants",
            headers=SPOOFED_IDENTITY_HEADERS,
            params={"limit": 2, "cursor": next_cursor},
        ),
        200,
        "GET /api/v1/platform/tenants second cursor page",
        expected_limit=2,
    )
    _assert_equal(terminal_cursor, None, "platform tenant terminal cursor")
    first_page_ids = [tenant["id"] for tenant in first_page]
    second_page_ids = [tenant["id"] for tenant in second_page]
    if set(first_page_ids) & set(second_page_ids):
        raise AssertionError("platform tenant cursor pages overlap")
    listed = first_page + second_page
    _assert_equal(len(listed), 3, "platform tenant list count")
    for index, tenant in enumerate(listed):
        _assert_exact_fields(
            tenant,
            PLATFORM_TENANT_FIELDS,
            f"platform tenant list item {index}",
        )
    listed_created = next(
        (tenant for tenant in listed if tenant["id"] == created["id"]),
        None,
    )
    _assert_equal(listed_created, created, "platform tenant list provisioned item")

    repeated_first_page, _ = _expect_phase1_list(
        await client.get(
            "/api/v1/platform/tenants",
            headers=SPOOFED_IDENTITY_HEADERS,
            params={"limit": 2},
        ),
        200,
        "GET /api/v1/platform/tenants repeated first page",
        expected_limit=2,
    )
    _assert_equal(
        [tenant["id"] for tenant in repeated_first_page],
        first_page_ids,
        "platform tenant deterministic first page",
    )

    for query in (
        {"limit": 0},
        {"limit": 201},
        {"offset": 1},
        {"cursor": "not-a-platform-tenant-cursor"},
    ):
        _expect_phase1_error_code(
            await client.get(
                "/api/v1/platform/tenants",
                headers=SPOOFED_IDENTITY_HEADERS,
                params=query,
            ),
            422,
            "platform_tenant_validation_error",
            f"GET /api/v1/platform/tenants invalid pagination {query}",
        )

    detail = _expect_phase1_data(
        await _request_documented(
            client,
            "get",
            f"/api/v1/platform/tenants/{created['id']}",
            documented_path="/api/v1/platform/tenants/{tenant_id}",
            headers=SPOOFED_IDENTITY_HEADERS,
        ),
        200,
        "GET /api/v1/platform/tenants/{tenant_id}",
        PLATFORM_TENANT_FIELDS,
    )
    _assert_equal(detail, created, "platform tenant detail payload")

    updated = _expect_phase1_data(
        await _request_documented(
            client,
            "patch",
            f"/api/v1/platform/tenants/{created['id']}",
            documented_path="/api/v1/platform/tenants/{tenant_id}",
            headers=SPOOFED_IDENTITY_HEADERS,
            json={
                "name": "Smoke Active Falcon",
                "status": TenantStatus.ACTIVE.value,
                "limits": {"active_employees": 350},
            },
        ),
        200,
        "PATCH /api/v1/platform/tenants/{tenant_id}",
        PLATFORM_TENANT_FIELDS,
    )
    _assert_equal(updated["id"], created["id"], "updated platform tenant id")
    _assert_equal(updated["slug"], created["slug"], "updated platform tenant slug")
    _assert_equal(updated["status"], TenantStatus.ACTIVE.value, "updated tenant status")
    _assert_equal(updated["health"], "healthy", "updated tenant health")
    _assert_equal(updated["name"], "Smoke Active Falcon", "updated tenant name")
    _assert_equal(
        updated["limits"],
        {"active_employees": 350},
        "updated configured tenant limit metadata",
    )
    _assert_no_hr_fields(
        [created, listed, detail, updated, default_features, updated_features],
        "platform tenant responses",
    )
    return provisioned_tenant_id


async def _smoke_current_tenant_endpoints(
    client: AsyncClient,
    provisioned_tenant_id: UUID,
) -> None:
    current = _expect_phase1_data(
        await _request_documented(
            client,
            "get",
            "/api/v1/tenant",
            headers=SPOOFED_IDENTITY_HEADERS,
        ),
        200,
        "GET /api/v1/tenant",
        CURRENT_TENANT_FIELDS,
    )
    _assert_equal(current["id"], str(provisioned_tenant_id), "injected current tenant id")
    _assert_equal(current["slug"], "smoke-provisioned-falcon", "current tenant slug")
    _assert_equal(current["status"], TenantStatus.ACTIVE.value, "current tenant status")
    _assert_equal(current["plan_code"], "professional", "current tenant plan")

    features = _expect_phase1_data(
        await _request_documented(
            client,
            "get",
            "/api/v1/tenant/features",
            headers=SPOOFED_IDENTITY_HEADERS,
        ),
        200,
        "GET /api/v1/tenant/features",
        TENANT_FEATURE_FIELDS,
    )
    _assert_feature_flags(features, {"organization": True})

    settings = _expect_phase1_data(
        await _request_documented(
            client,
            "get",
            "/api/v1/tenant/settings",
            headers=SPOOFED_IDENTITY_HEADERS,
        ),
        200,
        "GET /api/v1/tenant/settings",
        TENANT_SETTINGS_FIELDS,
    )
    _assert_equal(
        settings,
        {
            "locale": "en-US",
            "timezone": "Europe/London",
            "week_start_day": "sunday",
            "date_format": "MM/DD/YYYY",
            "time_format": "12h",
        },
        "provisioned typed tenant settings",
    )

    updated_settings = _expect_phase1_data(
        await _request_documented(
            client,
            "patch",
            "/api/v1/tenant/settings",
            headers=SPOOFED_IDENTITY_HEADERS,
            json={
                "locale": "tr-TR",
                "timezone": "Europe/Istanbul",
                "week_start_day": "monday",
                "date_format": "YYYY-MM-DD",
                "time_format": "24h",
            },
        ),
        200,
        "PATCH /api/v1/tenant/settings",
        TENANT_SETTINGS_FIELDS,
    )
    _assert_equal(
        updated_settings,
        {
            "locale": "tr-TR",
            "timezone": "Europe/Istanbul",
            "week_start_day": "monday",
            "date_format": "YYYY-MM-DD",
            "time_format": "24h",
        },
        "updated typed tenant settings",
    )
    persisted_settings = _expect_phase1_data(
        await client.get(
            "/api/v1/tenant/settings",
            headers=SPOOFED_IDENTITY_HEADERS,
        ),
        200,
        "GET /api/v1/tenant/settings after patch",
        TENANT_SETTINGS_FIELDS,
    )
    _assert_equal(
        persisted_settings,
        updated_settings,
        "persisted typed tenant settings",
    )
    _assert_no_hr_fields(
        [current, features, settings, updated_settings],
        "current tenant and settings responses",
    )


def _expect_documented_openapi_operations(openapi: dict[str, Any]) -> None:
    actual_operations = {
        (method, path)
        for path, path_item in openapi["paths"].items()
        for method in path_item
        if method in HTTP_METHODS
    }
    missing_operations = sorted(DOCUMENTED_OPENAPI_OPERATIONS - actual_operations)
    undocumented_operations = sorted(actual_operations - DOCUMENTED_OPENAPI_OPERATIONS)
    if missing_operations:
        raise AssertionError(
            "OpenAPI is missing documented operations: "
            f"{_format_operations(missing_operations)}"
        )
    if undocumented_operations:
        raise AssertionError(
            "OpenAPI has operations missing from backend smoke documentation: "
            f"{_format_operations(undocumented_operations)}"
        )


def _expect_phase1_openapi_contracts(openapi: dict[str, Any]) -> None:
    paths = openapi["paths"]
    for (method, path), status_code in PHASE1_SUCCESS_RESPONSES.items():
        operation = paths[path][method]
        _assert_equal(
            operation.get("x-required-principal"),
            PHASE1_REQUIRED_PRINCIPALS[(method, path)],
            f"{method.upper()} {path} required principal metadata",
        )
        if "security" in operation:
            raise AssertionError(
                f"{method.upper()} {path} must not advertise a Phase 2 credential scheme"
            )
        success_response = operation["responses"][status_code]
        _assert_equal(
            set(success_response.get("headers", {})),
            set(CORRELATION_RESPONSE_HEADERS),
            f"{method.upper()} {path} documented correlation headers",
        )
        schema = _resolve_openapi_schema(
            openapi,
            success_response["content"]["application/json"]["schema"],
        )
        _assert_equal(
            set(schema.get("properties", {})),
            {"data", "meta"},
            f"{method.upper()} {path} success envelope",
        )

    platform_list = paths["/api/v1/platform/tenants"]["get"]
    platform_parameters = {
        parameter["name"]: parameter for parameter in platform_list["parameters"]
    }
    _assert_equal(
        set(platform_parameters),
        {"cursor", "limit"},
        "platform tenant cursor-only query parameters",
    )
    limit_schema = platform_parameters["limit"]["schema"]
    _assert_equal(limit_schema.get("default"), 50, "platform tenant default limit")
    _assert_equal(limit_schema.get("minimum"), 1, "platform tenant minimum limit")
    _assert_equal(limit_schema.get("maximum"), 200, "platform tenant maximum limit")
    _assert_contains(
        platform_parameters["cursor"].get("description", "").lower(),
        "opaque",
        "platform tenant cursor description",
    )
    platform_list_schema = _resolve_openapi_schema(
        openapi,
        platform_list["responses"]["200"]["content"]["application/json"]["schema"],
    )
    _assert_equal(
        platform_list_schema["properties"]["data"].get("type"),
        "array",
        "platform tenant list data type",
    )
    platform_page_meta = _resolve_openapi_schema(
        openapi,
        platform_list_schema["properties"]["meta"],
    )
    _assert_equal(
        set(platform_page_meta.get("properties", {})),
        PAGE_META_FIELDS,
        "platform tenant page metadata fields",
    )
    _assert_equal(
        platform_page_meta["properties"]["limit"].get("maximum"),
        200,
        "platform tenant page metadata maximum limit",
    )

    schemas = openapi["components"]["schemas"]
    _assert_equal(
        schemas["FeatureFlagKey"].get("enum"),
        list(FEATURE_DEFAULTS),
        "typed feature flag OpenAPI catalog",
    )
    _assert_equal(
        set(schemas["TenantFeatureFlagRead"].get("properties", {})),
        FEATURE_FLAG_ITEM_FIELDS,
        "feature flag response fields",
    )
    _assert_equal(
        set(schemas["TenantFeaturesUpdate"].get("properties", {})),
        TENANT_FEATURE_FIELDS,
        "feature update allowlist",
    )
    _assert_equal(
        schemas["TenantFeaturesUpdate"]["properties"]["features"].get("maxItems"),
        len(FEATURE_DEFAULTS),
        "feature update catalog bound",
    )
    _assert_equal(
        schemas["TenantPlatformRead"]["properties"]["limits"].get("$ref"),
        "#/components/schemas/TenantLimitsRead",
        "platform metadata configured limits schema",
    )

    for path in PHASE0_CURSOR_LIST_PATHS:
        operation = paths[path]["get"]
        response_schema = _resolve_openapi_schema(
            openapi,
            operation["responses"]["200"]["content"]["application/json"]["schema"],
        )
        _assert_equal(
            response_schema.get("type"),
            "array",
            f"GET {path} Phase 0 plain-array response",
        )
        parameters = {parameter["name"]: parameter for parameter in operation["parameters"]}
        _assert_equal(
            parameters["offset"].get("deprecated"),
            True,
            f"GET {path} deprecated offset parameter",
        )
        _assert_contains(
            parameters["offset"].get("description", "").lower(),
            "compatibility",
            f"GET {path} offset compatibility note",
        )
        if "X-Next-Cursor" not in operation["responses"]["200"].get("headers", {}):
            raise AssertionError(f"GET {path} does not document X-Next-Cursor")


def _expect_f2a_openapi_contracts(openapi: dict[str, Any]) -> None:
    paths = openapi["paths"]
    security_schemes = openapi["components"].get("securitySchemes", {})
    _assert_equal(set(security_schemes), {"BearerAuth"}, "F2A security schemes")
    bearer = security_schemes["BearerAuth"]
    _assert_equal(bearer.get("type"), "http", "F2A bearer type")
    _assert_equal(bearer.get("scheme"), "bearer", "F2A bearer scheme")

    login = paths["/api/v1/auth/login"]["post"]
    activation = paths["/api/v1/auth/activate"]["post"]
    invitation = paths["/api/v1/users/invitations"]["post"]
    refresh = paths["/api/v1/auth/refresh"]["post"]
    logout = paths["/api/v1/auth/logout"]["post"]
    me = paths["/api/v1/me"]["get"]
    for operation, label in (
        (login, "F2A login"),
        (activation, "F2A activation"),
        (refresh, "F2B refresh"),
        (logout, "F2B logout"),
    ):
        if "security" in operation:
            raise AssertionError(f"{label} must remain a public credential endpoint")
    _assert_equal(
        invitation.get("security"),
        [{"BearerAuth": []}],
        "F2A invitation bearer requirement",
    )
    _assert_equal(me.get("security"), [{"BearerAuth": []}], "F2B me bearer requirement")

    for operation, success_status, label in (
        (login, "200", "F2A login"),
        (activation, "200", "F2A activation"),
        (invitation, "201", "F2A invitation"),
        (refresh, "200", "F2B refresh"),
        (me, "200", "F2B me"),
    ):
        success_response = operation["responses"][success_status]
        _assert_equal(
            set(success_response.get("headers", {})),
            set(CORRELATION_RESPONSE_HEADERS),
            f"{label} documented correlation headers",
        )
        schema = _resolve_openapi_schema(
            openapi,
            success_response["content"]["application/json"]["schema"],
        )
        _assert_equal(
            set(schema.get("properties", {})),
            {"data", "meta"},
            f"{label} success envelope",
        )
    _assert_equal(
        set(logout["responses"]["204"].get("headers", {})),
        set(CORRELATION_RESPONSE_HEADERS),
        "F2B logout documented correlation headers",
    )


def _resolve_openapi_schema(
    openapi: dict[str, Any],
    schema: dict[str, Any],
) -> dict[str, Any]:
    reference = schema.get("$ref")
    if reference is None:
        return schema
    prefix = "#/components/schemas/"
    if not isinstance(reference, str) or not reference.startswith(prefix):
        raise AssertionError(f"unsupported OpenAPI schema reference: {reference!r}")
    return openapi["components"]["schemas"][reference.removeprefix(prefix)]


def _smoke_documented_endpoint_tables() -> None:
    for doc_path, heading in DOCUMENTED_ENDPOINT_TABLES.items():
        _expect_documented_endpoint_table(doc_path, heading)


def _expect_documented_endpoint_table(doc_path: Path, heading: str) -> None:
    section = _read_markdown_section(doc_path, heading)
    actual_endpoints = _parse_markdown_endpoint_table(section)
    missing_endpoints = sorted(DOCUMENTED_SMOKE_ENDPOINTS - actual_endpoints)
    extra_endpoints = sorted(actual_endpoints - DOCUMENTED_SMOKE_ENDPOINTS)
    if missing_endpoints:
        raise AssertionError(
            f"{doc_path} is missing smoke-documented endpoints under {heading}: "
            f"{_format_operations(missing_endpoints)}"
        )
    if extra_endpoints:
        raise AssertionError(
            f"{doc_path} lists endpoints missing from backend smoke coverage under {heading}: "
            f"{_format_operations(extra_endpoints)}"
        )


async def _request_documented(
    client: AsyncClient,
    method: str,
    path: str,
    *,
    documented_path: str | None = None,
    **kwargs: Any,
) -> Response:
    response = await client.request(method.upper(), path, **kwargs)
    _record_documented_endpoint(method, documented_path or path)
    return response


def _record_documented_endpoint(method: str, path: str) -> None:
    operation = (method.lower(), path)
    if operation not in DOCUMENTED_SMOKE_ENDPOINTS:
        raise AssertionError(
            "Smoke tried to record an endpoint outside documented coverage: "
            f"{_format_operations([operation])}"
        )
    EXECUTED_DOCUMENTED_ENDPOINTS.add(operation)


def _expect_executed_documented_endpoint_coverage() -> None:
    missing_endpoints = sorted(DOCUMENTED_SMOKE_ENDPOINTS - EXECUTED_DOCUMENTED_ENDPOINTS)
    if missing_endpoints:
        raise AssertionError(
            "Backend smoke did not execute documented endpoints: "
            f"{_format_operations(missing_endpoints)}"
        )


def _read_markdown_section(doc_path: Path, heading: str) -> list[str]:
    lines = doc_path.read_text(encoding="utf-8").splitlines()
    try:
        start = lines.index(heading) + 1
    except ValueError as exc:
        raise AssertionError(f"{doc_path} is missing heading {heading!r}") from exc

    heading_level = len(heading) - len(heading.lstrip("#"))
    section: list[str] = []
    for line in lines[start:]:
        if line.startswith("#"):
            line_level = len(line) - len(line.lstrip("#"))
            if line_level <= heading_level:
                break
        section.append(line)
    return section


def _parse_markdown_endpoint_table(lines: list[str]) -> set[tuple[str, str]]:
    endpoints: set[tuple[str, str]] = set()
    for line in lines:
        if not line.startswith("|"):
            continue
        cells = [cell.strip().strip("`") for cell in line.strip().strip("|").split("|")]
        if len(cells) < 2:
            continue
        method = cells[0].lower()
        path = cells[1]
        if method in HTTP_METHODS and path.startswith("/"):
            endpoints.add((method, path))
    return endpoints


async def _smoke_tenant_header_errors(client: AsyncClient) -> None:
    _expect_error_code(
        await client.get(
            "/api/v1/dashboard/summary",
            headers={"X-Correlation-Id": "smoke-tenant-missing"},
        ),
        400,
        "tenant_header_missing",
        "GET /api/v1/dashboard/summary missing tenant header",
    )
    _expect_error_code(
        await client.get(
            "/api/v1/dashboard/summary",
            headers={
                "X-Tenant-Id": str(TENANT_ID).replace("-", ""),
                "X-Correlation-Id": "smoke-tenant-invalid",
            },
        ),
        400,
        "tenant_header_invalid",
        "GET /api/v1/dashboard/summary invalid tenant header",
    )
    _expect_error_code(
        await client.get(
            "/api/v1/dashboard/summary",
            headers=[
                ("X-Tenant-Id", str(TENANT_ID)),
                ("X-Tenant-Id", str(OTHER_TENANT_ID)),
                ("X-Correlation-Id", "smoke-tenant-repeated"),
            ],
        ),
        400,
        "tenant_header_invalid",
        "GET /api/v1/dashboard/summary repeated tenant header",
    )


async def _smoke_employee_endpoints(client: AsyncClient) -> tuple[str, str, str]:
    today = date.today().isoformat()
    employee_idempotency_headers = {
        **TENANT_HEADERS,
        "X-Idempotency-Key": "smoke-employee-create-001",
    }
    employee_payload = {
        "employee_number": "WF-SMOKE-001",
        "first_name": "Ada",
        "last_name": "Yilmaz",
        "email": "ada.smoke@wealthyfalcon.test",
        "department": "People",
        "position": "HR Specialist",
        "employment_start_date": today,
    }
    created = await _create_employee(
        client,
        employee_payload,
        headers=employee_idempotency_headers,
    )
    replayed_create = await _create_employee(
        client,
        employee_payload,
        headers=employee_idempotency_headers,
    )
    _assert_equal(replayed_create, created, "employee create idempotency replay")
    employee_id = created["id"]
    secondary = await _create_employee(
        client,
        {
            "employee_number": "WF-SMOKE-002",
            "first_name": "Ece",
            "last_name": "Kaya",
            "email": "ece.smoke@wealthyfalcon.test",
            "department": "Engineering",
            "position": "Backend Engineer",
            "employment_start_date": today,
        },
    )
    secondary_employee_id = secondary["id"]
    other_tenant_employee = await _create_employee(
        client,
        {
            "employee_number": "WF-SMOKE-001",
            "first_name": "Other",
            "last_name": "Tenant",
            "email": "cross.tenant@wealthyfalcon.test",
            "department": "People",
            "position": "Tenant Isolation Check",
            "employment_start_date": today,
        },
        headers=OTHER_TENANT_HEADERS,
    )
    other_employee_id = other_tenant_employee["id"]

    employees = _expect_phase0_list(
        await _request_documented(
            client,
            "get",
            "/api/v1/employees",
            headers=TENANT_HEADERS,
        ),
        200,
        "GET /api/v1/employees",
    )
    _assert_equal(
        [employee["employee_number"] for employee in employees],
        ["WF-SMOKE-001", "WF-SMOKE-002"],
        "employee list tenant scope",
    )

    blank_filter_employees = _expect_json(
        await client.get(
            "/api/v1/employees",
            headers=TENANT_HEADERS,
            params={"department": "   ", "q": "   "},
        ),
        200,
        "GET /api/v1/employees blank filters",
    )
    _assert_equal(
        [employee["employee_number"] for employee in blank_filter_employees],
        ["WF-SMOKE-001", "WF-SMOKE-002"],
        "employee blank filters are ignored",
    )

    department_filtered = _expect_json(
        await client.get(
            "/api/v1/employees",
            headers=TENANT_HEADERS,
            params={"department": "people"},
        ),
        200,
        "GET /api/v1/employees?department=people",
    )
    _assert_equal(
        [employee["employee_number"] for employee in department_filtered],
        ["WF-SMOKE-001"],
        "employee department filter",
    )
    partial_department_filtered = _expect_json(
        await client.get(
            "/api/v1/employees",
            headers=TENANT_HEADERS,
            params={"department": "peop"},
        ),
        200,
        "GET /api/v1/employees?department=peop",
    )
    _assert_equal(
        partial_department_filtered,
        [],
        "employee department filter requires exact match",
    )
    engineering_filtered = _expect_json(
        await client.get(
            "/api/v1/employees",
            headers=TENANT_HEADERS,
            params={"department": "ENGINEERING"},
        ),
        200,
        "GET /api/v1/employees?department=ENGINEERING",
    )
    _assert_equal(
        [employee["employee_number"] for employee in engineering_filtered],
        ["WF-SMOKE-002"],
        "employee department filter is case-insensitive",
    )
    trimmed_department_filtered = _expect_json(
        await client.get(
            "/api/v1/employees",
            headers=TENANT_HEADERS,
            params={"department": " People "},
        ),
        200,
        "GET /api/v1/employees?department=%20People%20",
    )
    _assert_equal(
        [employee["employee_number"] for employee in trimmed_department_filtered],
        ["WF-SMOKE-001"],
        "employee department filter trims whitespace",
    )

    search_filtered = _expect_json(
        await client.get(
            "/api/v1/employees",
            headers=TENANT_HEADERS,
            params={"q": "ADA.SMOKE"},
        ),
        200,
        "GET /api/v1/employees?q=ADA.SMOKE",
    )
    _assert_equal(
        [employee["employee_number"] for employee in search_filtered],
        ["WF-SMOKE-001"],
        "employee q filter",
    )
    number_search_filtered = _expect_json(
        await client.get(
            "/api/v1/employees",
            headers=TENANT_HEADERS,
            params={"q": "002"},
        ),
        200,
        "GET /api/v1/employees?q=002",
    )
    _assert_equal(
        [employee["employee_number"] for employee in number_search_filtered],
        ["WF-SMOKE-002"],
        "employee q filter searches employee_number",
    )
    trimmed_search_filtered = _expect_json(
        await client.get(
            "/api/v1/employees",
            headers=TENANT_HEADERS,
            params={"q": " ADA.SMOKE "},
        ),
        200,
        "GET /api/v1/employees?q=%20ADA.SMOKE%20",
    )
    _assert_equal(
        [employee["employee_number"] for employee in trimmed_search_filtered],
        ["WF-SMOKE-001"],
        "employee q filter trims whitespace",
    )
    cross_tenant_search_filtered = _expect_json(
        await client.get(
            "/api/v1/employees",
            headers=TENANT_HEADERS,
            params={"q": "cross.tenant"},
        ),
        200,
        "GET /api/v1/employees?q=cross.tenant",
    )
    _assert_equal(cross_tenant_search_filtered, [], "employee q filter tenant scope")

    wildcard_search_filtered = _expect_json(
        await client.get(
            "/api/v1/employees",
            headers=TENANT_HEADERS,
            params={"q": "%"},
        ),
        200,
        "GET /api/v1/employees?q=%25",
    )
    _assert_equal(
        wildcard_search_filtered,
        [],
        "employee q filter treats SQL wildcard as literal text",
    )
    name_search_filtered = _expect_json(
        await client.get(
            "/api/v1/employees",
            headers=TENANT_HEADERS,
            params={"q": "Yilmaz"},
        ),
        200,
        "GET /api/v1/employees?q=Yilmaz",
    )
    _assert_equal(
        name_search_filtered,
        [],
        "employee q filter does not search names",
    )

    detail = _expect_json(
        await _request_documented(
            client,
            "get",
            f"/api/v1/employees/{employee_id}",
            documented_path="/api/v1/employees/{employee_id}",
            headers=TENANT_HEADERS,
        ),
        200,
        "GET /api/v1/employees/{employee_id}",
    )
    _assert_equal(detail["employee_number"], "WF-SMOKE-001", "employee detail number")

    updated = _expect_json(
        await _request_documented(
            client,
            "patch",
            f"/api/v1/employees/{employee_id}",
            documented_path="/api/v1/employees/{employee_id}",
            headers=TENANT_HEADERS,
            json={"status": EmployeeStatus.ON_LEAVE.value},
        ),
        200,
        "PATCH /api/v1/employees/{employee_id}",
    )
    _assert_equal(updated["status"], EmployeeStatus.ON_LEAVE.value, "employee status")

    status_filtered = _expect_json(
        await client.get(
            "/api/v1/employees",
            headers=TENANT_HEADERS,
            params={"status": EmployeeStatus.ON_LEAVE.value},
        ),
        200,
        "GET /api/v1/employees?status=on_leave",
    )
    _assert_equal(
        [employee["employee_number"] for employee in status_filtered],
        ["WF-SMOKE-001"],
        "employee status filter",
    )
    active_filtered = _expect_json(
        await client.get(
            "/api/v1/employees",
            headers=TENANT_HEADERS,
            params={"status": EmployeeStatus.ACTIVE.value},
        ),
        200,
        "GET /api/v1/employees?status=active",
    )
    _assert_equal(
        [employee["employee_number"] for employee in active_filtered],
        ["WF-SMOKE-002"],
        "employee active status filter",
    )
    _expect_error_code(
        await client.get(
            "/api/v1/employees",
            headers=TENANT_HEADERS,
            params={"status": "disabled"},
        ),
        422,
        "employee_validation_error",
        "GET /api/v1/employees?status=disabled",
    )
    for params in ({"limit": 0}, {"limit": 201}, {"offset": -1}):
        _expect_error_code(
            await client.get(
                "/api/v1/employees",
                headers=TENANT_HEADERS,
                params=params,
            ),
            422,
            "employee_validation_error",
            "GET /api/v1/employees invalid pagination",
        )
    combined_filtered = _expect_json(
        await client.get(
            "/api/v1/employees",
            headers=TENANT_HEADERS,
            params={
                "department": "people",
                "status": EmployeeStatus.ON_LEAVE.value,
                "q": "WF-SMOKE-001",
            },
        ),
        200,
        "GET /api/v1/employees combined filters",
    )
    _assert_equal(
        [employee["employee_number"] for employee in combined_filtered],
        ["WF-SMOKE-001"],
        "employee combined filters",
    )
    conflicting_combined_filtered = _expect_json(
        await client.get(
            "/api/v1/employees",
            headers=TENANT_HEADERS,
            params={
                "department": "engineering",
                "status": EmployeeStatus.ON_LEAVE.value,
                "q": "WF-SMOKE-001",
            },
        ),
        200,
        "GET /api/v1/employees conflicting combined filters",
    )
    _assert_equal(
        conflicting_combined_filtered,
        [],
        "employee conflicting combined filters",
    )

    employee_cursor_response = await client.get(
        "/api/v1/employees",
        headers=TENANT_HEADERS,
        params={"limit": 1},
    )
    employee_cursor_page = _expect_phase0_list(
        employee_cursor_response,
        200,
        "GET /api/v1/employees?limit=1 cursor first page",
    )
    employee_cursor = employee_cursor_response.headers.get("X-Next-Cursor")
    if employee_cursor is None:
        raise AssertionError("employee cursor first page did not expose X-Next-Cursor")
    employee_next_page = _expect_phase0_list(
        await client.get(
            "/api/v1/employees",
            headers=TENANT_HEADERS,
            params={"limit": 1, "cursor": employee_cursor},
        ),
        200,
        "GET /api/v1/employees?limit=1&cursor=<cursor>",
    )
    _assert_equal(
        [employee["employee_number"] for employee in employee_cursor_page + employee_next_page],
        ["WF-SMOKE-001", "WF-SMOKE-002"],
        "employee deterministic cursor pagination",
    )
    _expect_error_code(
        await client.get(
            "/api/v1/employees",
            headers=TENANT_HEADERS,
            params={"cursor": employee_cursor, "offset": 1},
        ),
        422,
        "employee_validation_error",
        "GET /api/v1/employees cursor and offset conflict",
    )

    delete_candidate = await _create_employee(
        client,
        {
            "employee_number": "WF-SMOKE-DELETE",
            "first_name": "Delete",
            "last_name": "Candidate",
            "employment_start_date": today,
        },
    )
    paginated = _expect_json(
        await client.get(
            "/api/v1/employees",
            headers=TENANT_HEADERS,
            params={"limit": 1, "offset": 2},
        ),
        200,
        "GET /api/v1/employees?limit=1&offset=2",
    )
    _assert_equal(
        [employee["employee_number"] for employee in paginated],
        ["WF-SMOKE-DELETE"],
        "employee pagination",
    )
    _expect_status(
        await _request_documented(
            client,
            "delete",
            f"/api/v1/employees/{delete_candidate['id']}",
            documented_path="/api/v1/employees/{employee_id}",
            headers=TENANT_HEADERS,
        ),
        204,
        "DELETE /api/v1/employees/{employee_id}",
    )
    _expect_status(
        await client.get(
            f"/api/v1/employees/{delete_candidate['id']}",
            headers=TENANT_HEADERS,
        ),
        404,
        "GET archived /api/v1/employees/{employee_id}",
    )
    _expect_status(
        await client.delete(
            f"/api/v1/employees/{delete_candidate['id']}",
            headers=TENANT_HEADERS,
        ),
        204,
        "repeat archive /api/v1/employees/{employee_id}",
    )

    terminated = await _create_employee(
        client,
        {
            "employee_number": "WF-SMOKE-TERMINATED",
            "first_name": "Terminated",
            "last_name": "Employee",
            "department": "People",
            "position": "Former HR Specialist",
            "status": EmployeeStatus.TERMINATED.value,
            "employment_start_date": today,
            "employment_end_date": today,
        },
    )
    terminated_filtered = _expect_json(
        await client.get(
            "/api/v1/employees",
            headers=TENANT_HEADERS,
            params={"status": EmployeeStatus.TERMINATED.value},
        ),
        200,
        "GET /api/v1/employees?status=terminated",
    )
    _assert_equal(
        [employee["id"] for employee in terminated_filtered],
        [terminated["id"]],
        "employee terminated status filter",
    )

    return employee_id, secondary_employee_id, other_employee_id


async def _smoke_leave_balance_endpoint(
    client: AsyncClient,
    engine: AsyncEngine,
    employee_id: str,
    secondary_employee_id: str,
    other_employee_id: str,
) -> None:
    period_year = date.today().year
    balance_id = uuid4()
    other_balance_id = uuid4()
    bootstrap_sessions = async_sessionmaker(engine, expire_on_commit=False)
    async with bootstrap_sessions() as session:
        session.add_all(
            [
                LeaveBalanceSummary(
                    id=balance_id,
                    tenant_id=TENANT_ID,
                    employee_id=UUID(employee_id),
                    leave_type="annual",
                    period_year=period_year,
                    opening_balance_days=20.0,
                    used_days=5.0,
                    planned_days=2.0,
                ),
                LeaveBalanceSummary(
                    id=other_balance_id,
                    tenant_id=OTHER_TENANT_ID,
                    employee_id=UUID(other_employee_id),
                    leave_type="annual",
                    period_year=period_year,
                    opening_balance_days=99.0,
                    used_days=0.0,
                    planned_days=0.0,
                ),
            ]
        )
        await session.commit()

    balances = _expect_phase0_list(
        await _request_documented(
            client,
            "get",
            f"/api/v1/employees/{employee_id}/leave-balances",
            documented_path="/api/v1/employees/{employee_id}/leave-balances",
            headers=TENANT_HEADERS,
            params={"period_year": period_year},
        ),
        200,
        "GET /api/v1/employees/{employee_id}/leave-balances",
    )
    _assert_equal(len(balances), 1, "leave balance summary count")
    _assert_equal(balances[0]["id"], str(balance_id), "leave balance summary id")
    _assert_equal(balances[0]["remaining_days"], 13.0, "leave balance remaining_days")
    _assert_equal(
        balances[0]["calculation_mode"],
        "manual_placeholder",
        "leave balance calculation_mode",
    )
    _assert_equal(
        balances[0]["external_integration_enabled"],
        False,
        "leave balance external integration flag",
    )
    if "tenant_id" in balances[0]:
        raise AssertionError("leave balance summary leaked tenant_id")

    synthetic_balances = _expect_json(
        await client.get(
            f"/api/v1/employees/{secondary_employee_id}/leave-balances",
            headers=TENANT_HEADERS,
            params={"period_year": period_year},
        ),
        200,
        "GET /api/v1/employees/{employee_id}/leave-balances with only leave requests",
    )
    _assert_equal(
        synthetic_balances,
        [],
        "leave balance does not synthesize rows from leave requests",
    )

    _expect_error_code(
        await client.get(
            f"/api/v1/employees/{other_employee_id}/leave-balances",
            headers=TENANT_HEADERS,
        ),
        404,
        "employee_not_found",
        "GET cross-tenant /api/v1/employees/{employee_id}/leave-balances",
    )


async def _smoke_leave_request_endpoints(
    client: AsyncClient,
    employee_id: str,
    secondary_employee_id: str,
    other_employee_id: str,
) -> dict[str, str]:
    pending_request = await _create_leave_request(
        client,
        secondary_employee_id,
        day_offset=7,
        leave_type="personal",
    )
    approved_request = await _create_leave_request(client, employee_id, day_offset=14)
    rejected_request = await _create_leave_request(client, employee_id, day_offset=21)
    cancelled_request = await _create_leave_request(client, employee_id, day_offset=28)
    other_tenant_request = await _create_leave_request(
        client,
        other_employee_id,
        day_offset=35,
        headers=OTHER_TENANT_HEADERS,
        requested_by_user_id=str(OTHER_REQUESTING_USER_ID),
    )

    decision_note = "W3B2 backend smoke decision"
    decision_payload = {
        "decided_by_user_id": str(APPROVER_USER_ID),
        "decision_note": decision_note,
    }
    approved = _expect_json(
        await _request_documented(
            client,
            "post",
            f"/api/v1/leave-requests/{approved_request['id']}/approve",
            documented_path="/api/v1/leave-requests/{leave_request_id}/approve",
            headers={
                **TENANT_HEADERS,
                "X-Idempotency-Key": "smoke-leave-approve-001",
            },
            json=decision_payload,
        ),
        200,
        "POST /api/v1/leave-requests/{leave_request_id}/approve",
    )
    _assert_equal(
        approved["status"],
        LeaveRequestStatus.APPROVED.value,
        "approved leave status",
    )
    _assert_equal(
        approved["decided_by_user_id"],
        str(APPROVER_USER_ID),
        "approved leave decider",
    )
    _assert_equal(
        approved["decision_note"],
        decision_note,
        "approved leave decision note",
    )
    replayed_approval = _expect_json(
        await client.post(
            f"/api/v1/leave-requests/{approved_request['id']}/approve",
            headers={
                **TENANT_HEADERS,
                "X-Idempotency-Key": "smoke-leave-approve-001",
            },
            json=decision_payload,
        ),
        200,
        "replay POST /api/v1/leave-requests/{leave_request_id}/approve",
    )
    _assert_equal(replayed_approval, approved, "leave approval idempotency replay")

    rejected = _expect_json(
        await _request_documented(
            client,
            "post",
            f"/api/v1/leave-requests/{rejected_request['id']}/reject",
            documented_path="/api/v1/leave-requests/{leave_request_id}/reject",
            headers=TENANT_HEADERS,
            json=decision_payload,
        ),
        200,
        "POST /api/v1/leave-requests/{leave_request_id}/reject",
    )
    _assert_equal(
        rejected["status"],
        LeaveRequestStatus.REJECTED.value,
        "rejected leave status",
    )
    _assert_equal(
        rejected["decided_by_user_id"],
        str(APPROVER_USER_ID),
        "rejected leave decider",
    )
    _assert_equal(
        rejected["decision_note"],
        decision_note,
        "rejected leave decision note",
    )

    cancelled = _expect_json(
        await _request_documented(
            client,
            "post",
            f"/api/v1/leave-requests/{cancelled_request['id']}/cancel",
            documented_path="/api/v1/leave-requests/{leave_request_id}/cancel",
            headers=TENANT_HEADERS,
            json=decision_payload,
        ),
        200,
        "POST /api/v1/leave-requests/{leave_request_id}/cancel",
    )
    _assert_equal(
        cancelled["status"],
        LeaveRequestStatus.CANCELLED.value,
        "cancelled leave status",
    )
    _assert_equal(
        cancelled["decided_by_user_id"],
        str(APPROVER_USER_ID),
        "cancelled leave decider",
    )
    _assert_equal(
        cancelled["decision_note"],
        decision_note,
        "cancelled leave decision note",
    )

    await _expect_leave_request_transition_conflicts(
        client,
        decision_payload=decision_payload,
        request_ids_by_status={
            LeaveRequestStatus.APPROVED.value: approved_request["id"],
            LeaveRequestStatus.REJECTED.value: rejected_request["id"],
            LeaveRequestStatus.CANCELLED.value: cancelled_request["id"],
        },
    )
    _expect_error_code(
        await client.post(
            f"/api/v1/leave-requests/{other_tenant_request['id']}/approve",
            headers=TENANT_HEADERS,
            json=decision_payload,
        ),
        404,
        "leave_request_not_found",
        "POST cross-tenant /api/v1/leave-requests/{leave_request_id}/approve",
    )
    _expect_error_code(
        await client.post(
            f"/api/v1/leave-requests/{pending_request['id']}/approve",
            headers=TENANT_HEADERS,
            json={
                "decided_by_user_id": str(OTHER_REQUESTING_USER_ID),
                "decision_note": "Cross tenant decider",
            },
        ),
        404,
        "user_not_found",
        "POST /api/v1/leave-requests/{leave_request_id}/approve cross-tenant user",
    )

    leave_requests = _expect_phase0_list(
        await _request_documented(
            client,
            "get",
            "/api/v1/leave-requests",
            headers=TENANT_HEADERS,
        ),
        200,
        "GET /api/v1/leave-requests",
    )
    statuses = {leave_request["status"] for leave_request in leave_requests}
    _assert_equal(
        statuses,
        {
            LeaveRequestStatus.PENDING.value,
            LeaveRequestStatus.APPROVED.value,
            LeaveRequestStatus.REJECTED.value,
            LeaveRequestStatus.CANCELLED.value,
        },
        "leave request statuses",
    )
    _assert_equal(
        {leave_request["id"] for leave_request in leave_requests},
        {
            pending_request["id"],
            approved_request["id"],
            rejected_request["id"],
            cancelled_request["id"],
        },
        "leave request list tenant scope",
    )

    paginated = _expect_json(
        await client.get(
            "/api/v1/leave-requests",
            headers=TENANT_HEADERS,
            params={"limit": 2, "offset": 1},
        ),
        200,
        "GET /api/v1/leave-requests?limit=2&offset=1",
    )
    _assert_equal(len(paginated), 2, "leave request pagination")

    leave_cursor_response = await client.get(
        "/api/v1/leave-requests",
        headers=TENANT_HEADERS,
        params={"limit": 1},
    )
    leave_cursor_page = _expect_phase0_list(
        leave_cursor_response,
        200,
        "GET /api/v1/leave-requests?limit=1 cursor first page",
    )
    leave_cursor = leave_cursor_response.headers.get("X-Next-Cursor")
    if leave_cursor is None:
        raise AssertionError("leave cursor first page did not expose X-Next-Cursor")
    leave_next_page = _expect_phase0_list(
        await client.get(
            "/api/v1/leave-requests",
            headers=TENANT_HEADERS,
            params={"limit": 1, "cursor": leave_cursor},
        ),
        200,
        "GET /api/v1/leave-requests?limit=1&cursor=<cursor>",
    )
    _assert_equal(len(leave_cursor_page + leave_next_page), 2, "leave cursor page size")
    _assert_equal(
        len({item["id"] for item in leave_cursor_page + leave_next_page}),
        2,
        "leave cursor pages do not overlap",
    )
    _expect_error_code(
        await client.get(
            "/api/v1/leave-requests",
            headers=TENANT_HEADERS,
            params={"cursor": leave_cursor, "offset": 1},
        ),
        422,
        "leave_request_validation_error",
        "GET /api/v1/leave-requests cursor and offset conflict",
    )

    for params in ({"limit": 0}, {"limit": 201}, {"offset": -1}):
        _expect_error_code(
            await client.get(
                "/api/v1/leave-requests",
                headers=TENANT_HEADERS,
                params=params,
            ),
            422,
            "leave_request_validation_error",
            "GET /api/v1/leave-requests invalid pagination",
        )

    approved_filtered = _expect_json(
        await client.get(
            "/api/v1/leave-requests",
            headers=TENANT_HEADERS,
            params={"status": "approved"},
        ),
        200,
        "GET /api/v1/leave-requests?status=approved",
    )
    _assert_equal(
        [leave_request["id"] for leave_request in approved_filtered],
        [approved_request["id"]],
        "leave request status filter",
    )
    pending_filtered = _expect_json(
        await client.get(
            "/api/v1/leave-requests",
            headers=TENANT_HEADERS,
            params={"status": LeaveRequestStatus.PENDING.value},
        ),
        200,
        "GET /api/v1/leave-requests?status=pending",
    )
    _assert_equal(
        [leave_request["id"] for leave_request in pending_filtered],
        [pending_request["id"]],
        "leave request pending status filter",
    )
    for status_value, expected_id in (
        (LeaveRequestStatus.REJECTED.value, rejected_request["id"]),
        (LeaveRequestStatus.CANCELLED.value, cancelled_request["id"]),
    ):
        status_filtered = _expect_json(
            await client.get(
                "/api/v1/leave-requests",
                headers=TENANT_HEADERS,
                params={"status": status_value},
            ),
            200,
            f"GET /api/v1/leave-requests?status={status_value}",
        )
        _assert_equal(
            [leave_request["id"] for leave_request in status_filtered],
            [expected_id],
            f"leave request {status_value} status filter",
        )
    _expect_error_code(
        await client.get(
            "/api/v1/leave-requests",
            headers=TENANT_HEADERS,
            params={"status": "archived"},
        ),
        422,
        "leave_request_validation_error",
        "GET /api/v1/leave-requests?status=archived",
    )
    _expect_error_code(
        await client.get(
            "/api/v1/leave-requests",
            headers=TENANT_HEADERS,
            params={"employee_id": "not-a-uuid"},
        ),
        422,
        "leave_request_validation_error",
        "GET /api/v1/leave-requests?employee_id=not-a-uuid",
    )

    employee_filtered = _expect_json(
        await client.get(
            "/api/v1/leave-requests",
            headers=TENANT_HEADERS,
            params={"employee_id": employee_id},
        ),
        200,
        "GET /api/v1/leave-requests?employee_id=<employee_id>",
    )
    _assert_equal(
        {leave_request["id"] for leave_request in employee_filtered},
        {approved_request["id"], rejected_request["id"], cancelled_request["id"]},
        "leave request employee_id filter",
    )
    employee_filtered_page = _expect_json(
        await client.get(
            "/api/v1/leave-requests",
            headers=TENANT_HEADERS,
            params={"employee_id": employee_id, "limit": 1, "offset": 1},
        ),
        200,
        "GET /api/v1/leave-requests?employee_id=<employee_id>&limit=1&offset=1",
    )
    _assert_equal(len(employee_filtered_page), 1, "leave request filtered pagination size")
    employee_filter_ids = {
        approved_request["id"],
        rejected_request["id"],
        cancelled_request["id"],
    }
    if employee_filtered_page[0]["id"] not in employee_filter_ids:
        raise AssertionError("leave request filtered pagination returned wrong employee")
    secondary_employee_filtered = _expect_json(
        await client.get(
            "/api/v1/leave-requests",
            headers=TENANT_HEADERS,
            params={"employee_id": secondary_employee_id},
        ),
        200,
        "GET /api/v1/leave-requests?employee_id=<secondary_employee_id>",
    )
    _assert_equal(
        [leave_request["id"] for leave_request in secondary_employee_filtered],
        [pending_request["id"]],
        "leave request secondary employee_id filter",
    )
    combined_filtered = _expect_json(
        await client.get(
            "/api/v1/leave-requests",
            headers=TENANT_HEADERS,
            params={
                "status": LeaveRequestStatus.APPROVED.value,
                "employee_id": employee_id,
                "start_date": approved_request["start_date"],
                "end_date": approved_request["end_date"],
            },
        ),
        200,
        "GET /api/v1/leave-requests combined filters",
    )
    _assert_equal(
        [leave_request["id"] for leave_request in combined_filtered],
        [approved_request["id"]],
        "leave request combined filters",
    )
    conflicting_combined_filtered = _expect_json(
        await client.get(
            "/api/v1/leave-requests",
            headers=TENANT_HEADERS,
            params={
                "status": LeaveRequestStatus.PENDING.value,
                "employee_id": employee_id,
                "start_date": approved_request["start_date"],
                "end_date": cancelled_request["end_date"],
            },
        ),
        200,
        "GET /api/v1/leave-requests conflicting combined filters",
    )
    _assert_equal(
        conflicting_combined_filtered,
        [],
        "leave request conflicting combined filters",
    )
    cross_tenant_filtered = _expect_json(
        await client.get(
            "/api/v1/leave-requests",
            headers=TENANT_HEADERS,
            params={
                "employee_id": other_employee_id,
                "status": LeaveRequestStatus.PENDING.value,
            },
        ),
        200,
        "GET /api/v1/leave-requests?employee_id=<other_employee_id>&status=pending",
    )
    _assert_equal(cross_tenant_filtered, [], "leave request filter tenant scope")

    date_filtered = _expect_json(
        await client.get(
            "/api/v1/leave-requests",
            headers=TENANT_HEADERS,
            params={
                "start_date": rejected_request["start_date"],
                "end_date": rejected_request["end_date"],
            },
        ),
        200,
        "GET /api/v1/leave-requests?start_date=<date>&end_date=<date>",
    )
    _assert_equal(
        [leave_request["id"] for leave_request in date_filtered],
        [rejected_request["id"]],
        "leave request date range filter",
    )
    start_only_filtered = _expect_json(
        await client.get(
            "/api/v1/leave-requests",
            headers=TENANT_HEADERS,
            params={"start_date": cancelled_request["start_date"]},
        ),
        200,
        "GET /api/v1/leave-requests?start_date=<date>",
    )
    _assert_equal(
        [leave_request["id"] for leave_request in start_only_filtered],
        [cancelled_request["id"]],
        "leave request start_date-only filter",
    )
    end_only_filtered = _expect_json(
        await client.get(
            "/api/v1/leave-requests",
            headers=TENANT_HEADERS,
            params={"end_date": pending_request["end_date"]},
        ),
        200,
        "GET /api/v1/leave-requests?end_date=<date>",
    )
    _assert_equal(
        [leave_request["id"] for leave_request in end_only_filtered],
        [pending_request["id"]],
        "leave request end_date-only filter",
    )
    overlap_filtered = _expect_json(
        await client.get(
            "/api/v1/leave-requests",
            headers=TENANT_HEADERS,
            params={
                "start_date": approved_request["end_date"],
                "end_date": rejected_request["start_date"],
            },
        ),
        200,
        "GET /api/v1/leave-requests overlapping date window",
    )
    _assert_equal(
        {leave_request["id"] for leave_request in overlap_filtered},
        {approved_request["id"], rejected_request["id"]},
        "leave request overlapping date range filter",
    )
    _expect_error_code(
        await client.get(
            "/api/v1/leave-requests",
            headers=TENANT_HEADERS,
            params={
                "start_date": rejected_request["end_date"],
                "end_date": rejected_request["start_date"],
            },
        ),
        422,
        "leave_request_invalid_date_range",
        "GET /api/v1/leave-requests invalid date range",
    )
    _expect_error_code(
        await client.get(
            "/api/v1/leave-requests",
            headers=TENANT_HEADERS,
            params={"start_date": "2026-07-22T00:00:00"},
        ),
        422,
        "leave_request_validation_error",
        "GET /api/v1/leave-requests invalid date filter",
    )

    return {
        "pending": pending_request["id"],
        "approved": approved_request["id"],
        "rejected": rejected_request["id"],
        "cancelled": cancelled_request["id"],
        "other_tenant": other_tenant_request["id"],
    }


async def _expect_leave_request_transition_conflicts(
    client: AsyncClient,
    *,
    decision_payload: dict[str, str],
    request_ids_by_status: dict[str, str],
) -> None:
    for source_status, leave_request_id in request_ids_by_status.items():
        for action in ("approve", "reject", "cancel"):
            _expect_error_code(
                await client.post(
                    f"/api/v1/leave-requests/{leave_request_id}/{action}",
                    headers=TENANT_HEADERS,
                    json=decision_payload,
                ),
                409,
                "leave_request_transition_conflict",
                (
                    "POST "
                    f"{source_status} /api/v1/leave-requests/"
                    f"{{leave_request_id}}/{action}"
                ),
            )


async def _smoke_dashboard_endpoint(
    client: AsyncClient,
    *,
    other_employee_id: str,
    other_tenant_leave_request_id: str,
) -> None:
    summary = _expect_json(
        await _request_documented(
            client,
            "get",
            "/api/v1/dashboard/summary",
            headers=TENANT_HEADERS,
        ),
        200,
        "GET /api/v1/dashboard/summary",
    )
    _assert_equal(summary["active_employee_count"], 1, "dashboard active_employee_count")
    _assert_equal(summary["employee_count"], 2, "dashboard employee_count")
    _assert_equal(
        summary["employee_count"] - summary["active_employee_count"],
        1,
        "dashboard on-leave current employee count",
    )
    _assert_equal(summary["pending_leave_count"], 1, "dashboard pending_leave_count")
    _assert_equal(summary["pending_leave_requests"], 1, "dashboard pending_leave_requests")
    _assert_equal(
        summary["pending_leave_requests"],
        summary["pending_leave_count"],
        "dashboard pending leave compatibility count",
    )
    _assert_equal(summary["new_starters_this_month"], 2, "dashboard new_starters_this_month")
    _assert_equal(summary["open_tasks"], 0, "dashboard open_tasks")
    _assert_equal(
        summary["department_distribution"],
        [
            {"department": "Engineering", "count": 1},
            {"department": "People", "count": 1},
        ],
        "dashboard department_distribution",
    )
    _assert_equal(len(summary["recent_activity"]), 5, "dashboard recent_activity count")
    supported_activity_types = {
        "employee.created",
        "leave.approved",
        "leave.cancelled",
        "leave.rejected",
        "leave.requested",
    }
    activity_types = {activity["activity_type"] for activity in summary["recent_activity"]}
    unsupported_activity_types = activity_types - supported_activity_types
    if unsupported_activity_types:
        raise AssertionError(
            f"dashboard recent_activity has unsupported types: {unsupported_activity_types}"
        )
    leaked_entity_ids = {other_employee_id, other_tenant_leave_request_id}
    if any(activity["entity_id"] in leaked_entity_ids for activity in summary["recent_activity"]):
        raise AssertionError("dashboard recent_activity leaked other tenant")

    other_summary = _expect_json(
        await client.get(
            "/api/v1/dashboard/summary",
            headers=OTHER_TENANT_HEADERS,
        ),
        200,
        "GET other tenant /api/v1/dashboard/summary",
    )
    _assert_equal(
        other_summary["active_employee_count"],
        1,
        "other dashboard active_employee_count",
    )
    _assert_equal(other_summary["employee_count"], 1, "other dashboard employee_count")
    _assert_equal(
        other_summary["employee_count"] - other_summary["active_employee_count"],
        0,
        "other dashboard on-leave current employee count",
    )
    _assert_equal(
        other_summary["pending_leave_count"],
        1,
        "other dashboard pending_leave_count",
    )
    _assert_equal(
        other_summary["pending_leave_requests"],
        1,
        "other dashboard pending_leave_requests",
    )
    _assert_equal(
        other_summary["pending_leave_requests"],
        other_summary["pending_leave_count"],
        "other dashboard pending leave compatibility count",
    )
    _assert_equal(
        other_summary["new_starters_this_month"],
        1,
        "other dashboard new_starters_this_month",
    )
    _assert_equal(
        other_summary["department_distribution"],
        [{"department": "People", "count": 1}],
        "other dashboard department_distribution",
    )
    _assert_equal(
        len(other_summary["recent_activity"]),
        2,
        "other dashboard recent_activity count",
    )
    _assert_equal(
        {activity["activity_type"] for activity in other_summary["recent_activity"]},
        {"employee.created", "leave.requested"},
        "other dashboard recent_activity types",
    )
    _assert_equal(
        {activity["entity_id"] for activity in other_summary["recent_activity"]},
        {other_employee_id, other_tenant_leave_request_id},
        "other dashboard recent_activity tenant scope",
    )


async def _create_employee(
    client: AsyncClient,
    payload: dict[str, Any],
    headers: dict[str, str] | None = None,
) -> dict[str, Any]:
    return _expect_json(
        await _request_documented(
            client,
            "post",
            "/api/v1/employees",
            headers=headers or TENANT_HEADERS,
            json=payload,
        ),
        201,
        "POST /api/v1/employees",
    )


async def _create_leave_request(
    client: AsyncClient,
    employee_id: str,
    day_offset: int,
    *,
    headers: dict[str, str] | None = None,
    requested_by_user_id: str | None = None,
    leave_type: str = "annual",
) -> dict[str, Any]:
    start_date = date.today() + timedelta(days=day_offset)
    end_date = start_date + timedelta(days=1)
    return _expect_json(
        await _request_documented(
            client,
            "post",
            "/api/v1/leave-requests",
            headers=headers or TENANT_HEADERS,
            json={
                "employee_id": employee_id,
                "leave_type": leave_type,
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
                "requested_by_user_id": requested_by_user_id or str(REQUESTING_USER_ID),
            },
        ),
        201,
        "POST /api/v1/leave-requests",
    )


def _expect_json(response: Response, status_code: int, label: str) -> Any:
    _expect_status(response, status_code, label)
    return response.json()


def _expect_phase0_list(
    response: Response,
    status_code: int,
    label: str,
) -> list[Any]:
    body = _expect_json(response, status_code, label)
    if not isinstance(body, list):
        raise AssertionError(
            f"{label} must preserve the Phase 0 plain-array body, "
            f"got {type(body).__name__}"
        )
    return body


def _expect_phase1_data(
    response: Response,
    status_code: int,
    label: str,
    expected_fields: set[str],
) -> dict[str, Any]:
    body = _expect_json(response, status_code, label)
    _assert_exact_fields(body, {"data", "meta"}, f"{label} envelope")
    data = body["data"]
    _assert_exact_fields(data, expected_fields, f"{label} data")
    _expect_phase1_response_meta(body["meta"], response, label)
    return data


def _expect_phase1_list(
    response: Response,
    status_code: int,
    label: str,
    *,
    expected_limit: int,
) -> tuple[list[dict[str, Any]], str | None]:
    body = _expect_json(response, status_code, label)
    _assert_exact_fields(body, {"data", "meta"}, f"{label} envelope")
    data = body["data"]
    if not isinstance(data, list) or not all(isinstance(item, dict) for item in data):
        raise AssertionError(f"{label} data must be a list of objects")
    meta = body["meta"]
    _assert_exact_fields(meta, PAGE_META_FIELDS, f"{label} meta")
    _expect_phase1_response_meta(meta, response, label, exact_fields=False)
    _assert_equal(meta["limit"], expected_limit, f"{label} meta limit")
    next_cursor = meta["next_cursor"]
    if next_cursor is not None and (not isinstance(next_cursor, str) or not next_cursor):
        raise AssertionError(f"{label} next_cursor must be null or a non-empty string")
    return data, next_cursor


def _expect_phase1_response_meta(
    meta: object,
    response: Response,
    label: str,
    *,
    exact_fields: bool = True,
) -> None:
    if not isinstance(meta, dict):
        raise AssertionError(f"{label} meta must be an object")
    if exact_fields:
        _assert_equal(set(meta), RESPONSE_META_FIELDS, f"{label} meta fields")
    _assert_equal(
        meta.get("request_id"),
        response.headers["X-Request-Id"],
        f"{label} meta request_id",
    )
    _assert_equal(
        meta.get("trace_id"),
        response.headers["X-Trace-Id"],
        f"{label} meta trace_id",
    )
    _assert_equal(
        meta.get("correlation_id"),
        meta.get("request_id"),
        f"{label} meta correlation alias",
    )


def _expect_error_code(response: Response, status_code: int, code: str, label: str) -> None:
    body = _expect_json(response, status_code, label)
    _assert_equal(body["error"]["code"], code, f"{label} error code")


def _expect_phase1_error_code(
    response: Response,
    status_code: int,
    code: str,
    label: str,
) -> None:
    body = _expect_json(response, status_code, label)
    _assert_exact_fields(body, {"error"}, f"{label} error envelope")
    error = body["error"]
    _assert_exact_fields(
        error,
        {"code", "message", "details", "correlation_id"},
        f"{label} error",
    )
    _assert_equal(error["code"], code, f"{label} error code")
    _assert_equal(
        error["correlation_id"],
        response.headers["X-Request-Id"],
        f"{label} safe error correlation ID",
    )


def _expect_status(response: Response, status_code: int, label: str) -> None:
    _expect_correlation_headers(response, label)
    if response.status_code != status_code:
        raise AssertionError(
            f"{label} expected {status_code}, got {response.status_code}: {response.text}"
        )


def _expect_correlation_headers(response: Response, label: str) -> None:
    values = {
        header_name: response.headers.get_list(header_name)
        for header_name in CORRELATION_RESPONSE_HEADERS
    }
    for header_name, header_values in values.items():
        if len(header_values) != 1:
            raise AssertionError(
                f"{label} expected exactly one safe {header_name} response header, "
                f"got {header_values!r}"
            )
    request_id = values["X-Request-Id"][0]
    trace_id = values["X-Trace-Id"][0]
    correlation_id = values["X-Correlation-Id"][0]
    if REQUEST_ID_PATTERN.fullmatch(request_id) is None:
        raise AssertionError(f"{label} returned an unsafe request ID")
    if TRACE_ID_PATTERN.fullmatch(trace_id) is None or trace_id == "0" * 32:
        raise AssertionError(f"{label} returned an unsafe trace ID")
    _assert_equal(correlation_id, request_id, f"{label} correlation alias")


def _correlation_ids(response: Response) -> tuple[str, str]:
    _expect_correlation_headers(response, "correlation response")
    return response.headers["X-Request-Id"], response.headers["X-Trace-Id"]


def _assert_not_reflected(
    response: Response,
    unsafe_values: set[str],
    label: str,
) -> None:
    response_surface = "\n".join(
        [response.text, *(f"{name}: {value}" for name, value in response.headers.multi_items())]
    )
    reflected = sorted(value for value in unsafe_values if value in response_surface)
    if reflected:
        raise AssertionError(f"{label} reflected unsafe request metadata: {reflected!r}")


def _assert_equal(actual: Any, expected: Any, label: str = "value") -> None:
    if actual != expected:
        raise AssertionError(f"{label} expected {expected!r}, got {actual!r}")


def _assert_contains(value: str, expected: str, label: str) -> None:
    if expected not in value:
        raise AssertionError(f"{label} expected to contain {expected!r}")


def _assert_exact_fields(
    payload: object,
    expected_fields: set[str],
    label: str,
) -> None:
    if not isinstance(payload, dict):
        raise AssertionError(f"{label} expected an object, got {type(payload).__name__}")
    _assert_equal(set(payload), expected_fields, f"{label} fields")


def _assert_feature_flags(
    payload: dict[str, Any],
    overrides: dict[str, bool],
) -> None:
    features = payload.get("features")
    if not isinstance(features, list):
        raise AssertionError("feature response must contain a feature list")
    expected = [
        {
            "key": key,
            "enabled": overrides.get(key, default_enabled),
            "source": (
                "override"
                if key in overrides and overrides[key] is not default_enabled
                else "default"
            ),
        }
        for key, default_enabled in FEATURE_DEFAULTS.items()
    ]
    for feature in features:
        _assert_exact_fields(feature, FEATURE_FLAG_ITEM_FIELDS, "feature flag item")
    _assert_equal(features, expected, "effective tenant feature flags")


def _assert_no_hr_fields(payload: object, label: str) -> None:
    if isinstance(payload, dict):
        forbidden = set(payload) & FORBIDDEN_HR_FIELDS
        if forbidden:
            raise AssertionError(f"{label} leaked HR fields: {sorted(forbidden)}")
        for value in payload.values():
            _assert_no_hr_fields(value, label)
    elif isinstance(payload, list):
        for value in payload:
            _assert_no_hr_fields(value, label)


def _format_operations(operations: list[tuple[str, str]]) -> list[str]:
    return [f"{method.upper()} {path}" for method, path in operations]


def _ensure_disposable_postgresql_database(database_url: str) -> None:
    url = make_url(database_url)
    if url.get_backend_name() != "postgresql" or not (
        url.database and url.database.startswith("ik_p0a_")
    ):
        raise ValueError(
            "--database-url must target an isolated PostgreSQL database whose name starts "
            "with 'ik_p0a_'"
        )


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the backend API smoke scenario")
    parser.add_argument(
        "--database-url",
        help=(
            "Optional URL for an already migrated disposable integration-test database. "
            "The default remains an in-memory SQLite database."
        ),
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    asyncio.run(main(database_url=args.database_url))
