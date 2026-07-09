from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.employee import Employee
from app.models.leave_balance_summary import LeaveBalanceSummary


class LeaveBalanceEmployeeNotFoundError(Exception):
    pass


class LeaveBalanceService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_employee_balance_summaries(
        self,
        tenant_id: UUID,
        employee_id: UUID,
        period_year: int | None = None,
    ) -> list[LeaveBalanceSummary]:
        await self._ensure_employee_in_tenant(tenant_id, employee_id)

        statement = (
            select(LeaveBalanceSummary)
            .where(LeaveBalanceSummary.tenant_id == tenant_id)
            .where(LeaveBalanceSummary.employee_id == employee_id)
        )
        if period_year is not None:
            statement = statement.where(LeaveBalanceSummary.period_year == period_year)

        statement = statement.order_by(
            LeaveBalanceSummary.period_year.desc(),
            LeaveBalanceSummary.leave_type.asc(),
        )
        return list(await self.session.scalars(statement))

    async def _ensure_employee_in_tenant(self, tenant_id: UUID, employee_id: UUID) -> None:
        statement = (
            select(Employee.id)
            .where(Employee.tenant_id == tenant_id)
            .where(Employee.id == employee_id)
        )
        if await self.session.scalar(statement) is None:
            raise LeaveBalanceEmployeeNotFoundError
