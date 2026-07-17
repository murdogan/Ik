"""Private import upload/read commands and atomic idempotent employee commit."""

from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta
from hashlib import sha256
from pathlib import Path
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

from sqlalchemy import and_, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.department import Department, DepartmentStatus
from app.models.employee import Employee
from app.models.employee_assignment import EmployeeAssignment
from app.models.employee_import import (
    EmployeeImport,
    EmployeeImportIssue,
    EmployeeImportRow,
    EmployeeImportScanResult,
    EmployeeImportStatus,
)
from app.models.organization import Branch, BranchStatus, LegalEntity, LegalEntityStatus
from app.models.position import Position, PositionStatus
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
from app.platform.db import (
    SqlAlchemyUnitOfWork,
    configure_tenant_database_access,
    constraint_name_from_error,
)
from app.platform.idempotency import command_fingerprint
from app.platform.pagination import decode_cursor, encode_cursor
from app.platform.request_context import RequestContext
from app.platform.storage import ObjectStorage, ObjectStorageError
from app.schemas.employee import EmployeeCreate
from app.schemas.employee_import import (
    EMPLOYEE_IMPORT_FIELDS,
    EMPLOYEE_IMPORT_ISSUE_MAX_LIMIT,
    EMPLOYEE_IMPORT_ISSUE_MESSAGES,
    EMPLOYEE_IMPORT_MAX_BYTES,
    EMPLOYEE_IMPORT_MAX_ROWS,
    EMPLOYEE_IMPORT_TEMPLATE_VERSION,
    EmployeeImportCommitRead,
    EmployeeImportIssueRead,
    EmployeeImportRead,
)
from app.services.audit_recorder import SqlAlchemyAuditRecorder
from app.services.command_idempotency import CommandIdempotencyService, IdempotentCommandExecutor
from app.services.employee_service import (
    EMPLOYEE_NUMBER_NORMALIZED_UNIQUE_CONSTRAINT,
    EMPLOYEE_NUMBER_UNIQUE_CONSTRAINT,
    EMPLOYEE_WORK_EMAIL_NORMALIZED_UNIQUE_CONSTRAINT,
    build_employee_graph,
)
from app.services.reporting_access import (
    ReportingConflictError,
    ReportingNotFoundError,
    ReportingStorageUnavailableError,
    ReportingValidationError,
    require_reporting_feature,
)

_IMPORT_CONTENT_TYPES = {
    "csv": {"text/csv", "application/csv", "application/vnd.ms-excel", "application/octet-stream"},
    "xlsx": {
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "application/octet-stream",
    },
}
_CANONICAL_IMPORT_CONTENT_TYPES = {
    "csv": "text/csv",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}


class EmployeeImportService:
    def __init__(
        self,
        *,
        session_factory: async_sessionmaker[AsyncSession],
        storage: ObjectStorage,
    ) -> None:
        self.session_factory = session_factory
        self.storage = storage

    async def create_import(
        self,
        *,
        request_context: RequestContext,
        source: Path,
        original_filename: str,
        content_type: str,
        size_bytes: int,
    ) -> EmployeeImportRead:
        tenant_id, actor_id, membership_id = _actor_scope(request_context)
        file_format, canonical_content_type = _validated_upload_metadata(
            original_filename=original_filename,
            content_type=content_type,
            size_bytes=size_bytes,
        )
        async with self.session_factory() as session:
            configure_tenant_database_access(
                session,
                tenant_id,
                actor_id=actor_id,
                membership_id=membership_id,
            )
            async with session.begin():
                await require_reporting_feature(session, tenant_id=tenant_id, write=True)
        import_id = uuid4()
        object_key = f"{tenant_id}/{import_id}/{uuid4().hex}.{file_format}"
        try:
            uploaded = await self.storage.upload_from_path(
                key=object_key,
                source=source,
                content_type=canonical_content_type,
                metadata={
                    "resource": "employee-import",
                    "version": EMPLOYEE_IMPORT_TEMPLATE_VERSION,
                },
                maximum_bytes=EMPLOYEE_IMPORT_MAX_BYTES,
            )
        except ObjectStorageError as exc:
            try:
                await self.storage.delete(object_key)
            except ObjectStorageError:
                pass
            raise ReportingStorageUnavailableError() from exc
        if uploaded.size_bytes != size_bytes:
            try:
                await self.storage.delete(object_key)
            except ObjectStorageError:
                pass
            raise ReportingValidationError()
        now = datetime.now(UTC)
        try:
            async with self.session_factory() as session:
                configure_tenant_database_access(
                    session, tenant_id, actor_id=actor_id, membership_id=membership_id
                )
                async with session.begin():
                    await require_reporting_feature(session, tenant_id=tenant_id, write=True)
                    record = EmployeeImport(
                        id=import_id,
                        tenant_id=tenant_id,
                        requested_by_user_id=actor_id,
                        status=EmployeeImportStatus.QUEUED.value,
                        template_version=EMPLOYEE_IMPORT_TEMPLATE_VERSION,
                        file_format=file_format,
                        content_type=canonical_content_type,
                        object_key=object_key,
                        size_bytes=uploaded.size_bytes,
                        source_sha256=uploaded.sha256,
                        scan_result=EmployeeImportScanResult.PENDING.value,
                        row_count=0,
                        error_count=0,
                        warning_count=0,
                        committed_count=0,
                        attempt_count=0,
                        next_attempt_at=now,
                        expires_at=now + timedelta(hours=24),
                        created_at=now,
                        updated_at=now,
                    )
                    session.add(record)
                    await session.flush()
                    await _record_import_event(
                        session,
                        record=record,
                        request_context=request_context,
                        event_type=AuditEventType.EMPLOYEE_IMPORT_UPLOADED,
                        action="upload",
                        changed_fields=("status",),
                        metadata={
                            "file_format": file_format,
                            "template_version": EMPLOYEE_IMPORT_TEMPLATE_VERSION,
                            "size_bytes": uploaded.size_bytes,
                        },
                    )
                    return _import_read(record, issues=[], next_cursor=None)
        except Exception:
            registered = await self._source_registration_state(
                tenant_id=tenant_id,
                actor_id=actor_id,
                membership_id=membership_id,
                import_id=import_id,
                object_key=object_key,
                source_sha256=uploaded.sha256,
            )
            if registered is False:
                try:
                    await self.storage.delete(object_key)
                except ObjectStorageError:
                    pass
            raise

    async def _source_registration_state(
        self,
        *,
        tenant_id: UUID,
        actor_id: UUID,
        membership_id: UUID,
        import_id: UUID,
        object_key: str,
        source_sha256: str,
    ) -> bool | None:
        """Distinguish a rolled-back registration from an ambiguous database commit."""

        try:
            async with self.session_factory() as session:
                configure_tenant_database_access(
                    session,
                    tenant_id,
                    actor_id=actor_id,
                    membership_id=membership_id,
                )
                async with session.begin():
                    registered_id = await session.scalar(
                        select(EmployeeImport.id).where(
                            EmployeeImport.tenant_id == tenant_id,
                            EmployeeImport.id == import_id,
                            EmployeeImport.object_key == object_key,
                            EmployeeImport.source_sha256 == source_sha256,
                        )
                    )
            return registered_id is not None
        except Exception:
            return None

    async def get_import(
        self,
        *,
        request_context: RequestContext,
        import_id: UUID,
        issue_limit: int,
        issue_cursor: str | None,
    ) -> EmployeeImportRead:
        if not 1 <= issue_limit <= EMPLOYEE_IMPORT_ISSUE_MAX_LIMIT:
            raise ReportingValidationError()
        tenant_id, actor_id, membership_id = _actor_scope(request_context)
        cursor_values = _issue_cursor(issue_cursor, import_id=import_id)
        async with self.session_factory() as session:
            configure_tenant_database_access(
                session, tenant_id, actor_id=actor_id, membership_id=membership_id
            )
            async with session.begin():
                await require_reporting_feature(session, tenant_id=tenant_id)
                record = await _owned_import(
                    session, tenant_id=tenant_id, actor_id=actor_id, import_id=import_id
                )
                statement = select(EmployeeImportIssue).where(
                    EmployeeImportIssue.tenant_id == tenant_id,
                    EmployeeImportIssue.import_id == import_id,
                )
                if cursor_values is not None:
                    row_number, cursor_id = cursor_values
                    statement = statement.where(
                        or_(
                            EmployeeImportIssue.row_number > row_number,
                            and_(
                                EmployeeImportIssue.row_number == row_number,
                                EmployeeImportIssue.id > cursor_id,
                            ),
                        )
                    )
                issues = list(
                    await session.scalars(
                        statement.order_by(
                            EmployeeImportIssue.row_number.asc(),
                            EmployeeImportIssue.id.asc(),
                        ).limit(issue_limit + 1)
                    )
                )
                visible = issues[:issue_limit]
                next_cursor = None
                if len(issues) > issue_limit:
                    last = visible[-1]
                    next_cursor = encode_cursor(
                        "employee_import_issues",
                        {
                            "import_id": str(import_id),
                            "row_number": str(last.row_number),
                            "id": str(last.id),
                        },
                    )
                return _import_read(
                    record,
                    issues=[_issue_read(issue) for issue in visible],
                    next_cursor=next_cursor,
                )

    async def commit_import(
        self,
        *,
        request_context: RequestContext,
        import_id: UUID,
        idempotency_key: str,
    ) -> EmployeeImportCommitRead:
        tenant_id, actor_id, membership_id = _actor_scope(request_context)
        async with self.session_factory() as session:
            configure_tenant_database_access(
                session, tenant_id, actor_id=actor_id, membership_id=membership_id
            )
            executor = IdempotentCommandExecutor(
                service=CommandIdempotencyService(session=session),
                unit_of_work=SqlAlchemyUnitOfWork(session),
            )

            async def operation() -> EmployeeImportCommitRead:
                record = await _owned_import(
                    session,
                    tenant_id=tenant_id,
                    actor_id=actor_id,
                    import_id=import_id,
                    lock=True,
                )
                if record.status == EmployeeImportStatus.SUCCEEDED.value:
                    if record.committed_at is None:
                        raise ReportingConflictError()
                    return EmployeeImportCommitRead(
                        id=record.id,
                        status=EmployeeImportStatus.SUCCEEDED,
                        committed_count=record.committed_count,
                        committed_at=record.committed_at,
                    )
                now = datetime.now(UTC)
                if (
                    record.status != EmployeeImportStatus.READY.value
                    or record.scan_result != EmployeeImportScanResult.CLEAN.value
                    or record.error_count != 0
                    or record.validation_fingerprint is None
                    or record.expires_at <= now
                ):
                    raise ReportingConflictError()
                if await _has_import_errors(session, tenant_id=tenant_id, import_id=import_id):
                    raise ReportingConflictError()
                await _ensure_validation_is_current(
                    session,
                    tenant_id=tenant_id,
                    import_id=import_id,
                    expected_rows=record.row_count,
                )
                await _lock_import_references(
                    session,
                    tenant_id=tenant_id,
                    import_id=import_id,
                )
                digest = sha256()
                committed_count = 0
                last_row_number = 1
                while True:
                    chunk = list(
                        await session.scalars(
                            select(EmployeeImportRow)
                            .where(
                                EmployeeImportRow.tenant_id == tenant_id,
                                EmployeeImportRow.import_id == import_id,
                                EmployeeImportRow.row_number > last_row_number,
                            )
                            .order_by(EmployeeImportRow.row_number)
                            .limit(250)
                        )
                    )
                    if not chunk:
                        break
                    for row in chunk:
                        digest.update(canonical_import_row(row))
                    await _commit_rows(
                        session,
                        rows=chunk,
                        tenant_id=tenant_id,
                        import_id=import_id,
                        actor_id=actor_id,
                    )
                    committed_count += len(chunk)
                    last_row_number = chunk[-1].row_number
                if (
                    committed_count != record.row_count
                    or digest.hexdigest() != record.validation_fingerprint
                ):
                    raise ReportingConflictError()
                committed_at = datetime.now(UTC)
                record.status = EmployeeImportStatus.SUCCEEDED.value
                record.committed_count = committed_count
                record.committed_at = committed_at
                record.updated_at = committed_at
                record.next_attempt_at = None
                await session.flush()
                await _record_import_event(
                    session,
                    record=record,
                    request_context=request_context,
                    event_type=AuditEventType.EMPLOYEE_IMPORT_COMMITTED,
                    action="commit",
                    changed_fields=("status",),
                    metadata={
                        "file_format": record.file_format,
                        "template_version": record.template_version,
                        "row_count": committed_count,
                    },
                )
                return EmployeeImportCommitRead(
                    id=record.id,
                    status=EmployeeImportStatus.SUCCEEDED,
                    committed_count=committed_count,
                    committed_at=committed_at,
                )

            return await executor.execute(
                tenant_id=tenant_id,
                idempotency_key=idempotency_key,
                command_name="employee_imports.commit",
                request_fingerprint=command_fingerprint(
                    {"actor_id": str(actor_id), "import_id": str(import_id)}
                ),
                precondition=lambda: require_reporting_feature(
                    session,
                    tenant_id=tenant_id,
                    write=True,
                ),
                operation=operation,
                serialize=lambda result: result.model_dump(mode="json"),
                deserialize=EmployeeImportCommitRead.model_validate,
            )


async def _ensure_validation_is_current(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    import_id: UUID,
    expected_rows: int,
) -> None:
    actual_rows = await session.scalar(
        select(func.count())
        .select_from(EmployeeImportRow)
        .where(
            EmployeeImportRow.tenant_id == tenant_id,
            EmployeeImportRow.import_id == import_id,
        )
    )
    if int(actual_rows or 0) != expected_rows:
        raise ReportingConflictError()
    duplicate = await session.scalar(
        select(EmployeeImportRow.id)
        .join(
            Employee,
            and_(
                Employee.tenant_id == EmployeeImportRow.tenant_id,
                or_(
                    Employee.employee_number_normalized
                    == EmployeeImportRow.employee_number_normalized,
                    and_(
                        EmployeeImportRow.work_email_normalized.is_not(None),
                        Employee.email_normalized == EmployeeImportRow.work_email_normalized,
                    ),
                ),
            ),
        )
        .where(
            EmployeeImportRow.tenant_id == tenant_id,
            EmployeeImportRow.import_id == import_id,
        )
        .limit(1)
    )
    if duplicate is not None:
        raise ReportingConflictError()
    invalid_reference = await session.scalar(
        select(EmployeeImportRow.id)
        .outerjoin(
            LegalEntity,
            and_(
                LegalEntity.tenant_id == EmployeeImportRow.tenant_id,
                LegalEntity.id == EmployeeImportRow.legal_entity_id,
            ),
        )
        .outerjoin(
            Branch,
            and_(
                Branch.tenant_id == EmployeeImportRow.tenant_id,
                Branch.id == EmployeeImportRow.branch_id,
            ),
        )
        .outerjoin(
            Department,
            and_(
                Department.tenant_id == EmployeeImportRow.tenant_id,
                Department.id == EmployeeImportRow.department_id,
            ),
        )
        .outerjoin(
            Position,
            and_(
                Position.tenant_id == EmployeeImportRow.tenant_id,
                Position.id == EmployeeImportRow.position_id,
            ),
        )
        .where(
            EmployeeImportRow.tenant_id == tenant_id,
            EmployeeImportRow.import_id == import_id,
            or_(
                LegalEntity.id.is_(None),
                LegalEntity.status != LegalEntityStatus.ACTIVE.value,
                LegalEntity.code_normalized != EmployeeImportRow.legal_entity_code,
                Branch.id.is_(None),
                Branch.status != BranchStatus.ACTIVE.value,
                Branch.archived_at.is_not(None),
                Branch.legal_entity_id != EmployeeImportRow.legal_entity_id,
                Branch.code_normalized != EmployeeImportRow.branch_code,
                Department.id.is_(None),
                Department.status != DepartmentStatus.ACTIVE.value,
                Department.archived_at.is_not(None),
                Department.code_normalized != EmployeeImportRow.department_code,
                Position.id.is_(None),
                Position.status != PositionStatus.ACTIVE.value,
                Position.archived_at.is_not(None),
                Position.code_normalized != EmployeeImportRow.position_code,
            ),
        )
        .limit(1)
    )
    if invalid_reference is not None:
        raise ReportingConflictError()


async def _commit_rows(
    session: AsyncSession,
    *,
    rows: list[EmployeeImportRow],
    tenant_id: UUID,
    import_id: UUID,
    actor_id: UUID,
) -> None:
    legal_entity_ids = {row.legal_entity_id for row in rows}
    branch_ids = {row.branch_id for row in rows}
    department_ids = {row.department_id for row in rows}
    position_ids = {row.position_id for row in rows}
    legal_entities = {
        record.id: record
        for record in await session.scalars(
            select(LegalEntity)
            .where(
                LegalEntity.tenant_id == tenant_id,
                LegalEntity.id.in_(legal_entity_ids),
            )
            .order_by(LegalEntity.id)
            .with_for_update()
        )
    }
    branches = {
        record.id: record
        for record in await session.scalars(
            select(Branch)
            .where(Branch.tenant_id == tenant_id, Branch.id.in_(branch_ids))
            .order_by(Branch.id)
            .with_for_update()
        )
    }
    departments = {
        record.id: record
        for record in await session.scalars(
            select(Department)
            .where(
                Department.tenant_id == tenant_id,
                Department.id.in_(department_ids),
            )
            .order_by(Department.id)
            .with_for_update()
        )
    }
    positions = {
        record.id: record
        for record in await session.scalars(
            select(Position)
            .where(
                Position.tenant_id == tenant_id,
                Position.id.in_(position_ids),
            )
            .order_by(Position.id)
            .with_for_update()
        )
    }
    today = date.today()
    for row in rows:
        legal_entity = legal_entities.get(row.legal_entity_id)
        branch = branches.get(row.branch_id)
        department = departments.get(row.department_id)
        position = positions.get(row.position_id)
        if (
            legal_entity is None
            or legal_entity.status != LegalEntityStatus.ACTIVE.value
            or legal_entity.code_normalized != row.legal_entity_code
            or branch is None
            or branch.status != BranchStatus.ACTIVE.value
            or branch.archived_at is not None
            or branch.legal_entity_id != row.legal_entity_id
            or branch.code_normalized != row.branch_code
            or department is None
            or department.status != DepartmentStatus.ACTIVE.value
            or department.archived_at is not None
            or department.code_normalized != row.department_code
            or position is None
            or position.status != PositionStatus.ACTIVE.value
            or position.archived_at is not None
            or position.code_normalized != row.position_code
        ):
            raise ReportingConflictError()
        payload = EmployeeCreate(
            employee_number=row.employee_number,
            first_name=row.first_name,
            last_name=row.last_name,
            email=row.work_email,
            department=(department.name if row.employment_start_date <= today else None),
            position=(position.title if row.employment_start_date <= today else None),
            status=row.status,
            employment_start_date=row.employment_start_date,
            employment_end_date=row.employment_end_date,
        )
        employee_id = uuid5(
            NAMESPACE_URL,
            f"wealthy-falcon:import:{import_id}:{row.row_number}:employee",
        )
        employee, personal, employment = build_employee_graph(
            tenant_id=tenant_id,
            payload=payload,
            employee_id=employee_id,
        )
        assignment = EmployeeAssignment(
            id=uuid5(
                NAMESPACE_URL,
                f"wealthy-falcon:import:{import_id}:{row.row_number}:assignment",
            ),
            tenant_id=tenant_id,
            employee_id=employee_id,
            legal_entity_id=row.legal_entity_id,
            branch_id=row.branch_id,
            department_id=row.department_id,
            position_id=row.position_id,
            manager_user_id=None,
            supersedes_assignment_id=None,
            effective_from=row.employment_start_date,
            effective_to=None,
            change_reason=None,
            created_by_user_id=actor_id,
        )
        session.add_all([employee, personal, employment, assignment])
    try:
        await session.flush()
    except IntegrityError as exc:
        if constraint_name_from_error(exc) in {
            EMPLOYEE_NUMBER_UNIQUE_CONSTRAINT,
            EMPLOYEE_NUMBER_NORMALIZED_UNIQUE_CONSTRAINT,
            EMPLOYEE_WORK_EMAIL_NORMALIZED_UNIQUE_CONSTRAINT,
        }:
            raise ReportingConflictError() from exc
        raise


async def _lock_import_references(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    import_id: UUID,
) -> None:
    """Lock every referenced organization row in one stable global order."""

    reference_queries = (
        select(LegalEntity)
        .where(
            LegalEntity.tenant_id == tenant_id,
            LegalEntity.id.in_(
                select(EmployeeImportRow.legal_entity_id).where(
                    EmployeeImportRow.tenant_id == tenant_id,
                    EmployeeImportRow.import_id == import_id,
                )
            ),
        )
        .order_by(LegalEntity.id)
        .limit(EMPLOYEE_IMPORT_MAX_ROWS)
        .with_for_update(),
        select(Branch)
        .where(
            Branch.tenant_id == tenant_id,
            Branch.id.in_(
                select(EmployeeImportRow.branch_id).where(
                    EmployeeImportRow.tenant_id == tenant_id,
                    EmployeeImportRow.import_id == import_id,
                )
            ),
        )
        .order_by(Branch.id)
        .limit(EMPLOYEE_IMPORT_MAX_ROWS)
        .with_for_update(),
        select(Department)
        .where(
            Department.tenant_id == tenant_id,
            Department.id.in_(
                select(EmployeeImportRow.department_id).where(
                    EmployeeImportRow.tenant_id == tenant_id,
                    EmployeeImportRow.import_id == import_id,
                )
            ),
        )
        .order_by(Department.id)
        .limit(EMPLOYEE_IMPORT_MAX_ROWS)
        .with_for_update(),
        select(Position)
        .where(
            Position.tenant_id == tenant_id,
            Position.id.in_(
                select(EmployeeImportRow.position_id).where(
                    EmployeeImportRow.tenant_id == tenant_id,
                    EmployeeImportRow.import_id == import_id,
                )
            ),
        )
        .order_by(Position.id)
        .limit(EMPLOYEE_IMPORT_MAX_ROWS)
        .with_for_update(),
    )
    for statement in reference_queries:
        # Each result is explicitly capped by the import row limit; iterating consumes the
        # bounded result so PostgreSQL takes every row lock before employee writes begin.
        for _record in await session.scalars(statement):
            pass


def canonical_import_row(row: EmployeeImportRow) -> bytes:
    values = {
        "row_number": row.row_number,
        "employee_number": row.employee_number,
        "first_name": row.first_name,
        "last_name": row.last_name,
        "work_email": row.work_email,
        "status": row.status,
        "employment_start_date": row.employment_start_date.isoformat(),
        "employment_end_date": (
            row.employment_end_date.isoformat() if row.employment_end_date else None
        ),
        "legal_entity_code": row.legal_entity_code,
        "branch_code": row.branch_code,
        "department_code": row.department_code,
        "position_code": row.position_code,
        "legal_entity_id": str(row.legal_entity_id),
        "branch_id": str(row.branch_id),
        "department_id": str(row.department_id),
        "position_id": str(row.position_id),
    }
    return (
        json.dumps(values, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
        + b"\n"
    )


async def _owned_import(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    actor_id: UUID,
    import_id: UUID,
    lock: bool = False,
) -> EmployeeImport:
    statement = select(EmployeeImport).where(
        EmployeeImport.tenant_id == tenant_id,
        EmployeeImport.id == import_id,
        EmployeeImport.requested_by_user_id == actor_id,
    )
    if lock:
        statement = statement.with_for_update()
    record = await session.scalar(statement)
    if record is None:
        raise ReportingNotFoundError()
    return record


async def _has_import_errors(session: AsyncSession, *, tenant_id: UUID, import_id: UUID) -> bool:
    issue_id = await session.scalar(
        select(EmployeeImportIssue.id)
        .where(
            EmployeeImportIssue.tenant_id == tenant_id,
            EmployeeImportIssue.import_id == import_id,
            EmployeeImportIssue.severity == "error",
        )
        .limit(1)
    )
    return issue_id is not None


def _validated_upload_metadata(
    *, original_filename: str, content_type: str, size_bytes: int
) -> tuple[str, str]:
    if not 1 <= size_bytes <= EMPLOYEE_IMPORT_MAX_BYTES:
        raise ReportingValidationError()
    raw_filename = original_filename.strip()
    filename = Path(raw_filename).name
    if (
        not filename
        or filename != raw_filename
        or "\\" in filename
        or len(filename) > 255
        or any(ord(character) < 32 for character in filename)
    ):
        raise ReportingValidationError()
    suffix = Path(filename).suffix.casefold().removeprefix(".")
    normalized_type = content_type.split(";", 1)[0].strip().casefold()
    if suffix not in _IMPORT_CONTENT_TYPES or normalized_type not in _IMPORT_CONTENT_TYPES[suffix]:
        raise ReportingValidationError()
    return suffix, _CANONICAL_IMPORT_CONTENT_TYPES[suffix]


def _import_read(
    record: EmployeeImport,
    *,
    issues: list[EmployeeImportIssueRead],
    next_cursor: str | None,
) -> EmployeeImportRead:
    status = EmployeeImportStatus(record.status)
    if status not in {EmployeeImportStatus.SUCCEEDED, EmployeeImportStatus.EXPIRED}:
        if record.expires_at <= datetime.now(UTC):
            status = EmployeeImportStatus.EXPIRED
    return EmployeeImportRead(
        id=record.id,
        status=status,
        template_version=record.template_version,
        file_format=record.file_format,
        scan_result=EmployeeImportScanResult(record.scan_result),
        row_count=record.row_count,
        error_count=record.error_count,
        warning_count=record.warning_count,
        committed_count=record.committed_count,
        failure_code=record.failure_code,
        issues=issues,
        issues_next_cursor=next_cursor,
        validated_at=record.validated_at,
        committed_at=record.committed_at,
        expires_at=record.expires_at,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


def _issue_read(issue: EmployeeImportIssue) -> EmployeeImportIssueRead:
    code = issue.code if issue.code in EMPLOYEE_IMPORT_ISSUE_MESSAGES else "invalid_file"
    field = issue.field if issue.field in EMPLOYEE_IMPORT_FIELDS else None
    return EmployeeImportIssueRead(
        row_number=issue.row_number,
        severity="warning" if code == "future_start_date" else "error",
        code=code,
        field=field,
        message=EMPLOYEE_IMPORT_ISSUE_MESSAGES[code],
    )


def _issue_cursor(cursor: str | None, *, import_id: UUID) -> tuple[int, UUID] | None:
    if cursor is None:
        return None
    try:
        values = decode_cursor(cursor, expected_resource="employee_import_issues")
        if set(values) != {"import_id", "row_number", "id"}:
            raise ValueError
        if UUID(values["import_id"]) != import_id:
            raise ValueError
        row_number = int(values["row_number"])
        cursor_id = UUID(values["id"])
    except (TypeError, ValueError) as exc:
        raise ReportingValidationError() from exc
    if not 1 <= row_number <= EMPLOYEE_IMPORT_MAX_ROWS + 1:
        raise ReportingValidationError()
    return row_number, cursor_id


async def _record_import_event(
    session: AsyncSession,
    *,
    record: EmployeeImport,
    request_context: RequestContext,
    event_type: AuditEventType,
    action: str,
    changed_fields: tuple[str, ...],
    metadata: dict[str, object],
) -> None:
    await SqlAlchemyAuditRecorder(session).record(
        AuditEventDraft(
            scope_type=AuditScopeType.TENANT,
            tenant_id=record.tenant_id,
            actor_type=AuditActorType.USER,
            actor_user_id=request_context.actor_id,
            event_type=event_type,
            category=AuditCategory.HR_OPERATIONS,
            resource_type="employee_import",
            resource_id=record.id,
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
    if context.actor_id is None:
        raise ReportingValidationError()
    return context.require_tenant().tenant_id, context.actor_id, context.require_membership()


__all__ = ["EmployeeImportService", "canonical_import_row"]
