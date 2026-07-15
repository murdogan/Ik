"""Secure employee document policy, upload, scan, checklist, and access service."""

from __future__ import annotations

import tempfile
import unicodedata
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from re import fullmatch, sub
from uuid import UUID, uuid4

from sqlalchemy import and_, case, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings
from app.models.employee import Employee
from app.models.employee_account_link import EmployeeAccountLink
from app.models.employee_document import (
    DocumentExpiryMode,
    DocumentProcessingState,
    DocumentScanResult,
    DocumentType,
    DocumentUploadIntentStatus,
    EmployeeDocument,
    EmployeeDocumentUploadIntent,
)
from app.models.identity import TenantMembership
from app.modules.documents.scanning import (
    MalwareScanError,
    MalwareScanner,
    MalwareScanVerdict,
)
from app.platform.audit import (
    AuditActorType,
    AuditCategory,
    AuditContext,
    AuditDataClassification,
    AuditEventDraft,
    AuditEventType,
    AuditRecorder,
    AuditResult,
    AuditScopeType,
    AuditVisibilityClass,
)
from app.platform.db import SqlAlchemyUnitOfWork, configure_tenant_database_access
from app.platform.errors.application import ApplicationError
from app.platform.request_context import RequestContext
from app.platform.storage import (
    ObjectAlreadyExistsError,
    ObjectHead,
    ObjectNotFoundError,
    ObjectStorage,
    ObjectStorageError,
)
from app.schemas.employee_document import (
    DOCUMENT_LIST_LIMIT,
    AllowedDocumentMimeType,
    DocumentChecklistItemRead,
    DocumentChecklistStatus,
    DocumentTypeCreate,
    DocumentTypeRead,
    DocumentTypeUpdate,
    EmployeeDocumentDownloadGrantRead,
    EmployeeDocumentMetadataUpdate,
    EmployeeDocumentRead,
    EmployeeDocumentSummaryRead,
    EmployeeDocumentUploadGrantRead,
    EmployeeDocumentUploadInitiate,
    EmployeeDocumentWorkspaceRead,
    OwnEmployeeDocumentRead,
    OwnEmployeeDocumentWorkspaceRead,
)
from app.services.audit_recorder import SqlAlchemyAuditRecorder

_MIME_BY_EXTENSION = {
    "pdf": AllowedDocumentMimeType.PDF.value,
    "jpg": AllowedDocumentMimeType.JPEG.value,
    "jpeg": AllowedDocumentMimeType.JPEG.value,
    "png": AllowedDocumentMimeType.PNG.value,
}
_FILE_CLASS_BY_MIME = {
    AllowedDocumentMimeType.PDF.value: "pdf",
    AllowedDocumentMimeType.JPEG.value: "jpeg",
    AllowedDocumentMimeType.PNG.value: "png",
}
_FINALIZED_STATES = frozenset(
    {
        DocumentProcessingState.PENDING_SCAN.value,
        DocumentProcessingState.AVAILABLE.value,
        DocumentProcessingState.INFECTED.value,
        DocumentProcessingState.SCAN_ERROR.value,
    }
)


class DocumentNotFoundError(ApplicationError):
    pass


class DocumentTypeNotFoundError(ApplicationError):
    pass


class DocumentValidationError(ApplicationError):
    pass


class DocumentConflictError(ApplicationError):
    pass


class DocumentVersionConflictError(DocumentConflictError):
    pass


class DocumentStorageUnavailableError(ApplicationError):
    pass


@dataclass(frozen=True, slots=True)
class _Actor:
    user_id: UUID
    membership_id: UUID
    session_id: UUID | None
    audit_context: AuditContext

    @classmethod
    def from_request_context(cls, context: RequestContext) -> _Actor:
        if context.actor_id is None:
            raise RuntimeError("Employee document request context requires an actor")
        return cls(
            user_id=context.actor_id,
            membership_id=context.require_membership(),
            session_id=context.session_id,
            audit_context=AuditContext.from_request_context(context),
        )


@dataclass(frozen=True, slots=True)
class _FinalizeSnapshot:
    document_id: UUID
    employee_id: UUID
    intent_id: UUID
    upload_key: str
    final_key: str
    content_type: str
    size_bytes: int
    extension: str
    expected_metadata: dict[str, str]
    object_id: UUID


class EmployeeDocumentQueryService:
    """Bounded fixed-query projections reusable by Employee 360 insights."""

    def __init__(
        self,
        session: AsyncSession,
        *,
        today: date | None = None,
        expiring_window_days: int = 30,
    ) -> None:
        self.session = session
        self.today = today or date.today()
        self.expiring_window_days = expiring_window_days

    async def checklist(
        self,
        *,
        tenant_id: UUID,
        employee_id: UUID,
        own_only: bool = False,
    ) -> list[DocumentChecklistItemRead]:
        still_current = case(
            (
                or_(
                    EmployeeDocument.expires_on.is_(None),
                    EmployeeDocument.expires_on >= self.today,
                ),
                0,
            ),
            else_=1,
        )
        candidates = (
            select(
                EmployeeDocument.id.label("document_id"),
                EmployeeDocument.document_type_id.label("document_type_id"),
                EmployeeDocument.expires_on.label("expires_on"),
                func.row_number()
                .over(
                    partition_by=EmployeeDocument.document_type_id,
                    order_by=(
                        still_current.asc(),
                        EmployeeDocument.expires_on.desc().nulls_first(),
                        EmployeeDocument.created_at.desc(),
                        EmployeeDocument.id.desc(),
                    ),
                )
                .label("candidate_rank"),
            )
            .where(
                EmployeeDocument.tenant_id == tenant_id,
                EmployeeDocument.employee_id == employee_id,
                EmployeeDocument.processing_state == DocumentProcessingState.AVAILABLE.value,
                EmployeeDocument.archived_at.is_(None),
            )
        )
        if own_only:
            candidates = candidates.where(EmployeeDocument.employee_visible.is_(True))
        ranked = candidates.subquery()

        statement = (
            select(
                DocumentType.id,
                DocumentType.code,
                DocumentType.name,
                DocumentType.required,
                DocumentType.employee_visible,
                ranked.c.document_id,
                ranked.c.expires_on,
            )
            .outerjoin(
                ranked,
                and_(
                    ranked.c.document_type_id == DocumentType.id,
                    ranked.c.candidate_rank == 1,
                ),
            )
            .where(
                DocumentType.tenant_id == tenant_id,
                DocumentType.archived_at.is_(None),
            )
            .order_by(DocumentType.required.desc(), DocumentType.name, DocumentType.id)
            .limit(DOCUMENT_LIST_LIMIT)
        )
        if own_only:
            statement = statement.where(DocumentType.employee_visible.is_(True))
        rows = (await self.session.execute(statement)).all()
        return [
            DocumentChecklistItemRead(
                document_type_id=row.id,
                code=row.code,
                name=row.name,
                required=row.required,
                employee_visible=row.employee_visible,
                status=self._status(row.document_id, row.expires_on),
                document_id=row.document_id,
                expires_on=row.expires_on,
            )
            for row in rows
        ]

    async def summary(
        self,
        *,
        tenant_id: UUID,
        employee_id: UUID,
        own_only: bool = False,
    ) -> EmployeeDocumentSummaryRead:
        return summarize_checklist(
            await self.checklist(
                tenant_id=tenant_id,
                employee_id=employee_id,
                own_only=own_only,
            )
        )

    def _status(self, document_id: UUID | None, expires_on: date | None) -> DocumentChecklistStatus:
        if document_id is None:
            return DocumentChecklistStatus.MISSING
        if expires_on is not None and expires_on < self.today:
            return DocumentChecklistStatus.EXPIRED
        if expires_on is not None and expires_on <= self.today + timedelta(
            days=self.expiring_window_days
        ):
            return DocumentChecklistStatus.EXPIRING
        return DocumentChecklistStatus.AVAILABLE


class EmployeeDocumentService:
    def __init__(
        self,
        *,
        session_factory: async_sessionmaker[AsyncSession],
        storage: ObjectStorage,
        scanner: MalwareScanner,
        settings: Settings,
        audit_recorder_factory: Callable[[AsyncSession], AuditRecorder] = SqlAlchemyAuditRecorder,
    ) -> None:
        self._session_factory = session_factory
        self._storage = storage
        self._scanner = scanner
        self._settings = settings
        self._audit_recorder_factory = audit_recorder_factory

    async def list_document_types(
        self,
        *,
        tenant_id: UUID,
        include_archived: bool = True,
    ) -> list[DocumentTypeRead]:
        async with self._tenant_session(tenant_id) as session:
            async with session.begin():
                statement = select(DocumentType).where(DocumentType.tenant_id == tenant_id)
                if not include_archived:
                    statement = statement.where(DocumentType.archived_at.is_(None))
                records = tuple(
                    await session.scalars(
                        statement.order_by(
                            DocumentType.archived_at,
                            DocumentType.name,
                            DocumentType.id,
                        )
                        .limit(DOCUMENT_LIST_LIMIT)
                    )
                )
        return [_document_type_read(record) for record in records]

    async def create_document_type(
        self,
        *,
        tenant_id: UUID,
        payload: DocumentTypeCreate,
        request_context: RequestContext,
    ) -> DocumentTypeRead:
        actor = _Actor.from_request_context(request_context)
        self._validate_type_policy(payload)
        async with self._tenant_session(tenant_id, actor) as session:
            unit_of_work = SqlAlchemyUnitOfWork(session)

            async def operation() -> DocumentTypeRead:
                existing = await session.scalar(
                    select(DocumentType.id).where(
                        DocumentType.tenant_id == tenant_id,
                        DocumentType.code == payload.code,
                    )
                )
                if existing is not None:
                    raise DocumentConflictError("Document type code is already in use")
                type_count = await session.scalar(
                    select(func.count(DocumentType.id)).where(
                        DocumentType.tenant_id == tenant_id
                    )
                )
                if int(type_count or 0) >= DOCUMENT_LIST_LIMIT:
                    raise DocumentConflictError("Tenant document type limit has been reached")
                record = DocumentType(
                    id=uuid4(),
                    tenant_id=tenant_id,
                    code=payload.code,
                    name=payload.name,
                    description=payload.description,
                    required=payload.required,
                    employee_visible=payload.employee_visible,
                    sensitivity=payload.sensitivity.value,
                    expiry_mode=payload.expiry_mode.value,
                    allowed_mime_types=sorted(item.value for item in payload.allowed_mime_types),
                    allowed_extensions=sorted(item.value for item in payload.allowed_extensions),
                    max_size_bytes=payload.max_size_bytes,
                    version=1,
                )
                session.add(record)
                await session.flush()
                await self._record_user_audit(
                    session,
                    tenant_id=tenant_id,
                    actor=actor,
                    event_type=AuditEventType.DOCUMENT_TYPE_CREATED,
                    resource_type="document_type",
                    resource_id=record.id,
                    action="create",
                    changed_fields=(
                        "code",
                        "name",
                        "description",
                        "required",
                        "employee_visible",
                        "sensitivity",
                        "expiry_mode",
                        "allowed_mime_types",
                        "allowed_extensions",
                        "max_size_bytes",
                    ),
                    metadata={"sensitivity": record.sensitivity},
                )
                return _document_type_read(record)

            return await unit_of_work.execute(operation)

    async def update_document_type(
        self,
        *,
        tenant_id: UUID,
        document_type_id: UUID,
        payload: DocumentTypeUpdate,
        request_context: RequestContext,
    ) -> DocumentTypeRead:
        actor = _Actor.from_request_context(request_context)
        async with self._tenant_session(tenant_id, actor) as session:
            unit_of_work = SqlAlchemyUnitOfWork(session)

            async def operation() -> DocumentTypeRead:
                record = await self._document_type(
                    session,
                    tenant_id=tenant_id,
                    document_type_id=document_type_id,
                    lock=True,
                )
                if record.version != payload.expected_version:
                    raise DocumentVersionConflictError
                if record.archived_at is not None:
                    raise DocumentConflictError("Archived document types are read-only")
                values = _type_policy_values(record, payload)
                self._validate_type_policy_values(**values)
                changed_fields: list[str] = []
                for field_name in (
                    "name",
                    "description",
                    "required",
                    "employee_visible",
                    "sensitivity",
                    "expiry_mode",
                    "allowed_mime_types",
                    "allowed_extensions",
                    "max_size_bytes",
                ):
                    if field_name not in payload.model_fields_set:
                        continue
                    value = values[field_name]
                    if getattr(record, field_name) != value:
                        setattr(record, field_name, value)
                        changed_fields.append(field_name)
                if changed_fields:
                    await session.flush()
                    await session.refresh(record)
                    await self._record_user_audit(
                        session,
                        tenant_id=tenant_id,
                        actor=actor,
                        event_type=AuditEventType.DOCUMENT_TYPE_UPDATED,
                        resource_type="document_type",
                        resource_id=record.id,
                        action="update",
                        changed_fields=tuple(changed_fields),
                        metadata={"sensitivity": record.sensitivity},
                    )
                return _document_type_read(record)

            return await unit_of_work.execute(operation)

    async def set_document_type_archived(
        self,
        *,
        tenant_id: UUID,
        document_type_id: UUID,
        expected_version: int,
        archived: bool,
        request_context: RequestContext,
    ) -> DocumentTypeRead:
        actor = _Actor.from_request_context(request_context)
        async with self._tenant_session(tenant_id, actor) as session:
            unit_of_work = SqlAlchemyUnitOfWork(session)

            async def operation() -> DocumentTypeRead:
                record = await self._document_type(
                    session,
                    tenant_id=tenant_id,
                    document_type_id=document_type_id,
                    lock=True,
                )
                if record.version != expected_version:
                    raise DocumentVersionConflictError
                currently_archived = record.archived_at is not None
                if currently_archived == archived:
                    return _document_type_read(record)
                record.archived_at = datetime.now(UTC) if archived else None
                await session.flush()
                await session.refresh(record)
                await self._record_user_audit(
                    session,
                    tenant_id=tenant_id,
                    actor=actor,
                    event_type=(
                        AuditEventType.DOCUMENT_TYPE_ARCHIVED
                        if archived
                        else AuditEventType.DOCUMENT_TYPE_UNARCHIVED
                    ),
                    resource_type="document_type",
                    resource_id=record.id,
                    action="archive" if archived else "unarchive",
                    changed_fields=("archived_at",),
                    metadata={
                        "before_state": "active" if archived else "archived",
                        "after_state": "archived" if archived else "active",
                    },
                )
                return _document_type_read(record)

            return await unit_of_work.execute(operation)

    async def get_hr_workspace(
        self,
        *,
        tenant_id: UUID,
        employee_id: UUID,
        request_context: RequestContext,
    ) -> EmployeeDocumentWorkspaceRead:
        actor = _Actor.from_request_context(request_context)
        async with self._tenant_session(tenant_id, actor) as session:
            unit_of_work = SqlAlchemyUnitOfWork(session)

            async def operation() -> EmployeeDocumentWorkspaceRead:
                await self._require_employee(session, tenant_id, employee_id, include_archived=True)
                query = EmployeeDocumentQueryService(
                    session,
                    expiring_window_days=self._settings.document_expiring_window_days,
                )
                checklist = await query.checklist(tenant_id=tenant_id, employee_id=employee_id)
                documents = await self._list_documents(
                    session,
                    tenant_id=tenant_id,
                    employee_id=employee_id,
                    own_only=False,
                )
                document_types = tuple(
                    await session.scalars(
                        select(DocumentType)
                        .where(
                            DocumentType.tenant_id == tenant_id,
                            DocumentType.archived_at.is_(None),
                        )
                        .order_by(DocumentType.name, DocumentType.id)
                        .limit(DOCUMENT_LIST_LIMIT)
                    )
                )
                await self._record_user_audit(
                    session,
                    tenant_id=tenant_id,
                    actor=actor,
                    event_type=AuditEventType.EMPLOYEE_DOCUMENT_VIEWED,
                    resource_type="employee",
                    resource_id=employee_id,
                    action="view_documents",
                    metadata={"access_scope": "hr"},
                )
                return EmployeeDocumentWorkspaceRead(
                    employee_id=employee_id,
                    summary=summarize_checklist(checklist),
                    checklist=checklist,
                    documents=documents,
                    document_types=[_document_type_read(item) for item in document_types],
                )

            return await unit_of_work.execute(operation)

    async def get_own_workspace(
        self,
        *,
        tenant_id: UUID,
        request_context: RequestContext,
    ) -> OwnEmployeeDocumentWorkspaceRead:
        actor = _Actor.from_request_context(request_context)
        async with self._tenant_session(tenant_id, actor) as session:
            unit_of_work = SqlAlchemyUnitOfWork(session)

            async def operation() -> OwnEmployeeDocumentWorkspaceRead:
                employee_id = await self._own_employee_id(session, tenant_id, actor)
                query = EmployeeDocumentQueryService(
                    session,
                    expiring_window_days=self._settings.document_expiring_window_days,
                )
                checklist = await query.checklist(
                    tenant_id=tenant_id,
                    employee_id=employee_id,
                    own_only=True,
                )
                documents = await self._list_own_documents(
                    session,
                    tenant_id=tenant_id,
                    employee_id=employee_id,
                )
                await self._record_user_audit(
                    session,
                    tenant_id=tenant_id,
                    actor=actor,
                    event_type=AuditEventType.EMPLOYEE_DOCUMENT_VIEWED,
                    resource_type="employee",
                    resource_id=employee_id,
                    action="view_own_documents",
                    metadata={"access_scope": "own"},
                )
                return OwnEmployeeDocumentWorkspaceRead(
                    employee_id=employee_id,
                    summary=summarize_checklist(checklist),
                    checklist=checklist,
                    documents=documents,
                )

            return await unit_of_work.execute(operation)

    async def initiate_upload(
        self,
        *,
        tenant_id: UUID,
        employee_id: UUID,
        payload: EmployeeDocumentUploadInitiate,
        request_context: RequestContext,
    ) -> EmployeeDocumentUploadGrantRead:
        actor = _Actor.from_request_context(request_context)
        filename, extension = sanitize_display_filename(payload.display_filename)
        content_type = payload.declared_content_type.value
        if _MIME_BY_EXTENSION.get(extension) != content_type:
            raise DocumentValidationError("Filename extension and declared MIME type do not match")
        async with self._tenant_session(tenant_id, actor) as session:
            unit_of_work = SqlAlchemyUnitOfWork(session)

            async def operation() -> EmployeeDocumentUploadGrantRead:
                await self._require_employee(session, tenant_id, employee_id)
                document_count = await session.scalar(
                    select(func.count(EmployeeDocument.id)).where(
                        EmployeeDocument.tenant_id == tenant_id,
                        EmployeeDocument.employee_id == employee_id,
                    )
                )
                if int(document_count or 0) >= DOCUMENT_LIST_LIMIT:
                    raise DocumentConflictError(
                        "Employee document retention limit has been reached"
                    )
                document_type = await self._document_type(
                    session,
                    tenant_id=tenant_id,
                    document_type_id=payload.document_type_id,
                )
                if document_type.archived_at is not None:
                    raise DocumentTypeNotFoundError
                self._validate_upload_policy(
                    document_type=document_type,
                    content_type=content_type,
                    extension=extension,
                    size_bytes=payload.size_bytes,
                    issued_on=payload.issued_on,
                    expires_on=payload.expires_on,
                    employee_visible=payload.employee_visible,
                )
                document_id = uuid4()
                object_id = uuid4()
                intent_id = uuid4()
                final_key = _final_object_key(
                    tenant_id=tenant_id,
                    employee_id=employee_id,
                    document_id=document_id,
                    object_id=object_id,
                )
                upload_key = f"{final_key}.upload-{intent_id}"
                expected_metadata = {
                    "tenant-id": str(tenant_id),
                    "employee-id": str(employee_id),
                    "document-id": str(document_id),
                    "object-id": str(object_id),
                    "intent-id": str(intent_id),
                    "expected-size": str(payload.size_bytes),
                    "expected-type": content_type,
                }
                try:
                    grant = await self._storage.presign_upload(
                        key=upload_key,
                        content_type=content_type,
                        content_length=payload.size_bytes,
                        metadata=expected_metadata,
                        ttl_seconds=self._settings.document_upload_ttl_seconds,
                    )
                except ObjectStorageError as exc:
                    raise DocumentStorageUnavailableError from exc
                visible = (
                    document_type.employee_visible
                    if payload.employee_visible is None
                    else payload.employee_visible
                )
                document = EmployeeDocument(
                    id=document_id,
                    tenant_id=tenant_id,
                    employee_id=employee_id,
                    document_type_id=document_type.id,
                    object_id=object_id,
                    object_key=final_key,
                    display_filename=filename,
                    normalized_extension=extension,
                    declared_content_type=content_type,
                    stored_content_type=None,
                    size_bytes=payload.size_bytes,
                    sha256=None,
                    issued_on=payload.issued_on,
                    expires_on=payload.expires_on,
                    employee_visible=visible,
                    processing_state=DocumentProcessingState.PENDING_UPLOAD.value,
                    version=1,
                )
                now = datetime.now(UTC)
                intent = EmployeeDocumentUploadIntent(
                    id=intent_id,
                    tenant_id=tenant_id,
                    document_id=document_id,
                    initiated_by_user_id=actor.user_id,
                    initiated_by_membership_id=actor.membership_id,
                    upload_object_key=upload_key,
                    expected_content_type=content_type,
                    expected_size_bytes=payload.size_bytes,
                    expected_extension=extension,
                    expected_metadata=expected_metadata,
                    status=DocumentUploadIntentStatus.ACTIVE.value,
                    expires_at=now
                    + timedelta(
                        seconds=max(
                            self._settings.document_upload_ttl_seconds,
                            self._settings.document_upload_intent_ttl_minutes * 60,
                        )
                    ),
                    finalized_at=None,
                )
                session.add_all((document, intent))
                await session.flush()
                await self._record_user_audit(
                    session,
                    tenant_id=tenant_id,
                    actor=actor,
                    event_type=AuditEventType.EMPLOYEE_DOCUMENT_UPLOAD_INITIATED,
                    resource_type="employee_document",
                    resource_id=document.id,
                    action="initiate_upload",
                    changed_fields=("processing_state",),
                    metadata={
                        "after_state": document.processing_state,
                        "file_class": _FILE_CLASS_BY_MIME[content_type],
                        "sensitivity": document_type.sensitivity,
                    },
                )
                return EmployeeDocumentUploadGrantRead(
                    document=_document_read(document, document_type),
                    upload_intent_id=intent.id,
                    method=grant.method,
                    url=grant.url,
                    headers=dict(grant.headers),
                    expires_at=grant.expires_at,
                )

            return await unit_of_work.execute(operation)

    async def finalize_upload(
        self,
        *,
        tenant_id: UUID,
        employee_id: UUID,
        document_id: UUID,
        upload_intent_id: UUID,
        request_context: RequestContext,
    ) -> EmployeeDocumentRead:
        actor = _Actor.from_request_context(request_context)
        snapshot, existing = await self._finalize_snapshot(
            tenant_id=tenant_id,
            employee_id=employee_id,
            document_id=document_id,
            upload_intent_id=upload_intent_id,
            actor=actor,
        )
        if existing is not None:
            return existing

        try:
            head = await self._storage.head(snapshot.upload_key)
        except ObjectNotFoundError as exc:
            raise DocumentConflictError("The uploaded object is not available") from exc
        except ObjectStorageError as exc:
            raise DocumentStorageUnavailableError from exc
        try:
            self._validate_staging_head(snapshot, head)
        except DocumentValidationError:
            await self._reject_upload(tenant_id=tenant_id, snapshot=snapshot, actor=actor)
            await self._safe_delete(snapshot.upload_key)
            raise

        with tempfile.TemporaryDirectory(prefix="wf-document-scan-") as directory:
            local_path = Path(directory) / "object"
            try:
                downloaded = await self._storage.download_to_path(
                    key=snapshot.upload_key,
                    destination=local_path,
                    maximum_bytes=snapshot.size_bytes,
                )
            except ObjectStorageError as exc:
                raise DocumentStorageUnavailableError from exc
            try:
                if downloaded.size_bytes != snapshot.size_bytes:
                    raise DocumentValidationError("Stored object size does not match upload intent")
                _validate_magic(snapshot.content_type, downloaded.magic_prefix)
            except DocumentValidationError:
                await self._reject_upload(tenant_id=tenant_id, snapshot=snapshot, actor=actor)
                await self._safe_delete(snapshot.upload_key)
                raise

            final_metadata = {
                "tenant-id": str(tenant_id),
                "employee-id": str(employee_id),
                "document-id": str(document_id),
                "object-id": str(snapshot.object_id),
                "intent-id": str(upload_intent_id),
                "sha256": downloaded.sha256,
            }
            try:
                await self._storage.copy_if_absent(
                    source_key=snapshot.upload_key,
                    destination_key=snapshot.final_key,
                    content_type=snapshot.content_type,
                    metadata=final_metadata,
                )
            except ObjectAlreadyExistsError:
                await self._validate_existing_final_object(snapshot, final_metadata)
            except ObjectStorageError as exc:
                raise DocumentStorageUnavailableError from exc

            pending = await self._mark_pending_scan(
                tenant_id=tenant_id,
                snapshot=snapshot,
                actor=actor,
                sha256=downloaded.sha256,
            )
            await self._safe_delete(snapshot.upload_key)
            if pending.processing_state != DocumentProcessingState.PENDING_SCAN:
                return pending

            try:
                scan = await self._scanner.scan(local_path)
            except MalwareScanError as exc:
                return await self._record_scan_result(
                    tenant_id=tenant_id,
                    document_id=document_id,
                    result=DocumentScanResult.ERROR,
                    provider=self._settings.document_scanner_backend,
                    version=None,
                    error_code=exc.error_code,
                    audit_context=actor.audit_context,
                )
            result = (
                DocumentScanResult.CLEAN
                if scan.verdict is MalwareScanVerdict.CLEAN
                else DocumentScanResult.INFECTED
            )
            return await self._record_scan_result(
                tenant_id=tenant_id,
                document_id=document_id,
                result=result,
                provider=scan.provider,
                version=scan.version,
                error_code=None,
                audit_context=actor.audit_context,
            )

    async def update_document_metadata(
        self,
        *,
        tenant_id: UUID,
        employee_id: UUID,
        document_id: UUID,
        payload: EmployeeDocumentMetadataUpdate,
        request_context: RequestContext,
    ) -> EmployeeDocumentRead:
        actor = _Actor.from_request_context(request_context)
        async with self._tenant_session(tenant_id, actor) as session:
            unit_of_work = SqlAlchemyUnitOfWork(session)

            async def operation() -> EmployeeDocumentRead:
                document, document_type = await self._document_with_type(
                    session,
                    tenant_id=tenant_id,
                    employee_id=employee_id,
                    document_id=document_id,
                    lock=True,
                )
                if document.version != payload.expected_version:
                    raise DocumentVersionConflictError
                if document.archived_at is not None:
                    raise DocumentConflictError("Archived documents are read-only")
                changed_fields: list[str] = []
                if "display_filename" in payload.model_fields_set:
                    filename, extension = sanitize_display_filename(payload.display_filename or "")
                    if _MIME_BY_EXTENSION.get(extension) != document.declared_content_type:
                        raise DocumentValidationError(
                            "Filename extension does not match immutable document content"
                        )
                    if filename != document.display_filename:
                        document.display_filename = filename
                        changed_fields.append("display_filename")
                issued_on = (
                    payload.issued_on
                    if "issued_on" in payload.model_fields_set
                    else document.issued_on
                )
                expires_on = (
                    payload.expires_on
                    if "expires_on" in payload.model_fields_set
                    else document.expires_on
                )
                self._validate_expiry(document_type, issued_on, expires_on)
                for field_name, value in (("issued_on", issued_on), ("expires_on", expires_on)):
                    if (
                        field_name in payload.model_fields_set
                        and getattr(document, field_name) != value
                    ):
                        setattr(document, field_name, value)
                        changed_fields.append(field_name)
                if "employee_visible" in payload.model_fields_set:
                    visible = bool(payload.employee_visible)
                    if visible and not document_type.employee_visible:
                        raise DocumentValidationError(
                            "This document type cannot be made employee-visible"
                        )
                    if document.employee_visible != visible:
                        document.employee_visible = visible
                        changed_fields.append("employee_visible")
                if changed_fields:
                    await session.flush()
                    await session.refresh(document)
                    await self._record_user_audit(
                        session,
                        tenant_id=tenant_id,
                        actor=actor,
                        event_type=AuditEventType.EMPLOYEE_DOCUMENT_UPDATED,
                        resource_type="employee_document",
                        resource_id=document.id,
                        action="update_metadata",
                        changed_fields=tuple(changed_fields),
                    )
                return _document_read(document, document_type)

            return await unit_of_work.execute(operation)

    async def set_document_archived(
        self,
        *,
        tenant_id: UUID,
        employee_id: UUID,
        document_id: UUID,
        expected_version: int,
        archived: bool,
        request_context: RequestContext,
    ) -> EmployeeDocumentRead:
        actor = _Actor.from_request_context(request_context)
        async with self._tenant_session(tenant_id, actor) as session:
            unit_of_work = SqlAlchemyUnitOfWork(session)

            async def operation() -> EmployeeDocumentRead:
                document, document_type = await self._document_with_type(
                    session,
                    tenant_id=tenant_id,
                    employee_id=employee_id,
                    document_id=document_id,
                    lock=True,
                )
                if document.version != expected_version:
                    raise DocumentVersionConflictError
                currently_archived = document.archived_at is not None
                if currently_archived == archived:
                    return _document_read(document, document_type)
                document.archived_at = datetime.now(UTC) if archived else None
                await session.flush()
                await session.refresh(document)
                await self._record_user_audit(
                    session,
                    tenant_id=tenant_id,
                    actor=actor,
                    event_type=(
                        AuditEventType.EMPLOYEE_DOCUMENT_ARCHIVED
                        if archived
                        else AuditEventType.EMPLOYEE_DOCUMENT_UNARCHIVED
                    ),
                    resource_type="employee_document",
                    resource_id=document.id,
                    action="archive" if archived else "unarchive",
                    changed_fields=("archived_at",),
                    metadata={
                        "before_state": "active" if archived else "archived",
                        "after_state": "archived" if archived else "active",
                    },
                )
                return _document_read(document, document_type)

            return await unit_of_work.execute(operation)

    async def issue_hr_download(
        self,
        *,
        tenant_id: UUID,
        employee_id: UUID,
        document_id: UUID,
        request_context: RequestContext,
    ) -> EmployeeDocumentDownloadGrantRead:
        return await self._issue_download(
            tenant_id=tenant_id,
            employee_id=employee_id,
            document_id=document_id,
            actor=_Actor.from_request_context(request_context),
            own_only=False,
        )

    async def issue_own_download(
        self,
        *,
        tenant_id: UUID,
        document_id: UUID,
        request_context: RequestContext,
    ) -> EmployeeDocumentDownloadGrantRead:
        actor = _Actor.from_request_context(request_context)
        async with self._tenant_session(tenant_id, actor) as session:
            async with session.begin():
                employee_id = await self._own_employee_id(session, tenant_id, actor)
        return await self._issue_download(
            tenant_id=tenant_id,
            employee_id=employee_id,
            document_id=document_id,
            actor=actor,
            own_only=True,
        )

    async def _issue_download(
        self,
        *,
        tenant_id: UUID,
        employee_id: UUID,
        document_id: UUID,
        actor: _Actor,
        own_only: bool,
    ) -> EmployeeDocumentDownloadGrantRead:
        async with self._tenant_session(tenant_id, actor) as session:
            unit_of_work = SqlAlchemyUnitOfWork(session)

            async def operation() -> EmployeeDocumentDownloadGrantRead:
                if own_only:
                    current_employee_id = await self._own_employee_id(session, tenant_id, actor)
                    if current_employee_id != employee_id:
                        raise DocumentNotFoundError
                document, document_type = await self._document_with_type(
                    session,
                    tenant_id=tenant_id,
                    employee_id=employee_id,
                    document_id=document_id,
                )
                if (
                    document.archived_at is not None
                    or document.processing_state != DocumentProcessingState.AVAILABLE.value
                ):
                    raise DocumentConflictError("Document is not available for download")
                if own_only and (
                    not document.employee_visible
                    or not document_type.employee_visible
                    or document_type.archived_at is not None
                ):
                    raise DocumentNotFoundError
                download_name = f"employee-document.{document.normalized_extension}"
                try:
                    grant = await self._storage.presign_download(
                        key=document.object_key,
                        download_name=download_name,
                        ttl_seconds=self._settings.document_download_ttl_seconds,
                    )
                except ObjectStorageError as exc:
                    raise DocumentStorageUnavailableError from exc
                await self._record_user_audit(
                    session,
                    tenant_id=tenant_id,
                    actor=actor,
                    event_type=AuditEventType.EMPLOYEE_DOCUMENT_DOWNLOAD_URL_ISSUED,
                    resource_type="employee_document",
                    resource_id=document.id,
                    action="issue_download_url",
                    metadata={"access_scope": "own" if own_only else "hr"},
                )
                return EmployeeDocumentDownloadGrantRead(
                    document_id=document.id,
                    method=grant.method,
                    url=grant.url,
                    expires_at=grant.expires_at,
                )

            return await unit_of_work.execute(operation)

    async def _finalize_snapshot(
        self,
        *,
        tenant_id: UUID,
        employee_id: UUID,
        document_id: UUID,
        upload_intent_id: UUID,
        actor: _Actor,
    ) -> tuple[_FinalizeSnapshot, EmployeeDocumentRead | None]:
        async with self._tenant_session(tenant_id, actor) as session:
            async with session.begin():
                row = (
                    await session.execute(
                        select(EmployeeDocument, EmployeeDocumentUploadIntent, DocumentType)
                        .join(
                            EmployeeDocumentUploadIntent,
                            and_(
                                EmployeeDocumentUploadIntent.tenant_id
                                == EmployeeDocument.tenant_id,
                                EmployeeDocumentUploadIntent.document_id == EmployeeDocument.id,
                            ),
                        )
                        .join(
                            DocumentType,
                            and_(
                                DocumentType.tenant_id == EmployeeDocument.tenant_id,
                                DocumentType.id == EmployeeDocument.document_type_id,
                            ),
                        )
                        .where(
                            EmployeeDocument.tenant_id == tenant_id,
                            EmployeeDocument.employee_id == employee_id,
                            EmployeeDocument.id == document_id,
                            EmployeeDocumentUploadIntent.id == upload_intent_id,
                        )
                    )
                ).one_or_none()
                if row is None:
                    raise DocumentNotFoundError
                document, intent, document_type = row
                if (
                    intent.initiated_by_user_id != actor.user_id
                    or intent.initiated_by_membership_id != actor.membership_id
                ):
                    raise DocumentNotFoundError
                if document.processing_state in _FINALIZED_STATES:
                    return _snapshot(document, intent), _document_read(document, document_type)
                if (
                    document.archived_at is not None
                    or document.processing_state
                    != DocumentProcessingState.PENDING_UPLOAD.value
                    or intent.status != DocumentUploadIntentStatus.ACTIVE.value
                ):
                    raise DocumentConflictError("Upload cannot be finalized in its current state")
                expires_at = _as_utc(intent.expires_at)
                if expires_at <= datetime.now(UTC):
                    raise DocumentConflictError("Upload authorization has expired")
                return _snapshot(document, intent), None

    async def _mark_pending_scan(
        self,
        *,
        tenant_id: UUID,
        snapshot: _FinalizeSnapshot,
        actor: _Actor,
        sha256: str,
    ) -> EmployeeDocumentRead:
        async with self._tenant_session(tenant_id, actor) as session:
            unit_of_work = SqlAlchemyUnitOfWork(session)

            async def operation() -> EmployeeDocumentRead:
                row = (
                    await session.execute(
                        select(EmployeeDocument, EmployeeDocumentUploadIntent, DocumentType)
                        .join(
                            EmployeeDocumentUploadIntent,
                            and_(
                                EmployeeDocumentUploadIntent.tenant_id
                                == EmployeeDocument.tenant_id,
                                EmployeeDocumentUploadIntent.document_id == EmployeeDocument.id,
                            ),
                        )
                        .join(
                            DocumentType,
                            and_(
                                DocumentType.tenant_id == EmployeeDocument.tenant_id,
                                DocumentType.id == EmployeeDocument.document_type_id,
                            ),
                        )
                        .where(
                            EmployeeDocument.tenant_id == tenant_id,
                            EmployeeDocument.id == snapshot.document_id,
                            EmployeeDocumentUploadIntent.id == snapshot.intent_id,
                        )
                        .with_for_update(of=(EmployeeDocument, EmployeeDocumentUploadIntent))
                    )
                ).one_or_none()
                if row is None:
                    raise DocumentNotFoundError
                document, intent, document_type = row
                if document.processing_state in _FINALIZED_STATES:
                    return _document_read(document, document_type)
                if (
                    intent.initiated_by_user_id != actor.user_id
                    or intent.initiated_by_membership_id != actor.membership_id
                    or intent.status != DocumentUploadIntentStatus.ACTIVE.value
                    or document.processing_state != DocumentProcessingState.PENDING_UPLOAD.value
                ):
                    raise DocumentConflictError("Upload cannot be finalized in its current state")
                now = datetime.now(UTC)
                document.stored_content_type = snapshot.content_type
                document.sha256 = sha256
                document.finalized_at = now
                document.processing_state = DocumentProcessingState.PENDING_SCAN.value
                intent.status = DocumentUploadIntentStatus.FINALIZED.value
                intent.finalized_at = now
                await session.flush()
                await session.refresh(document)
                await self._record_user_audit(
                    session,
                    tenant_id=tenant_id,
                    actor=actor,
                    event_type=AuditEventType.EMPLOYEE_DOCUMENT_UPLOAD_FINALIZED,
                    resource_type="employee_document",
                    resource_id=document.id,
                    action="finalize_upload",
                    changed_fields=("processing_state", "finalized_at"),
                    metadata={
                        "before_state": DocumentProcessingState.PENDING_UPLOAD.value,
                        "after_state": DocumentProcessingState.PENDING_SCAN.value,
                        "file_class": _FILE_CLASS_BY_MIME[snapshot.content_type],
                    },
                )
                return _document_read(document, document_type)

            return await unit_of_work.execute(operation)

    async def _record_scan_result(
        self,
        *,
        tenant_id: UUID,
        document_id: UUID,
        result: DocumentScanResult,
        provider: str,
        version: str | None,
        error_code: str | None,
        audit_context: AuditContext,
    ) -> EmployeeDocumentRead:
        async with self._tenant_session(tenant_id) as session:
            unit_of_work = SqlAlchemyUnitOfWork(session)

            async def operation() -> EmployeeDocumentRead:
                row = (
                    await session.execute(
                        select(EmployeeDocument, DocumentType)
                        .join(
                            DocumentType,
                            and_(
                                DocumentType.tenant_id == EmployeeDocument.tenant_id,
                                DocumentType.id == EmployeeDocument.document_type_id,
                            ),
                        )
                        .where(
                            EmployeeDocument.tenant_id == tenant_id,
                            EmployeeDocument.id == document_id,
                        )
                        .with_for_update(of=EmployeeDocument)
                    )
                ).one_or_none()
                if row is None:
                    raise DocumentNotFoundError
                document, document_type = row
                if document.processing_state != DocumentProcessingState.PENDING_SCAN.value:
                    if document.processing_state in {
                        DocumentProcessingState.AVAILABLE.value,
                        DocumentProcessingState.INFECTED.value,
                        DocumentProcessingState.SCAN_ERROR.value,
                    }:
                        return _document_read(document, document_type)
                    raise DocumentConflictError("Document is not pending malware scan")
                state = {
                    DocumentScanResult.CLEAN: DocumentProcessingState.AVAILABLE,
                    DocumentScanResult.INFECTED: DocumentProcessingState.INFECTED,
                    DocumentScanResult.ERROR: DocumentProcessingState.SCAN_ERROR,
                }[result]
                document.processing_state = state.value
                document.scanned_at = datetime.now(UTC)
                document.scan_result = result.value
                document.scanner_provider = _safe_scanner_value(provider, 32)
                document.scanner_version = _safe_scanner_value(version, 64)
                document.scan_error_code = _safe_scanner_value(error_code, 32)
                await session.flush()
                await session.refresh(document)
                await self._audit_recorder_factory(session).record(
                    AuditEventDraft(
                        scope_type=AuditScopeType.TENANT,
                        tenant_id=tenant_id,
                        actor_type=AuditActorType.WORKER,
                        event_type=AuditEventType.EMPLOYEE_DOCUMENT_SCAN_COMPLETED,
                        category=AuditCategory.HR_OPERATIONS,
                        resource_type="employee_document",
                        resource_id=document.id,
                        action="scan",
                        result=AuditResult.SUCCESS,
                        context=audit_context,
                        changed_fields=("processing_state", "scan_result", "scanned_at"),
                        metadata={
                            "before_state": DocumentProcessingState.PENDING_SCAN.value,
                            "after_state": state.value,
                            "scan_result": result.value,
                            "scanner_provider": document.scanner_provider,
                        },
                        data_classification=AuditDataClassification.HR_METADATA,
                        visibility_class=AuditVisibilityClass.HR_OPERATIONS,
                    )
                )
                return _document_read(document, document_type)

            return await unit_of_work.execute(operation)

    async def _reject_upload(
        self,
        *,
        tenant_id: UUID,
        snapshot: _FinalizeSnapshot,
        actor: _Actor,
    ) -> None:
        async with self._tenant_session(tenant_id, actor) as session:
            unit_of_work = SqlAlchemyUnitOfWork(session)

            async def operation() -> None:
                row = (
                    await session.execute(
                        select(EmployeeDocument, EmployeeDocumentUploadIntent)
                        .join(
                            EmployeeDocumentUploadIntent,
                            and_(
                                EmployeeDocumentUploadIntent.tenant_id
                                == EmployeeDocument.tenant_id,
                                EmployeeDocumentUploadIntent.document_id == EmployeeDocument.id,
                            ),
                        )
                        .where(
                            EmployeeDocument.tenant_id == tenant_id,
                            EmployeeDocument.id == snapshot.document_id,
                            EmployeeDocumentUploadIntent.id == snapshot.intent_id,
                        )
                        .with_for_update(of=(EmployeeDocument, EmployeeDocumentUploadIntent))
                    )
                ).one_or_none()
                if row is None:
                    return
                document, intent = row
                if document.processing_state != DocumentProcessingState.PENDING_UPLOAD.value:
                    return
                document.processing_state = DocumentProcessingState.REJECTED.value
                intent.status = DocumentUploadIntentStatus.REJECTED.value
                await session.flush()
                await self._record_user_audit(
                    session,
                    tenant_id=tenant_id,
                    actor=actor,
                    event_type=AuditEventType.EMPLOYEE_DOCUMENT_UPLOAD_FINALIZED,
                    resource_type="employee_document",
                    resource_id=document.id,
                    action="reject_upload",
                    result=AuditResult.FAILURE,
                    changed_fields=("processing_state",),
                    metadata={
                        "before_state": DocumentProcessingState.PENDING_UPLOAD.value,
                        "after_state": DocumentProcessingState.REJECTED.value,
                        "file_class": _FILE_CLASS_BY_MIME[snapshot.content_type],
                    },
                )

            await unit_of_work.execute(operation)

    async def _validate_existing_final_object(
        self,
        snapshot: _FinalizeSnapshot,
        expected_metadata: dict[str, str],
    ) -> None:
        try:
            head = await self._storage.head(snapshot.final_key)
        except ObjectStorageError as exc:
            raise DocumentStorageUnavailableError from exc
        if (
            head.size_bytes != snapshot.size_bytes
            or _normalize_content_type(head.content_type) != snapshot.content_type
            or any(head.metadata.get(key) != value for key, value in expected_metadata.items())
        ):
            raise DocumentConflictError("Immutable document object key is already occupied")

    async def _safe_delete(self, key: str) -> None:
        try:
            await self._storage.delete(key)
        except ObjectStorageError:
            # A staging cleanup failure cannot make the immutable finalized object downloadable.
            return

    def _validate_staging_head(self, snapshot: _FinalizeSnapshot, head: ObjectHead) -> None:
        if head.key != snapshot.upload_key:
            raise DocumentValidationError("Stored object key does not match upload intent")
        if head.size_bytes != snapshot.size_bytes:
            raise DocumentValidationError("Stored object size does not match upload intent")
        if _normalize_content_type(head.content_type) != snapshot.content_type:
            raise DocumentValidationError("Stored object MIME type does not match upload intent")
        if any(
            head.metadata.get(name) != value
            for name, value in snapshot.expected_metadata.items()
        ):
            raise DocumentValidationError("Stored object metadata does not match upload intent")

    def _validate_type_policy(self, payload: DocumentTypeCreate) -> None:
        self._validate_type_policy_values(
            name=payload.name,
            description=payload.description,
            required=payload.required,
            employee_visible=payload.employee_visible,
            sensitivity=payload.sensitivity.value,
            expiry_mode=payload.expiry_mode.value,
            allowed_mime_types=sorted(item.value for item in payload.allowed_mime_types),
            allowed_extensions=sorted(item.value for item in payload.allowed_extensions),
            max_size_bytes=payload.max_size_bytes,
        )

    def _validate_type_policy_values(
        self,
        *,
        name: str,
        description: str | None,
        required: bool,
        employee_visible: bool,
        sensitivity: str,
        expiry_mode: str,
        allowed_mime_types: list[str],
        allowed_extensions: list[str],
        max_size_bytes: int,
    ) -> None:
        del name, description, required, employee_visible, sensitivity, expiry_mode
        if max_size_bytes > self._settings.document_default_max_size_bytes:
            raise DocumentValidationError(
                "Document type maximum exceeds the configured application maximum"
            )
        if len(set(allowed_mime_types)) != len(allowed_mime_types) or len(
            set(allowed_extensions)
        ) != len(allowed_extensions):
            raise DocumentValidationError("Document type file policy contains duplicates")
        known_mime_types = {item.value for item in AllowedDocumentMimeType}
        if any(value not in known_mime_types for value in allowed_mime_types):
            raise DocumentValidationError("Document type MIME policy is invalid")
        if any(value not in _MIME_BY_EXTENSION for value in allowed_extensions):
            raise DocumentValidationError("Document type extension policy is invalid")
        represented_mimes = {_MIME_BY_EXTENSION[value] for value in allowed_extensions}
        if represented_mimes != set(allowed_mime_types):
            raise DocumentValidationError("Document type MIME and extension policies differ")

    def _validate_upload_policy(
        self,
        *,
        document_type: DocumentType,
        content_type: str,
        extension: str,
        size_bytes: int,
        issued_on: date | None,
        expires_on: date | None,
        employee_visible: bool | None,
    ) -> None:
        if content_type not in document_type.allowed_mime_types:
            raise DocumentValidationError("Declared MIME type is not allowed for this type")
        if extension not in document_type.allowed_extensions:
            raise DocumentValidationError("Filename extension is not allowed for this type")
        if size_bytes > min(
            document_type.max_size_bytes,
            self._settings.document_default_max_size_bytes,
        ):
            raise DocumentValidationError("Document exceeds the configured file-size limit")
        if employee_visible and not document_type.employee_visible:
            raise DocumentValidationError("This document type cannot be employee-visible")
        self._validate_expiry(document_type, issued_on, expires_on)

    @staticmethod
    def _validate_expiry(
        document_type: DocumentType,
        issued_on: date | None,
        expires_on: date | None,
    ) -> None:
        if issued_on is not None and expires_on is not None and expires_on < issued_on:
            raise DocumentValidationError("Document expiry date cannot precede issue date")
        if document_type.expiry_mode == DocumentExpiryMode.NONE.value and expires_on is not None:
            raise DocumentValidationError("This document type does not allow an expiry date")
        if document_type.expiry_mode == DocumentExpiryMode.REQUIRED.value and expires_on is None:
            raise DocumentValidationError("This document type requires an expiry date")

    async def _list_documents(
        self,
        session: AsyncSession,
        *,
        tenant_id: UUID,
        employee_id: UUID,
        own_only: bool,
    ) -> list[EmployeeDocumentRead]:
        statement = (
            select(EmployeeDocument, DocumentType)
            .join(
                DocumentType,
                and_(
                    DocumentType.tenant_id == EmployeeDocument.tenant_id,
                    DocumentType.id == EmployeeDocument.document_type_id,
                ),
            )
            .where(
                EmployeeDocument.tenant_id == tenant_id,
                EmployeeDocument.employee_id == employee_id,
            )
            .order_by(
                EmployeeDocument.archived_at.nulls_first(),
                EmployeeDocument.created_at.desc(),
                EmployeeDocument.id.desc(),
            )
            .limit(DOCUMENT_LIST_LIMIT)
        )
        if own_only:
            statement = statement.where(
                EmployeeDocument.archived_at.is_(None),
                EmployeeDocument.employee_visible.is_(True),
                EmployeeDocument.processing_state == DocumentProcessingState.AVAILABLE.value,
                DocumentType.employee_visible.is_(True),
                DocumentType.archived_at.is_(None),
            )
        rows = (await session.execute(statement)).all()
        return [_document_read(document, document_type) for document, document_type in rows]

    async def _list_own_documents(
        self,
        session: AsyncSession,
        *,
        tenant_id: UUID,
        employee_id: UUID,
    ) -> list[OwnEmployeeDocumentRead]:
        records = await self._list_documents(
            session,
            tenant_id=tenant_id,
            employee_id=employee_id,
            own_only=True,
        )
        return [
            OwnEmployeeDocumentRead(
                id=record.id,
                employee_id=record.employee_id,
                document_type_id=record.document_type_id,
                document_type_name=record.document_type_name,
                display_filename=record.display_filename,
                content_type=record.content_type,
                size_bytes=record.size_bytes,
                issued_on=record.issued_on,
                expires_on=record.expires_on,
                created_at=record.created_at,
            )
            for record in records
        ]

    async def _document_type(
        self,
        session: AsyncSession,
        *,
        tenant_id: UUID,
        document_type_id: UUID,
        lock: bool = False,
    ) -> DocumentType:
        statement = select(DocumentType).where(
            DocumentType.tenant_id == tenant_id,
            DocumentType.id == document_type_id,
        )
        if lock:
            statement = statement.with_for_update(of=DocumentType)
        record = await session.scalar(statement)
        if record is None:
            raise DocumentTypeNotFoundError
        return record

    async def _document_with_type(
        self,
        session: AsyncSession,
        *,
        tenant_id: UUID,
        employee_id: UUID,
        document_id: UUID,
        lock: bool = False,
    ) -> tuple[EmployeeDocument, DocumentType]:
        statement = (
            select(EmployeeDocument, DocumentType)
            .join(
                DocumentType,
                and_(
                    DocumentType.tenant_id == EmployeeDocument.tenant_id,
                    DocumentType.id == EmployeeDocument.document_type_id,
                ),
            )
            .where(
                EmployeeDocument.tenant_id == tenant_id,
                EmployeeDocument.employee_id == employee_id,
                EmployeeDocument.id == document_id,
            )
        )
        if lock:
            statement = statement.with_for_update(of=EmployeeDocument)
        row = (await session.execute(statement)).one_or_none()
        if row is None:
            raise DocumentNotFoundError
        return row

    @staticmethod
    async def _require_employee(
        session: AsyncSession,
        tenant_id: UUID,
        employee_id: UUID,
        *,
        include_archived: bool = False,
    ) -> None:
        statement = select(Employee.id).where(
            Employee.tenant_id == tenant_id,
            Employee.id == employee_id,
        )
        if not include_archived:
            statement = statement.where(Employee.archived_at.is_(None))
        if await session.scalar(statement) is None:
            raise DocumentNotFoundError

    @staticmethod
    async def _own_employee_id(
        session: AsyncSession,
        tenant_id: UUID,
        actor: _Actor,
    ) -> UUID:
        employee_id = await session.scalar(
            select(Employee.id)
            .join(
                EmployeeAccountLink,
                and_(
                    EmployeeAccountLink.tenant_id == Employee.tenant_id,
                    EmployeeAccountLink.employee_id == Employee.id,
                ),
            )
            .join(
                TenantMembership,
                and_(
                    TenantMembership.tenant_id == EmployeeAccountLink.tenant_id,
                    TenantMembership.id == EmployeeAccountLink.membership_id,
                ),
            )
            .where(
                Employee.tenant_id == tenant_id,
                Employee.archived_at.is_(None),
                EmployeeAccountLink.membership_id == actor.membership_id,
                TenantMembership.legacy_user_id == actor.user_id,
            )
        )
        if employee_id is None:
            raise DocumentNotFoundError
        return employee_id

    def _tenant_session(self, tenant_id: UUID, actor: _Actor | None = None) -> AsyncSession:
        session = self._session_factory()
        configure_tenant_database_access(
            session,
            tenant_id,
            actor_id=actor.user_id if actor is not None else None,
            membership_id=actor.membership_id if actor is not None else None,
        )
        return session

    async def _record_user_audit(
        self,
        session: AsyncSession,
        *,
        tenant_id: UUID,
        actor: _Actor,
        event_type: AuditEventType,
        resource_type: str,
        resource_id: UUID,
        action: str,
        result: AuditResult = AuditResult.SUCCESS,
        changed_fields: tuple[str, ...] = (),
        metadata: dict[str, object] | None = None,
    ) -> None:
        await self._audit_recorder_factory(session).record(
            AuditEventDraft(
                scope_type=AuditScopeType.TENANT,
                tenant_id=tenant_id,
                actor_type=AuditActorType.USER,
                actor_user_id=actor.user_id,
                event_type=event_type,
                category=AuditCategory.HR_OPERATIONS,
                resource_type=resource_type,
                resource_id=resource_id,
                action=action,
                result=result,
                context=actor.audit_context,
                session_id=actor.session_id,
                changed_fields=changed_fields,
                metadata=metadata or {},
                data_classification=AuditDataClassification.HR_METADATA,
                visibility_class=AuditVisibilityClass.HR_OPERATIONS,
            )
        )


def summarize_checklist(
    checklist: Sequence[DocumentChecklistItemRead],
) -> EmployeeDocumentSummaryRead:
    return EmployeeDocumentSummaryRead(
        missing=sum(
            item.required and item.status is DocumentChecklistStatus.MISSING
            for item in checklist
        ),
        available=sum(item.status is DocumentChecklistStatus.AVAILABLE for item in checklist),
        expiring=sum(item.status is DocumentChecklistStatus.EXPIRING for item in checklist),
        expired=sum(item.status is DocumentChecklistStatus.EXPIRED for item in checklist),
    )


def sanitize_display_filename(value: str) -> tuple[str, str]:
    normalized = unicodedata.normalize("NFKC", value)
    normalized = "".join(character for character in normalized if character.isprintable())
    normalized = sub(r"[\\/:]+", "_", normalized)
    normalized = sub(r"\s+", " ", normalized).strip(" .")
    extension = normalized.rsplit(".", 1)[-1].lower() if "." in normalized else ""
    if extension not in _MIME_BY_EXTENSION:
        raise DocumentValidationError("Filename must use PDF, JPG, JPEG, or PNG extension")
    stem = normalized[: -(len(extension) + 1)].strip(" .")
    if not stem:
        stem = "document"
    maximum_stem_length = 255 - len(extension) - 1
    stem = stem[:maximum_stem_length].rstrip(" .") or "document"
    return f"{stem}.{extension}", extension


def _validate_magic(content_type: str, prefix: bytes) -> None:
    matches = {
        AllowedDocumentMimeType.PDF.value: prefix.startswith(b"%PDF-"),
        AllowedDocumentMimeType.JPEG.value: prefix.startswith(b"\xff\xd8\xff"),
        AllowedDocumentMimeType.PNG.value: prefix.startswith(b"\x89PNG\r\n\x1a\n"),
    }
    if not matches.get(content_type, False):
        raise DocumentValidationError("Stored object signature does not match its MIME type")


def _normalize_content_type(value: str) -> str:
    return value.split(";", 1)[0].strip().lower()


def _final_object_key(
    *,
    tenant_id: UUID,
    employee_id: UUID,
    document_id: UUID,
    object_id: UUID,
) -> str:
    return (
        f"tenants/{tenant_id}/employees/{employee_id}/documents/"
        f"{document_id}/{object_id}"
    )


def _snapshot(
    document: EmployeeDocument,
    intent: EmployeeDocumentUploadIntent,
) -> _FinalizeSnapshot:
    return _FinalizeSnapshot(
        document_id=document.id,
        employee_id=document.employee_id,
        intent_id=intent.id,
        upload_key=intent.upload_object_key,
        final_key=document.object_key,
        content_type=intent.expected_content_type,
        size_bytes=intent.expected_size_bytes,
        extension=intent.expected_extension,
        expected_metadata={str(key): str(value) for key, value in intent.expected_metadata.items()},
        object_id=document.object_id,
    )


def _document_type_read(record: DocumentType) -> DocumentTypeRead:
    return DocumentTypeRead(
        id=record.id,
        code=record.code,
        name=record.name,
        description=record.description,
        required=record.required,
        employee_visible=record.employee_visible,
        sensitivity=record.sensitivity,
        expiry_mode=record.expiry_mode,
        allowed_mime_types=record.allowed_mime_types,
        allowed_extensions=record.allowed_extensions,
        max_size_bytes=record.max_size_bytes,
        version=record.version,
        archived_at=record.archived_at,
    )


def _document_read(
    document: EmployeeDocument,
    document_type: DocumentType,
) -> EmployeeDocumentRead:
    return EmployeeDocumentRead(
        id=document.id,
        employee_id=document.employee_id,
        document_type_id=document.document_type_id,
        document_type_code=document_type.code,
        document_type_name=document_type.name,
        display_filename=document.display_filename,
        content_type=document.declared_content_type,
        size_bytes=document.size_bytes,
        issued_on=document.issued_on,
        expires_on=document.expires_on,
        employee_visible=document.employee_visible,
        processing_state=document.processing_state,
        version=document.version,
        archived_at=document.archived_at,
        created_at=document.created_at,
        downloadable=(
            document.processing_state == DocumentProcessingState.AVAILABLE.value
            and document.archived_at is None
        ),
    )


def _type_policy_values(
    record: DocumentType,
    payload: DocumentTypeUpdate,
) -> dict[str, object]:
    values: dict[str, object] = {}
    for field_name in (
        "name",
        "description",
        "required",
        "employee_visible",
        "sensitivity",
        "expiry_mode",
        "allowed_mime_types",
        "allowed_extensions",
        "max_size_bytes",
    ):
        if field_name not in payload.model_fields_set:
            values[field_name] = getattr(record, field_name)
            continue
        value = getattr(payload, field_name)
        if field_name in {"sensitivity", "expiry_mode"}:
            value = value.value
        elif field_name in {"allowed_mime_types", "allowed_extensions"}:
            value = sorted(item.value for item in value)
        values[field_name] = value
    return values


def _safe_scanner_value(value: str | None, maximum_length: int) -> str | None:
    if value is None:
        return None
    normalized = value.strip().lower()
    if len(normalized) > maximum_length or fullmatch(r"[a-z0-9][a-z0-9_.-]*", normalized) is None:
        return None
    return normalized


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


__all__ = [
    "DocumentConflictError",
    "DocumentNotFoundError",
    "DocumentStorageUnavailableError",
    "DocumentTypeNotFoundError",
    "DocumentValidationError",
    "DocumentVersionConflictError",
    "EmployeeDocumentQueryService",
    "EmployeeDocumentService",
    "sanitize_display_filename",
    "summarize_checklist",
]
