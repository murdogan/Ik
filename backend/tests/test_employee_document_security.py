"""Critical employee-document upload, scan, and object-boundary regressions."""

from __future__ import annotations

import asyncio
import hashlib
from collections.abc import AsyncIterator, Mapping
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from uuid import UUID

import pytest
from app.core.config import Settings
from app.db.base import Base
from app.models.employee import Employee, EmployeeStatus
from app.models.employee_document import (
    DocumentExpiryMode,
    DocumentProcessingState,
    DocumentSensitivity,
    DocumentType,
    EmployeeDocument,
)
from app.models.identity import (
    Identity,
    IdentityStatus,
    MembershipStatus,
    TenantMembership,
)
from app.models.tenant import Tenant, TenantStatus
from app.models.user import User, UserStatus
from app.modules.documents.infrastructure.runtime import create_document_runtime
from app.modules.documents.infrastructure.scanning import (
    MalwareScanError,
    MalwareScanOutcome,
    MalwareScanVerdict,
)
from app.platform.audit import AuditEventDraft
from app.platform.request_context import AuthenticationStrength, RequestContext
from app.platform.storage import (
    DownloadedObject,
    ObjectAlreadyExistsError,
    ObjectHead,
    ObjectNotFoundError,
    PresignedRequest,
    UploadedObject,
)
from app.platform.tenancy import TenantContext
from app.schemas.employee_document import (
    AllowedDocumentMimeType,
    EmployeeDocumentUploadInitiate,
)
from app.services.employee_document_service import (
    DocumentConflictError,
    DocumentNotFoundError,
    EmployeeDocumentService,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool

TENANT_A_ID = UUID("11aa0000-0000-4000-8000-000000000001")
TENANT_B_ID = UUID("22bb0000-0000-4000-8000-000000000002")
EMPLOYEE_A_ID = UUID("aa000000-0000-4000-8000-000000000001")
EMPLOYEE_A_OTHER_ID = UUID("aa000000-0000-4000-8000-000000000002")
EMPLOYEE_B_ID = UUID("bb000000-0000-4000-8000-000000000001")
IDENTITY_A_ID = UUID("1d000000-0000-4000-8000-000000000001")
IDENTITY_B_ID = UUID("1d000000-0000-4000-8000-000000000002")
USER_A_ID = UUID("a5000000-0000-4000-8000-000000000001")
USER_B_ID = UUID("b5000000-0000-4000-8000-000000000001")
MEMBERSHIP_A_ID = UUID("a6000000-0000-4000-8000-000000000001")
MEMBERSHIP_B_ID = UUID("b6000000-0000-4000-8000-000000000001")
DOCUMENT_TYPE_A_ID = UUID("da000000-0000-4000-8000-000000000001")
DOCUMENT_TYPE_B_ID = UUID("db000000-0000-4000-8000-000000000001")
PDF_BYTES = b"%PDF-1.7\nsynthetic phase 11 document\n"


@dataclass(frozen=True, slots=True)
class _StoredObject:
    body: bytes
    content_type: str
    metadata: dict[str, str]


@dataclass(slots=True)
class _MemoryStorage:
    objects: dict[str, _StoredObject] = field(default_factory=dict)
    upload_requests: list[dict[str, object]] = field(default_factory=list)
    download_requests: list[dict[str, object]] = field(default_factory=list)

    async def initialize(self) -> None:
        return None

    async def close(self) -> None:
        return None

    async def presign_upload(
        self,
        *,
        key: str,
        content_type: str,
        content_length: int,
        metadata: Mapping[str, str],
        ttl_seconds: int,
    ) -> PresignedRequest:
        self.upload_requests.append(
            {
                "key": key,
                "content_type": content_type,
                "content_length": content_length,
                "metadata": dict(metadata),
                "ttl_seconds": ttl_seconds,
            }
        )
        return PresignedRequest(
            method="PUT",
            url="https://upload.example.invalid/opaque-grant",
            headers={
                "Content-Type": content_type,
                **{f"x-meta-{name}": value for name, value in metadata.items()},
            },
            expires_at=datetime.now(UTC) + timedelta(seconds=ttl_seconds),
        )

    async def head(self, key: str) -> ObjectHead:
        stored = self.objects.get(key)
        if stored is None:
            raise ObjectNotFoundError
        return ObjectHead(
            key=key,
            size_bytes=len(stored.body),
            content_type=stored.content_type,
            metadata=stored.metadata,
        )

    async def download_to_path(
        self,
        *,
        key: str,
        destination: Path,
        maximum_bytes: int,
    ) -> DownloadedObject:
        stored = self.objects.get(key)
        if stored is None:
            raise ObjectNotFoundError
        if len(stored.body) > maximum_bytes:
            raise AssertionError("test object exceeded the bounded download")
        destination.write_bytes(stored.body)
        return DownloadedObject(
            size_bytes=len(stored.body),
            sha256=hashlib.sha256(stored.body).hexdigest(),
            magic_prefix=stored.body[:32],
        )

    async def upload_from_path(
        self,
        *,
        key: str,
        source: Path,
        content_type: str,
        metadata: Mapping[str, str],
        maximum_bytes: int,
    ) -> UploadedObject:
        body = source.read_bytes()
        if len(body) > maximum_bytes:
            raise AssertionError("test object exceeded the bounded upload")
        if key in self.objects:
            raise ObjectAlreadyExistsError
        self.objects[key] = _StoredObject(body, content_type, dict(metadata))
        return UploadedObject(size_bytes=len(body), sha256=hashlib.sha256(body).hexdigest())

    async def copy_if_absent(
        self,
        *,
        source_key: str,
        destination_key: str,
        content_type: str,
        metadata: Mapping[str, str],
    ) -> None:
        if destination_key in self.objects:
            raise ObjectAlreadyExistsError
        source = self.objects.get(source_key)
        if source is None:
            raise ObjectNotFoundError
        self.objects[destination_key] = _StoredObject(
            source.body,
            content_type,
            dict(metadata),
        )

    async def delete(self, key: str) -> None:
        self.objects.pop(key, None)

    async def presign_download(
        self,
        *,
        key: str,
        download_name: str,
        ttl_seconds: int,
    ) -> PresignedRequest:
        if key not in self.objects:
            raise ObjectNotFoundError
        self.download_requests.append(
            {
                "key": key,
                "download_name": download_name,
                "ttl_seconds": ttl_seconds,
            }
        )
        return PresignedRequest(
            method="GET",
            url="https://download.example.invalid/opaque-grant",
            headers={},
            expires_at=datetime.now(UTC) + timedelta(seconds=ttl_seconds),
        )

    def stage_latest_upload(self, body: bytes = PDF_BYTES) -> str:
        request = self.upload_requests[-1]
        key = str(request["key"])
        self.objects[key] = _StoredObject(
            body=body,
            content_type=str(request["content_type"]),
            metadata=dict(request["metadata"]),
        )
        return key


@dataclass(slots=True)
class _CapturingAuditRecorder:
    events: list[AuditEventDraft] = field(default_factory=list)

    async def record(self, event: AuditEventDraft, /) -> None:
        self.events.append(event)


@dataclass(slots=True)
class _FixedScanner:
    outcome: MalwareScanOutcome | None = None
    error_code: str | None = None
    entered: asyncio.Event | None = None
    release: asyncio.Event | None = None

    async def scan(self, path: Path) -> MalwareScanOutcome:
        assert path.read_bytes() == PDF_BYTES
        if self.entered is not None:
            self.entered.set()
        if self.release is not None:
            await self.release.wait()
        if self.error_code is not None:
            raise MalwareScanError(self.error_code)
        if self.outcome is None:
            raise AssertionError("test scanner requires an outcome or error")
        return self.outcome


@dataclass(slots=True)
class _DocumentHarness:
    engine: AsyncEngine
    sessions: async_sessionmaker[AsyncSession]
    storage: _MemoryStorage
    audit: _CapturingAuditRecorder
    settings: Settings

    def service(self, scanner: _FixedScanner) -> EmployeeDocumentService:
        return EmployeeDocumentService(
            session_factory=self.sessions,
            storage=self.storage,
            scanner=scanner,
            settings=self.settings,
            audit_recorder_factory=lambda _session: self.audit,
        )

    async def document(self, document_id: UUID) -> EmployeeDocument:
        async with self.sessions() as session:
            record = await session.scalar(
                select(EmployeeDocument).where(EmployeeDocument.id == document_id)
            )
        assert record is not None
        return record


@pytest.fixture
async def document_harness() -> AsyncIterator[_DocumentHarness]:
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        use_insertmanyvalues=False,
    )
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    async with sessions() as session:
        session.add_all(_seed_records())
        await session.commit()

    harness = _DocumentHarness(
        engine=engine,
        sessions=sessions,
        storage=_MemoryStorage(),
        audit=_CapturingAuditRecorder(),
        settings=Settings(
            _env_file=None,
            environment="test",
            document_scanner_backend="clamav",
            clamav_host="scanner.example.invalid",
        ),
    )
    try:
        yield harness
    finally:
        await engine.dispose()


def test_protected_runtime_rejects_fail_open_document_backends() -> None:
    settings = Settings(
        _env_file=None,
        environment="staging",
        frontend_base_url="https://frontend.example.test",
        release_commit_sha="a" * 40,
        release_build_timestamp=datetime(2026, 7, 27, tzinfo=UTC),
        document_storage_backend="disabled",
        document_scanner_backend="local_clean",
    )

    with pytest.raises(ValueError, match="require S3 employee document storage"):
        create_document_runtime(settings)


async def test_upload_grant_and_finalize_are_bound_to_tenant_employee_and_intent(
    document_harness: _DocumentHarness,
) -> None:
    service = document_harness.service(
        _FixedScanner(
            outcome=MalwareScanOutcome(
                verdict=MalwareScanVerdict.CLEAN,
                provider="clamav",
                version="synthetic",
            )
        )
    )
    grant = await _initiate(service, _context_a())
    upload_request = document_harness.storage.upload_requests[-1]
    key = str(upload_request["key"])
    metadata = dict(upload_request["metadata"])

    assert isinstance(grant.document.created_at, datetime)
    assert key.startswith(f"tenants/{TENANT_A_ID}/employees/{EMPLOYEE_A_ID}/documents/")
    assert f"/{grant.document.id}/" in key
    assert key.endswith(f".upload-{grant.upload_intent_id}")
    assert metadata == {
        "tenant-id": str(TENANT_A_ID),
        "employee-id": str(EMPLOYEE_A_ID),
        "document-id": str(grant.document.id),
        "object-id": key.rsplit("/", 1)[1].split(".upload-", 1)[0],
        "intent-id": str(grant.upload_intent_id),
        "expected-size": str(len(PDF_BYTES)),
        "expected-type": AllowedDocumentMimeType.PDF.value,
    }
    assert "object_key" not in grant.model_dump()

    document_harness.storage.stage_latest_upload()
    with pytest.raises(DocumentNotFoundError):
        await service.finalize_upload(
            tenant_id=TENANT_B_ID,
            employee_id=EMPLOYEE_A_ID,
            document_id=grant.document.id,
            upload_intent_id=grant.upload_intent_id,
            request_context=_context_b(),
        )
    with pytest.raises(DocumentNotFoundError):
        await service.finalize_upload(
            tenant_id=TENANT_A_ID,
            employee_id=EMPLOYEE_A_OTHER_ID,
            document_id=grant.document.id,
            upload_intent_id=grant.upload_intent_id,
            request_context=_context_a(),
        )
    assert (await document_harness.document(grant.document.id)).processing_state == (
        DocumentProcessingState.PENDING_UPLOAD.value
    )


async def test_pending_scan_cannot_issue_download_grant(
    document_harness: _DocumentHarness,
) -> None:
    entered = asyncio.Event()
    release = asyncio.Event()
    service = document_harness.service(
        _FixedScanner(
            outcome=MalwareScanOutcome(
                verdict=MalwareScanVerdict.CLEAN,
                provider="clamav",
                version="synthetic",
            ),
            entered=entered,
            release=release,
        )
    )
    grant = await _initiate_and_stage(document_harness, service)

    finalizing = asyncio.create_task(
        service.finalize_upload(
            tenant_id=TENANT_A_ID,
            employee_id=EMPLOYEE_A_ID,
            document_id=grant.document.id,
            upload_intent_id=grant.upload_intent_id,
            request_context=_context_a(),
        )
    )
    await asyncio.wait_for(entered.wait(), timeout=2)
    persisted = await document_harness.document(grant.document.id)
    assert persisted.processing_state == DocumentProcessingState.PENDING_SCAN.value
    assert persisted.scan_result is None

    with pytest.raises(DocumentConflictError, match="not available for download"):
        await service.issue_hr_download(
            tenant_id=TENANT_A_ID,
            employee_id=EMPLOYEE_A_ID,
            document_id=grant.document.id,
            request_context=_context_a(),
        )
    assert document_harness.storage.download_requests == []

    release.set()
    finalized = await asyncio.wait_for(finalizing, timeout=2)
    assert finalized.processing_state is DocumentProcessingState.AVAILABLE
    assert finalized.downloadable is True


@pytest.mark.parametrize(
    ("scanner", "expected_state", "expected_scan_result"),
    [
        pytest.param(
            _FixedScanner(
                outcome=MalwareScanOutcome(
                    verdict=MalwareScanVerdict.INFECTED,
                    provider="clamav",
                    version="synthetic",
                )
            ),
            DocumentProcessingState.INFECTED,
            "infected",
            id="infected",
        ),
        pytest.param(
            _FixedScanner(error_code="scanner_unavailable"),
            DocumentProcessingState.SCAN_ERROR,
            "error",
            id="scanner-unavailable",
        ),
    ],
)
async def test_infected_or_scanner_error_content_stays_fail_closed(
    document_harness: _DocumentHarness,
    scanner: _FixedScanner,
    expected_state: DocumentProcessingState,
    expected_scan_result: str,
) -> None:
    service = document_harness.service(scanner)
    grant = await _initiate_and_stage(document_harness, service)

    finalized = await service.finalize_upload(
        tenant_id=TENANT_A_ID,
        employee_id=EMPLOYEE_A_ID,
        document_id=grant.document.id,
        upload_intent_id=grant.upload_intent_id,
        request_context=_context_a(),
    )

    assert finalized.processing_state is expected_state
    assert finalized.downloadable is False
    persisted = await document_harness.document(grant.document.id)
    assert persisted.processing_state == expected_state.value
    assert persisted.scan_result == expected_scan_result
    with pytest.raises(DocumentConflictError, match="not available for download"):
        await service.issue_hr_download(
            tenant_id=TENANT_A_ID,
            employee_id=EMPLOYEE_A_ID,
            document_id=grant.document.id,
            request_context=_context_a(),
        )
    assert document_harness.storage.download_requests == []


async def test_download_is_bola_safe_and_grant_and_audit_do_not_expose_object_key(
    document_harness: _DocumentHarness,
) -> None:
    service = document_harness.service(
        _FixedScanner(
            outcome=MalwareScanOutcome(
                verdict=MalwareScanVerdict.CLEAN,
                provider="clamav",
                version="synthetic",
            )
        )
    )
    upload_grant = await _initiate_and_stage(document_harness, service)
    finalized = await service.finalize_upload(
        tenant_id=TENANT_A_ID,
        employee_id=EMPLOYEE_A_ID,
        document_id=upload_grant.document.id,
        upload_intent_id=upload_grant.upload_intent_id,
        request_context=_context_a(),
    )
    document = await document_harness.document(finalized.id)

    with pytest.raises(DocumentNotFoundError):
        await service.issue_hr_download(
            tenant_id=TENANT_B_ID,
            employee_id=EMPLOYEE_A_ID,
            document_id=document.id,
            request_context=_context_b(),
        )
    with pytest.raises(DocumentNotFoundError):
        await service.issue_hr_download(
            tenant_id=TENANT_A_ID,
            employee_id=EMPLOYEE_A_OTHER_ID,
            document_id=document.id,
            request_context=_context_a(),
        )
    assert document_harness.storage.download_requests == []

    download_grant = await service.issue_hr_download(
        tenant_id=TENANT_A_ID,
        employee_id=EMPLOYEE_A_ID,
        document_id=document.id,
        request_context=_context_a(),
    )
    assert set(download_grant.model_dump()) == {"document_id", "method", "url", "expires_at"}
    assert document.object_key not in download_grant.model_dump_json()
    assert document_harness.storage.download_requests == [
        {
            "key": document.object_key,
            "download_name": "employee-document.pdf",
            "ttl_seconds": document_harness.settings.document_download_ttl_seconds,
        }
    ]
    audit_payloads = [
        f"{event.action}|{event.changed_fields}|{dict(event.metadata)}"
        for event in document_harness.audit.events
    ]
    assert all(document.object_key not in payload for payload in audit_payloads)
    assert all("https://" not in payload for payload in audit_payloads)


async def _initiate(
    service: EmployeeDocumentService,
    request_context: RequestContext,
):
    return await service.initiate_upload(
        tenant_id=TENANT_A_ID,
        employee_id=EMPLOYEE_A_ID,
        payload=EmployeeDocumentUploadInitiate(
            document_type_id=DOCUMENT_TYPE_A_ID,
            display_filename="phase-11-proof.pdf",
            declared_content_type=AllowedDocumentMimeType.PDF,
            size_bytes=len(PDF_BYTES),
            employee_visible=True,
        ),
        request_context=request_context,
    )


async def _initiate_and_stage(
    harness: _DocumentHarness,
    service: EmployeeDocumentService,
):
    grant = await _initiate(service, _context_a())
    harness.storage.stage_latest_upload()
    return grant


def _context_a() -> RequestContext:
    return _request_context(
        tenant_id=TENANT_A_ID,
        tenant_slug="tenant-a",
        user_id=USER_A_ID,
        membership_id=MEMBERSHIP_A_ID,
    )


def _context_b() -> RequestContext:
    return _request_context(
        tenant_id=TENANT_B_ID,
        tenant_slug="tenant-b",
        user_id=USER_B_ID,
        membership_id=MEMBERSHIP_B_ID,
    )


def _request_context(
    *,
    tenant_id: UUID,
    tenant_slug: str,
    user_id: UUID,
    membership_id: UUID,
) -> RequestContext:
    return RequestContext(
        request_id=f"p11-doc-{tenant_slug}",
        trace_id="1234567890abcdef1234567890abcdef",
        tenant=TenantContext(tenant_id=tenant_id, slug=tenant_slug),
        actor_id=user_id,
        membership_id=membership_id,
        authentication_strength=AuthenticationStrength.SINGLE_FACTOR,
    )


def _seed_records() -> list[object]:
    return [
        Tenant(
            id=TENANT_A_ID,
            slug="tenant-a",
            name="Phase 11 Tenant A",
            status=TenantStatus.ACTIVE.value,
            plan_code="core",
            data_region="tr-1",
            locale="tr-TR",
            timezone="Europe/Istanbul",
        ),
        Tenant(
            id=TENANT_B_ID,
            slug="tenant-b",
            name="Phase 11 Tenant B",
            status=TenantStatus.ACTIVE.value,
            plan_code="core",
            data_region="tr-1",
            locale="tr-TR",
            timezone="Europe/Istanbul",
        ),
        Identity(
            id=IDENTITY_A_ID,
            email="document-a@example.test",
            status=IdentityStatus.ACTIVE.value,
            password_hash="synthetic-hash",
        ),
        Identity(
            id=IDENTITY_B_ID,
            email="document-b@example.test",
            status=IdentityStatus.ACTIVE.value,
            password_hash="synthetic-hash",
        ),
        User(
            id=USER_A_ID,
            tenant_id=TENANT_A_ID,
            email="document-a@example.test",
            full_name="Document Actor A",
            status=UserStatus.ACTIVE.value,
            password_hash="synthetic-hash",
        ),
        User(
            id=USER_B_ID,
            tenant_id=TENANT_B_ID,
            email="document-b@example.test",
            full_name="Document Actor B",
            status=UserStatus.ACTIVE.value,
            password_hash="synthetic-hash",
        ),
        TenantMembership(
            id=MEMBERSHIP_A_ID,
            tenant_id=TENANT_A_ID,
            identity_id=IDENTITY_A_ID,
            legacy_user_id=USER_A_ID,
            full_name="Document Actor A",
            status=MembershipStatus.ACTIVE.value,
        ),
        TenantMembership(
            id=MEMBERSHIP_B_ID,
            tenant_id=TENANT_B_ID,
            identity_id=IDENTITY_B_ID,
            legacy_user_id=USER_B_ID,
            full_name="Document Actor B",
            status=MembershipStatus.ACTIVE.value,
        ),
        Employee(
            id=EMPLOYEE_A_ID,
            tenant_id=TENANT_A_ID,
            employee_number="DOC-A-001",
            first_name="Ada",
            last_name="Document",
            status=EmployeeStatus.ACTIVE.value,
            employment_start_date=date(2026, 1, 1),
        ),
        Employee(
            id=EMPLOYEE_A_OTHER_ID,
            tenant_id=TENANT_A_ID,
            employee_number="DOC-A-002",
            first_name="Other",
            last_name="Employee",
            status=EmployeeStatus.ACTIVE.value,
            employment_start_date=date(2026, 1, 1),
        ),
        Employee(
            id=EMPLOYEE_B_ID,
            tenant_id=TENANT_B_ID,
            employee_number="DOC-B-001",
            first_name="Grace",
            last_name="Document",
            status=EmployeeStatus.ACTIVE.value,
            employment_start_date=date(2026, 1, 1),
        ),
        DocumentType(
            id=DOCUMENT_TYPE_A_ID,
            tenant_id=TENANT_A_ID,
            code="identity",
            name="Identity",
            description=None,
            required=True,
            employee_visible=True,
            sensitivity=DocumentSensitivity.SENSITIVE.value,
            expiry_mode=DocumentExpiryMode.OPTIONAL.value,
            allowed_mime_types=[AllowedDocumentMimeType.PDF.value],
            allowed_extensions=["pdf"],
            max_size_bytes=1024 * 1024,
            version=1,
        ),
        DocumentType(
            id=DOCUMENT_TYPE_B_ID,
            tenant_id=TENANT_B_ID,
            code="identity",
            name="Identity",
            description=None,
            required=True,
            employee_visible=True,
            sensitivity=DocumentSensitivity.SENSITIVE.value,
            expiry_mode=DocumentExpiryMode.OPTIONAL.value,
            allowed_mime_types=[AllowedDocumentMimeType.PDF.value],
            allowed_extensions=["pdf"],
            max_size_bytes=1024 * 1024,
            version=1,
        ),
    ]
