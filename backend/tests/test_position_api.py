from __future__ import annotations

from collections import Counter
from uuid import UUID

import pytest
from app.models.audit import AuditEvent
from app.models.position import Position, PositionStatus
from app.models.tenant import TenantFeatureFlag
from app.modules.core.domain.feature_flags import FeatureFlagKey
from app.schemas.position import PositionCreate, PositionListCursor, PositionListPagination
from app.services.organization_access import (
    ORGANIZATION_READ_PERMISSION,
    ORGANIZATION_UPDATE_PERMISSION,
)
from app.services.position_service import (
    PositionLifecycleConflictError,
    PositionService,
    _position_search_predicate,
)
from sqlalchemy import select
from sqlalchemy.dialects import postgresql
from tests.test_organization_api import (
    ADMIN_A_EMAIL,
    EMPLOYEE_A_EMAIL,
    HR_A_EMAIL,
    TENANT_A_ID,
    TENANT_B_ID,
    _authorization,
    _FailingAuditRecorder,
    _login,
    _organization_api,
    _service_context,
)

POSITION_B_ID = UUID("cd000000-0000-4000-8000-000000000001")


async def _position_audit_events(session_factory) -> tuple[AuditEvent, ...]:
    async with session_factory() as session:
        return tuple(
            await session.scalars(
                select(AuditEvent)
                .where(
                    AuditEvent.tenant_id == TENANT_A_ID,
                    AuditEvent.event_type.in_(
                        (
                            "position.created",
                            "position.updated",
                            "position.archived",
                        )
                    ),
                )
                .order_by(AuditEvent.occurred_at, AuditEvent.id)
            )
        )


async def test_position_catalog_crud_search_keyset_archive_guard_and_audit() -> None:
    async with _organization_api() as harness:
        token = await _login(harness.client, email=ADMIN_A_EMAIL)
        headers = _authorization(token)

        created: dict[str, dict[str, object]] = {}
        for code, title in (
            ("backend", "Backend Engineer"),
            ("hr-spec", "People Specialist"),
            ("ops-lead", "Operations Lead"),
            ("pct", "People 100% Specialist"),
        ):
            response = await harness.client.post(
                "/api/v1/positions",
                headers=headers,
                json={"code": code, "title": title},
            )
            assert response.status_code == 201
            item = response.json()["data"]
            assert item["code"] == code.upper()
            assert item["title"] == title
            assert item["status"] == "active"
            assert item["archived_at"] is None
            assert item["accepts_new_assignments"] is True
            assert set(item) == {
                "id",
                "code",
                "title",
                "status",
                "archived_at",
                "accepts_new_assignments",
                "created_at",
                "updated_at",
            }
            created[item["code"]] = item

        first_page = await harness.client.get(
            "/api/v1/positions",
            headers=headers,
            params={"limit": 2, "status": "active"},
        )
        assert first_page.status_code == 200
        assert first_page.headers["Cache-Control"] == "no-store"
        assert [item["code"] for item in first_page.json()["data"]] == [
            "BACKEND",
            "HR-SPEC",
        ]
        assert first_page.json()["meta"]["limit"] == 2
        cursor = first_page.json()["meta"]["next_cursor"]
        assert cursor

        second_page = await harness.client.get(
            "/api/v1/positions",
            headers=headers,
            params={"limit": 2, "status": "active", "cursor": cursor},
        )
        assert second_page.status_code == 200
        assert [item["code"] for item in second_page.json()["data"]] == [
            "OPS-LEAD",
            "PCT",
        ]
        assert second_page.json()["meta"]["next_cursor"] is None

        title_search = await harness.client.get(
            "/api/v1/positions",
            headers=headers,
            params={"search": "PEOPLE"},
        )
        assert title_search.status_code == 200
        assert [item["code"] for item in title_search.json()["data"]] == [
            "HR-SPEC",
            "PCT",
        ]

        code_search = await harness.client.get(
            "/api/v1/positions",
            headers=headers,
            params={"search": "OPS"},
        )
        assert code_search.status_code == 200
        assert [item["code"] for item in code_search.json()["data"]] == ["OPS-LEAD"]

        literal_wildcard = await harness.client.get(
            "/api/v1/positions",
            headers=headers,
            params={"search": "100%"},
        )
        assert literal_wildcard.status_code == 200
        assert [item["code"] for item in literal_wildcard.json()["data"]] == ["PCT"]

        filtered_first = await harness.client.get(
            "/api/v1/positions",
            headers=headers,
            params={"search": "people", "status": "active", "limit": 1},
        )
        assert filtered_first.status_code == 200
        filtered_cursor = filtered_first.json()["meta"]["next_cursor"]
        assert filtered_cursor
        for params in (
            {"search": "operations", "status": "active", "cursor": filtered_cursor},
            {"search": "people", "status": "archived", "cursor": filtered_cursor},
        ):
            mismatched = await harness.client.get(
                "/api/v1/positions",
                headers=headers,
                params=params,
            )
            assert mismatched.status_code == 422
            assert mismatched.json()["error"]["code"] == "organization_validation_error"

        for path in (
            "/api/v1/positions?limit=101",
            "/api/v1/positions?offset=1",
            "/api/v1/positions?status=unknown",
            "/api/v1/positions?search=---",
            f"/api/v1/positions?search={'x' * 101}",
        ):
            invalid = await harness.client.get(path, headers=headers)
            assert invalid.status_code == 422
            assert invalid.json()["error"]["code"] == "organization_validation_error"

        backend_id = UUID(str(created["BACKEND"]["id"]))
        detail = await harness.client.get(
            f"/api/v1/positions/{backend_id}",
            headers=headers,
        )
        assert detail.status_code == 200
        assert detail.json()["data"] == created["BACKEND"]

        service = PositionService(session_factory=harness.session_factory)
        assignable = await service.require_assignable_position(
            request_context=_service_context(),
            position_id=backend_id,
            granted_permissions=(ORGANIZATION_READ_PERMISSION,),
        )
        assert assignable.id == backend_id

        immutable_code = await harness.client.patch(
            f"/api/v1/positions/{backend_id}",
            headers=headers,
            json={"code": "BACKEND-NEW"},
        )
        assert immutable_code.status_code == 422
        assert immutable_code.json()["error"]["code"] == "organization_validation_error"

        updated = await harness.client.patch(
            f"/api/v1/positions/{backend_id}",
            headers=headers,
            json={"title": "Senior Backend Engineer"},
        )
        assert updated.status_code == 200
        assert updated.json()["data"]["title"] == "Senior Backend Engineer"
        assert updated.json()["data"]["code"] == "BACKEND"

        archived = await harness.client.delete(
            f"/api/v1/positions/{backend_id}",
            headers=headers,
        )
        assert archived.status_code == 200
        archived_item = archived.json()["data"]
        assert archived_item["status"] == "archived"
        assert archived_item["archived_at"] is not None
        assert archived_item["accepts_new_assignments"] is False

        archived_again = await harness.client.delete(
            f"/api/v1/positions/{backend_id}",
            headers=headers,
        )
        assert archived_again.status_code == 200
        assert archived_again.json()["data"] == archived_item

        historical = await harness.client.get(
            f"/api/v1/positions/{backend_id}",
            headers=headers,
        )
        assert historical.status_code == 200
        assert historical.json()["data"] == archived_item

        archived_list = await harness.client.get(
            "/api/v1/positions",
            headers=headers,
            params={"status": "archived", "search": "backend"},
        )
        assert archived_list.status_code == 200
        assert [item["id"] for item in archived_list.json()["data"]] == [str(backend_id)]

        active_search = await harness.client.get(
            "/api/v1/positions",
            headers=headers,
            params={"status": "active", "search": "backend"},
        )
        assert active_search.status_code == 200
        assert active_search.json()["data"] == []

        archived_update = await harness.client.patch(
            f"/api/v1/positions/{backend_id}",
            headers=headers,
            json={"title": "Reopened Backend Engineer"},
        )
        assert archived_update.status_code == 409
        assert archived_update.json()["error"]["code"] == "organization_conflict"

        with pytest.raises(PositionLifecycleConflictError):
            await service.require_assignable_position(
                request_context=_service_context(),
                position_id=backend_id,
                granted_permissions=(ORGANIZATION_READ_PERMISSION,),
            )

        duplicate = await harness.client.post(
            "/api/v1/positions",
            headers=headers,
            json={"code": "backend", "title": "Replacement Backend Engineer"},
        )
        assert duplicate.status_code == 409
        assert duplicate.json()["error"]["code"] == "position_code_conflict"

        events = await _position_audit_events(harness.session_factory)
        assert Counter(event.event_type for event in events) == Counter(
            {
                "position.created": 4,
                "position.updated": 1,
                "position.archived": 1,
            }
        )
        assert all(event.resource_type == "position" for event in events)
        assert all(event.category == "hr_operations" for event in events)
        archived_event = next(event for event in events if event.event_type == "position.archived")
        assert archived_event.resource_id == backend_id
        assert archived_event.changed_fields == ["archived_at", "status"]
        assert archived_event.metadata_ == {
            "after_status": "archived",
            "before_status": "active",
        }


async def test_position_tenant_rbac_and_feature_boundaries() -> None:
    async with _organization_api() as harness:
        async with harness.session_factory.begin() as session:
            session.add(
                Position(
                    id=POSITION_B_ID,
                    tenant_id=TENANT_B_ID,
                    code="B-ONLY",
                    title="Tenant B Position",
                    status=PositionStatus.ACTIVE.value,
                    archived_at=None,
                )
            )

        admin_token = await _login(harness.client, email=ADMIN_A_EMAIL)
        employee_token = await _login(harness.client, email=EMPLOYEE_A_EMAIL)
        hr_token = await _login(harness.client, email=HR_A_EMAIL)

        spoofed = await harness.client.get(
            "/api/v1/positions",
            headers={
                **_authorization(admin_token),
                "X-Tenant-Id": str(TENANT_B_ID),
                "X-Tenant-Slug": "organization-b",
            },
        )
        assert spoofed.status_code == 200
        assert spoofed.json()["data"] == []

        cross_tenant = await harness.client.get(
            f"/api/v1/positions/{POSITION_B_ID}",
            headers=_authorization(admin_token),
        )
        assert cross_tenant.status_code == 404
        assert cross_tenant.json()["error"]["code"] == "position_not_found"

        denied_read = await harness.client.get(
            "/api/v1/positions",
            headers=_authorization(employee_token),
        )
        assert denied_read.status_code == 403
        assert denied_read.json()["error"]["code"] == "organization_access_denied"

        denied_write = await harness.client.post(
            "/api/v1/positions",
            headers=_authorization(employee_token),
            json={"code": "DENIED", "title": "Denied Position"},
        )
        assert denied_write.status_code == 403
        assert denied_write.json()["error"]["code"] == "organization_access_denied"

        hr_created = await harness.client.post(
            "/api/v1/positions",
            headers=_authorization(hr_token),
            json={"code": "HR-MANAGED", "title": "HR Managed Position"},
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
            "/api/v1/positions",
            headers=_authorization(admin_token),
        )
        assert disabled.status_code == 404
        assert disabled.json()["error"]["code"] == "organization_feature_unavailable"

        async with harness.session_factory() as session:
            tenant_b_position = await session.get(Position, POSITION_B_ID)
            assert tenant_b_position is not None
        assert tenant_b_position.title == "Tenant B Position"


async def test_position_search_uses_database_normalization_and_unicode_safe_cursor() -> None:
    async with _organization_api() as harness:
        token = await _login(harness.client, email=ADMIN_A_EMAIL)
        headers = _authorization(token)

        created = await harness.client.post(
            "/api/v1/positions",
            headers=headers,
            json={"code": "IK-UZMANI", "title": "İnsan Kaynakları Uzmanı"},
        )
        assert created.status_code == 201

        for code, title in (("i", "Single I"), ("ik", "IK Business Partner")):
            short_code = await harness.client.post(
                "/api/v1/positions",
                headers=headers,
                json={"code": code, "title": title},
            )
            assert short_code.status_code == 201

            exact_short_code_search = await harness.client.get(
                "/api/v1/positions",
                headers=headers,
                params={"search": code},
            )
            assert exact_short_code_search.status_code == 200
            assert [item["code"] for item in exact_short_code_search.json()["data"]] == [
                code.upper()
            ]

        exact_code_predicate = _position_search_predicate("i").compile(
            dialect=postgresql.dialect()
        )
        assert set(exact_code_predicate.params.values()) == {"I"}
        contains_predicate = _position_search_predicate("ikman").compile(
            dialect=postgresql.dialect()
        )
        assert set(contains_predicate.params.values()) == {"%IKMAN%", "%ikman%"}

        searched = await harness.client.get(
            "/api/v1/positions",
            headers=headers,
            params={"search": "İNSAN"},
        )
        assert searched.status_code == 200
        assert [item["code"] for item in searched.json()["data"]] == ["IK-UZMANI"]

        expanding_unicode_search = "İ" * 100
        pagination = PositionListPagination(search=expanding_unicode_search)
        cursor = pagination.next_cursor(
            code="ik-uzmani",
            position_id=UUID(created.json()["data"]["id"]),
        )
        assert PositionListCursor.from_token(cursor).search == expanding_unicode_search

        turkish_collation_code = PositionListCursor(
            code="ık-uzmanı",
            id=UUID(created.json()["data"]["id"]),
        )
        assert PositionListCursor.from_token(
            turkish_collation_code.to_token()
        ).code == "ık-uzmanı"


async def test_position_write_rolls_back_when_audit_fails() -> None:
    async with _organization_api() as harness:
        service = PositionService(
            session_factory=harness.session_factory,
            audit_recorder_factory=lambda _session: _FailingAuditRecorder(),
        )

        with pytest.raises(RuntimeError, match="forced organization audit failure"):
            await service.create_position(
                request_context=_service_context(),
                payload=PositionCreate(code="ROLLBACK-POS", title="Must Roll Back"),
                granted_permissions=(
                    ORGANIZATION_READ_PERMISSION,
                    ORGANIZATION_UPDATE_PERMISSION,
                ),
            )

        async with harness.session_factory() as session:
            rolled_back = await session.scalar(
                select(Position.id).where(
                    Position.tenant_id == TENANT_A_ID,
                    Position.code_normalized == "rollback-pos",
                )
            )
            audit_event = await session.scalar(
                select(AuditEvent.id).where(
                    AuditEvent.tenant_id == TENANT_A_ID,
                    AuditEvent.event_type == "position.created",
                )
            )
        assert rolled_back is None
        assert audit_event is None
