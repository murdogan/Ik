from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import date
from types import SimpleNamespace
from typing import Annotated
from uuid import UUID

from app.api.auth_dependencies import require_authenticated_session
from app.api.dependencies import (
    get_authenticated_tenant_request_context,
    get_phase0_tenant_request_context,
)
from app.db.base import Base
from app.db.session import get_session
from app.main import create_app
from app.models.department import Department, DepartmentStatus
from app.models.employee import Employee, EmployeeStatus
from app.models.employee_assignment import EmployeeAssignment
from app.models.employee_profile import (
    EmployeeEmploymentProfile,
    EmployeePersonalProfile,
)
from app.models.organization import Branch, BranchStatus, LegalEntity, LegalEntityStatus
from app.models.position import Position, PositionStatus
from app.models.tenant import Tenant, TenantStatus
from app.platform.observability.correlation import replace_request_context
from app.platform.request_context import RequestContext
from fastapi import Depends, Request
from httpx import ASGITransport, AsyncClient
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
PERSONAL_PROFILE_ID = UUID("a1000000-0000-4000-8000-000000000001")
EMPLOYMENT_PROFILE_ID = UUID("a1000000-0000-4000-8000-000000000002")
OTHER_PERSONAL_PROFILE_ID = UUID("a1000000-0000-4000-8000-000000000003")
OTHER_EMPLOYMENT_PROFILE_ID = UUID("a1000000-0000-4000-8000-000000000004")
LEGAL_ENTITY_ID = UUID("c1000000-0000-4000-8000-000000000001")
BRANCH_ID = UUID("c1000000-0000-4000-8000-000000000002")
DEPARTMENT_ID = UUID("c1000000-0000-4000-8000-000000000003")
OLD_DEPARTMENT_ID = UUID("c1000000-0000-4000-8000-000000000004")
POSITION_ID = UUID("c1000000-0000-4000-8000-000000000005")
CURRENT_ASSIGNMENT_ID = UUID("d1000000-0000-4000-8000-000000000001")
HISTORICAL_ASSIGNMENT_ID = UUID("d1000000-0000-4000-8000-000000000002")
ACTOR_ID = UUID("e1000000-0000-4000-8000-000000000001")


@dataclass(frozen=True)
class EmployeeProfileDatabase:
    engine: AsyncEngine
    sessions: async_sessionmaker[AsyncSession]


def get_profile_test_request_context(
    request: Request,
    context: Annotated[
        RequestContext,
        Depends(get_phase0_tenant_request_context),
    ],
) -> RequestContext:
    return replace_request_context(request, context.derive(actor_id=ACTOR_ID))


@asynccontextmanager
async def employee_profile_database() -> AsyncIterator[EmployeeProfileDatabase]:
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        use_insertmanyvalues=False,
    )
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    async with sessions() as session:
        session.add_all(_seed_records())
        await session.commit()
    try:
        yield EmployeeProfileDatabase(engine=engine, sessions=sessions)
    finally:
        await engine.dispose()


@asynccontextmanager
async def employee_profile_api(
    *,
    permissions: tuple[str, ...] = (
        "employee:read:tenant",
        "employee:update:tenant",
    ),
    raise_app_exceptions: bool = True,
) -> AsyncIterator[tuple[AsyncClient, EmployeeProfileDatabase]]:
    async with employee_profile_database() as database:

        async def override_session() -> AsyncIterator[AsyncSession]:
            async with database.sessions() as session:
                yield session

        app = create_app()
        app.dependency_overrides[get_session] = override_session
        app.dependency_overrides[get_authenticated_tenant_request_context] = (
            get_profile_test_request_context
        )
        app.dependency_overrides[require_authenticated_session] = lambda: SimpleNamespace(
            user=SimpleNamespace(permissions=permissions)
        )
        async with AsyncClient(
            transport=ASGITransport(
                app=app,
                raise_app_exceptions=raise_app_exceptions,
            ),
            base_url="http://testserver",
        ) as client:
            yield client, database


def tenant_headers(
    tenant_id: UUID = TENANT_ID,
    *,
    correlation_id: str | None = None,
) -> dict[str, str]:
    headers = {"X-Tenant-Id": str(tenant_id)}
    if correlation_id is not None:
        headers["X-Correlation-Id"] = correlation_id
    return headers


def _seed_records() -> list[object]:
    return [
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
            email="ada@example.test",
            department="Stale legacy department",
            position="Stale legacy position",
            status=EmployeeStatus.ACTIVE.value,
            employment_start_date=date(2026, 7, 1),
        ),
        Employee(
            id=OTHER_EMPLOYEE_ID,
            tenant_id=OTHER_TENANT_ID,
            employee_number="OT-001",
            first_name="Other",
            last_name="Employee",
            email="other@example.test",
            department="People",
            position="Partner",
            status=EmployeeStatus.ACTIVE.value,
            employment_start_date=date(2026, 6, 1),
        ),
        EmployeePersonalProfile(
            id=PERSONAL_PROFILE_ID,
            tenant_id=TENANT_ID,
            employee_id=EMPLOYEE_ID,
            preferred_name="Ada",
            birth_date=date(1992, 5, 14),
            phone="+90 555 000 0000",
        ),
        EmployeeEmploymentProfile(
            id=EMPLOYMENT_PROFILE_ID,
            tenant_id=TENANT_ID,
            employee_id=EMPLOYEE_ID,
            contract_type="indefinite",
            work_type="full_time",
        ),
        EmployeePersonalProfile(
            id=OTHER_PERSONAL_PROFILE_ID,
            tenant_id=OTHER_TENANT_ID,
            employee_id=OTHER_EMPLOYEE_ID,
            preferred_name="Other",
        ),
        EmployeeEmploymentProfile(
            id=OTHER_EMPLOYMENT_PROFILE_ID,
            tenant_id=OTHER_TENANT_ID,
            employee_id=OTHER_EMPLOYEE_ID,
        ),
        LegalEntity(
            id=LEGAL_ENTITY_ID,
            tenant_id=TENANT_ID,
            code="WF",
            name="Wealthy Falcon",
            registered_name="Wealthy Falcon A.S.",
            timezone="Europe/Istanbul",
            status=LegalEntityStatus.ACTIVE.value,
            is_default=True,
        ),
        Branch(
            id=BRANCH_ID,
            tenant_id=TENANT_ID,
            legal_entity_id=LEGAL_ENTITY_ID,
            code="IST",
            name="Istanbul",
            timezone="Europe/Istanbul",
            status=BranchStatus.ACTIVE.value,
        ),
        Department(
            id=DEPARTMENT_ID,
            tenant_id=TENANT_ID,
            code="ENG",
            name="Engineering",
            status=DepartmentStatus.ACTIVE.value,
        ),
        Department(
            id=OLD_DEPARTMENT_ID,
            tenant_id=TENANT_ID,
            code="PEOPLE",
            name="People",
            status=DepartmentStatus.ACTIVE.value,
        ),
        Position(
            id=POSITION_ID,
            tenant_id=TENANT_ID,
            code="BE",
            title="Backend Engineer",
            status=PositionStatus.ACTIVE.value,
        ),
        EmployeeAssignment(
            id=HISTORICAL_ASSIGNMENT_ID,
            tenant_id=TENANT_ID,
            employee_id=EMPLOYEE_ID,
            legal_entity_id=LEGAL_ENTITY_ID,
            branch_id=BRANCH_ID,
            department_id=OLD_DEPARTMENT_ID,
            position_id=POSITION_ID,
            manager_user_id=None,
            supersedes_assignment_id=None,
            effective_from=date(2026, 1, 1),
            effective_to=date(2026, 7, 1),
            change_reason="Initial assignment",
            created_by_user_id=None,
        ),
        EmployeeAssignment(
            id=CURRENT_ASSIGNMENT_ID,
            tenant_id=TENANT_ID,
            employee_id=EMPLOYEE_ID,
            legal_entity_id=LEGAL_ENTITY_ID,
            branch_id=BRANCH_ID,
            department_id=DEPARTMENT_ID,
            position_id=POSITION_ID,
            manager_user_id=None,
            supersedes_assignment_id=HISTORICAL_ASSIGNMENT_ID,
            effective_from=date(2026, 7, 1),
            effective_to=None,
            change_reason="Engineering transfer",
            created_by_user_id=None,
        ),
    ]
