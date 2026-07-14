from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from types import SimpleNamespace
from uuid import UUID

from app.api.auth_dependencies import require_authenticated_session
from app.api.dependencies import get_authenticated_tenant_request_context
from app.db.session import get_session
from app.main import create_app
from app.models.employee_account_link import EmployeeAccountLink
from app.platform.request_context import AuthenticationStrength, RequestContext
from app.platform.tenancy import TenantContext
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from tests._employee_account_link_support import (
    EMPLOYEE_ID,
    MEMBERSHIP_ID,
    TENANT_ID,
    USER_ID,
    employee_account_link_database,
    get_account_link_test_request_context,
    tenant_headers,
)
from tests._employee_profile_support import EmployeeProfileDatabase

ACCOUNT_LINK_ID = UUID("f4000000-0000-4000-8000-000000000001")


@asynccontextmanager
async def employee_profile_change_request_database() -> AsyncIterator[EmployeeProfileDatabase]:
    async with employee_account_link_database() as database:
        async with database.sessions() as session:
            session.add(
                EmployeeAccountLink(
                    id=ACCOUNT_LINK_ID,
                    tenant_id=TENANT_ID,
                    employee_id=EMPLOYEE_ID,
                    membership_id=MEMBERSHIP_ID,
                    version=1,
                )
            )
            await session.commit()
        yield database


@asynccontextmanager
async def employee_profile_change_request_api(
    *,
    permissions: tuple[str, ...] = (
        "employee:read:own",
        "employee:read:tenant",
        "employee:update:tenant",
    ),
    raise_app_exceptions: bool = True,
) -> AsyncIterator[tuple[AsyncClient, EmployeeProfileDatabase]]:
    async with employee_profile_change_request_database() as database:

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
            transport=ASGITransport(app=app, raise_app_exceptions=raise_app_exceptions),
            base_url="http://testserver",
        ) as client:
            yield client, database


def change_request_context() -> RequestContext:
    return RequestContext(
        request_id="req-p4e-test",
        trace_id="1234567890abcdef1234567890abcdef",
        tenant=TenantContext(tenant_id=TENANT_ID, slug="wealthy-falcon"),
        actor_id=USER_ID,
        membership_id=MEMBERSHIP_ID,
        authentication_strength=AuthenticationStrength.SINGLE_FACTOR,
    )


__all__ = [
    "ACCOUNT_LINK_ID",
    "EMPLOYEE_ID",
    "MEMBERSHIP_ID",
    "TENANT_ID",
    "USER_ID",
    "change_request_context",
    "employee_profile_change_request_api",
    "employee_profile_change_request_database",
    "tenant_headers",
]
