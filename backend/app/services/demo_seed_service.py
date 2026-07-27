import hashlib
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from uuid import UUID, uuid5

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.authorization import UserRole
from app.models.department import Department, DepartmentStatus
from app.models.employee import Employee, EmployeeStatus
from app.models.employee_assignment import EmployeeAssignment
from app.models.employee_profile import (
    EmployeeEmploymentProfile,
    EmployeePersonalProfile,
)
from app.models.identity import (
    Identity,
    IdentityStatus,
    MembershipRole,
    PlatformIdentityRole,
    TenantMembership,
)
from app.models.leave import (
    HolidayCalendar,
    LeaveBalanceLedger,
    LeavePolicy,
    LeaveRequestDay,
    LeaveRequestTimeline,
    LeaveType,
)
from app.models.leave_request import LeaveRequest, LeaveRequestStatus
from app.models.organization import (
    Branch,
    BranchStatus,
    LegalEntity,
    LegalEntityStatus,
)
from app.models.position import Position, PositionStatus
from app.models.privacy import PrivacyConsentPurpose
from app.models.tenant import Tenant, TenantFeatureFlag, TenantSettings, TenantStatus
from app.models.user import User, UserStatus
from app.modules.core.domain.feature_flags import FeatureFlagKey
from app.platform.authorization import ROLES_BY_CODE
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
    additional_role_codes: tuple[str, ...] = ()
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


_DEMO_STRUCTURE_NAMESPACE = UUID("f9000000-0000-4000-8000-000000000001")
_DEMO_MANAGER_USER_KEY_BY_TENANT = {
    "wealthy_falcon": "wf_manager",
    "atlas": "atlas_manager",
}
_DEMO_BRANCH_NAME = "Demo Main Branch"
_LEAVE_POLICY_EFFECTIVE_FROM = date(1900, 1, 1)
_DEMO_LEAVE_CONFIGURATION_CREATED_AT = datetime(2026, 7, 1, 8, tzinfo=UTC)
_STARTER_LEAVE_TYPES = (
    ("annual", "Annual leave", True, False),
    ("excuse", "Excuse leave", True, False),
    ("unpaid", "Unpaid leave", False, False),
    ("medical_report", "Medical/report leave", True, True),
)
_STARTER_LEAVE_TYPE_BY_CODE = {
    code: (name, paid, document_required)
    for code, name, paid, document_required in _STARTER_LEAVE_TYPES
}


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
        additional_role_codes=("hr_specialist",),
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
    await _ensure_demo_leave_configuration(session, tenants)
    await session.flush()
    await _ensure_privacy_consent_purposes(session, tenants)
    await session.flush()
    await _ensure_organization_feature(session, tenants)
    await session.flush()
    await _ensure_default_legal_entities(session, tenants)
    await session.flush()

    users = await _upsert_users(session, tenants)
    await session.flush()
    await _ensure_shared_admin_platform_role(session, users)
    await session.flush()

    employees = await _upsert_employees(session, tenants)
    await session.flush()
    await _ensure_employee_profiles(session, employees)
    await session.flush()

    await _ensure_structured_employee_assignments(
        session,
        tenants=tenants,
        users=users,
        employees=employees,
    )
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


async def _ensure_demo_leave_configuration(
    session: AsyncSession,
    tenants: dict[str, Tenant],
) -> None:
    leave_codes_by_tenant = {
        tenant_key: {code for code, *_ in _STARTER_LEAVE_TYPES} for tenant_key in tenants
    }
    for fixture in DEMO_LEAVE_REQUESTS:
        leave_codes_by_tenant[fixture.tenant_key].add(fixture.leave_type)

    for tenant_key, tenant in tenants.items():
        for raw_leave_type in sorted(leave_codes_by_tenant[tenant_key]):
            await _ensure_demo_leave_type_and_policy(
                session,
                tenant_id=tenant.id,
                raw_leave_type=raw_leave_type,
            )
        await _ensure_demo_default_calendar(session, tenant.id)


async def _ensure_demo_leave_type_and_policy(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    raw_leave_type: str,
) -> None:
    (
        leave_type_id,
        code,
        name,
        description,
        is_active,
        paid,
        document_required,
    ) = _demo_leave_type_seed(tenant_id, raw_leave_type)
    leave_type = await session.get(LeaveType, leave_type_id)
    leave_type_with_code = await session.scalar(
        select(LeaveType).where(
            LeaveType.tenant_id == tenant_id,
            LeaveType.code == code,
        )
    )
    if leave_type is None:
        if leave_type_with_code is not None:
            raise DemoSeedConflictError(f"Demo leave type code {code!r} is already in use")
        leave_type = LeaveType(
            id=leave_type_id,
            tenant_id=tenant_id,
            code=code,
            name=name,
            description=description,
            is_active=is_active,
            version=1,
            created_at=_DEMO_LEAVE_CONFIGURATION_CREATED_AT,
            updated_at=_DEMO_LEAVE_CONFIGURATION_CREATED_AT,
        )
        session.add(leave_type)
        await session.flush()
    else:
        _ensure_same_tenant(
            leave_type.tenant_id,
            tenant_id,
            f"leave type {leave_type_id}",
        )
        if leave_type.code != code:
            raise DemoSeedConflictError(f"Demo leave type id {leave_type_id} is already in use")

    policy_id = _demo_leave_policy_id(tenant_id, leave_type_id)
    policy = await session.get(LeavePolicy, policy_id)
    policy_with_version = await session.scalar(
        select(LeavePolicy).where(
            LeavePolicy.tenant_id == tenant_id,
            LeavePolicy.leave_type_id == leave_type_id,
            LeavePolicy.version == 1,
        )
    )
    if policy is None:
        if policy_with_version is not None:
            raise DemoSeedConflictError(
                f"Demo leave policy version for type {leave_type_id} is already in use"
            )
        session.add(
            LeavePolicy(
                id=policy_id,
                tenant_id=tenant_id,
                leave_type_id=leave_type_id,
                version=1,
                effective_from=_LEAVE_POLICY_EFFECTIVE_FROM,
                paid=paid,
                document_required=document_required,
                negative_balance_allowed=False,
                accrual_enabled=False,
                accrual_days_per_month=Decimal("0.00"),
                carryover_enabled=False,
                carryover_limit_days=None,
                created_by_user_id=None,
                created_at=_DEMO_LEAVE_CONFIGURATION_CREATED_AT,
            )
        )
        await session.flush()
        return

    _ensure_same_tenant(policy.tenant_id, tenant_id, f"leave policy {policy_id}")
    expected_policy_values = (
        leave_type_id,
        1,
        _LEAVE_POLICY_EFFECTIVE_FROM,
        paid,
        document_required,
        False,
        False,
        Decimal("0.00"),
        False,
        None,
        None,
    )
    actual_policy_values = (
        policy.leave_type_id,
        policy.version,
        policy.effective_from,
        policy.paid,
        policy.document_required,
        policy.negative_balance_allowed,
        policy.accrual_enabled,
        policy.accrual_days_per_month,
        policy.carryover_enabled,
        policy.carryover_limit_days,
        policy.created_by_user_id,
    )
    if actual_policy_values != expected_policy_values:
        raise DemoSeedConflictError(f"Demo leave policy id {policy_id} is already in use")


async def _ensure_demo_default_calendar(
    session: AsyncSession,
    tenant_id: UUID,
) -> None:
    calendar_id = _deterministic_uuid(f"p6:holiday-calendar:{tenant_id}:default")
    calendar = await session.get(HolidayCalendar, calendar_id)
    active_default = await session.scalar(
        select(HolidayCalendar).where(
            HolidayCalendar.tenant_id == tenant_id,
            HolidayCalendar.is_active.is_(True),
            HolidayCalendar.is_default.is_(True),
        )
    )
    if active_default is not None:
        return
    if calendar is not None:
        _ensure_same_tenant(
            calendar.tenant_id,
            tenant_id,
            f"holiday calendar {calendar_id}",
        )
        raise DemoSeedConflictError(f"Demo holiday calendar {calendar_id} is not an active default")
    session.add(
        HolidayCalendar(
            id=calendar_id,
            tenant_id=tenant_id,
            name="Default work calendar",
            is_default=True,
            is_active=True,
            non_working_weekdays=[5, 6],
            version=1,
            created_at=_DEMO_LEAVE_CONFIGURATION_CREATED_AT,
            updated_at=_DEMO_LEAVE_CONFIGURATION_CREATED_AT,
        )
    )


def _demo_leave_type_seed(
    tenant_id: UUID,
    raw_leave_type: str,
) -> tuple[UUID, str, str, str | None, bool, bool, bool]:
    starter = _STARTER_LEAVE_TYPE_BY_CODE.get(raw_leave_type)
    if starter is not None:
        name, paid, document_required = starter
        return (
            _deterministic_uuid(f"p6:leave-type:{tenant_id}:{raw_leave_type}"),
            raw_leave_type,
            name,
            None,
            True,
            paid,
            document_required,
        )

    digest = hashlib.md5(
        raw_leave_type.encode("utf-8"),
        usedforsecurity=False,
    ).hexdigest()
    display_name = raw_leave_type.strip() or "Legacy unclassified leave"
    return (
        _deterministic_uuid(f"p6:legacy-leave-type:{tenant_id}:{raw_leave_type}"),
        f"legacy_{digest}",
        display_name[:200],
        "Imported legacy leave type; inactive for new requests.",
        False,
        False,
        False,
    )


def _demo_leave_policy_id(tenant_id: UUID, leave_type_id: UUID) -> UUID:
    return _deterministic_uuid(f"p6:leave-policy:{tenant_id}:{leave_type_id}:1")


async def _ensure_privacy_consent_purposes(
    session: AsyncSession,
    tenants: dict[str, Tenant],
) -> None:
    for tenant in tenants.values():
        purpose = await session.scalar(
            select(PrivacyConsentPurpose).where(
                PrivacyConsentPurpose.tenant_id == tenant.id,
                PrivacyConsentPurpose.code == "optional_communications",
                PrivacyConsentPurpose.version == 1,
            )
        )
        if purpose is not None:
            continue
        session.add(
            PrivacyConsentPurpose(
                id=_demo_structure_id(
                    "privacy-consent-purpose",
                    tenant.id,
                    "optional_communications:1",
                ),
                tenant_id=tenant.id,
                code="optional_communications",
                version=1,
                title="İsteğe bağlı iletişimler",
                description=("Zorunlu olmayan çalışan iletişimleri için isteğe bağlı onay."),
                is_active=True,
                created_at=datetime.now(UTC),
            )
        )


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
        for role_code in (fixture.role_code, *fixture.additional_role_codes):
            await assign_system_role(
                session,
                tenant_id=tenant.id,
                user_id=user.id,
                role_code=role_code,
            )
        await _upsert_identity_membership_projection(session, user)
        users[fixture.key] = user
    return users


async def _ensure_shared_admin_platform_role(
    session: AsyncSession,
    users: dict[str, User],
) -> None:
    identity_ids: set[UUID] = set()
    for user_key in ("wf_admin", "atlas_admin"):
        user = users[user_key]
        membership = await session.scalar(
            select(TenantMembership).where(
                TenantMembership.tenant_id == user.tenant_id,
                TenantMembership.legacy_user_id == user.id,
            )
        )
        if membership is None:  # pragma: no cover - demo projection invariant
            raise DemoSeedConflictError(f"Demo shared admin membership {user_key!r} was not seeded")
        identity_ids.add(membership.identity_id)

    if len(identity_ids) != 1:
        raise DemoSeedConflictError(
            "Demo shared admin users did not resolve to one canonical identity"
        )

    identity_id = identity_ids.pop()
    super_admin_role = ROLES_BY_CODE["super_admin"]
    assignment = await session.get(
        PlatformIdentityRole,
        (identity_id, super_admin_role.id),
    )
    if assignment is None:
        session.add(
            PlatformIdentityRole(
                identity_id=identity_id,
                role_id=super_admin_role.id,
                role_scope_type=super_admin_role.scope_type.value,
                active=True,
            )
        )
    else:
        assignment.active = True


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
            select(Identity).where(Identity.id == stable_membership.identity_id).with_for_update()
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
    if identity.status == IdentityStatus.PENDING.value and user.password_hash is not None:
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
        if canonical_membership is not None and canonical_membership.id != stable_membership.id:
            raise DemoSeedConflictError(
                f"Demo identity already has a different membership in tenant {user.tenant_id}"
            )
        membership = stable_membership
        membership.identity_id = identity.id
        # The superseded identity is intentionally retained. Beyond the designated shared demo
        # admin role, the seed does not own platform roles, recovery/session history, or other
        # state that may reference an identity.
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


async def _ensure_employee_profiles(
    session: AsyncSession,
    employees: dict[str, Employee],
) -> None:
    """Keep the P4B one-to-one invariant when demo employees are inserted after 0033."""

    for key, employee in employees.items():
        personal = await session.scalar(
            select(EmployeePersonalProfile).where(
                EmployeePersonalProfile.tenant_id == employee.tenant_id,
                EmployeePersonalProfile.employee_id == employee.id,
            )
        )
        if personal is None:
            personal_id = _demo_structure_id(
                "employee-personal-profile",
                employee.tenant_id,
                key,
            )
            if await session.get(EmployeePersonalProfile, personal_id) is not None:
                raise DemoSeedConflictError(
                    f"Demo personal profile id {personal_id} is already in use"
                )
            session.add(
                EmployeePersonalProfile(
                    id=personal_id,
                    tenant_id=employee.tenant_id,
                    employee_id=employee.id,
                )
            )

        employment = await session.scalar(
            select(EmployeeEmploymentProfile).where(
                EmployeeEmploymentProfile.tenant_id == employee.tenant_id,
                EmployeeEmploymentProfile.employee_id == employee.id,
            )
        )
        if employment is None:
            employment_id = _demo_structure_id(
                "employee-employment-profile",
                employee.tenant_id,
                key,
            )
            if await session.get(EmployeeEmploymentProfile, employment_id) is not None:
                raise DemoSeedConflictError(
                    f"Demo employment profile id {employment_id} is already in use"
                )
            session.add(
                EmployeeEmploymentProfile(
                    id=employment_id,
                    tenant_id=employee.tenant_id,
                    employee_id=employee.id,
                )
            )


async def _ensure_structured_employee_assignments(
    session: AsyncSession,
    *,
    tenants: dict[str, Tenant],
    users: dict[str, User],
    employees: dict[str, Employee],
) -> None:
    """Add the P3I demo projection without taking ownership of existing history."""

    legal_entities: dict[str, LegalEntity] = {}
    branches: dict[str, Branch] = {}
    for tenant_key, tenant in tenants.items():
        legal_entity = await _active_default_legal_entity(session, tenant)
        legal_entities[tenant_key] = legal_entity
        branches[tenant_key] = await _ensure_demo_branch(
            session,
            tenant_key=tenant_key,
            tenant=tenant,
            legal_entity=legal_entity,
        )

    departments: dict[tuple[str, str], Department] = {}
    positions: dict[tuple[str, str], Position] = {}
    for fixture in DEMO_EMPLOYEES:
        tenant = tenants[fixture.tenant_key]
        department_key = (fixture.tenant_key, _normalized_demo_label(fixture.department))
        if department_key not in departments:
            departments[department_key] = await _ensure_demo_department(
                session,
                tenant=tenant,
                label=fixture.department,
            )

        position_key = (fixture.tenant_key, _normalized_demo_label(fixture.position))
        if position_key not in positions:
            positions[position_key] = await _ensure_demo_position(
                session,
                tenant=tenant,
                title=fixture.position,
            )

    for fixture in DEMO_EMPLOYEES:
        employee = employees[fixture.key]
        existing_assignment_id = await session.scalar(
            select(EmployeeAssignment.id)
            .where(
                EmployeeAssignment.tenant_id == employee.tenant_id,
                EmployeeAssignment.employee_id == employee.id,
            )
            .limit(1)
        )
        if existing_assignment_id is not None:
            # The seed is an expand-side bootstrap only. Once any history exists, P3I commands
            # exclusively own that employee's assignment chain.
            continue

        manager_key = _DEMO_MANAGER_USER_KEY_BY_TENANT[fixture.tenant_key]
        manager = users[manager_key]
        _ensure_same_tenant(
            manager.tenant_id,
            employee.tenant_id,
            f"assignment manager {manager.id}",
        )
        if manager.status != UserStatus.ACTIVE.value:
            raise DemoSeedConflictError(f"Demo assignment manager {manager.id} is not active")

        assignment_id = _demo_structure_id(
            "assignment",
            employee.tenant_id,
            str(employee.id),
        )
        conflicting_assignment = await session.get(EmployeeAssignment, assignment_id)
        if conflicting_assignment is not None:
            raise DemoSeedConflictError(f"Demo assignment id {assignment_id} is already in use")

        effective_to = None
        if fixture.status is EmployeeStatus.TERMINATED:
            if fixture.employment_end_date is None:
                raise DemoSeedConflictError(
                    f"Terminated demo employee {employee.id} has no employment end date"
                )
            effective_to = fixture.employment_end_date + timedelta(days=1)

        session.add(
            EmployeeAssignment(
                id=assignment_id,
                tenant_id=employee.tenant_id,
                employee_id=employee.id,
                legal_entity_id=legal_entities[fixture.tenant_key].id,
                branch_id=branches[fixture.tenant_key].id,
                department_id=departments[
                    (fixture.tenant_key, _normalized_demo_label(fixture.department))
                ].id,
                position_id=positions[
                    (fixture.tenant_key, _normalized_demo_label(fixture.position))
                ].id,
                manager_user_id=manager.id,
                supersedes_assignment_id=None,
                effective_from=fixture.employment_start_date,
                effective_to=effective_to,
                change_reason="Demo structured employee assignment",
                created_by_user_id=None,
            )
        )


async def _active_default_legal_entity(
    session: AsyncSession,
    tenant: Tenant,
) -> LegalEntity:
    legal_entity = await session.scalar(
        select(LegalEntity).where(
            LegalEntity.tenant_id == tenant.id,
            LegalEntity.is_default.is_(True),
        )
    )
    if legal_entity is None:
        raise DemoSeedConflictError(f"Demo tenant {tenant.id} has no default legal entity")
    if legal_entity.status != LegalEntityStatus.ACTIVE.value:
        raise DemoSeedConflictError(f"Demo tenant {tenant.id} default legal entity is not active")
    return legal_entity


async def _ensure_demo_branch(
    session: AsyncSession,
    *,
    tenant_key: str,
    tenant: Tenant,
    legal_entity: LegalEntity,
) -> Branch:
    code = f"DEMO-B-{tenant_key.replace('_', '-').upper()}"
    branch = await session.scalar(
        select(Branch)
        .where(
            Branch.tenant_id == tenant.id,
            Branch.legal_entity_id == legal_entity.id,
            func.lower(func.trim(Branch.code)) == code.casefold(),
        )
        .order_by(Branch.id)
    )
    if branch is not None:
        if branch.status != BranchStatus.ACTIVE.value or branch.archived_at is not None:
            raise DemoSeedConflictError(
                f"Demo branch code {code!r} is retained by an archived branch"
            )
        return branch

    branch_id = _demo_structure_id("branch", tenant.id, tenant_key)
    if await session.get(Branch, branch_id) is not None:
        raise DemoSeedConflictError(f"Demo branch id {branch_id} is already in use")
    branch = Branch(
        id=branch_id,
        tenant_id=tenant.id,
        legal_entity_id=legal_entity.id,
        code=code,
        name=_DEMO_BRANCH_NAME,
        timezone=tenant.timezone,
        country_code=None,
        city=None,
        address=None,
        status=BranchStatus.ACTIVE.value,
        archived_at=None,
    )
    session.add(branch)
    await session.flush()
    return branch


async def _ensure_demo_department(
    session: AsyncSession,
    *,
    tenant: Tenant,
    label: str,
) -> Department:
    normalized = _normalized_demo_label(label)
    department = await session.scalar(
        select(Department)
        .where(
            Department.tenant_id == tenant.id,
            Department.status == DepartmentStatus.ACTIVE.value,
            Department.archived_at.is_(None),
            func.lower(func.trim(Department.name)) == normalized,
        )
        .order_by(Department.id)
    )
    if department is not None:
        return department

    department_id = _demo_structure_id("department", tenant.id, normalized)
    code = _demo_catalog_code("D", department_id)
    await _ensure_demo_catalog_identity_available(
        session,
        model=Department,
        tenant_id=tenant.id,
        resource_id=department_id,
        code=code,
        resource_name="department",
    )
    department = Department(
        id=department_id,
        tenant_id=tenant.id,
        parent_id=None,
        code=code,
        name=label.strip(),
        status=DepartmentStatus.ACTIVE.value,
        archived_at=None,
    )
    session.add(department)
    await session.flush()
    return department


async def _ensure_demo_position(
    session: AsyncSession,
    *,
    tenant: Tenant,
    title: str,
) -> Position:
    normalized = _normalized_demo_label(title)
    position = await session.scalar(
        select(Position)
        .where(
            Position.tenant_id == tenant.id,
            Position.status == PositionStatus.ACTIVE.value,
            Position.archived_at.is_(None),
            func.lower(func.trim(Position.title)) == normalized,
        )
        .order_by(Position.id)
    )
    if position is not None:
        return position

    position_id = _demo_structure_id("position", tenant.id, normalized)
    code = _demo_catalog_code("P", position_id)
    await _ensure_demo_catalog_identity_available(
        session,
        model=Position,
        tenant_id=tenant.id,
        resource_id=position_id,
        code=code,
        resource_name="position",
    )
    position = Position(
        id=position_id,
        tenant_id=tenant.id,
        code=code,
        title=title.strip(),
        status=PositionStatus.ACTIVE.value,
        archived_at=None,
    )
    session.add(position)
    await session.flush()
    return position


async def _ensure_demo_catalog_identity_available(
    session: AsyncSession,
    *,
    model: type[Department] | type[Position],
    tenant_id: UUID,
    resource_id: UUID,
    code: str,
    resource_name: str,
) -> None:
    if await session.get(model, resource_id) is not None:
        raise DemoSeedConflictError(f"Demo {resource_name} id {resource_id} is already in use")
    code_column = model.code
    conflicting_code_id = await session.scalar(
        select(model.id).where(
            model.tenant_id == tenant_id,
            func.lower(func.trim(code_column)) == code.casefold(),
        )
    )
    if conflicting_code_id is not None:
        raise DemoSeedConflictError(f"Demo {resource_name} code {code!r} is already in use")


def _normalized_demo_label(value: str) -> str:
    return value.strip().casefold()


def _demo_structure_id(resource: str, tenant_id: UUID, key: str) -> UUID:
    return uuid5(_DEMO_STRUCTURE_NAMESPACE, f"{resource}:{tenant_id}:{key}")


def _deterministic_uuid(value: str) -> UUID:
    digest = hashlib.md5(value.encode("utf-8"), usedforsecurity=False).hexdigest()
    return UUID(digest, version=4)


def _demo_catalog_code(resource: str, resource_id: UUID) -> str:
    return f"DEMO-{resource}-{resource_id.hex[:16].upper()}"


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

        leave_type_id, *_ = _demo_leave_type_seed(
            tenant.id,
            fixture.leave_type,
        )
        policy_id = _demo_leave_policy_id(tenant.id, leave_type_id)
        submitted_at = _demo_leave_submitted_at(fixture)
        decided_at = _demo_leave_decided_at(fixture)
        leave_request = await session.get(LeaveRequest, fixture.id)
        if leave_request is not None:
            _ensure_same_tenant(
                leave_request.tenant_id,
                tenant.id,
                f"leave request {fixture.id}",
            )
        else:
            leave_request = LeaveRequest(
                id=fixture.id,
                tenant_id=tenant.id,
                created_at=submitted_at,
                updated_at=decided_at or submitted_at,
            )
            session.add(leave_request)

        leave_request.employee_id = employee.id
        leave_request.leave_type = fixture.leave_type
        leave_request.leave_type_id = leave_type_id
        leave_request.policy_id = policy_id
        leave_request.start_date = fixture.start_date
        leave_request.end_date = fixture.end_date
        leave_request.status = fixture.status.value
        leave_request.requested_by_user_id = requested_by_user.id
        # These are intentionally null for the pre-P6 demo history, matching the P6
        # migration when a legacy requester has no employee-account link.
        leave_request.requested_by_membership_id = None
        leave_request.routed_manager_user_id = None
        leave_request.document_id = None
        leave_request.employee_note = None
        leave_request.counted_days = _demo_counted_days(fixture)
        leave_request.decided_by_user_id = (
            decided_by_user.id if decided_by_user is not None else None
        )
        leave_request.decision_note = fixture.decision_note
        leave_request.decided_at = decided_at

    # The fact rows use scalar composite foreign keys rather than ORM relationships.
    # Persist every parent before scheduling its immutable child history.
    await session.flush()
    for fixture in DEMO_LEAVE_REQUESTS:
        await _ensure_demo_leave_request_facts(
            session,
            fixture=fixture,
            tenant=tenants[fixture.tenant_key],
            employee=employees[fixture.employee_key],
            requested_by_user=users[fixture.requested_by_user_key],
            decided_by_user=(
                users[fixture.decided_by_user_key]
                if fixture.decided_by_user_key is not None
                else None
            ),
        )


async def _ensure_demo_leave_request_facts(
    session: AsyncSession,
    *,
    fixture: DemoLeaveRequestFixture,
    tenant: Tenant,
    employee: Employee,
    requested_by_user: User,
    decided_by_user: User | None,
) -> None:
    day_values = _demo_leave_request_day_values(fixture)
    submitted_at = _demo_leave_submitted_at(fixture)
    decided_at = _demo_leave_decided_at(fixture)
    for leave_date, is_working_day, counted_days in day_values:
        day_id = _deterministic_uuid(
            f"p6:leave-request-day:{tenant.id}:{fixture.id}:{leave_date.isoformat()}"
        )
        day = await session.get(LeaveRequestDay, day_id)
        natural_day = await session.scalar(
            select(LeaveRequestDay).where(
                LeaveRequestDay.tenant_id == tenant.id,
                LeaveRequestDay.request_id == fixture.id,
                LeaveRequestDay.leave_date == leave_date,
            )
        )
        if day is None:
            if natural_day is not None:
                raise DemoSeedConflictError(
                    f"Demo leave request day {fixture.id}/{leave_date} is already in use"
                )
            session.add(
                LeaveRequestDay(
                    id=day_id,
                    tenant_id=tenant.id,
                    request_id=fixture.id,
                    leave_date=leave_date,
                    is_working_day=is_working_day,
                    is_holiday=False,
                    counted_days=counted_days,
                    holiday_entry_id=None,
                    created_at=submitted_at,
                )
            )
        elif (
            day.tenant_id != tenant.id
            or day.request_id != fixture.id
            or day.leave_date != leave_date
        ):
            raise DemoSeedConflictError(f"Demo leave request day id {day_id} is already in use")

    await _ensure_demo_leave_timeline_event(
        session,
        tenant_id=tenant.id,
        request_id=fixture.id,
        event_type="submitted",
        status=LeaveRequestStatus.PENDING.value,
        actor_user_id=requested_by_user.id,
        occurred_at=submitted_at,
    )
    if fixture.status is not LeaveRequestStatus.PENDING:
        if decided_by_user is None or decided_at is None:
            raise DemoSeedConflictError(
                f"Terminal demo leave request {fixture.id} has no decision actor"
            )
        await _ensure_demo_leave_timeline_event(
            session,
            tenant_id=tenant.id,
            request_id=fixture.id,
            event_type=fixture.status.value,
            status=fixture.status.value,
            actor_user_id=decided_by_user.id,
            occurred_at=decided_at,
        )

    ledger_entry_type = {
        LeaveRequestStatus.PENDING: "planned",
        LeaveRequestStatus.APPROVED: "used",
    }.get(fixture.status)
    if ledger_entry_type is None:
        return
    leave_type_id, *_ = _demo_leave_type_seed(tenant.id, fixture.leave_type)
    counted_by_year: dict[int, tuple[Decimal, date]] = {}
    for leave_date, _is_working_day, counted_days in day_values:
        if not counted_days:
            continue
        current_amount, first_counted_date = counted_by_year.get(
            leave_date.year,
            (Decimal("0.00"), leave_date),
        )
        counted_by_year[leave_date.year] = (
            current_amount + counted_days,
            first_counted_date,
        )
    for period_year, (amount_days, effective_date) in counted_by_year.items():
        source_key = f"legacy-request:{fixture.id}:{ledger_entry_type}:{period_year}"
        ledger_id = _deterministic_uuid(f"p6:leave-ledger:{tenant.id}:{source_key}")
        ledger = await session.get(LeaveBalanceLedger, ledger_id)
        natural_ledger = await session.scalar(
            select(LeaveBalanceLedger).where(
                LeaveBalanceLedger.tenant_id == tenant.id,
                LeaveBalanceLedger.source_key == source_key,
            )
        )
        if ledger is None:
            if natural_ledger is not None:
                raise DemoSeedConflictError(
                    f"Demo leave ledger source {source_key!r} is already in use"
                )
            session.add(
                LeaveBalanceLedger(
                    id=ledger_id,
                    tenant_id=tenant.id,
                    employee_id=employee.id,
                    leave_type_id=leave_type_id,
                    period_year=period_year,
                    entry_type=ledger_entry_type,
                    amount_days=amount_days,
                    effective_date=effective_date,
                    reason=None,
                    request_id=fixture.id,
                    source_type="legacy_request",
                    source_id=fixture.id,
                    source_key=source_key,
                    reversal_of_entry_id=None,
                    created_by_user_id=None,
                    created_at=submitted_at,
                )
            )
        elif (
            ledger.tenant_id != tenant.id
            or ledger.employee_id != employee.id
            or ledger.leave_type_id != leave_type_id
            or ledger.request_id != fixture.id
            or ledger.source_key != source_key
        ):
            raise DemoSeedConflictError(f"Demo leave ledger id {ledger_id} is already in use")


async def _ensure_demo_leave_timeline_event(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    request_id: UUID,
    event_type: str,
    status: str,
    actor_user_id: UUID,
    occurred_at: datetime,
) -> None:
    source_key = f"legacy-request:{request_id}:{event_type}"
    event_id = _deterministic_uuid(
        f"p6:leave-request-timeline:{tenant_id}:{request_id}:{event_type}"
    )
    event = await session.get(LeaveRequestTimeline, event_id)
    natural_event = await session.scalar(
        select(LeaveRequestTimeline).where(
            LeaveRequestTimeline.tenant_id == tenant_id,
            LeaveRequestTimeline.source_key == source_key,
        )
    )
    if event is None:
        if natural_event is not None:
            raise DemoSeedConflictError(
                f"Demo leave timeline source {source_key!r} is already in use"
            )
        session.add(
            LeaveRequestTimeline(
                id=event_id,
                tenant_id=tenant_id,
                request_id=request_id,
                event_type=event_type,
                status=status,
                actor_user_id=actor_user_id,
                source_key=source_key,
                occurred_at=occurred_at,
            )
        )
    elif (
        event.tenant_id != tenant_id
        or event.request_id != request_id
        or event.source_key != source_key
    ):
        raise DemoSeedConflictError(f"Demo leave timeline id {event_id} is already in use")


def _demo_leave_request_day_values(
    fixture: DemoLeaveRequestFixture,
) -> tuple[tuple[date, bool, Decimal], ...]:
    values: list[tuple[date, bool, Decimal]] = []
    leave_date = fixture.start_date
    while leave_date <= fixture.end_date:
        is_working_day = leave_date.weekday() not in {5, 6}
        values.append(
            (
                leave_date,
                is_working_day,
                Decimal("1.00") if is_working_day else Decimal("0.00"),
            )
        )
        leave_date += timedelta(days=1)
    return tuple(values)


def _demo_counted_days(fixture: DemoLeaveRequestFixture) -> Decimal:
    return sum(
        (counted_days for _, _, counted_days in _demo_leave_request_day_values(fixture)),
        Decimal("0.00"),
    )


def _demo_leave_submitted_at(fixture: DemoLeaveRequestFixture) -> datetime:
    submitted_date = fixture.start_date - timedelta(days=7)
    return datetime(
        submitted_date.year,
        submitted_date.month,
        submitted_date.day,
        9,
        tzinfo=UTC,
    )


def _demo_leave_decided_at(
    fixture: DemoLeaveRequestFixture,
) -> datetime | None:
    if fixture.status is LeaveRequestStatus.PENDING:
        return None
    return _demo_leave_submitted_at(fixture) + timedelta(days=1, hours=3)


def _ensure_same_tenant(actual_tenant_id: UUID, expected_tenant_id: UUID, label: str) -> None:
    if actual_tenant_id != expected_tenant_id:
        raise DemoSeedConflictError(
            f"Demo seed conflict for {label}: expected tenant {expected_tenant_id}, "
            f"found {actual_tenant_id}"
        )
