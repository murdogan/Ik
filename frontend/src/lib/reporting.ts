import { ApiClientError, type ApiFileSuccess } from "./api-client";
import {
  requestAuthenticatedApi,
  requestAuthenticatedApiEnvelope,
  requestAuthenticatedApiFile,
  requestAuthenticatedApiPlainSuccess,
} from "./session";

export const REPORT_TYPES = ["employees", "leaves", "missing_documents"] as const;
export const REPORT_FORMATS = ["csv", "xlsx"] as const;
export const REPORT_SCOPES = ["tenant", "team"] as const;
export const EXPORT_JOB_STATUSES = [
  "queued",
  "running",
  "retry",
  "succeeded",
  "failed",
  "cancelled",
  "expired",
] as const;
export const IMPORT_STATUSES = [
  "queued",
  "processing",
  "retry",
  "ready",
  "invalid",
  "succeeded",
  "failed",
  "expired",
] as const;

export const REPORT_FIELDS = {
  employees: [
    "employee_number",
    "first_name",
    "last_name",
    "work_email",
    "employment_status",
    "employment_start_date",
    "employment_end_date",
    "legal_entity",
    "branch",
    "department",
    "position",
  ],
  leaves: [
    "employee_number",
    "employee_name",
    "leave_type",
    "start_date",
    "end_date",
    "counted_days",
    "status",
    "submitted_at",
    "decided_at",
  ],
  missing_documents: [
    "employee_number",
    "employee_name",
    "document_type_code",
    "document_type_name",
    "checklist_status",
    "expires_on",
  ],
} as const;

export type ReportType = (typeof REPORT_TYPES)[number];
export type ReportFormat = (typeof REPORT_FORMATS)[number];
export type ReportScope = (typeof REPORT_SCOPES)[number];
export type ExportJobStatus = (typeof EXPORT_JOB_STATUSES)[number];
export type EmployeeImportStatus = (typeof IMPORT_STATUSES)[number];
export type ReportValue = string | number | null;
export type ReportFilters = Record<
  string,
  string | readonly string[] | null | undefined
>;

export interface ReportRow {
  values: Record<string, ReportValue>;
}

export interface ReportPage {
  data: ReportRow[];
  meta: {
    request_id: string;
    trace_id: string;
    correlation_id: string;
    limit: number;
    next_cursor: string | null;
    scope: ReportScope;
    fields: string[];
  };
}

export interface DashboardActivity {
  activity_type: string;
  entity_type: string;
  entity_id: string;
  title: string;
  occurred_at: string;
}

export interface DashboardSummary {
  scope: "tenant" | "team" | "own";
  active_employee_count: number;
  pending_leave_count: number;
  employee_count: number;
  pending_leave_requests: number;
  new_starters_this_month: number;
  terminated_this_month: number;
  missing_document_count: number;
  expiring_document_count: number;
  open_tasks: number;
  department_distribution: { department: string; count: number }[];
  recent_activity: DashboardActivity[];
}

export interface ExportJob {
  id: string;
  report_type: ReportType;
  format: ReportFormat;
  status: ExportJobStatus;
  request_scope: ReportScope;
  fields: string[];
  generated_scope: ReportScope | null;
  generated_fields: string[] | null;
  field_classifications: string[] | null;
  row_count: number | null;
  size_bytes: number | null;
  sha256: string | null;
  failure_code: string | null;
  cancel_requested: boolean;
  download_intents_remaining: number;
  available_at: string | null;
  expires_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface ExportDownloadIntent {
  export_job_id: string;
  method: "GET";
  url: string;
  expires_at: string;
}

export interface EmployeeImportIssue {
  row_number: number;
  severity: "error" | "warning";
  code: string;
  field: string | null;
  message: string;
}

export interface EmployeeImport {
  id: string;
  status: EmployeeImportStatus;
  template_version: "1";
  file_format: ReportFormat;
  scan_result: "pending" | "clean" | "infected" | "error";
  row_count: number;
  error_count: number;
  warning_count: number;
  committed_count: number;
  failure_code: string | null;
  issues: EmployeeImportIssue[];
  issues_next_cursor: string | null;
  validated_at: string | null;
  committed_at: string | null;
  expires_at: string;
  created_at: string;
  updated_at: string;
}

export interface EmployeeImportCommit {
  id: string;
  status: "succeeded";
  committed_count: number;
  committed_at: string;
}

const UUID_PATTERN =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
const SHA256_PATTERN = /^[0-9a-f]{64}$/;
const ISO_DATE_PATTERN = /^\d{4}-\d{2}-\d{2}$/;
const DECIMAL_PATTERN = /^\d{1,7}(?:\.\d{1,4})?$/;
const MAX_IMPORT_BYTES = 10 * 1024 * 1024;
const NULLABLE_REPORT_FIELDS = new Set([
  "work_email",
  "employment_end_date",
  "legal_entity",
  "branch",
  "department",
  "position",
  "decided_at",
  "expires_on",
]);
const DATE_REPORT_FIELDS = new Set([
  "employment_start_date",
  "employment_end_date",
  "start_date",
  "end_date",
  "expires_on",
]);
const DATETIME_REPORT_FIELDS = new Set(["submitted_at", "decided_at"]);
const DASHBOARD_ACTIVITY_CONTRACT: Record<
  string,
  { entityType: "employee" | "leave_request"; title: string }
> = {
  "employee.created": { entityType: "employee", title: "Employee record created" },
  "employee.updated": { entityType: "employee", title: "Employee record updated" },
  "employee.lifecycle.changed": {
    entityType: "employee",
    title: "Employee lifecycle updated",
  },
  "leave.requested": {
    entityType: "leave_request",
    title: "Leave request submitted",
  },
  "leave.approved": {
    entityType: "leave_request",
    title: "Leave request approved",
  },
  "leave.rejected": {
    entityType: "leave_request",
    title: "Leave request rejected",
  },
  "leave.cancelled": {
    entityType: "leave_request",
    title: "Leave request cancelled",
  },
};
const EXPORT_FAILURE_CODES = new Set([
  "authorization_revoked",
  "file_too_large",
  "row_limit_exceeded",
  "storage_unavailable",
  "worker_failure",
]);
const IMPORT_FAILURE_CODES = new Set([
  "infected_file",
  "invalid_file",
  "row_limit_exceeded",
  "scanner_unavailable",
  "storage_unavailable",
  "worker_failure",
]);
const FIELD_CLASSIFICATIONS = new Set(["work_safe", "work_contact", "hr_metadata"]);
const IMPORT_ISSUE_MESSAGES: Record<string, string> = {
  duplicate_employee_number_file: "Employee number is duplicated in this file.",
  duplicate_employee_number_tenant: "Employee number is already in use.",
  duplicate_work_email_file: "Work email is duplicated in this file.",
  duplicate_work_email_tenant: "Work email is already in use.",
  empty_file: "The file contains no employee rows.",
  employment_end_date_not_supported:
    "Employment end date must be blank in template version 1.",
  formula_not_allowed: "Spreadsheet formulas are not accepted in import fields.",
  future_start_date: "Employment starts in the future.",
  inactive_reference: "The organization reference is inactive.",
  infected_file: "The uploaded file did not pass malware scanning.",
  invalid_date: "Use an ISO date in YYYY-MM-DD format.",
  invalid_date_order: "Employment end date cannot precede the start date.",
  invalid_email: "Work email format is invalid.",
  invalid_file: "The uploaded file cannot be processed.",
  invalid_headers: "The template headers or version are invalid.",
  invalid_reference: "The organization code was not found.",
  invalid_row_shape: "The row does not match the versioned template.",
  invalid_status: "Status must be active or on_leave.",
  reference_mismatch: "The branch does not belong to the selected legal entity.",
  required: "This field is required.",
  row_limit_exceeded: "The file exceeds the 10,000-row limit.",
  value_too_long: "The field exceeds its maximum length.",
};
const IMPORT_FIELDS = new Set([
  "employee_number",
  "first_name",
  "last_name",
  "work_email",
  "status",
  "employment_start_date",
  "employment_end_date",
  "legal_entity_code",
  "branch_code",
  "department_code",
  "position_code",
]);

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function hasExactKeys(value: Record<string, unknown>, keys: readonly string[]): boolean {
  const actual = Object.keys(value);
  return actual.length === keys.length && keys.every((key) => key in value);
}

function isUuid(value: unknown): value is string {
  return typeof value === "string" && UUID_PATTERN.test(value);
}

function isAwareDateTime(value: unknown): value is string {
  return (
    typeof value === "string" &&
    /(?:Z|[+-]\d{2}:\d{2})$/.test(value) &&
    Number.isFinite(Date.parse(value))
  );
}

function isNullableAwareDateTime(value: unknown): value is string | null {
  return value === null || isAwareDateTime(value);
}

function isNonNegativeInteger(value: unknown, maximum = Number.MAX_SAFE_INTEGER): value is number {
  return (
    typeof value === "number" &&
    Number.isSafeInteger(value) &&
    value >= 0 &&
    value <= maximum
  );
}

function isNullableCursor(value: unknown): value is string | null {
  return (
    value === null ||
    (typeof value === "string" && value.length >= 1 && value.length <= 2_048)
  );
}

function isStringArray(value: unknown, maximum: number): value is string[] {
  return (
    Array.isArray(value) &&
    value.length <= maximum &&
    value.every((item) => typeof item === "string") &&
    new Set(value).size === value.length
  );
}

function invalidResponse(): ApiClientError {
  return new ApiClientError({ status: 200, code: "invalid_response" });
}

function reportFields(reportType: ReportType): readonly string[] {
  return REPORT_FIELDS[reportType];
}

function isIsoDate(value: unknown): value is string {
  if (typeof value !== "string" || !ISO_DATE_PATTERN.test(value)) return false;
  const parsed = new Date(`${value}T00:00:00Z`);
  return Number.isFinite(parsed.valueOf()) && parsed.toISOString().slice(0, 10) === value;
}

function isReportValue(field: string, value: unknown): value is ReportValue {
  if (value === null) return NULLABLE_REPORT_FIELDS.has(field);
  if (DATE_REPORT_FIELDS.has(field)) return isIsoDate(value);
  if (DATETIME_REPORT_FIELDS.has(field)) return isAwareDateTime(value);
  if (field === "counted_days") {
    return (
      (typeof value === "number" && Number.isFinite(value) && value >= 0) ||
      (typeof value === "string" && DECIMAL_PATTERN.test(value))
    );
  }
  if (field === "employment_status") {
    return (
      typeof value === "string" &&
      ["active", "on_leave", "terminated"].includes(value)
    );
  }
  if (field === "status") {
    return (
      typeof value === "string" &&
      ["pending", "approved", "rejected", "cancelled"].includes(value)
    );
  }
  if (field === "checklist_status") {
    return (
      typeof value === "string" &&
      ["missing", "expiring", "expired"].includes(value)
    );
  }
  return typeof value === "string" && value.length <= 32_767;
}

function isReportRow(
  value: unknown,
  allowedFields: ReadonlySet<string>,
  selectedFields: readonly string[],
): value is ReportRow {
  if (!isRecord(value) || !hasExactKeys(value, ["values"]) || !isRecord(value.values)) {
    return false;
  }
  const rowValues = value.values;
  const keys = Object.keys(rowValues);
  return (
    keys.length === selectedFields.length &&
    keys.every(
      (key) =>
        allowedFields.has(key) &&
        selectedFields.includes(key) &&
        isReportValue(key, rowValues[key]),
    )
  );
}

function parseReportPage(value: unknown, reportType: ReportType): ReportPage {
  if (!isRecord(value) || !hasExactKeys(value, ["data", "meta"]) || !isRecord(value.meta)) {
    throw invalidResponse();
  }
  const meta = value.meta;
  if (
    !hasExactKeys(meta, [
      "request_id",
      "trace_id",
      "correlation_id",
      "limit",
      "next_cursor",
      "scope",
      "fields",
    ]) ||
    typeof meta.request_id !== "string" ||
    typeof meta.trace_id !== "string" ||
    typeof meta.correlation_id !== "string" ||
    !isNonNegativeInteger(meta.limit, 200) ||
    Number(meta.limit) < 1 ||
    !isNullableCursor(meta.next_cursor) ||
    !REPORT_SCOPES.includes(meta.scope as ReportScope) ||
    !isStringArray(meta.fields, reportFields(reportType).length) ||
    !meta.fields.every((field) => new Set<string>(reportFields(reportType)).has(field)) ||
    !Array.isArray(value.data) ||
    value.data.length > Number(meta.limit)
  ) {
    throw invalidResponse();
  }
  const allowedFields = new Set<string>(reportFields(reportType));
  if (!value.data.every((row) => isReportRow(row, allowedFields, meta.fields as string[]))) {
    throw invalidResponse();
  }
  return value as unknown as ReportPage;
}

function isDepartmentDistribution(value: unknown): value is { department: string; count: number } {
  return (
    isRecord(value) &&
    hasExactKeys(value, ["department", "count"]) &&
    typeof value.department === "string" &&
    value.department.length > 0 &&
    isNonNegativeInteger(value.count)
  );
}

function isDashboardActivity(value: unknown): value is DashboardActivity {
  if (
    !isRecord(value) ||
    !hasExactKeys(value, [
      "activity_type",
      "entity_type",
      "entity_id",
      "title",
      "occurred_at",
    ]) ||
    typeof value.activity_type !== "string"
  ) {
    return false;
  }
  const contract = DASHBOARD_ACTIVITY_CONTRACT[value.activity_type];
  return (
    contract !== undefined &&
    value.entity_type === contract.entityType &&
    isUuid(value.entity_id) &&
    value.title === contract.title &&
    isAwareDateTime(value.occurred_at)
  );
}

function isDashboardSummary(value: unknown): value is DashboardSummary {
  if (
    !isRecord(value) ||
    !hasExactKeys(value, [
      "scope",
      "active_employee_count",
      "pending_leave_count",
      "employee_count",
      "pending_leave_requests",
      "new_starters_this_month",
      "terminated_this_month",
      "missing_document_count",
      "expiring_document_count",
      "open_tasks",
      "department_distribution",
      "recent_activity",
    ]) ||
    !["tenant", "team", "own"].includes(String(value.scope))
  ) {
    return false;
  }
  const counters = [
    value.active_employee_count,
    value.pending_leave_count,
    value.employee_count,
    value.pending_leave_requests,
    value.new_starters_this_month,
    value.terminated_this_month,
    value.missing_document_count,
    value.expiring_document_count,
    value.open_tasks,
  ];
  return (
    counters.every((counter) => isNonNegativeInteger(counter)) &&
    Array.isArray(value.department_distribution) &&
    value.department_distribution.length <= 20 &&
    value.department_distribution.every(isDepartmentDistribution) &&
    Array.isArray(value.recent_activity) &&
    value.recent_activity.length <= 20 &&
    value.recent_activity.every(isDashboardActivity)
  );
}

function isExportJob(value: unknown): value is ExportJob {
  if (
    !isRecord(value) ||
    !hasExactKeys(value, [
      "id",
      "report_type",
      "format",
      "status",
      "request_scope",
      "fields",
      "generated_scope",
      "generated_fields",
      "field_classifications",
      "row_count",
      "size_bytes",
      "sha256",
      "failure_code",
      "cancel_requested",
      "download_intents_remaining",
      "available_at",
      "expires_at",
      "created_at",
      "updated_at",
    ]) ||
    !isUuid(value.id) ||
    !REPORT_TYPES.includes(value.report_type as ReportType) ||
    !REPORT_FORMATS.includes(value.format as ReportFormat) ||
    !EXPORT_JOB_STATUSES.includes(value.status as ExportJobStatus) ||
    !REPORT_SCOPES.includes(value.request_scope as ReportScope) ||
    !isStringArray(value.fields, 11)
  ) {
    return false;
  }
  const type = value.report_type as ReportType;
  const allowed = new Set<string>(reportFields(type));
  const requestedFields = value.fields as string[];
  const commonValid =
    requestedFields.length > 0 &&
    requestedFields.every((field) => allowed.has(field)) &&
    (value.generated_scope === null || REPORT_SCOPES.includes(value.generated_scope as ReportScope)) &&
    (value.generated_fields === null ||
      (isStringArray(value.generated_fields, 11) &&
        value.generated_fields.every((field) => allowed.has(field)))) &&
    (value.field_classifications === null ||
      (isStringArray(value.field_classifications, 3) &&
        value.field_classifications.every((item) => FIELD_CLASSIFICATIONS.has(item)))) &&
    (value.row_count === null || isNonNegativeInteger(value.row_count, 10_000)) &&
    (value.size_bytes === null || (isNonNegativeInteger(value.size_bytes) && value.size_bytes > 0)) &&
    (value.sha256 === null || (typeof value.sha256 === "string" && SHA256_PATTERN.test(value.sha256))) &&
    (value.failure_code === null ||
      (typeof value.failure_code === "string" && EXPORT_FAILURE_CODES.has(value.failure_code))) &&
    typeof value.cancel_requested === "boolean" &&
    isNonNegativeInteger(value.download_intents_remaining, 3) &&
    isNullableAwareDateTime(value.available_at) &&
    isNullableAwareDateTime(value.expires_at) &&
    isAwareDateTime(value.created_at) &&
    isAwareDateTime(value.updated_at);
  if (!commonValid) return false;

  const status = value.status as ExportJobStatus;
  if (value.cancel_requested !== (status === "cancelled")) return false;
  const generatedFields = value.generated_fields as string[] | null;
  const hasArtifactMetadata =
    value.generated_scope !== null &&
    generatedFields !== null &&
    generatedFields.length > 0 &&
    generatedFields.every((field) => requestedFields.includes(field)) &&
    value.field_classifications !== null &&
    value.row_count !== null &&
    value.size_bytes !== null &&
    value.sha256 !== null &&
    value.available_at !== null &&
    value.expires_at !== null;
  if (status === "succeeded" || status === "expired") {
    if (!hasArtifactMetadata || value.failure_code !== null) return false;
    if (
      value.request_scope === "team" &&
      value.generated_scope !== "team"
    ) {
      return false;
    }
    const expectedClassifications = new Set(["work_safe"]);
    if (type === "employees" && generatedFields?.includes("work_email")) {
      expectedClassifications.add("work_contact");
    }
    if (type === "leaves" || type === "missing_documents") {
      expectedClassifications.add("hr_metadata");
    }
    const actualClassifications = value.field_classifications as string[];
    if (
      actualClassifications.length !== expectedClassifications.size ||
      !actualClassifications.every((item) => expectedClassifications.has(item)) ||
      Date.parse(value.available_at as string) > Date.parse(value.expires_at as string)
    ) {
      return false;
    }
    return true;
  }
  return (
    value.generated_scope === null &&
    value.generated_fields === null &&
    value.field_classifications === null &&
    value.row_count === null &&
    value.size_bytes === null &&
    value.sha256 === null &&
    value.available_at === null &&
    value.expires_at === null &&
    (status === "retry" || status === "failed"
      ? value.failure_code !== null
      : value.failure_code === null)
  );
}

function isDownloadIntent(value: unknown): value is ExportDownloadIntent {
  if (
    !isRecord(value) ||
    !hasExactKeys(value, ["export_job_id", "method", "url", "expires_at"]) ||
    !isUuid(value.export_job_id) ||
    value.method !== "GET" ||
    typeof value.url !== "string" ||
    value.url.length < 1 ||
    value.url.length > 4096 ||
    !isAwareDateTime(value.expires_at)
  ) {
    return false;
  }
  try {
    const parsed = new URL(value.url);
    const localHttp =
      parsed.protocol === "http:" &&
      ["localhost", "127.0.0.1", "::1", "[::1]"].includes(parsed.hostname);
    return (
      (parsed.protocol === "https:" || localHttp) &&
      parsed.username === "" &&
      parsed.password === "" &&
      parsed.hash === ""
    );
  } catch {
    return false;
  }
}

function isImportIssue(value: unknown): value is EmployeeImportIssue {
  if (
    !isRecord(value) ||
    !hasExactKeys(value, ["row_number", "severity", "code", "field", "message"]) ||
    !isNonNegativeInteger(value.row_number, 10_001) ||
    value.row_number < 1 ||
    typeof value.code !== "string"
  ) {
    return false;
  }
  const expectedMessage = IMPORT_ISSUE_MESSAGES[value.code];
  const expectedSeverity = value.code === "future_start_date" ? "warning" : "error";
  return (
    expectedMessage !== undefined &&
    value.severity === expectedSeverity &&
    (value.field === null ||
      (typeof value.field === "string" && IMPORT_FIELDS.has(value.field))) &&
    value.message === expectedMessage
  );
}

function isEmployeeImport(value: unknown): value is EmployeeImport {
  const commonValid =
    isRecord(value) &&
    hasExactKeys(value, [
      "id",
      "status",
      "template_version",
      "file_format",
      "scan_result",
      "row_count",
      "error_count",
      "warning_count",
      "committed_count",
      "failure_code",
      "issues",
      "issues_next_cursor",
      "validated_at",
      "committed_at",
      "expires_at",
      "created_at",
      "updated_at",
    ]) &&
    isUuid(value.id) &&
    IMPORT_STATUSES.includes(value.status as EmployeeImportStatus) &&
    value.template_version === "1" &&
    REPORT_FORMATS.includes(value.file_format as ReportFormat) &&
    ["pending", "clean", "infected", "error"].includes(String(value.scan_result)) &&
    isNonNegativeInteger(value.row_count, 10_000) &&
    isNonNegativeInteger(value.error_count) &&
    isNonNegativeInteger(value.warning_count) &&
    isNonNegativeInteger(value.committed_count, 10_000) &&
    (value.failure_code === null ||
      (typeof value.failure_code === "string" && IMPORT_FAILURE_CODES.has(value.failure_code))) &&
    Array.isArray(value.issues) &&
    value.issues.length <= 200 &&
    value.issues.every(isImportIssue) &&
    isNullableCursor(value.issues_next_cursor) &&
    isNullableAwareDateTime(value.validated_at) &&
    isNullableAwareDateTime(value.committed_at) &&
    isAwareDateTime(value.expires_at) &&
    isAwareDateTime(value.created_at) &&
    isAwareDateTime(value.updated_at);
  if (!commonValid) return false;

  const status = value.status as EmployeeImportStatus;
  const rowCount = value.row_count as number;
  const errorCount = value.error_count as number;
  const warningCount = value.warning_count as number;
  const committedCount = value.committed_count as number;
  if (status === "queued") {
    return (
      value.scan_result === "pending" &&
      rowCount === 0 &&
      errorCount === 0 &&
      warningCount === 0 &&
      committedCount === 0 &&
      value.failure_code === null &&
      value.validated_at === null &&
      value.committed_at === null
    );
  }
  if (status === "processing") {
    return (
      (value.scan_result === "pending" || value.scan_result === "error") &&
      committedCount === 0 &&
      value.failure_code === null &&
      value.validated_at === null &&
      value.committed_at === null
    );
  }
  if (status === "retry" || status === "failed") {
    return (
      committedCount === 0 &&
      value.failure_code !== null &&
      value.validated_at === null &&
      value.committed_at === null
    );
  }
  if (status === "ready") {
    return (
      value.scan_result === "clean" &&
      rowCount > 0 &&
      errorCount === 0 &&
      committedCount === 0 &&
      value.failure_code === null &&
      value.validated_at !== null &&
      value.committed_at === null
    );
  }
  if (status === "invalid") {
    return (
      (value.scan_result === "clean" || value.scan_result === "infected") &&
      errorCount > 0 &&
      committedCount === 0 &&
      value.validated_at !== null &&
      value.committed_at === null
    );
  }
  if (status === "succeeded") {
    return (
      value.scan_result === "clean" &&
      rowCount > 0 &&
      errorCount === 0 &&
      committedCount === rowCount &&
      value.failure_code === null &&
      value.validated_at !== null &&
      value.committed_at !== null
    );
  }
  return committedCount === 0 && value.committed_at === null;
}

function isEmployeeImportCommit(value: unknown): value is EmployeeImportCommit {
  return (
    isRecord(value) &&
    hasExactKeys(value, ["id", "status", "committed_count", "committed_at"]) &&
    isUuid(value.id) &&
    value.status === "succeeded" &&
    isNonNegativeInteger(value.committed_count, 10_000) &&
    isAwareDateTime(value.committed_at)
  );
}

function appendFilters(
  query: URLSearchParams,
  reportType: ReportType,
  filters: ReportFilters,
): void {
  for (const [key, rawValue] of Object.entries(filters)) {
    if (rawValue === null || rawValue === undefined || rawValue === "") continue;
    const queryKey = reportType === "missing_documents" && key === "statuses" ? "status" : key;
    if (typeof rawValue === "string") {
      query.set(queryKey, rawValue);
      continue;
    }
    for (const value of rawValue) {
      query.append(queryKey, value);
    }
  }
}

export async function readDashboardSummary(): Promise<DashboardSummary> {
  const response = await requestAuthenticatedApiPlainSuccess<unknown>(
    "/api/v1/dashboard/summary",
  );
  if (!isDashboardSummary(response.data)) throw invalidResponse();
  return response.data;
}

export async function readReport(
  reportType: ReportType,
  filters: ReportFilters,
  cursor: string | null = null,
  limit = 50,
): Promise<ReportPage> {
  const query = new URLSearchParams({ limit: String(limit) });
  if (cursor) query.set("cursor", cursor);
  appendFilters(query, reportType, filters);
  const path =
    reportType === "missing_documents"
      ? "/api/v1/reports/documents/missing"
      : `/api/v1/reports/${reportType}`;
  const response = await requestAuthenticatedApiEnvelope<unknown, unknown>(
    `${path}?${query.toString()}` as `/api/${string}`,
  );
  return parseReportPage(response, reportType);
}

export async function createExportJob(
  reportType: ReportType,
  format: ReportFormat,
  fields: readonly string[],
  filters: ReportFilters,
  idempotencyKey: string,
): Promise<ExportJob> {
  const data = await requestAuthenticatedApi<unknown>("/api/v1/export-jobs", {
    method: "POST",
    body: { report_type: reportType, format, fields: [...fields], filters },
    idempotencyKey,
  });
  if (!isExportJob(data)) throw invalidResponse();
  return data;
}

export async function readExportJob(jobId: string): Promise<ExportJob> {
  const data = await requestAuthenticatedApi<unknown>(
    `/api/v1/export-jobs/${encodeURIComponent(jobId)}`,
  );
  if (!isExportJob(data)) throw invalidResponse();
  return data;
}

export async function cancelExportJob(jobId: string): Promise<ExportJob> {
  const data = await requestAuthenticatedApi<unknown>(
    `/api/v1/export-jobs/${encodeURIComponent(jobId)}/cancel`,
    { method: "POST" },
  );
  if (!isExportJob(data)) throw invalidResponse();
  return data;
}

export async function createExportDownloadIntent(
  jobId: string,
): Promise<ExportDownloadIntent> {
  const data = await requestAuthenticatedApi<unknown>(
    `/api/v1/export-jobs/${encodeURIComponent(jobId)}/download-intents`,
    { method: "POST" },
  );
  if (!isDownloadIntent(data)) throw invalidResponse();
  return data;
}

export async function downloadEmployeeImportTemplate(
  format: ReportFormat,
): Promise<ApiFileSuccess> {
  const file = await requestAuthenticatedApiFile(
    `/api/v1/employees/imports/template?format=${format}&version=1`,
  );
  const expected =
    format === "csv"
      ? "text/csv"
      : "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet";
  if (file.contentType !== expected || file.blob.size <= 0 || file.blob.size > 2 * 1024 * 1024) {
    throw invalidResponse();
  }
  return file;
}

export async function uploadEmployeeImport(file: File): Promise<EmployeeImport> {
  const suffix = file.name.toLowerCase().split(".").pop();
  if (!file.name || file.size <= 0 || file.size > MAX_IMPORT_BYTES || !["csv", "xlsx"].includes(suffix ?? "")) {
    throw new ApiClientError({ status: 422, code: "reporting_validation_error" });
  }
  const form = new FormData();
  form.set("file", file, file.name);
  const data = await requestAuthenticatedApi<unknown>("/api/v1/employees/imports", {
    method: "POST",
    body: form,
  });
  if (!isEmployeeImport(data)) throw invalidResponse();
  return data;
}

export async function readEmployeeImport(
  importId: string,
  issueCursor: string | null = null,
): Promise<EmployeeImport> {
  const query = new URLSearchParams({ issue_limit: "200" });
  if (issueCursor) query.set("issue_cursor", issueCursor);
  const data = await requestAuthenticatedApi<unknown>(
    `/api/v1/employees/imports/${encodeURIComponent(importId)}?${query.toString()}`,
  );
  if (!isEmployeeImport(data)) throw invalidResponse();
  return data;
}

export async function commitEmployeeImport(
  importId: string,
  idempotencyKey: string,
): Promise<EmployeeImportCommit> {
  const data = await requestAuthenticatedApi<unknown>(
    `/api/v1/employees/imports/${encodeURIComponent(importId)}/commit`,
    { method: "POST", idempotencyKey },
  );
  if (!isEmployeeImportCommit(data)) throw invalidResponse();
  return data;
}

export function saveClientFile(file: ApiFileSuccess, fallbackName: string): void {
  const url = URL.createObjectURL(file.blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = file.filename ?? fallbackName;
  anchor.rel = "noopener";
  document.body.append(anchor);
  anchor.click();
  anchor.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 1_000);
}
