from datetime import date, timedelta
from uuid import UUID

import pytest
from app.db.base import Base
from app.models.department import Department
from app.models.employee import Employee
from app.models.employee_assignment import EmployeeAssignment
from app.models.identity import Identity, IdentityStatus, MembershipRole, TenantMembership
from app.models.leave_request import LeaveRequest
from app.models.organization import Branch, BranchStatus, LegalEntity
from app.models.position import Position
from app.models.tenant import Tenant, TenantFeatureFlag, TenantSettings, TenantStatus
from app.models.user import User
from app.modules.core.domain.feature_flags import FeatureFlagKey
from app.services.demo_seed_service import (
    DEMO_EMPLOYEES,
    DEMO_LEAVE_REQUESTS,
    DEMO_TENANTS,
    DEMO_USERS,
    DemoSeedConflictError,
    seed_demo_data,
)
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine
from sqlalchemy.pool import StaticPool


async def _session_with_database() -> tuple[AsyncSession, AsyncEngine]:
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        use_insertmanyvalues=False,
    )
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    return AsyncSession(engine, expire_on_commit=False), engine


async def test_demo_seed_is_idempotent_and_tenant_scoped() -> None:
    session, engine = await _session_with_database()
    try:
        first_result = await seed_demo_data(session)

        employee_fixture = DEMO_EMPLOYEES[0]
        employee = await session.get(Employee, employee_fixture.id)
        assert employee is not None
        employee.department = "Changed"
        tenant_settings = await session.get(TenantSettings, DEMO_TENANTS[0].id)
        assert tenant_settings is not None
        tenant_settings.week_start_day = "sunday"
        default_entity = await session.get(LegalEntity, DEMO_TENANTS[0].id)
        assert default_entity is not None
        default_entity.name = "Preserved legal entity name"

        seeded_assignments = tuple(
            await session.scalars(
                select(EmployeeAssignment).order_by(
                    EmployeeAssignment.tenant_id,
                    EmployeeAssignment.employee_id,
                )
            )
        )
        assert len(seeded_assignments) == len(DEMO_EMPLOYEES)
        seeded_assignment_ids = {assignment.id for assignment in seeded_assignments}
        preserved_assignment = seeded_assignments[0]
        preserved_assignment.change_reason = "Preserved assignment history"

        mixed_case_department = await session.get(
            Department,
            preserved_assignment.department_id,
        )
        mixed_case_position = await session.get(
            Position,
            preserved_assignment.position_id,
        )
        assert mixed_case_department is not None
        assert mixed_case_position is not None
        mixed_case_department.name = "pEoPlE"
        mixed_case_position.title = "pEoPlE oPeRaTiOnS lEaD"
        await session.commit()

        second_result = await seed_demo_data(session)

        assert second_result == first_result
        assert await _count(session, Tenant) == len(DEMO_TENANTS)
        assert await _count(session, TenantSettings) == len(DEMO_TENANTS)
        assert (
            await session.scalar(
                select(func.count())
                .select_from(TenantFeatureFlag)
                .where(
                    TenantFeatureFlag.key == FeatureFlagKey.ORGANIZATION.value,
                    TenantFeatureFlag.enabled.is_(True),
                )
            )
            == len(DEMO_TENANTS)
        )
        assert await _count(session, LegalEntity) == len(DEMO_TENANTS)
        assert await _count(session, Branch) == len(DEMO_TENANTS)
        assert await _count(session, Department) == len(
            {
                (fixture.tenant_key, fixture.department.strip().casefold())
                for fixture in DEMO_EMPLOYEES
            }
        )
        assert await _count(session, Position) == len(
            {
                (fixture.tenant_key, fixture.position.strip().casefold())
                for fixture in DEMO_EMPLOYEES
            }
        )
        assert await _count(session, EmployeeAssignment) == len(DEMO_EMPLOYEES)
        assert await _count(session, User) == len(DEMO_USERS)
        assert await _count(session, Identity) == 4
        assert await _count(session, TenantMembership) == len(DEMO_USERS)
        assert await _count(session, MembershipRole) == len(DEMO_USERS)
        assert await _count(session, Employee) == len(DEMO_EMPLOYEES)
        assert await _count(session, LeaveRequest) == len(DEMO_LEAVE_REQUESTS)
        assert set(second_result.tenant_ids) == {tenant.id for tenant in DEMO_TENANTS}
        shared_identity = await session.scalar(
            select(Identity).where(
                Identity.email_normalized == "admin@wealthyfalcon.demo"
            )
        )
        assert shared_identity is not None
        shared_memberships = tuple(
            await session.scalars(
                select(TenantMembership).where(
                    TenantMembership.identity_id == shared_identity.id
                )
            )
        )
        assert {membership.tenant_id for membership in shared_memberships} == {
            tenant.id for tenant in DEMO_TENANTS
        }

        updated_employee = await session.get(Employee, employee_fixture.id)
        assert updated_employee is not None
        assert updated_employee.department == employee_fixture.department
        preserved_settings = await session.get(TenantSettings, DEMO_TENANTS[0].id)
        assert preserved_settings is not None
        assert preserved_settings.week_start_day == "sunday"
        preserved_entity = await session.get(LegalEntity, DEMO_TENANTS[0].id)
        assert preserved_entity is not None
        assert preserved_entity.name == "Preserved legal entity name"
        assert preserved_entity.is_default is True

        assignments = tuple(
            await session.scalars(
                select(EmployeeAssignment).order_by(
                    EmployeeAssignment.tenant_id,
                    EmployeeAssignment.employee_id,
                )
            )
        )
        assert {assignment.id for assignment in assignments} == seeded_assignment_ids
        preserved_history = await session.get(
            EmployeeAssignment,
            preserved_assignment.id,
        )
        assert preserved_history is not None
        assert preserved_history.change_reason == "Preserved assignment history"

        fixtures_by_employee_id = {
            fixture.id: fixture for fixture in DEMO_EMPLOYEES
        }
        manager_ids_by_tenant_key = {
            fixture.tenant_key: fixture.id
            for fixture in DEMO_USERS
            if fixture.role_code == "manager"
        }
        for assignment in assignments:
            fixture = fixtures_by_employee_id[assignment.employee_id]
            tenant = next(
                tenant
                for tenant in DEMO_TENANTS
                if tenant.key == fixture.tenant_key
            )
            structured_employee = await session.get(Employee, assignment.employee_id)
            branch = await session.get(Branch, assignment.branch_id)
            department = await session.get(Department, assignment.department_id)
            position = await session.get(Position, assignment.position_id)

            assert structured_employee is not None
            assert branch is not None
            assert department is not None
            assert position is not None
            assert assignment.tenant_id == tenant.id
            assert assignment.legal_entity_id == tenant.id
            assert branch.tenant_id == tenant.id
            assert branch.legal_entity_id == tenant.id
            assert branch.status == BranchStatus.ACTIVE.value
            assert branch.archived_at is None
            assert branch.code.startswith("DEMO-B-")
            assert department.name.strip().casefold() == fixture.department.casefold()
            assert position.title.strip().casefold() == fixture.position.casefold()
            assert department.code.startswith("DEMO-D-")
            assert position.code.startswith("DEMO-P-")
            assert assignment.manager_user_id == manager_ids_by_tenant_key[
                fixture.tenant_key
            ]
            assert assignment.created_by_user_id is None
            assert assignment.supersedes_assignment_id is None
            assert assignment.effective_from == fixture.employment_start_date
            assert assignment.effective_to == (
                fixture.employment_end_date + timedelta(days=1)
                if fixture.employment_end_date is not None
                else None
            )
            assert structured_employee.department == fixture.department
            assert structured_employee.position == fixture.position

        team_scope_day = date(2026, 7, 13)
        current_team_counts = {
            tenant_key: sum(
                assignment.manager_user_id == manager_id
                and assignment.effective_from <= team_scope_day
                and (
                    assignment.effective_to is None
                    or assignment.effective_to > team_scope_day
                )
                for assignment in assignments
            )
            for tenant_key, manager_id in manager_ids_by_tenant_key.items()
        }
        assert current_team_counts == {"wealthy_falcon": 5, "atlas": 2}

        leave_requests = list(await session.scalars(select(LeaveRequest)))
        assert leave_requests
        for leave_request in leave_requests:
            employee = await session.get(Employee, leave_request.employee_id)
            requested_by_user = await session.get(User, leave_request.requested_by_user_id)
            decided_by_user = (
                await session.get(User, leave_request.decided_by_user_id)
                if leave_request.decided_by_user_id is not None
                else None
            )

            assert employee is not None
            assert requested_by_user is not None
            assert employee.tenant_id == leave_request.tenant_id
            assert requested_by_user.tenant_id == leave_request.tenant_id
            if decided_by_user is not None:
                assert decided_by_user.tenant_id == leave_request.tenant_id
    finally:
        await session.close()
        await engine.dispose()


async def test_demo_seed_repoints_legacy_membership_and_preserves_old_identity() -> None:
    session, engine = await _session_with_database()
    try:
        await seed_demo_data(session)
        await session.commit()
        atlas_user, shared_identity, atlas_membership = await _restore_legacy_atlas_projection(
            session
        )

        first_result = await seed_demo_data(session)
        await session.commit()
        second_result = await seed_demo_data(session)

        assert second_result == first_result
        await session.refresh(atlas_user)
        await session.refresh(atlas_membership)
        assert atlas_user.email == "admin@wealthyfalcon.demo"
        assert atlas_membership.id == atlas_user.id
        assert atlas_membership.legacy_user_id == atlas_user.id
        assert atlas_membership.identity_id == shared_identity.id
        detached_identity = await session.get(Identity, atlas_user.id)
        assert detached_identity is not None
        assert detached_identity.email_normalized == "admin@atlaspeople.demo"
        assert (
            await session.scalar(
                select(func.count())
                .select_from(TenantMembership)
                .where(TenantMembership.identity_id == detached_identity.id)
            )
            == 0
        )
        assert await _count(session, Identity) == 5
        assert (
            await session.scalar(
                select(func.count(func.distinct(TenantMembership.identity_id)))
            )
            == 4
        )
        assert (
            await session.scalar(
                select(func.count())
                .select_from(MembershipRole)
                .where(MembershipRole.membership_id == atlas_membership.id)
            )
            == 1
        )
    finally:
        await session.close()
        await engine.dispose()


async def test_demo_seed_refuses_to_merge_different_identity_password_hashes() -> None:
    session, engine = await _session_with_database()
    try:
        await seed_demo_data(session)
        await session.commit()
        atlas_user, shared_identity, _atlas_membership = (
            await _restore_legacy_atlas_projection(
                session,
                legacy_password_hash="legacy-atlas-password-hash",
            )
        )
        shared_identity.status = IdentityStatus.ACTIVE.value
        shared_identity.password_hash = "shared-admin-password-hash"
        await session.commit()

        with pytest.raises(
            DemoSeedConflictError,
            match=f"credential hashes disagree for legacy user {atlas_user.id}",
        ):
            await seed_demo_data(session)
    finally:
        await session.close()
        await engine.dispose()


async def test_demo_seed_service_flushes_without_completing_transaction() -> None:
    session, engine = await _session_with_database()
    try:
        await seed_demo_data(session)

        assert session.in_transaction() is True
        await session.rollback()

        async with AsyncSession(engine, expire_on_commit=False) as verification_session:
            assert await _count(verification_session, Tenant) == 0
            assert await _count(verification_session, TenantSettings) == 0
            assert await _count(verification_session, TenantFeatureFlag) == 0
            assert await _count(verification_session, LegalEntity) == 0
            assert await _count(verification_session, User) == 0
            assert await _count(verification_session, Identity) == 0
            assert await _count(verification_session, TenantMembership) == 0
            assert await _count(verification_session, Employee) == 0
            assert await _count(verification_session, LeaveRequest) == 0
    finally:
        await session.close()
        await engine.dispose()


async def test_demo_seed_does_not_rewrite_existing_assignment_history() -> None:
    session, engine = await _session_with_database()
    try:
        await seed_demo_data(session)
        fixture = DEMO_EMPLOYEES[0]
        assignment = await session.scalar(
            select(EmployeeAssignment).where(
                EmployeeAssignment.tenant_id
                == next(
                    tenant.id
                    for tenant in DEMO_TENANTS
                    if tenant.key == fixture.tenant_key
                ),
                EmployeeAssignment.employee_id == fixture.id,
            )
        )
        assert assignment is not None
        assignment_id = assignment.id
        assignment.manager_user_id = None
        assignment.change_reason = "P3I legacy employee backfill"
        await session.commit()

        await seed_demo_data(session)
        await session.flush()

        preserved = await session.get(EmployeeAssignment, assignment_id)
        assert preserved is not None
        assert preserved.manager_user_id is None
        assert preserved.change_reason == "P3I legacy employee backfill"
        assert (
            await session.scalar(
                select(func.count())
                .select_from(EmployeeAssignment)
                .where(
                    EmployeeAssignment.tenant_id == preserved.tenant_id,
                    EmployeeAssignment.employee_id == fixture.id,
                )
            )
            == 1
        )
    finally:
        await session.close()
        await engine.dispose()


async def test_demo_seed_rejects_conflicting_existing_tenant_slug() -> None:
    session, engine = await _session_with_database()
    try:
        tenant_fixture = DEMO_TENANTS[0]
        session.add(
            Tenant(
                id=UUID("aaaaaaaa-9999-4999-8999-aaaaaaaaaaaa"),
                slug=tenant_fixture.slug,
                name="Conflicting Tenant",
                status=TenantStatus.ACTIVE.value,
                plan_code="core",
                data_region="tr-1",
                locale="en-US",
                timezone="Europe/Istanbul",
            )
        )
        await session.commit()

        with pytest.raises(DemoSeedConflictError):
            await seed_demo_data(session)
    finally:
        await session.close()
        await engine.dispose()


async def _count(session: AsyncSession, model: type[object]) -> int:
    return int(await session.scalar(select(func.count()).select_from(model)) or 0)


async def _restore_legacy_atlas_projection(
    session: AsyncSession,
    *,
    legacy_password_hash: str | None = None,
) -> tuple[User, Identity, TenantMembership]:
    atlas_fixture = next(fixture for fixture in DEMO_USERS if fixture.key == "atlas_admin")
    atlas_user = await session.get(User, atlas_fixture.id)
    assert atlas_user is not None
    shared_identity = await session.scalar(
        select(Identity).where(
            Identity.email_normalized == "admin@wealthyfalcon.demo"
        )
    )
    assert shared_identity is not None
    atlas_membership = await session.scalar(
        select(TenantMembership).where(
            TenantMembership.tenant_id == atlas_user.tenant_id,
            TenantMembership.legacy_user_id == atlas_user.id,
        )
    )
    assert atlas_membership is not None

    detached_identity = Identity(
        id=atlas_user.id,
        email="admin@atlaspeople.demo",
        status=(
            IdentityStatus.ACTIVE.value
            if legacy_password_hash is not None
            else IdentityStatus.PENDING.value
        ),
        password_hash=legacy_password_hash,
    )
    session.add(detached_identity)
    await session.flush()
    atlas_user.email = detached_identity.email
    atlas_user.password_hash = legacy_password_hash
    atlas_membership.identity_id = detached_identity.id
    await session.commit()
    return atlas_user, shared_identity, atlas_membership
