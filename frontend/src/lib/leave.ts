import {
  ApiClientError,
  type ApiRequestOptions,
} from "./api-client";
import {
  requestAuthenticatedApiPlainCursorSuccess,
  requestAuthenticatedApiPlainSuccess,
} from "./session";

export const LEAVE_REQUEST_STATUSES = [
  "pending",
  "approved",
  "rejected",
  "cancelled",
] as const;

export type LeaveRequestStatus = (typeof LEAVE_REQUEST_STATUSES)[number];

export interface LeavePolicy {
  id: string;
  leave_type_id: string;
  leave_type_code: string | null;
  leave_type_name: string | null;
  version: number;
  effective_from: string;
  effective_to: string | null;
  created_at: string;
  paid: boolean;
  document_required: boolean;
  negative_balance_allowed: boolean;
  accrual_enabled: boolean;
  accrual_days_per_month: number;
  carryover_enabled: boolean;
  carryover_limit_days: number | null;
}

export interface LeaveType {
  id: string;
  code: string;
  name: string;
  description: string | null;
  is_active: boolean;
  version: number;
  current_policy: LeavePolicy | null;
}

export interface LeaveBalance {
  id: string;
  employee_id: string;
  period_year: number;
  leave_type_id: string;
  leave_type_code: string;
  leave_type_name: string;
  earned_days: number;
  adjusted_days: number;
  used_days: number;
  planned_days: number;
  available_days: number;
  negative_balance_allowed: boolean;
}

export interface LeaveLedgerEntry {
  id: string;
  employee_id: string;
  leave_type_id: string;
  leave_type_code: string | null;
  leave_type_name: string | null;
  period_year: number;
  entry_type: string;
  amount_days: number;
  effective_date: string;
  created_at: string | null;
  reason: string | null;
}

export interface LeaveTimelineEntry {
  id: string;
  event_type: string;
  status: LeaveRequestStatus;
  actor_user_id: string;
  occurred_at: string;
}

export interface LeaveRequest {
  id: string;
  employee_id: string;
  employee_name: string | null;
  leave_type_id: string;
  leave_type_code: string;
  leave_type_name: string;
  policy_id: string;
  start_date: string;
  end_date: string;
  counted_days: number;
  status: LeaveRequestStatus;
  requested_by_user_id: string;
  decided_by_user_id: string | null;
  employee_note: string | null;
  decision_note: string | null;
  has_document: boolean;
  version: number;
  created_at: string;
  decided_at: string | null;
  timeline: LeaveTimelineEntry[];
}

export interface ApprovalTask {
  id: string;
  request: LeaveRequest;
  available_days: number;
  manager_context: string | null;
}

export interface TeamCalendarEntry {
  id: string;
  request_id: string;
  employee_id: string;
  employee_name: string;
  leave_type_code: string;
  leave_type_name: string;
  start_date: string;
  end_date: string;
  counted_days: number;
  status: LeaveRequestStatus;
}

export interface HolidayEntry {
  id: string;
  holiday_date: string;
  name: string;
  is_active: boolean;
  version: number;
}

export interface HolidayCalendar {
  id: string;
  name: string;
  is_default: boolean;
  is_active: boolean;
  non_working_weekdays: number[];
  version: number;
  entries: HolidayEntry[];
  entries_truncated: boolean;
}

export interface CursorPage<T> {
  data: T[];
  nextCursor: string | null;
}

export interface LeaveRequestCreate {
  leave_type_id: string;
  start_date: string;
  end_date: string;
  employee_note?: string;
  document_id?: string;
}

export interface LeaveTypeCreate {
  code: string;
  name: string;
  description: string | null;
}

export interface LeaveTypeUpdate {
  expected_version: number;
  name?: string;
  description?: string | null;
  is_active?: boolean;
}

export interface LeavePolicyCreate {
  leave_type_id: string;
  effective_from: string;
  paid: boolean;
  document_required: boolean;
  negative_balance_allowed: boolean;
  accrual_enabled: boolean;
  accrual_days_per_month: number;
  carryover_enabled: boolean;
  carryover_limit_days: number | null;
}

export interface HolidayCalendarCreate {
  name: string;
  is_default: boolean;
  non_working_weekdays: number[];
}

export interface HolidayCalendarUpdate {
  expected_version: number;
  name?: string;
  is_default?: boolean;
  is_active?: boolean;
  non_working_weekdays?: number[];
}

export interface HolidayEntryCreate {
  holiday_date: string;
  name: string;
}

export interface HolidayEntryUpdate {
  expected_version: number;
  name?: string;
  is_active?: boolean;
}

export interface LeaveAdjustmentCreate {
  employee_id: string;
  leave_type_id: string;
  period_year: number;
  amount_days: number;
  effective_date: string;
  reason: string;
}

type AuthenticatedOptions = Pick<
  ApiRequestOptions,
  "method" | "body" | "idempotencyKey"
>;

const UUID_PATTERN =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
const DATE_PATTERN = /^\d{4}-\d{2}-\d{2}$/;

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function isUuid(value: unknown): value is string {
  return typeof value === "string" && UUID_PATTERN.test(value);
}

function isPositiveInteger(value: unknown): value is number {
  return Number.isSafeInteger(value) && Number(value) >= 1;
}

function isYear(value: unknown): value is number {
  return Number.isSafeInteger(value) && Number(value) >= 1900 && Number(value) <= 2200;
}

function isDateOnly(value: unknown): value is string {
  if (typeof value !== "string" || !DATE_PATTERN.test(value)) return false;
  const date = new Date(`${value}T00:00:00Z`);
  return Number.isFinite(date.valueOf()) && date.toISOString().slice(0, 10) === value;
}

function isAwareDateTime(value: unknown): value is string {
  return (
    typeof value === "string" &&
    /(?:Z|[+-]\d{2}:\d{2})$/.test(value) &&
    Number.isFinite(Date.parse(value))
  );
}

function stringOrNull(value: unknown): string | null | undefined {
  if (value === undefined) return undefined;
  if (value === null) return null;
  return typeof value === "string" ? value : undefined;
}

function decimal(value: unknown): number | null {
  const parsed =
    typeof value === "number"
      ? value
      : typeof value === "string" && value.trim() !== ""
        ? Number(value)
        : Number.NaN;
  return Number.isFinite(parsed) ? parsed : null;
}

function invalidResponse(status: number, headers: Headers): ApiClientError {
  return new ApiClientError({
    status,
    code: "invalid_response",
    correlationId: headers.get("x-request-id"),
  });
}

async function readPlain<T>(
  path: `/api/${string}`,
  parser: (value: unknown) => T | null,
  options: AuthenticatedOptions = {},
): Promise<T> {
  const response = await requestAuthenticatedApiPlainSuccess<unknown>(path, options);
  const parsed = parser(response.data);
  if (parsed === null) throw invalidResponse(response.status, response.headers);
  return parsed;
}

async function readCursorPage<T>(
  path: `/api/${string}`,
  parser: (value: unknown) => T | null,
): Promise<CursorPage<T>> {
  const response = await requestAuthenticatedApiPlainCursorSuccess<unknown>(path);
  if (!Array.isArray(response.data) || response.data.length > 200) {
    throw invalidResponse(response.status, response.headers);
  }
  const parsed = response.data.map(parser);
  if (parsed.some((item) => item === null)) {
    throw invalidResponse(response.status, response.headers);
  }
  return { data: parsed as T[], nextCursor: response.nextCursor };
}

function parsePolicy(value: unknown, fallbackLeaveTypeId?: string): LeavePolicy | null {
  if (!isRecord(value)) return null;
  const leaveTypeId = isUuid(value.leave_type_id)
    ? value.leave_type_id
    : fallbackLeaveTypeId;
  const accrual = decimal(value.accrual_days_per_month);
  const carryover = decimal(value.carryover_limit_days);
  const effectiveTo = stringOrNull(value.effective_to);
  if (
    !isUuid(value.id) ||
    !leaveTypeId ||
    !isPositiveInteger(value.version) ||
    !isDateOnly(value.effective_from) ||
    effectiveTo === undefined ||
    (effectiveTo !== null && !isDateOnly(effectiveTo)) ||
    !isAwareDateTime(value.created_at) ||
    typeof value.paid !== "boolean" ||
    typeof value.document_required !== "boolean" ||
    typeof value.negative_balance_allowed !== "boolean" ||
    typeof value.accrual_enabled !== "boolean" ||
    accrual === null ||
    typeof value.carryover_enabled !== "boolean" ||
    !(value.carryover_limit_days === null || carryover !== null)
  ) {
    return null;
  }
  const code = stringOrNull(value.leave_type_code);
  const name = stringOrNull(value.leave_type_name);
  if (code === undefined || name === undefined) return null;
  return {
    id: value.id,
    leave_type_id: leaveTypeId,
    leave_type_code: code,
    leave_type_name: name,
    version: value.version,
    effective_from: value.effective_from,
    effective_to: effectiveTo,
    created_at: value.created_at,
    paid: value.paid,
    document_required: value.document_required,
    negative_balance_allowed: value.negative_balance_allowed,
    accrual_enabled: value.accrual_enabled,
    accrual_days_per_month: accrual,
    carryover_enabled: value.carryover_enabled,
    carryover_limit_days: carryover,
  };
}

function parseLeaveType(value: unknown): LeaveType | null {
  if (
    !isRecord(value) ||
    !isUuid(value.id) ||
    typeof value.code !== "string" ||
    value.code.length < 1 ||
    value.code.length > 64 ||
    typeof value.name !== "string" ||
    value.name.length < 1 ||
    typeof value.is_active !== "boolean" ||
    !isPositiveInteger(value.version)
  ) {
    return null;
  }
  const description = stringOrNull(value.description);
  if (description === undefined) return null;
  const policy =
    value.current_policy === null || value.current_policy === undefined
      ? null
      : parsePolicy(value.current_policy, value.id);
  if (value.current_policy !== null && value.current_policy !== undefined && !policy) {
    return null;
  }
  return {
    id: value.id,
    code: value.code,
    name: value.name,
    description,
    is_active: value.is_active,
    version: value.version,
    current_policy: policy,
  };
}

function parseBalance(value: unknown): LeaveBalance | null {
  if (!isRecord(value)) return null;
  const earned = decimal(value.earned_days);
  const adjusted = decimal(value.adjusted_days);
  const used = decimal(value.used_days);
  const planned = decimal(value.planned_days);
  const available = decimal(value.available_days);
  if (
    !isUuid(value.id) ||
    !isUuid(value.employee_id) ||
    !isYear(value.period_year) ||
    !isUuid(value.leave_type_id) ||
    typeof value.leave_type_code !== "string" ||
    typeof value.leave_type_name !== "string" ||
    earned === null ||
    adjusted === null ||
    used === null ||
    planned === null ||
    available === null
    || typeof value.negative_balance_allowed !== "boolean"
  ) {
    return null;
  }
  return {
    id: value.id,
    employee_id: value.employee_id,
    period_year: value.period_year,
    leave_type_id: value.leave_type_id,
    leave_type_code: value.leave_type_code,
    leave_type_name: value.leave_type_name,
    earned_days: earned,
    adjusted_days: adjusted,
    used_days: used,
    planned_days: planned,
    available_days: available,
    negative_balance_allowed: value.negative_balance_allowed,
  };
}

function parseLedgerEntry(value: unknown): LeaveLedgerEntry | null {
  if (!isRecord(value)) return null;
  const amount = decimal(value.amount_days ?? value.amount);
  const typeId = value.leave_type_id;
  const effectiveDate = value.effective_date ?? value.entry_date;
  const entryType = value.entry_type ?? value.kind;
  if (
    !isUuid(value.id) ||
    !isUuid(value.employee_id) ||
    !isUuid(typeId) ||
    !isYear(value.period_year) ||
    typeof entryType !== "string" ||
    entryType.length < 1 ||
    amount === null ||
    !isDateOnly(effectiveDate)
  ) {
    return null;
  }
  const code = stringOrNull(value.leave_type_code);
  const name = stringOrNull(value.leave_type_name);
  const reason = stringOrNull(value.reason);
  const created = stringOrNull(value.created_at);
  if (
    code === undefined ||
    name === undefined ||
    reason === undefined ||
    created === undefined ||
    (created !== null && !isAwareDateTime(created))
  ) {
    return null;
  }
  return {
    id: value.id,
    employee_id: value.employee_id,
    leave_type_id: typeId,
    leave_type_code: code,
    leave_type_name: name,
    period_year: value.period_year,
    entry_type: entryType,
    amount_days: amount,
    effective_date: effectiveDate,
    created_at: created,
    reason,
  };
}

function parseTimelineEntry(value: unknown): LeaveTimelineEntry | null {
  if (!isRecord(value)) return null;
  const eventType = value.event_type;
  const occurredAt = value.occurred_at;
  const timelineStatus = value.status;
  if (
    !isUuid(value.id) ||
    typeof eventType !== "string" ||
    typeof timelineStatus !== "string" ||
    !LEAVE_REQUEST_STATUSES.includes(timelineStatus as LeaveRequestStatus) ||
    !isUuid(value.actor_user_id) ||
    !isAwareDateTime(occurredAt)
  ) {
    return null;
  }
  return {
    id: value.id,
    event_type: eventType,
    status: timelineStatus as LeaveRequestStatus,
    actor_user_id: value.actor_user_id,
    occurred_at: occurredAt,
  };
}

function parseLeaveRequest(value: unknown): LeaveRequest | null {
  if (!isRecord(value)) return null;
  const countedDays = decimal(value.counted_days);
  const status = value.status;
  const employeeName = stringOrNull(value.employee_name);
  const employeeNote = stringOrNull(value.employee_note);
  const decisionNote = stringOrNull(value.decision_note);
  const decidedAt = stringOrNull(value.decided_at);
  const timelineValue = value.timeline ?? [];
  if (
    !isUuid(value.id) ||
    !isUuid(value.employee_id) ||
    employeeName === undefined ||
    !isUuid(value.leave_type_id) ||
    typeof (value.leave_type_code ?? value.leave_type) !== "string" ||
    typeof value.leave_type_name !== "string" ||
    !isUuid(value.policy_id) ||
    !isDateOnly(value.start_date) ||
    !isDateOnly(value.end_date) ||
    value.end_date < value.start_date ||
    countedDays === null ||
    countedDays < 0 ||
    typeof status !== "string" ||
    !LEAVE_REQUEST_STATUSES.includes(status as LeaveRequestStatus) ||
    !isUuid(value.requested_by_user_id) ||
    !(value.decided_by_user_id === null || isUuid(value.decided_by_user_id)) ||
    employeeNote === undefined ||
    decisionNote === undefined ||
    typeof value.has_document !== "boolean" ||
    !isPositiveInteger(value.version) ||
    !isAwareDateTime(value.created_at) ||
    decidedAt === undefined ||
    (decidedAt !== null && !isAwareDateTime(decidedAt)) ||
    !Array.isArray(timelineValue) ||
    timelineValue.length > 100
  ) {
    return null;
  }
  const timeline = timelineValue.map(parseTimelineEntry);
  if (timeline.some((item) => item === null)) return null;
  return {
    id: value.id,
    employee_id: value.employee_id,
    employee_name: employeeName,
    leave_type_id: value.leave_type_id,
    leave_type_code: (value.leave_type_code ?? value.leave_type) as string,
    leave_type_name: value.leave_type_name,
    policy_id: value.policy_id,
    start_date: value.start_date,
    end_date: value.end_date,
    counted_days: countedDays,
    status: status as LeaveRequestStatus,
    requested_by_user_id: value.requested_by_user_id,
    decided_by_user_id: value.decided_by_user_id,
    employee_note: employeeNote,
    decision_note: decisionNote,
    has_document: value.has_document,
    version: value.version,
    created_at: value.created_at,
    decided_at: decidedAt,
    timeline: timeline as LeaveTimelineEntry[],
  };
}

function parseApprovalTask(value: unknown): ApprovalTask | null {
  if (!isRecord(value)) return null;
  const requestValue = isRecord(value.request) ? value.request : value;
  const request = parseLeaveRequest(requestValue);
  if (!request) return null;
  const availableDays = decimal(value.available_days);
  const context = stringOrNull(value.manager_context);
  if (!isUuid(value.id) || availableDays === null || context === undefined) return null;
  return { id: value.id, request, available_days: availableDays, manager_context: context };
}

function parseCalendarEntry(value: unknown): TeamCalendarEntry | null {
  if (!isRecord(value)) return null;
  const counted = decimal(value.counted_days);
  const status = value.status;
  if (
    !isUuid(value.id) ||
    !isUuid(value.request_id) ||
    !isUuid(value.employee_id) ||
    typeof value.employee_name !== "string" ||
    typeof value.leave_type_code !== "string" ||
    typeof value.leave_type_name !== "string" ||
    !isDateOnly(value.start_date) ||
    !isDateOnly(value.end_date) ||
    counted === null ||
    status !== "approved"
  ) {
    return null;
  }
  return {
    id: value.id,
    request_id: value.request_id,
    employee_id: value.employee_id,
    employee_name: value.employee_name,
    leave_type_code: value.leave_type_code,
    leave_type_name: value.leave_type_name,
    start_date: value.start_date,
    end_date: value.end_date,
    counted_days: counted,
    status,
  };
}

function parseHolidayEntry(value: unknown): HolidayEntry | null {
  if (
    !isRecord(value) ||
    !isUuid(value.id) ||
    !isDateOnly(value.holiday_date) ||
    typeof value.name !== "string" ||
    typeof value.is_active !== "boolean" ||
    !isPositiveInteger(value.version)
  ) {
    return null;
  }
  return {
    id: value.id,
    holiday_date: value.holiday_date,
    name: value.name,
    is_active: value.is_active,
    version: value.version,
  };
}

function parseHolidayCalendar(value: unknown): HolidayCalendar | null {
  if (
    !isRecord(value) ||
    !isUuid(value.id) ||
    typeof value.name !== "string" ||
    typeof value.is_default !== "boolean" ||
    typeof value.is_active !== "boolean" ||
    !Array.isArray(value.non_working_weekdays) ||
    value.non_working_weekdays.some(
      (day) => !Number.isInteger(day) || Number(day) < 0 || Number(day) > 6,
    ) ||
    new Set(value.non_working_weekdays).size !== value.non_working_weekdays.length ||
    !isPositiveInteger(value.version) ||
    !Array.isArray(value.entries) ||
    value.entries.length > 500 ||
    typeof value.entries_truncated !== "boolean"
  ) {
    return null;
  }
  const entries = value.entries.map(parseHolidayEntry);
  if (entries.some((entry) => entry === null)) return null;
  return {
    id: value.id,
    name: value.name,
    is_default: value.is_default,
    is_active: value.is_active,
    non_working_weekdays: value.non_working_weekdays as number[],
    version: value.version,
    entries: entries as HolidayEntry[],
    entries_truncated: value.entries_truncated,
  };
}

function parseList<T>(
  value: unknown,
  parser: (item: unknown) => T | null,
  maximum = 200,
): T[] | null {
  if (!Array.isArray(value) || value.length > maximum) return null;
  const parsed = value.map(parser);
  return parsed.some((item) => item === null) ? null : (parsed as T[]);
}

export function listLeaveTypes(
  includeInactive = false,
  effectiveOn?: string,
): Promise<LeaveType[]> {
  const query = new URLSearchParams();
  if (includeInactive) query.set("include_inactive", "true");
  if (effectiveOn) query.set("effective_on", effectiveOn);
  const suffix = query.size > 0 ? `?${query.toString()}` : "";
  return readPlain(`/api/v1/leave-types${suffix}`, (value) =>
    parseList(value, parseLeaveType),
  );
}

export function createLeaveType(
  payload: LeaveTypeCreate,
  idempotencyKey: string,
): Promise<LeaveType> {
  return readPlain("/api/v1/leave-types", parseLeaveType, {
    method: "POST",
    body: payload,
    idempotencyKey,
  });
}

export function updateLeaveType(
  leaveTypeId: string,
  payload: LeaveTypeUpdate,
  idempotencyKey: string,
): Promise<LeaveType> {
  return readPlain(
    `/api/v1/leave-types/${encodeURIComponent(leaveTypeId)}`,
    parseLeaveType,
    { method: "PATCH", body: payload, idempotencyKey },
  );
}

export function listLeavePolicies(leaveTypeId?: string): Promise<LeavePolicy[]> {
  const query = new URLSearchParams();
  if (leaveTypeId) query.set("leave_type_id", leaveTypeId);
  const suffix = query.size > 0 ? `?${query.toString()}` : "";
  return readPlain(`/api/v1/leave-policies${suffix}`, (value) =>
    parseList(value, (item) => parsePolicy(item)),
  );
}

export function createLeavePolicy(
  payload: LeavePolicyCreate,
  idempotencyKey: string,
): Promise<LeavePolicy> {
  return readPlain("/api/v1/leave-policies", (value) => parsePolicy(value), {
    method: "POST",
    body: payload,
    idempotencyKey,
  });
}

export function listOwnLeaveBalances(periodYear: number): Promise<LeaveBalance[]> {
  return readPlain(
    `/api/v1/me/leave-balances?period_year=${encodeURIComponent(String(periodYear))}`,
    (value) => parseList(value, parseBalance),
  );
}

export function listOwnLeaveBalanceHistory(
  cursor?: string | null,
  limit = 25,
): Promise<CursorPage<LeaveLedgerEntry>> {
  const query = new URLSearchParams({ limit: String(limit) });
  if (cursor) query.set("cursor", cursor);
  return readCursorPage(
    `/api/v1/me/leave-balances/history?${query.toString()}`,
    parseLedgerEntry,
  );
}

export function listEmployeeLeaveBalances(
  employeeId: string,
  periodYear: number,
): Promise<LeaveBalance[]> {
  return readPlain(
    `/api/v1/employees/${encodeURIComponent(employeeId)}/leave-balances?period_year=${encodeURIComponent(String(periodYear))}`,
    (value) => parseList(value, parseBalance),
  );
}

export function listEmployeeLeaveBalanceHistory(
  employeeId: string,
  options: {
    cursor?: string | null;
    limit?: number;
    periodYear?: number;
  } = {},
): Promise<CursorPage<LeaveLedgerEntry>> {
  const query = new URLSearchParams({ limit: String(options.limit ?? 25) });
  if (options.cursor) query.set("cursor", options.cursor);
  if (options.periodYear) query.set("period_year", String(options.periodYear));
  return readCursorPage(
    `/api/v1/employees/${encodeURIComponent(employeeId)}/leave-balances/history?${query.toString()}`,
    parseLedgerEntry,
  );
}

export function listLeaveRequests(options: {
  scope: "own" | "tenant";
  status?: LeaveRequestStatus | "";
  cursor?: string | null;
  limit?: number;
}): Promise<CursorPage<LeaveRequest>> {
  const query = new URLSearchParams({
    scope: options.scope,
    limit: String(options.limit ?? 25),
  });
  if (options.status) query.set("status", options.status);
  if (options.cursor) query.set("cursor", options.cursor);
  return readCursorPage(
    `/api/v1/leave-requests?${query.toString()}`,
    parseLeaveRequest,
  );
}

export function readLeaveRequest(requestId: string): Promise<LeaveRequest> {
  return readPlain(
    `/api/v1/leave-requests/${encodeURIComponent(requestId)}`,
    parseLeaveRequest,
  );
}

export function createLeaveRequest(
  payload: LeaveRequestCreate,
  idempotencyKey: string,
): Promise<LeaveRequest> {
  return readPlain("/api/v1/leave-requests", parseLeaveRequest, {
    method: "POST",
    body: payload,
    idempotencyKey,
  });
}

function decideLeaveRequest(
  requestId: string,
  action: "approve" | "reject" | "cancel",
  expectedVersion: number,
  decisionNote: string | null,
  idempotencyKey: string,
): Promise<LeaveRequest> {
  const body: { expected_version: number; decision_note?: string } = {
    expected_version: expectedVersion,
  };
  if (decisionNote) body.decision_note = decisionNote;
  return readPlain(
    `/api/v1/leave-requests/${encodeURIComponent(requestId)}/${action}`,
    parseLeaveRequest,
    { method: "POST", body, idempotencyKey },
  );
}

export function approveLeaveRequest(
  requestId: string,
  expectedVersion: number,
  decisionNote: string | null,
  idempotencyKey: string,
): Promise<LeaveRequest> {
  return decideLeaveRequest(
    requestId,
    "approve",
    expectedVersion,
    decisionNote,
    idempotencyKey,
  );
}

export function rejectLeaveRequest(
  requestId: string,
  expectedVersion: number,
  decisionNote: string,
  idempotencyKey: string,
): Promise<LeaveRequest> {
  return decideLeaveRequest(
    requestId,
    "reject",
    expectedVersion,
    decisionNote,
    idempotencyKey,
  );
}

export function cancelLeaveRequest(
  requestId: string,
  expectedVersion: number,
  decisionNote: string | null,
  idempotencyKey: string,
): Promise<LeaveRequest> {
  return decideLeaveRequest(
    requestId,
    "cancel",
    expectedVersion,
    decisionNote,
    idempotencyKey,
  );
}

export function listApprovalTasks(options: {
  cursor?: string | null;
  limit?: number;
} = {}): Promise<CursorPage<ApprovalTask>> {
  const query = new URLSearchParams({ limit: String(options.limit ?? 25) });
  if (options.cursor) query.set("cursor", options.cursor);
  return readCursorPage(
    `/api/v1/approval-tasks?${query.toString()}`,
    parseApprovalTask,
  );
}

export function listTeamCalendar(
  startDate: string,
  endDate: string,
): Promise<TeamCalendarEntry[]> {
  const query = new URLSearchParams({ start_date: startDate, end_date: endDate });
  query.set("scope", "team");
  return readPlain(`/api/v1/team-calendar?${query.toString()}`, (value) =>
    parseList(value, parseCalendarEntry, 500),
  );
}

export function listHolidayCalendars(
  includeInactive = false,
): Promise<HolidayCalendar[]> {
  const suffix = includeInactive ? "?include_inactive=true" : "";
  return readPlain(`/api/v1/holiday-calendars${suffix}`, (value) =>
    parseList(value, parseHolidayCalendar, 100),
  );
}

export function listHolidayEntries(
  calendarId: string,
  cursor?: string | null,
): Promise<CursorPage<HolidayEntry>> {
  const query = new URLSearchParams({
    include_inactive: "true",
    limit: "200",
  });
  if (cursor) query.set("cursor", cursor);
  return readCursorPage(
    `/api/v1/holiday-calendars/${encodeURIComponent(calendarId)}/holidays?${query.toString()}`,
    parseHolidayEntry,
  );
}

export function createHolidayCalendar(
  payload: HolidayCalendarCreate,
  idempotencyKey: string,
): Promise<HolidayCalendar> {
  return readPlain("/api/v1/holiday-calendars", parseHolidayCalendar, {
    method: "POST",
    body: payload,
    idempotencyKey,
  });
}

export function updateHolidayCalendar(
  calendarId: string,
  payload: HolidayCalendarUpdate,
  idempotencyKey: string,
): Promise<HolidayCalendar> {
  return readPlain(
    `/api/v1/holiday-calendars/${encodeURIComponent(calendarId)}`,
    parseHolidayCalendar,
    { method: "PATCH", body: payload, idempotencyKey },
  );
}

export function createHolidayEntry(
  calendarId: string,
  payload: HolidayEntryCreate,
  idempotencyKey: string,
): Promise<HolidayEntry> {
  return readPlain(
    `/api/v1/holiday-calendars/${encodeURIComponent(calendarId)}/holidays`,
    parseHolidayEntry,
    { method: "POST", body: payload, idempotencyKey },
  );
}

export function updateHolidayEntry(
  calendarId: string,
  entryId: string,
  payload: HolidayEntryUpdate,
  idempotencyKey: string,
): Promise<HolidayEntry> {
  return readPlain(
    `/api/v1/holiday-calendars/${encodeURIComponent(calendarId)}/holidays/${encodeURIComponent(entryId)}`,
    parseHolidayEntry,
    { method: "PATCH", body: payload, idempotencyKey },
  );
}

export function createLeaveAdjustment(
  payload: LeaveAdjustmentCreate,
  idempotencyKey: string,
): Promise<LeaveLedgerEntry> {
  return readPlain("/api/v1/leave-adjustments", parseLedgerEntry, {
    method: "POST",
    body: payload,
    idempotencyKey,
  });
}
