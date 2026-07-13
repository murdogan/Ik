from dataclasses import dataclass
from datetime import date
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.authorization import UserRole
from app.models.employee import Employee, EmployeeStatus
from app.models.identity import (
    Identity,
    IdentityStatus,
    MembershipRole,
    TenantMembership,
)
from app.models.leave_request import LeaveRequest, LeaveRequestStatus
from app.models.organization import LegalEntity, LegalEntityStatus
from app.models.tenant import Tenant, TenantFeatureFlag, TenantSettings, TenantStatus
from app.models.user import User, UserStatus
from app.modules.core.domain.feature_flags import FeatureFlagKey
from app.services.authorization_service import (
    assign_system_role,
    seed_authorization_catalog,
)


@dataclass(frozen=True)
class DemoTenantFixture:
    key: str
    id: UUID
    slug: str
    name: str
    status: TenantStatus = TenantStatus.ACTIVE
    plan_code: str = "core"
    data_region: str = "tr-1"
    locale: str = "en-US"
    timezone: str = "Europe/Istanbul"


@dataclass(frozen=True)
class DemoUserFixture:
    key: str
    tenant_key: str
    id: UUID
    email: str
    full_name: str
    role_code: str = "employee"
    status: UserStatus = UserStatus.ACTIVE


@dataclass(frozen=True)
class DemoEmployeeFixture:
    key: str
    tenant_key: str
    id: UUID
    employee_number: str
    first_name: str
    last_name: str
    email: str
    department: str
    position: str
    employment_start_date: date
    status: EmployeeStatus = EmployeeStatus.ACTIVE
    employment_end_date: date | None = None


@dataclass(frozen=True)
class DemoLeaveRequestFixture:
    key: str
    tenant_key: str
    id: UUID
    employee_key: str
    leave_type: str
    start_date: date
    end_date: date
    requested_by_user_key: str
    status: LeaveRequestStatus = LeaveRequestStatus.PENDING
    decided_by_user_key: str | None = None
    decision_note: str | None = None


@dataclass(frozen=True)
class DemoSeedResult:
    tenants: int
    users: int
    employees: int
    leave_requests: int
    tenant_ids: tuple[UUID, ...]


class DemoSeedConflictError(RuntimeError):
    pass


DEMO_TENANTS: tuple[DemoTenantFixture, ...] = (
    DemoTenantFixture(
        key="wealthy_falcon",
        id=UUID("f1000000-0000-4000-8000-000000000001"),
        slug="wealthy-falcon-demo",
        name="Wealthy Falcon HR Demo",
    ),
    DemoTenantFixture(
        key="atlas",
        id=UUID("f1000000-0000-4000-8000-000000000002"),
        slug="atlas-people-demo",
        name="Atlas People Operations",
        data_region="eu-1",
        timezone="Europe/Amsterdam",
    ),
)

DEMO_USERS: tuple[DemoUserFixture, ...] = (
    DemoUserFixture(
        key="wf_admin",
        tenant_key="wealthy_falcon",
        id=UUID("f2000000-0000-4000-8000-000000000001"),
        email="admin@wealthyfalcon.demo",
        full_name="Maya Stone",
        role_code="tenant_admin",
    ),
    DemoUserFixture(
        key="wf_people_partner",
        tenant_key="wealthy_falcon",
        id=UUID("f2000000-0000-4000-8000-000000000002"),
        email="people.partner@wealthyfalcon.demo",
        full_name="Deniz Carter",
        role_code="hr_specialist",
    ),
    DemoUserFixture(
        key="wf_manager",
        tenant_key="wealthy_falcon",
        id=UUID("f2000000-0000-4000-8000-000000000003"),
        email="manager@wealthyfalcon.demo",
        full_name="Leila Morgan",
        role_code="manager",
    ),
    DemoUserFixture(
        key="atlas_admin",
        tenant_key="atlas",
        id=UUID("f2000000-0000-4000-8000-000000000004"),
        email="admin@wealthyfalcon.demo",
        full_name="Arda Blake",
        role_code="tenant_admin",
    ),
    DemoUserFixture(
        key="atlas_manager",
        tenant_key="atlas",
        id=UUID("f2000000-0000-4000-8000-000000000005"),
        email="manager@atlaspeople.demo",
        full_name="Nora Ellis",
        role_code="manager",
    ),
)

DEMO_EMPLOYEES: tuple[DemoEmployeeFixture, ...] = (
    DemoEmployeeFixture(
        key="wf_001",
        tenant_key="wealthy_falcon",
        id=UUID("f3000000-0000-4000-8000-000000000001"),
        employee_number="WF-001",
        first_name="Ada",
        last_name="Yilmaz",
        email="ada.yilmaz@wealthyfalcon.demo",
        department="People",
        position="People Operations Lead",
        employment_start_date=date(2026, 7, 1),
    ),
    DemoEmployeeFixture(
        key="wf_002",
        tenant_key="wealthy_falcon",
        id=UUID("f3000000-0000-4000-8000-000000000002"),
        employee_number="WF-002",
        first_name="Bora",
        last_name="Demir",
        email="bora.demir@wealthyfalcon.demo",
        department="Engineering",
        position="Backend Engineer",
        employment_start_date=date(2026, 6, 10),
    ),
    DemoEmployeeFixture(
        key="wf_003",
        tenant_key="wealthy_falcon",
        id=UUID("f3000000-0000-4000-8000-000000000003"),
        employee_number="WF-003",
        first_name="Ece",
        last_name="Kaya",
        email="ece.kaya@wealthyfalcon.demo",
        department="Sales",
        position="Enterprise Account Executive",
        employment_start_date=date(2026, 5, 18),
    ),
    DemoEmployeeFixture(
        key="wf_004",
        tenant_key="wealthy_falcon",
        id=UUID("f3000000-0000-4000-8000-000000000004"),
        employee_number="WF-004",
        first_name="Jonas",
        last_name="Reed",
        email="jonas.reed@wealthyfalcon.demo",
        department="Finance",
        position="Finance Manager",
        employment_start_date=date(2026, 4, 7),
        status=EmployeeStatus.ON_LEAVE,
    ),
    DemoEmployeeFixture(
        key="wf_005",
        tenant_key="wealthy_falcon",
        id=UUID("f3000000-0000-4000-8000-000000000005"),
        employee_number="WF-005",
        first_name="Mina",
        last_name="Patel",
        email="mina.patel@wealthyfalcon.demo",
        department="Customer Success",
        position="Customer Success Manager",
        employment_start_date=date(2026, 7, 6),
    ),
    DemoEmployeeFixture(
        key="wf_006",
        tenant_key="wealthy_falcon",
        id=UUID("f3000000-0000-4000-8000-000000000006"),
        employee_number="WF-006",
        first_name="Can",
        last_name="Aydin",
        email="can.aydin@wealthyfalcon.demo",
        department="Engineering",
        position="Frontend Engineer",
        employment_start_date=date(2026, 3, 2),
        status=EmployeeStatus.TERMINATED,
        employment_end_date=date(2026, 7, 5),
    ),
    DemoEmployeeFixture(
        key="atlas_001",
        tenant_key="atlas",
        id=UUID("f3000000-0000-4000-8000-000000000007"),
        employee_number="AT-001",
        first_name="Lena",
        last_name="Vos",
        email="lena.vos@atlaspeople.demo",
        department="Operations",
        position="Operations Lead",
        employment_start_date=date(2026, 7, 3),
    ),
    DemoEmployeeFixture(
        key="atlas_002",
        tenant_key="atlas",
        id=UUID("f3000000-0000-4000-8000-000000000008"),
        employee_number="AT-002",
        first_name="Mateo",
        last_name="Silva",
        email="mateo.silva@atlaspeople.demo",
        department="People",
        position="People Partner",
        employment_start_date=date(2026, 6, 17),
    ),
)

DEMO_LEAVE_REQUESTS: tuple[DemoLeaveRequestFixture, ...] = (
    DemoLeaveRequestFixture(
        key="wf_pending",
        tenant_key="wealthy_falcon",
        id=UUID("f4000000-0000-4000-8000-000000000001"),
        employee_key="wf_002",
        leave_type="annual",
        start_date=date(2026, 8, 3),
        end_date=date(2026, 8, 7),
        requested_by_user_key="wf_people_partner",
    ),
    DemoLeaveRequestFixture(
        key="wf_approved",
        tenant_key="wealthy_falcon",
        id=UUID("f4000000-0000-4000-8000-000000000002"),
        employee_key="wf_004",
        leave_type="sick",
        start_date=date(2026, 7, 13),
        end_date=date(2026, 7, 14),
        requested_by_user_key="wf_people_partner",
        status=LeaveRequestStatus.APPROVED,
        decided_by_user_key="wf_manager",
        decision_note="Coverage confirmed.",
    ),
    DemoLeaveRequestFixture(
        key="wf_rejected",
        tenant_key="wealthy_falcon",
        id=UUID("f4000000-0000-4000-8000-000000000003"),
        employee_key="wf_003",
        leave_type="annual",
        start_date=date(2026, 7, 22),
        end_date=date(2026, 7, 24),
        requested_by_user_key="wf_people_partner",
        status=LeaveRequestStatus.REJECTED,
        decided_by_user_key="wf_manager",
        decision_note="Quarter-end customer coverage is required.",
    ),
    DemoLeaveRequestFixture(
        key="wf_cancelled",
        tenant_key="wealthy_falcon",
        id=UUID("f4000000-0000-4000-8000-000000000004"),
        employee_key="wf_005",
        leave_type="personal",
        start_date=date(2026, 7, 17),
        end_date=date(2026, 7, 17),
        requested_by_user_key="wf_people_partner",
        status=LeaveRequestStatus.CANCELLED,
        decided_by_user_key="wf_people_partner",
        decision_note="Employee cancelled the request.",
    ),
    DemoLeaveRequestFixture(
        key="atlas_pending",
        tenant_key="atlas",
        id=UUID("f4000000-0000-4000-8000-000000000005"),
        employee_key="atlas_002",
        leave_type="annual",
        start_date=date(2026, 8, 10),
        end_date=date(2026, 8, 12),
        requested_by_user_key="atlas_admin",
    ),
)


async def seed_demo_data(session: AsyncSession) -> DemoSeedResult:
    await seed_authorization_catalog(session)
    tenants = await _upsert_tenants(session)
    await session.flush()
    await _ensure_tenant_settings(session, tenants)
    await session.flush()
    await _ensure_organization_feature(session, tenants)
    await session.flush()
    await _ensure_default_legal_entities(session, tenants)
    await session.flush()

    users = await _upsert_users(session, tenants)
    await session.flush()

    employees = await _upsert_employees(session, tenants)
    await session.flush()

    await _upsert_leave_requests(session, tenants, users, employees)
    await session.flush()

    return DemoSeedResult(
        tenants=len(DEMO_TENANTS),
        users=len(DEMO_USERS),
        employees=len(DEMO_EMPLOYEES),
        leave_requests=len(DEMO_LEAVE_REQUESTS),
        tenant_ids=tuple(tenant.id for tenant in tenants.values()),
    )


async def _upsert_tenants(session: AsyncSession) -> dict[str, Tenant]:
    tenants: dict[str, Tenant] = {}
    for fixture in DEMO_TENANTS:
        tenant = await session.get(Tenant, fixture.id)
        tenant_with_slug = await session.scalar(select(Tenant).where(Tenant.slug == fixture.slug))
        if tenant is None and tenant_with_slug is not None:
            raise DemoSeedConflictError(
                f"Demo tenant slug {fixture.slug!r} already exists with a different id"
            )
        if tenant is not None and tenant_with_slug is not None and tenant_with_slug.id != tenant.id:
            raise DemoSeedConflictError(
                f"Demo tenant id {fixture.id} conflicts with slug {fixture.slug!r}"
            )
        if tenant is None:
            tenant = Tenant(id=fixture.id)
            session.add(tenant)

        tenant.slug = fixture.slug
        tenant.name = fixture.name
        tenant.status = fixture.status.value
        tenant.plan_code = fixture.plan_code
        tenant.data_region = fixture.data_region
        tenant.locale = fixture.locale
        tenant.timezone = fixture.timezone
        tenants[fixture.key] = tenant
    return tenants


async def _ensure_tenant_settings(
    session: AsyncSession,
    tenants: dict[str, Tenant],
) -> None:
    for tenant in tenants.values():
        if await session.get(TenantSettings, tenant.id) is None:
            session.add(TenantSettings(tenant_id=tenant.id))


async def _ensure_default_legal_entities(
    session: AsyncSession,
    tenants: dict[str, Tenant],
) -> None:
    for tenant in tenants.values():
        default_entity = await session.scalar(
            select(LegalEntity).where(
                LegalEntity.tenant_id == tenant.id,
                LegalEntity.is_default.is_(True),
            )
        )
        if default_entity is not None:
            continue
        entity_with_id = await session.get(LegalEntity, tenant.id)
        if entity_with_id is not None:
            raise DemoSeedConflictError(
                f"Demo tenant {tenant.id} default legal-entity id is already in use"
            )
        session.add(
            LegalEntity(
                id=tenant.id,
                tenant_id=tenant.id,
                code="DEFAULT",
                name=tenant.name,
                registered_name=tenant.name,
                country_code=None,
                tax_number=None,
                timezone=tenant.timezone,
                status=LegalEntityStatus.ACTIVE.value,
                is_default=True,
            )
        )


async def _ensure_organization_feature(
    session: AsyncSession,
    tenants: dict[str, Tenant],
) -> None:
    for tenant in tenants.values():
        feature = await session.get(
            TenantFeatureFlag,
            (tenant.id, FeatureFlagKey.ORGANIZATION.value),
        )
        if feature is None:
            session.add(
                TenantFeatureFlag(
                    tenant_id=tenant.id,
                    key=FeatureFlagKey.ORGANIZATION.value,
                    enabled=True,
                )
            )
        else:
            # Demo data is a manually usable P3F product fixture, not a production rollout.
            feature.enabled = True


async def _upsert_users(session: AsyncSession, tenants: dict[str, Tenant]) -> dict[str, User]:
    users: dict[str, User] = {}
    for fixture in DEMO_USERS:
        tenant = tenants[fixture.tenant_key]
        user = await session.get(User, fixture.id)
        user_with_email = await session.scalar(
            select(User).where(User.tenant_id == tenant.id).where(User.email == fixture.email)
        )
        if user is None and user_with_email is not None:
            raise DemoSeedConflictError(
                f"Demo user email {fixture.email!r} already exists with a different id"
            )
        is_new_user = user is None
        if user is not None:
            _ensure_same_tenant(user.tenant_id, tenant.id, f"user {fixture.id}")
            if user_with_email is not None and user_with_email.id != user.id:
                raise DemoSeedConflictError(
                    f"Demo user id {fixture.id} conflicts with email {fixture.email!r}"
                )
        else:
            user = User(id=fixture.id, tenant_id=tenant.id)
            session.add(user)

        user.email = fixture.email
        user.full_name = fixture.full_name
        # Repeatable product-data seeding must not erase credentials or activation state created
        # by the explicit local auth-demo flow.
        if is_new_user:
            user.status = fixture.status.value
            user.password_hash = None
        await session.flush()
        await assign_system_role(
            session,
            tenant_id=tenant.id,
            user_id=user.id,
            role_code=fixture.role_code,
        )
        await _upsert_identity_membership_projection(session, user)
        users[fixture.key] = user
    return users


async def _upsert_identity_membership_projection(
    session: AsyncSession,
    user: User,
) -> None:
    """Keep the local demo usable through the canonical P3 identity boundary."""

    stable_membership = await session.scalar(
        select(TenantMembership)
        .where(
            TenantMembership.tenant_id == user.tenant_id,
            TenantMembership.legacy_user_id == user.id,
        )
        .with_for_update()
    )
    previous_identity = None
    if stable_membership is not None:
        previous_identity = await session.scalar(
            select(Identity)
            .where(Identity.id == stable_membership.identity_id)
            .with_for_update()
        )

    identity = await session.scalar(
        select(Identity)
        .where(Identity.email_normalized == user.email.strip().lower())
        .with_for_update()
    )
    if identity is None:
        if previous_identity is not None:
            raise DemoSeedConflictError(
                "Demo user email changed without an existing canonical identity; "
                f"refusing to reinterpret identity {previous_identity.id}"
            )
        identity = Identity(
            id=user.id,
            email=user.email,
            status=(
                IdentityStatus.PENDING.value
                if user.password_hash is None
                else IdentityStatus.ACTIVE.value
            ),
            password_hash=user.password_hash,
        )
        session.add(identity)
        await session.flush()

    _ensure_compatible_identity_passwords(
        user=user,
        identity=identity,
        previous_identity=previous_identity,
    )
    if (
        identity.status == IdentityStatus.PENDING.value
        and user.password_hash is not None
    ):
        identity.email = user.email
        identity.status = IdentityStatus.ACTIVE.value
        identity.password_hash = user.password_hash

    canonical_membership = await session.scalar(
        select(TenantMembership)
        .where(
            TenantMembership.tenant_id == user.tenant_id,
            TenantMembership.identity_id == identity.id,
        )
        .with_for_update()
    )
    if stable_membership is not None:
        if (
            canonical_membership is not None
            and canonical_membership.id != stable_membership.id
        ):
            raise DemoSeedConflictError(
                "Demo identity already has a different membership in tenant "
                f"{user.tenant_id}"
            )
        membership = stable_membership
        membership.identity_id = identity.id
        # The superseded identity is intentionally retained. The demo seed does not own any
        # platform roles, recovery/session history, or other state that may reference it.
    elif canonical_membership is not None:
        if canonical_membership.legacy_user_id != user.id:
            raise DemoSeedConflictError(
                "Demo identity membership belongs to a different legacy user in tenant "
                f"{user.tenant_id}"
            )
        membership = canonical_membership
    else:
        membership = TenantMembership(
            id=user.id,
            tenant_id=user.tenant_id,
            identity_id=identity.id,
            legacy_user_id=user.id,
            full_name=user.full_name,
            status=user.status,
            permission_version=user.permission_version,
        )
        session.add(membership)
    membership.full_name = user.full_name
    membership.status = user.status
    membership.permission_version = user.permission_version
    await session.flush()

    assignments = tuple(
        await session.scalars(
            select(UserRole).where(
                UserRole.tenant_id == user.tenant_id,
                UserRole.user_id == user.id,
            )
        )
    )
    projected_roles = {
        role.role_id: role
        for role in await session.scalars(
            select(MembershipRole).where(
                MembershipRole.tenant_id == user.tenant_id,
                MembershipRole.membership_id == membership.id,
            )
        )
    }
    for assignment in assignments:
        projected = projected_roles.get(assignment.role_id)
        if projected is None:
            session.add(
                MembershipRole(
                    tenant_id=user.tenant_id,
                    membership_id=membership.id,
                    role_id=assignment.role_id,
                    role_scope_type=assignment.role_scope_type,
                    active=assignment.active,
                )
            )
        else:
            projected.active = assignment.active
    await session.flush()


def _ensure_compatible_identity_passwords(
    *,
    user: User,
    identity: Identity,
    previous_identity: Identity | None,
) -> None:
    password_hashes = {
        password_hash
        for password_hash in (
            user.password_hash,
            identity.password_hash,
            previous_identity.password_hash if previous_identity is not None else None,
        )
        if password_hash is not None
    }
    if len(password_hashes) > 1:
        raise DemoSeedConflictError(
            "Demo identity credential hashes disagree for legacy user "
            f"{user.id}; refusing to merge identities"
        )


async def _upsert_employees(
    session: AsyncSession,
    tenants: dict[str, Tenant],
) -> dict[str, Employee]:
    employees: dict[str, Employee] = {}
    for fixture in DEMO_EMPLOYEES:
        tenant = tenants[fixture.tenant_key]
        employee = await session.get(Employee, fixture.id)
        employee_with_number = await session.scalar(
            select(Employee)
            .where(Employee.tenant_id == tenant.id)
            .where(Employee.employee_number == fixture.employee_number)
        )
        if employee is None and employee_with_number is not None:
            raise DemoSeedConflictError(
                "Demo employee number "
                f"{fixture.employee_number!r} already exists with a different id"
            )
        if employee is not None:
            _ensure_same_tenant(employee.tenant_id, tenant.id, f"employee {fixture.id}")
            if employee_with_number is not None and employee_with_number.id != employee.id:
                raise DemoSeedConflictError(
                    "Demo employee id "
                    f"{fixture.id} conflicts with number {fixture.employee_number!r}"
                )
        else:
            employee = Employee(id=fixture.id, tenant_id=tenant.id)
            session.add(employee)

        employee.employee_number = fixture.employee_number
        employee.first_name = fixture.first_name
        employee.last_name = fixture.last_name
        employee.email = fixture.email
        employee.department = fixture.department
        employee.position = fixture.position
        employee.status = fixture.status.value
        employee.employment_start_date = fixture.employment_start_date
        employee.employment_end_date = fixture.employment_end_date
        employee.archived_at = None
        employees[fixture.key] = employee
    return employees


async def _upsert_leave_requests(
    session: AsyncSession,
    tenants: dict[str, Tenant],
    users: dict[str, User],
    employees: dict[str, Employee],
) -> None:
    for fixture in DEMO_LEAVE_REQUESTS:
        tenant = tenants[fixture.tenant_key]
        employee = employees[fixture.employee_key]
        requested_by_user = users[fixture.requested_by_user_key]
        decided_by_user = (
            users[fixture.decided_by_user_key] if fixture.decided_by_user_key is not None else None
        )
        _ensure_same_tenant(employee.tenant_id, tenant.id, f"leave employee {employee.id}")
        _ensure_same_tenant(
            requested_by_user.tenant_id,
            tenant.id,
            f"leave requested_by user {requested_by_user.id}",
        )
        if decided_by_user is not None:
            _ensure_same_tenant(
                decided_by_user.tenant_id,
                tenant.id,
                f"leave decided_by user {decided_by_user.id}",
            )

        leave_request = await session.get(LeaveRequest, fixture.id)
        if leave_request is not None:
            _ensure_same_tenant(
                leave_request.tenant_id,
                tenant.id,
                f"leave request {fixture.id}",
            )
        else:
            leave_request = LeaveRequest(id=fixture.id, tenant_id=tenant.id)
            session.add(leave_request)

        leave_request.employee_id = employee.id
        leave_request.leave_type = fixture.leave_type
        leave_request.start_date = fixture.start_date
        leave_request.end_date = fixture.end_date
        leave_request.status = fixture.status.value
        leave_request.requested_by_user_id = requested_by_user.id
        leave_request.decided_by_user_id = (
            decided_by_user.id if decided_by_user is not None else None
        )
        leave_request.decision_note = fixture.decision_note


def _ensure_same_tenant(actual_tenant_id: UUID, expected_tenant_id: UUID, label: str) -> None:
    if actual_tenant_id != expected_tenant_id:
        raise DemoSeedConflictError(
            f"Demo seed conflict for {label}: expected tenant {expected_tenant_id}, "
            f"found {actual_tenant_id}"
        )
