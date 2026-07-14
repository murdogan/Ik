import { ApiClientError } from "./api-client";
import { requestAuthenticatedApiPlainSuccess } from "./session";

export const EMPLOYEE_ACTIVITY_KINDS = [
  "employee.created",
  "employee.updated",
  "employee.lifecycle.changed",
  "employee.archived",
  "employee.personal_profile.updated",
  "employee.employment_profile.updated",
  "employee.account_link.changed",
  "employee.profile_change_request.submitted",
  "employee.profile_change_request.approved",
  "employee.profile_change_request.rejected",
  "employee.profile_change_request.cancelled",
  "employee.assignment.changed",
  "reporting_line.changed",
] as const;

export const EMPLOYEE_PROFILE_CHANGE_STATUSES = [
  "submitted",
  "approved",
  "rejected",
  "cancelled",
] as const;

export type EmployeeActivityKind = (typeof EMPLOYEE_ACTIVITY_KINDS)[number];
export type EmployeeProfileChangeStatus =
  (typeof EMPLOYEE_PROFILE_CHANGE_STATUSES)[number];

export interface EmployeeDocumentsInsight {
  availability: "unavailable";
}

export interface EmployeeLeaveInsight {
  period_year: number;
  remaining_balance_days: number;
  pending_request_count: number;
}

export interface EmployeeProfileChangesInsight {
  submitted_request_count: number;
  latest_status: EmployeeProfileChangeStatus | null;
  latest_submitted_at: string | null;
}

export interface EmployeeActivityItem {
  id: string;
  occurred_at: string;
  kind: EmployeeActivityKind;
}

export interface EmployeeActivityPage {
  items: EmployeeActivityItem[];
  limit: number;
  next_cursor: string | null;
}

export interface EmployeeProfileInsights {
  documents: EmployeeDocumentsInsight;
  leave: EmployeeLeaveInsight;
  profile_changes: EmployeeProfileChangesInsight;
  activity: EmployeeActivityPage;
}

interface EmployeeInsightsMeta {
  request_id: string;
  trace_id: string;
  correlation_id: string;
}

interface EmployeeInsightsEnvelope {
  data: EmployeeProfileInsights;
  meta: EmployeeInsightsMeta;
}

export interface EmployeeProfileInsightsOptions {
  limit?: number;
  cursor?: string | null;
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

function isNonNegativeInteger(value: unknown): value is number {
  return Number.isSafeInteger(value) && Number(value) >= 0;
}

function isFiniteNumber(value: unknown): value is number {
  return typeof value === "number" && Number.isFinite(value);
}

function isAwareIsoDateTime(value: unknown): value is string {
  return (
    typeof value === "string" &&
    /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$/.test(
      value,
    ) &&
    Number.isFinite(Date.parse(value))
  );
}

function isUuid(value: unknown): value is string {
  return (
    typeof value === "string" &&
    /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(
      value,
    )
  );
}

function isDocumentsInsight(value: unknown): value is EmployeeDocumentsInsight {
  return (
    isRecord(value) &&
    hasExactKeys(value, ["availability"]) &&
    value.availability === "unavailable"
  );
}

function isLeaveInsight(value: unknown): value is EmployeeLeaveInsight {
  return (
    isRecord(value) &&
    hasExactKeys(value, [
      "period_year",
      "remaining_balance_days",
      "pending_request_count",
    ]) &&
    Number.isSafeInteger(value.period_year) &&
    Number(value.period_year) >= 1900 &&
    Number(value.period_year) <= 2200 &&
    isFiniteNumber(value.remaining_balance_days) &&
    isNonNegativeInteger(value.pending_request_count)
  );
}

function isProfileChangesInsight(
  value: unknown,
): value is EmployeeProfileChangesInsight {
  return (
    isRecord(value) &&
    hasExactKeys(value, [
      "submitted_request_count",
      "latest_status",
      "latest_submitted_at",
    ]) &&
    isNonNegativeInteger(value.submitted_request_count) &&
    (value.latest_status === null ||
      (typeof value.latest_status === "string" &&
        EMPLOYEE_PROFILE_CHANGE_STATUSES.includes(
          value.latest_status as EmployeeProfileChangeStatus,
        ))) &&
    (value.latest_submitted_at === null ||
      isAwareIsoDateTime(value.latest_submitted_at)) &&
    (value.latest_status === null) === (value.latest_submitted_at === null)
  );
}

function isActivityItem(value: unknown): value is EmployeeActivityItem {
  return (
    isRecord(value) &&
    hasExactKeys(value, ["id", "occurred_at", "kind"]) &&
    isUuid(value.id) &&
    isAwareIsoDateTime(value.occurred_at) &&
    typeof value.kind === "string" &&
    EMPLOYEE_ACTIVITY_KINDS.includes(value.kind as EmployeeActivityKind)
  );
}

function isActivityPage(
  value: unknown,
  requestedLimit: number,
): value is EmployeeActivityPage {
  if (
    !isRecord(value) ||
    !hasExactKeys(value, ["items", "limit", "next_cursor"]) ||
    value.limit !== requestedLimit ||
    !Array.isArray(value.items) ||
    value.items.length > requestedLimit ||
    !value.items.every(isActivityItem) ||
    !(
      value.next_cursor === null ||
      (typeof value.next_cursor === "string" && value.next_cursor.trim() !== "")
    )
  ) {
    return false;
  }

  return new Set(value.items.map((item) => item.id)).size === value.items.length;
}

function isMeta(value: unknown): value is EmployeeInsightsMeta {
  return (
    isRecord(value) &&
    hasExactKeys(value, ["request_id", "trace_id", "correlation_id"]) &&
    typeof value.request_id === "string" &&
    typeof value.trace_id === "string" &&
    typeof value.correlation_id === "string"
  );
}

function isInsightsEnvelope(
  value: unknown,
  requestedLimit: number,
): value is EmployeeInsightsEnvelope {
  return (
    isRecord(value) &&
    hasExactKeys(value, ["data", "meta"]) &&
    isMeta(value.meta) &&
    isRecord(value.data) &&
    hasExactKeys(value.data, [
      "documents",
      "leave",
      "profile_changes",
      "activity",
    ]) &&
    isDocumentsInsight(value.data.documents) &&
    isLeaveInsight(value.data.leave) &&
    isProfileChangesInsight(value.data.profile_changes) &&
    isActivityPage(value.data.activity, requestedLimit)
  );
}

function invalidResponse(status: number, headers: Headers): ApiClientError {
  return new ApiClientError({
    status,
    code: "invalid_response",
    correlationId: headers.get("x-request-id"),
  });
}

export async function readEmployeeProfileInsights(
  employeeId: string,
  { limit = 20, cursor = null }: EmployeeProfileInsightsOptions = {},
): Promise<EmployeeProfileInsights> {
  if (!Number.isInteger(limit) || limit < 1 || limit > 50) {
    throw new RangeError("Employee insights limit must be between 1 and 50");
  }
  if (
    cursor !== null &&
    (typeof cursor !== "string" || cursor.trim() === "")
  ) {
    throw new TypeError("Employee insights cursor must not be empty");
  }

  const query = new URLSearchParams({ limit: String(limit) });
  if (cursor !== null) query.set("cursor", cursor);
  const response = await requestAuthenticatedApiPlainSuccess<unknown>(
    `/api/v1/employees/${encodeURIComponent(employeeId)}/profile/insights?${query.toString()}`,
  );
  if (!isInsightsEnvelope(response.data, limit)) {
    throw invalidResponse(response.status, response.headers);
  }
  return response.data.data;
}
