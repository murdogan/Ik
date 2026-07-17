"""Closed report, export, and role-aware dashboard-adjacent contracts."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from app.models.reporting import ExportFormat, ExportJobStatus, ReportScope, ReportType
from app.platform.request_context import RequestContext

REPORT_DEFAULT_LIMIT = 50
REPORT_MAX_LIMIT = 200
EXPORT_MAX_ROWS = 10_000


class EmployeeReportField(StrEnum):
    EMPLOYEE_NUMBER = "employee_number"
    FIRST_NAME = "first_name"
    LAST_NAME = "last_name"
    WORK_EMAIL = "work_email"
    EMPLOYMENT_STATUS = "employment_status"
    EMPLOYMENT_START_DATE = "employment_start_date"
    EMPLOYMENT_END_DATE = "employment_end_date"
    LEGAL_ENTITY = "legal_entity"
    BRANCH = "branch"
    DEPARTMENT = "department"
    POSITION = "position"


class LeaveReportField(StrEnum):
    EMPLOYEE_NUMBER = "employee_number"
    EMPLOYEE_NAME = "employee_name"
    LEAVE_TYPE = "leave_type"
    START_DATE = "start_date"
    END_DATE = "end_date"
    COUNTED_DAYS = "counted_days"
    STATUS = "status"
    SUBMITTED_AT = "submitted_at"
    DECIDED_AT = "decided_at"


class DocumentReportField(StrEnum):
    EMPLOYEE_NUMBER = "employee_number"
    EMPLOYEE_NAME = "employee_name"
    DOCUMENT_TYPE_CODE = "document_type_code"
    DOCUMENT_TYPE_NAME = "document_type_name"
    CHECKLIST_STATUS = "checklist_status"
    EXPIRES_ON = "expires_on"


class DocumentChecklistReportStatus(StrEnum):
    MISSING = "missing"
    EXPIRING = "expiring"
    EXPIRED = "expired"


ReportValue = (
    Annotated[str, Field(max_length=32_767)]
    | int
    | Decimal
    | date
    | datetime
    | None
)


class EmployeeReportRow(BaseModel):
    model_config = ConfigDict(extra="forbid")
    values: dict[EmployeeReportField, ReportValue]


class LeaveReportRow(BaseModel):
    model_config = ConfigDict(extra="forbid")
    values: dict[LeaveReportField, ReportValue]


class DocumentReportRow(BaseModel):
    model_config = ConfigDict(extra="forbid")
    values: dict[DocumentReportField, ReportValue]


class EmployeeReportFilters(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    q: str | None = Field(default=None, min_length=1, max_length=200)
    status: Literal["active", "on_leave", "terminated"] | None = None
    employment_start_from: date | None = None
    employment_start_to: date | None = None
    legal_entity_code: str | None = Field(default=None, min_length=1, max_length=32)
    branch_code: str | None = Field(default=None, min_length=1, max_length=32)
    department_code: str | None = Field(default=None, min_length=1, max_length=32)
    position_code: str | None = Field(default=None, min_length=1, max_length=32)

    @model_validator(mode="after")
    def validate_window(self) -> Self:
        if (
            self.employment_start_from is not None
            and self.employment_start_to is not None
            and self.employment_start_to < self.employment_start_from
        ):
            raise ValueError("employment_start_to must be on or after employment_start_from")
        return self


class LeaveReportFilters(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    status: Literal["pending", "approved", "rejected", "cancelled"] | None = None
    start_from: date | None = None
    start_to: date | None = None
    leave_type_code: str | None = Field(default=None, min_length=1, max_length=64)

    @model_validator(mode="after")
    def validate_window(self) -> Self:
        if self.start_from is not None and self.start_to is not None:
            if self.start_to < self.start_from:
                raise ValueError("start_to must be on or after start_from")
        return self


class DocumentReportFilters(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    statuses: list[DocumentChecklistReportStatus] = Field(
        default_factory=lambda: [
            DocumentChecklistReportStatus.MISSING,
            DocumentChecklistReportStatus.EXPIRING,
            DocumentChecklistReportStatus.EXPIRED,
        ],
        min_length=1,
        max_length=3,
    )
    document_type_code: str | None = Field(default=None, min_length=1, max_length=64)
    expires_before: date | None = None

    @model_validator(mode="after")
    def reject_duplicate_statuses(self) -> Self:
        if len(set(self.statuses)) != len(self.statuses):
            raise ValueError("Document statuses must be unique")
        return self


class ReportPageMeta(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    request_id: str
    trace_id: str
    correlation_id: str
    limit: int = Field(ge=1, le=REPORT_MAX_LIMIT)
    next_cursor: str | None
    scope: ReportScope
    fields: list[str]

    @classmethod
    def from_context(
        cls,
        context: RequestContext,
        *,
        limit: int,
        next_cursor: str | None,
        scope: ReportScope,
        fields: list[str],
    ) -> ReportPageMeta:
        return cls(
            request_id=context.request_id,
            trace_id=context.trace_id,
            correlation_id=context.request_id,
            limit=limit,
            next_cursor=next_cursor,
            scope=scope,
            fields=fields,
        )


class EmployeeReportEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid")
    data: list[EmployeeReportRow]
    meta: ReportPageMeta


class LeaveReportEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid")
    data: list[LeaveReportRow]
    meta: ReportPageMeta


class DocumentReportEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid")
    data: list[DocumentReportRow]
    meta: ReportPageMeta


class _ExportCreateBase(BaseModel):
    model_config = ConfigDict(extra="forbid")
    format: ExportFormat

    @staticmethod
    def _unique_fields(fields: list[StrEnum]) -> list[StrEnum]:
        if len(set(fields)) != len(fields):
            raise ValueError("Export fields must be unique")
        return fields


class EmployeeExportCreate(_ExportCreateBase):
    report_type: Literal[ReportType.EMPLOYEES] = ReportType.EMPLOYEES
    fields: list[EmployeeReportField] = Field(min_length=1, max_length=11)
    filters: EmployeeReportFilters = Field(default_factory=EmployeeReportFilters)

    @model_validator(mode="after")
    def validate_fields(self) -> Self:
        self._unique_fields(self.fields)
        return self


class LeaveExportCreate(_ExportCreateBase):
    report_type: Literal[ReportType.LEAVES] = ReportType.LEAVES
    fields: list[LeaveReportField] = Field(min_length=1, max_length=9)
    filters: LeaveReportFilters = Field(default_factory=LeaveReportFilters)

    @model_validator(mode="after")
    def validate_fields(self) -> Self:
        self._unique_fields(self.fields)
        return self


class DocumentExportCreate(_ExportCreateBase):
    report_type: Literal[ReportType.MISSING_DOCUMENTS] = ReportType.MISSING_DOCUMENTS
    fields: list[DocumentReportField] = Field(min_length=1, max_length=6)
    filters: DocumentReportFilters = Field(default_factory=DocumentReportFilters)

    @model_validator(mode="after")
    def validate_fields(self) -> Self:
        self._unique_fields(self.fields)
        return self


ExportJobCreate = Annotated[
    EmployeeExportCreate | LeaveExportCreate | DocumentExportCreate,
    Field(discriminator="report_type"),
]


class ExportJobRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    report_type: ReportType
    format: ExportFormat
    status: ExportJobStatus
    request_scope: ReportScope
    fields: list[str]
    generated_scope: ReportScope | None
    generated_fields: list[str] | None
    field_classifications: list[str] | None
    row_count: int | None = Field(default=None, ge=0, le=EXPORT_MAX_ROWS)
    size_bytes: int | None = Field(default=None, ge=1)
    sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    failure_code: str | None
    cancel_requested: bool
    download_intents_remaining: int = Field(ge=0, le=3)
    available_at: AwareDatetime | None
    expires_at: AwareDatetime | None
    created_at: AwareDatetime
    updated_at: AwareDatetime


class ExportDownloadIntentRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    export_job_id: UUID
    method: Literal["GET"] = "GET"
    url: str = Field(min_length=1, max_length=4096)
    expires_at: AwareDatetime


__all__ = [
    "DocumentChecklistReportStatus",
    "DocumentExportCreate",
    "DocumentReportEnvelope",
    "DocumentReportField",
    "DocumentReportFilters",
    "DocumentReportRow",
    "EmployeeExportCreate",
    "EmployeeReportEnvelope",
    "EmployeeReportField",
    "EmployeeReportFilters",
    "EmployeeReportRow",
    "ExportDownloadIntentRead",
    "ExportJobCreate",
    "ExportJobRead",
    "LeaveExportCreate",
    "LeaveReportEnvelope",
    "LeaveReportField",
    "LeaveReportFilters",
    "LeaveReportRow",
    "REPORT_DEFAULT_LIMIT",
    "REPORT_MAX_LIMIT",
    "ReportPageMeta",
]
