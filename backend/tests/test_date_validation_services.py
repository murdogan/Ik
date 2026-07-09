from datetime import date
from typing import cast
from uuid import UUID

import pytest
from app.schemas.employee import EmployeeCreate
from app.schemas.leave_request import LeaveRequestCreate
from app.services.employee_service import EmployeeDateRangeError, EmployeeService
from app.services.leave_request_service import LeaveRequestDateRangeError, LeaveRequestService
from sqlalchemy.ext.asyncio import AsyncSession

TENANT_ID = UUID("11111111-aaaa-4111-8111-111111111111")
EMPLOYEE_ID = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")
USER_ID = UUID("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb")


async def test_employee_service_create_rejects_constructed_invalid_date_range() -> None:
    service = EmployeeService(session=cast(AsyncSession, None))
    payload = EmployeeCreate.model_construct(
        employee_number="WF-001",
        first_name="Ada",
        last_name="Yilmaz",
        employment_start_date=date(2026, 7, 10),
        employment_end_date=date(2026, 7, 1),
    )

    with pytest.raises(EmployeeDateRangeError, match="Employment end date"):
        await service.create_employee(TENANT_ID, payload)


async def test_leave_request_service_create_rejects_constructed_invalid_date_range() -> None:
    service = LeaveRequestService(session=cast(AsyncSession, None))
    payload = LeaveRequestCreate.model_construct(
        employee_id=EMPLOYEE_ID,
        leave_type="annual",
        start_date=date(2026, 7, 22),
        end_date=date(2026, 7, 20),
        requested_by_user_id=USER_ID,
    )

    with pytest.raises(LeaveRequestDateRangeError, match="Leave end date"):
        await service.create_leave_request(TENANT_ID, payload)
