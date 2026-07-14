from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

from app.main import create_app
from app.models.audit import AuditEvent
from app.models.employee import Employee
from app.models.employee_account_link import EmployeeAccountLink
from app.services.audit_recorder import SqlAlchemyAuditRecorder
from sqlalchemy import func, select
from tests._employee_account_link_support import (
    EMPLOYEE_ID,
    MEMBERSHIP_ID,
    OTHER_EMPLOYEE_ID,
    OTHER_TENANT_MEMBERSHIP_ID,
    SECOND_EMPLOYEE_ID,
    SECOND_MEMBERSHIP_ID,
    TENANT_ID,
    employee_account_link_api,
    tenant_headers,
)


def test_main_registers_only_the_intended_p4c_account_link_and_own_profile_routes() -> None:
    paths = create_app().openapi()["paths"]
    assert set(paths["/api/v1/employees/{employee_id}/account-link"]) == {
        "get",
        "patch",
    }
    assert set(paths["/api/v1/employees/{employee_id}/account-link/eligible-memberships"]) == {
        "get"
    }
    assert set(paths["/api/v1/me/employee-profile"]) == {"get"}
    assert all(
        "employee_id" not in parameter["name"]
        for parameter in paths["/api/v1/me/employee-profile"]["get"].get("parameters", [])
    )


async def test_hr_link_flow_and_own_endpoint_ignore_guessed_employee_id() -> None:
    async with employee_account_link_api() as (client, _database):
        current = await client.get(
            f"/api/v1/employees/{EMPLOYEE_ID}/account-link",
            headers=tenant_headers(),
        )
        eligible = await client.get(
            f"/api/v1/employees/{EMPLOYEE_ID}/account-link/eligible-memberships",
            headers=tenant_headers(),
            params={"q": "ada@example.test", "limit": 20},
        )
        linked = await client.patch(
            f"/api/v1/employees/{EMPLOYEE_ID}/account-link",
            headers=tenant_headers(),
            json={"membership_id": str(MEMBERSHIP_ID), "expected_version": None},
        )
        own = await client.get(
            "/api/v1/me/employee-profile",
            headers=tenant_headers(),
            params={"employee_id": str(OTHER_EMPLOYEE_ID)},
        )
        p4b = await client.get(
            f"/api/v1/employees/{EMPLOYEE_ID}/profile",
            headers=tenant_headers(),
        )

    assert current.status_code == 200
    assert current.json()["data"] == {"employee_id": str(EMPLOYEE_ID), "link": None}
    assert current.headers["Cache-Control"] == "no-store"
    assert current.headers["Pragma"] == "no-cache"
    assert eligible.status_code == 200
    assert [row["membership_id"] for row in eligible.json()["data"]] == [str(MEMBERSHIP_ID)]
    assert linked.status_code == 200
    assert linked.json()["data"]["link"]["membership"]["membership_id"] == str(MEMBERSHIP_ID)
    assert own.status_code == 200
    assert own.json()["data"]["availability"] == "available"
    assert own.json()["data"]["profile"]["core"]["id"] == str(EMPLOYEE_ID)
    own_serialized = repr(own.json()["data"]).lower()
    for forbidden in ("history", "version", "identity_id", "manager_user_id"):
        assert forbidden not in own_serialized
    assert p4b.status_code == 200
    assert p4b.json()["data"]["core"]["id"] == str(EMPLOYEE_ID)


async def test_unlinked_own_profile_is_one_identifier_free_unavailable_state() -> None:
    async with employee_account_link_api() as (client, _database):
        own = await client.get(
            "/api/v1/me/employee-profile",
            headers=tenant_headers(),
            params={"employee_id": str(OTHER_EMPLOYEE_ID)},
        )

    assert own.status_code == 200
    assert own.json()["data"] == {
        "availability": "unavailable",
        "membership_id": None,
        "profile": None,
    }
    assert str(EMPLOYEE_ID) not in own.text
    assert str(OTHER_EMPLOYEE_ID) not in own.text


async def test_hr_link_routes_require_update_permission_and_own_route_requires_own_permission() -> (
    None
):
    async with employee_account_link_api(
        permissions=("employee:read:tenant",),
    ) as (client, _database):
        denied_hr = await client.get(
            f"/api/v1/employees/{EMPLOYEE_ID}/account-link",
            headers=tenant_headers(),
        )
        denied_own = await client.get(
            "/api/v1/me/employee-profile",
            headers=tenant_headers(),
        )

    assert denied_hr.status_code == 403
    assert denied_own.status_code == 403
    assert denied_hr.json()["error"]["code"] == "authorization_denied"
    assert denied_own.json()["error"]["code"] == "authorization_denied"


async def test_cross_tenant_employee_and_membership_fail_without_existence_details() -> None:
    async with employee_account_link_api() as (client, _database):
        missing = await client.get(
            f"/api/v1/employees/{OTHER_EMPLOYEE_ID}/account-link",
            headers=tenant_headers(),
        )
        foreign_membership = await client.patch(
            f"/api/v1/employees/{EMPLOYEE_ID}/account-link",
            headers=tenant_headers(),
            json={
                "membership_id": str(OTHER_TENANT_MEMBERSHIP_ID),
                "expected_version": None,
            },
        )
        linked = await client.patch(
            f"/api/v1/employees/{EMPLOYEE_ID}/account-link",
            headers=tenant_headers(),
            json={"membership_id": str(MEMBERSHIP_ID), "expected_version": None},
        )
        assert linked.status_code == 200
        membership_already_used = await client.patch(
            f"/api/v1/employees/{SECOND_EMPLOYEE_ID}/account-link",
            headers=tenant_headers(),
            json={"membership_id": str(MEMBERSHIP_ID), "expected_version": None},
        )

    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "employee_not_found"
    assert foreign_membership.status_code == 409
    assert foreign_membership.json()["error"] == {
        "code": "employee_account_link_conflict",
        "message": "The requested account link is unavailable",
        "details": None,
        "correlation_id": foreign_membership.json()["error"]["correlation_id"],
    }
    assert str(OTHER_TENANT_MEMBERSHIP_ID) not in foreign_membership.text
    assert membership_already_used.status_code == 409
    assert membership_already_used.json()["error"]["code"] == ("employee_account_link_conflict")
    assert str(MEMBERSHIP_ID) not in membership_already_used.text


async def test_patch_shape_is_strict_and_stale_version_returns_409() -> None:
    async with employee_account_link_api() as (client, _database):
        invalid = await client.patch(
            f"/api/v1/employees/{EMPLOYEE_ID}/account-link",
            headers=tenant_headers(),
            json={
                "membership_id": str(MEMBERSHIP_ID),
                "expected_version": None,
                "employee_id": str(OTHER_EMPLOYEE_ID),
            },
        )
        linked = await client.patch(
            f"/api/v1/employees/{EMPLOYEE_ID}/account-link",
            headers=tenant_headers(),
            json={"membership_id": str(MEMBERSHIP_ID), "expected_version": None},
        )
        stale = await client.patch(
            f"/api/v1/employees/{EMPLOYEE_ID}/account-link",
            headers=tenant_headers(),
            json={"membership_id": None, "expected_version": 99},
        )

    assert invalid.status_code == 422
    assert linked.status_code == 200
    assert stale.status_code == 409
    assert stale.json()["error"]["code"] == "concurrent_write_conflict"


async def test_archived_linked_employee_is_not_manageable_and_own_profile_is_unavailable() -> None:
    async with employee_account_link_api() as (client, database):
        linked = await client.patch(
            f"/api/v1/employees/{EMPLOYEE_ID}/account-link",
            headers=tenant_headers(),
            json={"membership_id": str(MEMBERSHIP_ID), "expected_version": None},
        )
        assert linked.status_code == 200
        async with database.sessions() as session:
            employee = await session.get(Employee, EMPLOYEE_ID)
            assert employee is not None
            employee.archived_at = datetime.now(UTC)
            await session.commit()

        current = await client.get(
            f"/api/v1/employees/{EMPLOYEE_ID}/account-link",
            headers=tenant_headers(),
        )
        own = await client.get(
            "/api/v1/me/employee-profile",
            headers=tenant_headers(),
        )

    assert current.status_code == 404
    assert own.status_code == 200
    assert own.json()["data"] == {
        "availability": "unavailable",
        "membership_id": None,
        "profile": None,
    }


async def test_link_audit_is_id_only_allowlisted_and_failure_rolls_back_atomically() -> None:
    async with employee_account_link_api() as (client, database):
        linked = await client.patch(
            f"/api/v1/employees/{EMPLOYEE_ID}/account-link",
            headers=tenant_headers(),
            json={"membership_id": str(MEMBERSHIP_ID), "expected_version": None},
        )
        assert linked.status_code == 200
        version = linked.json()["data"]["link"]["version"]
        relinked = await client.patch(
            f"/api/v1/employees/{EMPLOYEE_ID}/account-link",
            headers=tenant_headers(),
            json={
                "membership_id": str(SECOND_MEMBERSHIP_ID),
                "expected_version": version,
            },
        )
        assert relinked.status_code == 200
        version = relinked.json()["data"]["link"]["version"]
        unlinked = await client.patch(
            f"/api/v1/employees/{EMPLOYEE_ID}/account-link",
            headers=tenant_headers(),
            json={"membership_id": None, "expected_version": version},
        )
        assert unlinked.status_code == 200
        async with database.sessions() as session:
            events = tuple(
                await session.scalars(
                    select(AuditEvent).where(
                        AuditEvent.event_type == "employee.account_link.changed"
                    )
                )
            )

    assert len(events) == 3
    events_by_status = {event.metadata_["link_status"]: event for event in events}
    linked_event = events_by_status["linked"]
    relinked_event = events_by_status["relinked"]
    unlinked_event = events_by_status["unlinked"]
    assert linked_event.changed_fields == ["link_status", "membership_id"]
    assert linked_event.before_data == {}
    assert linked_event.after_data == {}
    assert linked_event.metadata_ == {
        "link_status": "linked",
        "new_membership_id": str(MEMBERSHIP_ID),
    }
    assert relinked_event.changed_fields == ["link_status", "membership_id"]
    assert relinked_event.before_data == {}
    assert relinked_event.after_data == {}
    assert relinked_event.metadata_ == {
        "link_status": "relinked",
        "previous_membership_id": str(MEMBERSHIP_ID),
        "new_membership_id": str(SECOND_MEMBERSHIP_ID),
    }
    assert unlinked_event.changed_fields == ["link_status", "membership_id"]
    assert unlinked_event.before_data == {}
    assert unlinked_event.after_data == {}
    assert unlinked_event.metadata_ == {
        "link_status": "unlinked",
        "previous_membership_id": str(SECOND_MEMBERSHIP_ID),
    }
    persisted = repr(
        [
            (event.before_data, event.after_data, event.metadata_)
            for event in events
        ]
    ).lower()
    for forbidden in ("ada@", "profile", "password", "token", "secret"):
        assert forbidden not in persisted

    async with employee_account_link_api(raise_app_exceptions=False) as (client, database):
        with patch.object(
            SqlAlchemyAuditRecorder,
            "record",
            new=AsyncMock(side_effect=RuntimeError("forced audit failure")),
        ):
            failed = await client.patch(
                f"/api/v1/employees/{EMPLOYEE_ID}/account-link",
                headers=tenant_headers(),
                json={"membership_id": str(MEMBERSHIP_ID), "expected_version": None},
            )
        async with database.sessions() as session:
            link_count = await session.scalar(select(func.count()).select_from(EmployeeAccountLink))
            audit_count = await session.scalar(select(func.count()).select_from(AuditEvent))

    assert failed.status_code == 500
    assert link_count == 0
    assert audit_count == 0

    async with employee_account_link_api(raise_app_exceptions=False) as (client, database):
        linked = await client.patch(
            f"/api/v1/employees/{EMPLOYEE_ID}/account-link",
            headers=tenant_headers(),
            json={"membership_id": str(MEMBERSHIP_ID), "expected_version": None},
        )
        assert linked.status_code == 200
        version = linked.json()["data"]["link"]["version"]
        with patch.object(
            SqlAlchemyAuditRecorder,
            "record",
            new=AsyncMock(side_effect=RuntimeError("forced unlink audit failure")),
        ):
            failed_unlink = await client.patch(
                f"/api/v1/employees/{EMPLOYEE_ID}/account-link",
                headers=tenant_headers(),
                json={"membership_id": None, "expected_version": version},
            )
        async with database.sessions() as session:
            retained_link = await session.scalar(
                select(EmployeeAccountLink).where(
                    EmployeeAccountLink.tenant_id == TENANT_ID,
                    EmployeeAccountLink.employee_id == EMPLOYEE_ID,
                )
            )
            audit_count = await session.scalar(select(func.count()).select_from(AuditEvent))

    assert failed_unlink.status_code == 500
    assert retained_link is not None
    assert retained_link.membership_id == MEMBERSHIP_ID
    assert retained_link.version == version
    assert audit_count == 1
