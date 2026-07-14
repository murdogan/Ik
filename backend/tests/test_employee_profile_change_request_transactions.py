from unittest.mock import AsyncMock, patch
from uuid import UUID

from app.models.employee_profile import EmployeePersonalProfile
from app.models.employee_profile_change_request import EmployeeProfileChangeRequest
from app.services.audit_recorder import SqlAlchemyAuditRecorder
from sqlalchemy import func, select
from tests._employee_profile_change_request_support import (
    EMPLOYEE_ID,
    employee_profile_change_request_api,
    tenant_headers,
)


async def test_submit_rolls_back_when_audit_recording_fails() -> None:
    async with employee_profile_change_request_api(
        raise_app_exceptions=False,
    ) as (client, database):
        with patch.object(
            SqlAlchemyAuditRecorder,
            "record",
            new=AsyncMock(side_effect=RuntimeError("forced audit failure")),
        ):
            response = await client.post(
                "/api/v1/me/profile-change-requests",
                headers=tenant_headers(),
                json={"preferred_name": "Rollback Sentinel"},
            )

        async with database.sessions() as session:
            request_count = await session.scalar(
                select(func.count()).select_from(EmployeeProfileChangeRequest)
            )
            profile = await session.scalar(
                select(EmployeePersonalProfile).where(
                    EmployeePersonalProfile.employee_id == EMPLOYEE_ID
                )
            )

    assert response.status_code == 500
    assert response.json()["error"]["code"] == "application_command_failed"
    assert "Rollback Sentinel" not in response.text
    assert request_count == 0
    assert profile is not None
    assert (profile.preferred_name, profile.version) == ("Ada", 1)


async def test_approval_profile_and_request_roll_back_when_audit_fails() -> None:
    async with employee_profile_change_request_api(
        raise_app_exceptions=False,
    ) as (client, database):
        submitted = await client.post(
            "/api/v1/me/profile-change-requests",
            headers=tenant_headers(),
            json={"preferred_name": "Approval Rollback Sentinel"},
        )
        assert submitted.status_code == 201
        request_id = submitted.json()["data"]["id"]

        with patch.object(
            SqlAlchemyAuditRecorder,
            "record",
            new=AsyncMock(side_effect=RuntimeError("forced audit failure")),
        ):
            approved = await client.post(
                f"/api/v1/employee-profile-change-requests/{request_id}/approve",
                headers=tenant_headers(),
                json={"expected_version": 1},
            )

        async with database.sessions() as session:
            profile = await session.scalar(
                select(EmployeePersonalProfile).where(
                    EmployeePersonalProfile.employee_id == EMPLOYEE_ID
                )
            )
            request = await session.get(EmployeeProfileChangeRequest, UUID(request_id))

    assert approved.status_code == 500
    assert approved.json()["error"]["code"] == "application_command_failed"
    assert profile is not None
    assert (profile.preferred_name, profile.version) == ("Ada", 1)
    assert request is not None
    assert (request.status, request.version, request.decided_at) == (
        "submitted",
        1,
        None,
    )
