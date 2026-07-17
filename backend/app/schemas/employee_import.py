"""Versioned employee import upload, validation issue, and commit contracts."""

from __future__ import annotations

from enum import StrEnum
from typing import Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from app.models.employee_import import EmployeeImportScanResult, EmployeeImportStatus

EMPLOYEE_IMPORT_TEMPLATE_VERSION = "1"
EMPLOYEE_IMPORT_MAX_BYTES = 10 * 1024 * 1024
EMPLOYEE_IMPORT_MAX_REQUEST_BYTES = EMPLOYEE_IMPORT_MAX_BYTES + 1024 * 1024
EMPLOYEE_IMPORT_MAX_ROWS = 10_000
EMPLOYEE_IMPORT_ISSUE_DEFAULT_LIMIT = 100
EMPLOYEE_IMPORT_ISSUE_MAX_LIMIT = 200
EMPLOYEE_IMPORT_FIELDS = (
    "employee_number",
    "first_name",
    "last_name",
    "work_email",
    "status",
    "employment_start_date",
    "employment_end_date",
    "legal_entity_code",
    "branch_code",
    "department_code",
    "position_code",
)
EMPLOYEE_IMPORT_ISSUE_MESSAGES = {
    "duplicate_employee_number_file": "Employee number is duplicated in this file.",
    "duplicate_employee_number_tenant": "Employee number is already in use.",
    "duplicate_work_email_file": "Work email is duplicated in this file.",
    "duplicate_work_email_tenant": "Work email is already in use.",
    "empty_file": "The file contains no employee rows.",
    "employment_end_date_not_supported": (
        "Employment end date must be blank in template version 1."
    ),
    "formula_not_allowed": "Spreadsheet formulas are not accepted in import fields.",
    "future_start_date": "Employment starts in the future.",
    "inactive_reference": "The organization reference is inactive.",
    "infected_file": "The uploaded file did not pass malware scanning.",
    "invalid_date": "Use an ISO date in YYYY-MM-DD format.",
    "invalid_date_order": "Employment end date cannot precede the start date.",
    "invalid_email": "Work email format is invalid.",
    "invalid_file": "The uploaded file cannot be processed.",
    "invalid_headers": "The template headers or version are invalid.",
    "invalid_reference": "The organization code was not found.",
    "invalid_row_shape": "The row does not match the versioned template.",
    "invalid_status": "Status must be active or on_leave.",
    "reference_mismatch": "The branch does not belong to the selected legal entity.",
    "required": "This field is required.",
    "row_limit_exceeded": "The file exceeds the 10,000-row limit.",
    "value_too_long": "The field exceeds its maximum length.",
}


class EmployeeImportIssueSeverity(StrEnum):
    ERROR = "error"
    WARNING = "warning"


class EmployeeImportIssueRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    row_number: int = Field(ge=1, le=EMPLOYEE_IMPORT_MAX_ROWS + 1)
    severity: EmployeeImportIssueSeverity
    code: str = Field(min_length=1, max_length=64)
    field: str | None = Field(default=None, max_length=64)
    message: str = Field(min_length=1, max_length=240)


class EmployeeImportRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    status: EmployeeImportStatus
    template_version: Literal["1"]
    file_format: Literal["csv", "xlsx"]
    scan_result: EmployeeImportScanResult
    row_count: int = Field(ge=0, le=EMPLOYEE_IMPORT_MAX_ROWS)
    error_count: int = Field(ge=0)
    warning_count: int = Field(ge=0)
    committed_count: int = Field(ge=0, le=EMPLOYEE_IMPORT_MAX_ROWS)
    failure_code: str | None
    issues: list[EmployeeImportIssueRead]
    issues_next_cursor: str | None
    validated_at: AwareDatetime | None
    committed_at: AwareDatetime | None
    expires_at: AwareDatetime
    created_at: AwareDatetime
    updated_at: AwareDatetime


class EmployeeImportCommitRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    status: Literal[EmployeeImportStatus.SUCCEEDED]
    committed_count: int = Field(ge=0, le=EMPLOYEE_IMPORT_MAX_ROWS)
    committed_at: AwareDatetime


__all__ = [
    "EMPLOYEE_IMPORT_FIELDS",
    "EMPLOYEE_IMPORT_ISSUE_DEFAULT_LIMIT",
    "EMPLOYEE_IMPORT_ISSUE_MAX_LIMIT",
    "EMPLOYEE_IMPORT_ISSUE_MESSAGES",
    "EMPLOYEE_IMPORT_MAX_BYTES",
    "EMPLOYEE_IMPORT_MAX_REQUEST_BYTES",
    "EMPLOYEE_IMPORT_MAX_ROWS",
    "EMPLOYEE_IMPORT_TEMPLATE_VERSION",
    "EmployeeImportCommitRead",
    "EmployeeImportIssueRead",
    "EmployeeImportIssueSeverity",
    "EmployeeImportRead",
]
