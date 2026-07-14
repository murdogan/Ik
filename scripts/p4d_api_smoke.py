#!/usr/bin/env python3
"""Isolated executable smoke for P4D employee field projections."""

# ruff: noqa: E402

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = ROOT / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from tests._employee_field_policy_support import (
    EMPLOYEE_ID,
    MANAGER_ID,
    MEMBERSHIP_ID,
    RAW_BIRTH_DATE,
    RAW_PHONE,
    UNRELATED_EMPLOYEE_ID,
    USER_ID,
    employee_field_policy_api,
    employee_field_policy_database,
    request_headers,
)


async def main() -> None:
    async with employee_field_policy_database() as database:
        async with employee_field_policy_api(
            database,
            actor_id=MANAGER_ID,
            permissions=("employee:read:tenant", "employee:read:team"),
        ) as hr_client:
            hr = await hr_client.get(
                f"/api/v1/employees/{EMPLOYEE_ID}/profile",
                headers=request_headers("p4d-smoke-hr"),
            )
            assert hr.status_code == 200, hr.text
            assert hr.json()["data"]["personal"] == {
                "preferred_name": "Ada",
                "birth_date": RAW_BIRTH_DATE,
                "phone": RAW_PHONE,
                "version": 1,
            }

            legacy_team = await hr_client.get(
                "/api/v1/teams/me",
                headers=request_headers("p4d-smoke-legacy-team"),
            )
            assert legacy_team.status_code == 200, legacy_team.text
            legacy_items = legacy_team.json()["data"]
            assert len(legacy_items) == 1
            _assert_exact_legacy_team_item(legacy_items[0])

        async with employee_field_policy_api(
            database,
            actor_id=MANAGER_ID,
            permissions=("employee:read:team",),
        ) as manager_client:
            denied_legacy = await manager_client.get(
                "/api/v1/teams/me",
                headers=request_headers("p4d-smoke-legacy-denied"),
            )
            assert denied_legacy.status_code == 403, denied_legacy.text

            team = await manager_client.get(
                "/api/v1/teams/me/members",
                headers=request_headers("p4d-smoke-team"),
            )
            assert team.status_code == 200, team.text
            assert [item["employee"]["id"] for item in team.json()["data"]] == [str(EMPLOYEE_ID)]
            assert "membership_id" not in team.text
            assert "birth_date" not in team.text
            assert "phone" not in team.text

            manager = await manager_client.get(
                f"/api/v1/teams/me/members/{EMPLOYEE_ID}/profile",
                headers=request_headers("p4d-smoke-manager"),
            )
            assert manager.status_code == 200, manager.text
            manager_data = manager.json()["data"]
            assert manager_data["core"]["id"] == str(EMPLOYEE_ID)
            assert manager_data["organization"]["current_assignment"]["manager"] == {
                "full_name": "Mina Manager"
            }
            assert RAW_PHONE not in manager.text
            assert RAW_BIRTH_DATE not in manager.text
            assert "birth_date" not in manager.text
            assert "phone" not in manager.text

            unrelated = await manager_client.get(
                f"/api/v1/teams/me/members/{UNRELATED_EMPLOYEE_ID}/profile",
                headers=request_headers("p4d-smoke-denial"),
            )
            assert unrelated.status_code == 404, unrelated.text
            assert str(UNRELATED_EMPLOYEE_ID) not in unrelated.text

            denied_hr = await manager_client.get(
                f"/api/v1/employees/{EMPLOYEE_ID}/profile",
                headers=request_headers("p4d-smoke-manager-hr"),
            )
            assert denied_hr.status_code == 403, denied_hr.text

        async with employee_field_policy_api(
            database,
            actor_id=USER_ID,
            membership_id=MEMBERSHIP_ID,
            permissions=("employee:read:own",),
        ) as own_client:
            own = await own_client.get(
                "/api/v1/me/employee-profile",
                headers=request_headers("p4d-smoke-own"),
            )
            assert own.status_code == 200, own.text
            own_data = own.json()["data"]
            assert set(own_data) == {
                "availability",
                "membership_id",
                "employee_id",
                "profile",
            }
            assert own_data["membership_id"] == str(MEMBERSHIP_ID)
            assert own_data["employee_id"] == str(EMPLOYEE_ID)
            assert own_data["employee_id"] == own_data["profile"]["core"]["id"]
            assert own_data["profile"]["personal"]["phone"]["visibility"] == "masked"
            assert own_data["profile"]["personal"]["birth_date"]["visibility"] == ("masked")
            assert RAW_PHONE not in own.text
            assert RAW_BIRTH_DATE not in own.text
            assert "membership_id" not in repr(own_data["profile"])

    print("P4D_API_SMOKE_OK")


def _assert_exact_legacy_team_item(item: dict[str, object]) -> None:
    assert set(item) == {"employee", "assignment"}
    employee = item["employee"]
    assignment = item["assignment"]
    assert isinstance(employee, dict)
    assert isinstance(assignment, dict)
    assert set(employee) == {
        "id",
        "employee_number",
        "first_name",
        "last_name",
        "email",
        "status",
    }
    assert set(assignment) == {
        "id",
        "employee",
        "legal_entity",
        "branch",
        "department",
        "position",
        "manager",
        "effective_from",
        "effective_to",
        "supersedes_assignment_id",
        "change_reason",
        "is_current",
        "created_at",
        "updated_at",
    }
    assert assignment["employee"] == employee
    assert set(assignment["legal_entity"]) == {"id", "code", "name", "status"}
    assert set(assignment["branch"]) == {"id", "code", "name", "status"}
    assert set(assignment["department"]) == {"id", "code", "name", "status"}
    assert set(assignment["position"]) == {"id", "code", "title", "status"}
    assert set(assignment["manager"]) == {"id", "full_name", "email", "status"}
    assert employee["id"] == str(EMPLOYEE_ID)


if __name__ == "__main__":
    asyncio.run(main())
