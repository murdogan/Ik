"""Tenant-safe employee account linking and backend-authoritative own-profile reads."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from uuid import UUID, uuid4

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.department import Department
from app.models.employee import Employee
from app.models.employee_account_link import EmployeeAccountLink
from app.models.employee_assignment import EmployeeAssignment
from app.models.employee_profile import EmployeeEmploymentProfile, EmployeePersonalProfile
from app.models.identity import Identity, IdentityStatus, MembershipStatus, TenantMembership
from app.models.organization import Branch, LegalEntity
from app.models.position import Position
from app.models.user import User, UserStatus
from app.platform.errors.application import ApplicationError
from app.schemas.employee_account_link import (
    ELIGIBLE_MEMBERSHIP_LIMIT_MAX,
    EmployeeAccountLinkRead,
    EmployeeAccountLinkStateRead,
    EmployeeAccountLinkUpdate,
    EmployeeAccountMembershipRead,
    OwnCurrentAssignmentRead,
    OwnEmployeeEmploymentProfileRead,
    OwnEmployeeOrganizationRead,
    OwnEmployeePersonalProfileRead,
    OwnEmployeeProfileCoreRead,
    OwnEmployeeProfileRead,
    OwnEmployeeProfileStateRead,
    OwnManagerReferenceRead,
    OwnOrganizationReferenceRead,
    OwnPositionReferenceRead,
)
from app.services.employee_service import EmployeeNotFoundError, EmployeeVersionConflictError


class EmployeeAccountLinkNotFoundError(EmployeeNotFoundError):
    """Employee is absent, archived, or outside the selected tenant."""


class EmployeeAccountLinkUnavailableError(ApplicationError):
    """Target account cannot be linked without disclosing why."""


class EmployeeAccountLinkVersionConflictError(EmployeeVersionConflictError):
    """The caller's optimistic link token is stale or invalid for this transition."""


@dataclass(frozen=True, slots=True)
class EmployeeAccountLinkMutation:
    response: EmployeeAccountLinkStateRead
    changed: bool
    previous_membership_id: UUID | None = None
    new_membership_id: UUID | None = None
    link_status: str | None = None


class EmployeeAccountLinkService:
    def __init__(self, session: AsyncSession, *, today: date | None = None) -> None:
        self.session = session
        self.today = today or date.today()

    async def get_account_link(
        self,
        tenant_id: UUID,
        employee_id: UUID,
    ) -> EmployeeAccountLinkStateRead:
        await self._require_current_employee(tenant_id, employee_id)
        row = await self._account_link_row(tenant_id, employee_id)
        return await self._link_state(tenant_id, employee_id, row)

    async def list_eligible_memberships(
        self,
        tenant_id: UUID,
        employee_id: UUID,
        *,
        query: str | None = None,
        limit: int = ELIGIBLE_MEMBERSHIP_LIMIT_MAX,
    ) -> list[EmployeeAccountMembershipRead]:
        await self._require_current_employee(tenant_id, employee_id)
        if limit < 1 or limit > ELIGIBLE_MEMBERSHIP_LIMIT_MAX:
            raise ValueError("Eligible membership limit is outside the bounded range")

        statement = (
            select(TenantMembership, User)
            .join(
                User,
                and_(
                    User.tenant_id == TenantMembership.tenant_id,
                    User.id == TenantMembership.legacy_user_id,
                ),
            )
            .outerjoin(
                EmployeeAccountLink,
                and_(
                    EmployeeAccountLink.tenant_id == TenantMembership.tenant_id,
                    EmployeeAccountLink.membership_id == TenantMembership.id,
                ),
            )
            .where(
                TenantMembership.tenant_id == tenant_id,
                EmployeeAccountLink.id.is_(None),
                *self._membership_eligibility_predicates(),
            )
            .order_by(func.lower(TenantMembership.full_name), TenantMembership.id)
            .limit(limit)
        )
        normalized_query = query.strip() if query is not None else ""
        if normalized_query:
            statement = statement.where(
                or_(
                    TenantMembership.full_name.icontains(normalized_query, autoescape=True),
                    User.email.icontains(normalized_query, autoescape=True),
                )
            )
        if not self._is_postgresql:
            statement = statement.join(
                Identity,
                Identity.id == TenantMembership.identity_id,
            ).where(Identity.status == IdentityStatus.ACTIVE.value)

        rows = (await self.session.execute(statement)).all()
        return [_membership_read(membership, user, eligible=True) for membership, user in rows]

    async def update_account_link(
        self,
        tenant_id: UUID,
        employee_id: UUID,
        payload: EmployeeAccountLinkUpdate,
    ) -> EmployeeAccountLinkMutation:
        await self._require_current_employee(tenant_id, employee_id, lock=True)
        row = await self._account_link_row(tenant_id, employee_id, lock=True)
        current_link = row[0] if row is not None else None

        if current_link is None and payload.membership_id is None:
            return EmployeeAccountLinkMutation(
                response=EmployeeAccountLinkStateRead(employee_id=employee_id, link=None),
                changed=False,
            )
        if current_link is not None and current_link.membership_id == payload.membership_id:
            return EmployeeAccountLinkMutation(
                response=await self._link_state(tenant_id, employee_id, row),
                changed=False,
            )

        if current_link is None:
            if payload.expected_version is not None:
                raise EmployeeAccountLinkVersionConflictError
        elif payload.expected_version != current_link.version:
            raise EmployeeAccountLinkVersionConflictError

        previous_membership_id = current_link.membership_id if current_link is not None else None
        if payload.membership_id is None:
            assert current_link is not None
            await self.session.delete(current_link)
            await self.session.flush()
            return EmployeeAccountLinkMutation(
                response=EmployeeAccountLinkStateRead(employee_id=employee_id, link=None),
                changed=True,
                previous_membership_id=previous_membership_id,
                link_status="unlinked",
            )

        membership_row = await self._eligible_membership_row(
            tenant_id,
            employee_id,
            payload.membership_id,
            lock=True,
        )
        if membership_row is None:
            raise EmployeeAccountLinkUnavailableError

        if current_link is None:
            current_link = EmployeeAccountLink(
                id=uuid4(),
                tenant_id=tenant_id,
                employee_id=employee_id,
                membership_id=payload.membership_id,
                version=1,
            )
            self.session.add(current_link)
            link_status = "linked"
        else:
            current_link.membership_id = payload.membership_id
            link_status = "relinked"

        await self.session.flush()
        await self.session.refresh(current_link)
        membership, user = membership_row
        return EmployeeAccountLinkMutation(
            response=EmployeeAccountLinkStateRead(
                employee_id=employee_id,
                link=await self._link_read(
                    tenant_id,
                    current_link,
                    membership,
                    user,
                ),
            ),
            changed=True,
            previous_membership_id=previous_membership_id,
            new_membership_id=payload.membership_id,
            link_status=link_status,
        )

    async def get_own_profile(
        self,
        tenant_id: UUID,
        membership_id: UUID,
        actor_user_id: UUID,
    ) -> OwnEmployeeProfileStateRead:
        statement = (
            select(
                Employee,
                EmployeePersonalProfile,
                EmployeeEmploymentProfile,
            )
            .join(
                EmployeeAccountLink,
                and_(
                    EmployeeAccountLink.tenant_id == Employee.tenant_id,
                    EmployeeAccountLink.employee_id == Employee.id,
                ),
            )
            .join(
                TenantMembership,
                and_(
                    TenantMembership.tenant_id == EmployeeAccountLink.tenant_id,
                    TenantMembership.id == EmployeeAccountLink.membership_id,
                ),
            )
            .join(
                User,
                and_(
                    User.tenant_id == TenantMembership.tenant_id,
                    User.id == TenantMembership.legacy_user_id,
                ),
            )
            .join(
                EmployeePersonalProfile,
                and_(
                    EmployeePersonalProfile.tenant_id == Employee.tenant_id,
                    EmployeePersonalProfile.employee_id == Employee.id,
                ),
            )
            .join(
                EmployeeEmploymentProfile,
                and_(
                    EmployeeEmploymentProfile.tenant_id == Employee.tenant_id,
                    EmployeeEmploymentProfile.employee_id == Employee.id,
                ),
            )
            .where(
                Employee.tenant_id == tenant_id,
                Employee.archived_at.is_(None),
                EmployeeAccountLink.membership_id == membership_id,
                TenantMembership.legacy_user_id == actor_user_id,
                User.id == actor_user_id,
                *self._membership_eligibility_predicates(),
            )
        )
        if not self._is_postgresql:
            statement = statement.join(
                Identity,
                Identity.id == TenantMembership.identity_id,
            ).where(Identity.status == IdentityStatus.ACTIVE.value)

        row = (await self.session.execute(statement)).one_or_none()
        if row is None:
            return _unavailable_own_profile()
        employee, personal, employment = row
        current_assignment = await self._own_current_assignment(tenant_id, employee.id)
        return OwnEmployeeProfileStateRead(
            availability="available",
            membership_id=membership_id,
            profile=OwnEmployeeProfileRead(
                core=OwnEmployeeProfileCoreRead(
                    id=employee.id,
                    employee_number=employee.employee_number,
                    first_name=employee.first_name,
                    last_name=employee.last_name,
                    email=employee.email,
                    status=employee.status,
                ),
                personal=OwnEmployeePersonalProfileRead(
                    preferred_name=personal.preferred_name,
                    birth_date=personal.birth_date,
                    phone=personal.phone,
                ),
                employment=OwnEmployeeEmploymentProfileRead(
                    employment_start_date=employee.employment_start_date,
                    contract_type=employment.contract_type,
                    work_type=employment.work_type,
                ),
                organization=OwnEmployeeOrganizationRead(
                    current_assignment=current_assignment,
                ),
            ),
        )

    async def _require_current_employee(
        self,
        tenant_id: UUID,
        employee_id: UUID,
        *,
        lock: bool = False,
    ) -> Employee:
        statement = select(Employee).where(
            Employee.tenant_id == tenant_id,
            Employee.id == employee_id,
            Employee.archived_at.is_(None),
        )
        if lock:
            statement = statement.with_for_update(of=Employee)
        employee = await self.session.scalar(statement)
        if employee is None:
            raise EmployeeAccountLinkNotFoundError
        return employee

    async def _account_link_row(
        self,
        tenant_id: UUID,
        employee_id: UUID,
        *,
        lock: bool = False,
    ) -> tuple[EmployeeAccountLink, TenantMembership, User] | None:
        statement = (
            select(EmployeeAccountLink, TenantMembership, User)
            .join(
                TenantMembership,
                and_(
                    TenantMembership.tenant_id == EmployeeAccountLink.tenant_id,
                    TenantMembership.id == EmployeeAccountLink.membership_id,
                ),
            )
            .join(
                User,
                and_(
                    User.tenant_id == TenantMembership.tenant_id,
                    User.id == TenantMembership.legacy_user_id,
                ),
            )
            .where(
                EmployeeAccountLink.tenant_id == tenant_id,
                EmployeeAccountLink.employee_id == employee_id,
            )
        )
        if lock:
            statement = statement.with_for_update(of=EmployeeAccountLink)
        row = (await self.session.execute(statement)).one_or_none()
        if row is None:
            return None
        link, membership, user = row
        return link, membership, user

    async def _eligible_membership_row(
        self,
        tenant_id: UUID,
        employee_id: UUID,
        membership_id: UUID,
        *,
        lock: bool,
    ) -> tuple[TenantMembership, User] | None:
        statement = (
            select(TenantMembership, User)
            .join(
                User,
                and_(
                    User.tenant_id == TenantMembership.tenant_id,
                    User.id == TenantMembership.legacy_user_id,
                ),
            )
            .outerjoin(
                EmployeeAccountLink,
                and_(
                    EmployeeAccountLink.tenant_id == TenantMembership.tenant_id,
                    EmployeeAccountLink.membership_id == TenantMembership.id,
                ),
            )
            .where(
                TenantMembership.tenant_id == tenant_id,
                TenantMembership.id == membership_id,
                or_(
                    EmployeeAccountLink.id.is_(None),
                    EmployeeAccountLink.employee_id == employee_id,
                ),
                *self._membership_eligibility_predicates(),
            )
        )
        if not self._is_postgresql:
            statement = statement.join(
                Identity,
                Identity.id == TenantMembership.identity_id,
            ).where(Identity.status == IdentityStatus.ACTIVE.value)
        if lock:
            statement = statement.with_for_update(of=TenantMembership)
        row = (await self.session.execute(statement)).one_or_none()
        if row is None:
            return None
        membership, user = row
        return membership, user

    def _membership_eligibility_predicates(self) -> tuple[object, ...]:
        predicates: tuple[object, ...] = (
            TenantMembership.status == MembershipStatus.ACTIVE.value,
            User.status == UserStatus.ACTIVE.value,
            TenantMembership.permission_version == User.permission_version,
        )
        if self._is_postgresql:
            predicates += (
                func.public.is_current_tenant_membership_link_eligible(TenantMembership.id).is_(
                    True
                ),
            )
        return predicates

    async def _link_state(
        self,
        tenant_id: UUID,
        employee_id: UUID,
        row: tuple[EmployeeAccountLink, TenantMembership, User] | None,
    ) -> EmployeeAccountLinkStateRead:
        if row is None:
            return EmployeeAccountLinkStateRead(employee_id=employee_id, link=None)
        link, membership, user = row
        return EmployeeAccountLinkStateRead(
            employee_id=employee_id,
            link=await self._link_read(tenant_id, link, membership, user),
        )

    async def _link_read(
        self,
        tenant_id: UUID,
        link: EmployeeAccountLink,
        membership: TenantMembership,
        user: User,
    ) -> EmployeeAccountLinkRead:
        return EmployeeAccountLinkRead(
            id=link.id,
            membership=_membership_read(
                membership,
                user,
                eligible=await self._membership_is_eligible(
                    tenant_id,
                    membership,
                    user,
                ),
            ),
            version=link.version,
            created_at=link.created_at,
            updated_at=link.updated_at,
        )

    async def _membership_is_eligible(
        self,
        tenant_id: UUID,
        membership: TenantMembership,
        user: User,
    ) -> bool:
        if (
            membership.tenant_id != tenant_id
            or user.tenant_id != tenant_id
            or membership.legacy_user_id != user.id
            or membership.status != MembershipStatus.ACTIVE.value
            or user.status != UserStatus.ACTIVE.value
            or membership.permission_version != user.permission_version
        ):
            return False
        if self._is_postgresql:
            return bool(
                await self.session.scalar(
                    select(func.public.is_current_tenant_membership_link_eligible(membership.id))
                )
            )
        identity_status = await self.session.scalar(
            select(Identity.status).where(Identity.id == membership.identity_id)
        )
        return identity_status == IdentityStatus.ACTIVE.value

    async def _own_current_assignment(
        self,
        tenant_id: UUID,
        employee_id: UUID,
    ) -> OwnCurrentAssignmentRead | None:
        statement = (
            select(
                LegalEntity,
                Branch,
                Department,
                Position,
                User.full_name,
            )
            .select_from(EmployeeAssignment)
            .join(
                LegalEntity,
                and_(
                    LegalEntity.tenant_id == EmployeeAssignment.tenant_id,
                    LegalEntity.id == EmployeeAssignment.legal_entity_id,
                ),
            )
            .join(
                Branch,
                and_(
                    Branch.tenant_id == EmployeeAssignment.tenant_id,
                    Branch.id == EmployeeAssignment.branch_id,
                ),
            )
            .join(
                Department,
                and_(
                    Department.tenant_id == EmployeeAssignment.tenant_id,
                    Department.id == EmployeeAssignment.department_id,
                ),
            )
            .join(
                Position,
                and_(
                    Position.tenant_id == EmployeeAssignment.tenant_id,
                    Position.id == EmployeeAssignment.position_id,
                ),
            )
            .outerjoin(
                User,
                and_(
                    User.tenant_id == EmployeeAssignment.tenant_id,
                    User.id == EmployeeAssignment.manager_user_id,
                ),
            )
            .where(
                EmployeeAssignment.tenant_id == tenant_id,
                EmployeeAssignment.employee_id == employee_id,
                EmployeeAssignment.effective_from <= self.today,
                or_(
                    EmployeeAssignment.effective_to.is_(None),
                    EmployeeAssignment.effective_to > self.today,
                ),
            )
            .order_by(
                EmployeeAssignment.effective_from.desc(),
                EmployeeAssignment.id.desc(),
            )
            .limit(1)
        )
        row = (await self.session.execute(statement)).one_or_none()
        if row is None:
            return None
        legal_entity, branch, department, position, manager_full_name = row
        return OwnCurrentAssignmentRead(
            legal_entity=OwnOrganizationReferenceRead(
                code=legal_entity.code,
                name=legal_entity.name,
            ),
            branch=OwnOrganizationReferenceRead(code=branch.code, name=branch.name),
            department=OwnOrganizationReferenceRead(
                code=department.code,
                name=department.name,
            ),
            position=OwnPositionReferenceRead(code=position.code, title=position.title),
            manager=(
                OwnManagerReferenceRead(full_name=manager_full_name)
                if manager_full_name is not None
                else None
            ),
        )

    @property
    def _is_postgresql(self) -> bool:
        return self.session.get_bind().dialect.name == "postgresql"


def _membership_read(
    membership: TenantMembership,
    user: User,
    *,
    eligible: bool,
) -> EmployeeAccountMembershipRead:
    return EmployeeAccountMembershipRead(
        membership_id=membership.id,
        full_name=membership.full_name,
        email=user.email,
        membership_status=membership.status,
        user_status=user.status,
        eligible=eligible,
    )


def _unavailable_own_profile() -> OwnEmployeeProfileStateRead:
    return OwnEmployeeProfileStateRead(
        availability="unavailable",
        membership_id=None,
        profile=None,
    )


__all__ = [
    "EmployeeAccountLinkMutation",
    "EmployeeAccountLinkNotFoundError",
    "EmployeeAccountLinkService",
    "EmployeeAccountLinkUnavailableError",
    "EmployeeAccountLinkVersionConflictError",
]
