"""Bounded lazy organization-chart read contracts."""

from __future__ import annotations

from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StrictStr, StringConstraints

from app.models.employee import EmployeeStatus
from app.models.user import UserStatus
from app.platform.pagination import decode_cursor, encode_cursor
from app.schemas.employee_assignment import (
    AssignmentBranchRead,
    AssignmentDepartmentRead,
    AssignmentLegalEntityRead,
    AssignmentPositionRead,
)

ORG_CHART_DEFAULT_LIMIT = 25
ORG_CHART_MAX_LIMIT = 100


class OrgChartNodeRead(BaseModel):
    """One reporting node with all labels needed to render it without follow-up reads."""

    model_config = ConfigDict(extra="forbid")

    id: UUID
    node_type: Literal["employee", "manager"]
    employee_id: UUID | None
    user_id: UUID | None
    parent_user_id: UUID | None
    assignment_id: UUID | None
    full_name: str
    email: str | None
    employee_number: str | None
    employee_status: EmployeeStatus | None
    user_status: UserStatus | None
    legal_entity: AssignmentLegalEntityRead | None
    branch: AssignmentBranchRead | None
    department: AssignmentDepartmentRead | None
    position: AssignmentPositionRead | None
    has_children: bool
    has_archived_reference: bool


class OrgChartCursor(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    node_type: Literal["employee", "manager"]
    id: UUID
    parent_id: Annotated[StrictStr, StringConstraints(max_length=36)] = ""

    @classmethod
    def from_token(cls, token: str) -> Self:
        values = decode_cursor(token, expected_resource="org_chart")
        if set(values) != {"node_type", "id", "parent_id"}:
            raise ValueError("Invalid organization-chart cursor fields")
        return cls.model_validate(values)

    def to_token(self) -> str:
        return encode_cursor("org_chart", self.model_dump(mode="json"))


class OrgChartPagination(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    limit: int = Field(default=ORG_CHART_DEFAULT_LIMIT, ge=1, le=ORG_CHART_MAX_LIMIT)
    cursor: OrgChartCursor | None = None
    parent_id: UUID | None = None

    def cursor_matches_level(self) -> bool:
        if self.cursor is None:
            return True
        if self.parent_id is not None and self.cursor.node_type != "employee":
            return False
        return self.cursor.parent_id == (
            str(self.parent_id) if self.parent_id is not None else ""
        )

    def next_cursor(
        self,
        *,
        node_type: Literal["employee", "manager"],
        node_id: UUID,
    ) -> str:
        return OrgChartCursor(
            node_type=node_type,
            id=node_id,
            parent_id=str(self.parent_id) if self.parent_id is not None else "",
        ).to_token()


__all__ = [
    "ORG_CHART_DEFAULT_LIMIT",
    "ORG_CHART_MAX_LIMIT",
    "OrgChartCursor",
    "OrgChartNodeRead",
    "OrgChartPagination",
]
