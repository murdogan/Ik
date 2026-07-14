#!/usr/bin/env python3
"""Isolated P4E employee-submit and HR-decision API smoke."""

# ruff: noqa: E402

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from uuid import UUID

ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = ROOT / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.models.employee_profile import EmployeePersonalProfile
from app.models.employee_profile_change_request import EmployeeProfileChangeRequest
from sqlalchemy import select
from tests._employee_profile_change_request_support import (
    EMPLOYEE_ID,
    employee_profile_change_request_api,
    tenant_headers,
)
from tests._employee_profile_support import EmployeeProfileDatabase


async def main() -> None:
    async with employee_profile_change_request_api() as (client, database):
        before = await _profile(database)
        assert before == ("Ada", "+90 555 000 0000", 1)

        submitted = await client.post(
            "/api/v1/me/profile-change-requests",
            headers=tenant_headers(),
            json={"preferred_name": "Ada Deniz", "phone": "+90 555 123 4567"},
        )
        assert submitted.status_code == 201, submitted.text
        request_id = submitted.json()["data"]["id"]
        assert "+905551234567" not in submitted.text
        assert await _profile(database) == before

        queue = await client.get(
            "/api/v1/employee-profile-change-requests",
            headers=tenant_headers(),
        )
        assert queue.status_code == 200, queue.text
        assert [row["id"] for row in queue.json()["data"]] == [request_id]
        assert "changes" not in queue.json()["data"][0]
        assert "Ada Deniz" not in queue.text

        detail = await client.get(
            f"/api/v1/employee-profile-change-requests/{request_id}",
            headers=tenant_headers(),
        )
        assert detail.status_code == 200, detail.text
        assert detail.json()["data"]["changes"]["phone"]["proposed_value"] == ("+905551234567")

        approved = await client.post(
            f"/api/v1/employee-profile-change-requests/{request_id}/approve",
            headers=tenant_headers(),
            json={"expected_version": 1},
        )
        assert approved.status_code == 200, approved.text
        assert approved.json()["data"]["status"] == "approved"
        assert await _profile(database) == ("Ada Deniz", "+905551234567", 2)

        loser = await client.post(
            f"/api/v1/employee-profile-change-requests/{request_id}/approve",
            headers=tenant_headers(),
            json={"expected_version": 1},
        )
        assert loser.status_code == 409, loser.text
        assert await _profile(database) == ("Ada Deniz", "+905551234567", 2)

        cancelled_request = await client.post(
            "/api/v1/me/profile-change-requests",
            headers=tenant_headers(),
            json={"phone": None},
        )
        assert cancelled_request.status_code == 201, cancelled_request.text
        cancelled = await client.post(
            f"/api/v1/me/profile-change-requests/{cancelled_request.json()['data']['id']}/cancel",
            headers=tenant_headers(),
            json={"expected_version": 1},
        )
        assert cancelled.status_code == 200, cancelled.text
        assert await _profile(database) == ("Ada Deniz", "+905551234567", 2)

        rejected_request = await client.post(
            "/api/v1/me/profile-change-requests",
            headers=tenant_headers(),
            json={"birth_date": "1990-01-02"},
        )
        assert rejected_request.status_code == 201, rejected_request.text
        rejected = await client.post(
            f"/api/v1/employee-profile-change-requests/"
            f"{rejected_request.json()['data']['id']}/reject",
            headers=tenant_headers(),
            json={"expected_version": 1, "reason": "Belge gerekli"},
        )
        assert rejected.status_code == 200, rejected.text
        assert rejected.json()["data"]["status"] == "rejected"
        assert await _profile(database) == ("Ada Deniz", "+905551234567", 2)

        stale_request = await client.post(
            "/api/v1/me/profile-change-requests",
            headers=tenant_headers(),
            json={"phone": "+905559999999"},
        )
        assert stale_request.status_code == 201, stale_request.text
        async with database.sessions() as session:
            profile = await session.scalar(
                select(EmployeePersonalProfile).where(
                    EmployeePersonalProfile.employee_id == EMPLOYEE_ID
                )
            )
            assert profile is not None
            profile.preferred_name = "HR concurrent edit"
            profile.version += 1
            await session.commit()
        stale_id = stale_request.json()["data"]["id"]
        stale = await client.post(
            f"/api/v1/employee-profile-change-requests/{stale_id}/approve",
            headers=tenant_headers(),
            json={"expected_version": 1},
        )
        assert stale.status_code == 409, stale.text
        assert stale.json()["error"]["code"] == ("employee_profile_change_request_stale_profile")
        async with database.sessions() as session:
            row = await session.scalar(
                select(EmployeeProfileChangeRequest).where(
                    EmployeeProfileChangeRequest.id == UUID(stale_id)
                )
            )
            assert row is not None and row.status == "submitted"
        assert await _profile(database) == ("HR concurrent edit", "+905551234567", 3)

    print("P4E_API_SMOKE_OK")


async def _profile(database: EmployeeProfileDatabase) -> tuple[str | None, str | None, int]:
    async with database.sessions() as session:
        profile = await session.scalar(
            select(EmployeePersonalProfile).where(
                EmployeePersonalProfile.employee_id == EMPLOYEE_ID
            )
        )
        assert profile is not None
        return profile.preferred_name, profile.phone, profile.version


if __name__ == "__main__":
    asyncio.run(main())
