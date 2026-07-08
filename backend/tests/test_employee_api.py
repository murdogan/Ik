from collections.abc import AsyncIterator
from datetime import date
from uuid import UUID

from app.db.base import Base
from app.db.session import get_session
from app.main import create_app
from app.models.employee import Employee, EmployeeStatus
from app.models.tenant import Tenant, TenantStatus
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool

TENANT_ID = UUID("11111111-aaaa-4111-8111-111111111111")
OTHER_TENANT_ID = UUID("22222222-bbbb-4222-8222-222222222222")
EMPLOYEE_ID = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")
OTHER_EMPLOYEE_ID = UUID("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb")


async def _client_with_database() -> tuple[AsyncClient, AsyncEngine]:
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        use_insertmanyvalues=False,
    )
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        session.add_all(
            [
                Tenant(
                    id=TENANT_ID,
                    slug="wealthy-falcon",
                    name="Wealthy Falcon HR",
                    status=TenantStatus.ACTIVE.value,
                    plan_code="core",
                    data_region="tr-1",
                    locale="tr-TR",
                    timezone="Europe/Istanbul",
                ),
                Tenant(
                    id=OTHER_TENANT_ID,
                    slug="other",
                    name="Other Tenant",
                    status=TenantStatus.ACTIVE.value,
                    plan_code="core",
                    data_region="tr-1",
                    locale="tr-TR",
                    timezone="Europe/Istanbul",
                ),
                Employee(
                    id=EMPLOYEE_ID,
                    tenant_id=TENANT_ID,
                    employee_number="WF-001",
                    first_name="Ada",
                    last_name="Yilmaz",
                    email="ada@wealthyfalcon.test",
                    department="People",
                    position="HR Specialist",
                    status=EmployeeStatus.ACTIVE.value,
                    employment_start_date=date(2026, 7, 1),
                ),
                Employee(
                    id=OTHER_EMPLOYEE_ID,
                    tenant_id=OTHER_TENANT_ID,
                    employee_number="OT-001",
                    first_name="Other",
                    last_name="Person",
                    status=EmployeeStatus.ACTIVE.value,
                    employment_start_date=date(2026, 7, 1),
                ),
            ]
        )
        await session.commit()

    async def override_session() -> AsyncIterator[AsyncSession]:
        async with session_factory() as session:
            yield session

    app = create_app()
    app.dependency_overrides[get_session] = override_session

    return (
        AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://testserver",
        ),
        engine,
    )


def _tenant_headers(tenant_id: UUID = TENANT_ID) -> dict[str, str]:
    return {"X-Tenant-Id": str(tenant_id)}


async def test_create_employee_uses_tenant_header_and_server_generated_id() -> None:
    client, engine = await _client_with_database()
    try:
        response = await client.post(
            "/api/v1/employees",
            headers=_tenant_headers(),
            json={
                "employee_number": "WF-002",
                "first_name": "Bora",
                "last_name": "Demir",
                "email": "bora@wealthyfalcon.test",
                "department": "Engineering",
                "position": "Backend Engineer",
                "employment_start_date": "2026-07-08",
            },
        )

        assert response.status_code == 201
        body = response.json()
        assert body["id"]
        assert "tenant_id" not in body
        assert body["employee_number"] == "WF-002"
        assert body["status"] == EmployeeStatus.ACTIVE.value

        async_session = async_sessionmaker(engine, expire_on_commit=False)
        async with async_session() as session:
            created = await session.scalar(
                select(Employee).where(Employee.employee_number == "WF-002")
            )

        assert created is not None
        assert created.tenant_id == TENANT_ID
    finally:
        await client.aclose()
        await engine.dispose()


async def test_create_employee_rejects_client_controlled_tenant_id() -> None:
    client, engine = await _client_with_database()
    try:
        response = await client.post(
            "/api/v1/employees",
            headers=_tenant_headers(),
            json={
                "tenant_id": str(OTHER_TENANT_ID),
                "employee_number": "WF-002",
                "first_name": "Bora",
                "last_name": "Demir",
                "employment_start_date": "2026-07-08",
            },
        )

        assert response.status_code == 422
    finally:
        await client.aclose()
        await engine.dispose()


async def test_list_employees_returns_current_tenant_records_only() -> None:
    client, engine = await _client_with_database()
    try:
        response = await client.get("/api/v1/employees", headers=_tenant_headers())

        assert response.status_code == 200
        assert [employee["employee_number"] for employee in response.json()] == ["WF-001"]
    finally:
        await client.aclose()
        await engine.dispose()


async def test_get_employee_is_tenant_scoped() -> None:
    client, engine = await _client_with_database()
    try:
        response = await client.get(
            f"/api/v1/employees/{EMPLOYEE_ID}",
            headers=_tenant_headers(),
        )
        cross_tenant_response = await client.get(
            f"/api/v1/employees/{OTHER_EMPLOYEE_ID}",
            headers=_tenant_headers(),
        )

        assert response.status_code == 200
        assert response.json()["employee_number"] == "WF-001"
        assert cross_tenant_response.status_code == 404
    finally:
        await client.aclose()
        await engine.dispose()


async def test_update_employee_changes_only_current_tenant_record() -> None:
    client, engine = await _client_with_database()
    try:
        response = await client.patch(
            f"/api/v1/employees/{EMPLOYEE_ID}",
            headers=_tenant_headers(),
            json={"department": "Operations", "email": None},
        )

        assert response.status_code == 200
        assert response.json()["department"] == "Operations"
        assert response.json()["email"] is None

        cross_tenant_response = await client.patch(
            f"/api/v1/employees/{OTHER_EMPLOYEE_ID}",
            headers=_tenant_headers(),
            json={"department": "Operations"},
        )

        assert cross_tenant_response.status_code == 404
    finally:
        await client.aclose()
        await engine.dispose()


async def test_update_employee_rejects_duplicate_employee_number_within_tenant() -> None:
    client, engine = await _client_with_database()
    try:
        create_response = await client.post(
            "/api/v1/employees",
            headers=_tenant_headers(),
            json={
                "employee_number": "WF-002",
                "first_name": "Bora",
                "last_name": "Demir",
                "employment_start_date": "2026-07-08",
            },
        )
        assert create_response.status_code == 201

        response = await client.patch(
            f"/api/v1/employees/{EMPLOYEE_ID}",
            headers=_tenant_headers(),
            json={"employee_number": "WF-002"},
        )

        assert response.status_code == 409
    finally:
        await client.aclose()
        await engine.dispose()


async def test_create_employee_allows_same_employee_number_in_different_tenants() -> None:
    client, engine = await _client_with_database()
    try:
        response = await client.post(
            "/api/v1/employees",
            headers=_tenant_headers(OTHER_TENANT_ID),
            json={
                "employee_number": "WF-001",
                "first_name": "Other",
                "last_name": "Duplicate",
                "employment_start_date": "2026-07-08",
            },
        )

        assert response.status_code == 201
    finally:
        await client.aclose()
        await engine.dispose()


async def test_create_employee_rejects_duplicate_employee_number_within_tenant() -> None:
    client, engine = await _client_with_database()
    try:
        response = await client.post(
            "/api/v1/employees",
            headers=_tenant_headers(),
            json={
                "employee_number": "WF-001",
                "first_name": "Duplicate",
                "last_name": "Person",
                "employment_start_date": "2026-07-08",
            },
        )

        assert response.status_code == 409
    finally:
        await client.aclose()
        await engine.dispose()


async def test_delete_employee_hard_deletes_current_tenant_record() -> None:
    client, engine = await _client_with_database()
    try:
        response = await client.delete(
            f"/api/v1/employees/{EMPLOYEE_ID}",
            headers=_tenant_headers(),
        )
        get_response = await client.get(
            f"/api/v1/employees/{EMPLOYEE_ID}",
            headers=_tenant_headers(),
        )
        cross_tenant_response = await client.delete(
            f"/api/v1/employees/{OTHER_EMPLOYEE_ID}",
            headers=_tenant_headers(),
        )

        assert response.status_code == 204
        assert get_response.status_code == 404
        assert cross_tenant_response.status_code == 404
    finally:
        await client.aclose()
        await engine.dispose()


async def test_employee_routes_require_tenant_header() -> None:
    client, engine = await _client_with_database()
    try:
        response = await client.get("/api/v1/employees")

        assert response.status_code == 422
    finally:
        await client.aclose()
        await engine.dispose()


async def test_employee_routes_are_exposed_in_openapi() -> None:
    client, engine = await _client_with_database()
    try:
        response = await client.get("/openapi.json")

        assert response.status_code == 200
        paths = response.json()["paths"]
        assert "/api/v1/employees" in paths
        assert "/api/v1/employees/{employee_id}" in paths
    finally:
        await client.aclose()
        await engine.dispose()
