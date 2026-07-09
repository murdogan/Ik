from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class LeaveBalanceSummaryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    employee_id: UUID
    leave_type: str
    period_year: int
    opening_balance_days: float
    used_days: float
    planned_days: float
    remaining_days: float
    calculation_mode: Literal["manual_placeholder"] = "manual_placeholder"
    external_integration_enabled: Literal[False] = False
