"""Employee write orchestration during the modular-monolith migration."""

from dataclasses import dataclass
from uuid import UUID

from app.models.employee import Employee
from app.platform.db import UnitOfWork
from app.platform.idempotency import command_fingerprint
from app.schemas.employee import EmployeeCreate, EmployeeRead, EmployeeUpdate
from app.services.command_idempotency import (
    CommandIdempotencyService,
    IdempotentCommandExecutor,
)
from app.services.employee_service import EmployeeReadProjection, EmployeeService


@dataclass(slots=True)
class EmployeeCommandHandler:
    service: EmployeeService
    unit_of_work: UnitOfWork
    idempotency: CommandIdempotencyService | None = None

    async def create_employee(
        self,
        tenant_id: UUID,
        payload: EmployeeCreate,
        idempotency_key: str | None = None,
    ) -> Employee | EmployeeRead:
        if idempotency_key is None:
            return await self.unit_of_work.execute(
                lambda: self.service.create_employee(tenant_id, payload)
            )
        executor = self._idempotent_executor()
        return await executor.execute(
            tenant_id=tenant_id,
            idempotency_key=idempotency_key,
            command_name="employees.create",
            request_fingerprint=command_fingerprint(
                {"payload": payload.model_dump(mode="json")}
            ),
            operation=lambda: self.service.create_employee(tenant_id, payload),
            serialize=_employee_response_payload,
            deserialize=EmployeeRead.model_validate,
        )

    async def update_employee(
        self,
        tenant_id: UUID,
        employee_id: UUID,
        payload: EmployeeUpdate,
    ) -> EmployeeReadProjection:
        async def operation() -> EmployeeReadProjection:
            await self.service.update_employee(tenant_id, employee_id, payload)
            return await self.service.get_employee_read(tenant_id, employee_id)

        return await self.unit_of_work.execute(operation)

    async def delete_employee(self, tenant_id: UUID, employee_id: UUID) -> None:
        await self.unit_of_work.execute(
            lambda: self.service.delete_employee(tenant_id, employee_id)
        )

    def _idempotent_executor(self) -> IdempotentCommandExecutor:
        if self.idempotency is None:
            raise RuntimeError("Idempotency service is required when a key is supplied")
        return IdempotentCommandExecutor(
            service=self.idempotency,
            unit_of_work=self.unit_of_work,
        )


def _employee_response_payload(employee: Employee | EmployeeRead) -> dict[str, object]:
    return EmployeeRead.model_validate(employee).model_dump(mode="json")
