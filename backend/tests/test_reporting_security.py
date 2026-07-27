"""Critical report, private-export, and employee-import security regressions."""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from hashlib import sha256
from uuid import UUID

import pytest
from app.core.config import Settings
from app.db.base import Base
from app.models.command_idempotency import CommandIdempotency
from app.models.department import Department, DepartmentStatus
from app.models.employee import Employee, EmployeeStatus
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
from app.models.reporting import ExportJobStatus, ReportExportJob, ReportScope, ReportType
from app.models.tenant import Tenant, TenantStatus
from app.models.user import User, UserStatus
from app.platform.request_context import AuthenticationStrength, RequestContext
from app.platform.storage import PresignedRequest
from app.platform.tenancy import TenantContext
from app.schemas.reporting import EmployeeReportField, EmployeeReportFilters
from app.services.employee_import_service import (
    EmployeeImportService,
    canonical_import_row,
)
from app.services.export_job_service import ExportJobService
from app.services.report_service import ReportService
from app.services.reporting_access import (
    REPORT_READ_TEAM_PERMISSION,
    REPORT_READ_TENANT_PERMISSION,
    REPORT_WORK_EMAIL_PERMISSION,
    ReportingAccessDeniedError,
    ReportingNotFoundError,
    allowed_report_fields,
    enforce_requested_fields,
    reduce_requested_fields,
    resolve_report_authorization,
)
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool

TENANT_A_ID = UUID("11aa0000-0000-4000-8000-000000000001")
TENANT_B_ID = UUID("22bb0000-0000-4000-8000-000000000002")
MANAGER_A_ID = UUID("aa100000-0000-4000-8000-000000000001")
HR_A_ID = UUID("aa200000-0000-4000-8000-000000000002")
OTHER_A_ID = UUID("aa300000-0000-4000-8000-000000000003")
HR_B_ID = UUID("bb200000-0000-4000-8000-000000000002")
TEAM_EMPLOYEE_ID = UUID("a0100000-0000-4000-8000-000000000001")
OUTSIDE_EMPLOYEE_ID = UUID("a0200000-0000-4000-8000-000000000002")
TENANT_B_EMPLOYEE_ID = UUID("b0100000-0000-4000-8000-000000000001")
LEGAL_ENTITY_ID = UUID("ae100000-0000-4000-8000-000000000001")
BRANCH_ID = UUID("ab100000-0000-4000-8000-000000000001")
DEPARTMENT_ID = UUID("ad100000-0000-4000-8000-000000000001")
POSITION_ID = UUID("ac100000-0000-4000-8000-000000000001")
TEAM_ASSIGNMENT_ID = UUID("a1100000-0000-4000-8000-000000000001")
OUTSIDE_ASSIGNMENT_ID = UUID("a1200000-0000-4000-8000-000000000002")
EXPORT_JOB_ID = UUID("e1000000-0000-4000-8000-000000000001")
PREVIEW_IMPORT_ID = UUID("1a100000-0000-4000-8000-000000000001")
INVALID_IMPORT_ID = UUID("1a200000-0000-4000-8000-000000000002")
VALID_IMPORT_ID = UUID("1a300000-0000-4000-8000-000000000003")
FIXED_NOW = datetime(2026, 7, 27, 12, 0, tzinfo=UTC)


@dataclass(slots=True)
class _PrivateStorage:
    download_calls: list[dict[str, object]] = field(default_factory=list)

    async def presign_download(
        self,
        *,
        key: str,
        download_name: str,
        ttl_seconds: int,
    ) -> PresignedRequest:
        self.download_calls.append(
            {
                "key": key,
                "download_name": download_name,
                "ttl_seconds": ttl_seconds,
            }
        )
        return PresignedRequest(
            method="GET",
            url="https://download.example.invalid/grants/opaque?X-Amz-Signature=synthetic",
            headers={},
            expires_at=datetime.now(UTC) + timedelta(seconds=ttl_seconds),
        )


@dataclass(slots=True)
class _ReportingHarness:
    engine: AsyncEngine
    sessions: async_sessionmaker[AsyncSession]
    storage: _PrivateStorage

    def export_service(self) -> ExportJobService:
        return ExportJobService(
            session_factory=self.sessions,
            storage=self.storage,
            settings=Settings(_env_file=None, environment="test"),
        )

    def import_service(self) -> EmployeeImportService:
        return EmployeeImportService(
            session_factory=self.sessions,
            storage=self.storage,
        )


@pytest.fixture
async def reporting_harness() -> AsyncIterator[_ReportingHarness]:
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
        session.add_all(_base_records())
        await session.commit()

    try:
        yield _ReportingHarness(
            engine=engine,
            sessions=sessions,
            storage=_PrivateStorage(),
        )
    finally:
        await engine.dispose()


async def test_report_scope_is_tenant_safe_and_manager_bounded_and_fields_fail_closed(
    reporting_harness: _ReportingHarness,
) -> None:
    manager_permissions = (REPORT_READ_TEAM_PERMISSION,)
    manager_fields = allowed_report_fields(ReportType.EMPLOYEES, manager_permissions)
    sensitive_fields = {
        "national_id",
        "birth_date",
        "personal_email",
        "personal_phone",
        "bank_account",
    }
    assert EmployeeReportField.WORK_EMAIL.value not in manager_fields
    assert not sensitive_fields.intersection(manager_fields)
    with pytest.raises(ReportingAccessDeniedError):
        enforce_requested_fields(
            report_type=ReportType.EMPLOYEES,
            requested_fields=["employee_number", "work_email"],
            permissions=manager_permissions,
        )
    assert reduce_requested_fields(
        report_type=ReportType.EMPLOYEES,
        request_fields=("employee_number", "work_email"),
        permissions=manager_permissions,
    ) == ("employee_number",)

    async with reporting_harness.sessions() as session:
        service = ReportService(session=session, today=date(2026, 7, 27))
        manager_page = await service.employee_report(
            tenant_id=TENANT_A_ID,
            authorization=resolve_report_authorization(
                permissions=manager_permissions,
                actor_id=MANAGER_A_ID,
                require_export=False,
            ),
            fields=manager_fields,
            filters=EmployeeReportFilters(),
            limit=20,
            cursor=None,
        )
        hr_permissions = (REPORT_READ_TENANT_PERMISSION, REPORT_WORK_EMAIL_PERMISSION)
        hr_page = await service.employee_report(
            tenant_id=TENANT_A_ID,
            authorization=resolve_report_authorization(
                permissions=hr_permissions,
                actor_id=HR_A_ID,
                require_export=False,
            ),
            fields=allowed_report_fields(ReportType.EMPLOYEES, hr_permissions),
            filters=EmployeeReportFilters(),
            limit=20,
            cursor=None,
        )

    assert [row.values["employee_number"] for row in manager_page.items] == ["A-TEAM-001"]
    assert all("work_email" not in row.values for row in manager_page.items)
    assert {row.values["employee_number"] for row in hr_page.items} == {
        "A-OUTSIDE-002",
        "A-TEAM-001",
    }
    assert {row.values["work_email"] for row in hr_page.items} == {
        "outside-a@example.test",
        "team-a@example.test",
    }


async def test_private_export_download_is_owner_and_tenant_bound_without_metadata_leak(
    reporting_harness: _ReportingHarness,
) -> None:
    object_key = f"{TENANT_A_ID}/{EXPORT_JOB_ID}/private-report.csv"
    async with reporting_harness.sessions() as session:
        session.add(_succeeded_export(object_key))
        await session.commit()

    service = reporting_harness.export_service()
    with pytest.raises(ReportingNotFoundError):
        await service.get_job(request_context=_context_b(), job_id=EXPORT_JOB_ID)
    with pytest.raises(ReportingNotFoundError):
        await service.get_job(request_context=_context_other_a(), job_id=EXPORT_JOB_ID)
    with pytest.raises(ReportingNotFoundError):
        await service.create_download_intent(
            request_context=_context_b(),
            permissions=_tenant_export_permissions(),
            job_id=EXPORT_JOB_ID,
        )
    assert reporting_harness.storage.download_calls == []

    job = await service.get_job(request_context=_context_hr_a(), job_id=EXPORT_JOB_ID)
    grant = await service.create_download_intent(
        request_context=_context_hr_a(),
        permissions=_tenant_export_permissions(),
        job_id=EXPORT_JOB_ID,
    )

    serialized_job = job.model_dump_json()
    serialized_grant = grant.model_dump_json()
    assert object_key not in serialized_job
    assert object_key not in serialized_grant
    assert "artifact_object_key" not in serialized_job
    assert "bearer" not in serialized_grant.casefold()
    assert "cookie" not in serialized_grant.casefold()
    assert set(grant.model_dump()) == {"export_job_id", "method", "url", "expires_at"}
    assert reporting_harness.storage.download_calls == [
        {
            "key": object_key,
            "download_name": f"report-{EXPORT_JOB_ID}.csv",
            "ttl_seconds": 300,
        }
    ]


async def test_import_preview_is_owner_tenant_bound_and_non_mutating(
    reporting_harness: _ReportingHarness,
) -> None:
    object_key = f"{TENANT_A_ID}/{PREVIEW_IMPORT_ID}/private-source.csv"
    async with reporting_harness.sessions() as session:
        session.add_all(
            [
                _preview_import(object_key),
                EmployeeImportIssue(
                    id=UUID("1f100000-0000-4000-8000-000000000001"),
                    tenant_id=TENANT_A_ID,
                    import_id=PREVIEW_IMPORT_ID,
                    row_number=2,
                    severity="error",
                    code="invalid_email",
                    field="work_email",
                    message="Work email format is invalid.",
                ),
            ]
        )
        before = await session.scalar(select(func.count()).select_from(Employee))
        await session.commit()

    service = reporting_harness.import_service()
    with pytest.raises(ReportingNotFoundError):
        await service.get_import(
            request_context=_context_b(),
            import_id=PREVIEW_IMPORT_ID,
            issue_limit=20,
            issue_cursor=None,
        )
    with pytest.raises(ReportingNotFoundError):
        await service.get_import(
            request_context=_context_other_a(),
            import_id=PREVIEW_IMPORT_ID,
            issue_limit=20,
            issue_cursor=None,
        )
    preview = await service.get_import(
        request_context=_context_hr_a(),
        import_id=PREVIEW_IMPORT_ID,
        issue_limit=20,
        issue_cursor=None,
    )

    async with reporting_harness.sessions() as session:
        after = await session.scalar(select(func.count()).select_from(Employee))
    assert after == before
    assert preview.status is EmployeeImportStatus.INVALID
    assert [issue.code for issue in preview.issues] == ["invalid_email"]
    assert object_key not in preview.model_dump_json()
    assert "object_key" not in preview.model_dump_json()


async def test_import_commit_rolls_back_every_row_when_staged_data_is_invalid(
    reporting_harness: _ReportingHarness,
) -> None:
    rows = [
        _import_row(
            row_id=UUID("1b200000-0000-4000-8000-000000000002"),
            import_id=INVALID_IMPORT_ID,
            row_number=2,
            employee_number="IMPORT-ROLLBACK-001",
            first_name="Valid",
        ),
        _import_row(
            row_id=UUID("1b200000-0000-4000-8000-000000000003"),
            import_id=INVALID_IMPORT_ID,
            row_number=3,
            employee_number="IMPORT-ROLLBACK-002",
            first_name="",
        ),
    ]
    async with reporting_harness.sessions() as session:
        session.add_all([_ready_import(INVALID_IMPORT_ID, rows), *rows])
        await session.commit()

    with pytest.raises(ValidationError):
        await reporting_harness.import_service().commit_import(
            request_context=_context_hr_a(),
            import_id=INVALID_IMPORT_ID,
            idempotency_key="p11-invalid-import-rollback",
        )

    async with reporting_harness.sessions() as session:
        imported_count = await session.scalar(
            select(func.count())
            .select_from(Employee)
            .where(Employee.employee_number.like("IMPORT-ROLLBACK-%"))
        )
        receipt_count = await session.scalar(
            select(func.count())
            .select_from(CommandIdempotency)
            .where(
                CommandIdempotency.tenant_id == TENANT_A_ID,
                CommandIdempotency.idempotency_key == "p11-invalid-import-rollback",
            )
        )
        persisted = await session.get(EmployeeImport, INVALID_IMPORT_ID)
    assert imported_count == 0
    assert receipt_count == 0
    assert persisted is not None
    assert persisted.status == EmployeeImportStatus.READY.value
    assert persisted.committed_count == 0
    assert persisted.committed_at is None


async def test_import_commit_replays_idempotently_without_duplicate_employee(
    reporting_harness: _ReportingHarness,
) -> None:
    rows = [
        _import_row(
            row_id=UUID("1b300000-0000-4000-8000-000000000002"),
            import_id=VALID_IMPORT_ID,
            row_number=2,
            employee_number="IMPORT-IDEMPOTENT-001",
            first_name="Idempotent",
        )
    ]
    async with reporting_harness.sessions() as session:
        session.add_all([_ready_import(VALID_IMPORT_ID, rows), *rows])
        await session.commit()

    service = reporting_harness.import_service()
    with pytest.raises(ReportingNotFoundError):
        await service.commit_import(
            request_context=_context_b(),
            import_id=VALID_IMPORT_ID,
            idempotency_key="p11-cross-tenant-import-denied",
        )
    first = await service.commit_import(
        request_context=_context_hr_a(),
        import_id=VALID_IMPORT_ID,
        idempotency_key="p11-valid-import-idempotency",
    )
    replay = await service.commit_import(
        request_context=_context_hr_a(),
        import_id=VALID_IMPORT_ID,
        idempotency_key="p11-valid-import-idempotency",
    )

    async with reporting_harness.sessions() as session:
        imported_count = await session.scalar(
            select(func.count())
            .select_from(Employee)
            .where(Employee.employee_number == "IMPORT-IDEMPOTENT-001")
        )
        receipt_count = await session.scalar(
            select(func.count())
            .select_from(CommandIdempotency)
            .where(
                CommandIdempotency.tenant_id == TENANT_A_ID,
                CommandIdempotency.idempotency_key == "p11-valid-import-idempotency",
            )
        )
    assert replay == first
    assert first.committed_count == 1
    assert imported_count == 1
    assert receipt_count == 1


def _base_records() -> list[object]:
    return [
        Tenant(
            id=TENANT_A_ID,
            slug="reporting-a",
            name="Reporting Tenant A",
            status=TenantStatus.ACTIVE.value,
            plan_code="core",
            data_region="tr-1",
            locale="tr-TR",
            timezone="Europe/Istanbul",
        ),
        Tenant(
            id=TENANT_B_ID,
            slug="reporting-b",
            name="Reporting Tenant B",
            status=TenantStatus.ACTIVE.value,
            plan_code="core",
            data_region="tr-1",
            locale="tr-TR",
            timezone="Europe/Istanbul",
        ),
        _user(MANAGER_A_ID, TENANT_A_ID, "manager-a@example.test", "Manager A"),
        _user(HR_A_ID, TENANT_A_ID, "hr-a@example.test", "HR A"),
        _user(OTHER_A_ID, TENANT_A_ID, "other-a@example.test", "Other A"),
        _user(HR_B_ID, TENANT_B_ID, "hr-b@example.test", "HR B"),
        LegalEntity(
            id=LEGAL_ENTITY_ID,
            tenant_id=TENANT_A_ID,
            code="LEGAL-A",
            name="Legal A",
            registered_name="Legal A Incorporated",
            country_code="TR",
            timezone="Europe/Istanbul",
            status=LegalEntityStatus.ACTIVE.value,
            is_default=True,
        ),
        Branch(
            id=BRANCH_ID,
            tenant_id=TENANT_A_ID,
            legal_entity_id=LEGAL_ENTITY_ID,
            code="BRANCH-A",
            name="Branch A",
            timezone="Europe/Istanbul",
            country_code="TR",
            status=BranchStatus.ACTIVE.value,
        ),
        Department(
            id=DEPARTMENT_ID,
            tenant_id=TENANT_A_ID,
            parent_id=None,
            code="DEPT-A",
            name="Department A",
            status=DepartmentStatus.ACTIVE.value,
        ),
        Position(
            id=POSITION_ID,
            tenant_id=TENANT_A_ID,
            code="POS-A",
            title="Position A",
            status=PositionStatus.ACTIVE.value,
        ),
        _employee(
            TEAM_EMPLOYEE_ID,
            TENANT_A_ID,
            "A-TEAM-001",
            "Team",
            "Employee",
            "team-a@example.test",
        ),
        _employee(
            OUTSIDE_EMPLOYEE_ID,
            TENANT_A_ID,
            "A-OUTSIDE-002",
            "Outside",
            "Employee",
            "outside-a@example.test",
        ),
        _employee(
            TENANT_B_EMPLOYEE_ID,
            TENANT_B_ID,
            "B-PRIVATE-001",
            "Private",
            "Tenant B",
            "private-b@example.test",
        ),
        EmployeeAssignment(
            id=TEAM_ASSIGNMENT_ID,
            tenant_id=TENANT_A_ID,
            employee_id=TEAM_EMPLOYEE_ID,
            legal_entity_id=LEGAL_ENTITY_ID,
            branch_id=BRANCH_ID,
            department_id=DEPARTMENT_ID,
            position_id=POSITION_ID,
            manager_user_id=MANAGER_A_ID,
            supersedes_assignment_id=None,
            effective_from=date(2020, 1, 1),
            effective_to=None,
            change_reason=None,
            created_by_user_id=HR_A_ID,
        ),
        EmployeeAssignment(
            id=OUTSIDE_ASSIGNMENT_ID,
            tenant_id=TENANT_A_ID,
            employee_id=OUTSIDE_EMPLOYEE_ID,
            legal_entity_id=LEGAL_ENTITY_ID,
            branch_id=BRANCH_ID,
            department_id=DEPARTMENT_ID,
            position_id=POSITION_ID,
            manager_user_id=OTHER_A_ID,
            supersedes_assignment_id=None,
            effective_from=date(2020, 1, 1),
            effective_to=None,
            change_reason=None,
            created_by_user_id=HR_A_ID,
        ),
    ]


def _user(user_id: UUID, tenant_id: UUID, email: str, full_name: str) -> User:
    return User(
        id=user_id,
        tenant_id=tenant_id,
        email=email,
        full_name=full_name,
        status=UserStatus.ACTIVE.value,
        password_hash="synthetic-hash",
    )


def _employee(
    employee_id: UUID,
    tenant_id: UUID,
    employee_number: str,
    first_name: str,
    last_name: str,
    email: str,
) -> Employee:
    return Employee(
        id=employee_id,
        tenant_id=tenant_id,
        employee_number=employee_number,
        first_name=first_name,
        last_name=last_name,
        email=email,
        status=EmployeeStatus.ACTIVE.value,
        employment_start_date=date(2020, 1, 1),
    )


def _succeeded_export(object_key: str) -> ReportExportJob:
    return ReportExportJob(
        id=EXPORT_JOB_ID,
        tenant_id=TENANT_A_ID,
        requested_by_user_id=HR_A_ID,
        report_type=ReportType.EMPLOYEES.value,
        format="csv",
        status=ExportJobStatus.SUCCEEDED.value,
        request_scope=ReportScope.TENANT.value,
        request_scope_user_id=None,
        fields_snapshot=["employee_number"],
        filters_snapshot={},
        generated_scope=ReportScope.TENANT.value,
        generated_scope_user_id=None,
        generated_fields=["employee_number"],
        field_classifications=["work_safe"],
        artifact_object_key=object_key,
        artifact_sha256="a" * 64,
        artifact_content_type="text/csv; charset=utf-8",
        size_bytes=42,
        row_count=1,
        attempt_count=1,
        failure_code=None,
        next_attempt_at=None,
        lease_expires_at=None,
        cancel_requested_at=None,
        available_at=FIXED_NOW,
        expires_at=datetime(2099, 1, 1, tzinfo=UTC),
        created_at=FIXED_NOW,
        updated_at=FIXED_NOW,
    )


def _preview_import(object_key: str) -> EmployeeImport:
    return EmployeeImport(
        id=PREVIEW_IMPORT_ID,
        tenant_id=TENANT_A_ID,
        requested_by_user_id=HR_A_ID,
        status=EmployeeImportStatus.INVALID.value,
        template_version="1",
        file_format="csv",
        content_type="text/csv",
        object_key=object_key,
        size_bytes=42,
        source_sha256="b" * 64,
        scan_result=EmployeeImportScanResult.CLEAN.value,
        validation_fingerprint=None,
        row_count=0,
        error_count=1,
        warning_count=0,
        committed_count=0,
        attempt_count=1,
        failure_code=None,
        next_attempt_at=None,
        lease_expires_at=None,
        validated_at=FIXED_NOW,
        committed_at=None,
        source_deleted_at=None,
        expires_at=datetime(2099, 1, 1, tzinfo=UTC),
        created_at=FIXED_NOW,
        updated_at=FIXED_NOW,
    )


def _ready_import(import_id: UUID, rows: list[EmployeeImportRow]) -> EmployeeImport:
    digest = sha256()
    for row in rows:
        digest.update(canonical_import_row(row))
    return EmployeeImport(
        id=import_id,
        tenant_id=TENANT_A_ID,
        requested_by_user_id=HR_A_ID,
        status=EmployeeImportStatus.READY.value,
        template_version="1",
        file_format="csv",
        content_type="text/csv",
        object_key=f"{TENANT_A_ID}/{import_id}/private-source.csv",
        size_bytes=42,
        source_sha256="c" * 64,
        scan_result=EmployeeImportScanResult.CLEAN.value,
        validation_fingerprint=digest.hexdigest(),
        row_count=len(rows),
        error_count=0,
        warning_count=0,
        committed_count=0,
        attempt_count=1,
        failure_code=None,
        next_attempt_at=None,
        lease_expires_at=None,
        validated_at=FIXED_NOW,
        committed_at=None,
        source_deleted_at=None,
        expires_at=datetime(2099, 1, 1, tzinfo=UTC),
        created_at=FIXED_NOW,
        updated_at=FIXED_NOW,
    )


def _import_row(
    *,
    row_id: UUID,
    import_id: UUID,
    row_number: int,
    employee_number: str,
    first_name: str,
) -> EmployeeImportRow:
    return EmployeeImportRow(
        id=row_id,
        tenant_id=TENANT_A_ID,
        import_id=import_id,
        row_number=row_number,
        employee_number=employee_number,
        employee_number_normalized=employee_number.casefold(),
        first_name=first_name,
        last_name="Import",
        work_email=f"{employee_number.casefold()}@example.test",
        work_email_normalized=f"{employee_number.casefold()}@example.test",
        status=EmployeeStatus.ACTIVE.value,
        employment_start_date=date(2020, 1, 1),
        employment_end_date=None,
        legal_entity_code="legal-a",
        branch_code="branch-a",
        department_code="dept-a",
        position_code="pos-a",
        legal_entity_id=LEGAL_ENTITY_ID,
        branch_id=BRANCH_ID,
        department_id=DEPARTMENT_ID,
        position_id=POSITION_ID,
    )


def _tenant_export_permissions() -> tuple[str, ...]:
    return (
        "report:read:tenant",
        "report:export:tenant",
    )


def _context_hr_a() -> RequestContext:
    return _context(TENANT_A_ID, "reporting-a", HR_A_ID, "a2")


def _context_other_a() -> RequestContext:
    return _context(TENANT_A_ID, "reporting-a", OTHER_A_ID, "a3")


def _context_b() -> RequestContext:
    return _context(TENANT_B_ID, "reporting-b", HR_B_ID, "b2")


def _context(
    tenant_id: UUID,
    slug: str,
    actor_id: UUID,
    membership_suffix: str,
) -> RequestContext:
    membership_id = UUID(f"{membership_suffix}000000-0000-4000-8000-000000000001")
    return RequestContext(
        request_id=f"p11-reporting-{slug}-{membership_suffix}",
        trace_id="1234567890abcdef1234567890abcdef",
        tenant=TenantContext(tenant_id=tenant_id, slug=slug),
        actor_id=actor_id,
        membership_id=membership_id,
        authentication_strength=AuthenticationStrength.SINGLE_FACTOR,
    )
