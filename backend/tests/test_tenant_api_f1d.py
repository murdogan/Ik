from __future__ import annotations

import json
from collections.abc import AsyncIterator, Mapping
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import date
from typing import Any
from uuid import UUID

import pytest
from app.api.dependencies import (
    get_platform_event_recorder,
    get_platform_principal,
    get_tenant_principal,
)
from app.db.base import Base
from app.db.session import get_session
from app.main import create_app
from app.models.employee import Employee, EmployeeStatus
from app.models.leave_request import LeaveRequest, LeaveRequestStatus
from app.models.tenant import Tenant, TenantSettings, TenantStatus
from app.models.user import User, UserStatus
from app.modules.core.application.events import (
    FeatureFlagChangedEvent,
    PlatformEventType,
    TenantCreatedEvent,
    TenantSettingChangedEvent,
    TenantStatusChangedEvent,
)
from app.platform.events import RecordingPlatformEventRecorder
from app.platform.principals import PlatformPrincipal, TenantPrincipal
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient, Response
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool

TENANT_A_ID = UUID("11111111-aaaa-4111-8111-111111111111")
TENANT_B_ID = UUID("22222222-bbbb-4222-8222-222222222222")
EMPLOYEE_A_ID = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")
EMPLOYEE_B_ID = UUID("dddddddd-dddd-4ddd-8ddd-dddddddddddd")
USER_A_ID = UUID("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb")
USER_B_ID = UUID("eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee")
LEAVE_REQUEST_A_ID = UUID("cccccccc-cccc-4ccc-8ccc-cccccccccccc")

FEATURE_CATALOG = (
    "organization",
    "employees",
    "documents",
    "leave",
    "self_service",
    "reporting",
    "notifications",
)
FEATURE_DEFAULTS = {
    "organization": False,
    "employees": True,
    "documents": False,
    "leave": True,
    "self_service": False,
    "reporting": True,
    "notifications": False,
}
FEATURE_ITEM_FIELDS = {"key", "enabled", "source"}
FEATURE_RESPONSE_FIELDS = {"features"}
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
RESPONSE_META_FIELDS = {"request_id", "trace_id", "correlation_id"}
PAGE_META_FIELDS = RESPONSE_META_FIELDS | {"limit", "next_cursor"}
SPOOFED_TENANT_A_HEADERS = {
    "X-Tenant-Id": str(TENANT_B_ID),
    "X-Tenant-Slug": "tenant-b",
    "X-User-Id": str(USER_B_ID),
}
SPOOFED_TENANT_B_HEADERS = {
    "X-Tenant-Id": str(TENANT_A_ID),
    "X-Tenant-Slug": "tenant-a",
    "X-User-Id": str(USER_A_ID),
}
HR_SENTINELS = {
    "WF-HR-SENTINEL-001",
    "WF-HR-SENTINEL-002",
    "Ada-HR-Sentinel",
    "Bora-HR-Sentinel",
    "Yilmaz-HR-Sentinel",
    "ada.hr.sentinel@wealthyfalcon.test",
    "bora.hr.sentinel@wealthyfalcon.test",
    "sensitive.user@wealthyfalcon.test",
    "other.sensitive.user@wealthyfalcon.test",
    "Sensitive HR User Sentinel",
    "Other Sensitive HR User Sentinel",
    "annual-sensitive-sentinel",
}
FORBIDDEN_HR_FIELDS = {
    "employee_count",
    "employee_id",
    "employees",
    "first_name",
    "last_name",
    "department",
    "position",
    "email",
    "leave_count",
    "leave_requests",
    "requested_by_user_id",
    "user_id",
    "users",
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
    tenant_a_status: str = TenantStatus.ACTIVE.value,
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
                    id=TENANT_A_ID,
                    slug="tenant-a",
                    name="Tenant A Platform Metadata",
                    status=tenant_a_status,
                    plan_code="core",
                    data_region="tr-1",
                    locale="tr-TR",
                    timezone="Europe/Istanbul",
                ),
                Tenant(
                    id=TENANT_B_ID,
                    slug="tenant-b",
                    name="Tenant B Platform Metadata",
                    status=TenantStatus.ACTIVE.value,
                    plan_code="enterprise",
                    data_region="eu-1",
                    locale="en-US",
                    timezone="UTC",
                ),
                TenantSettings(tenant_id=TENANT_A_ID),
                TenantSettings(tenant_id=TENANT_B_ID),
                Employee(
                    id=EMPLOYEE_A_ID,
                    tenant_id=TENANT_A_ID,
                    employee_number="WF-HR-SENTINEL-001",
                    first_name="Ada-HR-Sentinel",
                    last_name="Yilmaz-HR-Sentinel",
                    email="ada.hr.sentinel@wealthyfalcon.test",
                    department="Sensitive People Data",
                    position="Sensitive HR Position",
                    status=EmployeeStatus.ACTIVE.value,
                    employment_start_date=date(2026, 7, 1),
                ),
                Employee(
                    id=EMPLOYEE_B_ID,
                    tenant_id=TENANT_B_ID,
                    employee_number="WF-HR-SENTINEL-002",
                    first_name="Bora-HR-Sentinel",
                    last_name="Yilmaz-HR-Sentinel",
                    email="bora.hr.sentinel@wealthyfalcon.test",
                    department="Other Sensitive People Data",
                    position="Other Sensitive HR Position",
                    status=EmployeeStatus.ACTIVE.value,
                    employment_start_date=date(2026, 7, 1),
                ),
                User(
                    id=USER_A_ID,
                    tenant_id=TENANT_A_ID,
                    email="sensitive.user@wealthyfalcon.test",
                    full_name="Sensitive HR User Sentinel",
                    status=UserStatus.ACTIVE.value,
                ),
                User(
                    id=USER_B_ID,
                    tenant_id=TENANT_B_ID,
                    email="other.sensitive.user@wealthyfalcon.test",
                    full_name="Other Sensitive HR User Sentinel",
                    status=UserStatus.ACTIVE.value,
                ),
                LeaveRequest(
                    id=LEAVE_REQUEST_A_ID,
                    tenant_id=TENANT_A_ID,
                    employee_id=EMPLOYEE_A_ID,
                    leave_type="annual-sensitive-sentinel",
                    start_date=date(2026, 8, 3),
                    end_date=date(2026, 8, 4),
                    status=LeaveRequestStatus.PENDING.value,
                    requested_by_user_id=USER_A_ID,
                ),
            ]
        )
        await session.commit()

        feature_table = Base.metadata.tables.get("tenant_feature_flags")
        if feature_table is not None:
            await session.execute(
                feature_table.insert(),
                [
                    {
                        "tenant_id": tenant_id,
                        "key": key,
                        "enabled": FEATURE_DEFAULTS[key],
                    }
                    for tenant_id in (TENANT_A_ID, TENANT_B_ID)
                    for key in FEATURE_CATALOG
                ],
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
        source="f1d-api-test"
    )


def _authorize_tenant(app: FastAPI, tenant_id: UUID) -> None:
    app.dependency_overrides[get_tenant_principal] = lambda: TenantPrincipal(
        tenant_id=tenant_id,
        source="f1d-api-test",
    )


def _expected_features(
    overrides: Mapping[str, bool] | None = None,
) -> list[dict[str, object]]:
    overrides = overrides or {}
    return [
        {
            "key": key,
            "enabled": overrides.get(key, FEATURE_DEFAULTS[key]),
            "source": (
                "override"
                if key in overrides and overrides[key] != FEATURE_DEFAULTS[key]
                else "default"
            ),
        }
        for key in FEATURE_CATALOG
    ]


def _phase1_data(response: Response, expected_fields: set[str]) -> dict[str, Any]:
    body = response.json()
    assert set(body) == {"data", "meta"}
    assert isinstance(body["data"], dict)
    assert set(body["data"]) == expected_fields
    assert set(body["meta"]) == RESPONSE_META_FIELDS
    assert body["meta"]["request_id"] == response.headers["X-Request-Id"]
    assert body["meta"]["trace_id"] == response.headers["X-Trace-Id"]
    assert body["meta"]["correlation_id"] == body["meta"]["request_id"]
    return body["data"]


def _phase1_list(response: Response) -> list[dict[str, Any]]:
    body = response.json()
    assert set(body) == {"data", "meta"}
    assert isinstance(body["data"], list)
    assert set(body["meta"]) == PAGE_META_FIELDS
    assert body["meta"]["request_id"] == response.headers["X-Request-Id"]
    assert body["meta"]["trace_id"] == response.headers["X-Trace-Id"]
    assert body["meta"]["correlation_id"] == body["meta"]["request_id"]
    return body["data"]


def _feature_data(response: Response) -> dict[str, Any]:
    data = _phase1_data(response, FEATURE_RESPONSE_FIELDS)
    assert isinstance(data["features"], list)
    assert all(
        isinstance(feature, dict) and set(feature) == FEATURE_ITEM_FIELDS
        for feature in data["features"]
    )
    return data


def _assert_error(response: Response, status_code: int, code: str) -> None:
    assert response.status_code == status_code
    body = response.json()
    assert set(body) == {"error"}
    assert body["error"]["code"] == code
    assert body["error"]["correlation_id"] == response.headers["X-Request-Id"]


async def test_provisioning_assigns_exact_default_feature_catalog_in_stable_order() -> None:
    async with _tenant_api() as harness:
        _authorize_platform(harness.app)
        create_response = await harness.client.post(
            "/api/v1/platform/tenants",
            json={"slug": "new-feature-tenant", "name": "New Feature Tenant"},
        )
        assert create_response.status_code == 201
        created_id = UUID(create_response.json()["data"]["id"])

        platform_features_response = await harness.client.get(
            f"/api/v1/platform/tenants/{created_id}/features"
        )
        assert platform_features_response.status_code == 200
        platform_features = _feature_data(platform_features_response)

        activate_response = await harness.client.patch(
            f"/api/v1/platform/tenants/{created_id}",
            json={"status": TenantStatus.ACTIVE.value},
        )
        assert activate_response.status_code == 200
        _authorize_tenant(harness.app, created_id)
        tenant_features_response = await harness.client.get("/api/v1/tenant/features")

    assert tenant_features_response.status_code == 200
    assert platform_features == _feature_data(tenant_features_response)
    assert platform_features == {"features": _expected_features()}


async def test_platform_patch_returns_full_effective_catalog_and_derived_sources() -> None:
    async with _tenant_api() as harness:
        _authorize_platform(harness.app)
        patch_response = await harness.client.patch(
            f"/api/v1/platform/tenants/{TENANT_A_ID}/features",
            json={
                "features": [
                    {"key": "organization", "enabled": True},
                    {"key": "employees", "enabled": False},
                    {"key": "leave", "enabled": True},
                ]
            },
        )
        assert patch_response.status_code == 200
        patched = _feature_data(patch_response)
        assert patched == {
            "features": _expected_features(
                {"organization": True, "employees": False, "leave": True}
            )
        }

        get_response = await harness.client.get(
            f"/api/v1/platform/tenants/{TENANT_A_ID}/features"
        )
        assert get_response.status_code == 200
        assert _feature_data(get_response) == patched

        reset_response = await harness.client.patch(
            f"/api/v1/platform/tenants/{TENANT_A_ID}/features",
            json={"features": [{"key": "organization", "enabled": False}]},
        )
        assert reset_response.status_code == 200

    assert _feature_data(reset_response) == {
        "features": _expected_features({"employees": False})
    }


@pytest.mark.parametrize(
    "payload",
    [
        {"features": []},
        {"features": {"organization": True}},
        {"features": [{"key": "organization", "enabled": 1}]},
        {"features": [{"key": "organization", "enabled": "true"}]},
        {"features": [{"key": "organization", "enabled": None}]},
        {"features": [{"key": "payroll", "enabled": True}]},
        {
            "features": [
                {"key": "organization", "enabled": True},
                {"key": "organization", "enabled": False},
            ]
        },
        {
            "features": [
                {"key": "organization", "enabled": True, "source": "override"}
            ]
        },
        {
            "features": [
                {"key": "organization", "enabled": True, "token": "must-be-rejected"}
            ]
        },
        {
            "features": [{"key": "organization", "enabled": True}],
            "tenant_id": str(TENANT_B_ID),
        },
    ],
)
async def test_platform_feature_patch_rejects_unknown_duplicate_extra_and_non_strict_values(
    payload: dict[str, Any],
) -> None:
    async with _tenant_api() as harness:
        _authorize_platform(harness.app)
        response = await harness.client.patch(
            f"/api/v1/platform/tenants/{TENANT_A_ID}/features",
            json=payload,
        )

    _assert_error(response, 422, "platform_tenant_validation_error")


async def test_tenant_feature_scope_ignores_spoofed_headers_and_isolates_tenants() -> None:
    async with _tenant_api() as harness:
        _authorize_platform(harness.app)
        patch_response = await harness.client.patch(
            f"/api/v1/platform/tenants/{TENANT_A_ID}/features",
            headers=SPOOFED_TENANT_A_HEADERS,
            json={"features": [{"key": "documents", "enabled": True}]},
        )
        assert patch_response.status_code == 200

        _authorize_tenant(harness.app, TENANT_A_ID)
        tenant_a_response = await harness.client.get(
            "/api/v1/tenant/features",
            headers=SPOOFED_TENANT_A_HEADERS,
            params={"tenant_id": str(TENANT_B_ID), "user_id": str(USER_B_ID)},
        )
        assert tenant_a_response.status_code == 200

        _authorize_tenant(harness.app, TENANT_B_ID)
        tenant_b_response = await harness.client.get(
            "/api/v1/tenant/features",
            headers=SPOOFED_TENANT_B_HEADERS,
            params={"tenant_id": str(TENANT_A_ID), "user_id": str(USER_A_ID)},
        )
        assert tenant_b_response.status_code == 200

    assert _feature_data(tenant_a_response) == {
        "features": _expected_features({"documents": True})
    }
    assert _feature_data(tenant_b_response) == {"features": _expected_features()}


@pytest.mark.parametrize(
    ("method", "path", "payload"),
    [
        (
            "POST",
            "/api/v1/platform/tenants",
            {"slug": "must-not-create", "name": "Must Not Create"},
        ),
        ("GET", "/api/v1/platform/tenants", None),
        ("GET", f"/api/v1/platform/tenants/{TENANT_A_ID}", None),
        (
            "PATCH",
            f"/api/v1/platform/tenants/{TENANT_A_ID}",
            {"name": "Must Not Change"},
        ),
        ("GET", f"/api/v1/platform/tenants/{TENANT_A_ID}/features", None),
        (
            "PATCH",
            f"/api/v1/platform/tenants/{TENANT_A_ID}/features",
            {"features": [{"key": "documents", "enabled": True}]},
        ),
    ],
)
async def test_tenant_principal_alone_cannot_call_any_platform_route(
    method: str,
    path: str,
    payload: dict[str, Any] | None,
) -> None:
    async with _tenant_api() as harness:
        _authorize_tenant(harness.app, TENANT_A_ID)
        response = await harness.client.request(
            method,
            path,
            headers=SPOOFED_TENANT_A_HEADERS,
            json=payload,
        )

    _assert_error(response, 403, "platform_access_denied")


async def test_platform_principal_alone_does_not_grant_current_tenant_features() -> None:
    async with _tenant_api() as harness:
        _authorize_platform(harness.app)
        response = await harness.client.get(
            "/api/v1/tenant/features",
            headers=SPOOFED_TENANT_A_HEADERS,
        )

    _assert_error(response, 403, "tenant_access_denied")


@pytest.mark.parametrize(
    ("tenant_status", "expected_status", "expected_code"),
    [
        (TenantStatus.PROVISIONING.value, 423, "tenant_not_ready"),
        (TenantStatus.TRIAL.value, 200, None),
        (TenantStatus.ACTIVE.value, 200, None),
        (TenantStatus.SUSPENDED.value, 200, None),
        (TenantStatus.OFFBOARDING.value, 200, None),
        (TenantStatus.CLOSED.value, 410, "tenant_closed"),
    ],
)
async def test_current_tenant_feature_get_follows_lifecycle_read_policy(
    tenant_status: str,
    expected_status: int,
    expected_code: str | None,
) -> None:
    async with _tenant_api(tenant_a_status=tenant_status) as harness:
        _authorize_tenant(harness.app, TENANT_A_ID)
        response = await harness.client.get("/api/v1/tenant/features")

    if expected_code is not None:
        _assert_error(response, expected_status, expected_code)
        return
    assert response.status_code == expected_status
    assert _feature_data(response) == {"features": _expected_features()}


async def test_platform_list_and_detail_expose_configured_limits_without_hr_data() -> None:
    async with _tenant_api() as harness:
        _authorize_platform(harness.app)
        update_response = await harness.client.patch(
            f"/api/v1/platform/tenants/{TENANT_A_ID}",
            json={"limits": {"active_employees": 250}},
        )
        assert update_response.status_code == 200
        updated = _phase1_data(update_response, PLATFORM_TENANT_FIELDS)

        detail_response = await harness.client.get(
            f"/api/v1/platform/tenants/{TENANT_A_ID}"
        )
        assert detail_response.status_code == 200
        detailed = _phase1_data(detail_response, PLATFORM_TENANT_FIELDS)

        list_response = await harness.client.get("/api/v1/platform/tenants")
        assert list_response.status_code == 200
        listed = _phase1_list(list_response)

        features_response = await harness.client.get(
            f"/api/v1/platform/tenants/{TENANT_A_ID}/features"
        )
        assert features_response.status_code == 200
        feature_data = _feature_data(features_response)

    assert updated["limits"] == {"active_employees": 250}
    assert detailed == updated
    assert all(set(tenant) == PLATFORM_TENANT_FIELDS for tenant in listed)
    listed_by_id = {tenant["id"]: tenant for tenant in listed}
    assert listed_by_id[str(TENANT_A_ID)]["limits"] == {"active_employees": 250}
    assert listed_by_id[str(TENANT_B_ID)]["limits"] == {"active_employees": None}
    assert isinstance(listed_by_id[str(TENANT_A_ID)]["limits"]["active_employees"], int)
    assert listed_by_id[str(TENANT_A_ID)]["limits"]["active_employees"] > 0

    platform_payloads = [updated, detailed, listed, feature_data]
    _assert_no_hr_fields(platform_payloads)
    serialized = json.dumps(platform_payloads)
    for sentinel in HR_SENTINELS:
        assert sentinel not in serialized


@pytest.mark.parametrize("invalid_limit", [0, -1, True, "250", 1.5])
async def test_platform_limit_update_rejects_non_positive_or_non_strict_integer(
    invalid_limit: object,
) -> None:
    async with _tenant_api() as harness:
        _authorize_platform(harness.app)
        response = await harness.client.patch(
            f"/api/v1/platform/tenants/{TENANT_A_ID}",
            json={"limits": {"active_employees": invalid_limit}},
        )

    _assert_error(response, 422, "platform_tenant_validation_error")


@pytest.mark.parametrize(
    ("current_status", "payload"),
    [
        (
            TenantStatus.ACTIVE.value,
            {
                "status": TenantStatus.OFFBOARDING.value,
                "limits": {"active_employees": 250},
            },
        ),
        (
            TenantStatus.PROVISIONING.value,
            {"status": TenantStatus.CLOSED.value, "name": "Combined Closure"},
        ),
        (
            TenantStatus.OFFBOARDING.value,
            {"status": TenantStatus.CLOSED.value, "plan_code": "professional"},
        ),
    ],
)
async def test_terminal_lifecycle_changes_reject_combined_metadata_mutations(
    current_status: str,
    payload: dict[str, Any],
) -> None:
    async with _tenant_api(tenant_a_status=current_status) as harness:
        _authorize_platform(harness.app)
        response = await harness.client.patch(
            f"/api/v1/platform/tenants/{TENANT_A_ID}",
            json=payload,
        )

        _assert_error(response, 409, "tenant_lifecycle_conflict")
        async with harness.session_factory() as session:
            tenant = await session.get(Tenant, TENANT_A_ID)
            assert tenant is not None
            assert tenant.status == current_status
            assert tenant.active_employee_limit is None
            assert tenant.plan_code == "core"


async def test_region_change_must_be_separate_from_activation() -> None:
    async with _tenant_api(tenant_a_status=TenantStatus.PROVISIONING.value) as harness:
        _authorize_platform(harness.app)
        response = await harness.client.patch(
            f"/api/v1/platform/tenants/{TENANT_A_ID}",
            json={"status": TenantStatus.ACTIVE.value, "data_region": "eu-1"},
        )

        _assert_error(response, 409, "tenant_lifecycle_conflict")
        async with harness.session_factory() as session:
            tenant = await session.get(Tenant, TENANT_A_ID)
            assert tenant is not None
            assert tenant.status == TenantStatus.PROVISIONING.value
            assert tenant.data_region == "tr-1"


async def test_successful_actual_changes_record_all_four_redacted_event_contracts() -> None:
    async with _tenant_api() as harness:
        recorder = RecordingPlatformEventRecorder()
        harness.app.dependency_overrides[get_platform_event_recorder] = lambda: recorder
        _authorize_platform(harness.app)

        created_response = await harness.client.post(
            "/api/v1/platform/tenants",
            headers={
                "X-Request-Id": "req_f1d_created_001",
                "X-Trace-Id": "11111111111111111111111111111111",
            },
            json={"slug": "event-tenant", "name": "Never In Event Payload"},
        )
        assert created_response.status_code == 201
        tenant_id = UUID(created_response.json()["data"]["id"])

        status_response = await harness.client.patch(
            f"/api/v1/platform/tenants/{tenant_id}",
            headers={
                "X-Request-Id": "req_f1d_status_001",
                "X-Trace-Id": "22222222222222222222222222222222",
            },
            json={"status": "active"},
        )
        assert status_response.status_code == 200

        platform_setting_response = await harness.client.patch(
            f"/api/v1/platform/tenants/{tenant_id}",
            headers={
                "X-Request-Id": "req_f1d_limit_001",
                "X-Trace-Id": "33333333333333333333333333333333",
            },
            json={"limits": {"active_employees": 250}},
        )
        assert platform_setting_response.status_code == 200

        flag_response = await harness.client.patch(
            f"/api/v1/platform/tenants/{tenant_id}/features",
            headers={
                "X-Request-Id": "req_f1d_flag_001",
                "X-Trace-Id": "44444444444444444444444444444444",
            },
            json={"features": [{"key": "organization", "enabled": True}]},
        )
        assert flag_response.status_code == 200

        _authorize_tenant(harness.app, tenant_id)
        tenant_setting_response = await harness.client.patch(
            "/api/v1/tenant/settings",
            headers={
                "X-Request-Id": "req_f1d_setting_001",
                "X-Trace-Id": "55555555555555555555555555555555",
            },
            json={"locale": "en-US"},
        )
        assert tenant_setting_response.status_code == 200

        events = recorder.events
        assert [event.event_type for event in events] == [
            PlatformEventType.TENANT_CREATED,
            PlatformEventType.TENANT_STATUS_CHANGED,
            PlatformEventType.TENANT_SETTING_CHANGED,
            PlatformEventType.FEATURE_FLAG_CHANGED,
            PlatformEventType.TENANT_SETTING_CHANGED,
        ]
        assert isinstance(events[0], TenantCreatedEvent)
        assert isinstance(events[1], TenantStatusChangedEvent)
        assert isinstance(events[2], TenantSettingChangedEvent)
        assert isinstance(events[3], FeatureFlagChangedEvent)
        assert isinstance(events[4], TenantSettingChangedEvent)
        assert events[0].request_id == "req_f1d_created_001"
        assert events[1].request_id == "req_f1d_status_001"
        assert events[2].changed_fields == ("active_employee_limit",)
        assert events[3].feature_key == "organization"
        assert events[3].before_enabled is False
        assert events[3].after_enabled is True
        assert events[4].changed_fields == ("locale",)

        event_count = len(events)
        _authorize_platform(harness.app)
        assert (
            await harness.client.patch(
                f"/api/v1/platform/tenants/{tenant_id}",
                json={"status": "active"},
            )
        ).status_code == 200
        assert (
            await harness.client.patch(
                f"/api/v1/platform/tenants/{tenant_id}/features",
                json={"features": [{"key": "organization", "enabled": True}]},
            )
        ).status_code == 200
        assert len(recorder.events) == event_count

    serialized = json.dumps(
        [event.model_dump(mode="json") for event in events],
        sort_keys=True,
    )
    assert "Never In Event Payload" not in serialized
    assert "event-tenant" not in serialized


async def test_failed_platform_command_records_no_event() -> None:
    async with _tenant_api() as harness:
        recorder = RecordingPlatformEventRecorder()
        harness.app.dependency_overrides[get_platform_event_recorder] = lambda: recorder
        _authorize_platform(harness.app)

        response = await harness.client.patch(
            f"/api/v1/platform/tenants/{TENANT_A_ID}",
            json={"status": TenantStatus.PROVISIONING.value},
        )

        _assert_error(response, 409, "tenant_lifecycle_conflict")
        assert recorder.events == ()


async def test_event_recorder_failure_rolls_back_platform_metadata_change() -> None:
    class FailingRecorder:
        async def record(self, _event: object, /) -> None:
            raise RuntimeError("simulated Phase-2 recorder failure")

    async with _tenant_api() as harness:
        harness.app.dependency_overrides[get_platform_event_recorder] = FailingRecorder
        _authorize_platform(harness.app)

        with pytest.raises(RuntimeError, match="simulated Phase-2 recorder failure"):
            await harness.client.patch(
                f"/api/v1/platform/tenants/{TENANT_A_ID}",
                json={"limits": {"active_employees": 321}},
            )

        async with harness.session_factory() as session:
            tenant = await session.get(Tenant, TENANT_A_ID)
            assert tenant is not None
            assert tenant.active_employee_limit is None


def _assert_no_hr_fields(payload: object) -> None:
    if isinstance(payload, dict):
        assert FORBIDDEN_HR_FIELDS.isdisjoint(payload)
        for value in payload.values():
            _assert_no_hr_fields(value)
    elif isinstance(payload, list):
        for value in payload:
            _assert_no_hr_fields(value)
