from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import date
from types import SimpleNamespace
from typing import Annotated
from uuid import UUID

from app.api.auth_dependencies import require_authenticated_session
from app.api.dependencies import (
    get_authenticated_tenant_request_context,
    get_phase0_tenant_request_context,
)
from app.db.session import get_session
from app.main import create_app
from app.models.employee import Employee, EmployeeStatus
from app.models.identity import Identity, IdentityStatus, MembershipStatus, TenantMembership
from app.models.user import User, UserStatus
from app.platform.observability.correlation import replace_request_context
from app.platform.request_context import RequestContext
from fastapi import Depends, Request
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from tests._employee_profile_support import (
    EMPLOYEE_ID,
    OTHER_EMPLOYEE_ID,
    OTHER_TENANT_ID,
    TENANT_ID,
    EmployeeProfileDatabase,
    employee_profile_database,
)

IDENTITY_ID = UUID("f1000000-0000-4000-8000-000000000001")
SECOND_IDENTITY_ID = UUID("f1000000-0000-4000-8000-000000000002")
USER_ID = UUID("f2000000-0000-4000-8000-000000000001")
SECOND_USER_ID = UUID("f2000000-0000-4000-8000-000000000002")
OTHER_TENANT_USER_ID = UUID("f2000000-0000-4000-8000-000000000003")
MEMBERSHIP_ID = UUID("f3000000-0000-4000-8000-000000000001")
SECOND_MEMBERSHIP_ID = UUID("f3000000-0000-4000-8000-000000000002")
OTHER_TENANT_MEMBERSHIP_ID = UUID("f3000000-0000-4000-8000-000000000003")
SECOND_EMPLOYEE_ID = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaa02")


def get_account_link_test_request_context(
    request: Request,
    context: Annotated[
        RequestContext,
        Depends(get_phase0_tenant_request_context),
    ],
) -> RequestContext:
    return replace_request_context(
        request,
        context.derive(actor_id=USER_ID, membership_id=MEMBERSHIP_ID),
    )


@asynccontextmanager
async def employee_account_link_database() -> AsyncIterator[EmployeeProfileDatabase]:
    async with employee_profile_database() as database:
        async with database.sessions() as session:
            session.add_all(_account_records())
            await session.commit()
        yield database


@asynccontextmanager
async def employee_account_link_api(
    *,
    permissions: tuple[str, ...] = (
        "employee:read:own",
        "employee:read:tenant",
        "employee:update:tenant",
    ),
    raise_app_exceptions: bool = True,
) -> AsyncIterator[tuple[AsyncClient, EmployeeProfileDatabase]]:
    async with employee_account_link_database() as database:

        async def override_session() -> AsyncIterator[AsyncSession]:
            async with database.sessions() as session:
                yield session

        app = create_app()
        app.dependency_overrides[get_session] = override_session
        app.dependency_overrides[get_authenticated_tenant_request_context] = (
            get_account_link_test_request_context
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


def tenant_headers() -> dict[str, str]:
    return {"X-Tenant-Id": str(TENANT_ID)}


def _account_records() -> list[object]:
    return [
        Identity(
            id=IDENTITY_ID,
            email="ada@example.test",
            status=IdentityStatus.ACTIVE.value,
            password_hash="test-hash",
        ),
        Identity(
            id=SECOND_IDENTITY_ID,
            email="grace@example.test",
            status=IdentityStatus.ACTIVE.value,
            password_hash="test-hash",
        ),
        User(
            id=USER_ID,
            tenant_id=TENANT_ID,
            email="ada@example.test",
            full_name="Ada Account",
            status=UserStatus.ACTIVE.value,
            password_hash="test-hash",
            permission_version=1,
        ),
        User(
            id=SECOND_USER_ID,
            tenant_id=TENANT_ID,
            email="grace@example.test",
            full_name="Grace Account",
            status=UserStatus.ACTIVE.value,
            password_hash="test-hash",
            permission_version=1,
        ),
        User(
            id=OTHER_TENANT_USER_ID,
            tenant_id=OTHER_TENANT_ID,
            email="ada@example.test",
            full_name="Ada Other Tenant",
            status=UserStatus.ACTIVE.value,
            password_hash="test-hash",
            permission_version=1,
        ),
        TenantMembership(
            id=MEMBERSHIP_ID,
            tenant_id=TENANT_ID,
            identity_id=IDENTITY_ID,
            legacy_user_id=USER_ID,
            full_name="Ada Account",
            status=MembershipStatus.ACTIVE.value,
            permission_version=1,
        ),
        Employee(
            id=SECOND_EMPLOYEE_ID,
            tenant_id=TENANT_ID,
            employee_number="WF-002",
            first_name="Second",
            last_name="Employee",
            status=EmployeeStatus.ACTIVE.value,
            employment_start_date=date(2026, 7, 1),
        ),
        TenantMembership(
            id=SECOND_MEMBERSHIP_ID,
            tenant_id=TENANT_ID,
            identity_id=SECOND_IDENTITY_ID,
            legacy_user_id=SECOND_USER_ID,
            full_name="Grace Account",
            status=MembershipStatus.ACTIVE.value,
            permission_version=1,
        ),
        TenantMembership(
            id=OTHER_TENANT_MEMBERSHIP_ID,
            tenant_id=OTHER_TENANT_ID,
            identity_id=IDENTITY_ID,
            legacy_user_id=OTHER_TENANT_USER_ID,
            full_name="Ada Other Tenant",
            status=MembershipStatus.ACTIVE.value,
            permission_version=1,
        ),
    ]


__all__ = [
    "EMPLOYEE_ID",
    "IDENTITY_ID",
    "MEMBERSHIP_ID",
    "OTHER_EMPLOYEE_ID",
    "OTHER_TENANT_ID",
    "OTHER_TENANT_MEMBERSHIP_ID",
    "SECOND_IDENTITY_ID",
    "SECOND_EMPLOYEE_ID",
    "SECOND_MEMBERSHIP_ID",
    "SECOND_USER_ID",
    "TENANT_ID",
    "USER_ID",
    "employee_account_link_api",
    "employee_account_link_database",
    "tenant_headers",
]
