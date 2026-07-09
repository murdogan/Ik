from uuid import UUID

import pytest
from app.schemas.leave_balance_summary import LeaveBalanceSummaryRead
from pydantic import ValidationError


def test_leave_balance_summary_read_exposes_manual_placeholder_flags() -> None:
    payload = LeaveBalanceSummaryRead(
        id=UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"),
        employee_id=UUID("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"),
        leave_type="annual",
        period_year=2026,
        opening_balance_days=20.0,
        used_days=5.0,
        planned_days=2.0,
        remaining_days=13.0,
    )

    data = payload.model_dump()
    assert data["calculation_mode"] == "manual_placeholder"
    assert data["external_integration_enabled"] is False
    assert "tenant_id" not in data


def test_leave_balance_summary_read_rejects_external_integration_flag_override() -> None:
    with pytest.raises(ValidationError):
        LeaveBalanceSummaryRead(
            id=UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"),
            employee_id=UUID("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"),
            leave_type="annual",
            period_year=2026,
            opening_balance_days=20.0,
            used_days=5.0,
            planned_days=2.0,
            remaining_days=13.0,
            external_integration_enabled=True,
        )


@pytest.mark.parametrize("calculation_mode", ["accrual_engine", "external_integration"])
def test_leave_balance_summary_read_rejects_non_placeholder_calculation_modes(
    calculation_mode: str,
) -> None:
    with pytest.raises(ValidationError):
        LeaveBalanceSummaryRead(
            id=UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"),
            employee_id=UUID("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"),
            leave_type="annual",
            period_year=2026,
            opening_balance_days=20.0,
            used_days=5.0,
            planned_days=2.0,
            remaining_days=13.0,
            calculation_mode=calculation_mode,
        )
