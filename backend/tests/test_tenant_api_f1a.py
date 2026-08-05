import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

import pytest
from app.api.auth_dependencies import (
    PlatformAuthenticatedSession,
    require_platform_authenticated_session,
)
from app.api.dependencies import (
    get_authenticated_tenant_request_context,
    get_platform_event_recorder,
    get_platform_principal,
    get_tenant_principal,
)
from app.core.config import Settings
from app.db.base import Base
from app.db.session import get_session
from app.main import create_app
from app.models.audit import AuditEvent
from app.models.auth import UserActivationToken
from app.models.authorization import UserRole
from app.models.employee import Employee, EmployeeStatus
from app.models.identity import Identity, MembershipRole, TenantMembership
from app.models.leave import LeavePolicy, LeaveType, OutboxEvent
from app.models.leave_request import LeaveRequest, LeaveRequestStatus
from app.models.organization import LegalEntity
from app.models.tenant import Tenant, TenantSettings, TenantStatus
from app.models.user import User, UserStatus
from app.platform.authorization import ROLE_PERMISSION_CODES, ROLES_BY_CODE
from app.platform.identity import (
    PlatformAccessPrincipal,
    hash_activation_token,
    is_manual_activation_delivery_event,
)
from app.platform.principals import PlatformPrincipal
from app.platform.request_context import AuthenticationStrength, RequestContext
from app.platform.tenancy import TenantContext
from app.services.platform_auth_session_service import PlatformAuthenticatedUser
from fastapi import FastAPI, Request
from httpx import ASGITransport, AsyncClient
from pydantic import SecretStr
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
LEAVE_TYPE_ID = UUID("dddddddd-dddd-4ddd-8ddd-dddddddddddd")
LEAVE_POLICY_ID = UUID("eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee")

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
    "limits",
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
META_FIELDS = {"request_id", "trace_id", "correlation_id"}
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
    settings: Settings | None = None,
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
                LeaveType(
                    id=LEAVE_TYPE_ID,
                    tenant_id=TENANT_ID,
                    code="annual",
                    name="Annual leave",
                ),
                LeavePolicy(
                    id=LEAVE_POLICY_ID,
                    tenant_id=TENANT_ID,
                    leave_type_id=LEAVE_TYPE_ID,
                    version=1,
                    effective_from=date(2026, 1, 1),
                    paid=True,
                    document_required=False,
                    negative_balance_allowed=False,
                    accrual_enabled=False,
                    accrual_days_per_month=Decimal("0"),
                    carryover_enabled=False,
                    carryover_limit_days=None,
                    created_by_user_id=USER_ID,
                    created_at=datetime(2026, 1, 1, tzinfo=UTC),
                ),
                LeaveRequest(
                    id=LEAVE_REQUEST_ID,
                    tenant_id=TENANT_ID,
                    employee_id=EMPLOYEE_ID,
                    leave_type="annual",
                    leave_type_id=LEAVE_TYPE_ID,
                    policy_id=LEAVE_POLICY_ID,
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

    app = create_app(settings=settings)
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
    principal = PlatformAccessPrincipal(
        identity_id=USER_ID,
        session_family_id=OTHER_TENANT_ID,
        permission_version=1,
        authentication_strength=AuthenticationStrength.SINGLE_FACTOR,
    )
    authenticated = PlatformAuthenticatedSession(
        principal=principal,
        user=PlatformAuthenticatedUser(
            id=USER_ID,
            email="platform.test@wealthyfalcon.test",
            full_name="Platform Test",
            workspace_scope="platform",
            roles=(),
            permissions=tuple(sorted(ROLE_PERMISSION_CODES["super_admin"])),
            permission_version=principal.permission_version,
            authentication_strength=principal.authentication_strength,
        ),
    )
    app.dependency_overrides[require_platform_authenticated_session] = lambda: authenticated
    app.dependency_overrides[get_platform_principal] = lambda: PlatformPrincipal(
        source="phase1-test"
    )


def _authorize_tenant(app: FastAPI, tenant_id: UUID = TENANT_ID) -> None:
    def authenticated_context(request: Request) -> RequestContext:
        context = request.state.request_context
        assert isinstance(context, RequestContext)
        return context.derive(tenant=TenantContext(tenant_id=tenant_id, slug=str(tenant_id)))

    app.dependency_overrides[get_authenticated_tenant_request_context] = authenticated_context


def _assert_error_code(response: Any, status_code: int, code: str | None = None) -> None:
    assert response.status_code == status_code
    body = response.json()
    assert set(body) == {"error"}
    assert body["error"]["correlation_id"] == response.headers["X-Request-Id"]
    assert response.headers["X-Correlation-Id"] == response.headers["X-Request-Id"]
    assert len(response.headers["X-Trace-Id"]) == 32
    if code is not None:
        assert body["error"]["code"] == code


def _phase1_data(response: Any, expected_fields: set[str]) -> dict[str, Any]:
    body = response.json()
    assert set(body) == {"data", "meta"}
    assert set(body["data"]) == expected_fields
    assert set(body["meta"]) == META_FIELDS
    assert body["meta"]["request_id"] == response.headers["X-Request-Id"]
    assert body["meta"]["correlation_id"] == body["meta"]["request_id"]
    assert body["meta"]["trace_id"] == response.headers["X-Trace-Id"]
    return body["data"]


def _phase1_list(response: Any, *, expected_limit: int) -> tuple[list[dict[str, Any]], Any]:
    body = response.json()
    assert set(body) == {"data", "meta"}
    assert isinstance(body["data"], list)
    assert set(body["meta"]) == META_FIELDS | {"limit", "next_cursor"}
    assert body["meta"]["request_id"] == response.headers["X-Request-Id"]
    assert body["meta"]["correlation_id"] == body["meta"]["request_id"]
    assert body["meta"]["trace_id"] == response.headers["X-Trace-Id"]
    assert body["meta"]["limit"] == expected_limit
    return body["data"], body["meta"]["next_cursor"]


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
    _assert_error_code(tenant_response, 401, "authentication_required")


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
                "initial_admin": {
                    "full_name": "Ada Yönetici",
                    "email": "ada.yonetici@acme.test",
                },
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
        created = _phase1_data(create_response, PLATFORM_FIELDS | {"initial_admin"})
        assert created["initial_admin"] == {"status": "invitation_prepared"}
        assert UUID(created["id"]).version == 4
        assert created["status"] == "provisioning"
        assert created["health"] == "provisioning"
        assert created["plan_code"] == "professional"
        assert created["data_region"] == "eu-1"

        list_response = await harness.client.get("/api/v1/platform/tenants")
        assert list_response.status_code == 200
        listed, next_cursor = _phase1_list(list_response, expected_limit=50)
        assert len(listed) == 3
        assert next_cursor is None
        assert all(set(item) == PLATFORM_FIELDS for item in listed)

        detail_response = await harness.client.get(f"/api/v1/platform/tenants/{created['id']}")
        assert detail_response.status_code == 200
        detailed = _phase1_data(detail_response, PLATFORM_FIELDS)
        assert detailed == {field: created[field] for field in PLATFORM_FIELDS}

        serialized_platform_responses = json.dumps([created, listed, detailed])
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
            default_entity = await session.get(LegalEntity, UUID(created["id"]))
        assert settings is not None
        assert settings.week_start_day == "sunday"
        assert settings.date_format == "MM/DD/YYYY"
        assert settings.time_format == "12h"
        assert default_entity is not None
        assert default_entity.tenant_id == UUID(created["id"])
        assert default_entity.code == "DEFAULT"
        assert default_entity.name == "Acme Turkiye"
        assert default_entity.timezone == "Europe/London"
        assert default_entity.is_default is True


async def test_platform_create_prepares_only_the_initial_tenant_admin_invitation() -> None:
    async with _tenant_api() as harness:
        _authorize_platform(harness.app)

        response = await harness.client.post(
            "/api/v1/platform/tenants",
            json={
                "slug": "first-admin-ready",
                "name": "First Admin Ready",
                "initial_admin": {
                    "full_name": "  İlk Yönetici  ",
                    "email": "  FIRST.ADMIN@EXAMPLE.TEST  ",
                },
            },
        )

        assert response.status_code == 201
        data = response.json()["data"]
        assert set(data) == PLATFORM_FIELDS | {"initial_admin"}
        assert data["initial_admin"] == {"status": "invitation_prepared"}
        assert "token" not in json.dumps(response.json()).lower()
        tenant_id = UUID(data["id"])

        async with harness.session_factory() as session:
            user = await session.scalar(select(User).where(User.tenant_id == tenant_id))
            identity = await session.scalar(
                select(Identity).where(
                    Identity.email_normalized == "first.admin@example.test",
                )
            )
            membership = await session.scalar(
                select(TenantMembership).where(TenantMembership.tenant_id == tenant_id)
            )
            user_roles = tuple(
                await session.scalars(select(UserRole).where(UserRole.tenant_id == tenant_id))
            )
            membership_roles = tuple(
                await session.scalars(
                    select(MembershipRole).where(MembershipRole.tenant_id == tenant_id)
                )
            )
            activation_tokens = tuple(
                await session.scalars(
                    select(UserActivationToken).where(UserActivationToken.tenant_id == tenant_id)
                )
            )
            outbox_events = tuple(
                await session.scalars(select(OutboxEvent).where(OutboxEvent.tenant_id == tenant_id))
            )

        assert user is not None
        assert user.email == "first.admin@example.test"
        assert user.full_name == "İlk Yönetici"
        assert user.status == UserStatus.INVITED.value
        assert user.password_hash is None
        assert identity is not None
        assert identity.status == "pending"
        assert identity.password_hash is None
        assert membership is not None
        assert membership.identity_id == identity.id
        assert membership.legacy_user_id == user.id
        assert membership.status == UserStatus.INVITED.value
        tenant_admin_role_id = ROLES_BY_CODE["tenant_admin"].id
        assert [(assignment.role_id, assignment.active) for assignment in user_roles] == [
            (tenant_admin_role_id, True)
        ]
        assert [(assignment.role_id, assignment.active) for assignment in membership_roles] == [
            (tenant_admin_role_id, True)
        ]
        assert len(activation_tokens) == 1
        assert len(activation_tokens[0].token_hash) == 64
        assert len(outbox_events) == 1
        assert outbox_events[0].event_type == "identity.initial_admin_invited"
        assert outbox_events[0].aggregate_id == user.id
        assert outbox_events[0].payload == {
            "recipient_user_id": str(user.id),
            "activation_id": str(activation_tokens[0].id),
        }
        assert "token" not in json.dumps(outbox_events[0].payload).lower()


async def test_platform_corrects_only_unactivated_initial_admin_membership_and_invitation() -> None:
    old_identity_id = uuid4()
    target_identity_id = uuid4()
    other_membership_id = uuid4()
    old_password_hash = "$argon2id$old-global-credential-must-not-change"
    target_password_hash = "$argon2id$target-global-credential-must-not-change"
    old_email = "incorrect.initial.admin@example.test"
    corrected_email = "corrected.initial.admin@example.test"

    async with _tenant_api() as harness:
        async with harness.session_factory.begin() as session:
            session.add_all(
                [
                    Identity(
                        id=old_identity_id,
                        email=old_email,
                        status="active",
                        password_hash=old_password_hash,
                        platform_permission_version=7,
                    ),
                    Identity(
                        id=target_identity_id,
                        email=corrected_email,
                        status="active",
                        password_hash=target_password_hash,
                        platform_permission_version=11,
                    ),
                    User(
                        id=other_membership_id,
                        tenant_id=OTHER_TENANT_ID,
                        email=old_email,
                        full_name="Old Identity Other Tenant",
                        status=UserStatus.ACTIVE.value,
                        password_hash=old_password_hash,
                    ),
                    TenantMembership(
                        id=other_membership_id,
                        tenant_id=OTHER_TENANT_ID,
                        identity_id=old_identity_id,
                        legacy_user_id=other_membership_id,
                        full_name="Old Identity Other Tenant",
                        status=UserStatus.ACTIVE.value,
                        permission_version=3,
                    ),
                ]
            )

        _authorize_platform(harness.app)
        created = await harness.client.post(
            "/api/v1/platform/tenants",
            json={
                "slug": "correct-initial-admin",
                "name": "Correct Initial Admin",
                "initial_admin": {
                    "full_name": "Incorrect Initial Admin",
                    "email": old_email,
                },
            },
        )
        assert created.status_code == 201
        tenant_id = UUID(created.json()["data"]["id"])

        response = await harness.client.patch(
            f"/api/v1/platform/tenants/{tenant_id}/initial-admin-invitation",
            json={
                "full_name": "  Corrected Initial Admin  ",
                "email": f"  {corrected_email.upper()}  ",
            },
            headers={
                "X-Request-Id": "req_initial_admin_correction_001",
                "X-Trace-Id": "20000000000000000000000000000001",
            },
        )

        assert response.status_code == 202
        assert _phase1_data(response, {"status"}) == {"status": "invitation_prepared"}
        serialized_response = json.dumps(response.json()).lower()
        assert corrected_email not in serialized_response
        assert old_email not in serialized_response
        assert "token" not in serialized_response
        assert "activate" not in serialized_response
        assert "identity" not in serialized_response

        async with harness.session_factory() as session:
            user = await session.scalar(select(User).where(User.tenant_id == tenant_id))
            membership = await session.scalar(
                select(TenantMembership).where(TenantMembership.tenant_id == tenant_id)
            )
            old_identity = await session.get(Identity, old_identity_id)
            target_identity = await session.get(Identity, target_identity_id)
            old_other_membership = await session.get(TenantMembership, other_membership_id)
            activations = tuple(
                await session.scalars(
                    select(UserActivationToken)
                    .where(UserActivationToken.tenant_id == tenant_id)
                    .order_by(UserActivationToken.created_at, UserActivationToken.id)
                )
            )
            outbox_events = tuple(
                await session.scalars(
                    select(OutboxEvent)
                    .where(OutboxEvent.tenant_id == tenant_id)
                    .order_by(OutboxEvent.created_at, OutboxEvent.id)
                )
            )
            correction_audit = await session.scalar(
                select(AuditEvent).where(
                    AuditEvent.event_type == "platform.tenant.initial_admin_invitation_corrected",
                    AuditEvent.resource_id == tenant_id,
                )
            )

        assert user is not None
        assert user.email == corrected_email
        assert user.full_name == "Corrected Initial Admin"
        assert user.status == UserStatus.INVITED.value
        assert user.password_hash is None
        assert membership is not None
        assert membership.id == user.id
        assert membership.legacy_user_id == user.id
        assert membership.identity_id == target_identity_id
        assert membership.full_name == "Corrected Initial Admin"
        assert membership.status == UserStatus.INVITED.value
        assert old_identity is not None
        assert (
            old_identity.email,
            old_identity.status,
            old_identity.password_hash,
            old_identity.platform_permission_version,
        ) == (old_email, "active", old_password_hash, 7)
        assert target_identity is not None
        assert (
            target_identity.email,
            target_identity.status,
            target_identity.password_hash,
            target_identity.platform_permission_version,
        ) == (corrected_email, "active", target_password_hash, 11)
        assert old_other_membership is not None
        assert old_other_membership.identity_id == old_identity_id
        assert old_other_membership.tenant_id == OTHER_TENANT_ID
        assert len(activations) == 2
        assert (
            sum(
                activation.consumed_at is None and activation.revoked_at is None
                for activation in activations
            )
            == 1
        )
        assert sum(activation.revoked_at is not None for activation in activations) == 1
        assert len(outbox_events) == 2
        correction_event = next(
            event for event in outbox_events if ":correction:" in event.source_key
        )
        assert correction_event.aggregate_id == user.id
        assert correction_event.source_key == (
            f"identity.initial_admin_invited:{user.id}:correction:"
            f"{correction_event.payload['activation_id']}"
        )
        assert set(correction_event.payload) == {"recipient_user_id", "activation_id"}
        assert corrected_email not in json.dumps(correction_event.payload).lower()
        assert old_email not in json.dumps(correction_event.payload).lower()
        assert correction_audit is not None
        assert correction_audit.action == "correct_initial_admin_invitation"
        assert correction_audit.request_id == "req_initial_admin_correction_001"
        assert correction_audit.metadata_ == {}
        assert correction_audit.changed_fields == []
        assert correction_audit.before_data == {}
        assert correction_audit.after_data == {}


async def test_initial_admin_correction_rejects_duplicate_target_without_enumeration() -> None:
    target_identity_id = uuid4()
    conflicting_user_id = uuid4()
    target_email = "duplicate.target.initial.admin@example.test"
    async with _tenant_api() as harness:
        _authorize_platform(harness.app)
        created = await harness.client.post(
            "/api/v1/platform/tenants",
            json={
                "slug": "duplicate-correction-target",
                "name": "Duplicate Correction Target",
                "initial_admin": {
                    "full_name": "Original Initial Admin",
                    "email": "original.initial.admin@example.test",
                },
            },
        )
        assert created.status_code == 201
        tenant_id = UUID(created.json()["data"]["id"])

        async with harness.session_factory.begin() as session:
            session.add_all(
                [
                    Identity(
                        id=target_identity_id,
                        email=target_email,
                        status="active",
                        password_hash="$argon2id$duplicate-target-credential",
                    ),
                    User(
                        id=conflicting_user_id,
                        tenant_id=tenant_id,
                        email=target_email,
                        full_name="Existing Tenant Member",
                        status=UserStatus.ACTIVE.value,
                        password_hash="$argon2id$duplicate-target-credential",
                    ),
                    TenantMembership(
                        id=conflicting_user_id,
                        tenant_id=tenant_id,
                        identity_id=target_identity_id,
                        legacy_user_id=conflicting_user_id,
                        full_name="Existing Tenant Member",
                        status=UserStatus.ACTIVE.value,
                    ),
                ]
            )

        response = await harness.client.patch(
            f"/api/v1/platform/tenants/{tenant_id}/initial-admin-invitation",
            json={
                "full_name": "Must Not Apply",
                "email": target_email,
            },
        )

        assert response.status_code == 409
        assert response.json()["error"]["code"] == "tenant_initial_admin_unavailable"
        assert response.json()["error"]["message"] == (
            "The initial administrator cannot be prepared for access"
        )
        assert target_email not in json.dumps(response.json()).lower()

        async with harness.session_factory() as session:
            original_user = await session.scalar(
                select(User).where(
                    User.tenant_id == tenant_id,
                    User.id != conflicting_user_id,
                )
            )
            activations = tuple(
                await session.scalars(
                    select(UserActivationToken).where(UserActivationToken.tenant_id == tenant_id)
                )
            )
            outbox_events = tuple(
                await session.scalars(select(OutboxEvent).where(OutboxEvent.tenant_id == tenant_id))
            )
            correction_audit = await session.scalar(
                select(AuditEvent).where(
                    AuditEvent.event_type == "platform.tenant.initial_admin_invitation_corrected",
                    AuditEvent.resource_id == tenant_id,
                )
            )

        assert original_user is not None
        assert original_user.email == "original.initial.admin@example.test"
        assert original_user.full_name == "Original Initial Admin"
        assert len(activations) == 1
        assert activations[0].revoked_at is None
        assert len(outbox_events) == 1
        assert correction_audit is None


async def test_platform_can_safely_reissue_only_the_original_initial_admin_invitation() -> None:
    identity_id = uuid4()
    original_identity_hash = "$argon2id$existing-identity-credential-must-not-change"
    async with _tenant_api() as harness:
        async with harness.session_factory.begin() as session:
            session.add(
                Identity(
                    id=identity_id,
                    email="stranded.initial.admin@example.test",
                    status="active",
                    password_hash=original_identity_hash,
                    platform_permission_version=9,
                )
            )
        _authorize_platform(harness.app)
        created = await harness.client.post(
            "/api/v1/platform/tenants",
            json={
                "slug": "stranded-initial-admin",
                "name": "Stranded Initial Admin",
                "initial_admin": {
                    "full_name": "Stranded Initial Admin",
                    "email": "stranded.initial.admin@example.test",
                },
            },
        )
        assert created.status_code == 201
        tenant_id = UUID(created.json()["data"]["id"])

        first = await harness.client.post(
            f"/api/v1/platform/tenants/{tenant_id}/initial-admin-invitation/resend",
            headers={
                "X-Request-Id": "req_initial_admin_reissue_001",
                "X-Trace-Id": "10000000000000000000000000000001",
            },
        )
        second = await harness.client.post(
            f"/api/v1/platform/tenants/{tenant_id}/initial-admin-invitation/resend",
            headers={
                "X-Request-Id": "req_initial_admin_reissue_002",
                "X-Trace-Id": "10000000000000000000000000000002",
            },
        )

        for response in (first, second):
            assert response.status_code == 202
            assert _phase1_data(response, {"status"}) == {
                "status": "invitation_prepared",
            }
            serialized_response = json.dumps(response.json()).lower()
            assert "token" not in serialized_response
            assert "activate" not in serialized_response
            assert "email" not in serialized_response

        async with harness.session_factory() as session:
            user = await session.scalar(select(User).where(User.tenant_id == tenant_id))
            membership = await session.scalar(
                select(TenantMembership).where(TenantMembership.tenant_id == tenant_id)
            )
            identity = await session.get(Identity, identity_id)
            activations = tuple(
                await session.scalars(
                    select(UserActivationToken)
                    .where(UserActivationToken.tenant_id == tenant_id)
                    .order_by(UserActivationToken.created_at, UserActivationToken.id)
                )
            )
            outbox_events = tuple(
                await session.scalars(
                    select(OutboxEvent)
                    .where(OutboxEvent.tenant_id == tenant_id)
                    .order_by(OutboxEvent.created_at, OutboxEvent.id)
                )
            )
            reissue_audits = tuple(
                await session.scalars(
                    select(AuditEvent)
                    .where(
                        AuditEvent.event_type
                        == "platform.tenant.initial_admin_invitation_reissued",
                        AuditEvent.resource_id == tenant_id,
                    )
                    .order_by(AuditEvent.occurred_at, AuditEvent.id)
                )
            )

        assert user is not None
        assert user.status == UserStatus.INVITED.value
        assert user.password_hash is None
        assert membership is not None
        assert membership.status == UserStatus.INVITED.value
        assert identity is not None
        assert (
            identity.status,
            identity.password_hash,
            identity.platform_permission_version,
        ) == ("active", original_identity_hash, 9)
        assert len(activations) == 3
        assert (
            sum(
                activation.consumed_at is None and activation.revoked_at is None
                for activation in activations
            )
            == 1
        )
        assert all(len(activation.token_hash) == 64 for activation in activations)
        assert len(outbox_events) == 3
        assert len({event.source_key for event in outbox_events}) == 3
        original_event = next(
            event for event in outbox_events if ":reissue:" not in event.source_key
        )
        assert original_event.source_key == (
            f"identity.initial_admin_invited:{original_event.aggregate_id}"
        )
        assert all(
            set(event.payload) == {"recipient_user_id", "activation_id"} for event in outbox_events
        )
        assert (
            "token"
            not in json.dumps(
                [event.payload for event in outbox_events],
                sort_keys=True,
            ).lower()
        )
        assert len(reissue_audits) == 2
        assert {audit.request_id for audit in reissue_audits} == {
            "req_initial_admin_reissue_001",
            "req_initial_admin_reissue_002",
        }
        assert all(
            audit.metadata_ == {}
            and audit.changed_fields == []
            and audit.before_data == {}
            and audit.after_data == {}
            for audit in reissue_audits
        )
        assert (
            "token"
            not in json.dumps(
                [
                    {
                        "metadata": audit.metadata_,
                        "before": audit.before_data,
                        "after": audit.after_data,
                    }
                    for audit in reissue_audits
                ],
                sort_keys=True,
            ).lower()
        )


async def test_platform_can_generate_a_retry_safe_manual_initial_admin_link() -> None:
    settings = Settings(
        environment="test",
        auth_signing_key=SecretStr("manual-link-test-signing-key-material-0000000000000000"),
        frontend_base_url="https://tenant.example.test",
    )
    async with _tenant_api(settings=settings) as harness:
        _authorize_platform(harness.app)
        created = await harness.client.post(
            "/api/v1/platform/tenants",
            json={
                "slug": "manual-link-initial-admin",
                "name": "Manual Link Initial Admin",
                "initial_admin": {
                    "full_name": "Manual Link Admin",
                    "email": "manual.link.admin@example.test",
                },
            },
        )
        assert created.status_code == 201
        tenant_id = UUID(created.json()["data"]["id"])

        first = await harness.client.post(
            f"/api/v1/platform/tenants/{tenant_id}/initial-admin-invitation/manual-link",
            headers={
                "X-Request-Id": "req_initial_admin_manual_link_001",
                "X-Trace-Id": "20000000000000000000000000000001",
            },
        )
        second = await harness.client.post(
            f"/api/v1/platform/tenants/{tenant_id}/initial-admin-invitation/manual-link",
            headers={
                "X-Request-Id": "req_initial_admin_manual_link_002",
                "X-Trace-Id": "20000000000000000000000000000002",
            },
        )

        for response in (first, second):
            assert response.status_code == 201
            assert response.headers["cache-control"] == "no-store"
            assert response.headers["pragma"] == "no-cache"
            data = _phase1_data(response, {"activation_url", "expires_at", "status"})
            assert data["status"] == "manual_link_ready"
            assert data["activation_url"].startswith(
                "https://tenant.example.test/activate#token="
            )
            assert datetime.fromisoformat(data["expires_at"]).tzinfo is not None
            serialized_response = json.dumps(response.json()).lower()
            assert "email" not in serialized_response
            assert "identity" not in serialized_response
            assert "membership" not in serialized_response

        first_token = first.json()["data"]["activation_url"].split("#token=", 1)[1]
        second_token = second.json()["data"]["activation_url"].split("#token=", 1)[1]
        assert first_token != second_token

        async with harness.session_factory() as session:
            activations = tuple(
                await session.scalars(
                    select(UserActivationToken)
                    .where(UserActivationToken.tenant_id == tenant_id)
                    .order_by(UserActivationToken.created_at, UserActivationToken.id)
                )
            )
            outbox_events = tuple(
                await session.scalars(
                    select(OutboxEvent)
                    .where(OutboxEvent.tenant_id == tenant_id)
                    .order_by(OutboxEvent.created_at, OutboxEvent.id)
                )
            )
            audit_events = tuple(
                await session.scalars(
                    select(AuditEvent).where(AuditEvent.resource_id == tenant_id)
                )
            )

        assert len(activations) == 3
        active_activations = tuple(
            activation
            for activation in activations
            if activation.consumed_at is None and activation.revoked_at is None
        )
        assert len(active_activations) == 1
        assert active_activations[0].token_hash == hash_activation_token(second_token)
        assert any(
            activation.token_hash == hash_activation_token(first_token)
            and activation.revoked_at is not None
            for activation in activations
        )
        assert len(outbox_events) == 3
        assert all(
            set(event.payload) == {"recipient_user_id", "activation_id"}
            for event in outbox_events
        )
        manual_events = tuple(
            event
            for event in outbox_events
            if is_manual_activation_delivery_event(
                event.id,
                UUID(event.payload["activation_id"]),
            )
        )
        assert len(manual_events) == 2
        manual_activation_ids = {
            activation.id
            for activation in activations
            if activation.token_hash
            in {
                hash_activation_token(first_token),
                hash_activation_token(second_token),
            }
        }
        assert {event.payload["activation_id"] for event in manual_events} == {
            str(activation_id) for activation_id in manual_activation_ids
        }
        serialized_persistence = json.dumps(
            {
                "outbox": [event.payload for event in outbox_events],
                "audit": [
                    {
                        "metadata": event.metadata_,
                        "before": event.before_data,
                        "after": event.after_data,
                    }
                    for event in audit_events
                ],
            },
            sort_keys=True,
        )
        assert first_token not in serialized_persistence
        assert second_token not in serialized_persistence


async def test_initial_admin_reissue_does_not_enumerate_missing_or_activated_state() -> None:
    async with _tenant_api() as harness:
        _authorize_platform(harness.app)
        created = await harness.client.post(
            "/api/v1/platform/tenants",
            json={
                "slug": "already-activated-admin",
                "name": "Already Activated Admin",
                "initial_admin": {
                    "full_name": "Already Activated Admin",
                    "email": "already.activated.admin@example.test",
                },
            },
        )
        assert created.status_code == 201
        tenant_id = UUID(created.json()["data"]["id"])
        now = datetime.now(UTC)
        activated_password_hash = "$argon2id$activated-ineligible-credential"
        async with harness.session_factory.begin() as session:
            user = await session.scalar(select(User).where(User.tenant_id == tenant_id))
            membership = await session.scalar(
                select(TenantMembership).where(TenantMembership.tenant_id == tenant_id)
            )
            identity = await session.scalar(
                select(Identity).where(
                    Identity.email_normalized == "already.activated.admin@example.test"
                )
            )
            activation = await session.scalar(
                select(UserActivationToken).where(UserActivationToken.tenant_id == tenant_id)
            )
            assert user is not None
            assert membership is not None
            assert identity is not None
            assert activation is not None
            user.status = UserStatus.ACTIVE.value
            user.password_hash = activated_password_hash
            membership.status = UserStatus.ACTIVE.value
            identity.status = "active"
            identity.password_hash = activated_password_hash
            activation.consumed_at = now

        activated_response = await harness.client.post(
            f"/api/v1/platform/tenants/{tenant_id}/initial-admin-invitation/resend"
        )
        missing_response = await harness.client.post(
            f"/api/v1/platform/tenants/{uuid4()}/initial-admin-invitation/resend"
        )

        for response in (activated_response, missing_response):
            assert response.status_code == 409
            error = response.json()["error"]
            assert error["code"] == "tenant_initial_admin_unavailable"
            assert error["message"] == "The initial administrator cannot be prepared for access"
            assert "active" not in error["message"].lower()
            assert "identity" not in error["message"].lower()

        async with harness.session_factory() as session:
            activations = tuple(
                await session.scalars(
                    select(UserActivationToken).where(UserActivationToken.tenant_id == tenant_id)
                )
            )
            outbox_events = tuple(
                await session.scalars(select(OutboxEvent).where(OutboxEvent.tenant_id == tenant_id))
            )
            reissue_audit_count = len(
                tuple(
                    await session.scalars(
                        select(AuditEvent).where(
                            AuditEvent.event_type
                            == "platform.tenant.initial_admin_invitation_reissued",
                            AuditEvent.resource_id == tenant_id,
                        )
                    )
                )
            )

        assert len(activations) == 1
        assert activations[0].consumed_at is not None
        assert activations[0].revoked_at is None
        assert len(outbox_events) == 1
        assert reissue_audit_count == 0


async def test_initial_admin_reissue_rolls_back_when_audit_recording_fails() -> None:
    class FailingRecorder:
        async def record(self, _event: object, /) -> None:
            raise RuntimeError("simulated initial-admin audit failure")

    async with _tenant_api() as harness:
        _authorize_platform(harness.app)
        created = await harness.client.post(
            "/api/v1/platform/tenants",
            json={
                "slug": "reissue-audit-rollback",
                "name": "Reissue Audit Rollback",
                "initial_admin": {
                    "full_name": "Reissue Audit Rollback Admin",
                    "email": "reissue.audit.rollback@example.test",
                },
            },
        )
        assert created.status_code == 201
        tenant_id = UUID(created.json()["data"]["id"])
        async with harness.session_factory() as session:
            original_activation = await session.scalar(
                select(UserActivationToken).where(UserActivationToken.tenant_id == tenant_id)
            )
            assert original_activation is not None
            original_activation_id = original_activation.id
            original_activation_hash = original_activation.token_hash

        harness.app.dependency_overrides[get_platform_event_recorder] = FailingRecorder
        with pytest.raises(RuntimeError, match="simulated initial-admin audit failure"):
            await harness.client.post(
                f"/api/v1/platform/tenants/{tenant_id}/initial-admin-invitation/resend"
            )

        async with harness.session_factory() as session:
            activations = tuple(
                await session.scalars(
                    select(UserActivationToken).where(UserActivationToken.tenant_id == tenant_id)
                )
            )
            outbox_events = tuple(
                await session.scalars(select(OutboxEvent).where(OutboxEvent.tenant_id == tenant_id))
            )

        assert len(activations) == 1
        assert activations[0].id == original_activation_id
        assert activations[0].token_hash == original_activation_hash
        assert activations[0].revoked_at is None
        assert len(outbox_events) == 1
        assert ":reissue:" not in outbox_events[0].source_key


async def test_initial_admin_correction_rolls_back_when_audit_recording_fails() -> None:
    class FailingRecorder:
        async def record(self, _event: object, /) -> None:
            raise RuntimeError("simulated initial-admin correction audit failure")

    async with _tenant_api() as harness:
        _authorize_platform(harness.app)
        created = await harness.client.post(
            "/api/v1/platform/tenants",
            json={
                "slug": "correction-audit-rollback",
                "name": "Correction Audit Rollback",
                "initial_admin": {
                    "full_name": "Original Correction Admin",
                    "email": "original.correction.rollback@example.test",
                },
            },
        )
        assert created.status_code == 201
        tenant_id = UUID(created.json()["data"]["id"])
        async with harness.session_factory() as session:
            original_user = await session.scalar(select(User).where(User.tenant_id == tenant_id))
            original_membership = await session.scalar(
                select(TenantMembership).where(TenantMembership.tenant_id == tenant_id)
            )
            original_activation = await session.scalar(
                select(UserActivationToken).where(UserActivationToken.tenant_id == tenant_id)
            )
            assert original_user is not None
            assert original_membership is not None
            assert original_activation is not None
            original_state = (
                original_user.id,
                original_user.email,
                original_user.full_name,
                original_membership.identity_id,
                original_membership.full_name,
                original_activation.id,
                original_activation.token_hash,
            )

        harness.app.dependency_overrides[get_platform_event_recorder] = FailingRecorder
        with pytest.raises(
            RuntimeError,
            match="simulated initial-admin correction audit failure",
        ):
            await harness.client.patch(
                f"/api/v1/platform/tenants/{tenant_id}/initial-admin-invitation",
                json={
                    "full_name": "Must Roll Back",
                    "email": "must.rollback.correction@example.test",
                },
            )

        async with harness.session_factory() as session:
            user = await session.scalar(select(User).where(User.tenant_id == tenant_id))
            membership = await session.scalar(
                select(TenantMembership).where(TenantMembership.tenant_id == tenant_id)
            )
            activations = tuple(
                await session.scalars(
                    select(UserActivationToken).where(UserActivationToken.tenant_id == tenant_id)
                )
            )
            outbox_events = tuple(
                await session.scalars(select(OutboxEvent).where(OutboxEvent.tenant_id == tenant_id))
            )
            rolled_back_identity = await session.scalar(
                select(Identity).where(
                    Identity.email_normalized == "must.rollback.correction@example.test"
                )
            )

        assert user is not None
        assert membership is not None
        assert len(activations) == 1
        assert (
            user.id,
            user.email,
            user.full_name,
            membership.identity_id,
            membership.full_name,
            activations[0].id,
            activations[0].token_hash,
        ) == original_state
        assert activations[0].revoked_at is None
        assert len(outbox_events) == 1
        assert ":correction:" not in outbox_events[0].source_key
        assert rolled_back_identity is None


async def test_unusable_initial_admin_rolls_back_the_entire_tenant() -> None:
    async with _tenant_api() as harness:
        async with harness.session_factory.begin() as session:
            session.add(
                Identity(
                    id=uuid4(),
                    email="locked.initial.admin@example.test",
                    status="locked",
                    password_hash="$argon2id$locked-credential-must-remain-untouched",
                )
            )
        _authorize_platform(harness.app)

        response = await harness.client.post(
            "/api/v1/platform/tenants",
            json={
                "slug": "must-roll-back",
                "name": "Must Roll Back",
                "initial_admin": {
                    "full_name": "Locked Initial Admin",
                    "email": "locked.initial.admin@example.test",
                },
            },
        )

        assert response.status_code == 409
        assert response.json()["error"]["code"] == "tenant_initial_admin_unavailable"
        assert "locked" not in json.dumps(response.json()).lower()

        async with harness.session_factory() as session:
            tenant = await session.scalar(select(Tenant).where(Tenant.slug == "must-roll-back"))
            users = tuple(
                await session.scalars(
                    select(User).where(User.email == "locked.initial.admin@example.test")
                )
            )
            memberships = tuple(
                await session.scalars(
                    select(TenantMembership).where(
                        TenantMembership.identity_id
                        == select(Identity.id)
                        .where(Identity.email_normalized == "locked.initial.admin@example.test")
                        .scalar_subquery()
                    )
                )
            )

        assert tenant is None
        assert users == ()
        assert memberships == ()


async def test_existing_canonical_identity_is_attached_without_credential_changes() -> None:
    identity_id = uuid4()
    original_hash = "$argon2id$existing-canonical-credential"
    async with _tenant_api() as harness:
        async with harness.session_factory.begin() as session:
            session.add(
                Identity(
                    id=identity_id,
                    email="existing.initial.admin@example.test",
                    status="active",
                    password_hash=original_hash,
                    platform_permission_version=7,
                )
            )
        _authorize_platform(harness.app)

        response = await harness.client.post(
            "/api/v1/platform/tenants",
            json={
                "slug": "existing-admin-ready",
                "name": "Existing Admin Ready",
                "initial_admin": {
                    "full_name": "Existing Initial Admin",
                    "email": "existing.initial.admin@example.test",
                },
            },
        )

        assert response.status_code == 201
        tenant_id = UUID(response.json()["data"]["id"])
        async with harness.session_factory() as session:
            identities = tuple(
                await session.scalars(
                    select(Identity).where(
                        Identity.email_normalized == "existing.initial.admin@example.test"
                    )
                )
            )
            user = await session.scalar(select(User).where(User.tenant_id == tenant_id))
            membership = await session.scalar(
                select(TenantMembership).where(TenantMembership.tenant_id == tenant_id)
            )

        assert len(identities) == 1
        assert identities[0].id == identity_id
        assert identities[0].status == "active"
        assert identities[0].password_hash == original_hash
        assert identities[0].platform_permission_version == 7
        assert user is not None
        assert user.status == UserStatus.INVITED.value
        assert user.password_hash is None
        assert membership is not None
        assert membership.identity_id == identity_id
        assert membership.status == UserStatus.INVITED.value


async def test_platform_tenant_list_uses_bounded_deterministic_cursor_envelope() -> None:
    async with _tenant_api() as harness:
        _authorize_platform(harness.app)
        expected_ids = {str(TENANT_ID), str(OTHER_TENANT_ID)}
        for number in range(2):
            response = await harness.client.post(
                "/api/v1/platform/tenants",
                json={
                    "slug": f"cursor-falcon-{number}",
                    "name": f"Cursor Falcon {number}",
                    "initial_admin": {
                        "full_name": f"Cursor Admin {number}",
                        "email": f"cursor-admin-{number}@example.test",
                    },
                },
            )
            assert response.status_code == 201
            expected_ids.add(_phase1_data(response, PLATFORM_FIELDS | {"initial_admin"})["id"])

        fixed_created_at = datetime(2026, 7, 11, 8, 30, tzinfo=UTC)
        async with harness.session_factory() as session:
            tenants = list(await session.scalars(select(Tenant)))
            for tenant in tenants:
                tenant.created_at = fixed_created_at
            await session.commit()

        first_response = await harness.client.get(
            "/api/v1/platform/tenants",
            params={"limit": 2},
            headers={
                "X-Request-Id": "req_platform_page_001",
                "X-Trace-Id": "0123456789abcdef0123456789abcdef",
            },
        )
        assert first_response.status_code == 200
        first, cursor = _phase1_list(first_response, expected_limit=2)
        assert cursor is not None
        assert first_response.json()["meta"]["request_id"] == "req_platform_page_001"
        assert first_response.json()["meta"]["trace_id"] == ("0123456789abcdef0123456789abcdef")

        second_response = await harness.client.get(
            "/api/v1/platform/tenants",
            params={"limit": 2, "cursor": cursor},
        )
        assert second_response.status_code == 200
        second, terminal_cursor = _phase1_list(second_response, expected_limit=2)

    first_ids = [tenant["id"] for tenant in first]
    second_ids = [tenant["id"] for tenant in second]
    assert set(first_ids).isdisjoint(second_ids)
    assert set(first_ids + second_ids) == expected_ids
    assert first_ids + second_ids == sorted(expected_ids)
    assert terminal_cursor is None


@pytest.mark.parametrize(
    "query",
    [
        {"limit": 0},
        {"limit": 201},
        {"cursor": "not-a-platform-tenant-cursor"},
        {"offset": 1},
    ],
)
async def test_platform_tenant_list_rejects_unbounded_or_offset_pagination(
    query: dict[str, Any],
) -> None:
    async with _tenant_api() as harness:
        _authorize_platform(harness.app)

        response = await harness.client.get("/api/v1/platform/tenants", params=query)

    _assert_error_code(response, 422, "platform_tenant_validation_error")


async def test_platform_reads_legacy_premium_plan_but_new_writes_reject_it() -> None:
    async with _tenant_api() as harness:
        async with harness.session_factory() as session:
            tenant = await session.get(Tenant, OTHER_TENANT_ID)
            assert tenant is not None
            tenant.plan_code = "premium"
            await session.commit()
        _authorize_platform(harness.app)

        detail_response = await harness.client.get(f"/api/v1/platform/tenants/{OTHER_TENANT_ID}")
        create_response = await harness.client.post(
            "/api/v1/platform/tenants",
            json={
                "slug": "legacy-plan-write",
                "name": "Legacy Plan Write",
                "initial_admin": {
                    "full_name": "Legacy Plan Admin",
                    "email": "legacy-plan-admin@example.test",
                },
                "plan_code": "premium",
            },
        )

    assert detail_response.status_code == 200
    assert _phase1_data(detail_response, PLATFORM_FIELDS)["plan_code"] == "premium"
    assert create_response.status_code == 422


@pytest.mark.parametrize("client_field", ["id", "status", "tenant_id", "user_id"])
async def test_platform_provisioning_rejects_client_controlled_identity_and_status(
    client_field: str,
) -> None:
    async with _tenant_api() as harness:
        _authorize_platform(harness.app)
        payload = {
            "slug": f"client-field-{client_field}",
            "name": "Client Field",
            "initial_admin": {
                "full_name": "Client Field Admin",
                "email": f"client-field-{client_field}@example.test",
            },
        }
        payload[client_field] = str(uuid4()) if client_field != "status" else "active"

        response = await harness.client.post("/api/v1/platform/tenants", json=payload)

    assert response.status_code == 422


async def test_platform_provisioning_rejects_duplicate_slug_with_conflict() -> None:
    async with _tenant_api() as harness:
        _authorize_platform(harness.app)

        response = await harness.client.post(
            "/api/v1/platform/tenants",
            json={
                "slug": "wealthy-falcon",
                "name": "Duplicate",
                "initial_admin": {
                    "full_name": "Duplicate Admin",
                    "email": "duplicate-admin@example.test",
                },
            },
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
                "initial_admin": {
                    "full_name": "Invalid Metadata Admin",
                    "email": f"invalid-{field}@example.test",
                },
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
        body = _phase1_data(response, PLATFORM_FIELDS)
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
            json={
                "slug": "region-change",
                "name": "Region Change",
                "initial_admin": {
                    "full_name": "Region Change Admin",
                    "email": "region-change-admin@example.test",
                },
            },
        )
        assert create_response.status_code == 201
        created = _phase1_data(
            create_response,
            PLATFORM_FIELDS | {"initial_admin"},
        )
        region_response = await harness.client.patch(
            f"/api/v1/platform/tenants/{created['id']}",
            json={"data_region": "eu-1"},
        )
        assert region_response.status_code == 200
        assert _phase1_data(region_response, PLATFORM_FIELDS)["data_region"] == "eu-1"

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
                    assert _phase1_data(response, PLATFORM_FIELDS)["status"] == target
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
    assert _phase1_data(response, PLATFORM_FIELDS)["health"] == expected_health


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

    assert current_response.status_code == 401
    assert settings_response.status_code == 401
    assert current_response.json()["error"]["code"] == "authentication_required"
    assert settings_response.json()["error"]["code"] == "authentication_required"


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
    current = _phase1_data(current_response, TENANT_FIELDS)
    assert current["id"] == str(TENANT_ID)
    assert current["slug"] == "wealthy-falcon"
    assert current["plan_code"] == "core"

    assert settings_response.status_code == 200
    settings = _phase1_data(settings_response, SETTINGS_FIELDS)
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
        assert _phase1_data(response, SETTINGS_FIELDS) == {
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
