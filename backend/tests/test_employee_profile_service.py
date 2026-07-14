from datetime import date
from uuid import UUID

import pytest
from app.models.employee_assignment import EmployeeAssignment
from app.services.employee_profile_service import (
    EmployeeProfileNotFoundError,
    EmployeeProfileService,
)
from sqlalchemy import event
from tests._employee_profile_support import (
    BRANCH_ID,
    CURRENT_ASSIGNMENT_ID,
    DEPARTMENT_ID,
    EMPLOYEE_ID,
    HISTORICAL_ASSIGNMENT_ID,
    LEGAL_ENTITY_ID,
    OTHER_EMPLOYEE_ID,
    POSITION_ID,
    TENANT_ID,
    employee_profile_database,
)


async def test_employee_profile_read_aggregates_profiles_and_phase3_history_boundedly() -> None:
    async with employee_profile_database() as database:
        async with database.sessions() as session:
            current_assignment = await session.get(
                EmployeeAssignment,
                CURRENT_ASSIGNMENT_ID,
            )
            assert current_assignment is not None
            current_assignment.effective_to = date(2026, 8, 1)
            session.add(
                EmployeeAssignment(
                    id=UUID("d1000000-0000-4000-8000-000000000003"),
                    tenant_id=TENANT_ID,
                    employee_id=EMPLOYEE_ID,
                    legal_entity_id=LEGAL_ENTITY_ID,
                    branch_id=BRANCH_ID,
                    department_id=DEPARTMENT_ID,
                    position_id=POSITION_ID,
                    manager_user_id=None,
                    supersedes_assignment_id=CURRENT_ASSIGNMENT_ID,
                    effective_from=date(2026, 8, 1),
                    effective_to=None,
                    change_reason="Scheduled transfer",
                    created_by_user_id=None,
                )
            )
            await session.commit()

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
            async with database.sessions() as session:
                result = await EmployeeProfileService(
                    session,
                    today=date(2026, 7, 14),
                ).get_employee_profile(TENANT_ID, EMPLOYEE_ID)
        finally:
            event.remove(
                database.engine.sync_engine,
                "before_cursor_execute",
                capture_statement,
            )

    assert result.core.id == EMPLOYEE_ID
    assert result.personal.preferred_name == "Ada"
    assert result.employment.employment_start_date == date(2026, 7, 1)
    assert result.organization.current_assignment is not None
    assert result.organization.current_assignment.id == CURRENT_ASSIGNMENT_ID
    assert [row.id for row in result.organization.history] == [
        CURRENT_ASSIGNMENT_ID,
        HISTORICAL_ASSIGNMENT_ID,
    ]
    assert result.organization.history_limit == 50
    assert result.organization.history_truncated is False
    assert len(statements) <= 4
    assert len(statements) >= 1


async def test_employee_profile_service_does_not_leak_cross_tenant_existence() -> None:
    missing_id = UUID("ffffffff-ffff-4fff-8fff-ffffffffffff")
    async with employee_profile_database() as database:
        async with database.sessions() as session:
            service = EmployeeProfileService(session, today=date(2026, 7, 14))
            with pytest.raises(EmployeeProfileNotFoundError):
                await service.get_employee_profile(TENANT_ID, OTHER_EMPLOYEE_ID)
            with pytest.raises(EmployeeProfileNotFoundError):
                await service.get_employee_profile(TENANT_ID, missing_id)
