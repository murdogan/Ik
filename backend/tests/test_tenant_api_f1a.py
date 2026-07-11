import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import date
from typing import Any
from uuid import UUID, uuid4

import pytest
from app.api.dependencies import get_platform_principal, get_tenant_principal
from app.db.base import Base
from app.db.session import get_session
from app.main import create_app
from app.models.employee import Employee, EmployeeStatus
from app.models.leave_request import LeaveRequest, LeaveRequestStatus
from app.models.tenant import Tenant, TenantSettings, TenantStatus
from app.models.user import User, UserStatus
from app.platform.principals import PlatformPrincipal, TenantPrincipal
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool

TENANT_ID = UUID("11111111-aaaa-4111-8111-111111111111")
OTHER_TENANT_ID = UUID("22222222-bbbb-4222-8222-222222222222")
EMPLOYEE_ID = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")
USER_ID = UUID("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb")
LEAVE_REQUEST_ID = UUID("cccccccc-cccc-4ccc-8ccc-cccccccccccc")

PLATFORM_FIELDS = {
    "id",
    "slug",
    "name",
    "status",
    "plan_code",
    "data_region",
    "locale",
    "timezone",
    "health",
    "created_at",
    "updated_at",
}
TENANT_FIELDS = {"id", "slug", "name", "status", "plan_code", "locale", "timezone"}
SETTINGS_FIELDS = {
    "locale",
    "timezone",
    "week_start_day",
    "date_format",
    "time_format",
}
SPOOFED_IDENTITY_HEADERS = {
    "X-User-Id": "dddddddd-dddd-4ddd-8ddd-dddddddddddd",
    "X-Tenant-Id": str(OTHER_TENANT_ID),
}


@dataclass(slots=True)
class TenantApiHarness:
    app: FastAPI
    client: AsyncClient
    engine: AsyncEngine
    session_factory: async_sessionmaker[AsyncSession]


@asynccontextmanager
async def _tenant_api(
    *,
    tenant_status: str = TenantStatus.ACTIVE.value,
) -> AsyncIterator[TenantApiHarness]:
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        use_insertmanyvalues=False,
    )
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        session.add_all(
            [
                Tenant(
                    id=TENANT_ID,
                    slug="wealthy-falcon",
                    name="Wealthy Falcon HR",
                    status=tenant_status,
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
                    plan_code="enterprise",
                    data_region="eu-1",
                    locale="tr-TR",
                    timezone="UTC",
                ),
                TenantSettings(
                    tenant_id=TENANT_ID,
                    week_start_day="monday",
                    date_format="DD.MM.YYYY",
                    time_format="24h",
                ),
                TenantSettings(
                    tenant_id=OTHER_TENANT_ID,
                    week_start_day="monday",
                    date_format="MM/DD/YYYY",
                    time_format="24h",
                ),
                Employee(
                    id=EMPLOYEE_ID,
                    tenant_id=TENANT_ID,
                    employee_number="WF-001",
                    first_name="Ada",
                    last_name="Yilmaz",
                    email="ada@wealthyfalcon.test",
                    department="People",
                    position="HR Specialist",
                    status=EmployeeStatus.ACTIVE.value,
                    employment_start_date=date(2026, 7, 1),
                ),
                User(
                    id=USER_ID,
                    tenant_id=TENANT_ID,
                    email="platform-must-not-return-this@wealthyfalcon.test",
                    full_name="Sensitive User Name",
                    status=UserStatus.ACTIVE.value,
                ),
                LeaveRequest(
                    id=LEAVE_REQUEST_ID,
                    tenant_id=TENANT_ID,
                    employee_id=EMPLOYEE_ID,
                    leave_type="annual",
                    start_date=date(2026, 8, 3),
                    end_date=date(2026, 8, 4),
                    status=LeaveRequestStatus.PENDING.value,
                    requested_by_user_id=USER_ID,
                ),
            ]
        )
        await session.commit()

    async def override_session() -> AsyncIterator[AsyncSession]:
        async with session_factory() as session:
            yield session

    app = create_app()
    app.dependency_overrides[get_session] = override_session
    client = AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver")
    try:
        yield TenantApiHarness(
            app=app,
            client=client,
            engine=engine,
            session_factory=session_factory,
        )
    finally:
        await client.aclose()
        await engine.dispose()


def _authorize_platform(app: FastAPI) -> None:
    app.dependency_overrides[get_platform_principal] = lambda: PlatformPrincipal(
        source="phase1-test"
    )


def _authorize_tenant(app: FastAPI, tenant_id: UUID = TENANT_ID) -> None:
    app.dependency_overrides[get_tenant_principal] = lambda: TenantPrincipal(
        tenant_id=tenant_id,
        source="phase1-test",
    )


def _assert_error_code(response: Any, status_code: int, code: str | None = None) -> None:
    assert response.status_code == status_code
    body = response.json()
    assert set(body) == {"error"}
    if code is not None:
        assert body["error"]["code"] == code


async def test_platform_default_denial_happens_before_database_lookup() -> None:
    app = create_app()

    async def forbidden_session() -> AsyncIterator[AsyncSession]:
        raise AssertionError("default-denied platform request reached the database")
        yield

    app.dependency_overrides[get_session] = forbidden_session
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.get(f"/api/v1/platform/tenants/{TENANT_ID}")

    _assert_error_code(response, 403, "platform_access_denied")


async def test_invalid_injected_principal_values_still_fail_closed() -> None:
    async with _tenant_api() as harness:
        harness.app.dependency_overrides[get_platform_principal] = lambda: None
        harness.app.dependency_overrides[get_tenant_principal] = lambda: None

        platform_response = await harness.client.get("/api/v1/platform/tenants")
        tenant_response = await harness.client.get("/api/v1/tenant")

    _assert_error_code(platform_response, 403, "platform_access_denied")
    _assert_error_code(tenant_response, 403, "tenant_access_denied")


@pytest.mark.parametrize(
    ("method", "path", "payload"),
    [
        (
            "POST",
            "/api/v1/platform/tenants",
            {
                "id": str(uuid4()),
                "tenant_id": str(OTHER_TENANT_ID),
                "user_id": str(USER_ID),
                "slug": "spoofed-platform-create",
                "name": "Spoofed Platform Create",
                "status": "active",
            },
        ),
        ("GET", "/api/v1/platform/tenants", None),
        ("GET", f"/api/v1/platform/tenants/{TENANT_ID}", None),
        (
            "PATCH",
            f"/api/v1/platform/tenants/{TENANT_ID}",
            {
                "tenant_id": str(OTHER_TENANT_ID),
                "user_id": str(USER_ID),
                "status": "active",
            },
        ),
    ],
)
async def test_platform_operations_deny_by_default_despite_spoofed_identity(
    method: str,
    path: str,
    payload: dict[str, Any] | None,
) -> None:
    async with _tenant_api() as harness:
        response = await harness.client.request(
            method,
            path,
            headers=SPOOFED_IDENTITY_HEADERS,
            json=payload,
        )

    _assert_error_code(response, 403)


async def test_authorized_platform_can_provision_list_and_read_tenant_metadata_only() -> None:
    async with _tenant_api() as harness:
        _authorize_platform(harness.app)
        create_response = await harness.client.post(
            "/api/v1/platform/tenants",
            json={
                "slug": "acme-turkiye",
                "name": "Acme Turkiye",
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
        )

        assert create_response.status_code == 201
        created = create_response.json()
        assert set(created) == PLATFORM_FIELDS
        assert UUID(created["id"]).version == 4
        assert created["status"] == "provisioning"
        assert created["health"] == "provisioning"
        assert created["plan_code"] == "professional"
        assert created["data_region"] == "eu-1"

        list_response = await harness.client.get("/api/v1/platform/tenants")
        assert list_response.status_code == 200
        listed = list_response.json()
        assert isinstance(listed, list)
        assert len(listed) == 3
        assert all(set(item) == PLATFORM_FIELDS for item in listed)

        detail_response = await harness.client.get(
            f"/api/v1/platform/tenants/{created['id']}"
        )
        assert detail_response.status_code == 200
        assert detail_response.json() == created

        serialized_platform_responses = json.dumps(
            [created, listed, detail_response.json()]
        )
        for forbidden_value in (
            "WF-001",
            "Ada",
            "Yilmaz",
            "ada@wealthyfalcon.test",
            "platform-must-not-return-this@wealthyfalcon.test",
            "Sensitive User Name",
            "annual",
        ):
            assert forbidden_value not in serialized_platform_responses

        async with harness.session_factory() as session:
            settings = await session.get(TenantSettings, UUID(created["id"]))
        assert settings is not None
        assert settings.week_start_day == "sunday"
        assert settings.date_format == "MM/DD/YYYY"
        assert settings.time_format == "12h"


async def test_platform_reads_legacy_premium_plan_but_new_writes_reject_it() -> None:
    async with _tenant_api() as harness:
        async with harness.session_factory() as session:
            tenant = await session.get(Tenant, OTHER_TENANT_ID)
            assert tenant is not None
            tenant.plan_code = "premium"
            await session.commit()
        _authorize_platform(harness.app)

        detail_response = await harness.client.get(
            f"/api/v1/platform/tenants/{OTHER_TENANT_ID}"
        )
        create_response = await harness.client.post(
            "/api/v1/platform/tenants",
            json={
                "slug": "legacy-plan-write",
                "name": "Legacy Plan Write",
                "plan_code": "premium",
            },
        )

    assert detail_response.status_code == 200
    assert detail_response.json()["plan_code"] == "premium"
    assert create_response.status_code == 422


@pytest.mark.parametrize("client_field", ["id", "status", "tenant_id", "user_id"])
async def test_platform_provisioning_rejects_client_controlled_identity_and_status(
    client_field: str,
) -> None:
    async with _tenant_api() as harness:
        _authorize_platform(harness.app)
        payload = {"slug": f"client-field-{client_field}", "name": "Client Field"}
        payload[client_field] = str(uuid4()) if client_field != "status" else "active"

        response = await harness.client.post("/api/v1/platform/tenants", json=payload)

    assert response.status_code == 422


async def test_platform_provisioning_rejects_duplicate_slug_with_conflict() -> None:
    async with _tenant_api() as harness:
        _authorize_platform(harness.app)

        response = await harness.client.post(
            "/api/v1/platform/tenants",
            json={"slug": "wealthy-falcon", "name": "Duplicate"},
        )

    _assert_error_code(response, 409, "tenant_slug_conflict")


@pytest.mark.parametrize(
    ("field", "invalid_value"),
    [
        ("plan_code", "unlimited"),
        ("data_region", "us-1"),
        ("locale", "de-DE"),
        ("timezone", "Not/A-Timezone"),
        ("plan_code", None),
        ("data_region", None),
        ("locale", None),
        ("timezone", None),
    ],
)
async def test_platform_rejects_invalid_typed_tenant_metadata(
    field: str,
    invalid_value: Any,
) -> None:
    async with _tenant_api() as harness:
        _authorize_platform(harness.app)
        response = await harness.client.post(
            "/api/v1/platform/tenants",
            json={
                "slug": f"invalid-{field}",
                "name": "Invalid Metadata",
                field: invalid_value,
            },
        )

    assert response.status_code == 422


async def test_platform_patch_updates_only_allowlisted_metadata() -> None:
    async with _tenant_api() as harness:
        _authorize_platform(harness.app)

        response = await harness.client.patch(
            f"/api/v1/platform/tenants/{TENANT_ID}",
            json={
                "name": "Wealthy Falcon Enterprise",
                "plan_code": "enterprise",
                "locale": "en-US",
                "timezone": "Europe/London",
            },
        )

        assert response.status_code == 200
        body = response.json()
        assert set(body) == PLATFORM_FIELDS
        assert body["name"] == "Wealthy Falcon Enterprise"
        assert body["plan_code"] == "enterprise"
        assert body["data_region"] == "tr-1"
        assert body["locale"] == "en-US"
        assert body["timezone"] == "Europe/London"

        active_region_response = await harness.client.patch(
            f"/api/v1/platform/tenants/{TENANT_ID}",
            json={"data_region": "eu-1"},
        )
        _assert_error_code(active_region_response, 409, "tenant_lifecycle_conflict")

        create_response = await harness.client.post(
            "/api/v1/platform/tenants",
            json={"slug": "region-change", "name": "Region Change"},
        )
        assert create_response.status_code == 201
        region_response = await harness.client.patch(
            f"/api/v1/platform/tenants/{create_response.json()['id']}",
            json={"data_region": "eu-1"},
        )
        assert region_response.status_code == 200
        assert region_response.json()["data_region"] == "eu-1"

        forbidden_response = await harness.client.patch(
            f"/api/v1/platform/tenants/{TENANT_ID}",
            json={"slug": "rewritten-slug", "employee_count": 999},
        )
        assert forbidden_response.status_code == 422


@pytest.mark.parametrize("payload", [{}, {"name": None}, {"status": None}])
async def test_platform_patch_rejects_empty_or_null_changes(
    payload: dict[str, Any],
) -> None:
    async with _tenant_api() as harness:
        _authorize_platform(harness.app)

        response = await harness.client.patch(
            f"/api/v1/platform/tenants/{TENANT_ID}",
            json=payload,
        )

    assert response.status_code == 422


@pytest.mark.parametrize("tenant_status", ["offboarding", "closed"])
async def test_platform_cannot_rewrite_metadata_after_offboarding_starts(
    tenant_status: str,
) -> None:
    async with _tenant_api(tenant_status=tenant_status) as harness:
        _authorize_platform(harness.app)

        response = await harness.client.patch(
            f"/api/v1/platform/tenants/{TENANT_ID}",
            json={"name": "Reopened By Metadata"},
        )

    _assert_error_code(response, 409, "tenant_lifecycle_conflict")


async def test_tenant_lifecycle_transition_graph_is_explicit() -> None:
    allowed_transitions = {
        "provisioning": {"provisioning", "trial", "active", "closed"},
        "trial": {"trial", "active", "suspended", "offboarding"},
        "active": {"active", "suspended", "offboarding"},
        "suspended": {"suspended", "trial", "active", "offboarding"},
        "offboarding": {"offboarding", "closed"},
        "closed": {"closed"},
    }
    all_statuses = set(allowed_transitions)

    async with _tenant_api() as harness:
        _authorize_platform(harness.app)
        for source, allowed_targets in allowed_transitions.items():
            for target in all_statuses:
                async with harness.session_factory() as session:
                    tenant = await session.get(Tenant, TENANT_ID)
                    assert tenant is not None
                    tenant.status = source
                    await session.commit()

                response = await harness.client.patch(
                    f"/api/v1/platform/tenants/{TENANT_ID}",
                    json={"status": target},
                )

                if target in allowed_targets:
                    assert response.status_code == 200, (source, target, response.text)
                    assert response.json()["status"] == target
                else:
                    _assert_error_code(response, 409, "tenant_lifecycle_conflict")


@pytest.mark.parametrize(
    ("tenant_status", "expected_health"),
    [
        ("provisioning", "provisioning"),
        ("trial", "healthy"),
        ("active", "healthy"),
        ("suspended", "restricted"),
        ("offboarding", "offboarding"),
        ("closed", "closed"),
    ],
)
async def test_platform_health_is_derived_from_lifecycle_status(
    tenant_status: str,
    expected_health: str,
) -> None:
    async with _tenant_api(tenant_status=tenant_status) as harness:
        _authorize_platform(harness.app)

        response = await harness.client.get(f"/api/v1/platform/tenants/{TENANT_ID}")

    assert response.status_code == 200
    assert response.json()["health"] == expected_health


async def test_tenant_self_endpoints_deny_spoofed_headers_without_trusted_principal() -> None:
    async with _tenant_api() as harness:
        current_response = await harness.client.get(
            "/api/v1/tenant",
            headers={"X-Tenant-Id": str(TENANT_ID), "X-User-Id": str(USER_ID)},
        )
        settings_response = await harness.client.get(
            "/api/v1/tenant/settings",
            headers={"X-Tenant-Id": str(TENANT_ID), "X-User-Id": str(USER_ID)},
        )

    assert current_response.status_code == 403
    assert settings_response.status_code == 403


async def test_tenant_principal_not_spoofed_header_drives_current_tenant_and_settings() -> None:
    async with _tenant_api() as harness:
        _authorize_tenant(harness.app)

        current_response = await harness.client.get(
            "/api/v1/tenant",
            headers=SPOOFED_IDENTITY_HEADERS,
        )
        settings_response = await harness.client.get(
            "/api/v1/tenant/settings",
            headers=SPOOFED_IDENTITY_HEADERS,
        )

    assert current_response.status_code == 200
    current = current_response.json()
    assert set(current) == TENANT_FIELDS
    assert current["id"] == str(TENANT_ID)
    assert current["slug"] == "wealthy-falcon"
    assert current["plan_code"] == "core"

    assert settings_response.status_code == 200
    settings = settings_response.json()
    assert set(settings) == SETTINGS_FIELDS
    assert settings == {
        "locale": "tr-TR",
        "timezone": "Europe/Istanbul",
        "week_start_day": "monday",
        "date_format": "DD.MM.YYYY",
        "time_format": "24h",
    }


async def test_tenant_settings_patch_is_typed_partial_and_tenant_isolated() -> None:
    async with _tenant_api() as harness:
        _authorize_tenant(harness.app)

        response = await harness.client.patch(
            "/api/v1/tenant/settings",
            headers=SPOOFED_IDENTITY_HEADERS,
            json={
                "locale": "en-US",
                "timezone": "Europe/London",
                "week_start_day": "sunday",
                "date_format": "YYYY-MM-DD",
                "time_format": "12h",
            },
        )

        assert response.status_code == 200
        assert response.json() == {
            "locale": "en-US",
            "timezone": "Europe/London",
            "week_start_day": "sunday",
            "date_format": "YYYY-MM-DD",
            "time_format": "12h",
        }

        async with harness.session_factory() as session:
            tenants = {
                tenant.id: tenant
                for tenant in (
                    await session.scalars(
                        select(Tenant).where(Tenant.id.in_([TENANT_ID, OTHER_TENANT_ID]))
                    )
                ).all()
            }
            primary_settings = await session.get(TenantSettings, TENANT_ID)
            other_settings = await session.get(TenantSettings, OTHER_TENANT_ID)

        assert tenants[TENANT_ID].locale == "en-US"
        assert tenants[TENANT_ID].timezone == "Europe/London"
        assert primary_settings is not None
        assert primary_settings.week_start_day == "sunday"
        assert tenants[OTHER_TENANT_ID].locale == "tr-TR"
        assert tenants[OTHER_TENANT_ID].timezone == "UTC"
        assert other_settings is not None
        assert other_settings.week_start_day == "monday"
        assert other_settings.date_format == "MM/DD/YYYY"
        assert other_settings.time_format == "24h"


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"tenant_id": str(OTHER_TENANT_ID)},
        {"user_id": str(USER_ID)},
        {"arbitrary": "value"},
        {"feature_flags": {"payroll": True}},
        {"locale": None},
        {"timezone": None},
        {"week_start_day": None},
        {"date_format": None},
        {"time_format": None},
        {"locale": "de-DE"},
        {"timezone": "Not/A-Timezone"},
        {"week_start_day": "friday"},
        {"date_format": "DD/MM/YYYY"},
        {"time_format": "military"},
        {"locale": 42},
        {"timezone": ["Europe/Istanbul"]},
        {"week_start_day": True},
        {"date_format": {}},
        {"time_format": 24},
    ],
)
async def test_tenant_settings_reject_unknown_null_and_wrong_typed_values(
    payload: dict[str, Any],
) -> None:
    async with _tenant_api() as harness:
        _authorize_tenant(harness.app)
        response = await harness.client.patch("/api/v1/tenant/settings", json=payload)

    assert response.status_code == 422


@pytest.mark.parametrize("tenant_status", ["suspended", "offboarding"])
async def test_restricted_tenants_can_read_settings_but_cannot_patch(
    tenant_status: str,
) -> None:
    async with _tenant_api(tenant_status=tenant_status) as harness:
        _authorize_tenant(harness.app)

        current_response = await harness.client.get("/api/v1/tenant")
        get_response = await harness.client.get("/api/v1/tenant/settings")
        patch_response = await harness.client.patch(
            "/api/v1/tenant/settings",
            json={"week_start_day": "sunday"},
        )

    assert current_response.status_code == 200
    assert get_response.status_code == 200
    _assert_error_code(patch_response, 423, "tenant_read_only")


@pytest.mark.parametrize(
    ("tenant_status", "expected_status"),
    [("provisioning", 423), ("closed", 410)],
)
async def test_provisioning_and_closed_tenants_cannot_use_self_endpoints(
    tenant_status: str,
    expected_status: int,
) -> None:
    async with _tenant_api(tenant_status=tenant_status) as harness:
        _authorize_tenant(harness.app)

        responses = [
            await harness.client.get("/api/v1/tenant"),
            await harness.client.get("/api/v1/tenant/settings"),
            await harness.client.patch(
                "/api/v1/tenant/settings",
                json={"week_start_day": "sunday"},
            ),
        ]

    assert {response.status_code for response in responses} == {expected_status}
