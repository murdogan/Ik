import { ApiClientError } from "./api-client";
import {
  getSessionGeneration,
  isSessionGenerationCurrent,
  requestAuthenticatedApiPlainSuccess,
  subscribeToSessionChanges,
} from "./session";

export const DOCUMENT_MIME_TYPES = [
  "application/pdf",
  "image/jpeg",
  "image/png",
] as const;
export const DOCUMENT_EXTENSIONS = ["pdf", "jpg", "jpeg", "png"] as const;
export const DOCUMENT_SENSITIVITIES = [
  "standard",
  "sensitive",
  "highly_sensitive",
] as const;
export const DOCUMENT_EXPIRY_MODES = ["none", "optional", "required"] as const;
export const DOCUMENT_PROCESSING_STATES = [
  "pending_upload",
  "pending_scan",
  "available",
  "infected",
  "scan_error",
  "rejected",
] as const;
export const DOCUMENT_CHECKLIST_STATUSES = [
  "missing",
  "available",
  "expiring",
  "expired",
] as const;

export type DocumentMimeType = (typeof DOCUMENT_MIME_TYPES)[number];
export type DocumentExtension = (typeof DOCUMENT_EXTENSIONS)[number];
export type DocumentSensitivity = (typeof DOCUMENT_SENSITIVITIES)[number];
export type DocumentExpiryMode = (typeof DOCUMENT_EXPIRY_MODES)[number];
export type DocumentProcessingState =
  (typeof DOCUMENT_PROCESSING_STATES)[number];
export type DocumentChecklistStatus =
  (typeof DOCUMENT_CHECKLIST_STATUSES)[number];

export interface EmployeeDocumentType {
  id: string;
  code: string;
  name: string;
  description: string | null;
  required: boolean;
  employee_visible: boolean;
  sensitivity: DocumentSensitivity;
  expiry_mode: DocumentExpiryMode;
  allowed_mime_types: DocumentMimeType[];
  allowed_extensions: DocumentExtension[];
  max_size_bytes: number;
  version: number;
  archived_at: string | null;
}

export interface EmployeeDocument {
  id: string;
  employee_id: string;
  document_type_id: string;
  document_type_code: string;
  document_type_name: string;
  display_filename: string;
  content_type: DocumentMimeType;
  size_bytes: number;
  issued_on: string | null;
  expires_on: string | null;
  employee_visible: boolean;
  processing_state: DocumentProcessingState;
  version: number;
  archived_at: string | null;
  created_at: string;
  downloadable: boolean;
}

export interface DocumentChecklistItem {
  document_type_id: string;
  code: string;
  name: string;
  required: boolean;
  employee_visible: boolean;
  status: DocumentChecklistStatus;
  document_id: string | null;
  expires_on: string | null;
}

export interface EmployeeDocumentSummary {
  missing: number;
  available: number;
  expiring: number;
  expired: number;
}

export interface EmployeeDocumentWorkspace {
  employee_id: string;
  summary: EmployeeDocumentSummary;
  checklist: DocumentChecklistItem[];
  documents: EmployeeDocument[];
  document_types: EmployeeDocumentType[];
}

export interface OwnEmployeeDocument {
  id: string;
  employee_id: string;
  document_type_id: string;
  document_type_name: string;
  display_filename: string;
  content_type: DocumentMimeType;
  size_bytes: number;
  issued_on: string | null;
  expires_on: string | null;
  created_at: string;
}

export interface OwnEmployeeDocumentWorkspace {
  employee_id: string;
  summary: EmployeeDocumentSummary;
  checklist: DocumentChecklistItem[];
  documents: OwnEmployeeDocument[];
}

export interface DocumentTypeMutation {
  name: string;
  description: string | null;
  required: boolean;
  employee_visible: boolean;
  sensitivity: DocumentSensitivity;
  expiry_mode: DocumentExpiryMode;
  allowed_mime_types: DocumentMimeType[];
  allowed_extensions: DocumentExtension[];
  max_size_bytes: number;
}

export interface DocumentTypeCreate extends DocumentTypeMutation {
  code: string;
}

export interface EmployeeDocumentUploadFields {
  documentTypeId: string;
  issuedOn: string | null;
  expiresOn: string | null;
  employeeVisible: boolean;
}

export interface EmployeeDocumentMetadataMutation {
  expected_version: number;
  display_filename?: string;
  issued_on?: string | null;
  expires_on?: string | null;
  employee_visible?: boolean;
}

interface UploadGrant {
  document: EmployeeDocument;
  upload_intent_id: string;
  method: "PUT";
  url: string;
  headers: Record<string, string>;
  expires_at: string;
}

interface DownloadGrant {
  document_id: string;
  method: "GET";
  url: string;
  expires_at: string;
}

interface ApiEnvelope<T> {
  data: T;
  meta: {
    request_id: string;
    trace_id: string;
    correlation_id: string;
  };
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function hasExactKeys(
  value: Record<string, unknown>,
  keys: readonly string[],
): boolean {
  const actual = Object.keys(value).sort();
  const expected = [...keys].sort();
  return (
    actual.length === expected.length &&
    actual.every((key, index) => key === expected[index])
  );
}

function isUuid(value: unknown): value is string {
  return (
    typeof value === "string" &&
    /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(
      value,
    )
  );
}

function isDateOnly(value: unknown): value is string {
  if (typeof value !== "string" || !/^\d{4}-\d{2}-\d{2}$/.test(value)) {
    return false;
  }
  const parsed = new Date(`${value}T00:00:00Z`);
  return !Number.isNaN(parsed.valueOf()) && parsed.toISOString().slice(0, 10) === value;
}

function isAwareDateTime(value: unknown): value is string {
  return (
    typeof value === "string" &&
    /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$/.test(
      value,
    ) &&
    Number.isFinite(Date.parse(value))
  );
}

function isNullableDate(value: unknown): value is string | null {
  return value === null || isDateOnly(value);
}

function isNullableDateTime(value: unknown): value is string | null {
  return value === null || isAwareDateTime(value);
}

function isNonNegativeInteger(value: unknown): value is number {
  return Number.isSafeInteger(value) && Number(value) >= 0;
}

function isPositiveInteger(value: unknown): value is number {
  return Number.isSafeInteger(value) && Number(value) >= 1;
}

function isEnumValue<TValue extends string>(
  value: unknown,
  values: readonly TValue[],
): value is TValue {
  return typeof value === "string" && values.includes(value as TValue);
}

function isStringArray<TValue extends string>(
  value: unknown,
  values: readonly TValue[],
): value is TValue[] {
  return (
    Array.isArray(value) &&
    value.length >= 1 &&
    value.every((item) => isEnumValue(item, values)) &&
    new Set(value).size === value.length
  );
}

function isDocumentType(value: unknown): value is EmployeeDocumentType {
  return (
    isRecord(value) &&
    hasExactKeys(value, [
      "id",
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
      "version",
      "archived_at",
    ]) &&
    isUuid(value.id) &&
    typeof value.code === "string" &&
    /^[a-z][a-z0-9_]{0,63}$/.test(value.code) &&
    typeof value.name === "string" &&
    value.name.length > 0 &&
    (value.description === null || typeof value.description === "string") &&
    typeof value.required === "boolean" &&
    typeof value.employee_visible === "boolean" &&
    isEnumValue(value.sensitivity, DOCUMENT_SENSITIVITIES) &&
    isEnumValue(value.expiry_mode, DOCUMENT_EXPIRY_MODES) &&
    isStringArray(value.allowed_mime_types, DOCUMENT_MIME_TYPES) &&
    isStringArray(value.allowed_extensions, DOCUMENT_EXTENSIONS) &&
    isPositiveInteger(value.max_size_bytes) &&
    value.max_size_bytes <= 50 * 1024 * 1024 &&
    isPositiveInteger(value.version) &&
    isNullableDateTime(value.archived_at)
  );
}

function isEmployeeDocument(
  value: unknown,
  expectedEmployeeId?: string,
): value is EmployeeDocument {
  return (
    isRecord(value) &&
    hasExactKeys(value, [
      "id",
      "employee_id",
      "document_type_id",
      "document_type_code",
      "document_type_name",
      "display_filename",
      "content_type",
      "size_bytes",
      "issued_on",
      "expires_on",
      "employee_visible",
      "processing_state",
      "version",
      "archived_at",
      "created_at",
      "downloadable",
    ]) &&
    isUuid(value.id) &&
    isUuid(value.employee_id) &&
    (expectedEmployeeId === undefined || value.employee_id === expectedEmployeeId) &&
    isUuid(value.document_type_id) &&
    typeof value.document_type_code === "string" &&
    typeof value.document_type_name === "string" &&
    typeof value.display_filename === "string" &&
    isEnumValue(value.content_type, DOCUMENT_MIME_TYPES) &&
    isPositiveInteger(value.size_bytes) &&
    isNullableDate(value.issued_on) &&
    isNullableDate(value.expires_on) &&
    typeof value.employee_visible === "boolean" &&
    isEnumValue(value.processing_state, DOCUMENT_PROCESSING_STATES) &&
    isPositiveInteger(value.version) &&
    isNullableDateTime(value.archived_at) &&
    isAwareDateTime(value.created_at) &&
    typeof value.downloadable === "boolean" &&
    value.downloadable ===
      (value.processing_state === "available" && value.archived_at === null)
  );
}

function isChecklistItem(value: unknown): value is DocumentChecklistItem {
  return (
    isRecord(value) &&
    hasExactKeys(value, [
      "document_type_id",
      "code",
      "name",
      "required",
      "employee_visible",
      "status",
      "document_id",
      "expires_on",
    ]) &&
    isUuid(value.document_type_id) &&
    typeof value.code === "string" &&
    typeof value.name === "string" &&
    typeof value.required === "boolean" &&
    typeof value.employee_visible === "boolean" &&
    isEnumValue(value.status, DOCUMENT_CHECKLIST_STATUSES) &&
    (value.document_id === null || isUuid(value.document_id)) &&
    isNullableDate(value.expires_on) &&
    (value.status === "missing") === (value.document_id === null)
  );
}

function isSummary(value: unknown): value is EmployeeDocumentSummary {
  return (
    isRecord(value) &&
    hasExactKeys(value, ["missing", "available", "expiring", "expired"]) &&
    isNonNegativeInteger(value.missing) &&
    isNonNegativeInteger(value.available) &&
    isNonNegativeInteger(value.expiring) &&
    isNonNegativeInteger(value.expired)
  );
}

function isWorkspace(
  value: unknown,
  employeeId: string,
): value is EmployeeDocumentWorkspace {
  return (
    isRecord(value) &&
    hasExactKeys(value, [
      "employee_id",
      "summary",
      "checklist",
      "documents",
      "document_types",
    ]) &&
    value.employee_id === employeeId &&
    isSummary(value.summary) &&
    Array.isArray(value.checklist) &&
    value.checklist.length <= 200 &&
    value.checklist.every(isChecklistItem) &&
    Array.isArray(value.documents) &&
    value.documents.length <= 200 &&
    value.documents.every((item) => isEmployeeDocument(item, employeeId)) &&
    Array.isArray(value.document_types) &&
    value.document_types.length <= 200 &&
    value.document_types.every(isDocumentType)
  );
}

function isOwnDocument(
  value: unknown,
  employeeId: string,
): value is OwnEmployeeDocument {
  return (
    isRecord(value) &&
    hasExactKeys(value, [
      "id",
      "employee_id",
      "document_type_id",
      "document_type_name",
      "display_filename",
      "content_type",
      "size_bytes",
      "issued_on",
      "expires_on",
      "created_at",
    ]) &&
    isUuid(value.id) &&
    value.employee_id === employeeId &&
    isUuid(value.document_type_id) &&
    typeof value.document_type_name === "string" &&
    typeof value.display_filename === "string" &&
    isEnumValue(value.content_type, DOCUMENT_MIME_TYPES) &&
    isPositiveInteger(value.size_bytes) &&
    isNullableDate(value.issued_on) &&
    isNullableDate(value.expires_on) &&
    isAwareDateTime(value.created_at)
  );
}

function isOwnWorkspace(
  value: unknown,
  employeeId?: string,
): value is OwnEmployeeDocumentWorkspace {
  if (!isRecord(value) || !isUuid(value.employee_id)) return false;
  const resolvedEmployeeId = value.employee_id;
  return (
    hasExactKeys(value, ["employee_id", "summary", "checklist", "documents"]) &&
    (employeeId === undefined || resolvedEmployeeId === employeeId) &&
    isSummary(value.summary) &&
    Array.isArray(value.checklist) &&
    value.checklist.length <= 200 &&
    value.checklist.every(isChecklistItem) &&
    Array.isArray(value.documents) &&
    value.documents.length <= 200 &&
    value.documents.every((item) => isOwnDocument(item, resolvedEmployeeId))
  );
}

function isSafeUrl(value: unknown): value is string {
  if (typeof value !== "string" || value.length > 4096) return false;
  try {
    const url = new URL(value);
    return (
      (url.protocol === "http:" || url.protocol === "https:") &&
      url.username === "" &&
      url.password === ""
    );
  } catch {
    return false;
  }
}

function isStringRecord(value: unknown): value is Record<string, string> {
  return (
    isRecord(value) &&
    Object.entries(value).every(
      ([key, item]) => key.length > 0 && typeof item === "string",
    )
  );
}

function isUploadGrant(
  value: unknown,
  employeeId?: string,
): value is UploadGrant {
  return (
    isRecord(value) &&
    hasExactKeys(value, [
      "document",
      "upload_intent_id",
      "method",
      "url",
      "headers",
      "expires_at",
    ]) &&
    isEmployeeDocument(value.document, employeeId) &&
    value.document.processing_state === "pending_upload" &&
    isUuid(value.upload_intent_id) &&
    value.method === "PUT" &&
    isSafeUrl(value.url) &&
    isStringRecord(value.headers) &&
    isAwareDateTime(value.expires_at)
  );
}

function isDownloadGrant(value: unknown, documentId: string): value is DownloadGrant {
  return (
    isRecord(value) &&
    hasExactKeys(value, ["document_id", "method", "url", "expires_at"]) &&
    value.document_id === documentId &&
    value.method === "GET" &&
    isSafeUrl(value.url) &&
    isAwareDateTime(value.expires_at)
  );
}

function isMeta(value: unknown): value is ApiEnvelope<unknown>["meta"] {
  return (
    isRecord(value) &&
    hasExactKeys(value, ["request_id", "trace_id", "correlation_id"]) &&
    typeof value.request_id === "string" &&
    typeof value.trace_id === "string" &&
    value.correlation_id === value.request_id
  );
}

function envelopeData(
  value: unknown,
  predicate: (data: unknown) => boolean,
): unknown | null {
  if (
    !isRecord(value) ||
    !hasExactKeys(value, ["data", "meta"]) ||
    !isMeta(value.meta) ||
    !predicate(value.data)
  ) {
    return null;
  }
  return value.data;
}

function invalidResponse(status: number, headers: Headers): ApiClientError {
  return new ApiClientError({
    status,
    code: "invalid_response",
    correlationId: headers.get("x-request-id"),
  });
}

async function readEnvelope<T>(
  path: `/api/${string}`,
  predicate: (data: unknown) => data is T,
  options: { method?: "GET" | "POST" | "PATCH"; body?: object } = {},
): Promise<T> {
  const response = await requestAuthenticatedApiPlainSuccess<unknown>(path, options);
  const data = envelopeData(response.data, predicate);
  if (data === null) throw invalidResponse(response.status, response.headers);
  return data as T;
}

export async function listDocumentTypes(): Promise<EmployeeDocumentType[]> {
  return readEnvelope(
    "/api/v1/document-types?include_archived=true",
    (value): value is EmployeeDocumentType[] =>
      Array.isArray(value) && value.length <= 200 && value.every(isDocumentType),
  );
}

export async function createDocumentType(
  payload: DocumentTypeCreate,
): Promise<EmployeeDocumentType> {
  return readEnvelope("/api/v1/document-types", isDocumentType, {
    method: "POST",
    body: payload,
  });
}

export async function updateDocumentType(
  documentTypeId: string,
  expectedVersion: number,
  payload: DocumentTypeMutation,
): Promise<EmployeeDocumentType> {
  return readEnvelope(
    `/api/v1/document-types/${encodeURIComponent(documentTypeId)}`,
    isDocumentType,
    { method: "PATCH", body: { expected_version: expectedVersion, ...payload } },
  );
}

export async function setDocumentTypeArchived(
  documentTypeId: string,
  expectedVersion: number,
  archived: boolean,
): Promise<EmployeeDocumentType> {
  return readEnvelope(
    `/api/v1/document-types/${encodeURIComponent(documentTypeId)}/${archived ? "archive" : "unarchive"}`,
    isDocumentType,
    { method: "POST", body: { expected_version: expectedVersion } },
  );
}

export async function readEmployeeDocuments(
  employeeId: string,
): Promise<EmployeeDocumentWorkspace> {
  return readEnvelope(
    `/api/v1/employees/${encodeURIComponent(employeeId)}/documents`,
    (value): value is EmployeeDocumentWorkspace => isWorkspace(value, employeeId),
  );
}

function fileExtension(filename: string): DocumentExtension | null {
  const extension = filename.split(".").pop()?.toLocaleLowerCase("en-US") ?? "";
  return isEnumValue(extension, DOCUMENT_EXTENSIONS) ? extension : null;
}

function mimeForExtension(extension: DocumentExtension): DocumentMimeType {
  if (extension === "pdf") return "application/pdf";
  if (extension === "png") return "image/png";
  return "image/jpeg";
}

async function putPresignedObject(grant: UploadGrant, file: File): Promise<void> {
  const generation = getSessionGeneration();
  const controller = new AbortController();
  const unsubscribe = subscribeToSessionChanges(() => controller.abort());
  try {
    let response: Response;
    try {
      response = await fetch(grant.url, {
        method: "PUT",
        headers: grant.headers,
        body: file,
        cache: "no-store",
        credentials: "omit",
        signal: controller.signal,
      });
    } catch {
      throw new ApiClientError({ status: null, code: "object_upload_failed" });
    }
    if (!response.ok) {
      throw new ApiClientError({
        status: response.status,
        code: "object_upload_failed",
      });
    }
    if (!isSessionGenerationCurrent(generation)) {
      throw new ApiClientError({ status: null, code: "session_superseded" });
    }
  } finally {
    unsubscribe();
  }
}

export async function uploadEmployeeDocument(
  employeeId: string,
  file: File,
  fields: EmployeeDocumentUploadFields,
): Promise<EmployeeDocument> {
  const extension = fileExtension(file.name);
  if (extension === null) {
    throw new TypeError("Only PDF, JPG, JPEG, and PNG files are supported");
  }
  const contentType = mimeForExtension(extension);
  if (file.type !== "" && file.type !== contentType) {
    throw new TypeError("File MIME type and extension do not match");
  }
  const grant = await readEnvelope(
    `/api/v1/employees/${encodeURIComponent(employeeId)}/documents/uploads`,
    (value): value is UploadGrant => isUploadGrant(value, employeeId),
    {
      method: "POST",
      body: {
        document_type_id: fields.documentTypeId,
        display_filename: file.name,
        declared_content_type: contentType,
        size_bytes: file.size,
        issued_on: fields.issuedOn,
        expires_on: fields.expiresOn,
        employee_visible: fields.employeeVisible,
      },
    },
  );
  await putPresignedObject(grant, file);
  return readEnvelope(
    `/api/v1/employees/${encodeURIComponent(employeeId)}/documents/${encodeURIComponent(grant.document.id)}/finalize`,
    (value): value is EmployeeDocument =>
      isEmployeeDocument(value, employeeId) && value.id === grant.document.id,
    {
      method: "POST",
      body: { upload_intent_id: grant.upload_intent_id },
    },
  );
}

export async function updateEmployeeDocumentMetadata(
  employeeId: string,
  documentId: string,
  payload: EmployeeDocumentMetadataMutation,
): Promise<EmployeeDocument> {
  return readEnvelope(
    `/api/v1/employees/${encodeURIComponent(employeeId)}/documents/${encodeURIComponent(documentId)}`,
    (value): value is EmployeeDocument =>
      isEmployeeDocument(value, employeeId) && value.id === documentId,
    { method: "PATCH", body: payload },
  );
}

export async function setEmployeeDocumentArchived(
  employeeId: string,
  documentId: string,
  expectedVersion: number,
  archived: boolean,
): Promise<EmployeeDocument> {
  return readEnvelope(
    `/api/v1/employees/${encodeURIComponent(employeeId)}/documents/${encodeURIComponent(documentId)}/${archived ? "archive" : "unarchive"}`,
    (value): value is EmployeeDocument =>
      isEmployeeDocument(value, employeeId) && value.id === documentId,
    { method: "POST", body: { expected_version: expectedVersion } },
  );
}

export async function issueEmployeeDocumentDownload(
  employeeId: string,
  documentId: string,
): Promise<string> {
  const grant = await readEnvelope(
    `/api/v1/employees/${encodeURIComponent(employeeId)}/documents/${encodeURIComponent(documentId)}/download`,
    (value): value is DownloadGrant => isDownloadGrant(value, documentId),
    { method: "POST" },
  );
  return grant.url;
}

export async function readOwnEmployeeDocuments(
  employeeId?: string,
): Promise<OwnEmployeeDocumentWorkspace> {
  return readEnvelope(
    "/api/v1/me/documents",
    (value): value is OwnEmployeeDocumentWorkspace =>
      isOwnWorkspace(value, employeeId),
  );
}

export async function listOwnEmployeeDocumentUploadTypes(): Promise<
  EmployeeDocumentType[]
> {
  return readEnvelope(
    "/api/v1/me/documents/upload-types",
    (value): value is EmployeeDocumentType[] =>
      Array.isArray(value) &&
      value.length <= 200 &&
      value.every(isDocumentType),
  );
}

export async function uploadOwnEmployeeDocument(
  file: File,
  fields: EmployeeDocumentUploadFields,
): Promise<EmployeeDocument> {
  const extension = fileExtension(file.name);
  if (extension === null) {
    throw new TypeError("Only PDF, JPG, JPEG, and PNG files are supported");
  }
  const contentType = mimeForExtension(extension);
  if (file.type !== "" && file.type !== contentType) {
    throw new TypeError("File MIME type and extension do not match");
  }
  const grant = await readEnvelope(
    "/api/v1/me/documents/uploads",
    (value): value is UploadGrant => isUploadGrant(value),
    {
      method: "POST",
      body: {
        document_type_id: fields.documentTypeId,
        display_filename: file.name,
        declared_content_type: contentType,
        size_bytes: file.size,
        issued_on: fields.issuedOn,
        expires_on: fields.expiresOn,
        employee_visible: fields.employeeVisible,
      },
    },
  );
  await putPresignedObject(grant, file);
  return readEnvelope(
    `/api/v1/me/documents/${encodeURIComponent(grant.document.id)}/finalize`,
    (value): value is EmployeeDocument =>
      isEmployeeDocument(value) && value.id === grant.document.id,
    {
      method: "POST",
      body: { upload_intent_id: grant.upload_intent_id },
    },
  );
}

export async function issueOwnEmployeeDocumentDownload(
  documentId: string,
): Promise<string> {
  const grant = await readEnvelope(
    `/api/v1/me/documents/${encodeURIComponent(documentId)}/download`,
    (value): value is DownloadGrant => isDownloadGrant(value, documentId),
    { method: "POST" },
  );
  return grant.url;
}
