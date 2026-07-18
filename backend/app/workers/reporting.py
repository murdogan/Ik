"""Bounded PostgreSQL report export and employee import worker."""

from __future__ import annotations

import asyncio
import csv
import logging
import tempfile
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from hashlib import sha256
from pathlib import Path
from time import monotonic
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5
from xml.sax.saxutils import escape as xml_escape

from openpyxl import Workbook
from pydantic import ValidationError
from sqlalchemy import and_, delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings, get_settings
from app.db.session import create_database_runtime
from app.models.department import Department, DepartmentStatus
from app.models.employee import Employee
from app.models.employee_import import (
    EmployeeImport,
    EmployeeImportIssue,
    EmployeeImportRow,
    EmployeeImportScanResult,
    EmployeeImportStatus,
)
from app.models.organization import Branch, BranchStatus, LegalEntity, LegalEntityStatus
from app.models.position import Position, PositionStatus
from app.models.reporting import ExportJobStatus, ReportExportJob, ReportScope, ReportType
from app.models.tenant import Tenant
from app.models.user import User, UserStatus
from app.modules.documents import create_document_runtime
from app.modules.documents.scanning import MalwareScanError, MalwareScanner, MalwareScanVerdict
from app.modules.reporting.spreadsheets import (
    SpreadsheetFileError,
    iter_import_rows,
    spreadsheet_safe,
)
from app.platform.audit import (
    AuditActorType,
    AuditCategory,
    AuditContext,
    AuditDataClassification,
    AuditEventDraft,
    AuditEventType,
    AuditResult,
    AuditScopeType,
    AuditVisibilityClass,
)
from app.platform.db import configure_platform_database_access, configure_tenant_database_access
from app.platform.observability.operational import (
    configure_operational_logger,
    log_worker_failed,
    log_worker_heartbeat,
    log_worker_started,
    log_worker_stopped,
)
from app.platform.storage import ObjectStorage, ObjectStorageError
from app.schemas.employee import EMAIL_PATTERN, EmployeeCreate
from app.schemas.employee_import import (
    EMPLOYEE_IMPORT_FIELDS,
    EMPLOYEE_IMPORT_ISSUE_MESSAGES,
    EMPLOYEE_IMPORT_MAX_BYTES,
    EMPLOYEE_IMPORT_MAX_ROWS,
)
from app.schemas.reporting import EXPORT_MAX_ROWS
from app.services.audit_recorder import SqlAlchemyAuditRecorder
from app.services.authorization_service import load_authorization_snapshot
from app.services.employee_import_service import canonical_import_row
from app.services.report_service import ReportService
from app.services.reporting_access import (
    ReportAuthorization,
    ReportingAccessDeniedError,
    ReportingConflictError,
    ReportingFeatureUnavailableError,
    ReportingValidationError,
    authorization_covers_artifact,
    reduce_report_authorization,
    reduce_requested_fields,
    require_reporting_feature,
    resolve_report_authorization,
)

_LOGGER = logging.getLogger(__name__)
_EXPORT_PAGE_SIZE = 250
_VALIDATION_CHUNK_SIZE = 250
_FORMULA_PREFIXES = frozenset({"=", "+", "-", "@", "\t", "\r", "\n"})


@dataclass(frozen=True, slots=True)
class _ParsedImportRow:
    row_number: int
    employee_number: str
    employee_number_normalized: str
    first_name: str
    last_name: str
    work_email: str | None
    work_email_normalized: str | None
    status: str
    employment_start_date: date
    employment_end_date: date | None
    legal_entity_code: str
    branch_code: str
    department_code: str
    position_code: str


class _IssueCollection(dict[tuple[int, str, str | None], EmployeeImportIssue]):
    def __init__(self) -> None:
        super().__init__()
        self.error_rows: set[int] = set()
        self.seen_keys: set[tuple[int, str, str | None]] = set()
        self.error_count = 0
        self.warning_count = 0

    @property
    def total_count(self) -> int:
        return self.error_count + self.warning_count


class _ExportRowLimitError(RuntimeError):
    pass


class _ExportFileLimitError(RuntimeError):
    pass


class _ExportCancelledError(RuntimeError):
    pass


class ReportingWorker:
    def __init__(
        self,
        *,
        session_factory: async_sessionmaker[AsyncSession],
        settings: Settings,
        storage: ObjectStorage,
        scanner: MalwareScanner,
    ) -> None:
        self.session_factory = session_factory
        self.settings = settings
        self.storage = storage
        self.scanner = scanner
        self._tenant_cursor: UUID | None = None

    async def run_once(self) -> int:
        processed = 0
        for tenant_id in await self._discover_tenants():
            try:
                processed += await self._process_tenant(tenant_id)
            except ReportingFeatureUnavailableError:
                continue
            except Exception as exc:
                _LOGGER.error(
                    "Reporting tenant batch failed error_class=%s",
                    type(exc).__name__,
                )
        return processed

    async def _discover_tenants(self) -> list[UUID]:
        async with self.session_factory() as session:
            configure_platform_database_access(session)
            async with session.begin():
                statement = select(Tenant.id).where(
                    Tenant.status.in_(("trial", "active", "suspended", "offboarding", "closed"))
                )
                if self._tenant_cursor is not None:
                    statement = statement.where(Tenant.id > self._tenant_cursor)
                tenant_ids = list(
                    await session.scalars(
                        statement.order_by(Tenant.id).limit(
                            self.settings.reporting_worker_tenant_batch_size
                        )
                    )
                )
                if not tenant_ids and self._tenant_cursor is not None:
                    self._tenant_cursor = None
                    tenant_ids = list(
                        await session.scalars(
                            select(Tenant.id)
                            .where(
                                Tenant.status.in_(
                                    (
                                        "trial",
                                        "active",
                                        "suspended",
                                        "offboarding",
                                        "closed",
                                    )
                                )
                            )
                            .order_by(Tenant.id)
                            .limit(self.settings.reporting_worker_tenant_batch_size)
                        )
                    )
        if tenant_ids:
            self._tenant_cursor = tenant_ids[-1]
        return tenant_ids

    async def _process_tenant(self, tenant_id: UUID) -> int:
        try:
            import_ids = await self._claim_imports(tenant_id)
        except (ReportingConflictError, ReportingFeatureUnavailableError):
            import_ids = []
        try:
            export_ids = await self._claim_exports(tenant_id)
        except (ReportingConflictError, ReportingFeatureUnavailableError):
            export_ids = []
        for import_id in import_ids:
            await self._process_import(tenant_id, import_id)
        for export_id in export_ids:
            await self._process_export(tenant_id, export_id)
        await self._expire_artifacts(tenant_id)
        return len(import_ids) + len(export_ids)

    async def _claim_imports(self, tenant_id: UUID) -> list[UUID]:
        now = datetime.now(UTC)
        lease_until = now + timedelta(seconds=self.settings.reporting_worker_lease_seconds)
        async with self.session_factory() as session:
            configure_tenant_database_access(session, tenant_id)
            async with session.begin():
                await require_reporting_feature(session, tenant_id=tenant_id, write=True)
                exhausted = list(
                    await session.scalars(
                        select(EmployeeImport)
                        .where(
                            EmployeeImport.tenant_id == tenant_id,
                            EmployeeImport.status == EmployeeImportStatus.PROCESSING.value,
                            EmployeeImport.lease_expires_at < now,
                            EmployeeImport.attempt_count
                            >= self.settings.reporting_worker_max_attempts,
                        )
                        .order_by(EmployeeImport.created_at, EmployeeImport.id)
                        .limit(self.settings.reporting_worker_import_batch_size)
                        .with_for_update(skip_locked=True)
                    )
                )
                for job in exhausted:
                    job.status = EmployeeImportStatus.FAILED.value
                    job.failure_code = "worker_failure"
                    job.next_attempt_at = None
                    job.lease_expires_at = None
                    job.updated_at = now
                    await _record_worker_import_event(
                        session,
                        job=job,
                        event_type=AuditEventType.EMPLOYEE_IMPORT_FAILED,
                        action="process",
                        result=AuditResult.FAILURE,
                        metadata={
                            "file_format": job.file_format,
                            "template_version": job.template_version,
                            "failure_code": "worker_failure",
                            "attempt_count": job.attempt_count,
                        },
                    )
                jobs = list(
                    await session.scalars(
                        select(EmployeeImport)
                        .where(
                            EmployeeImport.tenant_id == tenant_id,
                            EmployeeImport.attempt_count
                            < self.settings.reporting_worker_max_attempts,
                            or_(
                                and_(
                                    EmployeeImport.status.in_(
                                        (
                                            EmployeeImportStatus.QUEUED.value,
                                            EmployeeImportStatus.RETRY.value,
                                        )
                                    ),
                                    EmployeeImport.next_attempt_at <= now,
                                ),
                                and_(
                                    EmployeeImport.status == EmployeeImportStatus.PROCESSING.value,
                                    EmployeeImport.lease_expires_at < now,
                                ),
                            ),
                            EmployeeImport.expires_at > now,
                        )
                        .order_by(EmployeeImport.created_at, EmployeeImport.id)
                        .limit(self.settings.reporting_worker_import_batch_size)
                        .with_for_update(skip_locked=True)
                    )
                )
                for job in jobs:
                    job.status = EmployeeImportStatus.PROCESSING.value
                    job.attempt_count += 1
                    job.lease_expires_at = lease_until
                    job.next_attempt_at = None
                    job.failure_code = None
                    job.updated_at = now
                await session.flush()
                return [job.id for job in jobs]

    async def _claim_exports(self, tenant_id: UUID) -> list[UUID]:
        now = datetime.now(UTC)
        lease_until = now + timedelta(seconds=self.settings.reporting_worker_lease_seconds)
        async with self.session_factory() as session:
            configure_tenant_database_access(session, tenant_id)
            async with session.begin():
                await require_reporting_feature(session, tenant_id=tenant_id, write=True)
                exhausted = list(
                    await session.scalars(
                        select(ReportExportJob)
                        .where(
                            ReportExportJob.tenant_id == tenant_id,
                            ReportExportJob.status == ExportJobStatus.RUNNING.value,
                            ReportExportJob.lease_expires_at < now,
                            ReportExportJob.attempt_count
                            >= self.settings.reporting_worker_max_attempts,
                        )
                        .order_by(ReportExportJob.created_at, ReportExportJob.id)
                        .limit(self.settings.reporting_worker_export_batch_size)
                        .with_for_update(skip_locked=True)
                    )
                )
                for job in exhausted:
                    job.status = ExportJobStatus.FAILED.value
                    job.failure_code = "worker_failure"
                    job.next_attempt_at = None
                    job.lease_expires_at = None
                    job.updated_at = now
                    await _record_worker_export_event(
                        session,
                        job=job,
                        event_type=AuditEventType.REPORT_EXPORT_FAILED,
                        action="generate",
                        result=AuditResult.FAILURE,
                        metadata={
                            "report_type": job.report_type,
                            "export_format": job.format,
                            "failure_code": "worker_failure",
                            "attempt_count": job.attempt_count,
                        },
                    )
                jobs = list(
                    await session.scalars(
                        select(ReportExportJob)
                        .where(
                            ReportExportJob.tenant_id == tenant_id,
                            ReportExportJob.attempt_count
                            < self.settings.reporting_worker_max_attempts,
                            or_(
                                and_(
                                    ReportExportJob.status.in_(
                                        (
                                            ExportJobStatus.QUEUED.value,
                                            ExportJobStatus.RETRY.value,
                                        )
                                    ),
                                    ReportExportJob.next_attempt_at <= now,
                                ),
                                and_(
                                    ReportExportJob.status == ExportJobStatus.RUNNING.value,
                                    ReportExportJob.lease_expires_at < now,
                                ),
                            ),
                        )
                        .order_by(ReportExportJob.created_at, ReportExportJob.id)
                        .limit(self.settings.reporting_worker_export_batch_size)
                        .with_for_update(skip_locked=True)
                    )
                )
                for job in jobs:
                    job.status = ExportJobStatus.RUNNING.value
                    job.attempt_count += 1
                    job.lease_expires_at = lease_until
                    job.next_attempt_at = None
                    job.failure_code = None
                    job.updated_at = now
                await session.flush()
                return [job.id for job in jobs]

    async def _process_import(self, tenant_id: UUID, import_id: UUID) -> None:
        try:
            snapshot = await self._import_snapshot(tenant_id, import_id)
            if snapshot is None:
                return
            object_key, expected_size, expected_sha, file_format = snapshot
            with tempfile.TemporaryDirectory(prefix="wf-employee-import-worker-") as directory:
                local_path = Path(directory) / f"source.{file_format}"
                downloaded = await self.storage.download_to_path(
                    key=object_key,
                    destination=local_path,
                    maximum_bytes=EMPLOYEE_IMPORT_MAX_BYTES,
                )
                if downloaded.size_bytes != expected_size or downloaded.sha256 != expected_sha:
                    await self._terminal_import_failure(tenant_id, import_id, "invalid_file")
                    return
                try:
                    scan = await self.scanner.scan(local_path)
                except MalwareScanError:
                    await self._retry_import(tenant_id, import_id, "scanner_unavailable")
                    return
                if scan.verdict is MalwareScanVerdict.INFECTED:
                    await self._invalid_import(
                        tenant_id,
                        import_id,
                        scan_provider=scan.provider,
                        failure_code="infected_file",
                    )
                    return
                await self._validate_clean_import(
                    tenant_id,
                    import_id,
                    local_path,
                    scan_provider=scan.provider,
                )
        except ObjectStorageError:
            await self._retry_import(tenant_id, import_id, "storage_unavailable")
        except Exception as exc:
            _LOGGER.error(
                "Employee import job failed error_class=%s",
                type(exc).__name__,
            )
            await self._retry_import(tenant_id, import_id, "worker_failure")

    async def _import_snapshot(
        self, tenant_id: UUID, import_id: UUID
    ) -> tuple[str, int, str, str] | None:
        async with self.session_factory() as session:
            configure_tenant_database_access(session, tenant_id)
            async with session.begin():
                job = await session.scalar(
                    select(EmployeeImport).where(
                        EmployeeImport.tenant_id == tenant_id,
                        EmployeeImport.id == import_id,
                        EmployeeImport.status == EmployeeImportStatus.PROCESSING.value,
                    )
                )
                if job is None or job.source_sha256 is None:
                    return None
                return job.object_key, job.size_bytes, job.source_sha256, job.file_format

    async def _validate_clean_import(
        self,
        tenant_id: UUID,
        import_id: UUID,
        local_path: Path,
        *,
        scan_provider: str,
    ) -> None:
        async with self.session_factory() as session:
            configure_tenant_database_access(session, tenant_id)
            async with session.begin():
                job = await session.scalar(
                    select(EmployeeImport)
                    .where(
                        EmployeeImport.tenant_id == tenant_id,
                        EmployeeImport.id == import_id,
                        EmployeeImport.status == EmployeeImportStatus.PROCESSING.value,
                    )
                    .with_for_update()
                )
                if job is None:
                    return
                await session.execute(
                    delete(EmployeeImportIssue).where(
                        EmployeeImportIssue.tenant_id == tenant_id,
                        EmployeeImportIssue.import_id == import_id,
                    )
                )
                await session.execute(
                    delete(EmployeeImportRow).where(
                        EmployeeImportRow.tenant_id == tenant_id,
                        EmployeeImportRow.import_id == import_id,
                    )
                )
                issues = _IssueCollection()
                first_numbers: dict[str, int] = {}
                first_emails: dict[str, int] = {}
                digest = sha256()
                row_count = 0
                processed_since_flush = 0
                chunk: list[_ParsedImportRow] = []
                try:
                    for row_number, raw in iter_import_rows(local_path, job.file_format):
                        row_count += 1
                        processed_since_flush += 1
                        if row_count > EMPLOYEE_IMPORT_MAX_ROWS:
                            _add_issue(
                                issues,
                                import_id=import_id,
                                tenant_id=tenant_id,
                                row_number=EMPLOYEE_IMPORT_MAX_ROWS + 1,
                                code="row_limit_exceeded",
                            )
                            break
                        parsed = _parse_import_row(
                            raw,
                            row_number=row_number,
                            issues=issues,
                            import_id=import_id,
                            tenant_id=tenant_id,
                        )
                        if parsed is not None:
                            _track_file_duplicates(
                                parsed,
                                issues=issues,
                                first_numbers=first_numbers,
                                first_emails=first_emails,
                                import_id=import_id,
                                tenant_id=tenant_id,
                            )
                            chunk.append(parsed)
                        if processed_since_flush == _VALIDATION_CHUNK_SIZE:
                            if chunk:
                                await _validate_and_store_chunk(
                                    session,
                                    tenant_id=tenant_id,
                                    import_id=import_id,
                                    rows=chunk,
                                    issues=issues,
                                    digest=digest,
                                )
                                chunk = []
                            await _persist_new_issues(session, issues)
                            processed_since_flush = 0
                    if chunk:
                        await _validate_and_store_chunk(
                            session,
                            tenant_id=tenant_id,
                            import_id=import_id,
                            rows=chunk,
                            issues=issues,
                            digest=digest,
                        )
                except SpreadsheetFileError as exc:
                    _add_issue(
                        issues,
                        import_id=import_id,
                        tenant_id=tenant_id,
                        row_number=1,
                        code=(
                            exc.code
                            if exc.code in EMPLOYEE_IMPORT_ISSUE_MESSAGES
                            else "invalid_file"
                        ),
                    )
                if row_count == 0 and issues.total_count == 0:
                    _add_issue(
                        issues,
                        import_id=import_id,
                        tenant_id=tenant_id,
                        row_number=1,
                        code="empty_file",
                    )
                await _persist_new_issues(session, issues)
                error_count = issues.error_count
                warning_count = issues.warning_count
                now = datetime.now(UTC)
                job.scan_result = EmployeeImportScanResult.CLEAN.value
                job.scanner_provider = scan_provider[:64]
                job.row_count = min(row_count, EMPLOYEE_IMPORT_MAX_ROWS)
                job.error_count = error_count
                job.warning_count = warning_count
                job.validation_fingerprint = digest.hexdigest() if error_count == 0 else None
                job.status = (
                    EmployeeImportStatus.READY.value
                    if error_count == 0
                    else EmployeeImportStatus.INVALID.value
                )
                job.validated_at = now
                job.lease_expires_at = None
                job.next_attempt_at = None
                job.failure_code = None
                job.updated_at = now
                await session.flush()
                await _record_worker_import_event(
                    session,
                    job=job,
                    event_type=AuditEventType.EMPLOYEE_IMPORT_VALIDATED,
                    action="validate",
                    result=AuditResult.SUCCESS,
                    metadata={
                        "file_format": job.file_format,
                        "template_version": job.template_version,
                        "row_count": job.row_count,
                        "error_count": error_count,
                        "warning_count": warning_count,
                    },
                )

    async def _invalid_import(
        self,
        tenant_id: UUID,
        import_id: UUID,
        *,
        scan_provider: str,
        failure_code: str,
    ) -> None:
        async with self.session_factory() as session:
            configure_tenant_database_access(session, tenant_id)
            async with session.begin():
                job = await session.scalar(
                    select(EmployeeImport)
                    .where(
                        EmployeeImport.tenant_id == tenant_id,
                        EmployeeImport.id == import_id,
                    )
                    .with_for_update()
                )
                if job is None or job.status != EmployeeImportStatus.PROCESSING.value:
                    return
                issue = _new_issue(
                    import_id=import_id,
                    tenant_id=tenant_id,
                    row_number=1,
                    code="infected_file",
                )
                session.add(issue)
                await session.flush()
                now = datetime.now(UTC)
                job.status = EmployeeImportStatus.INVALID.value
                job.scan_result = EmployeeImportScanResult.INFECTED.value
                job.scanner_provider = scan_provider[:64]
                job.error_count = 1
                job.failure_code = failure_code
                job.validated_at = now
                job.lease_expires_at = None
                job.updated_at = now
                await session.flush()
                await _record_worker_import_event(
                    session,
                    job=job,
                    event_type=AuditEventType.EMPLOYEE_IMPORT_FAILED,
                    action="scan",
                    result=AuditResult.FAILURE,
                    metadata={
                        "file_format": job.file_format,
                        "template_version": job.template_version,
                        "failure_code": failure_code,
                        "attempt_count": job.attempt_count,
                    },
                )

    async def _terminal_import_failure(
        self, tenant_id: UUID, import_id: UUID, failure_code: str
    ) -> None:
        await self._set_import_failure(tenant_id, import_id, failure_code=failure_code, retry=False)

    async def _retry_import(self, tenant_id: UUID, import_id: UUID, failure_code: str) -> None:
        await self._set_import_failure(tenant_id, import_id, failure_code=failure_code, retry=True)

    async def _set_import_failure(
        self,
        tenant_id: UUID,
        import_id: UUID,
        *,
        failure_code: str,
        retry: bool,
    ) -> None:
        async with self.session_factory() as session:
            configure_tenant_database_access(session, tenant_id)
            async with session.begin():
                job = await session.scalar(
                    select(EmployeeImport)
                    .where(
                        EmployeeImport.tenant_id == tenant_id,
                        EmployeeImport.id == import_id,
                    )
                    .with_for_update()
                )
                if job is None or job.status != EmployeeImportStatus.PROCESSING.value:
                    return
                now = datetime.now(UTC)
                should_retry = (
                    retry and job.attempt_count < self.settings.reporting_worker_max_attempts
                )
                job.status = (
                    EmployeeImportStatus.RETRY.value
                    if should_retry
                    else EmployeeImportStatus.FAILED.value
                )
                job.failure_code = failure_code
                job.scan_result = (
                    EmployeeImportScanResult.ERROR.value
                    if failure_code == "scanner_unavailable"
                    else job.scan_result
                )
                job.next_attempt_at = (
                    now + timedelta(seconds=30 * (2 ** max(job.attempt_count - 1, 0)))
                    if should_retry
                    else None
                )
                job.lease_expires_at = None
                job.updated_at = now
                if not should_retry:
                    await _record_worker_import_event(
                        session,
                        job=job,
                        event_type=AuditEventType.EMPLOYEE_IMPORT_FAILED,
                        action="process",
                        result=AuditResult.FAILURE,
                        metadata={
                            "file_format": job.file_format,
                            "template_version": job.template_version,
                            "failure_code": failure_code,
                            "attempt_count": job.attempt_count,
                        },
                    )

    async def _process_export(self, tenant_id: UUID, export_id: UUID) -> None:
        artifact_key: str | None = None
        try:
            snapshot = await self._export_snapshot(tenant_id, export_id)
            if snapshot is None:
                return
            (
                requester_id,
                report_type,
                export_format,
                request_scope,
                request_scope_user_id,
                request_fields,
                filters,
            ) = snapshot
            authorization, fields = await self._current_export_authorization(
                tenant_id=tenant_id,
                requester_id=requester_id,
                report_type=report_type,
                request_scope=request_scope,
                request_scope_user_id=request_scope_user_id,
                request_fields=request_fields,
            )
            with tempfile.TemporaryDirectory(prefix="wf-report-export-worker-") as directory:
                output = Path(directory) / f"report.{export_format}"
                row_count = await self._write_export(
                    tenant_id=tenant_id,
                    export_id=export_id,
                    report_type=report_type,
                    authorization=authorization,
                    fields=fields,
                    filters=filters,
                    export_format=export_format,
                    destination=output,
                )
                if output.stat().st_size > self.settings.export_max_file_size_bytes:
                    raise _ExportFileLimitError()
                artifact_key = f"{tenant_id}/{export_id}/{uuid4().hex}.{export_format}"
                content_type = (
                    "text/csv; charset=utf-8"
                    if export_format == "csv"
                    else "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )
                uploaded = await self.storage.upload_from_path(
                    key=artifact_key,
                    source=output,
                    content_type=content_type,
                    metadata={"resource": "report-export"},
                    maximum_bytes=self.settings.export_max_file_size_bytes,
                )
                completed = await self._complete_export(
                    tenant_id=tenant_id,
                    export_id=export_id,
                    artifact_key=artifact_key,
                    content_type=content_type,
                    sha256_value=uploaded.sha256,
                    size_bytes=uploaded.size_bytes,
                    row_count=row_count,
                    authorization=authorization,
                    fields=fields,
                )
                if not completed:
                    await self.storage.delete(artifact_key)
        except (ReportingAccessDeniedError, ReportingFeatureUnavailableError):
            if artifact_key is not None:
                try:
                    await self.storage.delete(artifact_key)
                except ObjectStorageError:
                    pass
            await self._fail_export(
                tenant_id, export_id, failure_code="authorization_revoked", retry=False
            )
        except _ExportRowLimitError:
            await self._fail_export(
                tenant_id, export_id, failure_code="row_limit_exceeded", retry=False
            )
        except _ExportFileLimitError:
            await self._fail_export(
                tenant_id, export_id, failure_code="file_too_large", retry=False
            )
        except _ExportCancelledError:
            return
        except (ReportingValidationError, ValidationError):
            await self._fail_export(
                tenant_id, export_id, failure_code="worker_failure", retry=False
            )
        except ObjectStorageError:
            if artifact_key is not None:
                try:
                    await self.storage.delete(artifact_key)
                except ObjectStorageError:
                    pass
            await self._fail_export(
                tenant_id, export_id, failure_code="storage_unavailable", retry=True
            )
        except Exception as exc:
            _LOGGER.error(
                "Report export job failed error_class=%s",
                type(exc).__name__,
            )
            if artifact_key is not None:
                registered = await self._artifact_registration_state(
                    tenant_id=tenant_id,
                    export_id=export_id,
                    artifact_key=artifact_key,
                )
                if registered is True:
                    return
                if registered is False:
                    try:
                        await self.storage.delete(artifact_key)
                    except ObjectStorageError:
                        pass
            await self._fail_export(tenant_id, export_id, failure_code="worker_failure", retry=True)

    async def _artifact_registration_state(
        self,
        *,
        tenant_id: UUID,
        export_id: UUID,
        artifact_key: str,
    ) -> bool | None:
        """Resolve a potentially committed completion without risking its private object."""

        try:
            async with self.session_factory() as session:
                configure_tenant_database_access(session, tenant_id)
                async with session.begin():
                    registered_id = await session.scalar(
                        select(ReportExportJob.id).where(
                            ReportExportJob.tenant_id == tenant_id,
                            ReportExportJob.id == export_id,
                            ReportExportJob.status.in_(
                                (
                                    ExportJobStatus.SUCCEEDED.value,
                                    ExportJobStatus.EXPIRED.value,
                                )
                            ),
                            ReportExportJob.artifact_object_key == artifact_key,
                        )
                    )
            return registered_id is not None
        except Exception:
            return None

    async def _export_snapshot(self, tenant_id: UUID, export_id: UUID):
        async with self.session_factory() as session:
            configure_tenant_database_access(session, tenant_id)
            async with session.begin():
                job = await session.scalar(
                    select(ReportExportJob).where(
                        ReportExportJob.tenant_id == tenant_id,
                        ReportExportJob.id == export_id,
                        ReportExportJob.status == ExportJobStatus.RUNNING.value,
                    )
                )
                if job is None:
                    return None
                return (
                    job.requested_by_user_id,
                    ReportType(job.report_type),
                    job.format,
                    ReportScope(job.request_scope),
                    job.request_scope_user_id,
                    tuple(job.fields_snapshot),
                    dict(job.filters_snapshot),
                )

    async def _current_export_authorization(
        self,
        *,
        tenant_id: UUID,
        requester_id: UUID,
        report_type: ReportType,
        request_scope: ReportScope,
        request_scope_user_id: UUID | None,
        request_fields: tuple[str, ...],
    ):
        async with self.session_factory() as session:
            configure_tenant_database_access(session, tenant_id)
            async with session.begin():
                await require_reporting_feature(
                    session,
                    tenant_id=tenant_id,
                    write=True,
                )
                return await _reauthorize_export(
                    session,
                    tenant_id=tenant_id,
                    requester_id=requester_id,
                    report_type=report_type,
                    request_scope=request_scope,
                    request_scope_user_id=request_scope_user_id,
                    request_fields=request_fields,
                )

    async def _write_export(
        self,
        *,
        tenant_id: UUID,
        export_id: UUID,
        report_type: ReportType,
        authorization,
        fields: tuple[str, ...],
        filters: dict,
        export_format: str,
        destination: Path,
    ) -> int:
        csv_handle = None
        workbook = None
        sheet = None
        if export_format == "csv":
            csv_handle = destination.open("w", encoding="utf-8-sig", newline="")
            writer = csv.writer(csv_handle, lineterminator="\r\n")
            writer.writerow(fields)
            csv_handle.flush()
        else:
            workbook = Workbook(write_only=True)
            sheet = workbook.create_sheet("report")
            sheet.append(list(fields))
            writer = None
        xlsx_estimated_bytes = _xlsx_row_cost(fields) if workbook is not None else 0
        row_count = 0
        cursor = None
        try:
            async with self.session_factory() as session:
                configure_tenant_database_access(session, tenant_id)
                async with session.begin():
                    await require_reporting_feature(session, tenant_id=tenant_id)
                    service = ReportService(session=session)
                    while True:
                        current_status = await session.scalar(
                            select(ReportExportJob.status).where(
                                ReportExportJob.tenant_id == tenant_id,
                                ReportExportJob.id == export_id,
                            )
                        )
                        if current_status != ExportJobStatus.RUNNING.value:
                            raise _ExportCancelledError()
                        page = await service.page_for_export(
                            report_type=report_type,
                            tenant_id=tenant_id,
                            authorization=authorization,
                            fields=fields,
                            filters=filters,
                            limit=_EXPORT_PAGE_SIZE,
                            cursor=cursor,
                        )
                        for item in page.items:
                            row_count += 1
                            if row_count > EXPORT_MAX_ROWS:
                                raise _ExportRowLimitError()
                            values = [spreadsheet_safe(item.values.get(field)) for field in fields]
                            if any(len(value) > 32_767 for value in values):
                                raise _ExportFileLimitError()
                            if writer is not None:
                                writer.writerow(values)
                                assert csv_handle is not None
                                csv_handle.flush()
                                if (
                                    destination.stat().st_size
                                    > self.settings.export_max_file_size_bytes
                                ):
                                    raise _ExportFileLimitError()
                            else:
                                assert sheet is not None
                                xlsx_estimated_bytes += _xlsx_row_cost(values)
                                if (
                                    xlsx_estimated_bytes
                                    > self.settings.export_max_file_size_bytes * 2
                                ):
                                    raise _ExportFileLimitError()
                                sheet.append(values)
                        if page.next_cursor is None:
                            break
                        cursor = page.next_cursor
            if workbook is not None:
                workbook.save(destination)
            if destination.stat().st_size > self.settings.export_max_file_size_bytes:
                raise _ExportFileLimitError()
            return row_count
        finally:
            if csv_handle is not None:
                csv_handle.close()
            if workbook is not None:
                workbook.close()

    async def _complete_export(
        self,
        *,
        tenant_id: UUID,
        export_id: UUID,
        artifact_key: str,
        content_type: str,
        sha256_value: str,
        size_bytes: int,
        row_count: int,
        authorization,
        fields: tuple[str, ...],
    ) -> bool:
        now = datetime.now(UTC)
        async with self.session_factory() as session:
            configure_tenant_database_access(session, tenant_id)
            async with session.begin():
                await require_reporting_feature(
                    session,
                    tenant_id=tenant_id,
                    write=True,
                )
                job = await session.scalar(
                    select(ReportExportJob)
                    .where(
                        ReportExportJob.tenant_id == tenant_id,
                        ReportExportJob.id == export_id,
                    )
                    .with_for_update()
                )
                if job is None or job.status != ExportJobStatus.RUNNING.value:
                    return False
                current, current_fields = await _reauthorize_export(
                    session,
                    tenant_id=tenant_id,
                    requester_id=job.requested_by_user_id,
                    report_type=ReportType(job.report_type),
                    request_scope=ReportScope(job.request_scope),
                    request_scope_user_id=job.request_scope_user_id,
                    request_fields=tuple(job.fields_snapshot),
                )
                if not authorization_covers_artifact(
                    current=current,
                    artifact_scope=authorization.scope,
                    artifact_scope_user_id=authorization.scope_user_id,
                ) or not set(fields) <= set(current_fields):
                    raise ReportingAccessDeniedError()
                classifications = _field_classifications(ReportType(job.report_type), fields)
                job.status = ExportJobStatus.SUCCEEDED.value
                job.generated_scope = authorization.scope.value
                job.generated_scope_user_id = authorization.scope_user_id
                job.generated_fields = list(fields)
                job.field_classifications = classifications
                job.artifact_object_key = artifact_key
                job.artifact_sha256 = sha256_value
                job.artifact_content_type = content_type
                job.size_bytes = size_bytes
                job.row_count = row_count
                job.available_at = now
                job.expires_at = now + timedelta(hours=self.settings.export_artifact_ttl_hours)
                job.lease_expires_at = None
                job.next_attempt_at = None
                job.failure_code = None
                job.updated_at = now
                await session.flush()
                await _record_worker_export_event(
                    session,
                    job=job,
                    event_type=AuditEventType.REPORT_EXPORT_COMPLETED,
                    action="generate",
                    result=AuditResult.SUCCESS,
                    metadata={
                        "report_type": job.report_type,
                        "export_format": job.format,
                        "report_scope": job.generated_scope,
                        "row_count": row_count,
                        "field_count": len(fields),
                        "field_classifications": classifications,
                    },
                )
                return True

    async def _fail_export(
        self,
        tenant_id: UUID,
        export_id: UUID,
        *,
        failure_code: str,
        retry: bool,
    ) -> None:
        async with self.session_factory() as session:
            configure_tenant_database_access(session, tenant_id)
            async with session.begin():
                job = await session.scalar(
                    select(ReportExportJob)
                    .where(
                        ReportExportJob.tenant_id == tenant_id,
                        ReportExportJob.id == export_id,
                    )
                    .with_for_update()
                )
                if job is None or job.status != ExportJobStatus.RUNNING.value:
                    return
                now = datetime.now(UTC)
                should_retry = (
                    retry and job.attempt_count < self.settings.reporting_worker_max_attempts
                )
                job.status = (
                    ExportJobStatus.RETRY.value if should_retry else ExportJobStatus.FAILED.value
                )
                job.failure_code = failure_code
                job.next_attempt_at = (
                    now + timedelta(seconds=30 * (2 ** max(job.attempt_count - 1, 0)))
                    if should_retry
                    else None
                )
                job.lease_expires_at = None
                job.updated_at = now
                if not should_retry:
                    await _record_worker_export_event(
                        session,
                        job=job,
                        event_type=AuditEventType.REPORT_EXPORT_FAILED,
                        action="generate",
                        result=AuditResult.FAILURE,
                        metadata={
                            "report_type": job.report_type,
                            "export_format": job.format,
                            "failure_code": failure_code,
                            "attempt_count": job.attempt_count,
                        },
                    )

    async def _expire_artifacts(self, tenant_id: UUID) -> None:
        async with self.session_factory() as session:
            configure_tenant_database_access(session, tenant_id)
            async with session.begin():
                now = await session.scalar(select(func.now()))
                if now is None:
                    return
                exports = list(
                    await session.scalars(
                        select(ReportExportJob)
                        .where(
                            ReportExportJob.tenant_id == tenant_id,
                            ReportExportJob.status == ExportJobStatus.SUCCEEDED.value,
                            ReportExportJob.expires_at <= now,
                        )
                        .order_by(ReportExportJob.expires_at, ReportExportJob.id)
                        .limit(10)
                        .with_for_update(skip_locked=True)
                    )
                )
                for job in exports:
                    if job.artifact_object_key is None:
                        continue
                    try:
                        await self.storage.delete(job.artifact_object_key)
                    except ObjectStorageError:
                        continue
                    job.status = ExportJobStatus.EXPIRED.value
                    job.updated_at = now
                    await _record_worker_export_event(
                        session,
                        job=job,
                        event_type=AuditEventType.REPORT_EXPORT_EXPIRED,
                        action="expire",
                        result=AuditResult.SUCCESS,
                        metadata={
                            "report_type": job.report_type,
                            "export_format": job.format,
                            "row_count": job.row_count or 0,
                        },
                    )
                imports = list(
                    await session.scalars(
                        select(EmployeeImport)
                        .where(
                            EmployeeImport.tenant_id == tenant_id,
                            EmployeeImport.expires_at <= now,
                            EmployeeImport.source_deleted_at.is_(None),
                        )
                        .order_by(EmployeeImport.expires_at, EmployeeImport.id)
                        .limit(10)
                        .with_for_update(skip_locked=True)
                    )
                )
                for job in imports:
                    try:
                        await self.storage.delete(job.object_key)
                    except ObjectStorageError:
                        continue
                    await session.execute(
                        delete(EmployeeImportIssue).where(
                            EmployeeImportIssue.tenant_id == tenant_id,
                            EmployeeImportIssue.import_id == job.id,
                        )
                    )
                    await session.execute(
                        delete(EmployeeImportRow).where(
                            EmployeeImportRow.tenant_id == tenant_id,
                            EmployeeImportRow.import_id == job.id,
                        )
                    )
                    job.source_deleted_at = now
                    changed_fields = ["source_deleted_at"]
                    if job.status != EmployeeImportStatus.SUCCEEDED.value:
                        job.status = EmployeeImportStatus.EXPIRED.value
                        job.next_attempt_at = None
                        job.lease_expires_at = None
                        changed_fields.append("status")
                    job.updated_at = now
                    await _record_worker_import_event(
                        session,
                        job=job,
                        event_type=AuditEventType.EMPLOYEE_IMPORT_SOURCE_EXPIRED,
                        action="expire_source",
                        result=AuditResult.SUCCESS,
                        changed_fields=tuple(changed_fields),
                        metadata={
                            "file_format": job.file_format,
                            "template_version": job.template_version,
                            "row_count": job.row_count,
                        },
                    )


async def _reauthorize_export(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    requester_id: UUID,
    report_type: ReportType,
    request_scope: ReportScope,
    request_scope_user_id: UUID | None,
    request_fields: tuple[str, ...],
) -> tuple[ReportAuthorization, tuple[str, ...]]:
    user = await session.scalar(
        select(User).where(
            User.tenant_id == tenant_id,
            User.id == requester_id,
            User.status == UserStatus.ACTIVE.value,
        )
    )
    if user is None:
        raise ReportingAccessDeniedError()
    snapshot = await load_authorization_snapshot(
        session,
        tenant_id=tenant_id,
        user_id=requester_id,
    )
    current = resolve_report_authorization(
        permissions=snapshot.permissions,
        actor_id=requester_id,
        require_export=True,
    )
    reduced = reduce_report_authorization(
        request_scope=request_scope,
        request_scope_user_id=request_scope_user_id,
        current=current,
    )
    fields = reduce_requested_fields(
        report_type=report_type,
        request_fields=request_fields,
        permissions=snapshot.permissions,
    )
    if not fields:
        raise ReportingAccessDeniedError()
    return reduced, fields


async def _validate_and_store_chunk(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    import_id: UUID,
    rows: list[_ParsedImportRow],
    issues: dict[tuple[int, str, str | None], EmployeeImportIssue],
    digest,
) -> None:
    numbers = {row.employee_number_normalized for row in rows}
    emails = {row.work_email_normalized for row in rows if row.work_email_normalized is not None}
    existing = list(
        await session.scalars(
            select(Employee).where(
                Employee.tenant_id == tenant_id,
                or_(
                    Employee.employee_number_normalized.in_(numbers),
                    Employee.email_normalized.in_(emails) if emails else False,
                ),
            )
        )
    )
    existing_numbers = {employee.employee_number_normalized for employee in existing}
    existing_emails = {
        employee.email_normalized for employee in existing if employee.email_normalized is not None
    }
    legal_codes = {row.legal_entity_code for row in rows}
    branch_codes = {row.branch_code for row in rows}
    department_codes = {row.department_code for row in rows}
    position_codes = {row.position_code for row in rows}
    legal_entities = {
        record.code_normalized: record
        for record in await session.scalars(
            select(LegalEntity).where(
                LegalEntity.tenant_id == tenant_id,
                LegalEntity.code_normalized.in_(legal_codes),
            )
        )
    }
    branches = {
        record.code_normalized: record
        for record in await session.scalars(
            select(Branch).where(
                Branch.tenant_id == tenant_id,
                Branch.code_normalized.in_(branch_codes),
            )
        )
    }
    departments = {
        record.code_normalized: record
        for record in await session.scalars(
            select(Department).where(
                Department.tenant_id == tenant_id,
                Department.code_normalized.in_(department_codes),
            )
        )
    }
    positions = {
        record.code_normalized: record
        for record in await session.scalars(
            select(Position).where(
                Position.tenant_id == tenant_id,
                Position.code_normalized.in_(position_codes),
            )
        )
    }
    for row in rows:
        if row.employee_number_normalized in existing_numbers:
            _add_issue(
                issues,
                import_id=import_id,
                tenant_id=tenant_id,
                row_number=row.row_number,
                code="duplicate_employee_number_tenant",
                field="employee_number",
            )
        if row.work_email_normalized is not None and row.work_email_normalized in existing_emails:
            _add_issue(
                issues,
                import_id=import_id,
                tenant_id=tenant_id,
                row_number=row.row_number,
                code="duplicate_work_email_tenant",
                field="work_email",
            )
        legal_entity = legal_entities.get(row.legal_entity_code)
        branch = branches.get(row.branch_code)
        department = departments.get(row.department_code)
        position = positions.get(row.position_code)
        _validate_reference(
            legal_entity,
            active=(
                legal_entity is not None and legal_entity.status == LegalEntityStatus.ACTIVE.value
            ),
            row=row,
            field="legal_entity_code",
            issues=issues,
            import_id=import_id,
            tenant_id=tenant_id,
        )
        _validate_reference(
            branch,
            active=(
                branch is not None
                and branch.status == BranchStatus.ACTIVE.value
                and branch.archived_at is None
            ),
            row=row,
            field="branch_code",
            issues=issues,
            import_id=import_id,
            tenant_id=tenant_id,
        )
        _validate_reference(
            department,
            active=(
                department is not None
                and department.status == DepartmentStatus.ACTIVE.value
                and department.archived_at is None
            ),
            row=row,
            field="department_code",
            issues=issues,
            import_id=import_id,
            tenant_id=tenant_id,
        )
        _validate_reference(
            position,
            active=(
                position is not None
                and position.status == PositionStatus.ACTIVE.value
                and position.archived_at is None
            ),
            row=row,
            field="position_code",
            issues=issues,
            import_id=import_id,
            tenant_id=tenant_id,
        )
        if (
            branch is not None
            and legal_entity is not None
            and branch.legal_entity_id != legal_entity.id
        ):
            _add_issue(
                issues,
                import_id=import_id,
                tenant_id=tenant_id,
                row_number=row.row_number,
                code="reference_mismatch",
                field="branch_code",
            )
        if isinstance(issues, _IssueCollection) and row.row_number in issues.error_rows:
            continue
        assert legal_entity is not None and branch is not None
        assert department is not None and position is not None
        stored = EmployeeImportRow(
            id=uuid5(NAMESPACE_URL, f"wealthy-falcon:import:{import_id}:{row.row_number}:row"),
            tenant_id=tenant_id,
            import_id=import_id,
            row_number=row.row_number,
            employee_number=row.employee_number,
            employee_number_normalized=row.employee_number_normalized,
            first_name=row.first_name,
            last_name=row.last_name,
            work_email=row.work_email,
            work_email_normalized=row.work_email_normalized,
            status=row.status,
            employment_start_date=row.employment_start_date,
            employment_end_date=row.employment_end_date,
            legal_entity_code=row.legal_entity_code,
            branch_code=row.branch_code,
            department_code=row.department_code,
            position_code=row.position_code,
            legal_entity_id=legal_entity.id,
            branch_id=branch.id,
            department_id=department.id,
            position_id=position.id,
        )
        session.add(stored)
        digest.update(canonical_import_row(stored))
    await session.flush()


def _parse_import_row(
    raw: dict[str, str],
    *,
    row_number: int,
    issues: dict[tuple[int, str, str | None], EmployeeImportIssue],
    import_id: UUID,
    tenant_id: UUID,
) -> _ParsedImportRow | None:
    values = {field: raw[field].strip() for field in EMPLOYEE_IMPORT_FIELDS}
    for field, value in values.items():
        if value and value.lstrip(" ")[0] in _FORMULA_PREFIXES:
            _add_issue(
                issues,
                import_id=import_id,
                tenant_id=tenant_id,
                row_number=row_number,
                code="formula_not_allowed",
                field=field,
            )
    for field in (
        "employee_number",
        "first_name",
        "last_name",
        "status",
        "employment_start_date",
        "legal_entity_code",
        "branch_code",
        "department_code",
        "position_code",
    ):
        if not values[field]:
            _add_issue(
                issues,
                import_id=import_id,
                tenant_id=tenant_id,
                row_number=row_number,
                code="required",
                field=field,
            )
    maximum_lengths = {
        "employee_number": 64,
        "first_name": 200,
        "last_name": 200,
        "work_email": 320,
        "status": 32,
        "legal_entity_code": 32,
        "branch_code": 32,
        "department_code": 32,
        "position_code": 32,
    }
    for field, maximum in maximum_lengths.items():
        if len(values[field]) > maximum:
            _add_issue(
                issues,
                import_id=import_id,
                tenant_id=tenant_id,
                row_number=row_number,
                code="value_too_long",
                field=field,
            )
    if values["status"] not in {"active", "on_leave"}:
        _add_issue(
            issues,
            import_id=import_id,
            tenant_id=tenant_id,
            row_number=row_number,
            code="invalid_status",
            field="status",
        )
    if values["work_email"] and not EMAIL_PATTERN.fullmatch(values["work_email"]):
        _add_issue(
            issues,
            import_id=import_id,
            tenant_id=tenant_id,
            row_number=row_number,
            code="invalid_email",
            field="work_email",
        )
    start_date = _parse_date(
        values["employment_start_date"],
        field="employment_start_date",
        row_number=row_number,
        issues=issues,
        import_id=import_id,
        tenant_id=tenant_id,
        required=True,
    )
    end_date = _parse_date(
        values["employment_end_date"],
        field="employment_end_date",
        row_number=row_number,
        issues=issues,
        import_id=import_id,
        tenant_id=tenant_id,
        required=False,
    )
    if start_date is not None and end_date is not None and end_date < start_date:
        _add_issue(
            issues,
            import_id=import_id,
            tenant_id=tenant_id,
            row_number=row_number,
            code="invalid_date_order",
            field="employment_end_date",
        )
    if end_date is not None:
        _add_issue(
            issues,
            import_id=import_id,
            tenant_id=tenant_id,
            row_number=row_number,
            code="employment_end_date_not_supported",
            field="employment_end_date",
        )
    if start_date is not None and start_date > date.today():
        _add_issue(
            issues,
            import_id=import_id,
            tenant_id=tenant_id,
            row_number=row_number,
            code="future_start_date",
            field="employment_start_date",
            severity="warning",
        )
    if isinstance(issues, _IssueCollection) and row_number in issues.error_rows:
        return None
    assert start_date is not None
    try:
        EmployeeCreate(
            employee_number=values["employee_number"],
            first_name=values["first_name"],
            last_name=values["last_name"],
            email=values["work_email"] or None,
            status=values["status"],
            employment_start_date=start_date,
            employment_end_date=None,
        )
    except ValidationError:
        _add_issue(
            issues,
            import_id=import_id,
            tenant_id=tenant_id,
            row_number=row_number,
            code="invalid_file",
        )
        return None
    return _ParsedImportRow(
        row_number=row_number,
        employee_number=values["employee_number"],
        employee_number_normalized=_normalize(values["employee_number"]),
        first_name=values["first_name"],
        last_name=values["last_name"],
        work_email=values["work_email"] or None,
        work_email_normalized=(_normalize(values["work_email"]) if values["work_email"] else None),
        status=values["status"],
        employment_start_date=start_date,
        employment_end_date=None,
        legal_entity_code=_normalize(values["legal_entity_code"]),
        branch_code=_normalize(values["branch_code"]),
        department_code=_normalize(values["department_code"]),
        position_code=_normalize(values["position_code"]),
    )


def _track_file_duplicates(
    row: _ParsedImportRow,
    *,
    issues: dict[tuple[int, str, str | None], EmployeeImportIssue],
    first_numbers: dict[str, int],
    first_emails: dict[str, int],
    import_id: UUID,
    tenant_id: UUID,
) -> None:
    _track_duplicate(
        row.employee_number_normalized,
        row_number=row.row_number,
        first_rows=first_numbers,
        code="duplicate_employee_number_file",
        field="employee_number",
        issues=issues,
        import_id=import_id,
        tenant_id=tenant_id,
    )
    if row.work_email_normalized is not None:
        _track_duplicate(
            row.work_email_normalized,
            row_number=row.row_number,
            first_rows=first_emails,
            code="duplicate_work_email_file",
            field="work_email",
            issues=issues,
            import_id=import_id,
            tenant_id=tenant_id,
        )


def _track_duplicate(
    value: str,
    *,
    row_number: int,
    first_rows: dict[str, int],
    code: str,
    field: str,
    issues: dict[tuple[int, str, str | None], EmployeeImportIssue],
    import_id: UUID,
    tenant_id: UUID,
) -> None:
    first = first_rows.setdefault(value, row_number)
    if first == row_number:
        return
    for duplicate_row in (first, row_number):
        _add_issue(
            issues,
            import_id=import_id,
            tenant_id=tenant_id,
            row_number=duplicate_row,
            code=code,
            field=field,
        )


def _validate_reference(
    reference,
    *,
    active: bool,
    row: _ParsedImportRow,
    field: str,
    issues: dict[tuple[int, str, str | None], EmployeeImportIssue],
    import_id: UUID,
    tenant_id: UUID,
) -> None:
    if reference is None:
        code = "invalid_reference"
    elif not active:
        code = "inactive_reference"
    else:
        return
    _add_issue(
        issues,
        import_id=import_id,
        tenant_id=tenant_id,
        row_number=row.row_number,
        code=code,
        field=field,
    )


def _parse_date(
    value: str,
    *,
    field: str,
    row_number: int,
    issues: dict[tuple[int, str, str | None], EmployeeImportIssue],
    import_id: UUID,
    tenant_id: UUID,
    required: bool,
) -> date | None:
    if not value:
        return None
    try:
        parsed = date.fromisoformat(value)
    except ValueError:
        parsed = None
    if parsed is None or parsed.isoformat() != value:
        _add_issue(
            issues,
            import_id=import_id,
            tenant_id=tenant_id,
            row_number=row_number,
            code="invalid_date",
            field=field,
        )
        return None
    return parsed


def _add_issue(
    issues: dict[tuple[int, str, str | None], EmployeeImportIssue],
    *,
    import_id: UUID,
    tenant_id: UUID,
    row_number: int,
    code: str,
    field: str | None = None,
    severity: str = "error",
) -> None:
    key = (row_number, code, field)
    seen_keys = issues.seen_keys if isinstance(issues, _IssueCollection) else issues.keys()
    if key not in seen_keys:
        issues[key] = _new_issue(
            import_id=import_id,
            tenant_id=tenant_id,
            row_number=row_number,
            code=code,
            field=field,
            severity=severity,
        )
        if isinstance(issues, _IssueCollection):
            issues.seen_keys.add(key)
            if severity == "error":
                issues.error_rows.add(row_number)
                issues.error_count += 1
            else:
                issues.warning_count += 1


async def _persist_new_issues(
    session: AsyncSession,
    issues: _IssueCollection,
) -> None:
    if not issues:
        return
    pending = list(issues.values())
    session.add_all(pending)
    await session.flush()
    issues.clear()
    for issue in pending:
        session.sync_session.expunge(issue)


def _new_issue(
    *,
    import_id: UUID,
    tenant_id: UUID,
    row_number: int,
    code: str,
    field: str | None = None,
    severity: str = "error",
) -> EmployeeImportIssue:
    return EmployeeImportIssue(
        id=uuid5(
            NAMESPACE_URL,
            f"wealthy-falcon:import:{import_id}:issue:"
            f"{row_number}:{severity}:{code}:{field or '-'}",
        ),
        tenant_id=tenant_id,
        import_id=import_id,
        row_number=row_number,
        severity=severity,
        code=code,
        field=field,
        message=EMPLOYEE_IMPORT_ISSUE_MESSAGES.get(
            code,
            EMPLOYEE_IMPORT_ISSUE_MESSAGES["invalid_file"],
        ),
    )


def _normalize(value: str) -> str:
    return value.strip().lower()


def _field_classifications(report_type: ReportType, fields: tuple[str, ...]) -> list[str]:
    values = {"work_safe"}
    if report_type is ReportType.EMPLOYEES and "work_email" in fields:
        values.add("work_contact")
    if report_type in {ReportType.LEAVES, ReportType.MISSING_DOCUMENTS}:
        values.add("hr_metadata")
    return sorted(values)


def _xlsx_row_cost(values: Sequence[str]) -> int:
    """Conservatively bound write-only worksheet XML before archive finalization."""

    return 64 + sum(
        len(xml_escape(value, {'"': "&quot;", "'": "&apos;"}).encode("utf-8")) + 96
        for value in values
    )


async def _record_worker_export_event(
    session: AsyncSession,
    *,
    job: ReportExportJob,
    event_type: AuditEventType,
    action: str,
    result: AuditResult,
    metadata: dict[str, object],
) -> None:
    await SqlAlchemyAuditRecorder(session).record(
        AuditEventDraft(
            scope_type=AuditScopeType.TENANT,
            tenant_id=job.tenant_id,
            actor_type=AuditActorType.WORKER,
            event_type=event_type,
            category=AuditCategory.HR_OPERATIONS,
            resource_type="report_export_job",
            resource_id=job.id,
            action=action,
            result=result,
            context=AuditContext.internal(),
            changed_fields=("status",),
            metadata=metadata,
            data_classification=AuditDataClassification.HR_METADATA,
            visibility_class=AuditVisibilityClass.HR_OPERATIONS,
        )
    )


async def _record_worker_import_event(
    session: AsyncSession,
    *,
    job: EmployeeImport,
    event_type: AuditEventType,
    action: str,
    result: AuditResult,
    changed_fields: tuple[str, ...] = ("status",),
    metadata: dict[str, object],
) -> None:
    await SqlAlchemyAuditRecorder(session).record(
        AuditEventDraft(
            scope_type=AuditScopeType.TENANT,
            tenant_id=job.tenant_id,
            actor_type=AuditActorType.WORKER,
            event_type=event_type,
            category=AuditCategory.HR_OPERATIONS,
            resource_type="employee_import",
            resource_id=job.id,
            action=action,
            result=result,
            context=AuditContext.internal(),
            changed_fields=changed_fields,
            metadata=metadata,
            data_classification=AuditDataClassification.HR_METADATA,
            visibility_class=AuditVisibilityClass.HR_OPERATIONS,
        )
    )


async def run_worker() -> None:
    operational_logger = configure_operational_logger()
    try:
        settings = get_settings()
    except Exception as exc:
        log_worker_failed(
            operational_logger,
            worker="reporting",
            error=exc,
        )
        raise
    log_worker_started(
        operational_logger,
        service=settings.app_name,
        version=settings.app_version,
        commit_sha=settings.release_commit_sha,
        worker="reporting",
    )
    try:
        last_heartbeat_at = monotonic()
        aggregate_processed_count = 0
        database_runtime = create_database_runtime(settings)
        try:
            document_runtime = create_document_runtime(settings)
            try:
                await document_runtime.initialize()
                worker = ReportingWorker(
                    session_factory=database_runtime.session_factory,
                    settings=settings,
                    storage=document_runtime.storage,
                    scanner=document_runtime.scanner,
                )
                while True:
                    cycle_started_at = monotonic()
                    processed_count = await worker.run_once()
                    cycle_finished_at = monotonic()
                    cycle_duration_ms = max(
                        0.0,
                        (cycle_finished_at - cycle_started_at) * 1000,
                    )
                    aggregate_processed_count += processed_count
                    if (
                        cycle_finished_at - last_heartbeat_at
                        >= settings.worker_heartbeat_interval_seconds
                    ):
                        log_worker_heartbeat(
                            operational_logger,
                            service=settings.app_name,
                            version=settings.app_version,
                            commit_sha=settings.release_commit_sha,
                            worker="reporting",
                            cycle_duration_ms=cycle_duration_ms,
                            processed_count=aggregate_processed_count,
                        )
                        aggregate_processed_count = 0
                        last_heartbeat_at = monotonic()
                    await asyncio.sleep(settings.reporting_worker_poll_seconds)
            finally:
                await document_runtime.close()
        finally:
            await database_runtime.dispose()
    except Exception as exc:
        log_worker_failed(
            operational_logger,
            worker="reporting",
            error=exc,
        )
        raise
    finally:
        log_worker_stopped(
            operational_logger,
            service=settings.app_name,
            version=settings.app_version,
            commit_sha=settings.release_commit_sha,
            worker="reporting",
        )


def main() -> None:
    asyncio.run(run_worker())


if __name__ == "__main__":
    main()


__all__ = ["ReportingWorker", "main", "run_worker"]
