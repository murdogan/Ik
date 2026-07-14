"""Atomic P4C employee-account link commands with allowlisted audit metadata."""

from dataclasses import dataclass
from uuid import UUID

from app.platform.audit import (
    AuditActorType,
    AuditCategory,
    AuditContext,
    AuditDataClassification,
    AuditEventDraft,
    AuditEventType,
    AuditRecorder,
    AuditScopeType,
    AuditVisibilityClass,
)
from app.platform.db import UnitOfWork
from app.platform.request_context import RequestContext
from app.schemas.employee_account_link import (
    EmployeeAccountLinkStateRead,
    EmployeeAccountLinkUpdate,
)
from app.services.employee_account_link_service import EmployeeAccountLinkService


@dataclass(slots=True)
class EmployeeAccountLinkCommandHandler:
    service: EmployeeAccountLinkService
    unit_of_work: UnitOfWork
    audit_recorder: AuditRecorder

    async def update_account_link(
        self,
        tenant_id: UUID,
        employee_id: UUID,
        payload: EmployeeAccountLinkUpdate,
        *,
        request_context: RequestContext,
    ) -> EmployeeAccountLinkStateRead:
        if (
            request_context.tenant is None
            or request_context.tenant.tenant_id != tenant_id
            or request_context.actor_id is None
        ):
            raise RuntimeError("Account-link audit requires the authenticated tenant actor")

        async def operation() -> EmployeeAccountLinkStateRead:
            mutation = await self.service.update_account_link(
                tenant_id,
                employee_id,
                payload,
            )
            if mutation.changed:
                metadata: dict[str, object] = {"link_status": mutation.link_status}
                if mutation.previous_membership_id is not None:
                    metadata["previous_membership_id"] = mutation.previous_membership_id
                if mutation.new_membership_id is not None:
                    metadata["new_membership_id"] = mutation.new_membership_id
                await self.audit_recorder.record(
                    AuditEventDraft(
                        scope_type=AuditScopeType.TENANT,
                        tenant_id=tenant_id,
                        actor_type=AuditActorType.USER,
                        actor_user_id=request_context.actor_id,
                        event_type=AuditEventType.EMPLOYEE_ACCOUNT_LINK_CHANGED,
                        category=AuditCategory.HR_OPERATIONS,
                        resource_type="employee",
                        resource_id=employee_id,
                        action="change_account_link",
                        context=AuditContext.from_request_context(request_context),
                        session_id=request_context.session_id,
                        changed_fields=("membership_id", "link_status"),
                        metadata=metadata,
                        data_classification=AuditDataClassification.HR_METADATA,
                        visibility_class=AuditVisibilityClass.HR_OPERATIONS,
                    )
                )
            return mutation.response

        return await self.unit_of_work.execute(operation)


__all__ = ["EmployeeAccountLinkCommandHandler"]
