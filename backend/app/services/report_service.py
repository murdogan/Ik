"""Bounded allowlisted employee, leave, and document report queries."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from hashlib import sha256
from typing import Any
from uuid import UUID

from sqlalchemy import Select, and_, case, exists, func, literal, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.department import Department
from app.models.employee import Employee, EmployeeStatus
from app.models.employee_assignment import EmployeeAssignment
from app.models.employee_document import DocumentProcessingState, DocumentType, EmployeeDocument
from app.models.leave import LeaveType
from app.models.leave_request import LeaveRequest
from app.models.organization import Branch, LegalEntity
from app.models.position import Position
from app.models.reporting import ReportScope, ReportType
from app.platform.pagination import InvalidCursorError, decode_cursor, encode_cursor
from app.schemas.reporting import (
    DocumentChecklistReportStatus,
    DocumentReportField,
    DocumentReportFilters,
    DocumentReportRow,
    EmployeeReportField,
    EmployeeReportFilters,
    EmployeeReportRow,
    LeaveReportField,
    LeaveReportFilters,
    LeaveReportRow,
)
from app.services.reporting_access import ReportAuthorization, ReportingValidationError

_CURRENT_STATUSES = (EmployeeStatus.ACTIVE.value, EmployeeStatus.ON_LEAVE.value)


@dataclass(frozen=True, slots=True)
class ReportQueryPage:
    items: list[EmployeeReportRow | LeaveReportRow | DocumentReportRow]
    next_cursor: str | None


class ReportService:
    def __init__(
        self,
        *,
        session: AsyncSession,
        today: date | None = None,
        document_expiring_days: int = 30,
    ) -> None:
        self.session = session
        self.today = today or date.today()
        self.document_expiring_days = document_expiring_days

    async def employee_report(
        self,
        *,
        tenant_id: UUID,
        authorization: ReportAuthorization,
        fields: tuple[str, ...],
        filters: EmployeeReportFilters,
        limit: int,
        cursor: str | None,
    ) -> ReportQueryPage:
        _validate_limit(limit)
        field_names = _validated_field_names(fields, EmployeeReportField)
        fingerprint = _query_fingerprint(
            report_type=ReportType.EMPLOYEES,
            authorization=authorization,
            fields=field_names,
            filters=filters.model_dump(mode="json"),
            effective_on=self.today,
        )
        cursor_id = _id_cursor(
            cursor,
            resource="report_employees",
            fingerprint=fingerprint,
        )
        statement = _employee_statement(
            tenant_id=tenant_id,
            authorization=authorization,
            fields=field_names,
            filters=filters,
            effective_on=self.today,
        )
        if cursor_id is not None:
            statement = statement.where(Employee.id > cursor_id)
        rows = (
            await self.session.execute(
                statement.order_by(Employee.id.asc()).limit(limit + 1)
            )
        ).mappings().all()
        visible = rows[:limit]
        items = [EmployeeReportRow(values=_public_values(row, field_names)) for row in visible]
        next_cursor = None
        if len(rows) > limit:
            next_cursor = encode_cursor(
                "report_employees",
                {"id": str(visible[-1]["_cursor_id"]), "fingerprint": fingerprint},
            )
        return ReportQueryPage(items=items, next_cursor=next_cursor)

    async def leave_report(
        self,
        *,
        tenant_id: UUID,
        authorization: ReportAuthorization,
        fields: tuple[str, ...],
        filters: LeaveReportFilters,
        limit: int,
        cursor: str | None,
    ) -> ReportQueryPage:
        _validate_limit(limit)
        field_names = _validated_field_names(fields, LeaveReportField)
        fingerprint = _query_fingerprint(
            report_type=ReportType.LEAVES,
            authorization=authorization,
            fields=field_names,
            filters=filters.model_dump(mode="json"),
            effective_on=self.today,
        )
        cursor_values = _dated_cursor(
            cursor,
            resource="report_leaves",
            fingerprint=fingerprint,
        )
        statement = _leave_statement(
            tenant_id=tenant_id,
            authorization=authorization,
            fields=field_names,
            filters=filters,
            effective_on=self.today,
        )
        if cursor_values is not None:
            occurred_at, cursor_id = cursor_values
            statement = statement.where(
                or_(
                    LeaveRequest.created_at < occurred_at,
                    and_(LeaveRequest.created_at == occurred_at, LeaveRequest.id < cursor_id),
                )
            )
        rows = (
            await self.session.execute(
                statement.order_by(LeaveRequest.created_at.desc(), LeaveRequest.id.desc()).limit(
                    limit + 1
                )
            )
        ).mappings().all()
        visible = rows[:limit]
        items = [LeaveReportRow(values=_public_values(row, field_names)) for row in visible]
        next_cursor = None
        if len(rows) > limit:
            last = visible[-1]
            next_cursor = encode_cursor(
                "report_leaves",
                {
                    "created_at": last["_cursor_created_at"].isoformat(),
                    "id": str(last["_cursor_id"]),
                    "fingerprint": fingerprint,
                },
            )
        return ReportQueryPage(items=items, next_cursor=next_cursor)

    async def document_report(
        self,
        *,
        tenant_id: UUID,
        authorization: ReportAuthorization,
        fields: tuple[str, ...],
        filters: DocumentReportFilters,
        limit: int,
        cursor: str | None,
    ) -> ReportQueryPage:
        _validate_limit(limit)
        field_names = _validated_field_names(fields, DocumentReportField)
        fingerprint = _query_fingerprint(
            report_type=ReportType.MISSING_DOCUMENTS,
            authorization=authorization,
            fields=field_names,
            filters=filters.model_dump(mode="json"),
            effective_on=self.today,
        )
        cursor_values = _document_cursor(cursor, fingerprint=fingerprint)
        statement = _document_statement(
            tenant_id=tenant_id,
            authorization=authorization,
            fields=field_names,
            filters=filters,
            effective_on=self.today,
            expiring_on=self.today + timedelta(days=self.document_expiring_days),
        )
        if cursor_values is not None:
            employee_id, document_type_id = cursor_values
            statement = statement.where(
                or_(
                    Employee.id > employee_id,
                    and_(Employee.id == employee_id, DocumentType.id > document_type_id),
                )
            )
        rows = (
            await self.session.execute(
                statement.order_by(Employee.id.asc(), DocumentType.id.asc()).limit(limit + 1)
            )
        ).mappings().all()
        visible = rows[:limit]
        items = [DocumentReportRow(values=_public_values(row, field_names)) for row in visible]
        next_cursor = None
        if len(rows) > limit:
            last = visible[-1]
            next_cursor = encode_cursor(
                "report_missing_documents",
                {
                    "employee_id": str(last["_cursor_employee_id"]),
                    "document_type_id": str(last["_cursor_document_type_id"]),
                    "fingerprint": fingerprint,
                },
            )
        return ReportQueryPage(items=items, next_cursor=next_cursor)

    async def page_for_export(
        self,
        *,
        report_type: ReportType,
        tenant_id: UUID,
        authorization: ReportAuthorization,
        fields: tuple[str, ...],
        filters: dict[str, Any],
        limit: int,
        cursor: str | None,
    ) -> ReportQueryPage:
        if report_type is ReportType.EMPLOYEES:
            return await self.employee_report(
                tenant_id=tenant_id,
                authorization=authorization,
                fields=fields,
                filters=EmployeeReportFilters.model_validate(filters),
                limit=limit,
                cursor=cursor,
            )
        if report_type is ReportType.LEAVES:
            return await self.leave_report(
                tenant_id=tenant_id,
                authorization=authorization,
                fields=fields,
                filters=LeaveReportFilters.model_validate(filters),
                limit=limit,
                cursor=cursor,
            )
        if report_type is ReportType.MISSING_DOCUMENTS:
            return await self.document_report(
                tenant_id=tenant_id,
                authorization=authorization,
                fields=fields,
                filters=DocumentReportFilters.model_validate(filters),
                limit=limit,
                cursor=cursor,
            )
        raise ReportingValidationError()


def _employee_statement(
    *,
    tenant_id: UUID,
    authorization: ReportAuthorization,
    fields: tuple[str, ...],
    filters: EmployeeReportFilters,
    effective_on: date,
) -> Select[Any]:
    columns: dict[str, Any] = {
        EmployeeReportField.EMPLOYEE_NUMBER.value: Employee.employee_number,
        EmployeeReportField.FIRST_NAME.value: Employee.first_name,
        EmployeeReportField.LAST_NAME.value: Employee.last_name,
        EmployeeReportField.WORK_EMAIL.value: Employee.email,
        EmployeeReportField.EMPLOYMENT_STATUS.value: Employee.status,
        EmployeeReportField.EMPLOYMENT_START_DATE.value: Employee.employment_start_date,
        EmployeeReportField.EMPLOYMENT_END_DATE.value: Employee.employment_end_date,
        EmployeeReportField.LEGAL_ENTITY.value: LegalEntity.name,
        EmployeeReportField.BRANCH.value: Branch.name,
        EmployeeReportField.DEPARTMENT.value: Department.name,
        EmployeeReportField.POSITION.value: Position.title,
    }
    statement = (
        select(Employee.id.label("_cursor_id"), *(columns[field].label(field) for field in fields))
        .select_from(Employee)
        .outerjoin(
            EmployeeAssignment,
            and_(
                EmployeeAssignment.tenant_id == Employee.tenant_id,
                EmployeeAssignment.employee_id == Employee.id,
                _assignment_effective_on(effective_on),
            ),
        )
        .outerjoin(
            LegalEntity,
            and_(
                LegalEntity.tenant_id == EmployeeAssignment.tenant_id,
                LegalEntity.id == EmployeeAssignment.legal_entity_id,
            ),
        )
        .outerjoin(
            Branch,
            and_(
                Branch.tenant_id == EmployeeAssignment.tenant_id,
                Branch.id == EmployeeAssignment.branch_id,
            ),
        )
        .outerjoin(
            Department,
            and_(
                Department.tenant_id == EmployeeAssignment.tenant_id,
                Department.id == EmployeeAssignment.department_id,
            ),
        )
        .outerjoin(
            Position,
            and_(
                Position.tenant_id == EmployeeAssignment.tenant_id,
                Position.id == EmployeeAssignment.position_id,
            ),
        )
        .where(Employee.tenant_id == tenant_id, Employee.archived_at.is_(None))
    )
    statement = _apply_employee_scope(statement, authorization)
    if filters.status is not None:
        statement = statement.where(Employee.status == filters.status)
    if filters.employment_start_from is not None:
        statement = statement.where(
            Employee.employment_start_date >= filters.employment_start_from
        )
    if filters.employment_start_to is not None:
        statement = statement.where(Employee.employment_start_date <= filters.employment_start_to)
    if filters.q is not None:
        pattern = f"%{_escape_like(filters.q.casefold())}%"
        statement = statement.where(
            or_(
                func.lower(Employee.employee_number).like(pattern, escape="\\"),
                Employee.full_name_normalized.like(pattern, escape="\\"),
            )
        )
    for value, column in (
        (filters.legal_entity_code, LegalEntity.code_normalized),
        (filters.branch_code, Branch.code_normalized),
        (filters.department_code, Department.code_normalized),
        (filters.position_code, Position.code_normalized),
    ):
        if value is not None:
            statement = statement.where(column == value.casefold())
    return statement


def _leave_statement(
    *,
    tenant_id: UUID,
    authorization: ReportAuthorization,
    fields: tuple[str, ...],
    filters: LeaveReportFilters,
    effective_on: date,
) -> Select[Any]:
    columns: dict[str, Any] = {
        LeaveReportField.EMPLOYEE_NUMBER.value: Employee.employee_number,
        LeaveReportField.EMPLOYEE_NAME.value: func.concat(
            Employee.first_name,
            " ",
            Employee.last_name,
        ),
        LeaveReportField.LEAVE_TYPE.value: LeaveType.name,
        LeaveReportField.START_DATE.value: LeaveRequest.start_date,
        LeaveReportField.END_DATE.value: LeaveRequest.end_date,
        LeaveReportField.COUNTED_DAYS.value: LeaveRequest.counted_days,
        LeaveReportField.STATUS.value: LeaveRequest.status,
        LeaveReportField.SUBMITTED_AT.value: LeaveRequest.created_at,
        LeaveReportField.DECIDED_AT.value: LeaveRequest.decided_at,
    }
    statement = (
        select(
            LeaveRequest.id.label("_cursor_id"),
            LeaveRequest.created_at.label("_cursor_created_at"),
            *(columns[field].label(field) for field in fields),
        )
        .select_from(LeaveRequest)
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
        .where(LeaveRequest.tenant_id == tenant_id, Employee.archived_at.is_(None))
    )
    if authorization.scope is ReportScope.TEAM:
        statement = statement.where(
            _employee_in_team(
                tenant_id=tenant_id,
                employee_id=LeaveRequest.employee_id,
                manager_user_id=_required_scope_user(authorization),
                effective_on=effective_on,
            )
        )
    if filters.status is not None:
        statement = statement.where(LeaveRequest.status == filters.status)
    if filters.start_from is not None:
        statement = statement.where(LeaveRequest.start_date >= filters.start_from)
    if filters.start_to is not None:
        statement = statement.where(LeaveRequest.start_date <= filters.start_to)
    if filters.leave_type_code is not None:
        statement = statement.where(LeaveType.code == filters.leave_type_code.casefold())
    return statement


def _document_statement(
    *,
    tenant_id: UUID,
    authorization: ReportAuthorization,
    fields: tuple[str, ...],
    filters: DocumentReportFilters,
    effective_on: date,
    expiring_on: date,
) -> Select[Any]:
    best_document_id = (
        select(EmployeeDocument.id)
        .where(
            EmployeeDocument.tenant_id == tenant_id,
            EmployeeDocument.employee_id == Employee.id,
            EmployeeDocument.document_type_id == DocumentType.id,
            EmployeeDocument.archived_at.is_(None),
            EmployeeDocument.processing_state == DocumentProcessingState.AVAILABLE.value,
        )
        .order_by(
            EmployeeDocument.expires_on.desc().nulls_first(),
            EmployeeDocument.created_at.desc(),
            EmployeeDocument.id.desc(),
        )
        .limit(1)
        .correlate(Employee, DocumentType)
        .scalar_subquery()
    )
    best_expiry = (
        select(EmployeeDocument.expires_on)
        .where(EmployeeDocument.id == best_document_id)
        .correlate(Employee, DocumentType)
        .scalar_subquery()
    )
    checklist_status = case(
        (best_document_id.is_(None), literal(DocumentChecklistReportStatus.MISSING.value)),
        (best_expiry < effective_on, literal(DocumentChecklistReportStatus.EXPIRED.value)),
        (best_expiry <= expiring_on, literal(DocumentChecklistReportStatus.EXPIRING.value)),
        else_=literal("complete"),
    )
    columns: dict[str, Any] = {
        DocumentReportField.EMPLOYEE_NUMBER.value: Employee.employee_number,
        DocumentReportField.EMPLOYEE_NAME.value: func.concat(
            Employee.first_name,
            " ",
            Employee.last_name,
        ),
        DocumentReportField.DOCUMENT_TYPE_CODE.value: DocumentType.code,
        DocumentReportField.DOCUMENT_TYPE_NAME.value: DocumentType.name,
        DocumentReportField.CHECKLIST_STATUS.value: checklist_status,
        DocumentReportField.EXPIRES_ON.value: best_expiry,
    }
    statement = (
        select(
            Employee.id.label("_cursor_employee_id"),
            DocumentType.id.label("_cursor_document_type_id"),
            *(columns[field].label(field) for field in fields),
        )
        .select_from(Employee)
        .join(DocumentType, DocumentType.tenant_id == Employee.tenant_id)
        .where(
            Employee.tenant_id == tenant_id,
            Employee.archived_at.is_(None),
            Employee.status.in_(_CURRENT_STATUSES),
            DocumentType.required.is_(True),
            DocumentType.archived_at.is_(None),
            checklist_status.in_([status.value for status in filters.statuses]),
        )
    )
    if authorization.scope is ReportScope.TEAM:
        statement = statement.where(
            _employee_in_team(
                tenant_id=tenant_id,
                employee_id=Employee.id,
                manager_user_id=_required_scope_user(authorization),
                effective_on=effective_on,
            )
        )
    if filters.document_type_code is not None:
        statement = statement.where(DocumentType.code == filters.document_type_code.casefold())
    if filters.expires_before is not None:
        statement = statement.where(best_expiry.is_not(None), best_expiry <= filters.expires_before)
    return statement


def _apply_employee_scope(
    statement: Select[Any], authorization: ReportAuthorization
) -> Select[Any]:
    if authorization.scope is ReportScope.TEAM:
        return statement.where(
            EmployeeAssignment.manager_user_id == _required_scope_user(authorization)
        )
    return statement


def _employee_in_team(
    *, tenant_id: UUID, employee_id: Any, manager_user_id: UUID, effective_on: date
) -> Any:
    return exists(
        select(EmployeeAssignment.id).where(
            EmployeeAssignment.tenant_id == tenant_id,
            EmployeeAssignment.employee_id == employee_id,
            EmployeeAssignment.manager_user_id == manager_user_id,
            EmployeeAssignment.effective_from <= effective_on,
            or_(
                EmployeeAssignment.effective_to.is_(None),
                EmployeeAssignment.effective_to > effective_on,
            ),
        )
    )


def _assignment_effective_on(effective_on: date) -> Any:
    return and_(
        EmployeeAssignment.effective_from <= effective_on,
        or_(
            EmployeeAssignment.effective_to.is_(None),
            EmployeeAssignment.effective_to > effective_on,
        ),
    )


def _required_scope_user(authorization: ReportAuthorization) -> UUID:
    if authorization.scope_user_id is None:
        raise ReportingValidationError()
    return authorization.scope_user_id


def _public_values(row: Any, fields: tuple[str, ...]) -> dict[str, Any]:
    return {field: row[field] for field in fields}


def _validated_field_names(fields: tuple[str, ...], enum_type: type[Any]) -> tuple[str, ...]:
    allowed = {field.value for field in enum_type}
    if not fields or len(set(fields)) != len(fields) or not set(fields) <= allowed:
        raise ReportingValidationError()
    return fields


def _query_fingerprint(
    *,
    report_type: ReportType,
    authorization: ReportAuthorization,
    fields: tuple[str, ...],
    filters: dict[str, Any],
    effective_on: date,
) -> str:
    payload = {
        "report_type": report_type.value,
        "scope": authorization.scope.value,
        "scope_user_id": str(authorization.scope_user_id) if authorization.scope_user_id else None,
        "fields": fields,
        "filters": filters,
        "effective_on": effective_on.isoformat(),
    }
    return sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()


def _id_cursor(cursor: str | None, *, resource: str, fingerprint: str) -> UUID | None:
    if cursor is None:
        return None
    try:
        values = decode_cursor(cursor, expected_resource=resource)
    except InvalidCursorError as exc:
        raise ReportingValidationError() from exc
    if set(values) != {"id", "fingerprint"} or values["fingerprint"] != fingerprint:
        raise ReportingValidationError()
    try:
        return UUID(values["id"])
    except ValueError as exc:
        raise ReportingValidationError() from exc


def _dated_cursor(
    cursor: str | None, *, resource: str, fingerprint: str
) -> tuple[datetime, UUID] | None:
    if cursor is None:
        return None
    try:
        values = decode_cursor(cursor, expected_resource=resource)
    except InvalidCursorError as exc:
        raise ReportingValidationError() from exc
    if set(values) != {"created_at", "id", "fingerprint"}:
        raise ReportingValidationError()
    if values["fingerprint"] != fingerprint:
        raise ReportingValidationError()
    try:
        created_at = datetime.fromisoformat(values["created_at"])
        cursor_id = UUID(values["id"])
    except ValueError as exc:
        raise ReportingValidationError() from exc
    if created_at.tzinfo is None:
        raise ReportingValidationError()
    return created_at, cursor_id


def _document_cursor(cursor: str | None, *, fingerprint: str) -> tuple[UUID, UUID] | None:
    if cursor is None:
        return None
    try:
        values = decode_cursor(cursor, expected_resource="report_missing_documents")
    except InvalidCursorError as exc:
        raise ReportingValidationError() from exc
    if set(values) != {"employee_id", "document_type_id", "fingerprint"}:
        raise ReportingValidationError()
    if values["fingerprint"] != fingerprint:
        raise ReportingValidationError()
    try:
        return UUID(values["employee_id"]), UUID(values["document_type_id"])
    except ValueError as exc:
        raise ReportingValidationError() from exc


def _validate_limit(limit: int) -> None:
    if not 1 <= limit <= 500:
        raise ReportingValidationError()


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


__all__ = ["ReportQueryPage", "ReportService"]
