from datetime import date
from unittest.mock import AsyncMock, patch

from app.models.audit import AuditEvent
from app.models.employee import Employee
from app.models.employee_profile import EmployeePersonalProfile
from app.platform.audit import (
    AuditActorType,
    AuditCategory,
    AuditContext,
    AuditDataClassification,
    AuditEventDraft,
    AuditEventType,
    AuditScopeType,
    AuditVisibilityClass,
)
from app.platform.db import SqlAlchemyUnitOfWork
from app.services.audit_recorder import SqlAlchemyAuditRecorder
from sqlalchemy import func, select
from tests._employee_profile_support import (
    ACTOR_ID,
    EMPLOYEE_ID,
    TENANT_ID,
    employee_profile_api,
    employee_profile_database,
    tenant_headers,
)


async def test_personal_profile_audit_redacts_to_changed_p4b_values() -> None:
    async with employee_profile_database() as database:
        async with database.sessions() as session:
            recorder = SqlAlchemyAuditRecorder(session)

            async def operation() -> None:
                await recorder.record(
                    AuditEventDraft(
                        scope_type=AuditScopeType.TENANT,
                        tenant_id=TENANT_ID,
                        actor_type=AuditActorType.USER,
                        actor_user_id=ACTOR_ID,
                        event_type=(AuditEventType.EMPLOYEE_PERSONAL_PROFILE_UPDATED),
                        category=AuditCategory.HR_OPERATIONS,
                        resource_type="employee",
                        resource_id=EMPLOYEE_ID,
                        action="update_personal_profile",
                        context=_audit_context("p4b-personal-redaction"),
                        changed_fields=(
                            "first_name",
                            "email",
                            "preferred_name",
                            "birth_date",
                            "phone",
                            "tckn",
                        ),
                        before_values={
                            "first_name": "Ada",
                            "last_name": "Must not snapshot",
                            "email": "ada@example.test",
                            "preferred_name": "Ada",
                            "birth_date": date(1992, 5, 14),
                            "phone": "+90 555 000 0000",
                            "tckn": "NeverPersistTCKN",
                            "salary": 999_999,
                        },
                        after_values={
                            "first_name": "Ayse",
                            "last_name": "Must not snapshot",
                            "email": "ayse@example.test",
                            "preferred_name": "Ayse",
                            "birth_date": date(1992, 5, 15),
                            "phone": None,
                            "tckn": "NeverPersistTCKN",
                            "payload": {"passport": "NeverPersistPassport"},
                        },
                        metadata={"payload": "NeverPersistPayload"},
                        data_classification=AuditDataClassification.HR_METADATA,
                        visibility_class=AuditVisibilityClass.HR_OPERATIONS,
                    )
                )

            await SqlAlchemyUnitOfWork(session).execute(operation)

        async with database.sessions() as session:
            event = await session.scalar(
                select(AuditEvent).where(
                    AuditEvent.event_type == "employee.personal_profile.updated"
                )
            )

    assert event is not None
    assert event.changed_fields == [
        "birth_date",
        "email",
        "first_name",
        "phone",
        "preferred_name",
    ]
    assert event.before_data == {
        "birth_date": "1992-05-14",
        "email": "ada@example.test",
        "first_name": "Ada",
        "phone": "+90 555 000 0000",
        "preferred_name": "Ada",
    }
    assert event.after_data == {
        "birth_date": "1992-05-15",
        "email": "ayse@example.test",
        "first_name": "Ayse",
        "phone": None,
        "preferred_name": "Ayse",
    }
    assert event.metadata_ == {}
    persisted = repr((event.changed_fields, event.before_data, event.after_data)).lower()
    for forbidden in (
        "must not snapshot",
        "tckn",
        "neverpersist",
        "salary",
        "passport",
        "payload",
    ):
        assert forbidden not in persisted


async def test_employment_profile_audit_redacts_to_changed_p4b_values() -> None:
    async with employee_profile_database() as database:
        async with database.sessions() as session:
            recorder = SqlAlchemyAuditRecorder(session)

            async def operation() -> None:
                await recorder.record(
                    AuditEventDraft(
                        scope_type=AuditScopeType.TENANT,
                        tenant_id=TENANT_ID,
                        actor_type=AuditActorType.USER,
                        actor_user_id=ACTOR_ID,
                        event_type=(AuditEventType.EMPLOYEE_EMPLOYMENT_PROFILE_UPDATED),
                        category=AuditCategory.HR_OPERATIONS,
                        resource_type="employee",
                        resource_id=EMPLOYEE_ID,
                        action="update_employment_profile",
                        context=_audit_context("p4b-employment-redaction"),
                        changed_fields=(
                            "employment_start_date",
                            "contract_type",
                            "work_type",
                            "status",
                        ),
                        before_values={
                            "employment_start_date": date(2026, 7, 1),
                            "contract_type": "indefinite",
                            "work_type": "full_time",
                            "status": "active",
                            "employment_end_date": None,
                        },
                        after_values={
                            "employment_start_date": date(2026, 7, 2),
                            "contract_type": "fixed_term",
                            "work_type": "part_time",
                            "status": "terminated",
                            "employment_end_date": date(2026, 7, 30),
                        },
                        data_classification=AuditDataClassification.HR_METADATA,
                        visibility_class=AuditVisibilityClass.HR_OPERATIONS,
                    )
                )

            await SqlAlchemyUnitOfWork(session).execute(operation)

        async with database.sessions() as session:
            event = await session.scalar(
                select(AuditEvent).where(
                    AuditEvent.event_type == "employee.employment_profile.updated"
                )
            )

    assert event is not None
    assert event.changed_fields == [
        "contract_type",
        "employment_start_date",
        "work_type",
    ]
    assert event.before_data == {
        "contract_type": "indefinite",
        "employment_start_date": "2026-07-01",
        "work_type": "full_time",
    }
    assert event.after_data == {
        "contract_type": "fixed_term",
        "employment_start_date": "2026-07-02",
        "work_type": "part_time",
    }
    assert "terminated" not in repr(event.after_data)
    assert "employment_end_date" not in event.after_data


async def test_profile_command_audits_only_actual_before_and_after_values() -> None:
    async with employee_profile_api() as (client, database):
        response = await client.patch(
            f"/api/v1/employees/{EMPLOYEE_ID}/profile/personal",
            headers=tenant_headers(),
            json={
                "expected_version": 1,
                "expected_employee_version": 1,
                "first_name": "Ayse",
                "preferred_name": "Ayse",
                "phone": None,
            },
        )
        assert response.status_code == 200

        async with database.sessions() as session:
            event = await session.scalar(
                select(AuditEvent).where(
                    AuditEvent.event_type == "employee.personal_profile.updated"
                )
            )

    assert event is not None
    assert event.changed_fields == ["first_name", "phone", "preferred_name"]
    assert event.before_data == {
        "first_name": "Ada",
        "phone": "+90 555 000 0000",
        "preferred_name": "Ada",
    }
    assert event.after_data == {
        "first_name": "Ayse",
        "phone": None,
        "preferred_name": "Ayse",
    }
    assert "email" not in event.before_data
    assert "birth_date" not in event.before_data


async def test_audit_failure_rolls_back_core_and_personal_profile_atomically() -> None:
    async with employee_profile_api(raise_app_exceptions=False) as (client, database):
        with patch.object(
            SqlAlchemyAuditRecorder,
            "record",
            new=AsyncMock(side_effect=RuntimeError("forced audit failure")),
        ):
            response = await client.patch(
                f"/api/v1/employees/{EMPLOYEE_ID}/profile/personal",
                headers=tenant_headers(correlation_id="p4b-audit-rollback"),
                json={
                    "expected_version": 1,
                    "expected_employee_version": 1,
                    "first_name": "Must Roll Back",
                    "preferred_name": "Must Roll Back",
                },
            )

        async with database.sessions() as session:
            employee = await session.get(Employee, EMPLOYEE_ID)
            personal = await session.scalar(
                select(EmployeePersonalProfile).where(
                    EmployeePersonalProfile.tenant_id == TENANT_ID,
                    EmployeePersonalProfile.employee_id == EMPLOYEE_ID,
                )
            )
            audit_count = await session.scalar(select(func.count()).select_from(AuditEvent))

    assert response.status_code == 500
    assert employee is not None
    assert employee.first_name == "Ada"
    assert employee.version == 1
    assert personal is not None
    assert personal.preferred_name == "Ada"
    assert personal.version == 1
    assert audit_count == 0


def _audit_context(request_id: str) -> AuditContext:
    return AuditContext(
        request_id=request_id,
        trace_id="0123456789abcdef0123456789abcdef",
    )
