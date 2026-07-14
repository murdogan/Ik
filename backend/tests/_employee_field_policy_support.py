from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace
from uuid import UUID

from app.api.auth_dependencies import (
    get_authenticated_request_context,
    require_authenticated_session,
)
from app.api.dependencies import get_authenticated_tenant_request_context
from app.api.employee_assignments import get_employee_assignment_service
from app.db.session import get_session
from app.main import create_app
from app.models.employee import Employee, EmployeeStatus
from app.models.employee_account_link import EmployeeAccountLink
from app.models.employee_assignment import EmployeeAssignment
from app.models.employee_profile import (
    EmployeeEmploymentProfile,
    EmployeePersonalProfile,
)
from app.models.tenant import TenantFeatureFlag
from app.models.user import User, UserStatus
from app.modules.core.domain.feature_flags import FeatureFlagKey
from app.platform.observability.correlation import (
    get_or_create_request_context,
    replace_request_context,
)
from app.platform.request_context import AuthenticationStrength, RequestContext
from app.platform.tenancy import TenantContext
from app.services.employee_assignment_service import EmployeeAssignmentService
from fastapi import Request
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from tests._employee_account_link_support import (
    MEMBERSHIP_ID,
    USER_ID,
    employee_account_link_database,
)
from tests._employee_profile_support import (
    BRANCH_ID,
    CURRENT_ASSIGNMENT_ID,
    DEPARTMENT_ID,
    EMPLOYEE_ID,
    LEGAL_ENTITY_ID,
    OTHER_EMPLOYEE_ID,
    POSITION_ID,
    TENANT_ID,
    EmployeeProfileDatabase,
)

TODAY = date(2026, 7, 14)

MANAGER_ID = UUID("d4000000-0000-4000-8000-000000000001")
OTHER_MANAGER_ID = UUID("d4000000-0000-4000-8000-000000000002")
DIRECT_REPORT_USER_ID = UUID("d4000000-0000-4000-8000-000000000003")

UNRELATED_EMPLOYEE_ID = UUID("d4100000-0000-4000-8000-000000000001")
FORMER_EMPLOYEE_ID = UUID("d4100000-0000-4000-8000-000000000002")
FUTURE_EMPLOYEE_ID = UUID("d4100000-0000-4000-8000-000000000003")
ARCHIVED_EMPLOYEE_ID = UUID("d4100000-0000-4000-8000-000000000004")
INDIRECT_EMPLOYEE_ID = UUID("d4100000-0000-4000-8000-000000000005")
GUESSED_EMPLOYEE_ID = UUID("ffffffff-ffff-4fff-8fff-ffffffffffff")

RAW_PHONE = "+90 555 000 0000"
RAW_BIRTH_DATE = "1992-05-14"
RESTRICTED_QUERY_VALUE = "TR-SENSITIVE-12345678901"


@asynccontextmanager
async def employee_field_policy_database() -> AsyncIterator[EmployeeProfileDatabase]:
    async with employee_account_link_database() as database:
        async with database.sessions() as session:
            session.add(
                TenantFeatureFlag(
                    tenant_id=TENANT_ID,
                    key=FeatureFlagKey.ORGANIZATION.value,
                    enabled=True,
                )
            )
            session.add_all(_manager_users())
            await session.flush()

            current = await session.get(EmployeeAssignment, CURRENT_ASSIGNMENT_ID)
            assert current is not None
            current.manager_user_id = MANAGER_ID

            session.add_all(_manager_scope_records())
            session.add(
                EmployeeAccountLink(
                    id=UUID("d4500000-0000-4000-8000-000000000001"),
                    tenant_id=TENANT_ID,
                    employee_id=EMPLOYEE_ID,
                    membership_id=MEMBERSHIP_ID,
                )
            )
            await session.commit()
        yield database


@asynccontextmanager
async def employee_field_policy_api(
    database: EmployeeProfileDatabase,
    *,
    actor_id: UUID,
    permissions: tuple[str, ...],
    membership_id: UUID | None = None,
    raise_app_exceptions: bool = True,
) -> AsyncIterator[AsyncClient]:
    async def override_session() -> AsyncIterator[AsyncSession]:
        async with database.sessions() as session:
            yield session

    def override_request_context(request: Request) -> RequestContext:
        context = get_or_create_request_context(request)
        return replace_request_context(
            request,
            context.derive(
                tenant=TenantContext(tenant_id=TENANT_ID, slug="wealthy-falcon"),
                actor_id=actor_id,
                membership_id=membership_id,
                authentication_strength=AuthenticationStrength.SINGLE_FACTOR,
            ),
        )

    def override_tenant_request_context(request: Request) -> RequestContext:
        return override_request_context(request)

    app = create_app()
    app.dependency_overrides[get_session] = override_session
    app.dependency_overrides[get_authenticated_request_context] = override_request_context
    app.dependency_overrides[get_authenticated_tenant_request_context] = (
        override_tenant_request_context
    )
    app.dependency_overrides[require_authenticated_session] = lambda: SimpleNamespace(
        user=SimpleNamespace(permissions=permissions)
    )
    app.dependency_overrides[get_employee_assignment_service] = lambda: EmployeeAssignmentService(
        session_factory=database.sessions,
        today_factory=lambda: TODAY,
    )

    async with AsyncClient(
        transport=ASGITransport(
            app=app,
            raise_app_exceptions=raise_app_exceptions,
        ),
        base_url="http://testserver",
    ) as client:
        yield client


def manager_request_context() -> RequestContext:
    return RequestContext(
        request_id="p4d-manager-service",
        trace_id="d4000000000040008000000000000001",
        tenant=TenantContext(tenant_id=TENANT_ID, slug="wealthy-falcon"),
        actor_id=MANAGER_ID,
        authentication_strength=AuthenticationStrength.SINGLE_FACTOR,
    )


def request_headers(request_id: str = "p4d-manager-api") -> dict[str, str]:
    return {"X-Request-Id": request_id}


def _manager_users() -> list[User]:
    return [
        User(
            id=MANAGER_ID,
            tenant_id=TENANT_ID,
            email="manager@example.test",
            full_name="Mina Manager",
            status=UserStatus.ACTIVE.value,
            password_hash="test-hash",
        ),
        User(
            id=OTHER_MANAGER_ID,
            tenant_id=TENANT_ID,
            email="other-manager@example.test",
            full_name="Other Manager",
            status=UserStatus.ACTIVE.value,
            password_hash="test-hash",
        ),
        User(
            id=DIRECT_REPORT_USER_ID,
            tenant_id=TENANT_ID,
            email="direct-report@example.test",
            full_name="Ada Direct Report",
            status=UserStatus.ACTIVE.value,
            password_hash="test-hash",
        ),
    ]


def _manager_scope_records() -> list[object]:
    records: list[object] = []
    employee_specs = (
        (UNRELATED_EMPLOYEE_ID, "WF-101", "Una", "Related", None),
        (FORMER_EMPLOYEE_ID, "WF-102", "Fora", "Former", None),
        (FUTURE_EMPLOYEE_ID, "WF-103", "Fia", "Future", None),
        (
            ARCHIVED_EMPLOYEE_ID,
            "WF-104",
            "Arda",
            "Archived",
            datetime(2026, 7, 13, tzinfo=UTC),
        ),
        (INDIRECT_EMPLOYEE_ID, "WF-105", "Indra", "Indirect", None),
    )
    for index, (employee_id, number, first_name, last_name, archived_at) in enumerate(
        employee_specs,
        start=1,
    ):
        records.extend(
            (
                Employee(
                    id=employee_id,
                    tenant_id=TENANT_ID,
                    employee_number=number,
                    first_name=first_name,
                    last_name=last_name,
                    email=f"{first_name.lower()}@example.test",
                    department="Stale legacy department",
                    position="Stale legacy position",
                    status=EmployeeStatus.ACTIVE.value,
                    employment_start_date=date(2025, 1, index),
                    archived_at=archived_at,
                ),
                EmployeePersonalProfile(
                    id=UUID(f"d4200000-0000-4000-8000-{index:012d}"),
                    tenant_id=TENANT_ID,
                    employee_id=employee_id,
                    preferred_name=first_name,
                    birth_date=date(1990, 1, index),
                    phone=f"+90 555 100 00{index:02d}",
                ),
                EmployeeEmploymentProfile(
                    id=UUID(f"d4300000-0000-4000-8000-{index:012d}"),
                    tenant_id=TENANT_ID,
                    employee_id=employee_id,
                    contract_type="indefinite",
                    work_type="full_time",
                ),
            )
        )

    records.extend(
        (
            _assignment(
                UUID("d4400000-0000-4000-8000-000000000001"),
                UNRELATED_EMPLOYEE_ID,
                OTHER_MANAGER_ID,
                effective_from=date(2025, 1, 1),
            ),
            _assignment(
                UUID("d4400000-0000-4000-8000-000000000002"),
                FORMER_EMPLOYEE_ID,
                MANAGER_ID,
                effective_from=date(2025, 1, 1),
                effective_to=date(2026, 7, 1),
            ),
            _assignment(
                UUID("d4400000-0000-4000-8000-000000000003"),
                FORMER_EMPLOYEE_ID,
                OTHER_MANAGER_ID,
                effective_from=date(2026, 7, 1),
            ),
            _assignment(
                UUID("d4400000-0000-4000-8000-000000000004"),
                FUTURE_EMPLOYEE_ID,
                OTHER_MANAGER_ID,
                effective_from=date(2026, 1, 1),
                effective_to=TODAY + timedelta(days=1),
            ),
            _assignment(
                UUID("d4400000-0000-4000-8000-000000000005"),
                FUTURE_EMPLOYEE_ID,
                MANAGER_ID,
                effective_from=TODAY + timedelta(days=1),
            ),
            _assignment(
                UUID("d4400000-0000-4000-8000-000000000006"),
                ARCHIVED_EMPLOYEE_ID,
                MANAGER_ID,
                effective_from=date(2025, 1, 1),
            ),
            _assignment(
                UUID("d4400000-0000-4000-8000-000000000007"),
                INDIRECT_EMPLOYEE_ID,
                DIRECT_REPORT_USER_ID,
                effective_from=date(2025, 1, 1),
            ),
        )
    )

    # A large retained history must not add queries or rows to one direct/current profile read.
    for index in range(55):
        effective_from = date(2020, 1, 1) + timedelta(days=index)
        records.append(
            _assignment(
                UUID(f"d4600000-0000-4000-8000-{index + 1:012d}"),
                EMPLOYEE_ID,
                OTHER_MANAGER_ID,
                effective_from=effective_from,
                effective_to=effective_from + timedelta(days=1),
            )
        )
    return records


def _assignment(
    assignment_id: UUID,
    employee_id: UUID,
    manager_id: UUID,
    *,
    effective_from: date,
    effective_to: date | None = None,
) -> EmployeeAssignment:
    return EmployeeAssignment(
        id=assignment_id,
        tenant_id=TENANT_ID,
        employee_id=employee_id,
        legal_entity_id=LEGAL_ENTITY_ID,
        branch_id=BRANCH_ID,
        department_id=DEPARTMENT_ID,
        position_id=POSITION_ID,
        manager_user_id=manager_id,
        effective_from=effective_from,
        effective_to=effective_to,
        change_reason="P4D scope fixture",
        created_by_user_id=None,
    )


__all__ = [
    "ARCHIVED_EMPLOYEE_ID",
    "EMPLOYEE_ID",
    "FORMER_EMPLOYEE_ID",
    "FUTURE_EMPLOYEE_ID",
    "GUESSED_EMPLOYEE_ID",
    "INDIRECT_EMPLOYEE_ID",
    "MANAGER_ID",
    "MEMBERSHIP_ID",
    "OTHER_EMPLOYEE_ID",
    "RAW_BIRTH_DATE",
    "RAW_PHONE",
    "RESTRICTED_QUERY_VALUE",
    "TENANT_ID",
    "TODAY",
    "UNRELATED_EMPLOYEE_ID",
    "USER_ID",
    "employee_field_policy_api",
    "employee_field_policy_database",
    "manager_request_context",
    "request_headers",
]
