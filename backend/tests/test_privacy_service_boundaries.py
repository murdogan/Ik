"""Critical Phase 9 privacy evidence and non-destructive retention boundaries."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime
from uuid import UUID

import pytest
from app.db.base import Base
from app.models.authorization import Permission, Role, RolePermission, UserRole
from app.models.employee import Employee, EmployeeStatus, EmployeeTerminationReason
from app.models.identity import Identity, IdentityStatus, MembershipStatus, TenantMembership
from app.models.privacy import (
    PrivacyConsentAction,
    PrivacyConsentEvent,
    PrivacyConsentPurpose,
    PrivacyNoticeAcknowledgement,
    RetentionAction,
    RetentionAnchor,
    RetentionDataCategory,
    RetentionPolicyStatus,
)
from app.models.tenant import Tenant, TenantStatus
from app.models.user import User, UserStatus
from app.platform.authorization import PermissionTargetType, RoleScopeType
from app.platform.request_context import AuthenticationStrength, RequestContext
from app.platform.tenancy import TenantContext
from app.schemas.privacy import (
    PrivacyNoticeAcknowledge,
    PrivacyNoticeCreate,
    RetentionDryRunRequest,
    RetentionPolicyCreate,
)
from app.services.phase7_access import Phase7NotFoundError
from app.services.privacy_service import PrivacyService
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool

TENANT_A_ID = UUID("9a000000-0000-4000-8000-000000000001")
TENANT_B_ID = UUID("9a000000-0000-4000-8000-000000000002")
USER_A_ID = UUID("9a000000-0000-4000-8000-000000000011")
USER_A_OTHER_ID = UUID("9a000000-0000-4000-8000-000000000012")
USER_B_ID = UUID("9a000000-0000-4000-8000-000000000021")
MEMBERSHIP_A_ID = UUID("9a000000-0000-4000-8000-000000000031")
MEMBERSHIP_A_OTHER_ID = UUID("9a000000-0000-4000-8000-000000000032")
MEMBERSHIP_B_ID = UUID("9a000000-0000-4000-8000-000000000041")
PURPOSE_A_ID = UUID("9a000000-0000-4000-8000-000000000051")
PURPOSE_B_ID = UUID("9a000000-0000-4000-8000-000000000052")
PRIVACY_ROLE_ID = UUID("9a000000-0000-4000-8000-000000000061")
PRIVACY_PERMISSION_ID = UUID("9a000000-0000-4000-8000-000000000071")
NOW = datetime(2026, 7, 27, 12, 0, tzinfo=UTC)


@dataclass(slots=True)
class _PrivacyDatabase:
    engine: AsyncEngine
    sessions: async_sessionmaker[AsyncSession]


@pytest.fixture
async def privacy_database():
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
        yield _PrivacyDatabase(engine=engine, sessions=sessions)
    finally:
        await engine.dispose()


async def test_notice_acknowledgement_binds_actor_to_exact_published_version_and_hash(
    privacy_database: _PrivacyDatabase,
) -> None:
    async with privacy_database.sessions() as session:
        service = PrivacyService(session)
        async with session.begin():
            first = await service.create_notice(
                request_context=_context_a(),
                payload=PrivacyNoticeCreate(
                    title="Employee privacy notice v1",
                    body="Synthetic version one privacy notice.",
                    locale="tr-TR",
                ),
            )
            first = await service.publish_notice(
                request_context=_context_a(),
                notice_id=first.id,
                expected_revision=first.revision,
            )
        assert first.eligible_count == 2

        current = await service.current_employee_notice(request_context=_context_a())
        assert current.notice is not None
        assert current.notice.id == first.id
        assert current.acknowledged_at is None

        with pytest.raises(Phase7NotFoundError):
            await service.acknowledge_notice(
                request_context=_context_a(),
                payload=PrivacyNoticeAcknowledge(
                    notice_id=first.id,
                    notice_content_hash="0" * 64,
                ),
            )
        with pytest.raises(Phase7NotFoundError):
            await service.acknowledge_notice(
                request_context=_context_b(),
                payload=PrivacyNoticeAcknowledge(
                    notice_id=first.id,
                    notice_content_hash=first.content_hash,
                ),
            )

        acknowledged = await service.acknowledge_notice(
            request_context=_context_a(),
            payload=PrivacyNoticeAcknowledge(
                notice_id=first.id,
                notice_content_hash=first.content_hash,
            ),
        )
        await session.commit()
        assert acknowledged.acknowledged_at is not None

        other_actor = await service.current_employee_notice(request_context=_context_a_other())
        assert other_actor.notice is not None
        assert other_actor.notice.id == first.id
        assert other_actor.acknowledged_at is None

        second = await service.create_notice(
            request_context=_context_a(),
            payload=PrivacyNoticeCreate(
                title="Employee privacy notice v2",
                body="Synthetic version two privacy notice.",
                locale="tr-TR",
            ),
        )
        second = await service.publish_notice(
            request_context=_context_a(),
            notice_id=second.id,
            expected_revision=second.revision,
        )
        await session.commit()

        latest = await service.current_employee_notice(request_context=_context_a())
        assert latest.notice is not None
        assert latest.notice.id == second.id
        assert latest.notice.notice_version == 2
        assert latest.acknowledged_at is None
        assert (
            await session.scalar(
                select(func.count())
                .select_from(PrivacyNoticeAcknowledgement)
                .where(
                    PrivacyNoticeAcknowledgement.tenant_id == TENANT_A_ID,
                    PrivacyNoticeAcknowledgement.user_id == USER_A_ID,
                )
            )
            == 1
        )


async def test_consent_transitions_append_own_evidence_without_cross_actor_history(
    privacy_database: _PrivacyDatabase,
) -> None:
    async with privacy_database.sessions() as session:
        service = PrivacyService(session)
        async with session.begin():
            granted = await service.transition_consent(
                request_context=_context_a(),
                purpose_id=PURPOSE_A_ID,
                action=PrivacyConsentAction.GRANT,
            )
            withdrawn = await service.transition_consent(
                request_context=_context_a(),
                purpose_id=PURPOSE_A_ID,
                action=PrivacyConsentAction.WITHDRAW,
            )
        assert granted.granted is True
        assert withdrawn.granted is False
        assert [event.action for event in withdrawn.history] == [
            PrivacyConsentAction.WITHDRAW,
            PrivacyConsentAction.GRANT,
        ]
        assert withdrawn.state_version == 2

        own_center = await service.consent_center(request_context=_context_a())
        other_center = await service.consent_center(request_context=_context_a_other())
        assert [event.action for event in own_center.purposes[0].history] == [
            PrivacyConsentAction.WITHDRAW,
            PrivacyConsentAction.GRANT,
        ]
        assert other_center.purposes[0].history == []
        assert other_center.purposes[0].granted is False

        with pytest.raises(Phase7NotFoundError):
            await service.transition_consent(
                request_context=_context_b(),
                purpose_id=PURPOSE_A_ID,
                action=PrivacyConsentAction.GRANT,
            )
        events = list(
            await session.scalars(
                select(PrivacyConsentEvent)
                .where(
                    PrivacyConsentEvent.tenant_id == TENANT_A_ID,
                    PrivacyConsentEvent.purpose_id == PURPOSE_A_ID,
                )
                .order_by(PrivacyConsentEvent.occurred_at, PrivacyConsentEvent.id)
            )
        )
        assert len(events) == 2
        assert {event.user_id for event in events} == {USER_A_ID}
        assert {event.membership_id for event in events} == {MEMBERSHIP_A_ID}


async def test_retention_delete_policy_is_tenant_bounded_count_only_and_non_destructive(
    privacy_database: _PrivacyDatabase,
) -> None:
    async with privacy_database.sessions() as session:
        service = PrivacyService(session)
        async with session.begin():
            policy = await service.create_retention_policy(
                request_context=_context_a(),
                payload=RetentionPolicyCreate(
                    data_category=RetentionDataCategory.EMPLOYEE_RECORDS,
                    legal_basis_note="Synthetic legal-basis inventory proof.",
                    retention_days=365,
                    anchor=RetentionAnchor.EMPLOYMENT_END_DATE,
                    action=RetentionAction.DELETE,
                    status=RetentionPolicyStatus.ACTIVE,
                ),
            )

        before_ids = set(
            await session.scalars(select(Employee.id).where(Employee.tenant_id == TENANT_A_ID))
        )
        dry_run = await service.retention_dry_run(
            request_context=_context_a(),
            payload=RetentionDryRunRequest(policy_ids=[policy.id]),
        )
        await session.commit()
        after_ids = set(
            await session.scalars(select(Employee.id).where(Employee.tenant_id == TENANT_A_ID))
        )

        assert len(dry_run.items) == 1
        assert dry_run.items[0].policy_id == policy.id
        assert dry_run.items[0].action is RetentionAction.DELETE
        assert dry_run.items[0].count == 1
        assert after_ids == before_ids

        with pytest.raises(Phase7NotFoundError):
            await service.retention_dry_run(
                request_context=_context_b(),
                payload=RetentionDryRunRequest(policy_ids=[policy.id]),
            )


def _context_a() -> RequestContext:
    return _context(
        tenant_id=TENANT_A_ID,
        tenant_slug="privacy-a",
        actor_id=USER_A_ID,
        membership_id=MEMBERSHIP_A_ID,
    )


def _context_a_other() -> RequestContext:
    return _context(
        tenant_id=TENANT_A_ID,
        tenant_slug="privacy-a",
        actor_id=USER_A_OTHER_ID,
        membership_id=MEMBERSHIP_A_OTHER_ID,
    )


def _context_b() -> RequestContext:
    return _context(
        tenant_id=TENANT_B_ID,
        tenant_slug="privacy-b",
        actor_id=USER_B_ID,
        membership_id=MEMBERSHIP_B_ID,
    )


def _context(
    *,
    tenant_id: UUID,
    tenant_slug: str,
    actor_id: UUID,
    membership_id: UUID,
) -> RequestContext:
    return RequestContext(
        request_id=f"p11-{tenant_slug}-{str(actor_id)[-4:]}",
        trace_id="9a000000000040008000000000000001",
        tenant=TenantContext(tenant_id=tenant_id, slug=tenant_slug),
        actor_id=actor_id,
        membership_id=membership_id,
        session_id=UUID("9a000000-0000-4000-8000-000000000099"),
        authentication_strength=AuthenticationStrength.SINGLE_FACTOR,
    )


def _seed_records() -> list[object]:
    tenants = [
        Tenant(
            id=TENANT_A_ID,
            slug="privacy-a",
            name="Privacy Synthetic Tenant A",
            status=TenantStatus.ACTIVE.value,
            plan_code="core",
            data_region="tr-1",
            locale="tr-TR",
            timezone="Europe/Istanbul",
        ),
        Tenant(
            id=TENANT_B_ID,
            slug="privacy-b",
            name="Privacy Synthetic Tenant B",
            status=TenantStatus.ACTIVE.value,
            plan_code="core",
            data_region="tr-1",
            locale="tr-TR",
            timezone="Europe/Istanbul",
        ),
    ]
    actor_rows = [
        (
            USER_A_ID,
            MEMBERSHIP_A_ID,
            TENANT_A_ID,
            "privacy-a@example.test",
            "Privacy Actor A",
        ),
        (
            USER_A_OTHER_ID,
            MEMBERSHIP_A_OTHER_ID,
            TENANT_A_ID,
            "privacy-a-other@example.test",
            "Privacy Actor A Other",
        ),
        (
            USER_B_ID,
            MEMBERSHIP_B_ID,
            TENANT_B_ID,
            "privacy-b@example.test",
            "Privacy Actor B",
        ),
    ]
    identities = [
        Identity(
            id=UUID(f"9a000000-0000-4000-8000-{100 + index:012d}"),
            email=email,
            status=IdentityStatus.ACTIVE.value,
            password_hash="synthetic-hash",
        )
        for index, (_user_id, _membership_id, _tenant_id, email, _name) in enumerate(
            actor_rows, start=1
        )
    ]
    users = [
        User(
            id=user_id,
            tenant_id=tenant_id,
            email=email,
            full_name=name,
            status=UserStatus.ACTIVE.value,
            password_hash="synthetic-hash",
        )
        for user_id, _membership_id, tenant_id, email, name in actor_rows
    ]
    memberships = [
        TenantMembership(
            id=membership_id,
            tenant_id=tenant_id,
            identity_id=identity.id,
            legacy_user_id=user_id,
            full_name=name,
            status=MembershipStatus.ACTIVE.value,
        )
        for identity, (user_id, membership_id, tenant_id, _email, name) in zip(
            identities, actor_rows, strict=True
        )
    ]
    permission = Permission(
        id=PRIVACY_PERMISSION_ID,
        code="privacy_notice:read:own",
        resource="privacy_notice",
        action="read",
        target="own",
        target_type=PermissionTargetType.SCOPE.value,
        description="Read the current employee privacy notice.",
    )
    role = Role(
        id=PRIVACY_ROLE_ID,
        code="p11_privacy_reader",
        name="Privacy Reader",
        description="Synthetic privacy notice reader",
        scope_type=RoleScopeType.TENANT.value,
    )
    user_roles = [
        UserRole(
            tenant_id=tenant_id,
            user_id=user_id,
            role_id=PRIVACY_ROLE_ID,
            role_scope_type=RoleScopeType.TENANT.value,
            active=True,
        )
        for user_id, _membership_id, tenant_id, _email, _name in actor_rows
    ]
    purposes = [
        PrivacyConsentPurpose(
            id=PURPOSE_A_ID,
            tenant_id=TENANT_A_ID,
            code="optional_updates",
            version=1,
            title="Optional updates",
            description="Synthetic optional processing purpose.",
            is_active=True,
        ),
        PrivacyConsentPurpose(
            id=PURPOSE_B_ID,
            tenant_id=TENANT_B_ID,
            code="optional_updates",
            version=1,
            title="Optional updates",
            description="Synthetic optional processing purpose.",
            is_active=True,
        ),
    ]
    employees = [
        Employee(
            id=UUID("9a000000-0000-4000-8000-000000000081"),
            tenant_id=TENANT_A_ID,
            employee_number="PRIV-A-OLD",
            first_name="Old",
            last_name="Eligible",
            status=EmployeeStatus.TERMINATED.value,
            employment_start_date=date(2018, 1, 1),
            employment_end_date=date(2020, 1, 1),
            termination_reason=EmployeeTerminationReason.CONTRACT_END.value,
        ),
        Employee(
            id=UUID("9a000000-0000-4000-8000-000000000082"),
            tenant_id=TENANT_A_ID,
            employee_number="PRIV-A-ACTIVE",
            first_name="Active",
            last_name="Ineligible",
            status=EmployeeStatus.ACTIVE.value,
            employment_start_date=date(2025, 1, 1),
        ),
        Employee(
            id=UUID("9a000000-0000-4000-8000-000000000083"),
            tenant_id=TENANT_B_ID,
            employee_number="PRIV-B-OLD",
            first_name="Cross",
            last_name="Tenant",
            status=EmployeeStatus.TERMINATED.value,
            employment_start_date=date(2018, 1, 1),
            employment_end_date=date(2020, 1, 1),
            termination_reason=EmployeeTerminationReason.CONTRACT_END.value,
        ),
    ]
    return [
        *tenants,
        *identities,
        *users,
        *memberships,
        permission,
        role,
        RolePermission(role_id=role.id, permission_id=permission.id),
        *user_roles,
        *purposes,
        *employees,
    ]
