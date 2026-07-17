"""Transactional export job commands and reauthorized private download grants."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings
from app.models.reporting import (
    ExportJobStatus,
    ReportExportDownloadIntent,
    ReportExportJob,
    ReportScope,
    ReportType,
)
from app.platform.audit import (
    AuditActorType,
    AuditCategory,
    AuditContext,
    AuditDataClassification,
    AuditEventDraft,
    AuditEventType,
    AuditScopeType,
    AuditVisibilityClass,
)
from app.platform.db import SqlAlchemyUnitOfWork, configure_tenant_database_access
from app.platform.idempotency import command_fingerprint
from app.platform.request_context import RequestContext
from app.platform.storage import ObjectStorage, ObjectStorageError
from app.schemas.reporting import (
    ExportDownloadIntentRead,
    ExportJobCreate,
    ExportJobRead,
)
from app.services.audit_recorder import SqlAlchemyAuditRecorder
from app.services.command_idempotency import (
    CommandIdempotencyService,
    IdempotentCommandExecutor,
)
from app.services.reporting_access import (
    ReportingAccessDeniedError,
    ReportingConflictError,
    ReportingNotFoundError,
    ReportingStorageUnavailableError,
    authorization_covers_artifact,
    enforce_requested_fields,
    require_reporting_feature,
    resolve_report_authorization,
)

_MAX_ACTIVE_EXPORTS_PER_USER = 10
_MAX_DOWNLOAD_INTENTS = 3


class ExportJobService:
    def __init__(
        self,
        *,
        session_factory: async_sessionmaker[AsyncSession],
        storage: ObjectStorage,
        settings: Settings,
    ) -> None:
        self.session_factory = session_factory
        self.storage = storage
        self.settings = settings

    async def create_job(
        self,
        *,
        request_context: RequestContext,
        permissions: tuple[str, ...],
        payload: ExportJobCreate,
        idempotency_key: str,
    ) -> ExportJobRead:
        tenant_id, actor_id, membership_id = _actor_scope(request_context)
        report_type = ReportType(payload.report_type)
        authorization = resolve_report_authorization(
            permissions=permissions,
            actor_id=actor_id,
            require_export=True,
        )
        fields = enforce_requested_fields(
            report_type=report_type,
            requested_fields=[field.value for field in payload.fields],
            permissions=permissions,
        )
        classifications = _field_classifications(report_type, fields)
        async with self.session_factory() as session:
            configure_tenant_database_access(
                session, tenant_id, actor_id=actor_id, membership_id=membership_id
            )
            executor = IdempotentCommandExecutor(
                service=CommandIdempotencyService(session=session),
                unit_of_work=SqlAlchemyUnitOfWork(session),
            )

            async def operation() -> ExportJobRead:
                now = datetime.now(UTC)
                active_count = await session.scalar(
                    select(func.count())
                    .select_from(ReportExportJob)
                    .where(
                        ReportExportJob.tenant_id == tenant_id,
                        ReportExportJob.requested_by_user_id == actor_id,
                        ReportExportJob.status.in_(
                            (
                                ExportJobStatus.QUEUED.value,
                                ExportJobStatus.RUNNING.value,
                                ExportJobStatus.RETRY.value,
                            )
                        ),
                    )
                )
                if int(active_count or 0) >= _MAX_ACTIVE_EXPORTS_PER_USER:
                    raise ReportingConflictError()
                job = ReportExportJob(
                    id=uuid4(),
                    tenant_id=tenant_id,
                    requested_by_user_id=actor_id,
                    report_type=report_type.value,
                    format=payload.format.value,
                    status=ExportJobStatus.QUEUED.value,
                    request_scope=authorization.scope.value,
                    request_scope_user_id=authorization.scope_user_id,
                    fields_snapshot=list(fields),
                    filters_snapshot=payload.filters.model_dump(mode="json"),
                    attempt_count=0,
                    next_attempt_at=now,
                    created_at=now,
                    updated_at=now,
                )
                session.add(job)
                await session.flush()
                await _record_export_event(
                    session,
                    job=job,
                    event_type=AuditEventType.REPORT_EXPORT_REQUESTED,
                    action="request",
                    request_context=request_context,
                    changed_fields=("status",),
                    metadata={
                        "report_type": job.report_type,
                        "export_format": job.format,
                        "report_scope": job.request_scope,
                        "field_count": len(fields),
                        "field_classifications": classifications,
                    },
                )
                return _job_read(job, download_intent_count=0, now=now)

            return await executor.execute(
                tenant_id=tenant_id,
                idempotency_key=idempotency_key,
                command_name="report_exports.create",
                request_fingerprint=command_fingerprint(
                    {
                        "actor_id": str(actor_id),
                        "payload": payload.model_dump(mode="json"),
                    }
                ),
                precondition=lambda: require_reporting_feature(
                    session,
                    tenant_id=tenant_id,
                    write=True,
                ),
                operation=operation,
                serialize=lambda result: result.model_dump(mode="json"),
                deserialize=ExportJobRead.model_validate,
            )

    async def get_job(
        self,
        *,
        request_context: RequestContext,
        job_id: UUID,
    ) -> ExportJobRead:
        tenant_id, actor_id, membership_id = _actor_scope(request_context)
        async with self.session_factory() as session:
            configure_tenant_database_access(
                session, tenant_id, actor_id=actor_id, membership_id=membership_id
            )
            async with session.begin():
                await require_reporting_feature(session, tenant_id=tenant_id)
                job = await _owned_job(
                    session,
                    tenant_id=tenant_id,
                    actor_id=actor_id,
                    job_id=job_id,
                )
                intent_count = await _download_intent_count(session, tenant_id, job.id)
                return _job_read(job, download_intent_count=intent_count, now=datetime.now(UTC))

    async def cancel_job(
        self,
        *,
        request_context: RequestContext,
        job_id: UUID,
    ) -> ExportJobRead:
        tenant_id, actor_id, membership_id = _actor_scope(request_context)
        now = datetime.now(UTC)
        async with self.session_factory() as session:
            configure_tenant_database_access(
                session, tenant_id, actor_id=actor_id, membership_id=membership_id
            )
            async with session.begin():
                await require_reporting_feature(session, tenant_id=tenant_id, write=True)
                job = await _owned_job(
                    session,
                    tenant_id=tenant_id,
                    actor_id=actor_id,
                    job_id=job_id,
                    lock=True,
                )
                if job.status in {
                    ExportJobStatus.SUCCEEDED.value,
                    ExportJobStatus.FAILED.value,
                    ExportJobStatus.EXPIRED.value,
                }:
                    raise ReportingConflictError()
                if job.status != ExportJobStatus.CANCELLED.value:
                    job.status = ExportJobStatus.CANCELLED.value
                    job.cancel_requested_at = now
                    job.failure_code = None
                    job.next_attempt_at = None
                    job.lease_expires_at = None
                    job.updated_at = now
                    await _record_export_event(
                        session,
                        job=job,
                        event_type=AuditEventType.REPORT_EXPORT_CANCELLED,
                        action="cancel",
                        request_context=request_context,
                        changed_fields=("status",),
                        metadata={"report_type": job.report_type, "export_format": job.format},
                    )
                intent_count = await _download_intent_count(session, tenant_id, job.id)
                return _job_read(job, download_intent_count=intent_count, now=now)

    async def create_download_intent(
        self,
        *,
        request_context: RequestContext,
        permissions: tuple[str, ...],
        job_id: UUID,
    ) -> ExportDownloadIntentRead:
        tenant_id, actor_id, membership_id = _actor_scope(request_context)
        now = datetime.now(UTC)
        async with self.session_factory() as session:
            configure_tenant_database_access(
                session, tenant_id, actor_id=actor_id, membership_id=membership_id
            )
            async with session.begin():
                await require_reporting_feature(session, tenant_id=tenant_id, write=True)
                job = await _owned_job(
                    session,
                    tenant_id=tenant_id,
                    actor_id=actor_id,
                    job_id=job_id,
                    lock=True,
                )
                if (
                    job.status != ExportJobStatus.SUCCEEDED.value
                    or job.expires_at is None
                    or job.expires_at <= now
                    or job.artifact_object_key is None
                    or job.generated_scope is None
                    or job.generated_fields is None
                ):
                    raise ReportingConflictError()
                current = resolve_report_authorization(
                    permissions=permissions,
                    actor_id=actor_id,
                    require_export=True,
                )
                artifact_scope = ReportScope(job.generated_scope)
                if not authorization_covers_artifact(
                    current=current,
                    artifact_scope=artifact_scope,
                    artifact_scope_user_id=job.generated_scope_user_id,
                ):
                    raise ReportingAccessDeniedError()
                enforce_requested_fields(
                    report_type=ReportType(job.report_type),
                    requested_fields=job.generated_fields,
                    permissions=permissions,
                )
                intent_count = await _download_intent_count(session, tenant_id, job.id)
                if intent_count >= _MAX_DOWNLOAD_INTENTS:
                    raise ReportingConflictError()
                ttl_seconds = min(
                    self.settings.export_download_ttl_seconds,
                    max(0, int((job.expires_at - now).total_seconds()) - 1),
                )
                if ttl_seconds < 1:
                    raise ReportingConflictError()
                try:
                    grant = await self.storage.presign_download(
                        key=job.artifact_object_key,
                        download_name=f"report-{job.id}.{job.format}",
                        ttl_seconds=ttl_seconds,
                    )
                except ObjectStorageError as exc:
                    raise ReportingStorageUnavailableError() from exc
                expires_at = min(grant.expires_at, job.expires_at)
                intent = ReportExportDownloadIntent(
                    id=uuid4(),
                    tenant_id=tenant_id,
                    export_job_id=job.id,
                    issued_to_user_id=actor_id,
                    expires_at=expires_at,
                    created_at=now,
                )
                session.add(intent)
                await session.flush()
                await _record_export_event(
                    session,
                    job=job,
                    event_type=AuditEventType.REPORT_EXPORT_DOWNLOAD_INTENT_ISSUED,
                    action="issue_download_intent",
                    request_context=request_context,
                    changed_fields=(),
                    metadata={
                        "report_type": job.report_type,
                        "export_format": job.format,
                        "download_intent_count": intent_count + 1,
                    },
                )
                return ExportDownloadIntentRead(
                    export_job_id=job.id,
                    url=grant.url,
                    expires_at=expires_at,
                )


async def _owned_job(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    actor_id: UUID,
    job_id: UUID,
    lock: bool = False,
) -> ReportExportJob:
    statement = select(ReportExportJob).where(
        ReportExportJob.tenant_id == tenant_id,
        ReportExportJob.id == job_id,
        ReportExportJob.requested_by_user_id == actor_id,
    )
    if lock:
        statement = statement.with_for_update()
    job = await session.scalar(statement)
    if job is None:
        raise ReportingNotFoundError()
    return job


async def _download_intent_count(session: AsyncSession, tenant_id: UUID, job_id: UUID) -> int:
    value = await session.scalar(
        select(func.count())
        .select_from(ReportExportDownloadIntent)
        .where(
            ReportExportDownloadIntent.tenant_id == tenant_id,
            ReportExportDownloadIntent.export_job_id == job_id,
        )
    )
    return int(value or 0)


def _job_read(job: ReportExportJob, *, download_intent_count: int, now: datetime) -> ExportJobRead:
    status = ExportJobStatus(job.status)
    if status is ExportJobStatus.SUCCEEDED and job.expires_at is not None and job.expires_at <= now:
        status = ExportJobStatus.EXPIRED
    return ExportJobRead(
        id=job.id,
        report_type=ReportType(job.report_type),
        format=job.format,
        status=status,
        request_scope=ReportScope(job.request_scope),
        fields=list(job.fields_snapshot),
        generated_scope=ReportScope(job.generated_scope) if job.generated_scope else None,
        generated_fields=list(job.generated_fields) if job.generated_fields is not None else None,
        field_classifications=(
            list(job.field_classifications) if job.field_classifications is not None else None
        ),
        row_count=job.row_count,
        size_bytes=job.size_bytes,
        sha256=job.artifact_sha256,
        failure_code=job.failure_code,
        cancel_requested=job.cancel_requested_at is not None,
        download_intents_remaining=max(0, _MAX_DOWNLOAD_INTENTS - download_intent_count),
        available_at=job.available_at,
        expires_at=job.expires_at,
        created_at=job.created_at,
        updated_at=job.updated_at,
    )


def _field_classifications(report_type: ReportType, fields: tuple[str, ...]) -> list[str]:
    values = {"work_safe"}
    if report_type is ReportType.EMPLOYEES and "work_email" in fields:
        values.add("work_contact")
    if report_type in {ReportType.LEAVES, ReportType.MISSING_DOCUMENTS}:
        values.add("hr_metadata")
    return sorted(values)


async def _record_export_event(
    session: AsyncSession,
    *,
    job: ReportExportJob,
    event_type: AuditEventType,
    action: str,
    request_context: RequestContext,
    changed_fields: tuple[str, ...],
    metadata: dict[str, object],
) -> None:
    await SqlAlchemyAuditRecorder(session).record(
        AuditEventDraft(
            scope_type=AuditScopeType.TENANT,
            tenant_id=job.tenant_id,
            actor_type=AuditActorType.USER,
            actor_user_id=request_context.actor_id,
            event_type=event_type,
            category=AuditCategory.HR_OPERATIONS,
            resource_type="report_export_job",
            resource_id=job.id,
            action=action,
            context=AuditContext.from_request_context(request_context),
            session_id=request_context.session_id,
            changed_fields=changed_fields,
            metadata=metadata,
            data_classification=AuditDataClassification.HR_METADATA,
            visibility_class=AuditVisibilityClass.HR_OPERATIONS,
        )
    )


def _actor_scope(context: RequestContext) -> tuple[UUID, UUID, UUID]:
    actor_id = context.actor_id
    if actor_id is None:
        raise ReportingAccessDeniedError()
    return context.require_tenant().tenant_id, actor_id, context.require_membership()


__all__ = ["ExportJobService"]
