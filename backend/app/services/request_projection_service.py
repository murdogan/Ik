"""Bounded fixed read model across existing request domains."""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import and_, exists, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document_request import (
    EmployeeDocumentRequest,
    EmployeeDocumentRequestTimeline,
)
from app.models.employee import Employee
from app.models.employee_account_link import EmployeeAccountLink
from app.models.employee_assignment import EmployeeAssignment
from app.models.employee_profile_change_request import EmployeeProfileChangeRequest
from app.models.leave import LeaveRequestTimeline, LeaveType
from app.models.leave_request import LeaveRequest
from app.modules.core.domain.feature_flags import FeatureFlagKey
from app.platform.pagination import CursorPage, InvalidCursorError, decode_cursor, encode_cursor
from app.schemas.request_projection import (
    UnifiedRequestKind,
    UnifiedRequestRead,
    UnifiedRequestTimelineRead,
)
from app.services.phase7_access import (
    Phase7AccessDeniedError,
    Phase7ConflictError,
    Phase7NotFoundError,
    Phase7ValidationError,
    require_phase7_feature,
)

_CURSOR_RESOURCE = "unified_requests_v1"
_TIMELINE_LIMIT = 50


class RequestProjectionService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_page(
        self,
        *,
        tenant_id: UUID,
        actor_id: UUID,
        membership_id: UUID,
        permissions: tuple[str, ...],
        limit: int,
        cursor: str | None,
        kind: UnifiedRequestKind | None,
        status: str | None,
    ) -> CursorPage[UnifiedRequestRead]:
        await require_phase7_feature(
            self.session, tenant_id=tenant_id, feature=FeatureFlagKey.SELF_SERVICE
        )
        _require_projection_permission(permissions)
        cursor_value = _decode_cursor(cursor, kind=kind, status=status)
        own_employee_id = await self._own_employee_id(tenant_id, membership_id)
        rows: list[tuple[tuple[datetime, str, UUID], UnifiedRequestRead]] = []
        requested_kinds = (kind,) if kind is not None else tuple(UnifiedRequestKind)
        if UnifiedRequestKind.LEAVE in requested_kinds:
            rows.extend(
                await self._leave_rows(
                    tenant_id=tenant_id,
                    actor_id=actor_id,
                    own_employee_id=own_employee_id,
                    permissions=permissions,
                    limit=limit + 1,
                    cursor=cursor_value,
                    status=status,
                )
            )
        if UnifiedRequestKind.PROFILE_CHANGE in requested_kinds:
            rows.extend(
                await self._profile_rows(
                    tenant_id=tenant_id,
                    actor_id=actor_id,
                    permissions=permissions,
                    limit=limit + 1,
                    cursor=cursor_value,
                    status=status,
                )
            )
        if UnifiedRequestKind.DOCUMENT in requested_kinds:
            rows.extend(
                await self._document_rows(
                    tenant_id=tenant_id,
                    actor_id=actor_id,
                    permissions=permissions,
                    limit=limit + 1,
                    cursor=cursor_value,
                    status=status,
                )
            )
        rows.sort(key=lambda item: item[0], reverse=True)
        page_rows = rows[:limit]
        next_cursor = None
        if len(rows) > limit:
            timestamp, row_kind, row_id = page_rows[-1][0]
            next_cursor = encode_cursor(
                _CURSOR_RESOURCE,
                {
                    "submitted_at": timestamp.isoformat(),
                    "kind_key": row_kind,
                    "id": str(row_id),
                    "kind": kind.value if kind is not None else "",
                    "status": status or "",
                },
            )
        return CursorPage(items=[item for _, item in page_rows], next_cursor=next_cursor)

    async def get(
        self,
        *,
        tenant_id: UUID,
        actor_id: UUID,
        membership_id: UUID,
        permissions: tuple[str, ...],
        request_id: UUID,
    ) -> UnifiedRequestRead:
        await require_phase7_feature(
            self.session, tenant_id=tenant_id, feature=FeatureFlagKey.SELF_SERVICE
        )
        _require_projection_permission(permissions)
        own_employee_id = await self._own_employee_id(tenant_id, membership_id)
        candidates: list[UnifiedRequestRead] = []

        leave_statement = self._leave_statement(tenant_id).where(LeaveRequest.id == request_id)
        leave_scope = _leave_visibility(
            tenant_id=tenant_id,
            actor_id=actor_id,
            own_employee_id=own_employee_id,
            permissions=permissions,
        )
        if leave_scope is not None:
            leave_row = (
                await self.session.execute(leave_statement.where(leave_scope).limit(1))
            ).one_or_none()
            if leave_row is not None:
                request, employee, leave_type = leave_row
                item = _leave_read(request, employee, leave_type)
                item.timeline = await self._leave_timeline(tenant_id, request.id)
                candidates.append(item)

        profile_scope = _hr_or_own_visibility(
            actor_id=actor_id,
            requester_column=EmployeeProfileChangeRequest.requester_user_id,
            permissions=permissions,
        )
        if profile_scope is not None:
            profile_row = (
                await self.session.execute(
                    self._profile_statement(tenant_id)
                    .where(EmployeeProfileChangeRequest.id == request_id, profile_scope)
                    .limit(1)
                )
            ).one_or_none()
            if profile_row is not None:
                profile, employee = profile_row
                item = _profile_read(profile, employee)
                item.timeline = _profile_timeline(profile)
                candidates.append(item)

        document_scope = _hr_or_own_visibility(
            actor_id=actor_id,
            requester_column=EmployeeDocumentRequest.requester_user_id,
            permissions=permissions,
        )
        if document_scope is not None:
            document_row = (
                await self.session.execute(
                    self._document_statement(tenant_id)
                    .where(EmployeeDocumentRequest.id == request_id, document_scope)
                    .limit(1)
                )
            ).one_or_none()
            if document_row is not None:
                document, employee = document_row
                item = _document_read(document, employee)
                item.timeline = await self._document_timeline(tenant_id, document.id)
                candidates.append(item)

        if not candidates:
            raise Phase7NotFoundError
        if len(candidates) > 1:
            raise Phase7ConflictError
        return candidates[0]

    async def _leave_rows(
        self,
        *,
        tenant_id: UUID,
        actor_id: UUID,
        own_employee_id: UUID | None,
        permissions: tuple[str, ...],
        limit: int,
        cursor: tuple[datetime, str, UUID] | None,
        status: str | None,
    ) -> list[tuple[tuple[datetime, str, UUID], UnifiedRequestRead]]:
        visibility = _leave_visibility(
            tenant_id=tenant_id,
            actor_id=actor_id,
            own_employee_id=own_employee_id,
            permissions=permissions,
        )
        if visibility is None:
            return []
        statement = self._leave_statement(tenant_id).where(visibility)
        if status is not None:
            statement = statement.where(LeaveRequest.status == status)
        statement = _apply_kind_cursor(
            statement,
            timestamp_column=LeaveRequest.created_at,
            id_column=LeaveRequest.id,
            kind=UnifiedRequestKind.LEAVE,
            cursor=cursor,
        )
        records = (
            await self.session.execute(
                statement.order_by(LeaveRequest.created_at.desc(), LeaveRequest.id.desc()).limit(
                    limit
                )
            )
        ).all()
        return [
            (
                (_aware(request.created_at), UnifiedRequestKind.LEAVE.value, request.id),
                _leave_read(request, employee, leave_type),
            )
            for request, employee, leave_type in records
        ]

    async def _profile_rows(
        self,
        *,
        tenant_id: UUID,
        actor_id: UUID,
        permissions: tuple[str, ...],
        limit: int,
        cursor: tuple[datetime, str, UUID] | None,
        status: str | None,
    ) -> list[tuple[tuple[datetime, str, UUID], UnifiedRequestRead]]:
        visibility = _hr_or_own_visibility(
            actor_id=actor_id,
            requester_column=EmployeeProfileChangeRequest.requester_user_id,
            permissions=permissions,
        )
        if visibility is None:
            return []
        statement = self._profile_statement(tenant_id).where(visibility)
        if status is not None:
            statement = statement.where(EmployeeProfileChangeRequest.status == status)
        statement = _apply_kind_cursor(
            statement,
            timestamp_column=EmployeeProfileChangeRequest.submitted_at,
            id_column=EmployeeProfileChangeRequest.id,
            kind=UnifiedRequestKind.PROFILE_CHANGE,
            cursor=cursor,
        )
        records = (
            await self.session.execute(
                statement.order_by(
                    EmployeeProfileChangeRequest.submitted_at.desc(),
                    EmployeeProfileChangeRequest.id.desc(),
                ).limit(limit)
            )
        ).all()
        return [
            (
                (
                    _aware(request.submitted_at),
                    UnifiedRequestKind.PROFILE_CHANGE.value,
                    request.id,
                ),
                _profile_read(request, employee),
            )
            for request, employee in records
        ]

    async def _document_rows(
        self,
        *,
        tenant_id: UUID,
        actor_id: UUID,
        permissions: tuple[str, ...],
        limit: int,
        cursor: tuple[datetime, str, UUID] | None,
        status: str | None,
    ) -> list[tuple[tuple[datetime, str, UUID], UnifiedRequestRead]]:
        visibility = _hr_or_own_visibility(
            actor_id=actor_id,
            requester_column=EmployeeDocumentRequest.requester_user_id,
            permissions=permissions,
        )
        if visibility is None:
            return []
        statement = self._document_statement(tenant_id).where(visibility)
        if status is not None:
            statement = statement.where(EmployeeDocumentRequest.status == status)
        statement = _apply_kind_cursor(
            statement,
            timestamp_column=EmployeeDocumentRequest.created_at,
            id_column=EmployeeDocumentRequest.id,
            kind=UnifiedRequestKind.DOCUMENT,
            cursor=cursor,
        )
        records = (
            await self.session.execute(
                statement.order_by(
                    EmployeeDocumentRequest.created_at.desc(),
                    EmployeeDocumentRequest.id.desc(),
                ).limit(limit)
            )
        ).all()
        return [
            (
                (
                    _aware(request.created_at),
                    UnifiedRequestKind.DOCUMENT.value,
                    request.id,
                ),
                _document_read(request, employee),
            )
            for request, employee in records
        ]

    @staticmethod
    def _leave_statement(tenant_id: UUID):
        return (
            select(LeaveRequest, Employee, LeaveType)
            .join(
                Employee,
                and_(
                    Employee.tenant_id == LeaveRequest.tenant_id,
                    Employee.id == LeaveRequest.employee_id,
                ),
            )
            .join(
                LeaveType,
                and_(
                    LeaveType.tenant_id == LeaveRequest.tenant_id,
                    LeaveType.id == LeaveRequest.leave_type_id,
                ),
            )
            .where(LeaveRequest.tenant_id == tenant_id)
        )

    @staticmethod
    def _profile_statement(tenant_id: UUID):
        return (
            select(EmployeeProfileChangeRequest, Employee)
            .join(
                Employee,
                and_(
                    Employee.tenant_id == EmployeeProfileChangeRequest.tenant_id,
                    Employee.id == EmployeeProfileChangeRequest.employee_id,
                ),
            )
            .where(EmployeeProfileChangeRequest.tenant_id == tenant_id)
        )

    @staticmethod
    def _document_statement(tenant_id: UUID):
        return (
            select(EmployeeDocumentRequest, Employee)
            .join(
                Employee,
                and_(
                    Employee.tenant_id == EmployeeDocumentRequest.tenant_id,
                    Employee.id == EmployeeDocumentRequest.employee_id,
                ),
            )
            .where(EmployeeDocumentRequest.tenant_id == tenant_id)
        )

    async def _own_employee_id(self, tenant_id: UUID, membership_id: UUID) -> UUID | None:
        return await self.session.scalar(
            select(EmployeeAccountLink.employee_id).where(
                EmployeeAccountLink.tenant_id == tenant_id,
                EmployeeAccountLink.membership_id == membership_id,
            )
        )

    async def _leave_timeline(
        self, tenant_id: UUID, request_id: UUID
    ) -> list[UnifiedRequestTimelineRead]:
        records = tuple(
            await self.session.scalars(
                select(LeaveRequestTimeline)
                .where(
                    LeaveRequestTimeline.tenant_id == tenant_id,
                    LeaveRequestTimeline.request_id == request_id,
                )
                .order_by(LeaveRequestTimeline.occurred_at, LeaveRequestTimeline.id)
                .limit(_TIMELINE_LIMIT)
            )
        )
        return [
            UnifiedRequestTimelineRead(
                event_type=record.event_type,
                status=record.status,
                occurred_at=_aware(record.occurred_at),
            )
            for record in records
        ]

    async def _document_timeline(
        self, tenant_id: UUID, request_id: UUID
    ) -> list[UnifiedRequestTimelineRead]:
        records = tuple(
            await self.session.scalars(
                select(EmployeeDocumentRequestTimeline)
                .where(
                    EmployeeDocumentRequestTimeline.tenant_id == tenant_id,
                    EmployeeDocumentRequestTimeline.request_id == request_id,
                )
                .order_by(
                    EmployeeDocumentRequestTimeline.occurred_at,
                    EmployeeDocumentRequestTimeline.id,
                )
                .limit(_TIMELINE_LIMIT)
            )
        )
        return [
            UnifiedRequestTimelineRead(
                event_type=record.event_type,
                status=record.status,
                occurred_at=_aware(record.occurred_at),
            )
            for record in records
        ]


def _leave_visibility(
    *,
    tenant_id: UUID,
    actor_id: UUID,
    own_employee_id: UUID | None,
    permissions: tuple[str, ...],
):
    conditions = []
    if "request:read:tenant" in permissions and "leave:read:tenant" in permissions:
        conditions.append(LeaveRequest.tenant_id == tenant_id)
    if (
        "request:read:team" in permissions
        and "leave:read:team" in permissions
    ):
        conditions.append(
            exists(
                select(EmployeeAssignment.id).where(
                    EmployeeAssignment.tenant_id == tenant_id,
                    EmployeeAssignment.employee_id == LeaveRequest.employee_id,
                    EmployeeAssignment.manager_user_id == actor_id,
                    EmployeeAssignment.effective_from <= date.today(),
                    or_(
                        EmployeeAssignment.effective_to.is_(None),
                        EmployeeAssignment.effective_to > date.today(),
                    ),
                )
            )
        )
    if (
        own_employee_id is not None
        and "request:read:own" in permissions
        and "leave:read:own" in permissions
    ):
        conditions.append(LeaveRequest.employee_id == own_employee_id)
    return or_(*conditions) if conditions else None


def _hr_or_own_visibility(*, actor_id: UUID, requester_column, permissions: tuple[str, ...]):
    conditions = []
    if "request:read:tenant" in permissions:
        conditions.append(True)
    if "request:read:own" in permissions:
        conditions.append(requester_column == actor_id)
    return or_(*conditions) if conditions else None


def _apply_kind_cursor(statement, *, timestamp_column, id_column, kind, cursor):
    if cursor is None:
        return statement
    timestamp, cursor_kind, cursor_id = cursor
    if kind.value < cursor_kind:
        return statement.where(timestamp_column <= timestamp)
    if kind.value == cursor_kind:
        return statement.where(
            or_(
                timestamp_column < timestamp,
                and_(timestamp_column == timestamp, id_column < cursor_id),
            )
        )
    return statement.where(timestamp_column < timestamp)


def _leave_read(request: LeaveRequest, employee: Employee, leave_type: LeaveType):
    return UnifiedRequestRead(
        id=request.id,
        kind=UnifiedRequestKind.LEAVE,
        status=request.status,
        title=f"{leave_type.name} leave request",
        requester_employee_id=employee.id,
        requester_name=_employee_name(employee),
        submitted_at=_aware(request.created_at),
        updated_at=_aware(request.updated_at),
        version=request.version,
        start_date=request.start_date,
        end_date=request.end_date,
        counted_days=Decimal(request.counted_days),
    )


def _profile_read(request: EmployeeProfileChangeRequest, employee: Employee):
    changed_fields = tuple(
        field_name
        for field_name, changed in (
            ("preferred_name", request.preferred_name_changed),
            ("phone", request.phone_changed),
            ("birth_date", request.birth_date_changed),
        )
        if changed
    )
    return UnifiedRequestRead(
        id=request.id,
        kind=UnifiedRequestKind.PROFILE_CHANGE,
        status=request.status,
        title="Personal profile change request",
        requester_employee_id=employee.id,
        requester_name=_employee_name(employee),
        submitted_at=_aware(request.submitted_at),
        updated_at=_aware(request.updated_at),
        version=request.version,
        changed_fields=changed_fields,
    )


def _document_read(request: EmployeeDocumentRequest, employee: Employee):
    return UnifiedRequestRead(
        id=request.id,
        kind=UnifiedRequestKind.DOCUMENT,
        status=request.status,
        title="HR document request",
        requester_employee_id=employee.id,
        requester_name=_employee_name(employee),
        submitted_at=_aware(request.created_at),
        updated_at=_aware(request.updated_at),
        version=request.version,
        document_request_type=request.request_type,
    )


def _profile_timeline(
    request: EmployeeProfileChangeRequest,
) -> list[UnifiedRequestTimelineRead]:
    timeline = [
        UnifiedRequestTimelineRead(
            event_type="submitted",
            status="submitted",
            occurred_at=_aware(request.submitted_at),
        )
    ]
    terminal_at = request.decided_at or request.cancelled_at
    if request.status != "submitted" and terminal_at is not None:
        timeline.append(
            UnifiedRequestTimelineRead(
                event_type=request.status,
                status=request.status,
                occurred_at=_aware(terminal_at),
            )
        )
    return timeline


def _decode_cursor(
    token: str | None,
    *,
    kind: UnifiedRequestKind | None,
    status: str | None,
) -> tuple[datetime, str, UUID] | None:
    if token is None:
        return None
    try:
        values = decode_cursor(token, expected_resource=_CURSOR_RESOURCE)
        if set(values) != {"submitted_at", "kind_key", "id", "kind", "status"}:
            raise InvalidCursorError
        if values["kind"] != (kind.value if kind is not None else ""):
            raise InvalidCursorError
        if values["status"] != (status or ""):
            raise InvalidCursorError
        if values["kind_key"] not in {item.value for item in UnifiedRequestKind}:
            raise InvalidCursorError
        timestamp = datetime.fromisoformat(values["submitted_at"])
        if timestamp.tzinfo is None or timestamp.utcoffset() is None:
            raise InvalidCursorError
        return timestamp, values["kind_key"], UUID(values["id"])
    except (InvalidCursorError, ValueError) as exc:
        raise Phase7ValidationError("The request cursor is invalid") from exc


def _require_projection_permission(permissions: tuple[str, ...]) -> None:
    if not any(
        permission in permissions
        for permission in ("request:read:own", "request:read:team", "request:read:tenant")
    ):
        raise Phase7AccessDeniedError


def _employee_name(employee: Employee) -> str:
    return f"{employee.first_name} {employee.last_name}".strip()


def _aware(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


__all__ = ["RequestProjectionService"]
