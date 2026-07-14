"""Same-session SQLAlchemy adapter for append-only audit recording."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit import AuditEvent
from app.platform.audit.contracts import AuditEventDraft
from app.platform.audit.redaction import redact_audit_values
from app.platform.request_context import is_valid_request_id, is_valid_trace_id


class SqlAlchemyAuditRecorder:
    """Append a redacted event using the caller's active Unit of Work."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def record(self, event: AuditEventDraft, /) -> None:
        if not self._session.in_transaction():
            raise RuntimeError("Audit recording requires an active Unit of Work")
        if not is_valid_request_id(event.context.request_id):
            raise ValueError("Audit request_id must be a safe opaque identifier")
        if not is_valid_trace_id(event.context.trace_id):
            raise ValueError("Audit trace_id must be a canonical non-zero trace ID")

        safe = redact_audit_values(event)
        self._session.add(
            AuditEvent(
                id=event.id,
                occurred_at=event.occurred_at,
                scope_type=event.scope_type.value,
                tenant_id=event.tenant_id,
                actor_type=event.actor_type.value,
                actor_user_id=event.actor_user_id,
                impersonator_user_id=event.impersonator_user_id,
                event_type=event.event_type.value,
                category=event.category.value,
                severity=event.severity.value,
                resource_type=event.resource_type,
                resource_id=event.resource_id,
                action=event.action,
                result=event.result.value,
                request_id=event.context.request_id,
                trace_id=event.context.trace_id,
                session_id=event.session_id,
                ip_address=safe.ip_address,
                user_agent=safe.user_agent,
                reason=None,
                support_ticket_id=None,
                changed_fields=safe.changed_fields,
                before_data=safe.before_data,
                after_data=safe.after_data,
                metadata_=safe.metadata,
                data_classification=event.data_classification.value,
                visibility_class=event.visibility_class.value,
                integrity_hash=None,
            )
        )
        await self._session.flush()


__all__ = ["SqlAlchemyAuditRecorder"]
