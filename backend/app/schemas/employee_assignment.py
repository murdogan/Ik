"""Public contracts for effective-dated employee assignments and manager teams."""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.department import DepartmentStatus
from app.models.employee import EmployeeStatus
from app.models.organization import BranchStatus, LegalEntityStatus
from app.models.position import PositionStatus
from app.models.user import UserStatus
from app.platform.pagination import decode_cursor, encode_cursor
from app.schemas.date_fields import DateOnly

ASSIGNMENT_LIST_DEFAULT_LIMIT = 50
ASSIGNMENT_LIST_MAX_LIMIT = 100
ASSIGNMENT_OPTIONS_DEFAULT_LIMIT = 100
ASSIGNMENT_OPTIONS_MAX_LIMIT = 200


class _AssignmentPayload(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class EmployeeAssignmentCreate(_AssignmentPayload):
    employee_id: UUID
    legal_entity_id: UUID
    branch_id: UUID
    department_id: UUID
    position_id: UUID
    manager_id: UUID | None = None
    effective_from: DateOnly
    change_reason: str | None = Field(default=None, min_length=1, max_length=500)


class EmployeeAssignmentChange(_AssignmentPayload):
    legal_entity_id: UUID | None = None
    branch_id: UUID | None = None
    department_id: UUID | None = None
    position_id: UUID | None = None
    manager_id: UUID | None = None
    effective_from: DateOnly
    change_reason: str = Field(min_length=1, max_length=500)

    @model_validator(mode="after")
    def require_structural_change(self) -> Self:
        structural_fields = {
            "legal_entity_id",
            "branch_id",
            "department_id",
            "position_id",
            "manager_id",
        }
        if not (self.model_fields_set & structural_fields):
            raise ValueError("At least one assignment field must be provided")
        for field_name in self.model_fields_set & (structural_fields - {"manager_id"}):
            if getattr(self, field_name) is None:
                raise ValueError(f"{field_name} cannot be null")
        return self


class AssignmentEmployeeRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    employee_number: str
    first_name: str
    last_name: str
    email: str | None
    status: EmployeeStatus


class AssignmentLegalEntityRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    code: str
    name: str
    status: LegalEntityStatus


class AssignmentBranchRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    code: str
    name: str
    status: BranchStatus


class AssignmentDepartmentRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    code: str
    name: str
    status: DepartmentStatus


class AssignmentPositionRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    code: str
    title: str
    status: PositionStatus


class AssignmentManagerRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    full_name: str
    email: str
    status: UserStatus


class EmployeeAssignmentRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    employee: AssignmentEmployeeRead
    legal_entity: AssignmentLegalEntityRead
    branch: AssignmentBranchRead
    department: AssignmentDepartmentRead
    position: AssignmentPositionRead
    manager: AssignmentManagerRead | None
    effective_from: DateOnly
    effective_to: DateOnly | None
    supersedes_assignment_id: UUID | None
    change_reason: str | None
    is_current: bool
    created_at: datetime
    updated_at: datetime


class AssignmentEmployeeOptionRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    employee_number: str
    full_name: str
    email: str | None
    status: EmployeeStatus
    current_assignment_id: UUID | None


class AssignmentManagerOptionRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    full_name: str
    email: str


class EmployeeAssignmentOptionsRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    employees: list[AssignmentEmployeeOptionRead]
    managers: list[AssignmentManagerOptionRead]


class TeamMemberRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    employee: AssignmentEmployeeRead
    assignment: EmployeeAssignmentRead


class ManagerTeamEmployeeRead(BaseModel):
    """Minimal work identity exposed inside the derived manager boundary."""

    model_config = ConfigDict(extra="forbid")

    id: UUID
    employee_number: str
    first_name: str
    last_name: str
    preferred_name: str | None
    email: str | None
    status: EmployeeStatus


class ManagerTeamOrganizationReferenceRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str
    name: str


class ManagerTeamPositionReferenceRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str
    title: str


class ManagerTeamAssignmentRead(BaseModel):
    """Current work-safe assignment without operational or identity identifiers."""

    model_config = ConfigDict(extra="forbid")

    legal_entity: ManagerTeamOrganizationReferenceRead
    branch: ManagerTeamOrganizationReferenceRead
    department: ManagerTeamOrganizationReferenceRead
    position: ManagerTeamPositionReferenceRead
    effective_from: DateOnly


class ManagerTeamMemberRead(BaseModel):
    """Work-safe direct-team list item for manager-facing consumers."""

    model_config = ConfigDict(extra="forbid")

    employee: ManagerTeamEmployeeRead
    assignment: ManagerTeamAssignmentRead


class ManagerTeamManagerRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    full_name: str


class ManagerTeamCurrentAssignmentRead(ManagerTeamAssignmentRead):
    manager: ManagerTeamManagerRead | None


class ManagerTeamEmploymentRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    employment_start_date: DateOnly
    contract_type: Literal["indefinite", "fixed_term"] | None
    work_type: Literal["full_time", "part_time"] | None


class ManagerTeamOrganizationRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    current_assignment: ManagerTeamCurrentAssignmentRead | None


class ManagerTeamMemberProfileRead(BaseModel):
    """Dedicated direct-report projection; personal contact is structurally absent."""

    model_config = ConfigDict(extra="forbid")

    core: ManagerTeamEmployeeRead
    employment: ManagerTeamEmploymentRead
    organization: ManagerTeamOrganizationRead


class EmployeeAssignmentListCursor(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    employee_number: str = Field(min_length=1, max_length=64)
    effective_from: date
    id: UUID
    employee_id: str = ""
    include_history: str = "false"

    @classmethod
    def from_token(cls, token: str) -> Self:
        values = decode_cursor(token, expected_resource="employee_assignments")
        if set(values) != {
            "employee_number",
            "effective_from",
            "id",
            "employee_id",
            "include_history",
        }:
            raise ValueError("Invalid employee-assignment cursor fields")
        return cls.model_validate(values)

    def to_token(self) -> str:
        return encode_cursor("employee_assignments", self.model_dump(mode="json"))


class EmployeeAssignmentListPagination(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    limit: int = Field(
        default=ASSIGNMENT_LIST_DEFAULT_LIMIT,
        ge=1,
        le=ASSIGNMENT_LIST_MAX_LIMIT,
    )
    cursor: EmployeeAssignmentListCursor | None = None
    employee_id: UUID | None = None
    include_history: bool = False

    def cursor_matches_filters(self) -> bool:
        if self.cursor is None:
            return True
        return (
            self.cursor.employee_id
            == (str(self.employee_id) if self.employee_id is not None else "")
            and self.cursor.include_history == str(self.include_history).lower()
        )

    def next_cursor(
        self,
        *,
        employee_number: str,
        effective_from: date,
        assignment_id: UUID,
    ) -> str:
        return EmployeeAssignmentListCursor(
            employee_number=employee_number,
            effective_from=effective_from,
            id=assignment_id,
            employee_id=str(self.employee_id) if self.employee_id is not None else "",
            include_history=str(self.include_history).lower(),
        ).to_token()


class TeamListCursor(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    employee_number: str = Field(min_length=1, max_length=64)
    id: UUID

    @classmethod
    def from_token(cls, token: str) -> Self:
        return cls.model_validate(decode_cursor(token, expected_resource="manager_team"))

    def to_token(self) -> str:
        return encode_cursor("manager_team", self.model_dump(mode="json"))


class TeamListPagination(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    limit: int = Field(
        default=ASSIGNMENT_LIST_DEFAULT_LIMIT,
        ge=1,
        le=ASSIGNMENT_LIST_MAX_LIMIT,
    )
    cursor: TeamListCursor | None = None


__all__ = [
    "ASSIGNMENT_LIST_DEFAULT_LIMIT",
    "ASSIGNMENT_LIST_MAX_LIMIT",
    "ASSIGNMENT_OPTIONS_DEFAULT_LIMIT",
    "ASSIGNMENT_OPTIONS_MAX_LIMIT",
    "AssignmentBranchRead",
    "AssignmentDepartmentRead",
    "AssignmentEmployeeOptionRead",
    "AssignmentEmployeeRead",
    "AssignmentLegalEntityRead",
    "AssignmentManagerOptionRead",
    "AssignmentManagerRead",
    "AssignmentPositionRead",
    "EmployeeAssignmentChange",
    "EmployeeAssignmentCreate",
    "EmployeeAssignmentListCursor",
    "EmployeeAssignmentListPagination",
    "EmployeeAssignmentOptionsRead",
    "EmployeeAssignmentRead",
    "ManagerTeamAssignmentRead",
    "ManagerTeamCurrentAssignmentRead",
    "ManagerTeamEmployeeRead",
    "ManagerTeamEmploymentRead",
    "ManagerTeamManagerRead",
    "ManagerTeamMemberRead",
    "ManagerTeamMemberProfileRead",
    "ManagerTeamOrganizationRead",
    "ManagerTeamOrganizationReferenceRead",
    "ManagerTeamPositionReferenceRead",
    "TeamListCursor",
    "TeamListPagination",
    "TeamMemberRead",
]
