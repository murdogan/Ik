"""Phase 6 leave configuration, balance ledger, and approval workflow."""

from __future__ import annotations

from collections import defaultdict
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

from sqlalchemy import and_, case, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.models.employee import Employee, EmployeeStatus
from app.models.employee_account_link import EmployeeAccountLink
from app.models.employee_assignment import EmployeeAssignment
from app.models.employee_document import DocumentProcessingState, EmployeeDocument
from app.models.identity import MembershipStatus, TenantMembership
from app.models.leave import (
    HolidayCalendar,
    HolidayEntry,
    LeaveBalanceLedger,
    LeavePolicy,
    LeaveRequestDay,
    LeaveRequestTimeline,
    LeaveType,
    OutboxEvent,
)
from app.models.leave_request import LeaveRequest, LeaveRequestStatus
from app.models.tenant import Tenant
from app.models.user import User, UserStatus
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
from app.platform.errors.application import ApplicationError
from app.platform.pagination import CursorPage
from app.platform.request_context import RequestContext
from app.schemas.leave import (
    ApprovalTaskListCursor,
    ApprovalTaskRead,
    HolidayCalendarCreate,
    HolidayCalendarRead,
    HolidayCalendarUpdate,
    HolidayEntryCreate,
    HolidayEntryListCursor,
    HolidayEntryRead,
    HolidayEntryUpdate,
    LeaveAccessScope,
    LeaveAdjustmentCreate,
    LeaveBalanceRead,
    LeaveLedgerEntryRead,
    LeaveLedgerEntryType,
    LeaveLedgerListCursor,
    LeavePolicyCreate,
    LeavePolicyRead,
    LeaveRequestCreate,
    LeaveRequestDecision,
    LeaveRequestListCursor,
    LeaveRequestListFilters,
    LeaveRequestRead,
    LeaveRequestTimelineRead,
    LeaveTimelineEventType,
    LeaveTypeCreate,
    LeaveTypeRead,
    LeaveTypeUpdate,
    TeamCalendarEntryRead,
)
from app.services.audit_recorder import SqlAlchemyAuditRecorder

_ZERO = Decimal("0.00")
_ONE = Decimal("1.00")
_MAX_REQUEST_CALENDAR_DAYS = 366
_CONFIG_LIST_LIMIT = 200
_CALENDAR_LIMIT = 50
_HOLIDAY_ENTRY_LIMIT = 500


class LeaveAccessDeniedError(ApplicationError):
    pass


class LeaveNotFoundError(ApplicationError):
    pass


class LeaveValidationError(ApplicationError, ValueError):
    pass


class LeaveConflictError(ApplicationError, ValueError):
    pass


class LeaveVersionConflictError(LeaveConflictError):
    pass


class LeaveInsufficientBalanceError(LeaveConflictError):
    pass


class LeaveEmployeeLinkUnavailableError(LeaveConflictError):
    pass


class LeaveService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self._audit = SqlAlchemyAuditRecorder(session)

    # Configuration -----------------------------------------------------

    async def list_leave_types(
        self,
        tenant_id: UUID,
        *,
        include_inactive: bool,
        effective_on: date | None = None,
        limit: int = _CONFIG_LIST_LIMIT,
    ) -> list[LeaveTypeRead]:
        effective_on = effective_on or date.today()
        current_policy_id = (
            select(LeavePolicy.id)
            .where(
                LeavePolicy.tenant_id == tenant_id,
                LeavePolicy.leave_type_id == LeaveType.id,
                LeavePolicy.effective_from <= effective_on,
            )
            .order_by(LeavePolicy.effective_from.desc(), LeavePolicy.version.desc())
            .limit(1)
            .correlate(LeaveType)
            .scalar_subquery()
        )
        statement = (
            select(LeaveType, LeavePolicy)
            .outerjoin(LeavePolicy, LeavePolicy.id == current_policy_id)
            .where(LeaveType.tenant_id == tenant_id)
        )
        if not include_inactive:
            statement = statement.where(LeaveType.is_active.is_(True))
        rows = (
            await self.session.execute(
                statement.order_by(LeaveType.name, LeaveType.id).limit(min(limit, 200))
            )
        ).all()
        return [
            self._leave_type_read(record, policy, effective_to=None)
            for record, policy in rows
        ]

    async def create_leave_type(
        self,
        *,
        request_context: RequestContext,
        payload: LeaveTypeCreate,
    ) -> LeaveTypeRead:
        tenant_id, actor_id = _tenant_actor(request_context)
        await self._lock_configuration_tenant(tenant_id)
        count = await self.session.scalar(
            select(func.count(LeaveType.id)).where(LeaveType.tenant_id == tenant_id)
        )
        if int(count or 0) >= _CONFIG_LIST_LIMIT:
            raise LeaveConflictError("Tenant leave type limit has been reached")
        if await self.session.scalar(
            select(LeaveType.id).where(
                LeaveType.tenant_id == tenant_id,
                LeaveType.code == payload.code,
            )
        ):
            raise LeaveConflictError("Leave type code is already in use")
        record = LeaveType(
            id=uuid4(),
            tenant_id=tenant_id,
            code=payload.code,
            name=payload.name,
            description=payload.description,
            is_active=True,
            version=1,
        )
        self.session.add(record)
        await self.session.flush()
        await self.session.refresh(record)
        await self._record_audit(
            request_context,
            actor_id=actor_id,
            event_type=AuditEventType.LEAVE_TYPE_CREATED,
            resource_type="leave_type",
            resource_id=record.id,
            action="create",
            changed_fields=("code", "name", "description", "is_active"),
        )
        return self._leave_type_read(record, None, effective_to=None)

    async def update_leave_type(
        self,
        *,
        request_context: RequestContext,
        leave_type_id: UUID,
        payload: LeaveTypeUpdate,
    ) -> LeaveTypeRead:
        tenant_id, actor_id = _tenant_actor(request_context)
        record = await self.session.scalar(
            select(LeaveType)
            .where(LeaveType.tenant_id == tenant_id, LeaveType.id == leave_type_id)
            .with_for_update()
        )
        if record is None:
            raise LeaveNotFoundError
        if record.version != payload.expected_version:
            raise LeaveVersionConflictError("Leave type changed; reload before saving")
        changed_fields: list[str] = []
        for field_name in ("name", "description", "is_active"):
            if field_name in payload.model_fields_set:
                value = getattr(payload, field_name)
                if getattr(record, field_name) != value:
                    setattr(record, field_name, value)
                    changed_fields.append(field_name)
        event_type = (
            AuditEventType.LEAVE_TYPE_DEACTIVATED
            if "is_active" in changed_fields and not record.is_active
            else AuditEventType.LEAVE_TYPE_UPDATED
        )
        if changed_fields:
            await self.session.flush()
            await self.session.refresh(record)
            await self._record_audit(
                request_context,
                actor_id=actor_id,
                event_type=event_type,
                resource_type="leave_type",
                resource_id=record.id,
                action=(
                    "deactivate"
                    if event_type is AuditEventType.LEAVE_TYPE_DEACTIVATED
                    else "update"
                ),
                changed_fields=tuple(changed_fields),
            )
        policy = await self._effective_policy(tenant_id, record.id, date.today())
        return self._leave_type_read(record, policy, effective_to=None)

    async def list_holiday_calendars(
        self,
        tenant_id: UUID,
        *,
        include_inactive: bool,
    ) -> list[HolidayCalendarRead]:
        statement = select(HolidayCalendar).where(HolidayCalendar.tenant_id == tenant_id)
        if not include_inactive:
            statement = statement.where(HolidayCalendar.is_active.is_(True))
        calendars = tuple(
            await self.session.scalars(
                statement.order_by(
                    HolidayCalendar.is_default.desc(), HolidayCalendar.name, HolidayCalendar.id
                ).limit(_CALENDAR_LIMIT)
            )
        )
        if not calendars:
            return []
        entries = (
            await self.session.execute(
                select(HolidayEntry)
                .where(
                    HolidayEntry.tenant_id == tenant_id,
                    HolidayEntry.calendar_id.in_(item.id for item in calendars),
                )
                .order_by(HolidayEntry.holiday_date.desc(), HolidayEntry.id)
                .limit(_HOLIDAY_ENTRY_LIMIT)
            )
        ).scalars()
        by_calendar: dict[UUID, list[HolidayEntryRead]] = defaultdict(list)
        for entry in entries:
            by_calendar[entry.calendar_id].append(self._holiday_entry_read(entry))
        entry_counts = {
            calendar_id: int(count)
            for calendar_id, count in (
                await self.session.execute(
                    select(HolidayEntry.calendar_id, func.count(HolidayEntry.id))
                    .where(
                        HolidayEntry.tenant_id == tenant_id,
                        HolidayEntry.calendar_id.in_(item.id for item in calendars),
                    )
                    .group_by(HolidayEntry.calendar_id)
                )
            ).all()
        }
        return [
            self._holiday_calendar_read(
                item,
                by_calendar.get(item.id, []),
                entries_truncated=(
                    entry_counts.get(item.id, 0) > len(by_calendar.get(item.id, []))
                ),
            )
            for item in calendars
        ]

    async def create_holiday_calendar(
        self,
        *,
        request_context: RequestContext,
        payload: HolidayCalendarCreate,
    ) -> HolidayCalendarRead:
        tenant_id, actor_id = _tenant_actor(request_context)
        await self._lock_configuration_tenant(tenant_id)
        calendars = tuple(
            await self.session.scalars(
                select(HolidayCalendar)
                .where(HolidayCalendar.tenant_id == tenant_id)
                .order_by(
                    HolidayCalendar.is_default.desc(),
                    HolidayCalendar.name,
                    HolidayCalendar.id,
                )
                .with_for_update()
            )
        )
        if len(calendars) >= _CALENDAR_LIMIT:
            raise LeaveConflictError("Tenant holiday calendar limit has been reached")
        make_default = payload.is_default or not any(
            item.is_default and item.is_active for item in calendars
        )
        demoted_calendars: list[HolidayCalendar] = []
        if make_default:
            for item in calendars:
                if item.is_default:
                    item.is_default = False
                    demoted_calendars.append(item)
            await self.session.flush()
        record = HolidayCalendar(
            id=uuid4(),
            tenant_id=tenant_id,
            name=payload.name,
            is_default=make_default,
            is_active=True,
            non_working_weekdays=list(payload.non_working_weekdays),
            version=1,
        )
        self.session.add(record)
        await self.session.flush()
        await self.session.refresh(record)
        await self._record_audit(
            request_context,
            actor_id=actor_id,
            event_type=AuditEventType.HOLIDAY_CALENDAR_CREATED,
            resource_type="holiday_calendar",
            resource_id=record.id,
            action="create",
            changed_fields=("name", "is_default", "is_active", "non_working_weekdays"),
        )
        for demoted in demoted_calendars:
            await self._record_audit(
                request_context,
                actor_id=actor_id,
                event_type=AuditEventType.HOLIDAY_CALENDAR_UPDATED,
                resource_type="holiday_calendar",
                resource_id=demoted.id,
                action="update",
                changed_fields=("is_default",),
            )
        return self._holiday_calendar_read(record, [], entries_truncated=False)

    async def list_holiday_entry_page(
        self,
        *,
        tenant_id: UUID,
        calendar_id: UUID,
        include_inactive: bool,
        start_date: date | None,
        end_date: date | None,
        limit: int,
        cursor: HolidayEntryListCursor | None,
    ) -> CursorPage[HolidayEntryRead]:
        if start_date is not None and end_date is not None and end_date < start_date:
            raise LeaveValidationError("Holiday end_date must be on or after start_date")
        calendar_exists = await self.session.scalar(
            select(HolidayCalendar.id).where(
                HolidayCalendar.tenant_id == tenant_id,
                HolidayCalendar.id == calendar_id,
            )
        )
        if calendar_exists is None:
            raise LeaveNotFoundError
        statement = select(HolidayEntry).where(
            HolidayEntry.tenant_id == tenant_id,
            HolidayEntry.calendar_id == calendar_id,
        )
        if not include_inactive:
            statement = statement.where(HolidayEntry.is_active.is_(True))
        if start_date is not None:
            statement = statement.where(HolidayEntry.holiday_date >= start_date)
        if end_date is not None:
            statement = statement.where(HolidayEntry.holiday_date <= end_date)
        if cursor is not None:
            statement = statement.where(
                or_(
                    HolidayEntry.holiday_date < cursor.holiday_date,
                    and_(
                        HolidayEntry.holiday_date == cursor.holiday_date,
                        HolidayEntry.id < cursor.id,
                    ),
                )
            )
        rows = tuple(
            await self.session.scalars(
                statement.order_by(
                    HolidayEntry.holiday_date.desc(), HolidayEntry.id.desc()
                ).limit(limit + 1)
            )
        )
        items = [self._holiday_entry_read(item) for item in rows[:limit]]
        next_cursor = None
        if len(rows) > limit:
            last = rows[limit - 1]
            next_cursor = HolidayEntryListCursor(
                holiday_date=last.holiday_date,
                id=last.id,
            ).to_token()
        return CursorPage(items=items, next_cursor=next_cursor)

    async def update_holiday_calendar(
        self,
        *,
        request_context: RequestContext,
        calendar_id: UUID,
        payload: HolidayCalendarUpdate,
    ) -> HolidayCalendarRead:
        tenant_id, actor_id = _tenant_actor(request_context)
        calendars = tuple(
            await self.session.scalars(
                select(HolidayCalendar)
                .where(HolidayCalendar.tenant_id == tenant_id)
                .order_by(
                    HolidayCalendar.is_default.desc(),
                    HolidayCalendar.name,
                    HolidayCalendar.id,
                )
                .with_for_update()
            )
        )
        record = next((item for item in calendars if item.id == calendar_id), None)
        if record is None:
            raise LeaveNotFoundError
        if record.version != payload.expected_version:
            raise LeaveVersionConflictError("Holiday calendar changed; reload before saving")
        target_active = (
            payload.is_active
            if "is_active" in payload.model_fields_set
            else record.is_active
        )
        target_default = (
            payload.is_default if "is_default" in payload.model_fields_set else record.is_default
        )
        update_fields = set(payload.model_fields_set)
        if not target_active and target_default and "is_default" in update_fields:
            raise LeaveConflictError("An inactive calendar cannot be the tenant default")
        if not target_active and record.is_default:
            # Deactivation implicitly demotes the current default. This keeps the concise
            # versioned toggle contract usable while the replacement below preserves the
            # invariant that every tenant has one active default calendar.
            target_default = False
            update_fields.add("is_default")
        replacement: HolidayCalendar | None = None
        if record.is_default and (not target_default or not target_active):
            replacement = next(
                (item for item in calendars if item.id != record.id and item.is_active), None
            )
            if replacement is None:
                raise LeaveConflictError("At least one active default calendar is required")
        demoted_calendars: list[HolidayCalendar] = []
        if target_default and not record.is_default:
            for item in calendars:
                if item.id != record.id and item.is_default:
                    item.is_default = False
                    demoted_calendars.append(item)
            if demoted_calendars:
                await self.session.flush()
        changed_fields: list[str] = []
        for field_name in ("name", "is_default", "is_active", "non_working_weekdays"):
            if field_name in update_fields:
                value = (
                    target_default
                    if field_name == "is_default"
                    else getattr(payload, field_name)
                )
                if field_name == "non_working_weekdays":
                    value = list(value or [])
                if getattr(record, field_name) != value:
                    setattr(record, field_name, value)
                    changed_fields.append(field_name)
        if changed_fields:
            await self.session.flush()
        if replacement is not None:
            replacement.is_default = True
            await self.session.flush()
        if changed_fields:
            await self.session.refresh(record)
            await self._record_audit(
                request_context,
                actor_id=actor_id,
                event_type=AuditEventType.HOLIDAY_CALENDAR_UPDATED,
                resource_type="holiday_calendar",
                resource_id=record.id,
                action="update",
                changed_fields=tuple(changed_fields),
            )
        for demoted in demoted_calendars:
            await self._record_audit(
                request_context,
                actor_id=actor_id,
                event_type=AuditEventType.HOLIDAY_CALENDAR_UPDATED,
                resource_type="holiday_calendar",
                resource_id=demoted.id,
                action="update",
                changed_fields=("is_default",),
            )
        if replacement is not None:
            await self._record_audit(
                request_context,
                actor_id=actor_id,
                event_type=AuditEventType.HOLIDAY_CALENDAR_UPDATED,
                resource_type="holiday_calendar",
                resource_id=replacement.id,
                action="update",
                changed_fields=("is_default",),
            )
        entries, entries_truncated = await self._calendar_entries(tenant_id, record.id)
        return self._holiday_calendar_read(
            record, entries, entries_truncated=entries_truncated
        )

    async def create_holiday_entry(
        self,
        *,
        request_context: RequestContext,
        calendar_id: UUID,
        payload: HolidayEntryCreate,
    ) -> HolidayEntryRead:
        tenant_id, actor_id = _tenant_actor(request_context)
        await self._lock_configuration_tenant(tenant_id)
        calendar = await self.session.scalar(
            select(HolidayCalendar)
            .where(
                HolidayCalendar.tenant_id == tenant_id,
                HolidayCalendar.id == calendar_id,
                HolidayCalendar.is_active.is_(True),
            )
            .with_for_update()
        )
        if calendar is None:
            raise LeaveNotFoundError
        if await self.session.scalar(
            select(HolidayEntry.id).where(
                HolidayEntry.tenant_id == tenant_id,
                HolidayEntry.calendar_id == calendar_id,
                HolidayEntry.holiday_date == payload.holiday_date,
            )
        ):
            raise LeaveConflictError("A holiday already exists on this date")
        record = HolidayEntry(
            id=uuid4(),
            tenant_id=tenant_id,
            calendar_id=calendar_id,
            holiday_date=payload.holiday_date,
            name=payload.name,
            is_active=True,
            version=1,
        )
        self.session.add(record)
        await self.session.flush()
        await self.session.refresh(record)
        await self._record_audit(
            request_context,
            actor_id=actor_id,
            event_type=AuditEventType.HOLIDAY_ENTRY_CREATED,
            resource_type="holiday_entry",
            resource_id=record.id,
            action="create",
            changed_fields=("holiday_date", "name", "is_active"),
        )
        return self._holiday_entry_read(record)

    async def update_holiday_entry(
        self,
        *,
        request_context: RequestContext,
        calendar_id: UUID,
        entry_id: UUID,
        payload: HolidayEntryUpdate,
    ) -> HolidayEntryRead:
        tenant_id, actor_id = _tenant_actor(request_context)
        record = await self.session.scalar(
            select(HolidayEntry)
            .where(
                HolidayEntry.tenant_id == tenant_id,
                HolidayEntry.calendar_id == calendar_id,
                HolidayEntry.id == entry_id,
            )
            .with_for_update()
        )
        if record is None:
            raise LeaveNotFoundError
        if record.version != payload.expected_version:
            raise LeaveVersionConflictError("Holiday entry changed; reload before saving")
        changed_fields: list[str] = []
        for field_name in ("name", "is_active"):
            if field_name in payload.model_fields_set:
                value = getattr(payload, field_name)
                if getattr(record, field_name) != value:
                    setattr(record, field_name, value)
                    changed_fields.append(field_name)
        if changed_fields:
            await self.session.flush()
            event_type = (
                AuditEventType.HOLIDAY_ENTRY_DEACTIVATED
                if "is_active" in changed_fields and not record.is_active
                else AuditEventType.HOLIDAY_ENTRY_UPDATED
            )
            await self._record_audit(
                request_context,
                actor_id=actor_id,
                event_type=event_type,
                resource_type="holiday_entry",
                resource_id=record.id,
                action="deactivate" if not record.is_active else "update",
                changed_fields=tuple(changed_fields),
            )
        return self._holiday_entry_read(record)

    async def list_policies(
        self,
        tenant_id: UUID,
        *,
        leave_type_id: UUID | None,
        limit: int = _CONFIG_LIST_LIMIT,
    ) -> list[LeavePolicyRead]:
        statement = (
            select(LeavePolicy, LeaveType)
            .join(
                LeaveType,
                and_(
                    LeaveType.tenant_id == LeavePolicy.tenant_id,
                    LeaveType.id == LeavePolicy.leave_type_id,
                ),
            )
            .where(LeavePolicy.tenant_id == tenant_id)
        )
        if leave_type_id is not None:
            statement = statement.where(LeavePolicy.leave_type_id == leave_type_id)
        rows = (
            await self.session.execute(
                statement.order_by(
                    LeaveType.name,
                    LeavePolicy.effective_from.desc(),
                    LeavePolicy.version.desc(),
                    LeavePolicy.id,
                ).limit(min(limit, 200))
            )
        ).all()
        next_effective: dict[UUID, date] = {}
        by_type: dict[UUID, list[LeavePolicy]] = defaultdict(list)
        for policy, _leave_type in rows:
            by_type[policy.leave_type_id].append(policy)
        for policies in by_type.values():
            ordered = sorted(policies, key=lambda item: item.effective_from)
            for current, successor in zip(ordered, ordered[1:], strict=False):
                next_effective[current.id] = successor.effective_from - timedelta(days=1)
        return [
            self._policy_read(policy, leave_type, next_effective.get(policy.id))
            for policy, leave_type in rows
        ]

    async def create_policy(
        self,
        *,
        request_context: RequestContext,
        payload: LeavePolicyCreate,
    ) -> LeavePolicyRead:
        tenant_id, actor_id = _tenant_actor(request_context)
        # One tenant-row lock serializes policy creation across leave types so the bounded,
        # immutable history cannot race past the list contract's hard limit.
        await self._lock_configuration_tenant(tenant_id)
        leave_type = await self.session.scalar(
            select(LeaveType)
            .where(
                LeaveType.tenant_id == tenant_id,
                LeaveType.id == payload.leave_type_id,
            )
            .with_for_update()
        )
        if leave_type is None:
            raise LeaveNotFoundError
        if leave_type.code == "medical_report" and not payload.document_required:
            raise LeaveValidationError(
                "Medical/report leave policies must require a document"
            )
        policy_count = await self.session.scalar(
            select(func.count(LeavePolicy.id)).where(LeavePolicy.tenant_id == tenant_id)
        )
        if int(policy_count or 0) >= _CONFIG_LIST_LIMIT:
            raise LeaveConflictError("Tenant leave policy history limit has been reached")
        latest = await self.session.scalar(
            select(LeavePolicy)
            .where(
                LeavePolicy.tenant_id == tenant_id,
                LeavePolicy.leave_type_id == leave_type.id,
            )
            .order_by(LeavePolicy.version.desc())
            .limit(1)
        )
        if latest is not None and payload.effective_from <= latest.effective_from:
            raise LeaveConflictError(
                "A new policy version must start after the latest effective version"
            )
        record = LeavePolicy(
            id=uuid4(),
            tenant_id=tenant_id,
            leave_type_id=leave_type.id,
            version=1 if latest is None else latest.version + 1,
            effective_from=payload.effective_from,
            paid=payload.paid,
            document_required=payload.document_required,
            negative_balance_allowed=payload.negative_balance_allowed,
            accrual_enabled=payload.accrual_enabled,
            accrual_days_per_month=payload.accrual_days_per_month,
            carryover_enabled=payload.carryover_enabled,
            carryover_limit_days=payload.carryover_limit_days,
            created_by_user_id=actor_id,
        )
        self.session.add(record)
        await self.session.flush()
        await self.session.refresh(record)
        await self._record_audit(
            request_context,
            actor_id=actor_id,
            event_type=AuditEventType.LEAVE_POLICY_VERSION_CREATED,
            resource_type="leave_policy",
            resource_id=record.id,
            action="create_version",
            changed_fields=(
                "effective_from",
                "paid",
                "document_required",
                "negative_balance_allowed",
                "accrual_enabled",
                "accrual_days_per_month",
                "carryover_enabled",
                "carryover_limit_days",
            ),
        )
        return self._policy_read(record, leave_type, None)

    # Balances ----------------------------------------------------------

    async def list_balances(
        self,
        *,
        tenant_id: UUID,
        employee_id: UUID,
        period_year: int,
    ) -> list[LeaveBalanceRead]:
        await self._require_employee(
            tenant_id, employee_id, lock=False, require_active=False
        )
        aggregate = (
            select(
                LeaveBalanceLedger.leave_type_id.label("leave_type_id"),
                func.coalesce(
                    func.sum(
                        case(
                            (
                                LeaveBalanceLedger.entry_type
                                == LeaveLedgerEntryType.EARNED.value,
                                LeaveBalanceLedger.amount_days,
                            ),
                            else_=0,
                        )
                    ),
                    0,
                ).label("earned"),
                func.coalesce(
                    func.sum(
                        case(
                            (
                                LeaveBalanceLedger.entry_type
                                == LeaveLedgerEntryType.ADJUSTMENT.value,
                                LeaveBalanceLedger.amount_days,
                            ),
                            else_=0,
                        )
                    ),
                    0,
                ).label("adjusted"),
                func.coalesce(
                    func.sum(
                        case(
                            (
                                LeaveBalanceLedger.entry_type.in_(
                                    (
                                        LeaveLedgerEntryType.USED.value,
                                        LeaveLedgerEntryType.USED_RELEASE.value,
                                    )
                                ),
                                LeaveBalanceLedger.amount_days,
                            ),
                            else_=0,
                        )
                    ),
                    0,
                ).label("used"),
                func.coalesce(
                    func.sum(
                        case(
                            (
                                LeaveBalanceLedger.entry_type.in_(
                                    (
                                        LeaveLedgerEntryType.PLANNED.value,
                                        LeaveLedgerEntryType.PLANNED_RELEASE.value,
                                    )
                                ),
                                LeaveBalanceLedger.amount_days,
                            ),
                            else_=0,
                        )
                    ),
                    0,
                ).label("planned"),
            )
            .where(
                LeaveBalanceLedger.tenant_id == tenant_id,
                LeaveBalanceLedger.employee_id == employee_id,
                LeaveBalanceLedger.period_year == period_year,
            )
            .group_by(LeaveBalanceLedger.leave_type_id)
            .subquery()
        )
        rows = (
            await self.session.execute(
                select(LeaveType, aggregate)
                .outerjoin(aggregate, aggregate.c.leave_type_id == LeaveType.id)
                .where(
                    LeaveType.tenant_id == tenant_id,
                    or_(LeaveType.is_active.is_(True), aggregate.c.leave_type_id.is_not(None)),
                )
                .order_by(LeaveType.name, LeaveType.id)
                .limit(_CONFIG_LIST_LIMIT)
            )
        ).all()
        policies = await self._effective_policies_for_types(
            tenant_id,
            [row[0].id for row in rows],
            date(period_year, 12, 31),
        )
        balances: list[LeaveBalanceRead] = []
        for row in rows:
            leave_type = row[0]
            earned = _decimal(row.earned)
            adjusted = _decimal(row.adjusted)
            used = max(_ZERO, _decimal(row.used))
            planned = max(_ZERO, _decimal(row.planned))
            policy = policies.get(leave_type.id)
            balances.append(
                LeaveBalanceRead(
                    id=uuid5(
                        NAMESPACE_URL,
                        f"wealthy-falcon:leave-balance:{tenant_id}:{employee_id}:"
                        f"{leave_type.id}:{period_year}",
                    ),
                    employee_id=employee_id,
                    period_year=period_year,
                    leave_type_id=leave_type.id,
                    leave_type_code=leave_type.code,
                    leave_type_name=leave_type.name,
                    leave_type=(
                        leave_type.name
                        if leave_type.code.startswith("legacy_")
                        else leave_type.code
                    ),
                    earned_days=earned,
                    adjusted_days=adjusted,
                    used_days=used,
                    planned_days=planned,
                    available_days=earned + adjusted - used - planned,
                    negative_balance_allowed=(
                        policy.negative_balance_allowed if policy is not None else False
                    ),
                    opening_balance_days=earned + adjusted,
                    remaining_days=earned + adjusted - used - planned,
                )
            )
        return balances

    async def list_own_balances(
        self,
        *,
        request_context: RequestContext,
        period_year: int,
    ) -> list[LeaveBalanceRead]:
        tenant_id, actor_id = _tenant_actor(request_context)
        employee = await self._resolve_own_employee(
            tenant_id,
            actor_id=actor_id,
            membership_id=request_context.require_membership(),
            lock=False,
        )
        return await self.list_balances(
            tenant_id=tenant_id,
            employee_id=employee.id,
            period_year=period_year,
        )

    async def list_ledger_page(
        self,
        *,
        tenant_id: UUID,
        employee_id: UUID,
        limit: int,
        cursor: LeaveLedgerListCursor | None,
        period_year: int | None = None,
    ) -> CursorPage[LeaveLedgerEntryRead]:
        await self._require_employee(
            tenant_id, employee_id, lock=False, require_active=False
        )
        statement = (
            select(LeaveBalanceLedger, LeaveType)
            .join(
                LeaveType,
                and_(
                    LeaveType.tenant_id == LeaveBalanceLedger.tenant_id,
                    LeaveType.id == LeaveBalanceLedger.leave_type_id,
                ),
            )
            .where(
                LeaveBalanceLedger.tenant_id == tenant_id,
                LeaveBalanceLedger.employee_id == employee_id,
            )
        )
        if period_year is not None:
            statement = statement.where(LeaveBalanceLedger.period_year == period_year)
        if cursor is not None:
            statement = statement.where(
                or_(
                    LeaveBalanceLedger.created_at < cursor.created_at,
                    and_(
                        LeaveBalanceLedger.created_at == cursor.created_at,
                        LeaveBalanceLedger.id < cursor.id,
                    ),
                )
            )
        rows = (
            await self.session.execute(
                statement.order_by(
                    LeaveBalanceLedger.created_at.desc(), LeaveBalanceLedger.id.desc()
                ).limit(limit + 1)
            )
        ).all()
        items = [self._ledger_read(entry, leave_type) for entry, leave_type in rows[:limit]]
        next_cursor = None
        if len(rows) > limit:
            last = rows[limit - 1][0]
            next_cursor = LeaveLedgerListCursor(
                created_at=_aware(last.created_at), id=last.id
            ).to_token()
        return CursorPage(items=items, next_cursor=next_cursor)

    async def list_own_ledger_page(
        self,
        *,
        request_context: RequestContext,
        limit: int,
        cursor: LeaveLedgerListCursor | None,
        period_year: int | None,
    ) -> CursorPage[LeaveLedgerEntryRead]:
        tenant_id, actor_id = _tenant_actor(request_context)
        employee = await self._resolve_own_employee(
            tenant_id,
            actor_id=actor_id,
            membership_id=request_context.require_membership(),
            lock=False,
        )
        return await self.list_ledger_page(
            tenant_id=tenant_id,
            employee_id=employee.id,
            limit=limit,
            cursor=cursor,
            period_year=period_year,
        )

    async def create_adjustment(
        self,
        *,
        request_context: RequestContext,
        payload: LeaveAdjustmentCreate,
    ) -> LeaveLedgerEntryRead:
        tenant_id, actor_id = _tenant_actor(request_context)
        await self._require_employee(
            tenant_id, payload.employee_id, lock=True, require_active=True
        )
        leave_type = await self.session.scalar(
            select(LeaveType).where(
                LeaveType.tenant_id == tenant_id,
                LeaveType.id == payload.leave_type_id,
                LeaveType.is_active.is_(True),
            )
        )
        if leave_type is None:
            raise LeaveNotFoundError
        ledger = LeaveBalanceLedger(
            id=uuid4(),
            tenant_id=tenant_id,
            employee_id=payload.employee_id,
            leave_type_id=leave_type.id,
            period_year=payload.period_year,
            entry_type=LeaveLedgerEntryType.ADJUSTMENT.value,
            amount_days=payload.amount_days,
            effective_date=payload.effective_date,
            reason=payload.reason,
            request_id=None,
            source_type="manual_adjustment",
            source_id=None,
            source_key=f"adjustment:{uuid4()}",
            reversal_of_entry_id=None,
            created_by_user_id=actor_id,
        )
        self.session.add(ledger)
        await self.session.flush()
        await self._record_audit(
            request_context,
            actor_id=actor_id,
            event_type=AuditEventType.LEAVE_BALANCE_ADJUSTED,
            resource_type="leave_balance_ledger",
            resource_id=ledger.id,
            action="adjust",
            changed_fields=("adjusted_days", "available_days"),
        )
        self._add_outbox(
            tenant_id=tenant_id,
            aggregate_type="leave_balance",
            aggregate_id=ledger.id,
            event_type="leave.balance_adjusted",
            source_key=f"leave.balance_adjusted:{ledger.id}",
            payload={
                "ledger_entry_id": str(ledger.id),
                "employee_id": str(payload.employee_id),
                "leave_type_id": str(leave_type.id),
                "period_year": payload.period_year,
                "amount_days": str(payload.amount_days),
            },
        )
        await self.session.flush()
        return self._ledger_read(ledger, leave_type)

    # Requests and approvals -------------------------------------------

    async def create_request(
        self,
        *,
        request_context: RequestContext,
        payload: LeaveRequestCreate,
        permissions: tuple[str, ...],
    ) -> LeaveRequestRead:
        if "leave:create:own" not in permissions:
            raise LeaveAccessDeniedError
        tenant_id, actor_id = _tenant_actor(request_context)
        membership_id = request_context.require_membership()
        employee = await self._resolve_own_employee(
            tenant_id,
            actor_id=actor_id,
            membership_id=membership_id,
            lock=True,
        )
        self._validate_employment_dates(employee, payload.start_date, payload.end_date)
        leave_type = await self.session.scalar(
            select(LeaveType).where(
                LeaveType.tenant_id == tenant_id,
                LeaveType.id == payload.leave_type_id,
                LeaveType.is_active.is_(True),
            )
        )
        if leave_type is None:
            raise LeaveNotFoundError
        policy = await self._effective_policy(tenant_id, leave_type.id, payload.start_date)
        if policy is None:
            raise LeaveConflictError("No leave policy is effective for the selected date")
        days = await self._count_request_days(
            tenant_id=tenant_id,
            start_date=payload.start_date,
            end_date=payload.end_date,
        )
        counted_days = sum((item[3] for item in days), _ZERO)
        if counted_days <= 0:
            raise LeaveValidationError("The selected range contains no counted working day")
        await self._validate_document(
            tenant_id=tenant_id,
            employee_id=employee.id,
            document_id=payload.document_id,
            required=policy.document_required,
            valid_through=payload.end_date,
        )
        overlap = await self.session.scalar(
            select(LeaveRequest.id).where(
                LeaveRequest.tenant_id == tenant_id,
                LeaveRequest.employee_id == employee.id,
                LeaveRequest.status.in_(
                    (LeaveRequestStatus.PENDING.value, LeaveRequestStatus.APPROVED.value)
                ),
                LeaveRequest.start_date <= payload.end_date,
                LeaveRequest.end_date >= payload.start_date,
            )
        )
        if overlap is not None:
            raise LeaveConflictError("The leave request overlaps an existing active request")
        manager_user_id = await self._current_manager_id(tenant_id, employee.id, date.today())
        if manager_user_id is None:
            raise LeaveConflictError("The employee has no current manager for leave approval")
        by_year = _counted_by_year(days)
        if policy.paid and not policy.negative_balance_allowed:
            for year, amount in by_year.items():
                available = await self._available_days(
                    tenant_id, employee.id, leave_type.id, year
                )
                if available < amount:
                    raise LeaveInsufficientBalanceError(
                        "Available leave balance is insufficient for the selected dates"
                    )
        request_id = uuid4()
        request = LeaveRequest(
            id=request_id,
            tenant_id=tenant_id,
            employee_id=employee.id,
            leave_type=leave_type.code,
            leave_type_id=leave_type.id,
            policy_id=policy.id,
            start_date=payload.start_date,
            end_date=payload.end_date,
            status=LeaveRequestStatus.PENDING.value,
            requested_by_user_id=actor_id,
            requested_by_membership_id=membership_id,
            routed_manager_user_id=manager_user_id,
            document_id=payload.document_id,
            employee_note=payload.employee_note,
            counted_days=counted_days,
            version=1,
            decided_by_user_id=None,
            decision_note=None,
            decided_at=None,
        )
        self.session.add(request)
        # The child fact rows carry scalar composite foreign keys rather than ORM
        # relationships. Persist the parent first so SQLAlchemy cannot schedule a
        # ledger/day insert ahead of the new request within the same atomic transaction.
        await self.session.flush()
        for leave_date, is_working, holiday_id, counted in days:
            self.session.add(
                LeaveRequestDay(
                    id=uuid4(),
                    tenant_id=tenant_id,
                    request_id=request_id,
                    leave_date=leave_date,
                    is_working_day=is_working,
                    is_holiday=holiday_id is not None,
                    counted_days=counted,
                    holiday_entry_id=holiday_id,
                )
            )
        planned_entries: list[LeaveBalanceLedger] = []
        for year, amount in by_year.items():
            entry = LeaveBalanceLedger(
                id=uuid4(),
                tenant_id=tenant_id,
                employee_id=employee.id,
                leave_type_id=leave_type.id,
                period_year=year,
                entry_type=LeaveLedgerEntryType.PLANNED.value,
                amount_days=amount,
                effective_date=max(payload.start_date, date(year, 1, 1)),
                reason=None,
                request_id=request_id,
                source_type="leave_request",
                source_id=request_id,
                source_key=f"request:{request_id}:planned:{year}",
                reversal_of_entry_id=None,
                created_by_user_id=actor_id,
            )
            planned_entries.append(entry)
            self.session.add(entry)
        occurred_at = datetime.now(UTC)
        self.session.add(
            LeaveRequestTimeline(
                id=uuid4(),
                tenant_id=tenant_id,
                request_id=request_id,
                event_type=LeaveTimelineEventType.SUBMITTED.value,
                status=LeaveRequestStatus.PENDING.value,
                actor_user_id=actor_id,
                source_key=f"request:{request_id}:submitted",
                occurred_at=occurred_at,
            )
        )
        self._add_outbox(
            tenant_id=tenant_id,
            aggregate_type="leave_request",
            aggregate_id=request_id,
            event_type="leave.requested",
            source_key=f"leave.requested:{request_id}",
            payload=self._request_outbox_payload(request, leave_type),
            occurred_at=occurred_at,
        )
        await self.session.flush()
        await self._record_audit(
            request_context,
            actor_id=actor_id,
            event_type=AuditEventType.LEAVE_REQUEST_SUBMITTED,
            resource_type="leave_request",
            resource_id=request_id,
            action="submit",
            changed_fields=("status", "counted_days", "version"),
        )
        return await self._request_read(request, employee, leave_type, include_timeline=True)

    async def list_request_page(
        self,
        *,
        request_context: RequestContext,
        permissions: tuple[str, ...],
        filters: LeaveRequestListFilters,
        limit: int,
        offset: int,
        cursor: LeaveRequestListCursor | None,
    ) -> CursorPage[LeaveRequestRead]:
        tenant_id, actor_id = _tenant_actor(request_context)
        scope = _resolve_read_scope(permissions, filters.scope)
        statement = self._request_rows_statement(tenant_id)
        statement = await self._apply_request_scope(
            statement,
            tenant_id=tenant_id,
            actor_id=actor_id,
            membership_id=request_context.require_membership(),
            scope=scope,
        )
        if filters.status is not None:
            statement = statement.where(LeaveRequest.status == filters.status.value)
        if filters.employee_id is not None:
            statement = statement.where(LeaveRequest.employee_id == filters.employee_id)
        if filters.start_date is not None:
            statement = statement.where(LeaveRequest.end_date >= filters.start_date)
        if filters.end_date is not None:
            statement = statement.where(LeaveRequest.start_date <= filters.end_date)
        if cursor is not None:
            statement = statement.where(
                or_(
                    LeaveRequest.created_at < cursor.created_at,
                    and_(
                        LeaveRequest.created_at == cursor.created_at,
                        LeaveRequest.start_date > cursor.start_date,
                    ),
                    and_(
                        LeaveRequest.created_at == cursor.created_at,
                        LeaveRequest.start_date == cursor.start_date,
                        LeaveRequest.id > cursor.id,
                    ),
                )
            )
        elif offset:
            statement = statement.offset(offset)
        rows = (
            await self.session.execute(
                statement.order_by(
                    LeaveRequest.created_at.desc(),
                    LeaveRequest.start_date,
                    LeaveRequest.id,
                ).limit(limit + 1)
            )
        ).all()
        items = [
            await self._request_read(request, employee, leave_type, include_timeline=False)
            for request, employee, leave_type in rows[:limit]
        ]
        next_cursor = None
        if len(rows) > limit:
            last = rows[limit - 1][0]
            next_cursor = LeaveRequestListCursor(
                created_at=_aware(last.created_at),
                start_date=last.start_date,
                id=last.id,
            ).to_token()
        return CursorPage(items=items, next_cursor=next_cursor)

    async def get_request(
        self,
        *,
        request_context: RequestContext,
        permissions: tuple[str, ...],
        request_id: UUID,
        scope: LeaveAccessScope | None = None,
    ) -> LeaveRequestRead:
        tenant_id, actor_id = _tenant_actor(request_context)
        base_statement = self._request_rows_statement(tenant_id).where(
            LeaveRequest.id == request_id
        )
        row = None
        if scope is not None or "leave:read:tenant" in permissions:
            resolved_scope = _resolve_read_scope(permissions, scope)
            statement = await self._apply_request_scope(
                base_statement,
                tenant_id=tenant_id,
                actor_id=actor_id,
                membership_id=request_context.require_membership(),
                scope=resolved_scope,
            )
            row = (await self.session.execute(statement.limit(1))).one_or_none()
        else:
            # A manager can be both an employee and an approver. With no explicit scope, accept
            # the union of their exact own and current-team visibility instead of choosing one
            # role and accidentally hiding records visible through the other.
            for candidate in (LeaveAccessScope.TEAM, LeaveAccessScope.OWN):
                permission = {
                    LeaveAccessScope.TEAM: "leave:read:team",
                    LeaveAccessScope.OWN: "leave:read:own",
                }[candidate]
                if permission not in permissions:
                    continue
                try:
                    statement = await self._apply_request_scope(
                        base_statement,
                        tenant_id=tenant_id,
                        actor_id=actor_id,
                        membership_id=request_context.require_membership(),
                        scope=candidate,
                    )
                except LeaveEmployeeLinkUnavailableError:
                    continue
                row = (await self.session.execute(statement.limit(1))).one_or_none()
                if row is not None:
                    break
        if row is None:
            raise LeaveNotFoundError
        request, employee, leave_type = row
        return await self._request_read(request, employee, leave_type, include_timeline=True)

    async def decide_request(
        self,
        *,
        request_context: RequestContext,
        request_id: UUID,
        action: str,
        payload: LeaveRequestDecision,
        permissions: tuple[str, ...],
    ) -> LeaveRequestRead:
        tenant_id, actor_id = _tenant_actor(request_context)
        if action not in {"approve", "reject", "cancel"}:
            raise LeaveValidationError("Unsupported leave request action")
        request = await self.session.scalar(
            select(LeaveRequest)
            .where(LeaveRequest.tenant_id == tenant_id, LeaveRequest.id == request_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if request is None:
            raise LeaveNotFoundError
        if request.version != payload.expected_version:
            raise LeaveVersionConflictError("Leave request changed; reload before deciding")
        if action in {"approve", "reject"}:
            if request.status != LeaveRequestStatus.PENDING.value:
                raise LeaveConflictError("Only pending leave requests can be approved or rejected")
            if "leave:manage:tenant" not in permissions:
                if "leave:approve:team" not in permissions or not await self._is_current_manager(
                    tenant_id, request.employee_id, actor_id, date.today()
                ):
                    raise LeaveNotFoundError
                # Assignment mutations lock the employee row. Locking it here and checking
                # manager scope again establishes a deterministic before/after order with a
                # concurrent reporting-line change.
                await self._lock_employee_for_manager_decision(tenant_id, request.employee_id)
                if not await self._is_current_manager(
                    tenant_id, request.employee_id, actor_id, date.today()
                ):
                    raise LeaveNotFoundError
            if action == "reject" and not payload.decision_note:
                raise LeaveValidationError("A rejection note is required")
        else:
            if request.status not in {
                LeaveRequestStatus.PENDING.value,
                LeaveRequestStatus.APPROVED.value,
            }:
                raise LeaveConflictError("Only pending or approved leave requests can be cancelled")
            if "leave:manage:tenant" not in permissions:
                if "leave:cancel:own" not in permissions:
                    raise LeaveAccessDeniedError
                own = await self._resolve_own_employee(
                    tenant_id,
                    actor_id=actor_id,
                    membership_id=request_context.require_membership(),
                    lock=False,
                )
                if own.id != request.employee_id:
                    raise LeaveNotFoundError
        previous_status = request.status
        target_status = {
            "approve": LeaveRequestStatus.APPROVED.value,
            "reject": LeaveRequestStatus.REJECTED.value,
            "cancel": LeaveRequestStatus.CANCELLED.value,
        }[action]
        approval_policy: LeavePolicy | None = None
        if action == "approve":
            await self._validate_employee_for_approval(tenant_id, request)
            approval_policy = await self.session.scalar(
                select(LeavePolicy).where(
                    LeavePolicy.tenant_id == tenant_id,
                    LeavePolicy.leave_type_id == request.leave_type_id,
                    LeavePolicy.id == request.policy_id,
                )
            )
            if approval_policy is None:
                raise LeaveConflictError("The request policy snapshot is unavailable")
            if approval_policy.document_required:
                await self._validate_document(
                    tenant_id=tenant_id,
                    employee_id=request.employee_id,
                    document_id=request.document_id,
                    required=True,
                    valid_through=request.end_date,
                )
        entries = tuple(
            await self.session.scalars(
                select(LeaveBalanceLedger)
                .where(
                    LeaveBalanceLedger.tenant_id == tenant_id,
                    LeaveBalanceLedger.request_id == request.id,
                )
                .order_by(LeaveBalanceLedger.period_year, LeaveBalanceLedger.created_at)
                .with_for_update()
            )
        )
        now = datetime.now(UTC)
        if previous_status == LeaveRequestStatus.PENDING.value:
            planned = [
                item
                for item in entries
                if item.entry_type == LeaveLedgerEntryType.PLANNED.value
            ]
            if not planned and _decimal(request.counted_days) > _ZERO:
                raise LeaveConflictError("The leave reservation is unavailable")
            if (
                action == "approve"
                and approval_policy is not None
                and approval_policy.paid
                and not approval_policy.negative_balance_allowed
            ):
                for entry in planned:
                    available = await self._available_days(
                        tenant_id,
                        request.employee_id,
                        request.leave_type_id,
                        entry.period_year,
                    )
                    # The existing planned row already reserves this request. Conversion to
                    # used is balance-neutral, so a negative current value means a later
                    # adjustment made the request ineligible for approval.
                    if available < _ZERO:
                        raise LeaveInsufficientBalanceError(
                            "Available leave balance is insufficient to approve this request"
                        )
            for entry in planned:
                self.session.add(
                    self._reversal_entry(
                        entry,
                        actor_id=actor_id,
                        entry_type=LeaveLedgerEntryType.PLANNED_RELEASE,
                        source_key=f"request:{request.id}:{action}:planned_release:{entry.period_year}",
                    )
                )
                if action == "approve":
                    self.session.add(
                        LeaveBalanceLedger(
                            id=uuid4(),
                            tenant_id=tenant_id,
                            employee_id=request.employee_id,
                            leave_type_id=request.leave_type_id,
                            period_year=entry.period_year,
                            entry_type=LeaveLedgerEntryType.USED.value,
                            amount_days=entry.amount_days,
                            effective_date=entry.effective_date,
                            reason=None,
                            request_id=request.id,
                            source_type="leave_request",
                            source_id=request.id,
                            source_key=f"request:{request.id}:approved:used:{entry.period_year}",
                            reversal_of_entry_id=None,
                            created_by_user_id=actor_id,
                        )
                    )
        elif previous_status == LeaveRequestStatus.APPROVED.value and action == "cancel":
            used = [
                item for item in entries if item.entry_type == LeaveLedgerEntryType.USED.value
            ]
            if not used and _decimal(request.counted_days) > _ZERO:
                raise LeaveConflictError("The approved leave usage is unavailable")
            for entry in used:
                self.session.add(
                    self._reversal_entry(
                        entry,
                        actor_id=actor_id,
                        entry_type=LeaveLedgerEntryType.USED_RELEASE,
                        source_key=f"request:{request.id}:cancelled:used_release:{entry.period_year}",
                    )
                )
        request.status = target_status
        request.decided_by_user_id = actor_id
        request.decision_note = payload.decision_note
        request.decided_at = now
        self.session.add(
            LeaveRequestTimeline(
                id=uuid4(),
                tenant_id=tenant_id,
                request_id=request.id,
                event_type=target_status,
                status=target_status,
                actor_user_id=actor_id,
                source_key=f"request:{request.id}:{target_status}:v{payload.expected_version}",
                occurred_at=now,
            )
        )
        leave_type = await self.session.scalar(
            select(LeaveType).where(
                LeaveType.tenant_id == tenant_id, LeaveType.id == request.leave_type_id
            )
        )
        if leave_type is None:
            raise LeaveConflictError("The request leave type is unavailable")
        self._add_outbox(
            tenant_id=tenant_id,
            aggregate_type="leave_request",
            aggregate_id=request.id,
            event_type=f"leave.{target_status}",
            source_key=f"leave.{target_status}:{request.id}:v{payload.expected_version}",
            payload={**self._request_outbox_payload(request, leave_type), "status": target_status},
            occurred_at=now,
        )
        await self.session.flush()
        event_type = {
            "approve": AuditEventType.LEAVE_REQUEST_APPROVED,
            "reject": AuditEventType.LEAVE_REQUEST_REJECTED,
            "cancel": AuditEventType.LEAVE_REQUEST_CANCELLED,
        }[action]
        await self._record_audit(
            request_context,
            actor_id=actor_id,
            event_type=event_type,
            resource_type="leave_request",
            resource_id=request.id,
            action=action,
            changed_fields=("status", "counted_days", "version"),
        )
        employee = await self.session.scalar(
            select(Employee).where(
                Employee.tenant_id == tenant_id, Employee.id == request.employee_id
            )
        )
        if employee is None:
            raise LeaveConflictError("The request employee is unavailable")
        return await self._request_read(request, employee, leave_type, include_timeline=True)

    async def list_approval_tasks(
        self,
        *,
        request_context: RequestContext,
        permissions: tuple[str, ...],
        limit: int,
        cursor: ApprovalTaskListCursor | None,
    ) -> CursorPage[ApprovalTaskRead]:
        tenant_id, actor_id = _tenant_actor(request_context)
        statement = self._request_rows_statement(tenant_id).where(
            LeaveRequest.status == LeaveRequestStatus.PENDING.value
        )
        if "leave:manage:tenant" not in permissions:
            if "leave:approve:team" not in permissions:
                raise LeaveAccessDeniedError
            statement = statement.where(
                _current_assignment_exists(
                    tenant_id=tenant_id,
                    employee_id=LeaveRequest.employee_id,
                    manager_user_id=actor_id,
                    effective_on=date.today(),
                )
            )
        if cursor is not None:
            statement = statement.where(
                or_(
                    LeaveRequest.created_at > cursor.created_at,
                    and_(
                        LeaveRequest.created_at == cursor.created_at,
                        LeaveRequest.id > cursor.id,
                    ),
                )
            )
        rows = (
            await self.session.execute(
                statement.order_by(LeaveRequest.created_at, LeaveRequest.id).limit(limit + 1)
            )
        ).all()
        tasks: list[ApprovalTaskRead] = []
        for request, employee, leave_type in rows[:limit]:
            balance = await self._available_days(
                tenant_id,
                employee.id,
                leave_type.id,
                request.start_date.year,
            )
            tasks.append(
                ApprovalTaskRead(
                    id=request.id,
                    request=await self._request_read(
                        request, employee, leave_type, include_timeline=False
                    ),
                    available_days=balance,
                )
            )
        next_cursor = None
        if len(rows) > limit:
            last = rows[limit - 1][0]
            next_cursor = ApprovalTaskListCursor(
                created_at=_aware(last.created_at), id=last.id
            ).to_token()
        return CursorPage(items=tasks, next_cursor=next_cursor)

    async def list_team_calendar(
        self,
        *,
        request_context: RequestContext,
        permissions: tuple[str, ...],
        start_date: date,
        end_date: date,
        limit: int,
        scope: LeaveAccessScope | None,
    ) -> list[TeamCalendarEntryRead]:
        if end_date < start_date or (end_date - start_date).days > 366:
            raise LeaveValidationError("Team calendar date range must be at most 367 days")
        tenant_id, actor_id = _tenant_actor(request_context)
        requested_scope = scope or (
            LeaveAccessScope.TENANT
            if "leave:read:tenant" in permissions
            else LeaveAccessScope.TEAM
        )
        if requested_scope is LeaveAccessScope.TENANT:
            if "leave:read:tenant" not in permissions:
                raise LeaveAccessDeniedError
        elif requested_scope is LeaveAccessScope.TEAM:
            if "leave:read:team" not in permissions:
                raise LeaveAccessDeniedError
        else:
            raise LeaveAccessDeniedError
        statement = self._request_rows_statement(tenant_id).where(
            LeaveRequest.status == LeaveRequestStatus.APPROVED.value,
            LeaveRequest.start_date <= end_date,
            LeaveRequest.end_date >= start_date,
        )
        if requested_scope is LeaveAccessScope.TEAM:
            statement = statement.where(
                _current_assignment_exists(
                    tenant_id=tenant_id,
                    employee_id=LeaveRequest.employee_id,
                    manager_user_id=actor_id,
                    effective_on=date.today(),
                )
            )
        rows = (
            await self.session.execute(
                statement.order_by(LeaveRequest.start_date, LeaveRequest.id).limit(limit)
            )
        ).all()
        return [
            TeamCalendarEntryRead(
                request_id=request.id,
                id=request.id,
                employee_id=employee.id,
                employee_name=f"{employee.first_name} {employee.last_name}".strip(),
                leave_type_code=leave_type.code,
                leave_type_name=leave_type.name,
                start_date=request.start_date,
                end_date=request.end_date,
                counted_days=_decimal(request.counted_days),
            )
            for request, employee, leave_type in rows
        ]

    # Internal projections and validation ------------------------------

    async def _lock_configuration_tenant(self, tenant_id: UUID) -> None:
        """Serialize bounded configuration creates before taking any child-row lock."""

        tenant_exists = await self.session.scalar(
            select(Tenant.id).where(Tenant.id == tenant_id).with_for_update()
        )
        if tenant_exists is None:
            raise LeaveNotFoundError

    async def _resolve_own_employee(
        self,
        tenant_id: UUID,
        *,
        actor_id: UUID,
        membership_id: UUID,
        lock: bool,
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
                Employee.tenant_id == tenant_id,
                Employee.archived_at.is_(None),
                Employee.status.in_((EmployeeStatus.ACTIVE.value, EmployeeStatus.ON_LEAVE.value)),
                EmployeeAccountLink.membership_id == membership_id,
                TenantMembership.id == membership_id,
                TenantMembership.legacy_user_id == actor_id,
                TenantMembership.status == MembershipStatus.ACTIVE.value,
                User.id == actor_id,
                User.status == UserStatus.ACTIVE.value,
                User.permission_version == TenantMembership.permission_version,
            )
        )
        if lock:
            statement = statement.with_for_update(of=Employee)
        employee = await self.session.scalar(statement)
        if employee is None:
            raise LeaveEmployeeLinkUnavailableError(
                "The authenticated account is not linked to an active employee"
            )
        return employee

    async def _require_employee(
        self,
        tenant_id: UUID,
        employee_id: UUID,
        *,
        lock: bool,
        require_active: bool,
    ) -> Employee:
        statement = select(Employee).where(
            Employee.tenant_id == tenant_id,
            Employee.id == employee_id,
        )
        if require_active:
            statement = statement.where(
                Employee.archived_at.is_(None),
                Employee.status.in_(
                    (EmployeeStatus.ACTIVE.value, EmployeeStatus.ON_LEAVE.value)
                ),
            )
        if lock:
            statement = statement.with_for_update(of=Employee)
        employee = await self.session.scalar(statement)
        if employee is None:
            raise LeaveNotFoundError
        return employee

    async def _validate_employee_for_approval(
        self, tenant_id: UUID, request: LeaveRequest
    ) -> None:
        employee = await self.session.scalar(
            select(Employee)
            .where(
                Employee.tenant_id == tenant_id,
                Employee.id == request.employee_id,
                Employee.archived_at.is_(None),
                Employee.status.in_(
                    (EmployeeStatus.ACTIVE.value, EmployeeStatus.ON_LEAVE.value)
                ),
            )
            .with_for_update(of=Employee)
        )
        if employee is None:
            raise LeaveConflictError("The request employee is no longer active")
        self._validate_employment_dates(employee, request.start_date, request.end_date)

    async def _lock_employee_for_manager_decision(
        self, tenant_id: UUID, employee_id: UUID
    ) -> None:
        employee_exists = await self.session.scalar(
            select(Employee.id)
            .where(Employee.tenant_id == tenant_id, Employee.id == employee_id)
            .with_for_update()
        )
        if employee_exists is None:
            raise LeaveNotFoundError

    @staticmethod
    def _validate_employment_dates(
        employee: Employee, start_date: date, end_date: date
    ) -> None:
        if start_date < employee.employment_start_date:
            raise LeaveValidationError("Leave cannot start before employment")
        if employee.employment_end_date is not None and end_date > employee.employment_end_date:
            raise LeaveValidationError("Leave cannot extend beyond employment")

    async def _validate_document(
        self,
        *,
        tenant_id: UUID,
        employee_id: UUID,
        document_id: UUID | None,
        required: bool,
        valid_through: date,
    ) -> None:
        if document_id is None:
            if required:
                raise LeaveValidationError("The selected leave policy requires a document")
            return
        document = await self.session.scalar(
            select(EmployeeDocument)
            .where(
                EmployeeDocument.tenant_id == tenant_id,
                EmployeeDocument.id == document_id,
                EmployeeDocument.employee_id == employee_id,
                EmployeeDocument.archived_at.is_(None),
                EmployeeDocument.employee_visible.is_(True),
                EmployeeDocument.processing_state == DocumentProcessingState.AVAILABLE.value,
                or_(
                    EmployeeDocument.expires_on.is_(None),
                    EmployeeDocument.expires_on >= valid_through,
                ),
            )
            .with_for_update(of=EmployeeDocument)
        )
        if document is None:
            raise LeaveValidationError(
                "The selected document is not available through the leave end date"
            )

    async def _count_request_days(
        self, *, tenant_id: UUID, start_date: date, end_date: date
    ) -> list[tuple[date, bool, UUID | None, Decimal]]:
        span = (end_date - start_date).days + 1
        if span < 1 or span > _MAX_REQUEST_CALENDAR_DAYS:
            raise LeaveValidationError("A leave request may cover at most 366 calendar days")
        calendar = await self.session.scalar(
            select(HolidayCalendar).where(
                HolidayCalendar.tenant_id == tenant_id,
                HolidayCalendar.is_active.is_(True),
                HolidayCalendar.is_default.is_(True),
            )
        )
        non_working = set(calendar.non_working_weekdays if calendar is not None else [5, 6])
        holidays: dict[date, UUID] = {}
        if calendar is not None:
            holiday_rows = tuple(
                await self.session.scalars(
                    select(HolidayEntry).where(
                        HolidayEntry.tenant_id == tenant_id,
                        HolidayEntry.calendar_id == calendar.id,
                        HolidayEntry.is_active.is_(True),
                        HolidayEntry.holiday_date >= start_date,
                        HolidayEntry.holiday_date <= end_date,
                    )
                )
            )
            holidays = {item.holiday_date: item.id for item in holiday_rows}
        result: list[tuple[date, bool, UUID | None, Decimal]] = []
        for offset in range(span):
            leave_date = start_date + timedelta(days=offset)
            is_working = leave_date.weekday() not in non_working
            holiday_id = holidays.get(leave_date)
            counted = _ONE if is_working and holiday_id is None else _ZERO
            result.append((leave_date, is_working, holiday_id, counted))
        return result

    async def _effective_policy(
        self, tenant_id: UUID, leave_type_id: UUID, effective_on: date
    ) -> LeavePolicy | None:
        return await self.session.scalar(
            select(LeavePolicy)
            .where(
                LeavePolicy.tenant_id == tenant_id,
                LeavePolicy.leave_type_id == leave_type_id,
                LeavePolicy.effective_from <= effective_on,
            )
            .order_by(LeavePolicy.effective_from.desc(), LeavePolicy.version.desc())
            .limit(1)
        )

    async def _effective_policies_for_types(
        self, tenant_id: UUID, leave_type_ids: list[UUID], effective_on: date
    ) -> dict[UUID, LeavePolicy]:
        if not leave_type_ids:
            return {}
        policy_alias = aliased(LeavePolicy)
        current_id = (
            select(policy_alias.id)
            .where(
                policy_alias.tenant_id == tenant_id,
                policy_alias.leave_type_id == LeaveType.id,
                policy_alias.effective_from <= effective_on,
            )
            .order_by(policy_alias.effective_from.desc(), policy_alias.version.desc())
            .limit(1)
            .correlate(LeaveType)
            .scalar_subquery()
        )
        rows = tuple(
            await self.session.scalars(
                select(LeavePolicy)
                .join(LeaveType, LeavePolicy.id == current_id)
                .where(
                    LeaveType.tenant_id == tenant_id,
                    LeaveType.id.in_(leave_type_ids),
                )
            )
        )
        return {item.leave_type_id: item for item in rows}

    async def _available_days(
        self, tenant_id: UUID, employee_id: UUID, leave_type_id: UUID, period_year: int
    ) -> Decimal:
        entries = (
            await self.session.execute(
                select(LeaveBalanceLedger.entry_type, LeaveBalanceLedger.amount_days).where(
                    LeaveBalanceLedger.tenant_id == tenant_id,
                    LeaveBalanceLedger.employee_id == employee_id,
                    LeaveBalanceLedger.leave_type_id == leave_type_id,
                    LeaveBalanceLedger.period_year == period_year,
                )
            )
        ).all()
        earned = sum(
            (
                _decimal(amount)
                for kind, amount in entries
                if kind == LeaveLedgerEntryType.EARNED.value
            ),
            _ZERO,
        )
        adjusted = sum(
            (
                _decimal(amount)
                for kind, amount in entries
                if kind == LeaveLedgerEntryType.ADJUSTMENT.value
            ),
            _ZERO,
        )
        used = sum(
            (
                _decimal(amount)
                for kind, amount in entries
                if kind
                in (LeaveLedgerEntryType.USED.value, LeaveLedgerEntryType.USED_RELEASE.value)
            ),
            _ZERO,
        )
        planned = sum(
            (
                _decimal(amount)
                for kind, amount in entries
                if kind
                in (
                    LeaveLedgerEntryType.PLANNED.value,
                    LeaveLedgerEntryType.PLANNED_RELEASE.value,
                )
            ),
            _ZERO,
        )
        return earned + adjusted - used - planned

    async def _current_manager_id(
        self, tenant_id: UUID, employee_id: UUID, effective_on: date
    ) -> UUID | None:
        return await self.session.scalar(
            select(EmployeeAssignment.manager_user_id).where(
                EmployeeAssignment.tenant_id == tenant_id,
                EmployeeAssignment.employee_id == employee_id,
                EmployeeAssignment.manager_user_id.is_not(None),
                EmployeeAssignment.effective_from <= effective_on,
                or_(
                    EmployeeAssignment.effective_to.is_(None),
                    EmployeeAssignment.effective_to > effective_on,
                ),
            ).order_by(
                EmployeeAssignment.effective_from.desc(),
                EmployeeAssignment.id.desc(),
            )
        )

    async def _is_current_manager(
        self, tenant_id: UUID, employee_id: UUID, actor_id: UUID, effective_on: date
    ) -> bool:
        return bool(
            await self.session.scalar(
                select(
                    _current_assignment_exists(
                        tenant_id=tenant_id,
                        employee_id=employee_id,
                        manager_user_id=actor_id,
                        effective_on=effective_on,
                    )
                )
            )
        )

    def _request_rows_statement(self, tenant_id: UUID):
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

    async def _apply_request_scope(
        self,
        statement,
        *,
        tenant_id: UUID,
        actor_id: UUID,
        membership_id: UUID,
        scope: LeaveAccessScope,
    ):
        if scope is LeaveAccessScope.TENANT:
            return statement
        if scope is LeaveAccessScope.TEAM:
            return statement.where(
                _current_assignment_exists(
                    tenant_id=tenant_id,
                    employee_id=LeaveRequest.employee_id,
                    manager_user_id=actor_id,
                    effective_on=date.today(),
                )
            )
        employee = await self._resolve_own_employee(
            tenant_id,
            actor_id=actor_id,
            membership_id=membership_id,
            lock=False,
        )
        return statement.where(LeaveRequest.employee_id == employee.id)

    async def _request_read(
        self,
        request: LeaveRequest,
        employee: Employee,
        leave_type: LeaveType,
        *,
        include_timeline: bool,
    ) -> LeaveRequestRead:
        timeline: list[LeaveRequestTimelineRead] = []
        if include_timeline:
            records = tuple(
                await self.session.scalars(
                    select(LeaveRequestTimeline)
                    .where(
                        LeaveRequestTimeline.tenant_id == request.tenant_id,
                        LeaveRequestTimeline.request_id == request.id,
                    )
                    .order_by(
                        LeaveRequestTimeline.occurred_at, LeaveRequestTimeline.id
                    )
                    .limit(20)
                )
            )
            timeline = [
                LeaveRequestTimelineRead(
                    id=item.id,
                    event_type=item.event_type,
                    status=item.status,
                    actor_user_id=item.actor_user_id,
                    occurred_at=item.occurred_at,
                )
                for item in records
            ]
        return LeaveRequestRead(
            id=request.id,
            employee_id=employee.id,
            employee_name=f"{employee.first_name} {employee.last_name}".strip(),
            leave_type_id=leave_type.id,
            leave_type=request.leave_type,
            leave_type_code=leave_type.code,
            leave_type_name=leave_type.name,
            policy_id=request.policy_id,
            start_date=request.start_date,
            end_date=request.end_date,
            counted_days=_decimal(request.counted_days),
            status=request.status,
            requested_by_user_id=request.requested_by_user_id,
            decided_by_user_id=request.decided_by_user_id,
            employee_note=request.employee_note,
            decision_note=request.decision_note,
            has_document=request.document_id is not None,
            version=request.version,
            created_at=request.created_at,
            decided_at=request.decided_at,
            timeline=timeline,
        )

    async def _calendar_entries(
        self, tenant_id: UUID, calendar_id: UUID
    ) -> tuple[list[HolidayEntryRead], bool]:
        records = tuple(
            await self.session.scalars(
                select(HolidayEntry)
                .where(
                    HolidayEntry.tenant_id == tenant_id,
                    HolidayEntry.calendar_id == calendar_id,
                )
                .order_by(HolidayEntry.holiday_date.desc(), HolidayEntry.id)
                .limit(_HOLIDAY_ENTRY_LIMIT + 1)
            )
        )
        return (
            [self._holiday_entry_read(item) for item in records[:_HOLIDAY_ENTRY_LIMIT]],
            len(records) > _HOLIDAY_ENTRY_LIMIT,
        )

    @staticmethod
    def _policy_read(
        record: LeavePolicy, leave_type: LeaveType, effective_to: date | None
    ) -> LeavePolicyRead:
        return LeavePolicyRead(
            id=record.id,
            leave_type_id=leave_type.id,
            leave_type_code=leave_type.code,
            leave_type_name=leave_type.name,
            version=record.version,
            effective_from=record.effective_from,
            effective_to=effective_to,
            paid=record.paid,
            document_required=record.document_required,
            negative_balance_allowed=record.negative_balance_allowed,
            accrual_enabled=record.accrual_enabled,
            accrual_days_per_month=record.accrual_days_per_month,
            carryover_enabled=record.carryover_enabled,
            carryover_limit_days=record.carryover_limit_days,
            created_at=record.created_at,
        )

    def _leave_type_read(
        self,
        record: LeaveType,
        policy: LeavePolicy | None,
        *,
        effective_to: date | None,
    ) -> LeaveTypeRead:
        return LeaveTypeRead(
            id=record.id,
            code=record.code,
            name=record.name,
            description=record.description,
            is_active=record.is_active,
            version=record.version,
            current_policy=(
                self._policy_read(policy, record, effective_to)
                if policy is not None
                else None
            ),
            created_at=record.created_at,
            updated_at=record.updated_at,
        )

    @staticmethod
    def _holiday_entry_read(record: HolidayEntry) -> HolidayEntryRead:
        return HolidayEntryRead(
            id=record.id,
            holiday_date=record.holiday_date,
            name=record.name,
            is_active=record.is_active,
            version=record.version,
        )

    @staticmethod
    def _holiday_calendar_read(
        record: HolidayCalendar,
        entries: list[HolidayEntryRead],
        *,
        entries_truncated: bool,
    ) -> HolidayCalendarRead:
        return HolidayCalendarRead(
            id=record.id,
            name=record.name,
            is_default=record.is_default,
            is_active=record.is_active,
            non_working_weekdays=list(record.non_working_weekdays),
            version=record.version,
            entries=entries,
            entries_truncated=entries_truncated,
            created_at=record.created_at,
            updated_at=record.updated_at,
        )

    @staticmethod
    def _ledger_read(
        entry: LeaveBalanceLedger, leave_type: LeaveType
    ) -> LeaveLedgerEntryRead:
        return LeaveLedgerEntryRead(
            id=entry.id,
            employee_id=entry.employee_id,
            leave_type_id=leave_type.id,
            leave_type_code=leave_type.code,
            leave_type_name=leave_type.name,
            period_year=entry.period_year,
            entry_type=entry.entry_type,
            amount_days=entry.amount_days,
            effective_date=entry.effective_date,
            reason=entry.reason,
            created_at=entry.created_at,
        )

    @staticmethod
    def _reversal_entry(
        entry: LeaveBalanceLedger,
        *,
        actor_id: UUID,
        entry_type: LeaveLedgerEntryType,
        source_key: str,
    ) -> LeaveBalanceLedger:
        return LeaveBalanceLedger(
            id=uuid4(),
            tenant_id=entry.tenant_id,
            employee_id=entry.employee_id,
            leave_type_id=entry.leave_type_id,
            period_year=entry.period_year,
            entry_type=entry_type.value,
            amount_days=-abs(_decimal(entry.amount_days)),
            effective_date=entry.effective_date,
            reason=None,
            request_id=entry.request_id,
            source_type="leave_request",
            source_id=entry.request_id,
            source_key=source_key,
            reversal_of_entry_id=entry.id,
            created_by_user_id=actor_id,
        )

    def _add_outbox(
        self,
        *,
        tenant_id: UUID,
        aggregate_type: str,
        aggregate_id: UUID,
        event_type: str,
        source_key: str,
        payload: dict[str, object],
        occurred_at: datetime | None = None,
    ) -> None:
        self.session.add(
            OutboxEvent(
                id=uuid4(),
                tenant_id=tenant_id,
                aggregate_type=aggregate_type,
                aggregate_id=aggregate_id,
                event_type=event_type,
                payload=payload,
                source_key=source_key,
                occurred_at=occurred_at or datetime.now(UTC),
            )
        )

    @staticmethod
    def _request_outbox_payload(
        request: LeaveRequest, leave_type: LeaveType
    ) -> dict[str, object]:
        return {
            "request_id": str(request.id),
            "employee_id": str(request.employee_id),
            "leave_type_id": str(leave_type.id),
            "status": request.status,
            "start_date": request.start_date.isoformat(),
            "end_date": request.end_date.isoformat(),
            "counted_days": str(request.counted_days),
        }

    async def _record_audit(
        self,
        request_context: RequestContext,
        *,
        actor_id: UUID,
        event_type: AuditEventType,
        resource_type: str,
        resource_id: UUID,
        action: str,
        changed_fields: tuple[str, ...],
    ) -> None:
        await self._audit.record(
            AuditEventDraft(
                scope_type=AuditScopeType.TENANT,
                tenant_id=request_context.require_tenant().tenant_id,
                actor_type=AuditActorType.USER,
                actor_user_id=actor_id,
                event_type=event_type,
                category=AuditCategory.HR_OPERATIONS,
                resource_type=resource_type,
                resource_id=resource_id,
                action=action,
                result=AuditResult.SUCCESS,
                context=AuditContext.from_request_context(request_context),
                session_id=request_context.session_id,
                changed_fields=changed_fields,
                metadata={},
                data_classification=AuditDataClassification.HR_METADATA,
                visibility_class=AuditVisibilityClass.HR_OPERATIONS,
            )
        )


def _tenant_actor(context: RequestContext) -> tuple[UUID, UUID]:
    if context.actor_id is None:
        raise RuntimeError("Authenticated leave request context requires an actor")
    return context.require_tenant().tenant_id, context.actor_id


def _resolve_read_scope(
    permissions: tuple[str, ...], requested: LeaveAccessScope | None
) -> LeaveAccessScope:
    allowed = {
        LeaveAccessScope.OWN: "leave:read:own" in permissions,
        LeaveAccessScope.TEAM: "leave:read:team" in permissions,
        LeaveAccessScope.TENANT: "leave:read:tenant" in permissions,
    }
    if requested is not None:
        if not allowed[requested]:
            raise LeaveAccessDeniedError
        return requested
    for scope in (LeaveAccessScope.TENANT, LeaveAccessScope.TEAM, LeaveAccessScope.OWN):
        if allowed[scope]:
            return scope
    raise LeaveAccessDeniedError


def _current_assignment_exists(
    *, tenant_id: UUID, employee_id, manager_user_id: UUID, effective_on: date
):
    return (
        select(EmployeeAssignment.id)
        .where(
            EmployeeAssignment.tenant_id == tenant_id,
            EmployeeAssignment.employee_id == employee_id,
            EmployeeAssignment.manager_user_id == manager_user_id,
            EmployeeAssignment.effective_from <= effective_on,
            or_(
                EmployeeAssignment.effective_to.is_(None),
                EmployeeAssignment.effective_to > effective_on,
            ),
        )
        .exists()
    )


def _counted_by_year(
    days: list[tuple[date, bool, UUID | None, Decimal]],
) -> dict[int, Decimal]:
    result: dict[int, Decimal] = defaultdict(lambda: _ZERO)
    for leave_date, _is_working, _holiday_id, counted in days:
        if counted:
            result[leave_date.year] += counted
    return dict(result)


def _decimal(value: object | None) -> Decimal:
    if value is None:
        return _ZERO
    return value if isinstance(value, Decimal) else Decimal(str(value))


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


__all__ = [
    "LeaveAccessDeniedError",
    "LeaveConflictError",
    "LeaveEmployeeLinkUnavailableError",
    "LeaveInsufficientBalanceError",
    "LeaveNotFoundError",
    "LeaveService",
    "LeaveValidationError",
    "LeaveVersionConflictError",
]
