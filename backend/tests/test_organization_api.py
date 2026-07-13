from __future__ import annotations

from collections import Counter
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from uuid import UUID, uuid4

import pytest
from app.core.auth_runtime import AUTH_RUNTIME_STATE_KEY, AuthRuntime
from app.core.config import Settings
from app.db.base import Base
from app.db.session import DATABASE_RUNTIME_STATE_KEY, DatabaseRuntime
from app.main import create_app
from app.models.audit import AuditEvent
from app.models.department import Department, DepartmentStatus
from app.models.organization import Branch, BranchStatus, LegalEntity, LegalEntityStatus
from app.models.tenant import Tenant, TenantFeatureFlag, TenantStatus
from app.models.user import User, UserStatus
from app.modules.core.domain.feature_flags import FeatureFlagKey
from app.platform.identity import PasswordManager
from app.platform.pagination import encode_cursor
from app.platform.request_context import AuthenticationStrength, RequestContext
from app.platform.tenancy import TenantContext
from app.schemas.department import DepartmentCreate
from app.schemas.organization import BranchCreate, BranchListCursor
from app.services.authorization_service import assign_system_role, seed_authorization_catalog
from app.services.department_service import (
    DepartmentLifecycleConflictError,
    DepartmentService,
)
from app.services.identity_projection_service import sync_identity_membership_projection
from app.services.organization_service import (
    ORGANIZATION_READ_PERMISSION,
    ORGANIZATION_UPDATE_PERMISSION,
    BranchNotAssignableError,
    OrganizationService,
)
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

TENANT_A_ID = UUID("c1000000-0000-4000-8000-000000000001")
TENANT_B_ID = UUID("c1000000-0000-4000-8000-000000000002")
ADMIN_A_ID = UUID("ca000000-0000-4000-8000-000000000001")
EMPLOYEE_A_ID = UUID("ca000000-0000-4000-8000-000000000002")
HR_A_ID = UUID("ca000000-0000-4000-8000-000000000003")
DEFAULT_ENTITY_A_ID = TENANT_A_ID
DEFAULT_ENTITY_B_ID = TENANT_B_ID
BRANCH_B_ID = UUID("cb000000-0000-4000-8000-000000000001")
DEPARTMENT_B_ID = UUID("cc000000-0000-4000-8000-000000000001")

ADMIN_A_EMAIL = "admin@organization-a.test"
EMPLOYEE_A_EMAIL = "employee@organization-a.test"
HR_A_EMAIL = "hr@organization-a.test"
PASSWORD = "P3F focused organization API password"


@dataclass(slots=True)
class OrganizationApiHarness:
    app: FastAPI
    client: AsyncClient
    runtime: DatabaseRuntime
    session_factory: async_sessionmaker[AsyncSession]


@asynccontextmanager
async def _organization_api() -> AsyncIterator[OrganizationApiHarness]:
    settings = Settings(
        _env_file=None,
        environment="test",
        database_url="sqlite+aiosqlite:///:memory:",
        auth_signing_key="p3f-test-signing-key-material-that-is-not-a-real-secret",
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
        await _seed_organization(runtime.session_factory, auth_runtime.password_manager)

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://testserver",
        ) as client:
            yield OrganizationApiHarness(
                app=app,
                client=client,
                runtime=runtime,
                session_factory=runtime.session_factory,
            )


async def _seed_organization(
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
                    slug="organization-a",
                    name="Organization A",
                    status=TenantStatus.ACTIVE.value,
                    plan_code="core",
                    data_region="tr-1",
                    locale="en-US",
                    timezone="Europe/Istanbul",
                ),
                Tenant(
                    id=TENANT_B_ID,
                    slug="organization-b",
                    name="Organization B",
                    status=TenantStatus.ACTIVE.value,
                    plan_code="core",
                    data_region="tr-1",
                    locale="en-US",
                    timezone="Europe/London",
                ),
                TenantFeatureFlag(
                    tenant_id=TENANT_A_ID,
                    key=FeatureFlagKey.ORGANIZATION.value,
                    enabled=True,
                ),
                TenantFeatureFlag(
                    tenant_id=TENANT_B_ID,
                    key=FeatureFlagKey.ORGANIZATION.value,
                    enabled=True,
                ),
                User(
                    id=ADMIN_A_ID,
                    tenant_id=TENANT_A_ID,
                    email=ADMIN_A_EMAIL,
                    full_name="Organization A Administrator",
                    status=UserStatus.ACTIVE.value,
                    password_hash=password_hash,
                    can_invite_users=True,
                ),
                User(
                    id=EMPLOYEE_A_ID,
                    tenant_id=TENANT_A_ID,
                    email=EMPLOYEE_A_EMAIL,
                    full_name="Organization A Employee",
                    status=UserStatus.ACTIVE.value,
                    password_hash=password_hash,
                ),
                User(
                    id=HR_A_ID,
                    tenant_id=TENANT_A_ID,
                    email=HR_A_EMAIL,
                    full_name="Organization A HR Specialist",
                    status=UserStatus.ACTIVE.value,
                    password_hash=password_hash,
                ),
            ]
        )
        await session.flush()
        session.add_all(
            [
                LegalEntity(
                    id=DEFAULT_ENTITY_A_ID,
                    tenant_id=TENANT_A_ID,
                    code="DEFAULT",
                    name="Organization A",
                    registered_name="Organization A",
                    country_code="TR",
                    tax_number=None,
                    timezone="Europe/Istanbul",
                    status=LegalEntityStatus.ACTIVE.value,
                    is_default=True,
                ),
                LegalEntity(
                    id=DEFAULT_ENTITY_B_ID,
                    tenant_id=TENANT_B_ID,
                    code="DEFAULT",
                    name="Organization B",
                    registered_name="Organization B",
                    country_code="GB",
                    tax_number=None,
                    timezone="Europe/London",
                    status=LegalEntityStatus.ACTIVE.value,
                    is_default=True,
                ),
                Branch(
                    id=BRANCH_B_ID,
                    tenant_id=TENANT_B_ID,
                    legal_entity_id=DEFAULT_ENTITY_B_ID,
                    code="LON",
                    name="London",
                    timezone="Europe/London",
                    country_code="GB",
                    city="London",
                    address="Tenant B historical address",
                    status=BranchStatus.ACTIVE.value,
                    archived_at=None,
                ),
                Department(
                    id=DEPARTMENT_B_ID,
                    tenant_id=TENANT_B_ID,
                    parent_id=None,
                    code="B-ROOT",
                    name="Tenant B Department",
                    status=DepartmentStatus.ACTIVE.value,
                    archived_at=None,
                ),
            ]
        )
        await session.flush()
        await assign_system_role(
            session,
            tenant_id=TENANT_A_ID,
            user_id=ADMIN_A_ID,
            role_code="tenant_admin",
        )
        await assign_system_role(
            session,
            tenant_id=TENANT_A_ID,
            user_id=EMPLOYEE_A_ID,
            role_code="employee",
        )
        await assign_system_role(
            session,
            tenant_id=TENANT_A_ID,
            user_id=HR_A_ID,
            role_code="hr_specialist",
        )
        for user_id in (ADMIN_A_ID, EMPLOYEE_A_ID, HR_A_ID):
            user = await session.get(User, user_id)
            assert user is not None
            await sync_identity_membership_projection(session, user)


async def _login(client: AsyncClient, *, email: str) -> str:
    response = await client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": PASSWORD},
    )
    assert response.status_code == 200
    return response.json()["data"]["access_token"]


def _authorization(access_token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {access_token}"}


def _service_context() -> RequestContext:
    return RequestContext(
        request_id="req-p3f-assignable",
        trace_id="1234567890abcdef1234567890abcdef",
        tenant=TenantContext(tenant_id=TENANT_A_ID, slug="organization-a"),
        actor_id=ADMIN_A_ID,
        authentication_strength=AuthenticationStrength.SINGLE_FACTOR,
    )


class _FailingAuditRecorder:
    async def record(self, _event: object) -> None:
        raise RuntimeError("forced organization audit failure")


async def _organization_audit_events(
    session_factory: async_sessionmaker[AsyncSession],
) -> tuple[AuditEvent, ...]:
    async with session_factory() as session:
        return tuple(
            await session.scalars(
                select(AuditEvent)
                .where(
                    AuditEvent.tenant_id == TENANT_A_ID,
                    AuditEvent.event_type.in_(
                        (
                            "legal_entity.created",
                            "legal_entity.updated",
                            "branch.created",
                            "branch.updated",
                            "branch.archived",
                        )
                    ),
                )
                .order_by(AuditEvent.occurred_at, AuditEvent.id)
            )
        )


async def test_tenant_admin_reads_edits_and_creates_legal_entities_with_audit() -> None:
    async with _organization_api() as harness:
        token = await _login(harness.client, email=ADMIN_A_EMAIL)
        headers = {
            **_authorization(token),
            "X-Tenant-Id": str(TENANT_B_ID),
            "X-Tenant-Slug": "organization-b",
        }

        listed = await harness.client.get("/api/v1/legal-entities", headers=headers)
        assert listed.status_code == 200
        assert listed.headers["Cache-Control"] == "no-store"
        assert listed.json()["meta"]["limit"] == 25
        assert [entity["id"] for entity in listed.json()["data"]] == [str(DEFAULT_ENTITY_A_ID)]
        assert listed.json()["data"][0]["is_default"] is True

        detail = await harness.client.get(
            f"/api/v1/legal-entities/{DEFAULT_ENTITY_A_ID}",
            headers=headers,
        )
        assert detail.status_code == 200
        assert detail.json()["data"]["code"] == "DEFAULT"

        updated = await harness.client.patch(
            f"/api/v1/legal-entities/{DEFAULT_ENTITY_A_ID}",
            headers=headers,
            json={
                "name": "Falcon Turkey",
                "registered_name": "Falcon Turkey Incorporated",
                "country_code": "tr",
                "tax_number": "TR-100200300",
                "timezone": "Europe/Istanbul",
            },
        )
        assert updated.status_code == 200
        updated_entity = updated.json()["data"]
        assert updated_entity["name"] == "Falcon Turkey"
        assert updated_entity["registered_name"] == "Falcon Turkey Incorporated"
        assert updated_entity["country_code"] == "TR"
        assert updated_entity["tax_number"] == "TR-100200300"

        immutable_code = await harness.client.patch(
            f"/api/v1/legal-entities/{DEFAULT_ENTITY_A_ID}",
            headers=headers,
            json={"code": "RENAMED"},
        )
        assert immutable_code.status_code == 422
        assert immutable_code.json()["error"]["code"] == "organization_validation_error"

        created = await harness.client.post(
            "/api/v1/legal-entities",
            headers=headers,
            json={
                "code": "falcon-eu",
                "name": "Falcon Europe",
                "registered_name": "Falcon Europe B.V.",
                "country_code": "nl",
                "tax_number": "NL-998877",
                "timezone": "Europe/Amsterdam",
            },
        )
        assert created.status_code == 201
        created_entity = created.json()["data"]
        assert created_entity["code"] == "FALCON-EU"
        assert created_entity["is_default"] is False

        duplicate = await harness.client.post(
            "/api/v1/legal-entities",
            headers=headers,
            json={
                "code": "FALCON-EU",
                "name": "Duplicate",
                "registered_name": "Duplicate B.V.",
                "timezone": "Europe/Amsterdam",
            },
        )
        assert duplicate.status_code == 409
        assert duplicate.json()["error"]["code"] == "legal_entity_code_conflict"

        first_page = await harness.client.get(
            "/api/v1/legal-entities",
            headers=headers,
            params={"limit": 1},
        )
        assert first_page.status_code == 200
        assert len(first_page.json()["data"]) == 1
        assert first_page.json()["meta"]["next_cursor"]
        second_page = await harness.client.get(
            "/api/v1/legal-entities",
            headers=headers,
            params={
                "limit": 1,
                "cursor": first_page.json()["meta"]["next_cursor"],
            },
        )
        assert second_page.status_code == 200
        assert {
            first_page.json()["data"][0]["id"],
            second_page.json()["data"][0]["id"],
        } == {str(DEFAULT_ENTITY_A_ID), created_entity["id"]}

        events = await _organization_audit_events(harness.session_factory)
        events_by_type = {event.event_type: event for event in events}
        assert set(events_by_type) == {"legal_entity.created", "legal_entity.updated"}
        assert all(event.actor_user_id == ADMIN_A_ID for event in events)
        assert all(event.category == "hr_operations" for event in events)
        assert events_by_type["legal_entity.updated"].resource_id == DEFAULT_ENTITY_A_ID
        assert events_by_type["legal_entity.created"].resource_id == UUID(created_entity["id"])


async def test_branch_crud_cursor_archive_history_assignable_guard_and_stable_code() -> None:
    async with _organization_api() as harness:
        token = await _login(harness.client, email=ADMIN_A_EMAIL)
        headers = _authorization(token)

        created_ids: dict[str, UUID] = {}
        for payload in (
            {
                "legal_entity_id": str(DEFAULT_ENTITY_A_ID),
                "code": "ist",
                "name": "Istanbul",
                "timezone": "Europe/Istanbul",
                "country_code": "tr",
                "city": "Istanbul",
                "address": "Maslak",
            },
            {
                "legal_entity_id": str(DEFAULT_ENTITY_A_ID),
                "code": "ank",
                "name": "Ankara",
                "timezone": "Europe/Istanbul",
                "country_code": "tr",
                "city": "Ankara",
                "address": "Cankaya",
            },
        ):
            response = await harness.client.post(
                "/api/v1/branches",
                headers=headers,
                json=payload,
            )
            assert response.status_code == 201
            assert response.json()["data"]["accepts_new_assignments"] is True
            created_ids[response.json()["data"]["code"]] = UUID(response.json()["data"]["id"])

        first_page = await harness.client.get(
            "/api/v1/branches",
            headers=headers,
            params={"limit": 1},
        )
        assert first_page.status_code == 200
        assert [branch["code"] for branch in first_page.json()["data"]] == ["ANK"]
        assert first_page.json()["meta"]["next_cursor"]
        second_page = await harness.client.get(
            "/api/v1/branches",
            headers=headers,
            params={
                "limit": 1,
                "cursor": first_page.json()["meta"]["next_cursor"],
            },
        )
        assert second_page.status_code == 200
        assert [branch["code"] for branch in second_page.json()["data"]] == ["IST"]

        istanbul_id = created_ids["IST"]
        detail = await harness.client.get(
            f"/api/v1/branches/{istanbul_id}",
            headers=headers,
        )
        assert detail.status_code == 200
        assert detail.json()["data"]["accepts_new_assignments"] is True

        service = OrganizationService(session_factory=harness.session_factory)
        assignable = await service.require_assignable_branch(
            request_context=_service_context(),
            branch_id=istanbul_id,
            granted_permissions=(ORGANIZATION_READ_PERMISSION,),
        )
        assert assignable.id == istanbul_id

        immutable_code = await harness.client.patch(
            f"/api/v1/branches/{istanbul_id}",
            headers=headers,
            json={"code": "IST-NEW"},
        )
        assert immutable_code.status_code == 422
        assert immutable_code.json()["error"]["code"] == "organization_validation_error"

        updated = await harness.client.patch(
            f"/api/v1/branches/{istanbul_id}",
            headers=headers,
            json={
                "name": "Istanbul Headquarters",
                "timezone": "Europe/Istanbul",
                "city": "Istanbul",
                "address": "Levent",
            },
        )
        assert updated.status_code == 200
        assert updated.json()["data"]["name"] == "Istanbul Headquarters"
        assert updated.json()["data"]["address"] == "Levent"

        archived = await harness.client.delete(
            f"/api/v1/branches/{istanbul_id}",
            headers=headers,
        )
        assert archived.status_code == 200
        assert archived.json()["data"]["status"] == "archived"
        assert archived.json()["data"]["archived_at"] is not None
        assert archived.json()["data"]["accepts_new_assignments"] is False

        historical = await harness.client.get(
            f"/api/v1/branches/{istanbul_id}",
            headers=headers,
        )
        assert historical.status_code == 200
        assert historical.json()["data"]["status"] == "archived"
        assert historical.json()["data"]["accepts_new_assignments"] is False

        archived_list = await harness.client.get(
            "/api/v1/branches",
            headers=headers,
            params={"status": "archived"},
        )
        assert archived_list.status_code == 200
        assert [branch["id"] for branch in archived_list.json()["data"]] == [str(istanbul_id)]

        archived_update = await harness.client.patch(
            f"/api/v1/branches/{istanbul_id}",
            headers=headers,
            json={"name": "Reopened"},
        )
        assert archived_update.status_code == 409
        assert archived_update.json()["error"]["code"] == "organization_conflict"

        with pytest.raises(BranchNotAssignableError):
            await service.require_assignable_branch(
                request_context=_service_context(),
                branch_id=istanbul_id,
                granted_permissions=(ORGANIZATION_READ_PERMISSION,),
            )

        reused_code = await harness.client.post(
            "/api/v1/branches",
            headers=headers,
            json={
                "legal_entity_id": str(DEFAULT_ENTITY_A_ID),
                "code": "ist",
                "name": "Replacement Istanbul",
                "timezone": "Europe/Istanbul",
            },
        )
        assert reused_code.status_code == 409
        assert reused_code.json()["error"]["code"] == "branch_code_conflict"

        events = await _organization_audit_events(harness.session_factory)
        assert Counter(event.event_type for event in events) == Counter(
            {
                "branch.created": 2,
                "branch.updated": 1,
                "branch.archived": 1,
            }
        )
        archived_event = next(event for event in events if event.event_type == "branch.archived")
        assert archived_event.resource_id == istanbul_id
        assert archived_event.changed_fields == ["archived_at", "status"]
        assert archived_event.metadata_ == {
            "after_status": "archived",
            "before_status": "active",
        }


async def test_tenant_and_rbac_boundaries_ignore_spoofed_headers_and_fail_closed() -> None:
    async with _organization_api() as harness:
        admin_token = await _login(harness.client, email=ADMIN_A_EMAIL)
        employee_token = await _login(harness.client, email=EMPLOYEE_A_EMAIL)
        hr_token = await _login(harness.client, email=HR_A_EMAIL)
        spoofed_headers = {
            **_authorization(admin_token),
            "X-Tenant-Id": str(TENANT_B_ID),
            "X-Tenant-Slug": "organization-b",
        }

        entities = await harness.client.get(
            "/api/v1/legal-entities",
            headers=spoofed_headers,
        )
        assert entities.status_code == 200
        assert [entity["id"] for entity in entities.json()["data"]] == [str(DEFAULT_ENTITY_A_ID)]
        branches = await harness.client.get("/api/v1/branches", headers=spoofed_headers)
        assert branches.status_code == 200
        assert branches.json()["data"] == []

        cross_entity = await harness.client.get(
            f"/api/v1/legal-entities/{DEFAULT_ENTITY_B_ID}",
            headers=_authorization(admin_token),
        )
        assert cross_entity.status_code == 404
        assert cross_entity.json()["error"]["code"] == "legal_entity_not_found"
        cross_branch = await harness.client.get(
            f"/api/v1/branches/{BRANCH_B_ID}",
            headers=_authorization(admin_token),
        )
        assert cross_branch.status_code == 404
        assert cross_branch.json()["error"]["code"] == "branch_not_found"
        cross_parent = await harness.client.post(
            "/api/v1/branches",
            headers=_authorization(admin_token),
            json={
                "legal_entity_id": str(DEFAULT_ENTITY_B_ID),
                "code": "ESCAPE",
                "name": "Cross tenant branch",
                "timezone": "UTC",
            },
        )
        assert cross_parent.status_code == 404
        assert cross_parent.json()["error"]["code"] == "legal_entity_not_found"

        employee_headers = _authorization(employee_token)
        denied_read = await harness.client.get(
            "/api/v1/legal-entities",
            headers=employee_headers,
        )
        assert denied_read.status_code == 403
        assert denied_read.json()["error"]["code"] == "organization_access_denied"
        denied_write = await harness.client.post(
            "/api/v1/branches",
            headers=employee_headers,
            json={
                "legal_entity_id": str(DEFAULT_ENTITY_A_ID),
                "code": "DENIED",
                "name": "Denied branch",
                "timezone": "UTC",
            },
        )
        assert denied_write.status_code == 403
        assert denied_write.json()["error"]["code"] == "organization_access_denied"

        hr_read = await harness.client.get(
            "/api/v1/legal-entities",
            headers=_authorization(hr_token),
        )
        assert hr_read.status_code == 200
        hr_write = await harness.client.post(
            "/api/v1/branches",
            headers=_authorization(hr_token),
            json={
                "legal_entity_id": str(DEFAULT_ENTITY_A_ID),
                "code": "HR-SCOPE",
                "name": "HR managed branch",
                "timezone": "UTC",
            },
        )
        assert hr_write.status_code == 201

        async with harness.session_factory() as session:
            tenant_b_branch = await session.get(Branch, BRANCH_B_ID)
            assert tenant_b_branch is not None
            assert tenant_b_branch.name == "London"


async def test_organization_validation_is_bounded_and_filter_bound() -> None:
    async with _organization_api() as harness:
        token = await _login(harness.client, email=ADMIN_A_EMAIL)
        headers = _authorization(token)
        mismatched_cursor = BranchListCursor(
            code="ank",
            id=uuid4(),
            status="",
            legal_entity_id="",
        ).to_token()
        malformed_legal_cursor = encode_cursor(
            "legal_entities",
            {"code": "\u0000", "id": str(uuid4())},
        )
        malformed_branch_cursor = encode_cursor(
            "branches",
            {
                "code": "\u0000",
                "id": str(uuid4()),
                "status": "",
                "legal_entity_id": "",
            },
        )

        paths = (
            "/api/v1/legal-entities?limit=101",
            "/api/v1/legal-entities?limit=1&limit=2",
            "/api/v1/legal-entities?offset=1",
            "/api/v1/legal-entities?cursor=not-a-cursor",
            f"/api/v1/legal-entities?cursor={malformed_legal_cursor}",
            "/api/v1/branches?limit=101",
            "/api/v1/branches?offset=1",
            "/api/v1/branches?status=unknown",
            f"/api/v1/branches?cursor={mismatched_cursor}&status=active",
            f"/api/v1/branches?cursor={malformed_branch_cursor}",
        )
        for path in paths:
            response = await harness.client.get(path, headers=headers)
            assert response.status_code == 422
            assert response.json()["error"]["code"] == "organization_validation_error"

        invalid_timezone = await harness.client.post(
            "/api/v1/branches",
            headers=headers,
            json={
                "legal_entity_id": str(DEFAULT_ENTITY_A_ID),
                "code": "BAD-TZ",
                "name": "Invalid timezone",
                "timezone": "Mars/Olympus_Mons",
            },
        )
        assert invalid_timezone.status_code == 422
        assert invalid_timezone.json()["error"]["code"] == "organization_validation_error"

        nul_text = await harness.client.post(
            "/api/v1/branches",
            headers=headers,
            json={
                "legal_entity_id": str(DEFAULT_ENTITY_A_ID),
                "code": "NUL-TEXT",
                "name": "Invalid\u0000branch",
                "timezone": "UTC",
            },
        )
        assert nul_text.status_code == 422
        assert nul_text.json()["error"]["code"] == "organization_validation_error"

        empty_patch = await harness.client.patch(
            f"/api/v1/legal-entities/{DEFAULT_ENTITY_A_ID}",
            headers=headers,
            json={},
        )
        assert empty_patch.status_code == 422
        assert empty_patch.json()["error"]["code"] == "organization_validation_error"


async def test_disabled_organization_feature_fails_closed_before_data_access() -> None:
    async with _organization_api() as harness:
        token = await _login(harness.client, email=ADMIN_A_EMAIL)
        async with harness.session_factory.begin() as session:
            feature = await session.get(
                TenantFeatureFlag,
                (TENANT_A_ID, FeatureFlagKey.ORGANIZATION.value),
            )
            assert feature is not None
            feature.enabled = False

        response = await harness.client.get(
            "/api/v1/legal-entities",
            headers=_authorization(token),
        )
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "organization_feature_unavailable"

        write = await harness.client.post(
            "/api/v1/branches",
            headers=_authorization(token),
            json={
                "legal_entity_id": str(DEFAULT_ENTITY_A_ID),
                "code": "DISABLED",
                "name": "Must not be created",
                "timezone": "UTC",
            },
        )
        assert write.status_code == 404
        assert write.json()["error"]["code"] == "organization_feature_unavailable"

        async with harness.session_factory() as session:
            assert (
                await session.scalar(select(Branch.id).where(Branch.code_normalized == "disabled"))
                is None
            )

        async with harness.session_factory.begin() as session:
            feature = await session.get(
                TenantFeatureFlag,
                (TENANT_A_ID, FeatureFlagKey.ORGANIZATION.value),
            )
            assert feature is not None
            await session.delete(feature)
        missing_flag = await harness.client.get(
            "/api/v1/branches",
            headers=_authorization(token),
        )
        assert missing_flag.status_code == 404
        assert missing_flag.json()["error"]["code"] == ("organization_feature_unavailable")


async def test_organization_write_rolls_back_when_same_transaction_audit_fails() -> None:
    async with _organization_api() as harness:
        service = OrganizationService(
            session_factory=harness.session_factory,
            audit_recorder_factory=lambda _session: _FailingAuditRecorder(),
        )
        with pytest.raises(RuntimeError, match="forced organization audit failure"):
            await service.create_branch(
                request_context=_service_context(),
                payload=BranchCreate(
                    legal_entity_id=DEFAULT_ENTITY_A_ID,
                    code="ROLLBACK",
                    name="Must Roll Back",
                    timezone="UTC",
                ),
                granted_permissions=(
                    ORGANIZATION_READ_PERMISSION,
                    ORGANIZATION_UPDATE_PERMISSION,
                ),
            )

        async with harness.session_factory() as session:
            rolled_back = await session.scalar(
                select(Branch.id).where(
                    Branch.tenant_id == TENANT_A_ID,
                    Branch.code_normalized == "rollback",
                )
            )
            audit_event = await session.scalar(
                select(AuditEvent.id).where(
                    AuditEvent.tenant_id == TENANT_A_ID,
                    AuditEvent.event_type == "branch.created",
                )
            )
        assert rolled_back is None
        assert audit_event is None


async def test_department_lazy_hierarchy_move_cycle_archive_history_and_audit() -> None:
    async with _organization_api() as harness:
        token = await _login(harness.client, email=ADMIN_A_EMAIL)
        headers = _authorization(token)

        async def create_department(
            *,
            code: str,
            name: str,
            parent_id: str | None = None,
        ) -> dict[str, object]:
            response = await harness.client.post(
                "/api/v1/departments",
                headers=headers,
                json={"code": code, "name": name, "parent_id": parent_id},
            )
            assert response.status_code == 201
            assert response.json()["data"]["accepts_new_assignments"] is True
            return response.json()["data"]

        engineering = await create_department(code="eng", name="Engineering")
        operations = await create_department(code="ops", name="Operations")
        platform = await create_department(
            code="platform",
            name="Platform Engineering",
            parent_id=str(engineering["id"]),
        )
        sre = await create_department(
            code="sre",
            name="Site Reliability",
            parent_id=str(platform["id"]),
        )

        first_roots = await harness.client.get(
            "/api/v1/departments/tree",
            headers=headers,
            params={"limit": 1},
        )
        assert first_roots.status_code == 200
        assert first_roots.headers["Cache-Control"] == "no-store"
        assert [item["code"] for item in first_roots.json()["data"]] == ["ENG"]
        assert first_roots.json()["data"][0]["has_children"] is True
        root_cursor = first_roots.json()["meta"]["next_cursor"]
        assert root_cursor

        second_roots = await harness.client.get(
            "/api/v1/departments/tree",
            headers=headers,
            params={"limit": 1, "cursor": root_cursor},
        )
        assert second_roots.status_code == 200
        assert [item["code"] for item in second_roots.json()["data"]] == ["OPS"]

        mismatched_level = await harness.client.get(
            "/api/v1/departments/tree",
            headers=headers,
            params={
                "limit": 1,
                "cursor": root_cursor,
                "parent_id": engineering["id"],
            },
        )
        assert mismatched_level.status_code == 422
        assert mismatched_level.json()["error"]["code"] == "organization_validation_error"

        engineering_children = await harness.client.get(
            "/api/v1/departments/tree",
            headers=headers,
            params={"parent_id": engineering["id"]},
        )
        assert engineering_children.status_code == 200
        assert [item["code"] for item in engineering_children.json()["data"]] == ["PLATFORM"]
        assert engineering_children.json()["data"][0]["has_children"] is True

        platform_children = await harness.client.get(
            "/api/v1/departments/tree",
            headers=headers,
            params={"parent_id": platform["id"]},
        )
        assert [item["code"] for item in platform_children.json()["data"]] == ["SRE"]

        renamed = await harness.client.patch(
            f"/api/v1/departments/{platform['id']}",
            headers=headers,
            json={"name": "Cloud Platform"},
        )
        assert renamed.status_code == 200
        assert renamed.json()["data"]["name"] == "Cloud Platform"
        assert renamed.json()["data"]["code"] == "PLATFORM"

        immutable_code = await harness.client.patch(
            f"/api/v1/departments/{platform['id']}",
            headers=headers,
            json={"code": "RENAMED"},
        )
        assert immutable_code.status_code == 422
        assert immutable_code.json()["error"]["code"] == "organization_validation_error"

        moved_to_root = await harness.client.patch(
            f"/api/v1/departments/{platform['id']}",
            headers=headers,
            json={"parent_id": None},
        )
        assert moved_to_root.status_code == 200
        assert moved_to_root.json()["data"]["parent_id"] is None

        moved_to_operations = await harness.client.patch(
            f"/api/v1/departments/{platform['id']}",
            headers=headers,
            json={"parent_id": operations["id"]},
        )
        assert moved_to_operations.status_code == 200
        assert moved_to_operations.json()["data"]["parent_id"] == operations["id"]

        cycle = await harness.client.patch(
            f"/api/v1/departments/{operations['id']}",
            headers=headers,
            json={"parent_id": sre["id"]},
        )
        assert cycle.status_code == 409
        assert cycle.json()["error"]["code"] == "department_cycle_conflict"

        self_cycle = await harness.client.patch(
            f"/api/v1/departments/{platform['id']}",
            headers=headers,
            json={"parent_id": platform["id"]},
        )
        assert self_cycle.status_code == 409
        assert self_cycle.json()["error"]["code"] == "department_cycle_conflict"

        used_parent = await harness.client.delete(
            f"/api/v1/departments/{platform['id']}",
            headers=headers,
        )
        assert used_parent.status_code == 409
        assert used_parent.json()["error"]["code"] == "organization_conflict"

        department_service = DepartmentService(session_factory=harness.session_factory)
        assignable = await department_service.require_assignable_department(
            request_context=_service_context(),
            department_id=UUID(str(sre["id"])),
            granted_permissions=(ORGANIZATION_READ_PERMISSION,),
        )
        assert assignable.id == UUID(str(sre["id"]))

        archived_sre = await harness.client.delete(
            f"/api/v1/departments/{sre['id']}",
            headers=headers,
        )
        assert archived_sre.status_code == 200
        assert archived_sre.json()["data"]["status"] == "archived"
        assert archived_sre.json()["data"]["parent_id"] == platform["id"]
        assert archived_sre.json()["data"]["accepts_new_assignments"] is False
        with pytest.raises(DepartmentLifecycleConflictError):
            await department_service.require_assignable_department(
                request_context=_service_context(),
                department_id=UUID(str(sre["id"])),
                granted_permissions=(ORGANIZATION_READ_PERMISSION,),
            )

        active_platform_children = await harness.client.get(
            "/api/v1/departments/tree",
            headers=headers,
            params={"parent_id": platform["id"]},
        )
        assert active_platform_children.status_code == 200
        assert active_platform_children.json()["data"] == []

        archived_platform = await harness.client.delete(
            f"/api/v1/departments/{platform['id']}",
            headers=headers,
        )
        assert archived_platform.status_code == 200
        assert archived_platform.json()["data"]["status"] == "archived"
        assert archived_platform.json()["data"]["parent_id"] == operations["id"]
        assert archived_platform.json()["data"]["has_children"] is True

        history_level = await harness.client.get(
            "/api/v1/departments/tree",
            headers=headers,
            params={"parent_id": operations["id"], "include_archived": True},
        )
        assert history_level.status_code == 200
        assert [item["code"] for item in history_level.json()["data"]] == ["PLATFORM"]
        assert history_level.json()["data"][0]["status"] == "archived"

        nested_history = await harness.client.get(
            "/api/v1/departments/tree",
            headers=headers,
            params={"parent_id": platform["id"], "include_archived": True},
        )
        assert [item["code"] for item in nested_history.json()["data"]] == ["SRE"]

        archived_update = await harness.client.patch(
            f"/api/v1/departments/{platform['id']}",
            headers=headers,
            json={"name": "Reopened"},
        )
        assert archived_update.status_code == 409
        assert archived_update.json()["error"]["code"] == "organization_conflict"

        archived_list = await harness.client.get(
            "/api/v1/departments",
            headers=headers,
            params={"status": "archived", "limit": 1},
        )
        assert archived_list.status_code == 200
        assert len(archived_list.json()["data"]) == 1
        assert archived_list.json()["meta"]["next_cursor"]

        reused_code = await harness.client.post(
            "/api/v1/departments",
            headers=headers,
            json={"code": "platform", "name": "Replacement Platform"},
        )
        assert reused_code.status_code == 409
        assert reused_code.json()["error"]["code"] == "department_code_conflict"

        async with harness.session_factory() as session:
            events = tuple(
                await session.scalars(
                    select(AuditEvent)
                    .where(
                        AuditEvent.tenant_id == TENANT_A_ID,
                        AuditEvent.event_type.in_(
                            (
                                "department.created",
                                "department.updated",
                                "department.archived",
                            )
                        ),
                    )
                    .order_by(AuditEvent.occurred_at, AuditEvent.id)
                )
            )
        assert Counter(event.event_type for event in events) == Counter(
            {
                "department.created": 4,
                "department.updated": 3,
                "department.archived": 2,
            }
        )
        assert all(event.actor_user_id == ADMIN_A_ID for event in events)
        assert all(event.resource_type == "department" for event in events)


async def test_department_tenant_rbac_feature_and_audit_transaction_boundaries() -> None:
    async with _organization_api() as harness:
        admin_token = await _login(harness.client, email=ADMIN_A_EMAIL)
        employee_token = await _login(harness.client, email=EMPLOYEE_A_EMAIL)
        hr_token = await _login(harness.client, email=HR_A_EMAIL)

        spoofed = await harness.client.get(
            "/api/v1/departments/tree",
            headers={
                **_authorization(admin_token),
                "X-Tenant-Id": str(TENANT_B_ID),
                "X-Tenant-Slug": "organization-b",
            },
        )
        assert spoofed.status_code == 200
        assert spoofed.json()["data"] == []

        cross_tenant = await harness.client.get(
            f"/api/v1/departments/{DEPARTMENT_B_ID}",
            headers=_authorization(admin_token),
        )
        assert cross_tenant.status_code == 404
        assert cross_tenant.json()["error"]["code"] == "department_not_found"

        cross_parent = await harness.client.post(
            "/api/v1/departments",
            headers=_authorization(admin_token),
            json={
                "code": "ESCAPE",
                "name": "Cross tenant department",
                "parent_id": str(DEPARTMENT_B_ID),
            },
        )
        assert cross_parent.status_code == 404
        assert cross_parent.json()["error"]["code"] == "department_not_found"

        denied_read = await harness.client.get(
            "/api/v1/departments/tree",
            headers=_authorization(employee_token),
        )
        assert denied_read.status_code == 403
        assert denied_read.json()["error"]["code"] == "organization_access_denied"
        denied_write = await harness.client.post(
            "/api/v1/departments",
            headers=_authorization(employee_token),
            json={"code": "DENIED", "name": "Denied"},
        )
        assert denied_write.status_code == 403
        assert denied_write.json()["error"]["code"] == "organization_access_denied"

        hr_created = await harness.client.post(
            "/api/v1/departments",
            headers=_authorization(hr_token),
            json={"code": "HR", "name": "HR managed"},
        )
        assert hr_created.status_code == 201

        async with harness.session_factory.begin() as session:
            feature = await session.get(
                TenantFeatureFlag,
                (TENANT_A_ID, FeatureFlagKey.ORGANIZATION.value),
            )
            assert feature is not None
            feature.enabled = False
        disabled = await harness.client.get(
            "/api/v1/departments/tree",
            headers=_authorization(admin_token),
        )
        assert disabled.status_code == 404
        assert disabled.json()["error"]["code"] == "organization_feature_unavailable"

    async with _organization_api() as harness:
        service = DepartmentService(
            session_factory=harness.session_factory,
            audit_recorder_factory=lambda _session: _FailingAuditRecorder(),
        )
        with pytest.raises(RuntimeError, match="forced organization audit failure"):
            await service.create_department(
                request_context=_service_context(),
                payload=DepartmentCreate(code="ROLLBACK-DEPT", name="Must Roll Back"),
                granted_permissions=(
                    ORGANIZATION_READ_PERMISSION,
                    ORGANIZATION_UPDATE_PERMISSION,
                ),
            )

        async with harness.session_factory() as session:
            rolled_back = await session.scalar(
                select(Department.id).where(
                    Department.tenant_id == TENANT_A_ID,
                    Department.code_normalized == "rollback-dept",
                )
            )
            audit_event = await session.scalar(
                select(AuditEvent.id).where(
                    AuditEvent.tenant_id == TENANT_A_ID,
                    AuditEvent.event_type == "department.created",
                )
            )
        assert rolled_back is None
        assert audit_event is None
