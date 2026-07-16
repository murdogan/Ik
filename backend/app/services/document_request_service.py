"""Atomic employee-to-HR document request commands and bounded projections."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document_request import (
    EmployeeDocumentRequest,
    EmployeeDocumentRequestStatus,
    EmployeeDocumentRequestTimeline,
)
from app.models.employee import Employee
from app.models.employee_account_link import EmployeeAccountLink
from app.modules.core.domain.feature_flags import FeatureFlagKey
from app.platform.audit import (
    AuditActorType,
    AuditCategory,
    AuditContext,
    AuditDataClassification,
    AuditEventDraft,
    AuditEventType,
    AuditResult,
    AuditScopeType,
    AuditVisibilityClass,
)
from app.platform.pagination import CursorPage, InvalidCursorError, decode_cursor, encode_cursor
from app.platform.request_context import RequestContext
from app.schemas.document_request import (
    EmployeeDocumentRequestCreate,
    EmployeeDocumentRequestDecision,
    EmployeeDocumentRequestRead,
    EmployeeDocumentRequestTimelineRead,
)
from app.services.audit_recorder import SqlAlchemyAuditRecorder
from app.services.phase7_access import (
    Phase7ConflictError,
    Phase7NotFoundError,
    Phase7ValidationError,
    Phase7VersionConflictError,
    require_phase7_feature,
)

_CURSOR_RESOURCE = "employee_document_requests_v1"
_TIMELINE_LIMIT = 50


class DocumentRequestService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.audit = SqlAlchemyAuditRecorder(session)

    async def create(
        self,
        *,
        request_context: RequestContext,
        payload: EmployeeDocumentRequestCreate,
    ) -> EmployeeDocumentRequestRead:
        tenant_id, actor_id = _tenant_actor(request_context)
        await require_phase7_feature(
            self.session, tenant_id=tenant_id, feature=FeatureFlagKey.SELF_SERVICE
        )
        employee = await self._own_employee(
            tenant_id=tenant_id,
            membership_id=request_context.require_membership(),
        )
        now = datetime.now(UTC)
        request = EmployeeDocumentRequest(
            id=uuid4(),
            tenant_id=tenant_id,
            employee_id=employee.id,
            requester_user_id=actor_id,
            requester_membership_id=request_context.require_membership(),
            request_type=payload.request_type.value,
            status=EmployeeDocumentRequestStatus.SUBMITTED.value,
            version=1,
            decided_by_user_id=None,
            decided_at=None,
            resolution_reason=None,
        )
        self.session.add(request)
        await self.session.flush()
        await self.session.refresh(request)
        self.session.add(
            EmployeeDocumentRequestTimeline(
                id=uuid4(),
                tenant_id=tenant_id,
                request_id=request.id,
                event_type=EmployeeDocumentRequestStatus.SUBMITTED.value,
                status=EmployeeDocumentRequestStatus.SUBMITTED.value,
                actor_user_id=actor_id,
                source_key=f"document-request:{request.id}:submitted",
                occurred_at=now,
            )
        )
        await self.session.flush()
        await self._audit(
            request_context,
            event_type=AuditEventType.DOCUMENT_REQUEST_SUBMITTED,
            request=request,
            action="submit",
            before_status=None,
        )
        return await self._read(request, employee_name=None, include_timeline=True)

    async def decide(
        self,
        *,
        request_context: RequestContext,
        request_id: UUID,
        decision: EmployeeDocumentRequestStatus,
        payload: EmployeeDocumentRequestDecision,
    ) -> EmployeeDocumentRequestRead:
        if decision not in {
            EmployeeDocumentRequestStatus.RESOLVED,
            EmployeeDocumentRequestStatus.REJECTED,
        }:
            raise Phase7ConflictError
        tenant_id, actor_id = _tenant_actor(request_context)
        await require_phase7_feature(
            self.session, tenant_id=tenant_id, feature=FeatureFlagKey.SELF_SERVICE
        )
        request = await self.session.scalar(
            select(EmployeeDocumentRequest)
            .where(
                EmployeeDocumentRequest.tenant_id == tenant_id,
                EmployeeDocumentRequest.id == request_id,
            )
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if request is None:
            raise Phase7NotFoundError
        if request.version != payload.expected_version:
            raise Phase7VersionConflictError
        if request.status != EmployeeDocumentRequestStatus.SUBMITTED.value:
            raise Phase7ConflictError
        before_status = request.status
        now = datetime.now(UTC)
        request.status = decision.value
        request.decided_by_user_id = actor_id
        request.decided_at = now
        request.resolution_reason = payload.reason
        self.session.add(
            EmployeeDocumentRequestTimeline(
                id=uuid4(),
                tenant_id=tenant_id,
                request_id=request.id,
                event_type=decision.value,
                status=decision.value,
                actor_user_id=actor_id,
                source_key=(
                    f"document-request:{request.id}:{decision.value}:v{payload.expected_version}"
                ),
                occurred_at=now,
            )
        )
        await self.session.flush()
        await self.session.refresh(request)
        await self._audit(
            request_context,
            event_type=(
                AuditEventType.DOCUMENT_REQUEST_RESOLVED
                if decision is EmployeeDocumentRequestStatus.RESOLVED
                else AuditEventType.DOCUMENT_REQUEST_REJECTED
            ),
            request=request,
            action=decision.value,
            before_status=before_status,
        )
        employee = await self.session.scalar(
            select(Employee).where(
                Employee.tenant_id == tenant_id,
                Employee.id == request.employee_id,
            )
        )
        if employee is None:
            raise Phase7ConflictError
        return await self._read(
            request,
            employee_name=_employee_name(employee),
            include_timeline=True,
        )

    async def list_page(
        self,
        *,
        tenant_id: UUID,
        actor_id: UUID,
        own: bool,
        status: EmployeeDocumentRequestStatus | None,
        limit: int,
        cursor: str | None,
    ) -> CursorPage[EmployeeDocumentRequestRead]:
        await require_phase7_feature(
            self.session, tenant_id=tenant_id, feature=FeatureFlagKey.SELF_SERVICE
        )
        cursor_values = _decode_cursor(cursor, own=own, status=status)
        statement = (
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
        if own:
            statement = statement.where(EmployeeDocumentRequest.requester_user_id == actor_id)
        if status is not None:
            statement = statement.where(EmployeeDocumentRequest.status == status.value)
        if cursor_values is not None:
            created_at, request_id = cursor_values
            statement = statement.where(
                or_(
                    EmployeeDocumentRequest.created_at < created_at,
                    and_(
                        EmployeeDocumentRequest.created_at == created_at,
                        EmployeeDocumentRequest.id < request_id,
                    ),
                )
            )
        rows = (
            await self.session.execute(
                statement.order_by(
                    EmployeeDocumentRequest.created_at.desc(),
                    EmployeeDocumentRequest.id.desc(),
                ).limit(limit + 1)
            )
        ).all()
        items = [
            await self._read(
                request,
                employee_name=None if own else _employee_name(employee),
                include_timeline=False,
            )
            for request, employee in rows[:limit]
        ]
        next_cursor = None
        if len(rows) > limit:
            last = rows[limit - 1][0]
            next_cursor = encode_cursor(
                _CURSOR_RESOURCE,
                {
                    "created_at": _aware(last.created_at).isoformat(),
                    "id": str(last.id),
                    "own": "1" if own else "0",
                    "status": status.value if status is not None else "",
                },
            )
        return CursorPage(items=items, next_cursor=next_cursor)

    async def get(
        self,
        *,
        tenant_id: UUID,
        actor_id: UUID,
        request_id: UUID,
        own: bool,
    ) -> EmployeeDocumentRequestRead:
        await require_phase7_feature(
            self.session, tenant_id=tenant_id, feature=FeatureFlagKey.SELF_SERVICE
        )
        statement = (
            select(EmployeeDocumentRequest, Employee)
            .join(
                Employee,
                and_(
                    Employee.tenant_id == EmployeeDocumentRequest.tenant_id,
                    Employee.id == EmployeeDocumentRequest.employee_id,
                ),
            )
            .where(
                EmployeeDocumentRequest.tenant_id == tenant_id,
                EmployeeDocumentRequest.id == request_id,
            )
        )
        if own:
            statement = statement.where(EmployeeDocumentRequest.requester_user_id == actor_id)
        row = (await self.session.execute(statement.limit(1))).one_or_none()
        if row is None:
            raise Phase7NotFoundError
        request, employee = row
        return await self._read(
            request,
            employee_name=None if own else _employee_name(employee),
            include_timeline=True,
        )

    async def _own_employee(
        self,
        *,
        tenant_id: UUID,
        membership_id: UUID,
    ) -> Employee:
        statement = (
            select(Employee)
            .join(
                EmployeeAccountLink,
                and_(
                    EmployeeAccountLink.tenant_id == Employee.tenant_id,
                    EmployeeAccountLink.employee_id == Employee.id,
                ),
            )
            .where(
                Employee.tenant_id == tenant_id,
                EmployeeAccountLink.membership_id == membership_id,
                Employee.archived_at.is_(None),
                Employee.status.in_(("active", "on_leave")),
            )
        )
        employee = await self.session.scalar(statement)
        if employee is None:
            raise Phase7ConflictError
        return employee

    async def _read(
        self,
        request: EmployeeDocumentRequest,
        *,
        employee_name: str | None,
        include_timeline: bool,
    ) -> EmployeeDocumentRequestRead:
        timeline: list[EmployeeDocumentRequestTimelineRead] = []
        if include_timeline:
            records = tuple(
                await self.session.scalars(
                    select(EmployeeDocumentRequestTimeline)
                    .where(
                        EmployeeDocumentRequestTimeline.tenant_id == request.tenant_id,
                        EmployeeDocumentRequestTimeline.request_id == request.id,
                    )
                    .order_by(
                        EmployeeDocumentRequestTimeline.occurred_at,
                        EmployeeDocumentRequestTimeline.id,
                    )
                    .limit(_TIMELINE_LIMIT)
                )
            )
            timeline = [
                EmployeeDocumentRequestTimelineRead(
                    event_type=record.event_type,
                    status=record.status,
                    occurred_at=_aware(record.occurred_at),
                )
                for record in records
            ]
        return EmployeeDocumentRequestRead(
            id=request.id,
            employee_id=request.employee_id,
            employee_name=employee_name,
            request_type=request.request_type,
            status=request.status,
            version=request.version,
            resolution_reason=request.resolution_reason,
            decided_at=_aware(request.decided_at) if request.decided_at is not None else None,
            created_at=_aware(request.created_at),
            updated_at=_aware(request.updated_at),
            timeline=timeline,
        )

    async def _audit(
        self,
        request_context: RequestContext,
        *,
        event_type: AuditEventType,
        request: EmployeeDocumentRequest,
        action: str,
        before_status: str | None,
    ) -> None:
        metadata: dict[str, object] = {
            "request_id": request.id,
            "employee_id": request.employee_id,
            "after_request_status": request.status,
        }
        if before_status is not None:
            metadata["before_request_status"] = before_status
        await self.audit.record(
            AuditEventDraft(
                scope_type=AuditScopeType.TENANT,
                tenant_id=request_context.require_tenant().tenant_id,
                actor_type=AuditActorType.USER,
                actor_user_id=request_context.actor_id,
                session_id=request_context.session_id,
                event_type=event_type,
                category=AuditCategory.HR_OPERATIONS,
                resource_type="employee_document_request",
                resource_id=request.id,
                action=action,
                result=AuditResult.SUCCESS,
                changed_fields=("status", "version"),
                metadata=metadata,
                data_classification=AuditDataClassification.HR_METADATA,
                visibility_class=AuditVisibilityClass.HR_OPERATIONS,
                context=AuditContext.from_request_context(request_context),
            )
        )


def _decode_cursor(
    token: str | None,
    *,
    own: bool,
    status: EmployeeDocumentRequestStatus | None,
) -> tuple[datetime, UUID] | None:
    if token is None:
        return None
    try:
        values = decode_cursor(token, expected_resource=_CURSOR_RESOURCE)
        if set(values) != {"created_at", "id", "own", "status"}:
            raise InvalidCursorError
        if values["own"] != ("1" if own else "0"):
            raise InvalidCursorError
        if values["status"] != (status.value if status is not None else ""):
            raise InvalidCursorError
        created_at = datetime.fromisoformat(values["created_at"])
        if created_at.tzinfo is None or created_at.utcoffset() is None:
            raise InvalidCursorError
        return created_at, UUID(values["id"])
    except (InvalidCursorError, ValueError) as exc:
        raise Phase7ValidationError("The document request cursor is invalid") from exc


def _tenant_actor(context: RequestContext) -> tuple[UUID, UUID]:
    if context.actor_id is None:
        raise RuntimeError("Document request context requires an actor")
    return context.require_tenant().tenant_id, context.actor_id


def _employee_name(employee: Employee) -> str:
    return f"{employee.first_name} {employee.last_name}".strip()


def _aware(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


__all__ = ["DocumentRequestService"]
