from __future__ import annotations

from collections.abc import Mapping, Sequence

from app.main import create_app
from app.schemas.employee_assignment import TeamMemberRead
from tests._employee_field_policy_support import (
    EMPLOYEE_ID,
    INDIRECT_EMPLOYEE_ID,
    MANAGER_ID,
    RAW_BIRTH_DATE,
    RAW_PHONE,
    UNRELATED_EMPLOYEE_ID,
    employee_field_policy_api,
    employee_field_policy_database,
    request_headers,
)

LEGACY_TEAM_PATH = "/api/v1/teams/me"
SAFE_TEAM_PATH = "/api/v1/teams/me/members"

LEGACY_EMPLOYEE_FIELDS = {
    "id",
    "employee_number",
    "first_name",
    "last_name",
    "email",
    "status",
}
LEGACY_ASSIGNMENT_FIELDS = {
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
MANAGER_FORBIDDEN_FIELDS = frozenset(
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
        "change_reason",
        "supersedes_assignment_id",
        "created_at",
        "updated_at",
        "effective_to",
    }
)


def test_openapi_preserves_deprecated_legacy_operation_and_adds_safe_list() -> None:
    openapi = create_app().openapi()
    paths = openapi["paths"]
    schemas = openapi["components"]["schemas"]
    legacy = paths[LEGACY_TEAM_PATH]["get"]
    safe = paths[SAFE_TEAM_PATH]["get"]

    assert legacy["operationId"] == "get_my_team_api_v1_teams_me_get"
    assert legacy["deprecated"] is True
    assert "Migrate to GET /api/v1/teams/me/members" in legacy["description"]
    assert "removed in a future API version" in legacy["description"]
    assert legacy["responses"]["200"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/ListEnvelope_TeamMemberRead_"
    }
    assert safe["responses"]["200"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/ListEnvelope_ManagerTeamMemberRead_"
    }

    assert schemas["TeamMemberRead"] == {
        "additionalProperties": False,
        "properties": {
            "employee": {"$ref": "#/components/schemas/AssignmentEmployeeRead"},
            "assignment": {"$ref": "#/components/schemas/EmployeeAssignmentRead"},
        },
        "required": ["employee", "assignment"],
        "title": "TeamMemberRead",
        "type": "object",
    }
    assert schemas["ManagerTeamMemberRead"]["properties"] == {
        "employee": {"$ref": "#/components/schemas/ManagerTeamEmployeeRead"},
        "assignment": {"$ref": "#/components/schemas/ManagerTeamAssignmentRead"},
    }
    assert schemas["ManagerTeamMemberRead"]["required"] == ["employee", "assignment"]

    for operation in (legacy, safe):
        assert {
            (parameter["in"], parameter["name"]) for parameter in operation.get("parameters", [])
        } == {("query", "limit"), ("query", "cursor")}


async def test_legacy_requires_tenant_and_team_permissions_while_manager_uses_safe_list() -> None:
    async with employee_field_policy_database() as database:
        async with employee_field_policy_api(
            database,
            actor_id=MANAGER_ID,
            permissions=("employee:read:team",),
        ) as manager_client:
            manager_legacy = await manager_client.get(
                LEGACY_TEAM_PATH,
                headers=request_headers("p4d-legacy-manager-denied"),
            )
            manager_safe = await manager_client.get(
                SAFE_TEAM_PATH,
                headers=request_headers("p4d-safe-manager"),
            )

        async with employee_field_policy_api(
            database,
            actor_id=MANAGER_ID,
            permissions=("employee:read:tenant",),
        ) as tenant_only_client:
            tenant_only_legacy = await tenant_only_client.get(
                LEGACY_TEAM_PATH,
                headers=request_headers("p4d-legacy-tenant-only-denied"),
            )

        async with employee_field_policy_api(
            database,
            actor_id=MANAGER_ID,
            permissions=("employee:read:tenant", "employee:read:team"),
        ) as legacy_client:
            authorized_legacy = await legacy_client.get(
                LEGACY_TEAM_PATH,
                headers=request_headers("p4d-legacy-authorized"),
            )

    assert manager_legacy.status_code == 403
    assert manager_legacy.json()["error"]["code"] == "employee_assignment_access_denied"
    assert tenant_only_legacy.status_code == 403
    assert tenant_only_legacy.json()["error"]["code"] == ("employee_assignment_access_denied")

    assert manager_safe.status_code == 200
    assert manager_safe.headers["Cache-Control"] == "no-store"
    safe_items = manager_safe.json()["data"]
    assert [item["employee"]["id"] for item in safe_items] == [str(EMPLOYEE_ID)]
    assert str(UNRELATED_EMPLOYEE_ID) not in manager_safe.text
    assert str(INDIRECT_EMPLOYEE_ID) not in manager_safe.text
    assert RAW_PHONE not in manager_safe.text
    assert RAW_BIRTH_DATE not in manager_safe.text
    _assert_forbidden_fields_absent(safe_items, MANAGER_FORBIDDEN_FIELDS)

    assert authorized_legacy.status_code == 200
    assert authorized_legacy.headers["Cache-Control"] == "no-store"
    legacy_items = authorized_legacy.json()["data"]
    assert len(legacy_items) == 1
    item = legacy_items[0]
    assert set(item) == {"employee", "assignment"}
    assert set(item["employee"]) == LEGACY_EMPLOYEE_FIELDS
    assert set(item["assignment"]) == LEGACY_ASSIGNMENT_FIELDS
    assert set(item["assignment"]["employee"]) == LEGACY_EMPLOYEE_FIELDS
    assert item["employee"] == item["assignment"]["employee"]
    assert item["employee"]["id"] == str(EMPLOYEE_ID)
    assert set(item["assignment"]["legal_entity"]) == {"id", "code", "name", "status"}
    assert set(item["assignment"]["branch"]) == {"id", "code", "name", "status"}
    assert set(item["assignment"]["department"]) == {"id", "code", "name", "status"}
    assert set(item["assignment"]["position"]) == {"id", "code", "title", "status"}
    assert set(item["assignment"]["manager"]) == {"id", "full_name", "email", "status"}
    assert TeamMemberRead.model_validate(item).model_dump(mode="json") == item
    assert str(UNRELATED_EMPLOYEE_ID) not in authorized_legacy.text
    assert str(INDIRECT_EMPLOYEE_ID) not in authorized_legacy.text


def _assert_forbidden_fields_absent(value: object, forbidden: frozenset[str]) -> None:
    if isinstance(value, Mapping):
        assert not (set(value) & forbidden)
        for child in value.values():
            _assert_forbidden_fields_absent(child, forbidden)
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        for child in value:
            _assert_forbidden_fields_absent(child, forbidden)
