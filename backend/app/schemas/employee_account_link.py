"""Strict P4C contracts for account linking and the own-profile projection."""

from __future__ import annotations

from datetime import datetime
from typing import Literal, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models.employee import EmployeeStatus
from app.models.identity import MembershipStatus
from app.models.user import UserStatus
from app.schemas.date_fields import DateOnly
from app.schemas.employee_profile import EmployeeContractType, EmployeeWorkType

ELIGIBLE_MEMBERSHIP_SEARCH_MAX_LENGTH = 100
ELIGIBLE_MEMBERSHIP_LIMIT_MAX = 20


class EmployeeAccountMembershipRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    membership_id: UUID
    full_name: str
    email: str
    membership_status: MembershipStatus
    user_status: UserStatus
    eligible: bool


class EmployeeAccountLinkRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    membership: EmployeeAccountMembershipRead
    version: int = Field(ge=1)
    created_at: datetime
    updated_at: datetime


class EmployeeAccountLinkStateRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    employee_id: UUID
    link: EmployeeAccountLinkRead | None


class EmployeeAccountLinkUpdate(BaseModel):
    """One strict versioned link, relink, or unlink command.

    Both fields are required. An initial link carries a null expected version; a relink or
    unlink carries the current positive link version. Same-target and already-unlinked retries
    remain idempotent regardless of a stale retry token.
    """

    model_config = ConfigDict(extra="forbid")

    membership_id: UUID | None
    expected_version: int | None = Field(ge=1)

    @field_validator("membership_id")
    @classmethod
    def reject_zero_membership_id(cls, value: UUID | None) -> UUID | None:
        if value is not None and value.int == 0:
            raise ValueError("membership_id must be a non-zero UUID")
        return value


class OwnEmployeeProfileCoreRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    employee_number: str
    first_name: str
    last_name: str
    email: str | None
    status: EmployeeStatus


class OwnMaskedFieldRead(BaseModel):
    """A backend-produced masked display with no reveal/unmask contract."""

    model_config = ConfigDict(extra="forbid")

    visibility: Literal["masked", "unavailable"]
    display_value: str | None

    @model_validator(mode="after")
    def require_consistent_visibility(self) -> Self:
        if (self.visibility == "masked") != (self.display_value is not None):
            raise ValueError("Masked-field visibility and display are inconsistent")
        return self


class OwnEmployeePersonalProfileRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    preferred_name: str | None
    birth_date: OwnMaskedFieldRead
    phone: OwnMaskedFieldRead


class OwnEmployeeEmploymentProfileRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    employment_start_date: DateOnly
    contract_type: EmployeeContractType | None
    work_type: EmployeeWorkType | None


class OwnOrganizationReferenceRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str
    name: str


class OwnPositionReferenceRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str
    title: str


class OwnManagerReferenceRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    full_name: str


class OwnCurrentAssignmentRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    legal_entity: OwnOrganizationReferenceRead
    branch: OwnOrganizationReferenceRead
    department: OwnOrganizationReferenceRead
    position: OwnPositionReferenceRead
    manager: OwnManagerReferenceRead | None


class OwnEmployeeOrganizationRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    current_assignment: OwnCurrentAssignmentRead | None


class OwnEmployeeProfileRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    core: OwnEmployeeProfileCoreRead
    personal: OwnEmployeePersonalProfileRead
    employment: OwnEmployeeEmploymentProfileRead
    organization: OwnEmployeeOrganizationRead


class OwnEmployeeProfileStateRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    availability: Literal["available", "unavailable"]
    employee_id: UUID | None
    profile: OwnEmployeeProfileRead | None

    @model_validator(mode="after")
    def require_consistent_availability(self) -> Self:
        available = self.availability == "available"
        if available != (self.employee_id is not None and self.profile is not None):
            raise ValueError("Own-profile availability fields are inconsistent")
        if not available and (self.employee_id is not None or self.profile is not None):
            raise ValueError("Unavailable own profile cannot disclose identifiers")
        if available and self.profile is not None and self.employee_id != self.profile.core.id:
            raise ValueError("Own-profile employee identifiers are inconsistent")
        return self


__all__ = [
    "ELIGIBLE_MEMBERSHIP_LIMIT_MAX",
    "ELIGIBLE_MEMBERSHIP_SEARCH_MAX_LENGTH",
    "EmployeeAccountLinkRead",
    "EmployeeAccountLinkStateRead",
    "EmployeeAccountLinkUpdate",
    "EmployeeAccountMembershipRead",
    "OwnCurrentAssignmentRead",
    "OwnEmployeeEmploymentProfileRead",
    "OwnEmployeeOrganizationRead",
    "OwnEmployeePersonalProfileRead",
    "OwnEmployeeProfileCoreRead",
    "OwnEmployeeProfileRead",
    "OwnEmployeeProfileStateRead",
    "OwnManagerReferenceRead",
    "OwnMaskedFieldRead",
    "OwnOrganizationReferenceRead",
    "OwnPositionReferenceRead",
]
