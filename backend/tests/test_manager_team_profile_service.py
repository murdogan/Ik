from __future__ import annotations

import pytest
from app.schemas.employee_assignment import TeamListPagination
from app.services.employee_assignment_service import (
    EmployeeAssignmentAccessDeniedError,
    EmployeeAssignmentNotFoundError,
    EmployeeAssignmentService,
)
from sqlalchemy import event
from tests._employee_field_policy_support import (
    ARCHIVED_EMPLOYEE_ID,
    EMPLOYEE_ID,
    FORMER_EMPLOYEE_ID,
    FUTURE_EMPLOYEE_ID,
    GUESSED_EMPLOYEE_ID,
    INDIRECT_EMPLOYEE_ID,
    OTHER_EMPLOYEE_ID,
    TODAY,
    UNRELATED_EMPLOYEE_ID,
    employee_field_policy_database,
    manager_request_context,
)

TEAM_PERMISSION = ("employee:read:team",)


async def test_manager_profile_is_one_bounded_work_safe_query_with_no_history_n_plus_one() -> None:
    async with employee_field_policy_database() as database:
        statements: list[str] = []

        def capture_statement(
            _connection: object,
            _cursor: object,
            statement: str,
            _parameters: object,
            _context: object,
            _executemany: bool,
        ) -> None:
            statements.append(statement)

        event.listen(database.engine.sync_engine, "before_cursor_execute", capture_statement)
        try:
            service = EmployeeAssignmentService(
                session_factory=database.sessions,
                today_factory=lambda: TODAY,
            )
            profile = await service.manager_team_member_profile(
                request_context=manager_request_context(),
                employee_id=EMPLOYEE_ID,
                granted_permissions=TEAM_PERMISSION,
            )
        finally:
            event.remove(
                database.engine.sync_engine,
                "before_cursor_execute",
                capture_statement,
            )

    assert profile.model_dump(mode="json") == {
        "core": {
            "id": str(EMPLOYEE_ID),
            "employee_number": "WF-001",
            "first_name": "Ada",
            "last_name": "Yilmaz",
            "preferred_name": "Ada",
            "email": "ada@example.test",
            "status": "active",
        },
        "employment": {
            "employment_start_date": "2026-07-01",
            "contract_type": "indefinite",
            "work_type": "full_time",
        },
        "organization": {
            "current_assignment": {
                "legal_entity": {"code": "WF", "name": "Wealthy Falcon"},
                "branch": {"code": "IST", "name": "Istanbul"},
                "department": {"code": "ENG", "name": "Engineering"},
                "position": {"code": "BE", "title": "Backend Engineer"},
                "effective_from": "2026-07-01",
                "manager": {"full_name": "Mina Manager"},
            }
        },
    }

    selects = [
        statement for statement in statements if statement.lstrip().upper().startswith("SELECT")
    ]
    # Two constant tenant/feature reads plus one joined candidate projection. The 55 retained
    # assignment-history rows in the fixture must not add queries or response rows.
    assert len(selects) == 3
    profile_selects = [
        statement for statement in selects if "employee_assignments" in statement.lower()
    ]
    assert len(profile_selects) == 1
    profile_sql = profile_selects[0].lower()
    assert "employee_assignments.manager_user_id" in profile_sql
    assert "employee_assignments.effective_from" in profile_sql
    assert "employee_assignments.effective_to" in profile_sql
    assert "employees.archived_at" in profile_sql
    assert "employees.id" in profile_sql
    assert " limit " in f" {profile_sql.replace(chr(10), ' ')} "
    assert "employee_profiles.phone" not in profile_sql
    assert "employee_profiles.birth_date" not in profile_sql


@pytest.mark.parametrize(
    "candidate_id",
    [
        UNRELATED_EMPLOYEE_ID,
        FORMER_EMPLOYEE_ID,
        FUTURE_EMPLOYEE_ID,
        ARCHIVED_EMPLOYEE_ID,
        INDIRECT_EMPLOYEE_ID,
        OTHER_EMPLOYEE_ID,
        GUESSED_EMPLOYEE_ID,
    ],
)
async def test_manager_profile_scope_is_current_direct_only_and_fails_closed(
    candidate_id,
) -> None:
    async with employee_field_policy_database() as database:
        service = EmployeeAssignmentService(
            session_factory=database.sessions,
            today_factory=lambda: TODAY,
        )
        with pytest.raises(EmployeeAssignmentNotFoundError):
            await service.manager_team_member_profile(
                request_context=manager_request_context(),
                employee_id=candidate_id,
                granted_permissions=TEAM_PERMISSION,
            )


async def test_manager_list_and_profile_require_team_permission_at_service_boundary() -> None:
    async with employee_field_policy_database() as database:
        service = EmployeeAssignmentService(
            session_factory=database.sessions,
            today_factory=lambda: TODAY,
        )
        with pytest.raises(EmployeeAssignmentAccessDeniedError):
            await service.manager_team_member_profile(
                request_context=manager_request_context(),
                employee_id=EMPLOYEE_ID,
                granted_permissions=("employee:read:own",),
            )
        with pytest.raises(EmployeeAssignmentAccessDeniedError):
            await service.my_team(
                request_context=manager_request_context(),
                pagination=TeamListPagination(),
                granted_permissions=("employee:read:own",),
            )
