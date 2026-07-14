"""P4E employee profile-change workflow, projections, and concurrency rules."""

from __future__ import annotations

from collections.abc import Callable, Collection
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import cast
from uuid import UUID

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.employee import Employee
from app.models.employee_account_link import EmployeeAccountLink
from app.models.employee_profile import EmployeePersonalProfile
from app.models.employee_profile_change_request import (
    EmployeeProfileChangeRequest,
    EmployeeProfileChangeRequestStatus,
)
from app.models.identity import Identity, IdentityStatus, MembershipStatus, TenantMembership
from app.models.user import User, UserStatus
from app.platform.authorization import DenyByDefaultPolicy
from app.platform.errors.application import ApplicationError
from app.platform.pagination import CursorPage, InvalidCursorError, decode_cursor, encode_cursor
from app.schemas.employee_account_link import OwnMaskedFieldRead
from app.schemas.employee_profile_change_request import (
    EmployeeProfileChangeFieldName,
    EmployeeProfileChangeRequestCreate,
    EmployeeProfileChangeRequestEmployeeRead,
    EmployeeProfileChangeRequestExpectedVersion,
    EmployeeProfileChangeRequestHrDetailRead,
    EmployeeProfileChangeRequestHrSummaryRead,
    EmployeeProfileChangeRequestReject,
    HrBirthDateChangeRead,
    HrEmployeeProfileChangesRead,
    HrPhoneChangeRead,
    HrPreferredNameChangeRead,
    OwnEmployeeProfileChangeRequestRead,
    OwnEmployeeProfileChangesRead,
    OwnMaskedProfileChangeRead,
    OwnPreferredNameChangeRead,
    normalized_existing_phone,
)
from app.services.employee_field_policy import (
    PROFILE_CHANGE_REQUESTABLE_FIELDS,
    EmployeeProjectionScope,
    project_field,
)

ACTIVE_PROFILE_CHANGE_REQUEST_CONSTRAINT = "uq_employee_profile_change_requests_active_employee"
EMPLOYEE_READ_TENANT_PERMISSION = "employee:read:tenant"
EMPLOYEE_UPDATE_TENANT_PERMISSION = "employee:update:tenant"
_OWN_CURSOR_RESOURCE = "own_employee_profile_change_requests"
_HR_CURSOR_RESOURCE = "hr_employee_profile_change_requests"
_FIELD_ORDER: tuple[EmployeeProfileChangeFieldName, ...] = (
    "preferred_name",
    "phone",
    "birth_date",
)
_POLICY = DenyByDefaultPolicy()


class EmployeeProfileChangeRequestInvalidError(ApplicationError, ValueError):
    """The closed command is invalid or contains a normalized no-op."""


class EmployeeProfileChangeRequestNotFoundError(ApplicationError):
    """The request is absent, unrelated, or outside the selected tenant."""


class EmployeeProfileChangeRequestConflictError(ApplicationError):
    """An active request or optimistic request transition won the race."""


class EmployeeProfileChangeRequestStaleProfileError(ApplicationError):
    """The personal-profile base changed after request submission."""


@dataclass(frozen=True, slots=True)
class EmployeeProfileChangeRequestMutation:
    response: OwnEmployeeProfileChangeRequestRead | EmployeeProfileChangeRequestHrDetailRead
    request_id: UUID
    employee_id: UUID
    changed_fields: tuple[EmployeeProfileChangeFieldName, ...]
    before_status: str
    after_status: str


@dataclass(frozen=True, slots=True)
class _OwnTarget:
    employee: Employee
    personal: EmployeePersonalProfile


class EmployeeProfileChangeRequestService:
    def __init__(
        self,
        session: AsyncSession,
        *,
        now_factory: Callable[[], datetime] | None = None,
    ) -> None:
        self.session = session
        self._now_factory = now_factory or (lambda: datetime.now(UTC))

    async def submit_own(
        self,
        *,
        request_id: UUID,
        tenant_id: UUID,
        membership_id: UUID,
        actor_user_id: UUID,
        payload: EmployeeProfileChangeRequestCreate,
    ) -> EmployeeProfileChangeRequestMutation:
        selected_fields = payload.selected_fields()
        self._require_requestable_fields(selected_fields)

        if self._is_postgresql:
            outcome = await self.session.scalar(
                select(
                    func.public.submit_own_employee_profile_change_request(
                        request_id,
                        "preferred_name" in selected_fields,
                        payload.preferred_name,
                        "phone" in selected_fields,
                        payload.phone,
                        "birth_date" in selected_fields,
                        payload.birth_date,
                    )
                )
            )
            self._raise_submit_outcome(outcome)
            request = await self._get_own_request_row(
                tenant_id=tenant_id,
                membership_id=membership_id,
                actor_user_id=actor_user_id,
                request_id=request_id,
            )
        else:
            target = await self._resolve_own_target(
                tenant_id=tenant_id,
                membership_id=membership_id,
                actor_user_id=actor_user_id,
                lock=True,
            )
            self._reject_selected_no_ops(target.personal, payload, selected_fields)
            active_request_id = await self.session.scalar(
                select(EmployeeProfileChangeRequest.id).where(
                    EmployeeProfileChangeRequest.tenant_id == tenant_id,
                    EmployeeProfileChangeRequest.employee_id == target.employee.id,
                    EmployeeProfileChangeRequest.status
                    == EmployeeProfileChangeRequestStatus.SUBMITTED.value,
                )
            )
            if active_request_id is not None:
                raise EmployeeProfileChangeRequestConflictError
            request = EmployeeProfileChangeRequest(
                id=request_id,
                tenant_id=tenant_id,
                employee_id=target.employee.id,
                requester_membership_id=membership_id,
                requester_user_id=actor_user_id,
                status=EmployeeProfileChangeRequestStatus.SUBMITTED.value,
                version=1,
                base_profile_version=target.personal.version,
                preferred_name_changed="preferred_name" in selected_fields,
                previous_preferred_name=(
                    target.personal.preferred_name if "preferred_name" in selected_fields else None
                ),
                proposed_preferred_name=(
                    payload.preferred_name if "preferred_name" in selected_fields else None
                ),
                phone_changed="phone" in selected_fields,
                previous_phone=(target.personal.phone if "phone" in selected_fields else None),
                proposed_phone=(payload.phone if "phone" in selected_fields else None),
                birth_date_changed="birth_date" in selected_fields,
                previous_birth_date=(
                    target.personal.birth_date if "birth_date" in selected_fields else None
                ),
                proposed_birth_date=(
                    payload.birth_date if "birth_date" in selected_fields else None
                ),
                submitted_at=self._now(),
            )
            self.session.add(request)
            await self.session.flush()
            await self.session.refresh(request)

        changed_fields = _changed_fields(request)
        return EmployeeProfileChangeRequestMutation(
            response=_own_read(request),
            request_id=request.id,
            employee_id=request.employee_id,
            changed_fields=changed_fields,
            before_status="none",
            after_status=EmployeeProfileChangeRequestStatus.SUBMITTED.value,
        )

    async def list_own(
        self,
        *,
        tenant_id: UUID,
        membership_id: UUID,
        actor_user_id: UUID,
        limit: int,
        cursor: str | None,
    ) -> CursorPage[OwnEmployeeProfileChangeRequestRead]:
        target = await self._resolve_own_target(
            tenant_id=tenant_id,
            membership_id=membership_id,
            actor_user_id=actor_user_id,
        )
        statement = select(EmployeeProfileChangeRequest).where(
            EmployeeProfileChangeRequest.tenant_id == tenant_id,
            EmployeeProfileChangeRequest.employee_id == target.employee.id,
            EmployeeProfileChangeRequest.requester_membership_id == membership_id,
            EmployeeProfileChangeRequest.requester_user_id == actor_user_id,
        )
        if cursor is not None:
            submitted_at, request_id = _decode_cursor(
                cursor,
                expected_resource=_OWN_CURSOR_RESOURCE,
            )
            statement = statement.where(
                or_(
                    EmployeeProfileChangeRequest.submitted_at < submitted_at,
                    and_(
                        EmployeeProfileChangeRequest.submitted_at == submitted_at,
                        EmployeeProfileChangeRequest.id < request_id,
                    ),
                )
            )
        rows = list(
            (
                await self.session.scalars(
                    statement.order_by(
                        EmployeeProfileChangeRequest.submitted_at.desc(),
                        EmployeeProfileChangeRequest.id.desc(),
                    ).limit(limit + 1)
                )
            ).all()
        )
        return _own_page(rows, limit=limit)

    async def get_own(
        self,
        *,
        tenant_id: UUID,
        membership_id: UUID,
        actor_user_id: UUID,
        request_id: UUID,
    ) -> OwnEmployeeProfileChangeRequestRead:
        target = await self._resolve_own_target(
            tenant_id=tenant_id,
            membership_id=membership_id,
            actor_user_id=actor_user_id,
        )
        request = await self._get_own_request_row(
            tenant_id=tenant_id,
            membership_id=membership_id,
            actor_user_id=actor_user_id,
            request_id=request_id,
            employee_id=target.employee.id,
        )
        return _own_read(request)

    async def cancel_own(
        self,
        *,
        tenant_id: UUID,
        membership_id: UUID,
        actor_user_id: UUID,
        request_id: UUID,
        payload: EmployeeProfileChangeRequestExpectedVersion,
    ) -> EmployeeProfileChangeRequestMutation:
        if self._is_postgresql:
            outcome = await self.session.scalar(
                select(
                    func.public.transition_employee_profile_change_request(
                        request_id,
                        payload.expected_version,
                        "cancel",
                        None,
                    )
                )
            )
            self._raise_transition_outcome(outcome)
            request = await self._get_own_request_row(
                tenant_id=tenant_id,
                membership_id=membership_id,
                actor_user_id=actor_user_id,
                request_id=request_id,
            )
        else:
            target = await self._resolve_own_target(
                tenant_id=tenant_id,
                membership_id=membership_id,
                actor_user_id=actor_user_id,
                lock=True,
            )
            request = await self._get_request_row(
                tenant_id=tenant_id,
                request_id=request_id,
                lock=True,
            )
            if (
                request.employee_id != target.employee.id
                or request.requester_membership_id != membership_id
                or request.requester_user_id != actor_user_id
            ):
                raise EmployeeProfileChangeRequestNotFoundError
            self._require_submitted_version(request, payload.expected_version)
            request.status = EmployeeProfileChangeRequestStatus.CANCELLED.value
            request.cancelled_at = self._now()
            await self.session.flush()
            await self.session.refresh(request)

        return EmployeeProfileChangeRequestMutation(
            response=_own_read(request),
            request_id=request.id,
            employee_id=request.employee_id,
            changed_fields=_changed_fields(request),
            before_status=EmployeeProfileChangeRequestStatus.SUBMITTED.value,
            after_status=EmployeeProfileChangeRequestStatus.CANCELLED.value,
        )

    async def list_hr(
        self,
        *,
        tenant_id: UUID,
        granted_permissions: Collection[str],
        status: EmployeeProfileChangeRequestStatus,
        limit: int,
        cursor: str | None,
    ) -> CursorPage[EmployeeProfileChangeRequestHrSummaryRead]:
        _require_hr_permissions(granted_permissions)
        statement = self._hr_rows_statement(tenant_id).where(
            EmployeeProfileChangeRequest.status == status.value
        )
        if cursor is not None:
            submitted_at, request_id = _decode_cursor(
                cursor,
                expected_resource=f"{_HR_CURSOR_RESOURCE}:{status.value}",
            )
            statement = statement.where(
                or_(
                    EmployeeProfileChangeRequest.submitted_at > submitted_at,
                    and_(
                        EmployeeProfileChangeRequest.submitted_at == submitted_at,
                        EmployeeProfileChangeRequest.id > request_id,
                    ),
                )
            )
        rows = list(
            (
                await self.session.execute(
                    statement.order_by(
                        EmployeeProfileChangeRequest.submitted_at,
                        EmployeeProfileChangeRequest.id,
                    ).limit(limit + 1)
                )
            ).all()
        )
        items = [
            _hr_summary(request, employee, profile) for request, employee, profile in rows[:limit]
        ]
        next_cursor = None
        if len(rows) > limit:
            request = rows[limit - 1][0]
            next_cursor = _encode_request_cursor(
                request,
                resource=f"{_HR_CURSOR_RESOURCE}:{status.value}",
            )
        return CursorPage(items=items, next_cursor=next_cursor)

    async def get_hr(
        self,
        *,
        tenant_id: UUID,
        granted_permissions: Collection[str],
        request_id: UUID,
    ) -> EmployeeProfileChangeRequestHrDetailRead:
        _require_hr_permissions(granted_permissions)
        request, employee, profile = await self._get_hr_row(tenant_id, request_id)
        return _hr_detail(request, employee, profile)

    async def approve(
        self,
        *,
        tenant_id: UUID,
        membership_id: UUID,
        actor_user_id: UUID,
        granted_permissions: Collection[str],
        request_id: UUID,
        payload: EmployeeProfileChangeRequestExpectedVersion,
    ) -> EmployeeProfileChangeRequestMutation:
        _require_hr_permissions(granted_permissions)
        if self._is_postgresql:
            outcome = await self.session.scalar(
                select(
                    func.public.transition_employee_profile_change_request(
                        request_id,
                        payload.expected_version,
                        "approve",
                        None,
                    )
                )
            )
            self._raise_transition_outcome(outcome)
        else:
            request = await self._get_request_row(
                tenant_id=tenant_id,
                request_id=request_id,
                lock=True,
            )
            self._require_submitted_version(request, payload.expected_version)
            profile = await self._get_personal_profile(
                tenant_id=tenant_id,
                employee_id=request.employee_id,
                lock=True,
            )
            if _profile_is_stale(request, profile):
                raise EmployeeProfileChangeRequestStaleProfileError
            if request.preferred_name_changed:
                profile.preferred_name = request.proposed_preferred_name
            if request.phone_changed:
                profile.phone = request.proposed_phone
            if request.birth_date_changed:
                profile.birth_date = request.proposed_birth_date
            profile.version += 1
            request.status = EmployeeProfileChangeRequestStatus.APPROVED.value
            request.decided_at = self._now()
            request.decided_by_membership_id = membership_id
            request.decided_by_user_id = actor_user_id
            await self.session.flush()

        request, employee, profile = await self._get_hr_row(tenant_id, request_id)
        return EmployeeProfileChangeRequestMutation(
            response=_hr_detail(request, employee, profile),
            request_id=request.id,
            employee_id=request.employee_id,
            changed_fields=_changed_fields(request),
            before_status=EmployeeProfileChangeRequestStatus.SUBMITTED.value,
            after_status=EmployeeProfileChangeRequestStatus.APPROVED.value,
        )

    async def reject(
        self,
        *,
        tenant_id: UUID,
        membership_id: UUID,
        actor_user_id: UUID,
        granted_permissions: Collection[str],
        request_id: UUID,
        payload: EmployeeProfileChangeRequestReject,
    ) -> EmployeeProfileChangeRequestMutation:
        _require_hr_permissions(granted_permissions)
        if self._is_postgresql:
            outcome = await self.session.scalar(
                select(
                    func.public.transition_employee_profile_change_request(
                        request_id,
                        payload.expected_version,
                        "reject",
                        payload.reason,
                    )
                )
            )
            self._raise_transition_outcome(outcome)
        else:
            request = await self._get_request_row(
                tenant_id=tenant_id,
                request_id=request_id,
                lock=True,
            )
            self._require_submitted_version(request, payload.expected_version)
            request.status = EmployeeProfileChangeRequestStatus.REJECTED.value
            request.decided_at = self._now()
            request.decided_by_membership_id = membership_id
            request.decided_by_user_id = actor_user_id
            request.rejection_reason = payload.reason
            await self.session.flush()

        request, employee, profile = await self._get_hr_row(tenant_id, request_id)
        return EmployeeProfileChangeRequestMutation(
            response=_hr_detail(request, employee, profile),
            request_id=request.id,
            employee_id=request.employee_id,
            changed_fields=_changed_fields(request),
            before_status=EmployeeProfileChangeRequestStatus.SUBMITTED.value,
            after_status=EmployeeProfileChangeRequestStatus.REJECTED.value,
        )

    async def _resolve_own_target(
        self,
        *,
        tenant_id: UUID,
        membership_id: UUID,
        actor_user_id: UUID,
        lock: bool = False,
    ) -> _OwnTarget:
        statement = (
            select(Employee, EmployeePersonalProfile)
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
            .where(
                Employee.tenant_id == tenant_id,
                Employee.archived_at.is_(None),
                EmployeeAccountLink.membership_id == membership_id,
                TenantMembership.legacy_user_id == actor_user_id,
                User.id == actor_user_id,
                TenantMembership.status == MembershipStatus.ACTIVE.value,
                User.status == UserStatus.ACTIVE.value,
                TenantMembership.permission_version == User.permission_version,
            )
        )
        if self._is_postgresql:
            statement = statement.where(
                func.public.is_current_tenant_membership_link_eligible(TenantMembership.id).is_(
                    True
                )
            )
        else:
            statement = statement.join(
                Identity,
                Identity.id == TenantMembership.identity_id,
            ).where(Identity.status == IdentityStatus.ACTIVE.value)
        if lock:
            statement = statement.with_for_update(of=EmployeePersonalProfile)
        row = (await self.session.execute(statement)).one_or_none()
        if row is None:
            raise EmployeeProfileChangeRequestConflictError
        employee, personal = row
        return _OwnTarget(employee=employee, personal=personal)

    async def _get_own_request_row(
        self,
        *,
        tenant_id: UUID,
        membership_id: UUID,
        actor_user_id: UUID,
        request_id: UUID,
        employee_id: UUID | None = None,
    ) -> EmployeeProfileChangeRequest:
        statement = select(EmployeeProfileChangeRequest).where(
            EmployeeProfileChangeRequest.tenant_id == tenant_id,
            EmployeeProfileChangeRequest.id == request_id,
            EmployeeProfileChangeRequest.requester_membership_id == membership_id,
            EmployeeProfileChangeRequest.requester_user_id == actor_user_id,
        )
        if employee_id is not None:
            statement = statement.where(EmployeeProfileChangeRequest.employee_id == employee_id)
        request = await self.session.scalar(statement)
        if request is None:
            raise EmployeeProfileChangeRequestNotFoundError
        return request

    async def _get_request_row(
        self,
        *,
        tenant_id: UUID,
        request_id: UUID,
        lock: bool,
    ) -> EmployeeProfileChangeRequest:
        statement = select(EmployeeProfileChangeRequest).where(
            EmployeeProfileChangeRequest.tenant_id == tenant_id,
            EmployeeProfileChangeRequest.id == request_id,
        )
        if lock:
            statement = statement.with_for_update(of=EmployeeProfileChangeRequest)
        request = await self.session.scalar(statement)
        if request is None:
            raise EmployeeProfileChangeRequestNotFoundError
        return request

    async def _get_personal_profile(
        self,
        *,
        tenant_id: UUID,
        employee_id: UUID,
        lock: bool,
    ) -> EmployeePersonalProfile:
        statement = select(EmployeePersonalProfile).where(
            EmployeePersonalProfile.tenant_id == tenant_id,
            EmployeePersonalProfile.employee_id == employee_id,
        )
        if lock:
            statement = statement.with_for_update(of=EmployeePersonalProfile)
        profile = await self.session.scalar(statement)
        if profile is None:
            raise EmployeeProfileChangeRequestNotFoundError
        return profile

    def _hr_rows_statement(self, tenant_id: UUID):
        return (
            select(EmployeeProfileChangeRequest, Employee, EmployeePersonalProfile)
            .join(
                Employee,
                and_(
                    Employee.tenant_id == EmployeeProfileChangeRequest.tenant_id,
                    Employee.id == EmployeeProfileChangeRequest.employee_id,
                ),
            )
            .join(
                EmployeePersonalProfile,
                and_(
                    EmployeePersonalProfile.tenant_id == EmployeeProfileChangeRequest.tenant_id,
                    EmployeePersonalProfile.employee_id == EmployeeProfileChangeRequest.employee_id,
                ),
            )
            .where(EmployeeProfileChangeRequest.tenant_id == tenant_id)
        )

    async def _get_hr_row(
        self,
        tenant_id: UUID,
        request_id: UUID,
    ) -> tuple[EmployeeProfileChangeRequest, Employee, EmployeePersonalProfile]:
        row = (
            await self.session.execute(
                self._hr_rows_statement(tenant_id).where(
                    EmployeeProfileChangeRequest.id == request_id
                )
            )
        ).one_or_none()
        if row is None:
            raise EmployeeProfileChangeRequestNotFoundError
        request, employee, profile = row
        return request, employee, profile

    @staticmethod
    def _require_requestable_fields(
        selected_fields: tuple[EmployeeProfileChangeFieldName, ...],
    ) -> None:
        if not selected_fields or not set(selected_fields) <= PROFILE_CHANGE_REQUESTABLE_FIELDS:
            raise EmployeeProfileChangeRequestInvalidError

    @staticmethod
    def _reject_selected_no_ops(
        profile: EmployeePersonalProfile,
        payload: EmployeeProfileChangeRequestCreate,
        selected_fields: tuple[EmployeeProfileChangeFieldName, ...],
    ) -> None:
        for field_name in selected_fields:
            current_value: object = getattr(profile, field_name)
            proposed_value: object = getattr(payload, field_name)
            if field_name == "phone":
                current_value = normalized_existing_phone(cast(str | None, current_value))
            elif field_name == "preferred_name" and current_value is not None:
                current_value = " ".join(cast(str, current_value).split())
            if current_value == proposed_value:
                raise EmployeeProfileChangeRequestInvalidError

    @staticmethod
    def _require_submitted_version(
        request: EmployeeProfileChangeRequest,
        expected_version: int,
    ) -> None:
        if (
            request.status != EmployeeProfileChangeRequestStatus.SUBMITTED.value
            or request.version != expected_version
        ):
            raise EmployeeProfileChangeRequestConflictError

    @staticmethod
    def _raise_submit_outcome(outcome: object) -> None:
        if outcome == "submitted":
            return
        if outcome == "invalid_request":
            raise EmployeeProfileChangeRequestInvalidError
        if outcome in {"active_request_exists", "context_invalid", "profile_unavailable"}:
            raise EmployeeProfileChangeRequestConflictError
        raise RuntimeError("Profile-change submit returned an unknown safe outcome")

    @staticmethod
    def _raise_transition_outcome(outcome: object) -> None:
        if outcome in {"approved", "rejected", "cancelled"}:
            return
        if outcome in {"not_found", "access_denied", "context_invalid"}:
            raise EmployeeProfileChangeRequestNotFoundError
        if outcome == "profile_conflict":
            raise EmployeeProfileChangeRequestStaleProfileError
        if outcome == "version_conflict":
            raise EmployeeProfileChangeRequestConflictError
        if outcome == "invalid_request":
            raise EmployeeProfileChangeRequestInvalidError
        raise RuntimeError("Profile-change transition returned an unknown safe outcome")

    def _now(self) -> datetime:
        value = self._now_factory()
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Profile-change clock must return an aware datetime")
        return value

    @property
    def _is_postgresql(self) -> bool:
        return self.session.get_bind().dialect.name == "postgresql"


def _require_hr_permissions(granted_permissions: Collection[str]) -> None:
    can_read = _POLICY.allows(EMPLOYEE_READ_TENANT_PERMISSION, granted_permissions)
    can_update = _POLICY.allows(EMPLOYEE_UPDATE_TENANT_PERMISSION, granted_permissions)
    if not can_read or not can_update:
        # The API edge maps this established authorization error without exposing which grant is
        # absent. Importing lazily avoids coupling the domain module to the API dependency graph.
        from app.services.authorization_service import AuthorizationAccessDeniedError

        raise AuthorizationAccessDeniedError


def _changed_fields(
    request: EmployeeProfileChangeRequest,
) -> tuple[EmployeeProfileChangeFieldName, ...]:
    return tuple(
        field_name
        for field_name in _FIELD_ORDER
        if cast(bool, getattr(request, f"{field_name}_changed"))
    )


def _own_read(request: EmployeeProfileChangeRequest) -> OwnEmployeeProfileChangeRequestRead:
    scope = EmployeeProjectionScope.EMPLOYEE_OWN
    return OwnEmployeeProfileChangeRequestRead(
        **_common_values(request),
        employee_id=cast(UUID, project_field(scope, "employee.id", request.employee_id)),
        changes=OwnEmployeeProfileChangesRead(
            preferred_name=(
                OwnPreferredNameChangeRead(
                    previous_value=cast(
                        str | None,
                        project_field(
                            scope,
                            "personal.preferred_name",
                            request.previous_preferred_name,
                        ),
                    ),
                    proposed_value=cast(
                        str | None,
                        project_field(
                            scope,
                            "personal.preferred_name",
                            request.proposed_preferred_name,
                        ),
                    ),
                )
                if request.preferred_name_changed
                else None
            ),
            phone=(
                OwnMaskedProfileChangeRead(
                    previous_value=cast(
                        OwnMaskedFieldRead,
                        project_field(scope, "personal.phone", request.previous_phone),
                    ),
                    proposed_value=cast(
                        OwnMaskedFieldRead,
                        project_field(scope, "personal.phone", request.proposed_phone),
                    ),
                )
                if request.phone_changed
                else None
            ),
            birth_date=(
                OwnMaskedProfileChangeRead(
                    previous_value=cast(
                        OwnMaskedFieldRead,
                        project_field(
                            scope,
                            "personal.birth_date",
                            request.previous_birth_date,
                        ),
                    ),
                    proposed_value=cast(
                        OwnMaskedFieldRead,
                        project_field(
                            scope,
                            "personal.birth_date",
                            request.proposed_birth_date,
                        ),
                    ),
                )
                if request.birth_date_changed
                else None
            ),
        ),
    )


def _hr_summary(
    request: EmployeeProfileChangeRequest,
    employee: Employee,
    profile: EmployeePersonalProfile,
) -> EmployeeProfileChangeRequestHrSummaryRead:
    return EmployeeProfileChangeRequestHrSummaryRead(
        **_common_values(request),
        employee=EmployeeProfileChangeRequestEmployeeRead(
            id=_hr_project("employee.id", employee.id),
            employee_number=_hr_project("employee.employee_number", employee.employee_number),
            first_name=_hr_project("employee.first_name", employee.first_name),
            last_name=_hr_project("employee.last_name", employee.last_name),
            email=_hr_project("employee.email", employee.email),
            status=_hr_project("employee.status", employee.status),
        ),
        base_profile_version=_hr_project("personal.version", request.base_profile_version),
        current_profile_version=_hr_project("personal.version", profile.version),
        profile_is_stale=(
            request.status == EmployeeProfileChangeRequestStatus.SUBMITTED.value
            and _profile_is_stale(request, profile)
        ),
    )


def _hr_detail(
    request: EmployeeProfileChangeRequest,
    employee: Employee,
    profile: EmployeePersonalProfile,
) -> EmployeeProfileChangeRequestHrDetailRead:
    summary = _hr_summary(request, employee, profile)
    return EmployeeProfileChangeRequestHrDetailRead(
        **_common_values(request),
        employee=summary.employee,
        base_profile_version=summary.base_profile_version,
        current_profile_version=summary.current_profile_version,
        profile_is_stale=summary.profile_is_stale,
        changes=HrEmployeeProfileChangesRead(
            preferred_name=(
                HrPreferredNameChangeRead(
                    base_value=_hr_project(
                        "personal.preferred_name", request.previous_preferred_name
                    ),
                    current_value=_hr_project("personal.preferred_name", profile.preferred_name),
                    proposed_value=_hr_project(
                        "personal.preferred_name", request.proposed_preferred_name
                    ),
                    current_matches_base=(
                        profile.preferred_name == request.previous_preferred_name
                    ),
                )
                if request.preferred_name_changed
                else None
            ),
            phone=(
                HrPhoneChangeRead(
                    base_value=_hr_project("personal.phone", request.previous_phone),
                    current_value=_hr_project("personal.phone", profile.phone),
                    proposed_value=_hr_project("personal.phone", request.proposed_phone),
                    current_matches_base=profile.phone == request.previous_phone,
                )
                if request.phone_changed
                else None
            ),
            birth_date=(
                HrBirthDateChangeRead(
                    base_value=_hr_project("personal.birth_date", request.previous_birth_date),
                    current_value=_hr_project("personal.birth_date", profile.birth_date),
                    proposed_value=_hr_project("personal.birth_date", request.proposed_birth_date),
                    current_matches_base=(profile.birth_date == request.previous_birth_date),
                )
                if request.birth_date_changed
                else None
            ),
        ),
    )


def _hr_project[ValueT](field_name: str, value: ValueT) -> ValueT:
    """Keep every HR-visible employee value behind P4D's deny-by-default registry."""

    return cast(
        ValueT,
        project_field(EmployeeProjectionScope.HR_TENANT, field_name, value),
    )


def _common_values(request: EmployeeProfileChangeRequest) -> dict[str, object]:
    return {
        "id": request.id,
        "status": request.status,
        "version": request.version,
        "submitted_at": _as_aware(request.submitted_at),
        "decided_at": _as_aware(request.decided_at),
        "cancelled_at": _as_aware(request.cancelled_at),
        "rejection_reason": request.rejection_reason,
        "changed_fields": _changed_fields(request),
    }


def _as_aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=UTC)
    return value


def _profile_is_stale(
    request: EmployeeProfileChangeRequest,
    profile: EmployeePersonalProfile,
) -> bool:
    return (
        profile.version != request.base_profile_version
        or (
            request.preferred_name_changed
            and profile.preferred_name != request.previous_preferred_name
        )
        or (request.phone_changed and profile.phone != request.previous_phone)
        or (request.birth_date_changed and profile.birth_date != request.previous_birth_date)
    )


def _own_page(
    rows: list[EmployeeProfileChangeRequest],
    *,
    limit: int,
) -> CursorPage[OwnEmployeeProfileChangeRequestRead]:
    items = [_own_read(request) for request in rows[:limit]]
    next_cursor = None
    if len(rows) > limit:
        next_cursor = _encode_request_cursor(rows[limit - 1], resource=_OWN_CURSOR_RESOURCE)
    return CursorPage(items=items, next_cursor=next_cursor)


def _encode_request_cursor(
    request: EmployeeProfileChangeRequest,
    *,
    resource: str,
) -> str:
    submitted_at = request.submitted_at
    if submitted_at.tzinfo is None or submitted_at.utcoffset() is None:
        submitted_at = submitted_at.replace(tzinfo=UTC)
    return encode_cursor(
        resource,
        {
            "submitted_at": submitted_at.isoformat(),
            "id": str(request.id),
        },
    )


def _decode_cursor(
    cursor: str,
    *,
    expected_resource: str,
) -> tuple[datetime, UUID]:
    try:
        values = decode_cursor(cursor, expected_resource=expected_resource)
        if set(values) != {"submitted_at", "id"}:
            raise InvalidCursorError
        submitted_at = datetime.fromisoformat(values["submitted_at"])
        if submitted_at.tzinfo is None or submitted_at.utcoffset() is None:
            raise ValueError
        request_id = UUID(values["id"])
        if request_id.int == 0:
            raise ValueError
        return submitted_at, request_id
    except (InvalidCursorError, KeyError, ValueError) as exc:
        raise EmployeeProfileChangeRequestInvalidError from exc


__all__ = [
    "ACTIVE_PROFILE_CHANGE_REQUEST_CONSTRAINT",
    "EMPLOYEE_READ_TENANT_PERMISSION",
    "EMPLOYEE_UPDATE_TENANT_PERMISSION",
    "EmployeeProfileChangeRequestConflictError",
    "EmployeeProfileChangeRequestInvalidError",
    "EmployeeProfileChangeRequestMutation",
    "EmployeeProfileChangeRequestNotFoundError",
    "EmployeeProfileChangeRequestService",
    "EmployeeProfileChangeRequestStaleProfileError",
]
