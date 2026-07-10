"""Employee write orchestration during the modular-monolith migration."""

from dataclasses import dataclass
from uuid import UUID

from app.models.employee import Employee
from app.platform.db import UnitOfWork
from app.schemas.employee import EmployeeCreate, EmployeeUpdate
from app.services.employee_service import EmployeeService


@dataclass(slots=True)
class EmployeeCommandHandler:
    service: EmployeeService
    unit_of_work: UnitOfWork

    async def create_employee(self, tenant_id: UUID, payload: EmployeeCreate) -> Employee:
        return await self.unit_of_work.execute(
            lambda: self.service.create_employee(tenant_id, payload)
        )

    async def update_employee(
        self,
        tenant_id: UUID,
        employee_id: UUID,
        payload: EmployeeUpdate,
    ) -> Employee:
        return await self.unit_of_work.execute(
            lambda: self.service.update_employee(tenant_id, employee_id, payload)
        )

    async def delete_employee(self, tenant_id: UUID, employee_id: UUID) -> None:
        await self.unit_of_work.execute(
            lambda: self.service.delete_employee(tenant_id, employee_id)
        )
