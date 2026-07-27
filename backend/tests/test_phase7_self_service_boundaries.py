"""Critical Phase 7 self-service, announcement, and notification boundaries."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime
from uuid import UUID

import pytest
from app.db.base import Base
from app.models.announcement import AnnouncementRecipient
from app.models.authorization import Permission, Role, RolePermission, UserRole
from app.models.document_request import EmployeeDocumentRequestType
from app.models.employee import Employee, EmployeeStatus
from app.models.employee_account_link import EmployeeAccountLink
from app.models.identity import Identity, IdentityStatus, MembershipStatus, TenantMembership
from app.models.leave import OutboxEvent
from app.models.notification import Notification
from app.models.tenant import Tenant, TenantStatus
from app.models.user import User, UserStatus
from app.platform.authorization import PermissionTargetType, RoleScopeType
from app.platform.request_context import AuthenticationStrength, RequestContext
from app.platform.tenancy import TenantContext
from app.schemas.announcement import AnnouncementCreate, AnnouncementTargets
from app.schemas.document_request import EmployeeDocumentRequestCreate
from app.schemas.request_projection import UnifiedRequestKind
from app.services.announcement_service import AnnouncementService
from app.services.document_request_service import DocumentRequestService
from app.services.notification_service import NotificationService
from app.services.phase7_access import Phase7NotFoundError
from app.services.request_projection_service import RequestProjectionService
from sqlalchemy import select
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool

TENANT_A_ID = UUID("71a00000-0000-4000-8000-000000000001")
TENANT_B_ID = UUID("71a00000-0000-4000-8000-000000000002")
USER_A_ID = UUID("71a00000-0000-4000-8000-000000000011")
USER_A_OTHER_ID = UUID("71a00000-0000-4000-8000-000000000012")
USER_A_HR_ID = UUID("71a00000-0000-4000-8000-000000000013")
USER_B_ID = UUID("71a00000-0000-4000-8000-000000000021")
MEMBERSHIP_A_ID = UUID("71a00000-0000-4000-8000-000000000031")
MEMBERSHIP_A_OTHER_ID = UUID("71a00000-0000-4000-8000-000000000032")
MEMBERSHIP_A_HR_ID = UUID("71a00000-0000-4000-8000-000000000033")
MEMBERSHIP_B_ID = UUID("71a00000-0000-4000-8000-000000000041")
EMPLOYEE_A_ID = UUID("71a00000-0000-4000-8000-000000000051")
EMPLOYEE_A_OTHER_ID = UUID("71a00000-0000-4000-8000-000000000052")
EMPLOYEE_B_ID = UUID("71a00000-0000-4000-8000-000000000061")
TARGET_ROLE_ID = UUID("71a00000-0000-4000-8000-000000000071")
OTHER_ROLE_ID = UUID("71a00000-0000-4000-8000-000000000072")
ANNOUNCEMENT_PERMISSION_ID = UUID("71a00000-0000-4000-8000-000000000081")
NOTIFICATION_A_ID = UUID("71a00000-0000-4000-8000-000000000091")
NOTIFICATION_A_OTHER_ID = UUID("71a00000-0000-4000-8000-000000000092")
NOTIFICATION_B_ID = UUID("71a00000-0000-4000-8000-000000000093")
NOW = datetime(2026, 7, 27, 12, 0, tzinfo=UTC)


@dataclass(slots=True)
class _Phase7Database:
    engine: AsyncEngine
    sessions: async_sessionmaker[AsyncSession]


@pytest.fixture
async def phase7_database():
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
        yield _Phase7Database(engine=engine, sessions=sessions)
    finally:
        await engine.dispose()


async def test_document_request_target_and_unified_projection_are_scope_bounded(
    phase7_database: _Phase7Database,
) -> None:
    async with phase7_database.sessions() as session:
        document_requests = DocumentRequestService(session)
        async with session.begin():
            own_request = await document_requests.create(
                request_context=_context_a(),
                payload=EmployeeDocumentRequestCreate(
                    request_type=EmployeeDocumentRequestType.EMPLOYMENT_LETTER
                ),
            )
            other_request = await document_requests.create(
                request_context=_context_a_other(),
                payload=EmployeeDocumentRequestCreate(
                    request_type=EmployeeDocumentRequestType.EMPLOYMENT_LETTER
                ),
            )
            tenant_b_request = await document_requests.create(
                request_context=_context_b(),
                payload=EmployeeDocumentRequestCreate(
                    request_type=EmployeeDocumentRequestType.EMPLOYMENT_LETTER
                ),
            )

        assert own_request.employee_id == EMPLOYEE_A_ID
        assert other_request.employee_id == EMPLOYEE_A_OTHER_ID
        assert tenant_b_request.employee_id == EMPLOYEE_B_ID

        with pytest.raises(Phase7NotFoundError):
            await document_requests.get(
                tenant_id=TENANT_A_ID,
                actor_id=USER_A_ID,
                request_id=other_request.id,
                own=True,
            )
        with pytest.raises(Phase7NotFoundError):
            await document_requests.get(
                tenant_id=TENANT_A_ID,
                actor_id=USER_A_ID,
                request_id=tenant_b_request.id,
                own=False,
            )

        projection = RequestProjectionService(session)
        own_page = await projection.list_page(
            tenant_id=TENANT_A_ID,
            actor_id=USER_A_ID,
            membership_id=MEMBERSHIP_A_ID,
            permissions=("request:read:own",),
            limit=20,
            cursor=None,
            kind=UnifiedRequestKind.DOCUMENT,
            status=None,
        )
        team_page = await projection.list_page(
            tenant_id=TENANT_A_ID,
            actor_id=USER_A_ID,
            membership_id=MEMBERSHIP_A_ID,
            permissions=("request:read:team",),
            limit=20,
            cursor=None,
            kind=UnifiedRequestKind.DOCUMENT,
            status=None,
        )
        tenant_page = await projection.list_page(
            tenant_id=TENANT_A_ID,
            actor_id=USER_A_HR_ID,
            membership_id=MEMBERSHIP_A_HR_ID,
            permissions=("request:read:tenant",),
            limit=20,
            cursor=None,
            kind=UnifiedRequestKind.DOCUMENT,
            status=None,
        )

        assert [item.id for item in own_page.items] == [own_request.id]
        assert team_page.items == []
        assert {item.id for item in tenant_page.items} == {
            own_request.id,
            other_request.id,
        }


async def test_targeted_critical_announcement_visibility_and_ack_are_recipient_bound(
    phase7_database: _Phase7Database,
) -> None:
    async with phase7_database.sessions() as session:
        service = AnnouncementService(session)
        async with session.begin():
            announcement = await service.create(
                request_context=_context_a_hr(),
                payload=AnnouncementCreate(
                    title="Critical synthetic announcement",
                    body="Only the snapshotted target audience may read this.",
                    is_critical=True,
                    targets=AnnouncementTargets(role_ids=[TARGET_ROLE_ID]),
                ),
            )
            await service.publish(
                request_context=_context_a_hr(),
                announcement_id=announcement.id,
                expected_version=announcement.version,
            )

        recipient_ids = set(
            await session.scalars(
                select(AnnouncementRecipient.recipient_user_id).where(
                    AnnouncementRecipient.announcement_id == announcement.id
                )
            )
        )
        assert recipient_ids == {USER_A_ID}

        own_page = await service.list_page(
            tenant_id=TENANT_A_ID,
            actor_id=USER_A_ID,
            manage=False,
            status=None,
            limit=20,
            cursor=None,
        )
        excluded_page = await service.list_page(
            tenant_id=TENANT_A_ID,
            actor_id=USER_A_OTHER_ID,
            manage=False,
            status=None,
            limit=20,
            cursor=None,
        )
        cross_tenant_page = await service.list_page(
            tenant_id=TENANT_B_ID,
            actor_id=USER_B_ID,
            manage=False,
            status=None,
            limit=20,
            cursor=None,
        )
        assert [item.id for item in own_page.items] == [announcement.id]
        assert excluded_page.items == []
        assert cross_tenant_page.items == []

        with pytest.raises(Phase7NotFoundError):
            await service.acknowledge(
                request_context=_context_a_other(),
                announcement_id=announcement.id,
                expected_version=1,
            )
        with pytest.raises(Phase7NotFoundError):
            await service.acknowledge(
                request_context=_context_b(),
                announcement_id=announcement.id,
                expected_version=1,
            )

        acknowledged = await service.acknowledge(
            request_context=_context_a(),
            announcement_id=announcement.id,
            expected_version=1,
        )
        await session.commit()
        assert acknowledged.read_at is not None
        assert acknowledged.acknowledged_at is not None


async def test_notification_list_and_mark_read_are_current_actor_only(
    phase7_database: _Phase7Database,
) -> None:
    async with phase7_database.sessions() as session:
        service = NotificationService(session)
        own = await service.list_page(
            tenant_id=TENANT_A_ID,
            actor_id=USER_A_ID,
            limit=20,
            cursor=None,
            unread_only=False,
        )
        assert [item.id for item in own.items] == [NOTIFICATION_A_ID]
        assert own.unread_count == 1

        with pytest.raises(Phase7NotFoundError):
            await service.mark_read(
                tenant_id=TENANT_A_ID,
                actor_id=USER_A_ID,
                notification_id=NOTIFICATION_A_OTHER_ID,
                expected_version=1,
            )
        with pytest.raises(Phase7NotFoundError):
            await service.mark_read(
                tenant_id=TENANT_B_ID,
                actor_id=USER_B_ID,
                notification_id=NOTIFICATION_A_ID,
                expected_version=1,
            )

        marked = await service.mark_read(
            tenant_id=TENANT_A_ID,
            actor_id=USER_A_ID,
            notification_id=NOTIFICATION_A_ID,
            expected_version=1,
        )
        await session.commit()
        assert marked.read_at is not None
        unread = await service.list_page(
            tenant_id=TENANT_A_ID,
            actor_id=USER_A_ID,
            limit=20,
            cursor=None,
            unread_only=True,
        )
        assert unread.items == []
        assert unread.unread_count == 0

        other = await session.scalar(
            select(Notification).where(Notification.id == NOTIFICATION_A_OTHER_ID)
        )
        assert other is not None
        assert other.read_at is None


def _context_a() -> RequestContext:
    return _context(
        tenant_id=TENANT_A_ID,
        tenant_slug="phase7-a",
        actor_id=USER_A_ID,
        membership_id=MEMBERSHIP_A_ID,
    )


def _context_a_other() -> RequestContext:
    return _context(
        tenant_id=TENANT_A_ID,
        tenant_slug="phase7-a",
        actor_id=USER_A_OTHER_ID,
        membership_id=MEMBERSHIP_A_OTHER_ID,
    )


def _context_a_hr() -> RequestContext:
    return _context(
        tenant_id=TENANT_A_ID,
        tenant_slug="phase7-a",
        actor_id=USER_A_HR_ID,
        membership_id=MEMBERSHIP_A_HR_ID,
    )


def _context_b() -> RequestContext:
    return _context(
        tenant_id=TENANT_B_ID,
        tenant_slug="phase7-b",
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
        trace_id="71a00000000040008000000000000001",
        tenant=TenantContext(tenant_id=tenant_id, slug=tenant_slug),
        actor_id=actor_id,
        membership_id=membership_id,
        authentication_strength=AuthenticationStrength.SINGLE_FACTOR,
    )


def _seed_records() -> list[object]:
    tenants = [
        Tenant(
            id=TENANT_A_ID,
            slug="phase7-a",
            name="Phase 7 Synthetic Tenant A",
            status=TenantStatus.ACTIVE.value,
            plan_code="core",
            data_region="tr-1",
            locale="tr-TR",
            timezone="Europe/Istanbul",
        ),
        Tenant(
            id=TENANT_B_ID,
            slug="phase7-b",
            name="Phase 7 Synthetic Tenant B",
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
            "phase7-a-target@example.test",
            "Target Employee",
        ),
        (
            USER_A_OTHER_ID,
            MEMBERSHIP_A_OTHER_ID,
            TENANT_A_ID,
            "phase7-a-other@example.test",
            "Other Employee",
        ),
        (
            USER_A_HR_ID,
            MEMBERSHIP_A_HR_ID,
            TENANT_A_ID,
            "phase7-a-hr@example.test",
            "HR Publisher",
        ),
        (
            USER_B_ID,
            MEMBERSHIP_B_ID,
            TENANT_B_ID,
            "phase7-b-target@example.test",
            "Cross Tenant Employee",
        ),
    ]
    identities = [
        Identity(
            id=UUID(f"71a00000-0000-4000-8000-{index:012d}"),
            email=email,
            status=IdentityStatus.ACTIVE.value,
            password_hash="synthetic-hash",
        )
        for index, (_user_id, _membership_id, _tenant_id, email, _name) in enumerate(
            actor_rows, start=101
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
    employees = [
        Employee(
            id=EMPLOYEE_A_ID,
            tenant_id=TENANT_A_ID,
            employee_number="P7-A-001",
            first_name="Target",
            last_name="Employee",
            status=EmployeeStatus.ACTIVE.value,
            employment_start_date=date(2026, 1, 1),
        ),
        Employee(
            id=EMPLOYEE_A_OTHER_ID,
            tenant_id=TENANT_A_ID,
            employee_number="P7-A-002",
            first_name="Other",
            last_name="Employee",
            status=EmployeeStatus.ACTIVE.value,
            employment_start_date=date(2026, 1, 1),
        ),
        Employee(
            id=EMPLOYEE_B_ID,
            tenant_id=TENANT_B_ID,
            employee_number="P7-B-001",
            first_name="Cross",
            last_name="Tenant",
            status=EmployeeStatus.ACTIVE.value,
            employment_start_date=date(2026, 1, 1),
        ),
    ]
    links = [
        EmployeeAccountLink(
            id=UUID("71a00000-0000-4000-8000-000000000111"),
            tenant_id=TENANT_A_ID,
            employee_id=EMPLOYEE_A_ID,
            membership_id=MEMBERSHIP_A_ID,
        ),
        EmployeeAccountLink(
            id=UUID("71a00000-0000-4000-8000-000000000112"),
            tenant_id=TENANT_A_ID,
            employee_id=EMPLOYEE_A_OTHER_ID,
            membership_id=MEMBERSHIP_A_OTHER_ID,
        ),
        EmployeeAccountLink(
            id=UUID("71a00000-0000-4000-8000-000000000113"),
            tenant_id=TENANT_B_ID,
            employee_id=EMPLOYEE_B_ID,
            membership_id=MEMBERSHIP_B_ID,
        ),
    ]
    permission = Permission(
        id=ANNOUNCEMENT_PERMISSION_ID,
        code="announcement:read:own",
        resource="announcement",
        action="read",
        target="own",
        target_type=PermissionTargetType.SCOPE.value,
        description="Read announcements snapshotted for this user.",
    )
    roles = [
        Role(
            id=TARGET_ROLE_ID,
            code="p11_phase7_target",
            name="Phase 7 Target",
            description="Synthetic target role",
            scope_type=RoleScopeType.TENANT.value,
        ),
        Role(
            id=OTHER_ROLE_ID,
            code="p11_phase7_other",
            name="Phase 7 Other",
            description="Synthetic non-target role",
            scope_type=RoleScopeType.TENANT.value,
        ),
    ]
    role_permissions = [
        RolePermission(role_id=role.id, permission_id=permission.id) for role in roles
    ]
    user_roles = [
        UserRole(
            tenant_id=TENANT_A_ID,
            user_id=USER_A_ID,
            role_id=TARGET_ROLE_ID,
            role_scope_type=RoleScopeType.TENANT.value,
            active=True,
        ),
        UserRole(
            tenant_id=TENANT_A_ID,
            user_id=USER_A_OTHER_ID,
            role_id=OTHER_ROLE_ID,
            role_scope_type=RoleScopeType.TENANT.value,
            active=True,
        ),
        UserRole(
            tenant_id=TENANT_A_ID,
            user_id=USER_A_HR_ID,
            role_id=OTHER_ROLE_ID,
            role_scope_type=RoleScopeType.TENANT.value,
            active=True,
        ),
        UserRole(
            tenant_id=TENANT_B_ID,
            user_id=USER_B_ID,
            role_id=TARGET_ROLE_ID,
            role_scope_type=RoleScopeType.TENANT.value,
            active=True,
        ),
    ]
    notification_rows: list[object] = []
    for index, (notification_id, tenant_id, recipient_id) in enumerate(
        (
            (NOTIFICATION_A_ID, TENANT_A_ID, USER_A_ID),
            (NOTIFICATION_A_OTHER_ID, TENANT_A_ID, USER_A_OTHER_ID),
            (NOTIFICATION_B_ID, TENANT_B_ID, USER_B_ID),
        ),
        start=1,
    ):
        event_id = UUID(f"71a00000-0000-4000-8000-{200 + index:012d}")
        notification_rows.extend(
            (
                OutboxEvent(
                    id=event_id,
                    tenant_id=tenant_id,
                    aggregate_type="leave_request",
                    aggregate_id=UUID(f"71a00000-0000-4000-8000-{300 + index:012d}"),
                    event_type="leave.requested",
                    payload={"request_id": f"synthetic-{index}"},
                    source_key=f"p11-phase7-notification-{index}",
                    occurred_at=NOW,
                    created_at=NOW,
                ),
                Notification(
                    id=notification_id,
                    tenant_id=tenant_id,
                    recipient_user_id=recipient_id,
                    source_event_id=event_id,
                    source_key=f"p11-phase7-notification-{index}",
                    notification_type="leave.requested",
                    title=f"Synthetic notification {index}",
                    body="Synthetic notification body.",
                    portal_path="/leave",
                    read_at=None,
                    version=1,
                    created_at=NOW,
                ),
            )
        )
    return [
        *tenants,
        *identities,
        *users,
        *memberships,
        *employees,
        *links,
        permission,
        *roles,
        *role_permissions,
        *user_roles,
        *notification_rows,
    ]
