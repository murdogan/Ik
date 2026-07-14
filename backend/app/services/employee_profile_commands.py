"""Atomic Employee 360 profile writes and allowlisted audit events."""

from dataclasses import dataclass
from uuid import UUID, uuid4

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
from app.platform.db import (
    DatabaseCommandContext,
    DatabaseCommandIntent,
    UnitOfWork,
    configure_database_command_context,
)
from app.platform.request_context import RequestContext
from app.schemas.employee_profile import (
    EmployeeEmploymentProfileMutationRead,
    EmployeeEmploymentProfileUpdate,
    EmployeePersonalProfileMutationRead,
    EmployeePersonalProfileUpdate,
)
from app.services.employee_profile_service import EmployeeProfileService


@dataclass(slots=True)
class EmployeeProfileCommandHandler:
    service: EmployeeProfileService
    unit_of_work: UnitOfWork
    audit_recorder: AuditRecorder | None = None

    async def update_personal_profile(
        self,
        tenant_id: UUID,
        employee_id: UUID,
        payload: EmployeePersonalProfileUpdate,
        *,
        request_context: RequestContext | None = None,
    ) -> EmployeePersonalProfileMutationRead:
        self._configure_personal_database_command(
            tenant_id=tenant_id,
            employee_id=employee_id,
            request_context=request_context,
        )

        async def operation() -> EmployeePersonalProfileMutationRead:
            mutation = await self.service.update_personal_profile(
                tenant_id,
                employee_id,
                payload,
            )
            await self._record_event(
                employee_id=employee_id,
                request_context=request_context,
                event_type=AuditEventType.EMPLOYEE_PERSONAL_PROFILE_UPDATED,
                action="update_personal_profile",
                changed_fields=mutation.changed_fields,
                before_values=mutation.before_values,
                after_values=mutation.after_values,
            )
            return mutation.response

        return await self.unit_of_work.execute(operation)

    def _configure_personal_database_command(
        self,
        *,
        tenant_id: UUID,
        employee_id: UUID,
        request_context: RequestContext | None,
    ) -> None:
        if self.service.session.get_bind().dialect.name != "postgresql":
            return
        if request_context is None or request_context.actor_id is None:
            raise RuntimeError("PostgreSQL personal-profile commands require request context")
        if request_context.require_tenant().tenant_id != tenant_id:
            raise RuntimeError("Personal-profile command tenant does not match request context")
        configure_database_command_context(
            self.service.session,
            DatabaseCommandContext(
                tenant_id=tenant_id,
                actor_user_id=request_context.actor_id,
                membership_id=request_context.require_membership(),
                intent=DatabaseCommandIntent.P4B_PERSONAL_UPDATE,
                target_id=employee_id,
                audit_event_id=uuid4(),
                correlation_request_id=request_context.request_id,
                trace_id=request_context.trace_id,
                session_id=request_context.session_id,
            ),
        )

    async def update_employment_profile(
        self,
        tenant_id: UUID,
        employee_id: UUID,
        payload: EmployeeEmploymentProfileUpdate,
        *,
        request_context: RequestContext | None = None,
    ) -> EmployeeEmploymentProfileMutationRead:
        async def operation() -> EmployeeEmploymentProfileMutationRead:
            mutation = await self.service.update_employment_profile(
                tenant_id,
                employee_id,
                payload,
            )
            await self._record_event(
                employee_id=employee_id,
                request_context=request_context,
                event_type=AuditEventType.EMPLOYEE_EMPLOYMENT_PROFILE_UPDATED,
                action="update_employment_profile",
                changed_fields=mutation.changed_fields,
                before_values=mutation.before_values,
                after_values=mutation.after_values,
            )
            return mutation.response

        return await self.unit_of_work.execute(operation)

    async def _record_event(
        self,
        *,
        employee_id: UUID,
        request_context: RequestContext | None,
        event_type: AuditEventType,
        action: str,
        changed_fields: tuple[str, ...],
        before_values: dict[str, object],
        after_values: dict[str, object],
    ) -> None:
        if (
            not changed_fields
            or self.audit_recorder is None
            or request_context is None
            or request_context.actor_id is None
        ):
            return
        await self.audit_recorder.record(
            AuditEventDraft(
                scope_type=AuditScopeType.TENANT,
                tenant_id=request_context.require_tenant().tenant_id,
                actor_type=AuditActorType.USER,
                actor_user_id=request_context.actor_id,
                event_type=event_type,
                category=AuditCategory.HR_OPERATIONS,
                resource_type="employee",
                resource_id=employee_id,
                action=action,
                context=AuditContext.from_request_context(request_context),
                session_id=request_context.session_id,
                changed_fields=changed_fields,
                before_values=before_values,
                after_values=after_values,
                data_classification=AuditDataClassification.HR_METADATA,
                visibility_class=AuditVisibilityClass.HR_OPERATIONS,
            )
        )


__all__ = ["EmployeeProfileCommandHandler"]
