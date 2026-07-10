"""Leave-request write orchestration during the modular-monolith migration."""

from dataclasses import dataclass
from uuid import UUID

from app.models.leave_request import LeaveRequest
from app.platform.db import UnitOfWork
from app.schemas.leave_request import LeaveRequestCreate, LeaveRequestDecision
from app.services.leave_request_service import LeaveRequestService


@dataclass(slots=True)
class LeaveRequestCommandHandler:
    service: LeaveRequestService
    unit_of_work: UnitOfWork

    async def create_leave_request(
        self,
        tenant_id: UUID,
        payload: LeaveRequestCreate,
    ) -> LeaveRequest:
        return await self.unit_of_work.execute(
            lambda: self.service.create_leave_request(tenant_id, payload)
        )

    async def approve_leave_request(
        self,
        tenant_id: UUID,
        leave_request_id: UUID,
        payload: LeaveRequestDecision,
    ) -> LeaveRequest:
        return await self.unit_of_work.execute(
            lambda: self.service.approve_leave_request(tenant_id, leave_request_id, payload)
        )

    async def reject_leave_request(
        self,
        tenant_id: UUID,
        leave_request_id: UUID,
        payload: LeaveRequestDecision,
    ) -> LeaveRequest:
        return await self.unit_of_work.execute(
            lambda: self.service.reject_leave_request(tenant_id, leave_request_id, payload)
        )

    async def cancel_leave_request(
        self,
        tenant_id: UUID,
        leave_request_id: UUID,
        payload: LeaveRequestDecision,
    ) -> LeaveRequest:
        return await self.unit_of_work.execute(
            lambda: self.service.cancel_leave_request(tenant_id, leave_request_id, payload)
        )
