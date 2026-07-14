from uuid import UUID

from app.models.employee import Employee
from app.models.employee_profile import (
    EmployeeEmploymentProfile,
    EmployeePersonalProfile,
)
from sqlalchemy import func, select
from tests._employee_profile_support import (
    CURRENT_ASSIGNMENT_ID,
    EMPLOYEE_ID,
    HISTORICAL_ASSIGNMENT_ID,
    OTHER_EMPLOYEE_ID,
    TENANT_ID,
    employee_profile_api,
    tenant_headers,
)


async def test_get_employee_profile_returns_the_exact_employee_360_aggregate() -> None:
    async with employee_profile_api() as (client, _database):
        response = await client.get(
            f"/api/v1/employees/{EMPLOYEE_ID}/profile",
            headers=tenant_headers(correlation_id="p4b-read-aggregate"),
        )

    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"data", "meta"}
    assert body["meta"]["correlation_id"] == "p4b-read-aggregate"
    data = body["data"]
    assert data["core"] == {
        "id": str(EMPLOYEE_ID),
        "employee_number": "WF-001",
        "first_name": "Ada",
        "last_name": "Yilmaz",
        "email": "ada@example.test",
        "status": "active",
        "employee_version": 1,
    }
    assert data["personal"] == {
        "preferred_name": "Ada",
        "birth_date": "1992-05-14",
        "phone": "+90 555 000 0000",
        "version": 1,
    }
    assert data["employment"] == {
        "employment_start_date": "2026-07-01",
        "contract_type": "indefinite",
        "work_type": "full_time",
        "version": 1,
    }
    organization = data["organization"]
    assert organization["history_limit"] == 50
    assert organization["history_truncated"] is False
    assert organization["current_assignment"]["id"] == str(CURRENT_ASSIGNMENT_ID)
    assert organization["current_assignment"]["department"]["name"] == "Engineering"
    assert [row["id"] for row in organization["history"]] == [
        str(CURRENT_ASSIGNMENT_ID),
        str(HISTORICAL_ASSIGNMENT_ID),
    ]
    assert organization["history"][1]["department"]["name"] == "People"
    assert "Stale legacy department" not in repr(organization)


async def test_profile_routes_enforce_read_and_update_permissions_independently() -> None:
    async with employee_profile_api(
        permissions=("employee:read:tenant",),
    ) as (read_client, _database):
        assert (
            await read_client.get(
                f"/api/v1/employees/{EMPLOYEE_ID}/profile",
                headers=tenant_headers(),
            )
        ).status_code == 200
        for section, payload in (
            ("personal", {"expected_version": 1, "preferred_name": "Denied"}),
            ("employment", {"expected_version": 1, "work_type": "part_time"}),
        ):
            denied = await read_client.patch(
                f"/api/v1/employees/{EMPLOYEE_ID}/profile/{section}",
                headers=tenant_headers(),
                json=payload,
            )
            assert denied.status_code == 403
            assert denied.json()["error"]["code"] == "authorization_denied"

    async with employee_profile_api(
        permissions=("employee:update:tenant",),
    ) as (update_client, _database):
        denied_read = await update_client.get(
            f"/api/v1/employees/{EMPLOYEE_ID}/profile",
            headers=tenant_headers(),
        )
        allowed_update = await update_client.patch(
            f"/api/v1/employees/{EMPLOYEE_ID}/profile/personal",
            headers=tenant_headers(),
            json={"expected_version": 1, "preferred_name": "A."},
        )
        assert denied_read.status_code == 403
        assert denied_read.json()["error"]["code"] == "authorization_denied"
        assert allowed_update.status_code == 200


async def test_profile_patch_validation_is_strict_and_correlated() -> None:
    invalid_requests = (
        (
            "personal",
            {"preferred_name": "Missing section version"},
        ),
        (
            "personal",
            {"expected_version": 1, "first_name": "Missing employee version"},
        ),
        (
            "personal",
            {"expected_version": 1, "gender": "female"},
        ),
        (
            "employment",
            {"expected_version": 1, "employment_start_date": "2026-07-02"},
        ),
        (
            "employment",
            {"expected_version": 1, "contract_type": "contractor"},
        ),
        (
            "employment",
            {"expected_version": 1, "status": "terminated"},
        ),
    )
    async with employee_profile_api() as (client, _database):
        for index, (section, payload) in enumerate(invalid_requests):
            correlation_id = f"p4b-validation-{index}"
            response = await client.patch(
                f"/api/v1/employees/{EMPLOYEE_ID}/profile/{section}",
                headers=tenant_headers(correlation_id=correlation_id),
                json=payload,
            )
            assert response.status_code == 422
            assert response.json()["error"] == {
                "code": "employee_validation_error",
                "message": "Employee request validation failed",
                "details": None,
                "correlation_id": correlation_id,
            }


async def test_profile_read_and_updates_do_not_leak_cross_tenant_existence() -> None:
    missing_id = UUID("ffffffff-ffff-4fff-8fff-ffffffffffff")
    async with employee_profile_api() as (client, _database):
        cross_read = await client.get(
            f"/api/v1/employees/{OTHER_EMPLOYEE_ID}/profile",
            headers=tenant_headers(correlation_id="p4b-not-found"),
        )
        missing_read = await client.get(
            f"/api/v1/employees/{missing_id}/profile",
            headers=tenant_headers(correlation_id="p4b-not-found"),
        )
        cross_update = await client.patch(
            f"/api/v1/employees/{OTHER_EMPLOYEE_ID}/profile/personal",
            headers=tenant_headers(correlation_id="p4b-not-found"),
            json={"expected_version": 1, "preferred_name": "Leak"},
        )

    assert cross_read.status_code == 404
    assert missing_read.status_code == 404
    assert cross_update.status_code == 404
    assert cross_read.json() == missing_read.json() == cross_update.json()
    assert cross_read.json()["error"]["code"] == "employee_not_found"


async def test_personal_and_employment_versions_increment_independently_once() -> None:
    async with employee_profile_api() as (client, _database):
        personal = await client.patch(
            f"/api/v1/employees/{EMPLOYEE_ID}/profile/personal",
            headers=tenant_headers(),
            json={"expected_version": 1, "preferred_name": "A."},
        )
        employment = await client.patch(
            f"/api/v1/employees/{EMPLOYEE_ID}/profile/employment",
            headers=tenant_headers(),
            json={
                "expected_version": 1,
                "contract_type": "fixed_term",
                "work_type": "part_time",
            },
        )
        aggregate = await client.get(
            f"/api/v1/employees/{EMPLOYEE_ID}/profile",
            headers=tenant_headers(),
        )

    assert personal.status_code == 200
    assert set(personal.json()["data"]) == {"core", "personal"}
    assert personal.json()["data"]["core"]["employee_version"] == 1
    assert personal.json()["data"]["personal"]["version"] == 2
    assert employment.status_code == 200
    assert set(employment.json()["data"]) == {"core", "employment"}
    assert employment.json()["data"]["core"]["employee_version"] == 1
    assert employment.json()["data"]["employment"]["version"] == 2
    assert aggregate.json()["data"]["personal"]["version"] == 2
    assert aggregate.json()["data"]["employment"]["version"] == 2
    assert aggregate.json()["data"]["core"]["employee_version"] == 1


async def test_stale_profile_writes_return_409_without_partial_core_updates() -> None:
    async with employee_profile_api() as (client, _database):
        assert (
            await client.patch(
                f"/api/v1/employees/{EMPLOYEE_ID}/profile/personal",
                headers=tenant_headers(),
                json={"expected_version": 1, "preferred_name": "Fresh personal"},
            )
        ).status_code == 200
        stale_personal = await client.patch(
            f"/api/v1/employees/{EMPLOYEE_ID}/profile/personal",
            headers=tenant_headers(correlation_id="p4b-personal-stale"),
            json={
                "expected_version": 1,
                "expected_employee_version": 1,
                "first_name": "Must Not Persist",
                "phone": "+90 555 999 9999",
            },
        )

        assert (
            await client.patch(
                f"/api/v1/employees/{EMPLOYEE_ID}/profile/employment",
                headers=tenant_headers(),
                json={"expected_version": 1, "work_type": "part_time"},
            )
        ).status_code == 200
        stale_employment = await client.patch(
            f"/api/v1/employees/{EMPLOYEE_ID}/profile/employment",
            headers=tenant_headers(correlation_id="p4b-employment-stale"),
            json={
                "expected_version": 1,
                "expected_employee_version": 1,
                "employment_start_date": "2026-08-01",
                "contract_type": "fixed_term",
            },
        )
        aggregate = await client.get(
            f"/api/v1/employees/{EMPLOYEE_ID}/profile",
            headers=tenant_headers(),
        )

    for response, correlation_id in (
        (stale_personal, "p4b-personal-stale"),
        (stale_employment, "p4b-employment-stale"),
    ):
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "concurrent_write_conflict"
        assert response.json()["error"]["correlation_id"] == correlation_id
    data = aggregate.json()["data"]
    assert data["core"]["first_name"] == "Ada"
    assert data["personal"]["phone"] == "+90 555 000 0000"
    assert data["employment"]["employment_start_date"] == "2026-07-01"
    assert data["employment"]["contract_type"] == "indefinite"


async def test_core_and_section_updates_increment_their_own_versions_once() -> None:
    async with employee_profile_api() as (client, _database):
        personal = await client.patch(
            f"/api/v1/employees/{EMPLOYEE_ID}/profile/personal",
            headers=tenant_headers(),
            json={
                "expected_version": 1,
                "expected_employee_version": 1,
                "first_name": "Ayse",
                "preferred_name": "Ayse",
            },
        )
        employment = await client.patch(
            f"/api/v1/employees/{EMPLOYEE_ID}/profile/employment",
            headers=tenant_headers(),
            json={
                "expected_version": 1,
                "expected_employee_version": 2,
                "employment_start_date": "2026-07-02",
                "contract_type": "fixed_term",
            },
        )
        aggregate = await client.get(
            f"/api/v1/employees/{EMPLOYEE_ID}/profile",
            headers=tenant_headers(),
        )

    assert personal.status_code == 200
    assert personal.json()["data"]["core"]["employee_version"] == 2
    assert personal.json()["data"]["personal"]["version"] == 2
    assert employment.status_code == 200
    assert employment.json()["data"]["core"]["employee_version"] == 3
    assert employment.json()["data"]["employment"]["version"] == 2
    assert aggregate.json()["data"]["personal"]["version"] == 2
    assert aggregate.json()["data"]["employment"]["version"] == 2


async def test_core_only_profile_updates_consume_their_section_versions_once() -> None:
    async with employee_profile_api() as (client, _database):
        personal = await client.patch(
            f"/api/v1/employees/{EMPLOYEE_ID}/profile/personal",
            headers=tenant_headers(),
            json={
                "expected_version": 1,
                "expected_employee_version": 1,
                "first_name": "Ayse",
            },
        )
        employment = await client.patch(
            f"/api/v1/employees/{EMPLOYEE_ID}/profile/employment",
            headers=tenant_headers(),
            json={
                "expected_version": 1,
                "expected_employee_version": 2,
                "employment_start_date": "2026-07-02",
            },
        )
        stale_personal = await client.patch(
            f"/api/v1/employees/{EMPLOYEE_ID}/profile/personal",
            headers=tenant_headers(),
            json={"expected_version": 1, "phone": "+90 555 111 1111"},
        )
        stale_employment = await client.patch(
            f"/api/v1/employees/{EMPLOYEE_ID}/profile/employment",
            headers=tenant_headers(),
            json={"expected_version": 1, "work_type": "part_time"},
        )

    assert personal.status_code == 200
    assert personal.json()["data"]["core"]["employee_version"] == 2
    assert personal.json()["data"]["personal"]["version"] == 2
    assert employment.status_code == 200
    assert employment.json()["data"]["core"]["employee_version"] == 3
    assert employment.json()["data"]["employment"]["version"] == 2
    for stale in (stale_personal, stale_employment):
        assert stale.status_code == 409
        assert stale.json()["error"]["code"] == "concurrent_write_conflict"


async def test_legacy_employee_create_creates_exactly_one_profile_pair() -> None:
    async with employee_profile_api() as (client, database):
        response = await client.post(
            "/api/v1/employees",
            headers=tenant_headers(),
            json={
                "employee_number": "WF-NEW",
                "first_name": "New",
                "last_name": "Employee",
                "email": "new@example.test",
                "employment_start_date": "2026-07-14",
            },
        )
        assert response.status_code == 201
        employee_id = UUID(response.json()["id"])

        async with database.sessions() as session:
            employee = await session.get(Employee, employee_id)
            personal_count = await session.scalar(
                select(func.count())
                .select_from(EmployeePersonalProfile)
                .where(
                    EmployeePersonalProfile.tenant_id == TENANT_ID,
                    EmployeePersonalProfile.employee_id == employee_id,
                )
            )
            employment_count = await session.scalar(
                select(func.count())
                .select_from(EmployeeEmploymentProfile)
                .where(
                    EmployeeEmploymentProfile.tenant_id == TENANT_ID,
                    EmployeeEmploymentProfile.employee_id == employee_id,
                )
            )
            personal = await session.scalar(
                select(EmployeePersonalProfile).where(
                    EmployeePersonalProfile.employee_id == employee_id
                )
            )
            employment = await session.scalar(
                select(EmployeeEmploymentProfile).where(
                    EmployeeEmploymentProfile.employee_id == employee_id
                )
            )

    assert employee is not None
    assert personal_count == 1
    assert employment_count == 1
    assert personal is not None and personal.version == 1
    assert employment is not None and employment.version == 1
