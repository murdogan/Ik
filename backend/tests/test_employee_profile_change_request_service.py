from uuid import uuid4

import pytest
from app.models.employee_profile_change_request import EmployeeProfileChangeRequestStatus
from app.schemas.employee_profile_change_request import (
    EmployeeProfileChangeRequestCreate,
    EmployeeProfileChangeRequestExpectedVersion,
)
from app.services.authorization_service import AuthorizationAccessDeniedError
from app.services.employee_profile_change_request_service import (
    EmployeeProfileChangeRequestService,
)
from tests._employee_profile_change_request_support import (
    MEMBERSHIP_ID,
    TENANT_ID,
    USER_ID,
    employee_profile_change_request_database,
)


async def test_service_own_history_is_masked_deterministic_and_cursor_bounded() -> None:
    async with employee_profile_change_request_database() as database:
        async with database.sessions() as session:
            service = EmployeeProfileChangeRequestService(session)
            async with session.begin():
                first = await service.submit_own(
                    request_id=uuid4(),
                    tenant_id=TENANT_ID,
                    membership_id=MEMBERSHIP_ID,
                    actor_user_id=USER_ID,
                    payload=EmployeeProfileChangeRequestCreate(phone="+905551111111"),
                )
            async with session.begin():
                await service.cancel_own(
                    tenant_id=TENANT_ID,
                    membership_id=MEMBERSHIP_ID,
                    actor_user_id=USER_ID,
                    request_id=first.request_id,
                    payload=EmployeeProfileChangeRequestExpectedVersion(expected_version=1),
                )
            async with session.begin():
                second = await service.submit_own(
                    request_id=uuid4(),
                    tenant_id=TENANT_ID,
                    membership_id=MEMBERSHIP_ID,
                    actor_user_id=USER_ID,
                    payload=EmployeeProfileChangeRequestCreate(phone="+905552222222"),
                )

            page = await service.list_own(
                tenant_id=TENANT_ID,
                membership_id=MEMBERSHIP_ID,
                actor_user_id=USER_ID,
                limit=1,
                cursor=None,
            )
            assert [item.id for item in page.items] == [second.request_id]
            assert page.next_cursor is not None
            assert "+905552222222" not in repr(page.items)
            assert page.items[0].changes.phone is not None
            assert page.items[0].changes.phone.proposed_value.display_value == "••••••••22"

            next_page = await service.list_own(
                tenant_id=TENANT_ID,
                membership_id=MEMBERSHIP_ID,
                actor_user_id=USER_ID,
                limit=1,
                cursor=page.next_cursor,
            )
            assert [item.id for item in next_page.items] == [first.request_id]
            assert next_page.next_cursor is None


async def test_service_hr_reads_fail_closed_without_both_permissions() -> None:
    async with employee_profile_change_request_database() as database:
        async with database.sessions() as session:
            service = EmployeeProfileChangeRequestService(session)
            with pytest.raises(AuthorizationAccessDeniedError):
                await service.list_hr(
                    tenant_id=TENANT_ID,
                    granted_permissions=("employee:read:tenant",),
                    status=EmployeeProfileChangeRequestStatus.SUBMITTED,
                    limit=25,
                    cursor=None,
                )
