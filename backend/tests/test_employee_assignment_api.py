from __future__ import annotations

from collections import Counter
from datetime import UTC, date, datetime
from uuid import UUID

import pytest
from app.models.audit import AuditEvent
from app.models.department import Department, DepartmentStatus
from app.models.employee import Employee, EmployeeStatus
from app.models.employee_assignment import EmployeeAssignment
from app.models.organization import Branch, BranchStatus
from app.models.position import Position, PositionStatus
from app.models.user import User, UserStatus
from app.platform.audit import AuditEventDraft
from app.schemas.employee_assignment import (
    EmployeeAssignmentChange,
    EmployeeAssignmentCreate,
)
from app.services.audit_recorder import SqlAlchemyAuditRecorder
from app.services.authorization_service import assign_system_role
from app.services.employee_assignment_service import (
    EMPLOYEE_ASSIGNMENT_UPDATE_PERMISSION,
    EmployeeAssignmentService,
)
from app.services.identity_projection_service import sync_identity_membership_projection
from sqlalchemy import select
from tests.test_organization_api import (
    DEFAULT_ENTITY_A_ID,
    HR_A_EMAIL,
    TENANT_A_ID,
    _authorization,
    _login,
    _organization_api,
    _service_context,
)

MANAGER_ID = UUID("ce000000-0000-4000-8000-000000000001")
OTHER_MANAGER_ID = UUID("ce000000-0000-4000-8000-000000000002")
MANAGER_EMAIL = "manager@organization-a.test"
OTHER_MANAGER_EMAIL = "other-manager@organization-a.test"
BRANCH_ID = UUID("ce100000-0000-4000-8000-000000000001")
DEPARTMENT_ID = UUID("ce200000-0000-4000-8000-000000000001")
DEPARTMENT_2_ID = UUID("ce200000-0000-4000-8000-000000000002")
POSITION_ID = UUID("ce300000-0000-4000-8000-000000000001")
POSITION_2_ID = UUID("ce300000-0000-4000-8000-000000000002")
ARCHIVED_POSITION_ID = UUID("ce300000-0000-4000-8000-000000000003")
TEAM_EMPLOYEE_ID = UUID("ce400000-0000-4000-8000-000000000001")
OTHER_EMPLOYEE_ID = UUID("ce400000-0000-4000-8000-000000000002")
FREE_TEXT_EMPLOYEE_ID = UUID("ce400000-0000-4000-8000-000000000003")
ROLLBACK_EMPLOYEE_ID = UUID("ce400000-0000-4000-8000-000000000004")


async def _seed_assignment_fixture(harness) -> None:
    async with harness.session_factory.begin() as session:
        hr = await session.scalar(select(User).where(User.email == HR_A_EMAIL))
        assert hr is not None and hr.password_hash is not None
        session.add_all(
            [
                User(
                    id=MANAGER_ID,
                    tenant_id=TENANT_A_ID,
                    email=MANAGER_EMAIL,
                    full_name="Direct Manager",
                    status=UserStatus.ACTIVE.value,
                    password_hash=hr.password_hash,
                ),
                User(
                    id=OTHER_MANAGER_ID,
                    tenant_id=TENANT_A_ID,
                    email=OTHER_MANAGER_EMAIL,
                    full_name="Other Manager",
                    status=UserStatus.ACTIVE.value,
                    password_hash=hr.password_hash,
                ),
                Branch(
                    id=BRANCH_ID,
                    tenant_id=TENANT_A_ID,
                    legal_entity_id=DEFAULT_ENTITY_A_ID,
                    code="IST",
                    name="Istanbul",
                    timezone="Europe/Istanbul",
                    status=BranchStatus.ACTIVE.value,
                    archived_at=None,
                ),
                Department(
                    id=DEPARTMENT_ID,
                    tenant_id=TENANT_A_ID,
                    parent_id=None,
                    code="ENG",
                    name="Engineering",
                    status=DepartmentStatus.ACTIVE.value,
                    archived_at=None,
                ),
                Department(
                    id=DEPARTMENT_2_ID,
                    tenant_id=TENANT_A_ID,
                    parent_id=None,
                    code="PLAT",
                    name="Platform",
                    status=DepartmentStatus.ACTIVE.value,
                    archived_at=None,
                ),
                Position(
                    id=POSITION_ID,
                    tenant_id=TENANT_A_ID,
                    code="BE",
                    title="Backend Engineer",
                    status=PositionStatus.ACTIVE.value,
                    archived_at=None,
                ),
                Position(
                    id=POSITION_2_ID,
                    tenant_id=TENANT_A_ID,
                    code="SBE",
                    title="Senior Backend Engineer",
                    status=PositionStatus.ACTIVE.value,
                    archived_at=None,
                ),
                Position(
                    id=ARCHIVED_POSITION_ID,
                    tenant_id=TENANT_A_ID,
                    code="OLD",
                    title="Archived Role",
                    status=PositionStatus.ARCHIVED.value,
                    archived_at=datetime(2026, 7, 1, tzinfo=UTC),
                ),
                Employee(
                    id=TEAM_EMPLOYEE_ID,
                    tenant_id=TENANT_A_ID,
                    employee_number="ORG-001",
                    first_name="Ada",
                    last_name="Team",
                    email="ada.team@organization-a.test",
                    department="Legacy Engineering",
                    position="Legacy Developer",
                    status=EmployeeStatus.ACTIVE.value,
                    employment_start_date=date(2026, 1, 1),
                ),
                Employee(
                    id=OTHER_EMPLOYEE_ID,
                    tenant_id=TENANT_A_ID,
                    employee_number="ORG-002",
                    first_name="Bora",
                    last_name="Other",
                    email="bora.other@organization-a.test",
                    department="Engineering",
                    position="Backend Engineer",
                    status=EmployeeStatus.ACTIVE.value,
                    employment_start_date=date(2026, 1, 1),
                ),
                Employee(
                    id=FREE_TEXT_EMPLOYEE_ID,
                    tenant_id=TENANT_A_ID,
                    employee_number="ORG-003",
                    first_name="Cem",
                    last_name="Free Text",
                    email="cem.text@organization-a.test",
                    department="Engineering",
                    position="Backend Engineer",
                    status=EmployeeStatus.ACTIVE.value,
                    employment_start_date=date(2026, 1, 1),
                ),
                Employee(
                    id=ROLLBACK_EMPLOYEE_ID,
                    tenant_id=TENANT_A_ID,
                    employee_number="ORG-004",
                    first_name="Derya",
                    last_name="Rollback",
                    email="derya.rollback@organization-a.test",
                    department="Legacy",
                    position="Legacy",
                    status=EmployeeStatus.ACTIVE.value,
                    employment_start_date=date(2026, 1, 1),
                ),
            ]
        )
        await session.flush()
        for manager_id in (MANAGER_ID, OTHER_MANAGER_ID):
            await assign_system_role(
                session,
                tenant_id=TENANT_A_ID,
                user_id=manager_id,
                role_code="manager",
            )
            manager = await session.get(User, manager_id)
            assert manager is not None
            await sync_identity_membership_projection(session, manager)


def _assignment_payload(*, employee_id: UUID, manager_id: UUID) -> dict[str, str]:
    return {
        "employee_id": str(employee_id),
        "legal_entity_id": str(DEFAULT_ENTITY_A_ID),
        "branch_id": str(BRANCH_ID),
        "department_id": str(DEPARTMENT_ID),
        "position_id": str(POSITION_ID),
        "manager_id": str(manager_id),
        "effective_from": "2026-07-01",
        "change_reason": "Initial structured assignment",
    }


async def test_hr_assigns_changes_and_reads_history_while_team_scope_is_derived() -> None:
    async with _organization_api() as harness:
        await _seed_assignment_fixture(harness)
        hr_headers = _authorization(await _login(harness.client, email=HR_A_EMAIL))
        manager_headers = _authorization(await _login(harness.client, email=MANAGER_EMAIL))
        other_manager_headers = _authorization(
            await _login(harness.client, email=OTHER_MANAGER_EMAIL)
        )

        options = await harness.client.get(
            "/api/v1/employee-assignments/options",
            headers=hr_headers,
        )
        assert options.status_code == 200
        assert {item["id"] for item in options.json()["data"]["employees"]} >= {
            str(TEAM_EMPLOYEE_ID),
            str(OTHER_EMPLOYEE_ID),
        }
        assert {item["id"] for item in options.json()["data"]["managers"]} == {
            str(MANAGER_ID),
            str(OTHER_MANAGER_ID),
        }
        searched_options = await harness.client.get(
            "/api/v1/employee-assignments/options",
            headers=hr_headers,
            params={"search": "Ada Team"},
        )
        assert [item["id"] for item in searched_options.json()["data"]["employees"]] == [
            str(TEAM_EMPLOYEE_ID)
        ]
        assert {item["id"] for item in searched_options.json()["data"]["managers"]} == {
            str(MANAGER_ID),
            str(OTHER_MANAGER_ID),
        }

        created = await harness.client.post(
            "/api/v1/employee-assignments",
            headers=hr_headers,
            json=_assignment_payload(
                employee_id=TEAM_EMPLOYEE_ID,
                manager_id=MANAGER_ID,
            ),
        )
        assert created.status_code == 201
        initial = created.json()["data"]
        assert initial["employee"]["id"] == str(TEAM_EMPLOYEE_ID)
        assert initial["department"]["name"] == "Engineering"
        assert initial["position"]["title"] == "Backend Engineer"
        assert initial["manager"]["id"] == str(MANAGER_ID)
        assert initial["is_current"] is True

        other_created = await harness.client.post(
            "/api/v1/employee-assignments",
            headers=hr_headers,
            json=_assignment_payload(
                employee_id=OTHER_EMPLOYEE_ID,
                manager_id=OTHER_MANAGER_ID,
            ),
        )
        assert other_created.status_code == 201

        # Free-text similarity does not grant scope; only current assignment.manager_user_id does.
        team = await harness.client.get("/api/v1/teams/me/members", headers=manager_headers)
        assert team.status_code == 200
        assert [item["employee"]["id"] for item in team.json()["data"]] == [str(TEAM_EMPLOYEE_ID)]
        assert str(FREE_TEXT_EMPLOYEE_ID) not in str(team.json())
        other_team = await harness.client.get(
            "/api/v1/teams/me/members", headers=other_manager_headers
        )
        assert [item["employee"]["id"] for item in other_team.json()["data"]] == [
            str(OTHER_EMPLOYEE_ID)
        ]

        denied = await harness.client.get(
            f"/api/v1/employee-assignments/{initial['id']}",
            headers=other_manager_headers,
        )
        assert denied.status_code == 403
        assert denied.json()["error"]["code"] == "employee_assignment_access_denied"

        changed = await harness.client.patch(
            f"/api/v1/employee-assignments/{initial['id']}",
            headers=hr_headers,
            json={
                "department_id": str(DEPARTMENT_2_ID),
                "position_id": str(POSITION_2_ID),
                "manager_id": str(OTHER_MANAGER_ID),
                "effective_from": "2026-07-13",
                "change_reason": "Platform team transfer",
            },
        )
        assert changed.status_code == 200
        successor = changed.json()["data"]
        assert successor["supersedes_assignment_id"] == initial["id"]
        assert successor["department"]["name"] == "Platform"
        assert successor["manager"]["id"] == str(OTHER_MANAGER_ID)

        history = await harness.client.get(
            "/api/v1/employee-assignments",
            headers=hr_headers,
            params={
                "employee_id": str(TEAM_EMPLOYEE_ID),
                "include_history": "true",
            },
        )
        assert history.status_code == 200
        assert [row["id"] for row in history.json()["data"]] == [
            successor["id"],
            initial["id"],
        ]
        assert history.json()["data"][1]["effective_to"] == "2026-07-13"

        manager_team_after = await harness.client.get(
            "/api/v1/teams/me/members", headers=manager_headers
        )
        assert manager_team_after.json()["data"] == []
        other_team_after = await harness.client.get(
            "/api/v1/teams/me/members", headers=other_manager_headers
        )
        assert {item["employee"]["id"] for item in other_team_after.json()["data"]} == {
            str(TEAM_EMPLOYEE_ID),
            str(OTHER_EMPLOYEE_ID),
        }

        # Structured current names win while the legacy text fields remain available.
        async with harness.session_factory.begin() as session:
            employee = await session.get(Employee, TEAM_EMPLOYEE_ID)
            assert employee is not None
            employee.department = "Stale legacy department"
            employee.position = "Stale legacy position"
        legacy = await harness.client.get(
            f"/api/v1/employees/{TEAM_EMPLOYEE_ID}",
            headers=hr_headers,
        )
        assert legacy.status_code == 200
        assert set(legacy.json()) == {
            "id",
            "employee_number",
            "first_name",
            "last_name",
            "email",
            "department",
            "position",
            "status",
            "employment_start_date",
            "employment_end_date",
            "version",
            "current_assignment",
        }
        assert legacy.json()["department"] == "Platform"
        assert legacy.json()["position"] == "Senior Backend Engineer"
        assert legacy.json()["current_assignment"]["department"]["name"] == "Platform"
        assert legacy.json()["current_assignment"]["position"]["title"] == "Senior Backend Engineer"

        legacy_patch = await harness.client.patch(
            f"/api/v1/employees/{TEAM_EMPLOYEE_ID}",
            headers=hr_headers,
            json={
                "department": "Submitted legacy department",
                "position": "Submitted legacy position",
            },
        )
        assert legacy_patch.status_code == 200
        assert legacy_patch.json()["department"] == "Platform"
        assert legacy_patch.json()["position"] == "Senior Backend Engineer"
        legacy_after_patch = await harness.client.get(
            f"/api/v1/employees/{TEAM_EMPLOYEE_ID}",
            headers=hr_headers,
        )
        assert legacy_after_patch.json() == legacy_patch.json()
        async with harness.session_factory() as session:
            raw_employee = await session.get(Employee, TEAM_EMPLOYEE_ID)
        assert raw_employee is not None
        assert raw_employee.department == "Submitted legacy department"
        assert raw_employee.position == "Submitted legacy position"

        archived_rejected = await harness.client.post(
            "/api/v1/employee-assignments",
            headers=hr_headers,
            json={
                **_assignment_payload(
                    employee_id=FREE_TEXT_EMPLOYEE_ID,
                    manager_id=MANAGER_ID,
                ),
                "position_id": str(ARCHIVED_POSITION_ID),
            },
        )
        assert archived_rejected.status_code == 409
        assert archived_rejected.json()["error"]["code"] == ("employee_assignment_conflict")

        async with harness.session_factory() as session:
            events = tuple(
                await session.scalars(
                    select(AuditEvent).where(
                        AuditEvent.tenant_id == TENANT_A_ID,
                        AuditEvent.event_type.in_(
                            (
                                "employee.assignment.changed",
                                "reporting_line.changed",
                            )
                        ),
                    )
                )
            )
        assert Counter(event.event_type for event in events) == Counter(
            {
                "employee.assignment.changed": 3,
                "reporting_line.changed": 3,
            }
        )


class _FailOnSecondAudit:
    def __init__(self, session) -> None:
        self._delegate = SqlAlchemyAuditRecorder(session)
        self._count = 0

    async def record(self, event: AuditEventDraft) -> None:
        self._count += 1
        if self._count == 2:
            raise RuntimeError("forced reporting-line audit failure")
        await self._delegate.record(event)


async def test_assignment_and_both_audits_roll_back_atomically() -> None:
    async with _organization_api() as harness:
        await _seed_assignment_fixture(harness)
        service = EmployeeAssignmentService(
            session_factory=harness.session_factory,
            audit_recorder_factory=_FailOnSecondAudit,
            today_factory=lambda: date(2026, 7, 13),
        )

        with pytest.raises(RuntimeError, match="forced reporting-line audit failure"):
            await service.create_assignment(
                request_context=_service_context(),
                payload=EmployeeAssignmentCreate.model_validate(
                    _assignment_payload(
                        employee_id=ROLLBACK_EMPLOYEE_ID,
                        manager_id=MANAGER_ID,
                    )
                ),
                granted_permissions=(EMPLOYEE_ASSIGNMENT_UPDATE_PERMISSION,),
            )

        async with harness.session_factory() as session:
            assignment = await session.scalar(
                select(EmployeeAssignment.id).where(
                    EmployeeAssignment.tenant_id == TENANT_A_ID,
                    EmployeeAssignment.employee_id == ROLLBACK_EMPLOYEE_ID,
                )
            )
            events = tuple(
                await session.scalars(
                    select(AuditEvent.id).where(
                        AuditEvent.tenant_id == TENANT_A_ID,
                        AuditEvent.resource_type == "employee_assignment",
                    )
                )
            )
            employee = await session.get(Employee, ROLLBACK_EMPLOYEE_ID)
        assert assignment is None
        assert events == ()
        assert employee is not None
        assert employee.department == "Legacy"
        assert employee.position == "Legacy"


async def test_assignment_change_and_reporting_line_audits_roll_back_atomically() -> None:
    async with _organization_api() as harness:
        await _seed_assignment_fixture(harness)

        def today_factory() -> date:
            return date(2026, 7, 13)

        service = EmployeeAssignmentService(
            session_factory=harness.session_factory,
            today_factory=today_factory,
        )
        initial = await service.create_assignment(
            request_context=_service_context(),
            payload=EmployeeAssignmentCreate.model_validate(
                _assignment_payload(
                    employee_id=ROLLBACK_EMPLOYEE_ID,
                    manager_id=MANAGER_ID,
                )
            ),
            granted_permissions=(EMPLOYEE_ASSIGNMENT_UPDATE_PERMISSION,),
        )

        failing_service = EmployeeAssignmentService(
            session_factory=harness.session_factory,
            audit_recorder_factory=_FailOnSecondAudit,
            today_factory=today_factory,
        )
        with pytest.raises(RuntimeError, match="forced reporting-line audit failure"):
            await failing_service.change_assignment(
                request_context=_service_context(),
                assignment_id=initial.id,
                payload=EmployeeAssignmentChange.model_validate(
                    {
                        "department_id": str(DEPARTMENT_2_ID),
                        "position_id": str(POSITION_2_ID),
                        "manager_id": str(OTHER_MANAGER_ID),
                        "effective_from": "2026-07-13",
                        "change_reason": "Forced rollback transfer",
                    }
                ),
                granted_permissions=(EMPLOYEE_ASSIGNMENT_UPDATE_PERMISSION,),
            )

        async with harness.session_factory() as session:
            assignments = tuple(
                await session.scalars(
                    select(EmployeeAssignment).where(
                        EmployeeAssignment.tenant_id == TENANT_A_ID,
                        EmployeeAssignment.employee_id == ROLLBACK_EMPLOYEE_ID,
                    )
                )
            )
            events = tuple(
                await session.scalars(
                    select(AuditEvent).where(
                        AuditEvent.tenant_id == TENANT_A_ID,
                        AuditEvent.resource_type == "employee_assignment",
                    )
                )
            )
            employee = await session.get(Employee, ROLLBACK_EMPLOYEE_ID)

        assert len(assignments) == 1
        retained = assignments[0]
        assert retained.id == initial.id
        assert retained.effective_to is None
        assert retained.department_id == DEPARTMENT_ID
        assert retained.position_id == POSITION_ID
        assert retained.manager_user_id == MANAGER_ID
        assert Counter(event.event_type for event in events) == Counter(
            {
                "employee.assignment.changed": 1,
                "reporting_line.changed": 1,
            }
        )
        assert employee is not None
        assert employee.department == "Engineering"
        assert employee.position == "Backend Engineer"
