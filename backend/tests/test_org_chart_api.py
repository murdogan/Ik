from __future__ import annotations

from datetime import UTC, date, datetime
from uuid import UUID

from app.models.department import Department, DepartmentStatus
from app.models.employee import Employee
from app.models.employee_assignment import EmployeeAssignment
from app.models.tenant import TenantFeatureFlag
from app.models.user import User, UserStatus
from app.modules.core.domain.feature_flags import FeatureFlagKey
from app.platform.pagination import MAX_CURSOR_LENGTH
from app.schemas.org_chart import OrgChartPagination
from app.services.authorization_service import assign_system_role
from app.services.identity_projection_service import sync_identity_membership_projection
from app.services.org_chart_service import OrganizationChartService
from app.services.organization_access import ORGANIZATION_READ_PERMISSION
from sqlalchemy import event
from tests.test_employee_assignment_api import (
    BRANCH_ID,
    DEPARTMENT_ID,
    FREE_TEXT_EMPLOYEE_ID,
    MANAGER_ID,
    OTHER_EMPLOYEE_ID,
    POSITION_ID,
    ROLLBACK_EMPLOYEE_ID,
    TEAM_EMPLOYEE_ID,
    _seed_assignment_fixture,
)
from tests.test_organization_api import (
    ADMIN_A_EMAIL,
    EMPLOYEE_A_EMAIL,
    HR_A_EMAIL,
    HR_A_ID,
    TENANT_A_ID,
    _authorization,
    _login,
    _organization_api,
    _service_context,
)

TEAM_USER_ID = UUID("df000000-0000-4000-8000-000000000001")
TEAM_USER_EMAIL = "ada.team@organization-a.test"
TEAM_ASSIGNMENT_ID = UUID("df100000-0000-4000-8000-000000000001")
FREE_TEXT_ASSIGNMENT_ID = UUID("df100000-0000-4000-8000-000000000002")
ROLLBACK_ASSIGNMENT_ID = UUID("df100000-0000-4000-8000-000000000003")
GRANDCHILD_ASSIGNMENT_ID = UUID("df100000-0000-4000-8000-000000000004")
TODAY = date(2026, 7, 13)


async def _seed_chart_fixture(harness) -> None:
    await _seed_assignment_fixture(harness)
    async with harness.session_factory.begin() as session:
        session.add(
            User(
                id=TEAM_USER_ID,
                tenant_id=TENANT_A_ID,
                email=TEAM_USER_EMAIL,
                full_name="Ada Team",
                status=UserStatus.ACTIVE.value,
            )
        )
        await session.flush()
        await assign_system_role(
            session,
            tenant_id=TENANT_A_ID,
            user_id=TEAM_USER_ID,
            role_code="manager",
        )
        team_user = await session.get(User, TEAM_USER_ID)
        assert team_user is not None
        await sync_identity_membership_projection(session, team_user)
        session.add_all(
            [
                _assignment(
                    TEAM_ASSIGNMENT_ID,
                    employee_id=TEAM_EMPLOYEE_ID,
                    manager_id=MANAGER_ID,
                ),
                _assignment(
                    FREE_TEXT_ASSIGNMENT_ID,
                    employee_id=FREE_TEXT_EMPLOYEE_ID,
                    manager_id=MANAGER_ID,
                ),
                _assignment(
                    ROLLBACK_ASSIGNMENT_ID,
                    employee_id=ROLLBACK_EMPLOYEE_ID,
                    manager_id=MANAGER_ID,
                ),
                _assignment(
                    GRANDCHILD_ASSIGNMENT_ID,
                    employee_id=OTHER_EMPLOYEE_ID,
                    manager_id=TEAM_USER_ID,
                ),
            ]
        )


def _assignment(
    assignment_id: UUID,
    *,
    employee_id: UUID,
    manager_id: UUID,
) -> EmployeeAssignment:
    return EmployeeAssignment(
        id=assignment_id,
        tenant_id=TENANT_A_ID,
        employee_id=employee_id,
        legal_entity_id=TENANT_A_ID,
        branch_id=BRANCH_ID,
        department_id=DEPARTMENT_ID,
        position_id=POSITION_ID,
        manager_user_id=manager_id,
        supersedes_assignment_id=None,
        effective_from=date(2026, 7, 1),
        effective_to=None,
        change_reason="P3J representative hierarchy",
        created_by_user_id=HR_A_ID,
    )


async def test_org_chart_root_parent_and_cursor_pages_are_lazy_and_resolved() -> None:
    async with _organization_api() as harness:
        await _seed_chart_fixture(harness)
        headers = _authorization(await _login(harness.client, email=ADMIN_A_EMAIL))

        roots = await harness.client.get(
            "/api/v1/org-chart",
            headers=headers,
            params={"root": "true", "limit": 1},
        )
        assert roots.status_code == 200
        assert roots.headers["cache-control"] == "no-store"
        assert roots.json()["meta"]["limit"] == 1
        assert roots.json()["meta"]["next_cursor"] is None
        assert [node["full_name"] for node in roots.json()["data"]] == ["Direct Manager"]
        root = roots.json()["data"][0]
        assert root == {
            "id": str(MANAGER_ID),
            "node_type": "manager",
            "employee_id": None,
            "user_id": str(MANAGER_ID),
            "parent_user_id": None,
            "assignment_id": None,
            "full_name": "Direct Manager",
            "email": "manager@organization-a.test",
            "employee_number": None,
            "employee_status": None,
            "user_status": "active",
            "legal_entity": None,
            "branch": None,
            "department": None,
            "position": None,
            "has_children": True,
            "has_archived_reference": False,
        }

        first_children = await harness.client.get(
            "/api/v1/org-chart",
            headers=headers,
            params={"parent_id": str(MANAGER_ID), "limit": 1},
        )
        assert first_children.status_code == 200
        assert [node["employee_number"] for node in first_children.json()["data"]] == [
            "ORG-001"
        ]
        assert first_children.json()["meta"]["next_cursor"]
        ada = first_children.json()["data"][0]
        assert ada["user_id"] == str(TEAM_USER_ID)
        assert ada["has_children"] is True
        assert ada["department"] == {
            "id": str(DEPARTMENT_ID),
            "code": "ENG",
            "name": "Engineering",
            "status": "active",
        }
        assert ada["position"]["title"] == "Backend Engineer"
        assert ada["branch"]["name"] == "Istanbul"

        second_children = await harness.client.get(
            "/api/v1/org-chart",
            headers=headers,
            params={
                "parent_id": str(MANAGER_ID),
                "limit": 1,
                "cursor": first_children.json()["meta"]["next_cursor"],
            },
        )
        assert second_children.status_code == 200
        assert [node["employee_number"] for node in second_children.json()["data"]] == [
            "ORG-003"
        ]
        assert second_children.json()["meta"]["next_cursor"]

        third_children = await harness.client.get(
            "/api/v1/org-chart",
            headers=headers,
            params={
                "parent_id": str(MANAGER_ID),
                "limit": 1,
                "cursor": second_children.json()["meta"]["next_cursor"],
            },
        )
        assert third_children.status_code == 200
        assert [node["employee_number"] for node in third_children.json()["data"]] == [
            "ORG-004"
        ]
        assert third_children.json()["meta"]["next_cursor"] is None

        grandchildren = await harness.client.get(
            "/api/v1/org-chart",
            headers=headers,
            params={"parent": str(TEAM_USER_ID)},
        )
        assert grandchildren.status_code == 200
        assert [node["employee_number"] for node in grandchildren.json()["data"]] == [
            "ORG-002"
        ]
        assert all(node["employee_number"] != "ORG-002" for node in roots.json()["data"])
        assert all(
            node["employee_number"] != "ORG-002"
            for node in first_children.json()["data"]
        )

        mismatched_cursor = await harness.client.get(
            "/api/v1/org-chart",
            headers=headers,
            params={
                "parent_id": str(TEAM_USER_ID),
                "cursor": first_children.json()["meta"]["next_cursor"],
            },
        )
        assert mismatched_cursor.status_code == 422
        assert mismatched_cursor.json()["error"]["code"] == "organization_validation_error"

        for params in (
            {"root": "true", "parent_id": str(MANAGER_ID)},
            {"root": "false"},
            {"offset": "1"},
            {"limit": "101"},
        ):
            invalid = await harness.client.get(
                "/api/v1/org-chart",
                headers=headers,
                params=params,
            )
            assert invalid.status_code == 422
            assert invalid.json()["error"]["code"] == "organization_validation_error"

        async with harness.session_factory.begin() as session:
            department = await session.get(Department, DEPARTMENT_ID)
            assert department is not None
            department.status = DepartmentStatus.ARCHIVED.value
            department.archived_at = datetime(2026, 7, 13, tzinfo=UTC)
        retained_archive = await harness.client.get(
            "/api/v1/org-chart",
            headers=headers,
            params={"parent_id": str(MANAGER_ID), "limit": 1},
        )
        assert retained_archive.json()["data"][0]["department"]["status"] == "archived"
        assert retained_archive.json()["data"][0]["has_archived_reference"] is True


async def test_org_chart_is_tenant_scoped_feature_gated_and_employee_denied() -> None:
    async with _organization_api() as harness:
        await _seed_chart_fixture(harness)
        admin_headers = _authorization(await _login(harness.client, email=ADMIN_A_EMAIL))
        hr_headers = _authorization(await _login(harness.client, email=HR_A_EMAIL))
        employee_headers = _authorization(await _login(harness.client, email=EMPLOYEE_A_EMAIL))

        assert (
            await harness.client.get(
                "/api/v1/org-chart", headers=admin_headers, params={"root": "true"}
            )
        ).status_code == 200
        assert (
            await harness.client.get(
                "/api/v1/org-chart", headers=hr_headers, params={"root": "true"}
            )
        ).status_code == 200

        spoofed = await harness.client.get(
            "/api/v1/org-chart",
            headers={
                **admin_headers,
                "X-Tenant-Id": "c1000000-0000-4000-8000-000000000002",
                "X-Tenant-Slug": "organization-b",
            },
            params={"root": "true"},
        )
        assert spoofed.status_code == 200
        assert [node["full_name"] for node in spoofed.json()["data"]] == ["Direct Manager"]

        unknown_parent = await harness.client.get(
            "/api/v1/org-chart",
            headers=admin_headers,
            params={"parent_id": "c2000000-0000-4000-8000-000000000099"},
        )
        assert unknown_parent.status_code == 200
        assert unknown_parent.json()["data"] == []

        denied = await harness.client.get(
            "/api/v1/org-chart",
            headers=employee_headers,
            params={"root": "true"},
        )
        assert denied.status_code == 403
        assert denied.json()["error"]["code"] == "organization_access_denied"

        async with harness.session_factory.begin() as session:
            feature = await session.get(
                TenantFeatureFlag,
                (TENANT_A_ID, FeatureFlagKey.ORGANIZATION.value),
            )
            assert feature is not None
            feature.enabled = False
        disabled = await harness.client.get(
            "/api/v1/org-chart",
            headers=admin_headers,
            params={"root": "true"},
        )
        assert disabled.status_code == 404
        assert disabled.json()["error"]["code"] == "organization_feature_unavailable"


async def test_org_chart_query_count_is_constant_for_representative_hierarchy() -> None:
    async with _organization_api() as harness:
        await _seed_chart_fixture(harness)
        service = OrganizationChartService(
            session_factory=harness.session_factory,
            today_factory=lambda: TODAY,
        )
        select_count = 0

        def count_selects(_conn, _cursor, statement, _parameters, _context, _many) -> None:
            nonlocal select_count
            if statement.lstrip().upper().startswith("SELECT"):
                select_count += 1

        event.listen(
            harness.runtime.engine.sync_engine,
            "before_cursor_execute",
            count_selects,
        )
        try:
            small = await service.list_level(
                request_context=_service_context(),
                pagination=OrgChartPagination(limit=1, parent_id=MANAGER_ID),
                granted_permissions=(ORGANIZATION_READ_PERMISSION,),
            )
            small_count = select_count
            select_count = 0
            representative = await service.list_level(
                request_context=_service_context(),
                pagination=OrgChartPagination(limit=25, parent_id=MANAGER_ID),
                granted_permissions=(ORGANIZATION_READ_PERMISSION,),
            )
            representative_count = select_count
            select_count = 0
            roots = await service.list_level(
                request_context=_service_context(),
                pagination=OrgChartPagination(limit=25),
                granted_permissions=(ORGANIZATION_READ_PERMISSION,),
            )
            root_count = select_count
        finally:
            event.remove(
                harness.runtime.engine.sync_engine,
                "before_cursor_execute",
                count_selects,
            )

        assert len(small.items) == 1
        assert len(representative.items) == 3
        assert len(roots.items) == 1
        assert small_count == representative_count == 3
        assert root_count == 4
        assert any(node.has_children for node in representative.items)


async def test_org_chart_cursor_ignores_long_unicode_names_and_remains_reusable() -> None:
    async with _organization_api() as harness:
        await _seed_chart_fixture(harness)
        async with harness.session_factory.begin() as session:
            employee = await session.get(Employee, FREE_TEXT_EMPLOYEE_ID)
            assignment = await session.get(EmployeeAssignment, FREE_TEXT_ASSIGNMENT_ID)
            assert employee is not None
            assert assignment is not None
            employee.first_name = "A" + ("界" * 300)
            employee.last_name = "Uzun"
            assignment.manager_user_id = None

        headers = _authorization(await _login(harness.client, email=ADMIN_A_EMAIL))
        cursor = None
        names: list[str] = []
        while True:
            page = await harness.client.get(
                "/api/v1/org-chart",
                headers=headers,
                params={
                    "root": "true",
                    "limit": 1,
                    **({"cursor": cursor} if cursor is not None else {}),
                },
            )
            assert page.status_code == 200
            names.extend(node["full_name"] for node in page.json()["data"])
            cursor = page.json()["meta"]["next_cursor"]
            if cursor is None:
                break
            assert len(cursor) <= MAX_CURSOR_LENGTH

        assert names[0] == "Direct Manager"
        assert names[1].startswith("A" + ("界" * 100))
