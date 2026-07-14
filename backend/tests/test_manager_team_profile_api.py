from __future__ import annotations

import logging
from collections.abc import Mapping, Sequence

import pytest
from app.main import create_app
from app.models.audit import AuditEvent
from app.services.employee_field_policy import RESTRICTED_FUTURE_FIELD_NAMES
from sqlalchemy import func, select
from tests._employee_field_policy_support import (
    ARCHIVED_EMPLOYEE_ID,
    EMPLOYEE_ID,
    FORMER_EMPLOYEE_ID,
    FUTURE_EMPLOYEE_ID,
    GUESSED_EMPLOYEE_ID,
    INDIRECT_EMPLOYEE_ID,
    MANAGER_ID,
    MEMBERSHIP_ID,
    OTHER_EMPLOYEE_ID,
    RAW_BIRTH_DATE,
    RAW_PHONE,
    RESTRICTED_QUERY_VALUE,
    UNRELATED_EMPLOYEE_ID,
    USER_ID,
    employee_field_policy_api,
    employee_field_policy_database,
    request_headers,
)

TEAM_PROFILE_PATH = f"/api/v1/teams/me/members/{EMPLOYEE_ID}/profile"

MANAGER_FORBIDDEN_KEYS = frozenset(
    {
        "phone",
        "birth_date",
        "version",
        "employee_version",
        "tenant_id",
        "membership_id",
        "identity_id",
        "legacy_user_id",
        "manager_user_id",
        "manager_id",
        "history",
        "history_limit",
        "history_truncated",
        "audit",
        "change_reason",
        "supersedes_assignment_id",
        "created_at",
        "updated_at",
        "national_identifier",
        "passport",
        "bank_account",
        "iban",
        "compensation",
        "payroll",
        "health",
        "private_address",
        "emergency_contact",
        "special_category",
        "tckn",
    }
)

RESTRICTED_INPUTS = {
    field_name.removeprefix("restricted."): f"{RESTRICTED_QUERY_VALUE}-{index}"
    for index, field_name in enumerate(sorted(RESTRICTED_FUTURE_FIELD_NAMES), start=1)
}


def test_openapi_registers_one_manager_profile_without_scope_or_unmask_inputs() -> None:
    paths = create_app().openapi()["paths"]
    operation = paths["/api/v1/teams/me/members/{employee_id}/profile"]["get"]

    assert set(paths["/api/v1/teams/me/members/{employee_id}/profile"]) == {"get"}
    assert {
        (parameter["in"], parameter["name"]) for parameter in operation.get("parameters", [])
    } == {("path", "employee_id")}
    assert all(
        forbidden not in path.lower() for path in paths for forbidden in ("unmask", "reveal")
    )
    own_parameters = paths["/api/v1/me/employee-profile"]["get"].get("parameters", [])
    assert all(parameter["name"] != "employee_id" for parameter in own_parameters)


async def test_hr_manager_and_linked_employee_receive_distinct_server_projections() -> None:
    async with employee_field_policy_database() as database:
        async with employee_field_policy_api(
            database,
            actor_id=MANAGER_ID,
            permissions=("employee:read:tenant",),
        ) as hr_client:
            hr_response = await hr_client.get(
                f"/api/v1/employees/{EMPLOYEE_ID}/profile",
                headers=request_headers("p4d-matrix-hr"),
            )

        async with employee_field_policy_api(
            database,
            actor_id=MANAGER_ID,
            permissions=("employee:read:team",),
        ) as manager_client:
            team_response = await manager_client.get(
                "/api/v1/teams/me/members",
                headers=request_headers("p4d-matrix-team"),
            )
            manager_response = await manager_client.get(
                TEAM_PROFILE_PATH,
                headers=request_headers("p4d-matrix-manager"),
            )

        async with employee_field_policy_api(
            database,
            actor_id=USER_ID,
            membership_id=MEMBERSHIP_ID,
            permissions=("employee:read:own",),
        ) as own_client:
            own_response = await own_client.get(
                "/api/v1/me/employee-profile",
                headers=request_headers("p4d-matrix-own"),
            )

    assert hr_response.status_code == 200
    hr = hr_response.json()["data"]
    assert hr["core"] == {
        "id": str(EMPLOYEE_ID),
        "employee_number": "WF-001",
        "first_name": "Ada",
        "last_name": "Yilmaz",
        "email": "ada@example.test",
        "status": "active",
        "employee_version": 1,
    }
    assert hr["personal"] == {
        "preferred_name": "Ada",
        "birth_date": RAW_BIRTH_DATE,
        "phone": RAW_PHONE,
        "version": 1,
    }
    assert hr["employment"]["version"] == 1
    assert hr["organization"]["history"]

    assert team_response.status_code == 200
    assert team_response.json()["data"] == [
        {
            "employee": {
                "id": str(EMPLOYEE_ID),
                "employee_number": "WF-001",
                "first_name": "Ada",
                "last_name": "Yilmaz",
                "preferred_name": "Ada",
                "email": "ada@example.test",
                "status": "active",
            },
            "assignment": {
                "legal_entity": {"code": "WF", "name": "Wealthy Falcon"},
                "branch": {"code": "IST", "name": "Istanbul"},
                "department": {"code": "ENG", "name": "Engineering"},
                "position": {"code": "BE", "title": "Backend Engineer"},
                "effective_from": "2026-07-01",
            },
        }
    ]
    assert team_response.headers["Cache-Control"] == "no-store"
    _assert_forbidden_keys_absent(team_response.json()["data"], MANAGER_FORBIDDEN_KEYS)

    assert manager_response.status_code == 200
    assert manager_response.json()["data"] == _expected_manager_profile()
    assert manager_response.headers["Cache-Control"] == "no-store"
    _assert_forbidden_keys_absent(manager_response.json()["data"], MANAGER_FORBIDDEN_KEYS)
    assert RAW_PHONE not in manager_response.text
    assert RAW_BIRTH_DATE not in manager_response.text

    assert own_response.status_code == 200
    own = own_response.json()["data"]
    assert set(own) == {"availability", "membership_id", "employee_id", "profile"}
    assert own["availability"] == "available"
    assert own["membership_id"] == str(MEMBERSHIP_ID)
    assert own["employee_id"] == str(EMPLOYEE_ID)
    assert own["profile"]["core"]["id"] == str(EMPLOYEE_ID)
    assert own["profile"]["personal"] == {
        "preferred_name": "Ada",
        "birth_date": {"visibility": "masked", "display_value": "••••-05-14"},
        "phone": {"visibility": "masked", "display_value": "••••••••00"},
    }
    assert "membership_id" not in str(own["profile"])
    assert RAW_PHONE not in own_response.text
    assert RAW_BIRTH_DATE not in own_response.text
    for forbidden in ("version", "history", "manager_user_id", "identity_id"):
        assert forbidden not in own_response.text.lower()


async def test_manager_scope_bypasses_share_one_non_leaking_not_found_response() -> None:
    denied_ids = (
        UNRELATED_EMPLOYEE_ID,
        FORMER_EMPLOYEE_ID,
        FUTURE_EMPLOYEE_ID,
        ARCHIVED_EMPLOYEE_ID,
        INDIRECT_EMPLOYEE_ID,
        OTHER_EMPLOYEE_ID,
        GUESSED_EMPLOYEE_ID,
    )
    async with employee_field_policy_database() as database:
        async with employee_field_policy_api(
            database,
            actor_id=MANAGER_ID,
            permissions=("employee:read:team",),
        ) as manager_client:
            responses = [
                await manager_client.get(
                    f"/api/v1/teams/me/members/{candidate_id}/profile",
                    headers={
                        **request_headers("p4d-manager-nonleak"),
                        "X-Manager-Id": str(MANAGER_ID),
                    },
                    params={
                        "manager_id": str(MANAGER_ID),
                        "department_id": "spoofed-department",
                        "scope": "tenant",
                    },
                )
                for candidate_id in denied_ids
            ]
            direct = await manager_client.get(
                TEAM_PROFILE_PATH,
                headers=request_headers("p4d-manager-direct"),
            )
            denied_hr = await manager_client.get(
                f"/api/v1/employees/{EMPLOYEE_ID}/profile",
                headers=request_headers("p4d-manager-hr-denied"),
            )

    assert direct.status_code == 200
    assert all(response.status_code == 404 for response in responses)
    assert all(response.json() == responses[0].json() for response in responses)
    assert responses[0].json()["error"] == {
        "code": "employee_assignment_not_found",
        "message": "Employee assignment was not found",
        "details": None,
        "correlation_id": "p4d-manager-nonleak",
    }
    for candidate_id, response in zip(denied_ids, responses, strict=True):
        assert str(candidate_id) not in response.text
    assert denied_hr.status_code == 403
    assert denied_hr.json()["error"]["code"] == "authorization_denied"


async def test_own_only_actor_cannot_guess_manager_or_hr_projection() -> None:
    async with employee_field_policy_database() as database:
        async with employee_field_policy_api(
            database,
            actor_id=USER_ID,
            membership_id=MEMBERSHIP_ID,
            permissions=("employee:read:own",),
        ) as client:
            own = await client.get(
                "/api/v1/me/employee-profile",
                headers=request_headers("p4d-own"),
            )
            guessed_own = await client.get(
                "/api/v1/me/employee-profile",
                headers={
                    **request_headers("p4d-own-guessed"),
                    "X-Employee-Id": str(OTHER_EMPLOYEE_ID),
                },
                params={"employee_id": str(OTHER_EMPLOYEE_ID)},
            )
            guessed_path = await client.get(
                f"/api/v1/me/employee-profile/{OTHER_EMPLOYEE_ID}",
                headers=request_headers("p4d-own-path"),
            )
            manager_denied = await client.get(
                TEAM_PROFILE_PATH,
                headers=request_headers("p4d-own-team-denied"),
            )
            hr_denied = await client.get(
                f"/api/v1/employees/{EMPLOYEE_ID}/profile",
                headers=request_headers("p4d-own-hr-denied"),
            )

    assert own.status_code == 200
    assert guessed_own.status_code == 200
    assert guessed_own.json()["data"] == own.json()["data"]
    assert guessed_path.status_code == 404
    assert manager_denied.status_code == 403
    assert manager_denied.json()["error"]["code"] == ("employee_assignment_access_denied")
    assert hr_denied.status_code == 403
    assert hr_denied.json()["error"]["code"] == "authorization_denied"


async def test_manager_reads_denials_logs_and_audit_never_receive_excluded_values(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(
        logging.INFO,
        logger="app.platform.observability.correlation",
    )
    async with employee_field_policy_database() as database:
        async with employee_field_policy_api(
            database,
            actor_id=MANAGER_ID,
            permissions=("employee:read:team",),
        ) as client:
            success = await client.get(
                TEAM_PROFILE_PATH,
                headers={
                    **request_headers("p4d-log-success"),
                    "X-Private-Value": RESTRICTED_QUERY_VALUE,
                },
                params=RESTRICTED_INPUTS,
            )
            denial = await client.get(
                f"/api/v1/teams/me/members/{UNRELATED_EMPLOYEE_ID}/profile",
                headers={
                    **request_headers("p4d-log-denial"),
                    "X-Private-Value": RESTRICTED_QUERY_VALUE,
                },
                params=RESTRICTED_INPUTS,
            )
        async with database.sessions() as session:
            audit_count = await session.scalar(select(func.count()).select_from(AuditEvent))

    assert success.status_code == 200
    assert denial.status_code == 404
    assert denial.json()["error"]["details"] is None
    assert audit_count == 0

    completion_records = [
        record.__dict__ for record in caplog.records if record.message == "http.request.completed"
    ]
    assert len(completion_records) >= 2
    serialized = repr(
        [success.json(), denial.json(), completion_records, {"audit_count": audit_count}]
    ).lower()
    for forbidden in (
        RAW_PHONE.lower(),
        RAW_BIRTH_DATE,
        RESTRICTED_QUERY_VALUE.lower(),
        "birth_date",
        "phone",
        *RESTRICTED_INPUTS,
        *(value.lower() for value in RESTRICTED_INPUTS.values()),
    ):
        assert forbidden not in serialized
    assert str(UNRELATED_EMPLOYEE_ID) not in denial.text


def _expected_manager_profile() -> dict[str, object]:
    return {
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


def _assert_forbidden_keys_absent(
    value: object,
    forbidden: frozenset[str],
) -> None:
    if isinstance(value, Mapping):
        assert not (set(value) & forbidden)
        for child in value.values():
            _assert_forbidden_keys_absent(child, forbidden)
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        for child in value:
            _assert_forbidden_keys_absent(child, forbidden)
