import logging
from datetime import date
from uuid import UUID, uuid4

import pytest
from app.main import create_app
from app.models.audit import AuditEvent
from app.models.employee_profile import EmployeePersonalProfile
from app.models.employee_profile_change_request import EmployeeProfileChangeRequest
from sqlalchemy import event, func, select
from tests._employee_profile_change_request_support import (
    EMPLOYEE_ID,
    employee_profile_change_request_api,
    tenant_headers,
)


def test_p4e_routes_and_openapi_schemas_are_exact() -> None:
    document = create_app().openapi()
    paths = document["paths"]
    assert set(paths["/api/v1/me/profile-change-requests"]) == {"get", "post"}
    assert set(paths["/api/v1/me/profile-change-requests/{request_id}"]) == {"get"}
    assert set(paths["/api/v1/me/profile-change-requests/{request_id}/cancel"]) == {"post"}
    assert set(paths["/api/v1/employee-profile-change-requests"]) == {"get"}
    assert set(paths["/api/v1/employee-profile-change-requests/{request_id}"]) == {"get"}
    assert set(paths["/api/v1/employee-profile-change-requests/{request_id}/approve"]) == {"post"}
    assert set(paths["/api/v1/employee-profile-change-requests/{request_id}/reject"]) == {"post"}
    own_operations = (
        *paths["/api/v1/me/profile-change-requests"].values(),
        *paths["/api/v1/me/profile-change-requests/{request_id}"].values(),
    )
    assert all(
        parameter.get("name") != "employee_id"
        for operation in own_operations
        for parameter in operation.get("parameters", [])
    )
    schemas = document["components"]["schemas"]
    create_schema = schemas["EmployeeProfileChangeRequestCreate"]
    assert create_schema["additionalProperties"] is False
    assert set(create_schema["properties"]) == {
        "preferred_name",
        "phone",
        "birth_date",
    }
    employee_schema = schemas["EmployeeProfileChangeRequestEmployeeRead"]
    assert set(employee_schema["properties"]) == {
        "id",
        "employee_number",
        "first_name",
        "last_name",
        "email",
        "status",
    }
    own_request_schema = schemas["OwnEmployeeProfileChangeRequestRead"]
    assert set(own_request_schema["properties"]) == {
        "id",
        "employee_id",
        "status",
        "version",
        "submitted_at",
        "decided_at",
        "cancelled_at",
        "rejection_reason",
        "changed_fields",
        "changes",
    }


async def test_submit_queue_detail_and_approve_apply_exactly_once_without_value_leakage() -> None:
    raw_name = "Requested Name Sentinel"
    raw_phone = "+905559876543"
    async with employee_profile_change_request_api() as (client, database):
        submitted = await client.post(
            "/api/v1/me/profile-change-requests",
            headers=tenant_headers(),
            json={"preferred_name": raw_name, "phone": raw_phone},
        )
        assert submitted.status_code == 201
        request_id = submitted.json()["data"]["id"]
        assert submitted.json()["data"]["employee_id"] == str(EMPLOYEE_ID)
        assert submitted.json()["data"]["changes"] == {
            "preferred_name": {"previous_value": "Ada", "proposed_value": raw_name},
            "phone": {
                "previous_value": {
                    "visibility": "masked",
                    "display_value": "••••••••00",
                },
                "proposed_value": {
                    "visibility": "masked",
                    "display_value": "••••••••43",
                },
            },
            "birth_date": None,
        }
        assert raw_phone not in submitted.text

        async with database.sessions() as session:
            profile = await session.scalar(
                select(EmployeePersonalProfile).where(
                    EmployeePersonalProfile.employee_id == EMPLOYEE_ID
                )
            )
            assert profile is not None
            assert (profile.preferred_name, profile.phone, profile.version) == (
                "Ada",
                "+90 555 000 0000",
                1,
            )

        duplicate = await client.post(
            "/api/v1/me/profile-change-requests",
            headers=tenant_headers(),
            json={"birth_date": "1990-01-01"},
        )
        queue = await client.get(
            "/api/v1/employee-profile-change-requests",
            headers=tenant_headers(),
        )
        detail = await client.get(
            f"/api/v1/employee-profile-change-requests/{request_id}",
            headers=tenant_headers(),
        )
        approved = await client.post(
            f"/api/v1/employee-profile-change-requests/{request_id}/approve",
            headers=tenant_headers(),
            json={"expected_version": 1},
        )
        loser = await client.post(
            f"/api/v1/employee-profile-change-requests/{request_id}/approve",
            headers=tenant_headers(),
            json={"expected_version": 1},
        )

        assert duplicate.status_code == 409
        assert duplicate.json()["error"]["code"] == ("employee_profile_change_request_conflict")
        assert queue.status_code == 200
        assert len(queue.json()["data"]) == 1
        summary = queue.json()["data"][0]
        assert set(summary["employee"]) == {
            "id",
            "employee_number",
            "first_name",
            "last_name",
            "email",
            "status",
        }
        assert "changes" not in summary
        assert raw_name not in queue.text
        assert raw_phone not in queue.text
        assert detail.status_code == 200
        assert detail.json()["data"]["changes"]["phone"]["proposed_value"] == raw_phone
        assert approved.status_code == 200
        assert approved.json()["data"]["status"] == "approved"
        assert approved.json()["data"]["version"] == 2
        assert loser.status_code == 409
        assert loser.json()["error"]["code"] == ("employee_profile_change_request_conflict")

        async with database.sessions() as session:
            profile = await session.scalar(
                select(EmployeePersonalProfile).where(
                    EmployeePersonalProfile.employee_id == EMPLOYEE_ID
                )
            )
            events = list(
                (
                    await session.scalars(
                        select(AuditEvent)
                        .where(AuditEvent.resource_type == "employee_profile_change_request")
                        .order_by(AuditEvent.occurred_at)
                    )
                ).all()
            )

        assert profile is not None
        assert (profile.preferred_name, profile.phone, profile.version) == (
            raw_name,
            raw_phone,
            2,
        )
        assert [event.event_type for event in events] == [
            "employee.profile_change_request.submitted",
            "employee.profile_change_request.approved",
        ]
        persisted_audit = repr(
            [
                (
                    event.changed_fields,
                    event.before_data,
                    event.after_data,
                    event.metadata_,
                )
                for event in events
            ]
        )
        assert raw_name not in persisted_audit
        assert raw_phone not in persisted_audit
        assert all(event.before_data == event.after_data == {} for event in events)


async def test_any_explicit_normalized_no_op_rejects_whole_submission() -> None:
    async with employee_profile_change_request_api() as (client, database):
        response = await client.post(
            "/api/v1/me/profile-change-requests",
            headers=tenant_headers(),
            json={
                "preferred_name": "  Ada  ",
                "phone": "+90 (555) 987-6543",
            },
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

    assert response.status_code == 422
    assert response.json()["error"]["code"] == ("employee_profile_change_request_validation_error")
    assert "Ada" not in response.text
    assert request_count == 0
    assert profile is not None and profile.version == 1


async def test_no_op_validation_precedes_active_request_conflict() -> None:
    async with employee_profile_change_request_api() as (client, _database):
        submitted = await client.post(
            "/api/v1/me/profile-change-requests",
            headers=tenant_headers(),
            json={"phone": "+905559876543"},
        )
        assert submitted.status_code == 201

        unchanged = await client.post(
            "/api/v1/me/profile-change-requests",
            headers=tenant_headers(),
            json={"preferred_name": "Ada"},
        )

    assert unchanged.status_code == 422
    assert unchanged.json()["error"]["code"] == ("employee_profile_change_request_validation_error")
    assert "Ada" not in unchanged.text


async def test_stale_profile_conflicts_without_partial_apply_then_reject_never_mutates() -> None:
    rejection_reason = "Reason Text Must Not Enter Audit Sentinel"
    async with employee_profile_change_request_api() as (client, database):
        submitted = await client.post(
            "/api/v1/me/profile-change-requests",
            headers=tenant_headers(),
            json={"birth_date": "1990-01-02"},
        )
        assert submitted.status_code == 201
        request_id = submitted.json()["data"]["id"]

        async with database.sessions() as session:
            profile = await session.scalar(
                select(EmployeePersonalProfile).where(
                    EmployeePersonalProfile.employee_id == EMPLOYEE_ID
                )
            )
            assert profile is not None
            profile.phone = "+905551111111"
            profile.version += 1
            await session.commit()

        stale = await client.post(
            f"/api/v1/employee-profile-change-requests/{request_id}/approve",
            headers=tenant_headers(),
            json={"expected_version": 1},
        )
        reloaded = await client.get(
            f"/api/v1/employee-profile-change-requests/{request_id}",
            headers=tenant_headers(),
        )
        rejected = await client.post(
            f"/api/v1/employee-profile-change-requests/{request_id}/reject",
            headers=tenant_headers(),
            json={"expected_version": 1, "reason": rejection_reason},
        )

        async with database.sessions() as session:
            profile = await session.scalar(
                select(EmployeePersonalProfile).where(
                    EmployeePersonalProfile.employee_id == EMPLOYEE_ID
                )
            )
            request = await session.get(
                EmployeeProfileChangeRequest,
                UUID(submitted.json()["data"]["id"]),
            )
            audit_events = list(
                (
                    await session.scalars(
                        select(AuditEvent).where(
                            AuditEvent.resource_type == "employee_profile_change_request"
                        )
                    )
                ).all()
            )

    assert stale.status_code == 409
    assert stale.json()["error"]["code"] == ("employee_profile_change_request_stale_profile")
    assert reloaded.status_code == 200
    assert reloaded.json()["data"]["status"] == "submitted"
    assert reloaded.json()["data"]["profile_is_stale"] is True
    assert rejected.status_code == 200
    assert rejected.json()["data"]["status"] == "rejected"
    assert profile is not None
    assert (profile.birth_date, profile.phone, profile.version) == (
        date(1992, 5, 14),
        "+905551111111",
        2,
    )
    assert request is not None and request.status == "rejected"
    audit_text = repr(
        [(event.metadata_, event.before_data, event.after_data) for event in audit_events]
    )
    assert rejection_reason not in audit_text
    assert "1990-01-02" not in audit_text


async def test_cancel_is_own_submitted_only_and_terminal_allows_later_request() -> None:
    async with employee_profile_change_request_api() as (client, database):
        first = await client.post(
            "/api/v1/me/profile-change-requests",
            headers=tenant_headers(),
            json={"phone": None},
        )
        assert first.status_code == 201
        request_id = first.json()["data"]["id"]
        cancelled = await client.post(
            f"/api/v1/me/profile-change-requests/{request_id}/cancel",
            headers=tenant_headers(),
            json={"expected_version": 1},
        )
        cancelled_again = await client.post(
            f"/api/v1/me/profile-change-requests/{request_id}/cancel",
            headers=tenant_headers(),
            json={"expected_version": 1},
        )
        later = await client.post(
            "/api/v1/me/profile-change-requests",
            headers=tenant_headers(),
            json={"phone": "+905551234567"},
        )
        history = await client.get(
            "/api/v1/me/profile-change-requests",
            headers=tenant_headers(),
            params={"limit": 1},
        )

        async with database.sessions() as session:
            profile = await session.scalar(
                select(EmployeePersonalProfile).where(
                    EmployeePersonalProfile.employee_id == EMPLOYEE_ID
                )
            )

    assert cancelled.status_code == 200
    assert cancelled.json()["data"]["status"] == "cancelled"
    assert cancelled.json()["data"]["version"] == 2
    assert cancelled_again.status_code == 409
    assert later.status_code == 201
    assert history.status_code == 200
    assert len(history.json()["data"]) == 1
    assert history.json()["meta"]["next_cursor"] is not None
    assert profile is not None
    assert (profile.phone, profile.version) == ("+90 555 000 0000", 1)


async def test_request_validation_not_found_manager_denial_and_logs_are_non_leaking(
    caplog: pytest.LogCaptureFixture,
) -> None:
    secret = "RawSecretShouldNotEcho"
    raw_name = "Log Name Sentinel"
    raw_phone = "+905559998877"
    rejection_reason = "Log Reason Sentinel"
    caplog.set_level(logging.INFO, logger="app.platform.observability.correlation")
    async with employee_profile_change_request_api(
        raise_app_exceptions=False,
    ) as (client, _database):
        invalid = await client.post(
            "/api/v1/me/profile-change-requests",
            headers=tenant_headers(),
            json={"first_name": secret},
        )
        invalid_control = await client.post(
            "/api/v1/me/profile-change-requests",
            headers=tenant_headers(),
            json={"preferred_name": "Unsafe\x00Name"},
        )
        missing_id = uuid4()
        missing_own = await client.get(
            f"/api/v1/me/profile-change-requests/{missing_id}",
            headers=tenant_headers(),
        )
        missing_hr = await client.get(
            f"/api/v1/employee-profile-change-requests/{missing_id}",
            headers=tenant_headers(),
        )
        submitted = await client.post(
            "/api/v1/me/profile-change-requests",
            headers=tenant_headers(),
            json={"preferred_name": raw_name, "phone": raw_phone},
        )
        rejected = await client.post(
            f"/api/v1/employee-profile-change-requests/{submitted.json()['data']['id']}/reject",
            headers=tenant_headers(),
            json={"expected_version": 1, "reason": rejection_reason},
        )

    async with employee_profile_change_request_api(
        permissions=("employee:read:own", "employee:read:team"),
    ) as (client, _database):
        denied_queue = await client.get(
            "/api/v1/employee-profile-change-requests",
            headers=tenant_headers(),
        )

    assert invalid.status_code == 422
    assert invalid_control.status_code == 422
    assert invalid.json()["error"]["code"] == ("employee_profile_change_request_validation_error")
    assert secret not in invalid.text
    assert missing_own.status_code == missing_hr.status_code == 404
    assert missing_own.json()["error"]["code"] == ("employee_profile_change_request_not_found")
    assert missing_hr.json()["error"]["code"] == ("employee_profile_change_request_not_found")
    assert str(missing_id) not in missing_own.text
    assert str(missing_id) not in missing_hr.text
    assert denied_queue.status_code == 403
    assert denied_queue.json()["error"]["code"] == "authorization_denied"
    assert submitted.status_code == 201
    assert rejected.status_code == 200
    completion_logs = repr(
        [record.__dict__ for record in caplog.records if record.message == "http.request.completed"]
    )
    for forbidden in (secret, "Unsafe\x00Name", raw_name, raw_phone, rejection_reason):
        assert forbidden not in completion_logs


async def test_queue_and_own_history_have_bounded_queries_without_n_plus_one() -> None:
    async with employee_profile_change_request_api() as (client, database):
        submitted = await client.post(
            "/api/v1/me/profile-change-requests",
            headers=tenant_headers(),
            json={"preferred_name": "Query Budget Name"},
        )
        assert submitted.status_code == 201

        statements: list[str] = []

        def capture_statement(
            _connection: object,
            _cursor: object,
            statement: str,
            _parameters: object,
            _context: object,
            _executemany: bool,
        ) -> None:
            if statement.lstrip().upper().startswith("SELECT"):
                statements.append(statement.lower())

        event.listen(database.engine.sync_engine, "before_cursor_execute", capture_statement)
        try:
            queue = await client.get(
                "/api/v1/employee-profile-change-requests",
                headers=tenant_headers(),
            )
            queue_statements = list(statements)
            statements.clear()
            history = await client.get(
                "/api/v1/me/profile-change-requests",
                headers=tenant_headers(),
            )
            own_statements = list(statements)
        finally:
            event.remove(
                database.engine.sync_engine,
                "before_cursor_execute",
                capture_statement,
            )

    assert queue.status_code == history.status_code == 200
    assert len(queue_statements) == 1
    assert "join employees" in queue_statements[0]
    assert "join employee_profiles" in queue_statements[0]
    assert len(own_statements) == 2


async def test_hr_queue_cursor_is_oldest_first_and_bound_to_status_filter() -> None:
    async with employee_profile_change_request_api() as (client, _database):
        first = await client.post(
            "/api/v1/me/profile-change-requests",
            headers=tenant_headers(),
            json={"preferred_name": "First cancelled request"},
        )
        first_id = first.json()["data"]["id"]
        first_cancel = await client.post(
            f"/api/v1/me/profile-change-requests/{first_id}/cancel",
            headers=tenant_headers(),
            json={"expected_version": 1},
        )
        second = await client.post(
            "/api/v1/me/profile-change-requests",
            headers=tenant_headers(),
            json={"phone": "+905551234567"},
        )
        second_id = second.json()["data"]["id"]
        second_cancel = await client.post(
            f"/api/v1/me/profile-change-requests/{second_id}/cancel",
            headers=tenant_headers(),
            json={"expected_version": 1},
        )

        page_one = await client.get(
            "/api/v1/employee-profile-change-requests",
            headers=tenant_headers(),
            params={"status": "cancelled", "limit": 1},
        )
        cursor = page_one.json()["meta"]["next_cursor"]
        page_two = await client.get(
            "/api/v1/employee-profile-change-requests",
            headers=tenant_headers(),
            params={"status": "cancelled", "limit": 1, "cursor": cursor},
        )
        mismatched_filter = await client.get(
            "/api/v1/employee-profile-change-requests",
            headers=tenant_headers(),
            params={"status": "rejected", "limit": 1, "cursor": cursor},
        )

    assert first.status_code == 201
    assert first_cancel.status_code == 200
    assert second.status_code == 201
    assert second_cancel.status_code == 200
    assert page_one.status_code == page_two.status_code == 200
    assert [item["id"] for item in page_one.json()["data"]] == [first_id]
    assert [item["id"] for item in page_two.json()["data"]] == [second_id]
    assert cursor is not None
    assert page_two.json()["meta"]["next_cursor"] is None
    assert mismatched_filter.status_code == 422
    assert mismatched_filter.json()["error"]["code"] == (
        "employee_profile_change_request_validation_error"
    )
