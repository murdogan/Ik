"""Closed API contracts for employee document policy and secure object grants."""

from __future__ import annotations

from datetime import date, datetime
from enum import StrEnum
from re import fullmatch
from typing import Self
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models.employee_document import (
    DocumentExpiryMode,
    DocumentProcessingState,
    DocumentSensitivity,
)

DEFAULT_DOCUMENT_MAX_SIZE_BYTES = 20 * 1024 * 1024
HARD_DOCUMENT_MAX_SIZE_BYTES = 50 * 1024 * 1024
DOCUMENT_LIST_LIMIT = 200
DOCUMENT_CODE_PATTERN = r"[a-z][a-z0-9_]{0,63}"


class AllowedDocumentMimeType(StrEnum):
    PDF = "application/pdf"
    JPEG = "image/jpeg"
    PNG = "image/png"


class AllowedDocumentExtension(StrEnum):
    PDF = "pdf"
    JPG = "jpg"
    JPEG = "jpeg"
    PNG = "png"


class DocumentChecklistStatus(StrEnum):
    MISSING = "missing"
    AVAILABLE = "available"
    EXPIRING = "expiring"
    EXPIRED = "expired"


class _DocumentTypePolicy(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=500)
    required: bool
    employee_visible: bool
    sensitivity: DocumentSensitivity
    expiry_mode: DocumentExpiryMode
    allowed_mime_types: list[AllowedDocumentMimeType] = Field(min_length=1, max_length=3)
    allowed_extensions: list[AllowedDocumentExtension] = Field(min_length=1, max_length=4)
    max_size_bytes: int = Field(ge=1, le=HARD_DOCUMENT_MAX_SIZE_BYTES)

    @field_validator("allowed_mime_types", "allowed_extensions")
    @classmethod
    def require_unique_values(cls, value: list[object]) -> list[object]:
        if len(set(value)) != len(value):
            raise ValueError("Allowed file policy values must be unique")
        return value

    @model_validator(mode="after")
    def require_coherent_file_policy(self) -> Self:
        mime_types = set(self.allowed_mime_types)
        extensions = set(self.allowed_extensions)
        mappings = {
            AllowedDocumentMimeType.PDF: {AllowedDocumentExtension.PDF},
            AllowedDocumentMimeType.JPEG: {
                AllowedDocumentExtension.JPG,
                AllowedDocumentExtension.JPEG,
            },
            AllowedDocumentMimeType.PNG: {AllowedDocumentExtension.PNG},
        }
        for mime_type, mapped_extensions in mappings.items():
            if (mime_type in mime_types) != bool(extensions & mapped_extensions):
                raise ValueError("Allowed MIME types and extensions must describe the same files")
        return self


class DocumentTypeCreate(_DocumentTypePolicy):
    code: str = Field(min_length=1, max_length=64)

    @field_validator("code")
    @classmethod
    def validate_code(cls, value: str) -> str:
        if fullmatch(DOCUMENT_CODE_PATTERN, value) is None:
            raise ValueError("Document type code must be a lowercase identifier")
        return value


class DocumentTypeUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    expected_version: int = Field(ge=1)
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=500)
    required: bool | None = None
    employee_visible: bool | None = None
    sensitivity: DocumentSensitivity | None = None
    expiry_mode: DocumentExpiryMode | None = None
    allowed_mime_types: list[AllowedDocumentMimeType] | None = Field(
        default=None, min_length=1, max_length=3
    )
    allowed_extensions: list[AllowedDocumentExtension] | None = Field(
        default=None, min_length=1, max_length=4
    )
    max_size_bytes: int | None = Field(default=None, ge=1, le=HARD_DOCUMENT_MAX_SIZE_BYTES)

    @field_validator("allowed_mime_types", "allowed_extensions")
    @classmethod
    def require_unique_values(cls, value: list[object] | None) -> list[object] | None:
        if value is not None and len(set(value)) != len(value):
            raise ValueError("Allowed file policy values must be unique")
        return value

    @model_validator(mode="after")
    def require_mutation(self) -> Self:
        mutable = set(self.model_fields_set) - {"expected_version"}
        if not mutable:
            raise ValueError("At least one document type field must be provided")
        for field_name in (
            "name",
            "required",
            "employee_visible",
            "sensitivity",
            "expiry_mode",
            "allowed_mime_types",
            "allowed_extensions",
            "max_size_bytes",
        ):
            if field_name in self.model_fields_set and getattr(self, field_name) is None:
                raise ValueError(f"{field_name} cannot be null")
        return self


class VersionedDocumentAction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_version: int = Field(ge=1)


class DocumentTypeRead(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)

    id: UUID
    code: str
    name: str
    description: str | None
    required: bool
    employee_visible: bool
    sensitivity: DocumentSensitivity
    expiry_mode: DocumentExpiryMode
    allowed_mime_types: list[AllowedDocumentMimeType]
    allowed_extensions: list[AllowedDocumentExtension]
    max_size_bytes: int = Field(ge=1, le=HARD_DOCUMENT_MAX_SIZE_BYTES)
    version: int = Field(ge=1)
    archived_at: datetime | None


class EmployeeDocumentUploadInitiate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    document_type_id: UUID
    display_filename: str = Field(min_length=1, max_length=255)
    declared_content_type: AllowedDocumentMimeType
    size_bytes: int = Field(ge=1, le=HARD_DOCUMENT_MAX_SIZE_BYTES)
    issued_on: date | None = None
    expires_on: date | None = None
    employee_visible: bool | None = None

    @model_validator(mode="after")
    def require_date_order(self) -> Self:
        if self.issued_on is not None and self.expires_on is not None:
            if self.expires_on < self.issued_on:
                raise ValueError("Document expiry date cannot precede issue date")
        return self


class EmployeeDocumentFinalize(BaseModel):
    model_config = ConfigDict(extra="forbid")

    upload_intent_id: UUID


class EmployeeDocumentMetadataUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    expected_version: int = Field(ge=1)
    display_filename: str | None = Field(default=None, min_length=1, max_length=255)
    issued_on: date | None = None
    expires_on: date | None = None
    employee_visible: bool | None = None

    @model_validator(mode="after")
    def validate_update(self) -> Self:
        mutable = set(self.model_fields_set) - {"expected_version"}
        if not mutable:
            raise ValueError("At least one document metadata field must be provided")
        if "display_filename" in self.model_fields_set and self.display_filename is None:
            raise ValueError("display_filename cannot be null")
        if "employee_visible" in self.model_fields_set and self.employee_visible is None:
            raise ValueError("employee_visible cannot be null")
        issued_on = self.issued_on if "issued_on" in self.model_fields_set else None
        expires_on = self.expires_on if "expires_on" in self.model_fields_set else None
        if issued_on is not None and expires_on is not None and expires_on < issued_on:
            raise ValueError("Document expiry date cannot precede issue date")
        return self


class EmployeeDocumentRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    employee_id: UUID
    document_type_id: UUID
    document_type_code: str
    document_type_name: str
    display_filename: str
    content_type: AllowedDocumentMimeType
    size_bytes: int = Field(ge=1, le=HARD_DOCUMENT_MAX_SIZE_BYTES)
    issued_on: date | None
    expires_on: date | None
    employee_visible: bool
    processing_state: DocumentProcessingState
    version: int = Field(ge=1)
    archived_at: datetime | None
    created_at: datetime
    downloadable: bool


class EmployeeDocumentUploadGrantRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    document: EmployeeDocumentRead
    upload_intent_id: UUID
    method: str = Field(pattern="^PUT$")
    url: str = Field(min_length=1, max_length=4096)
    headers: dict[str, str]
    expires_at: AwareDatetime


class EmployeeDocumentDownloadGrantRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    document_id: UUID
    method: str = Field(pattern="^GET$")
    url: str = Field(min_length=1, max_length=4096)
    expires_at: AwareDatetime


class DocumentChecklistItemRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    document_type_id: UUID
    code: str
    name: str
    required: bool
    employee_visible: bool
    status: DocumentChecklistStatus
    document_id: UUID | None
    expires_on: date | None


class EmployeeDocumentSummaryRead(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    missing: int = Field(ge=0)
    available: int = Field(ge=0)
    expiring: int = Field(ge=0)
    expired: int = Field(ge=0)


class EmployeeDocumentWorkspaceRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    employee_id: UUID
    summary: EmployeeDocumentSummaryRead
    checklist: list[DocumentChecklistItemRead]
    documents: list[EmployeeDocumentRead]
    document_types: list[DocumentTypeRead]


class OwnEmployeeDocumentRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    employee_id: UUID
    document_type_id: UUID
    document_type_name: str
    display_filename: str
    content_type: AllowedDocumentMimeType
    size_bytes: int = Field(ge=1, le=HARD_DOCUMENT_MAX_SIZE_BYTES)
    issued_on: date | None
    expires_on: date | None
    created_at: datetime


class OwnEmployeeDocumentWorkspaceRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    employee_id: UUID
    summary: EmployeeDocumentSummaryRead
    checklist: list[DocumentChecklistItemRead]
    documents: list[OwnEmployeeDocumentRead]


__all__ = [
    "AllowedDocumentExtension",
    "AllowedDocumentMimeType",
    "DEFAULT_DOCUMENT_MAX_SIZE_BYTES",
    "DOCUMENT_LIST_LIMIT",
    "DocumentChecklistItemRead",
    "DocumentChecklistStatus",
    "DocumentTypeCreate",
    "DocumentTypeRead",
    "DocumentTypeUpdate",
    "EmployeeDocumentDownloadGrantRead",
    "EmployeeDocumentFinalize",
    "EmployeeDocumentMetadataUpdate",
    "EmployeeDocumentRead",
    "EmployeeDocumentSummaryRead",
    "EmployeeDocumentUploadGrantRead",
    "EmployeeDocumentUploadInitiate",
    "EmployeeDocumentWorkspaceRead",
    "HARD_DOCUMENT_MAX_SIZE_BYTES",
    "OwnEmployeeDocumentRead",
    "OwnEmployeeDocumentWorkspaceRead",
    "VersionedDocumentAction",
]
