import { ApiClientError } from "./api-client";
import { requestAuthenticatedApiEnvelope } from "./session";

export const DOCUMENT_REQUEST_TYPES = [
  "employment_letter",
] as const;

export const DOCUMENT_REQUEST_TYPE_LABELS: Record<DocumentRequestType, string> = {
  employment_letter: "Çalışma belgesi",
};

export const ANNOUNCEMENT_STATUSES = ["draft", "published", "archived"] as const;
export const REQUEST_KINDS = ["leave", "profile_change", "document"] as const;

export type DocumentRequestType = (typeof DOCUMENT_REQUEST_TYPES)[number];
export type DocumentRequestStatus = "submitted" | "resolved" | "rejected";
export type AnnouncementStatus = (typeof ANNOUNCEMENT_STATUSES)[number];
export type UnifiedRequestKind = (typeof REQUEST_KINDS)[number];
export type DecimalValue = number | string;

export interface UnifiedRequestTimeline {
  event_type: string;
  status: string;
  occurred_at: string;
}

export interface UnifiedRequest {
  id: string;
  kind: UnifiedRequestKind;
  status: string;
  title: string;
  requester_employee_id: string;
  requester_name: string | null;
  submitted_at: string;
  updated_at: string;
  version: number;
  start_date: string | null;
  end_date: string | null;
  counted_days: DecimalValue | null;
  changed_fields: string[];
  document_request_type: string | null;
  timeline: UnifiedRequestTimeline[];
}

export interface DocumentRequestTimeline {
  event_type: DocumentRequestStatus;
  status: DocumentRequestStatus;
  occurred_at: string;
}

export interface DocumentRequest {
  id: string;
  employee_id: string;
  employee_name: string | null;
  request_type: DocumentRequestType;
  status: DocumentRequestStatus;
  version: number;
  resolution_reason: string | null;
  decided_at: string | null;
  created_at: string;
  updated_at: string;
  timeline: DocumentRequestTimeline[];
}

export interface AnnouncementTargets {
  role_ids: string[];
  department_ids: string[];
  branch_ids: string[];
}

export interface AnnouncementSummary {
  id: string;
  title: string;
  is_critical: boolean;
  status: AnnouncementStatus;
  version: number;
  published_at: string | null;
  archived_at: string | null;
  read_at: string | null;
  acknowledged_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface AnnouncementDetail extends AnnouncementSummary {
  body: string;
  targets: AnnouncementTargets | null;
}

export interface TargetOption {
  id: string;
  label: string;
}

export interface AnnouncementTargetOptions {
  roles: TargetOption[];
  departments: TargetOption[];
  branches: TargetOption[];
}

export interface NotificationItem {
  id: string;
  notification_type: string;
  title: string;
  body: string;
  portal_path: string;
  read_at: string | null;
  version: number;
  created_at: string;
}

export interface NotificationPage {
  items: NotificationItem[];
  next_cursor: string | null;
  unread_count: number;
}

export interface NotificationReadAllResult {
  id: string;
  updated_count: number;
  has_more: boolean;
}

export interface SelfServiceWorkSummary {
  employee_id: string;
  display_name: string;
  employee_number: string;
  status: string;
  department_name: string | null;
  branch_name: string | null;
  position_title: string | null;
  employment_start_date: string;
}

export interface SelfServiceLeaveBalance {
  leave_type_id: string;
  leave_type_name: string;
  period_year: number;
  available_days: DecimalValue;
}

export interface DocumentChecklistSummary {
  missing: number;
  available: number;
  expiring: number;
  expired: number;
}

export interface SelfServiceHome {
  work: SelfServiceWorkSummary;
  leave_balances: SelfServiceLeaveBalance[];
  leave_request_path: string;
  requests_path: string;
  recent_requests: UnifiedRequest[];
  document_summary: DocumentChecklistSummary;
  announcements: AnnouncementSummary[];
  unread_notification_count: number;
  notifications: NotificationItem[];
}

export interface CursorPage<TItem> {
  items: TItem[];
  nextCursor: string | null;
}

export interface AnnouncementCreateInput {
  title: string;
  body: string;
  is_critical: boolean;
  targets: AnnouncementTargets;
}

const UUID_PATTERN =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
const DATE_PATTERN = /^\d{4}-\d{2}-\d{2}$/;

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

function isDateOnly(value: unknown): value is string {
  if (typeof value !== "string" || !DATE_PATTERN.test(value)) return false;
  const parsed = new Date(`${value}T00:00:00Z`);
  return Number.isFinite(parsed.valueOf()) && parsed.toISOString().slice(0, 10) === value;
}

function isAwareDateTime(value: unknown): value is string {
  return (
    typeof value === "string" &&
    /(?:Z|[+-]\d{2}:\d{2})$/.test(value) &&
    Number.isFinite(Date.parse(value))
  );
}

function isNullableDateTime(value: unknown): value is string | null {
  return value === null || isAwareDateTime(value);
}

function isNullableString(value: unknown): value is string | null {
  return value === null || typeof value === "string";
}

function isPositiveInteger(value: unknown): value is number {
  return Number.isSafeInteger(value) && Number(value) >= 1;
}

function isNonNegativeInteger(value: unknown): value is number {
  return Number.isSafeInteger(value) && Number(value) >= 0;
}

function isDecimal(value: unknown): value is DecimalValue {
  if (typeof value === "number") return Number.isFinite(value);
  return (
    typeof value === "string" &&
    value.trim() !== "" &&
    Number.isFinite(Number(value))
  );
}

function isStringArray(value: unknown): value is string[] {
  return Array.isArray(value) && value.length <= 50 && value.every((item) => typeof item === "string");
}

function isUuidArray(value: unknown): value is string[] {
  return (
    Array.isArray(value) &&
    value.length <= 20 &&
    value.every(isUuid) &&
    new Set(value).size === value.length
  );
}

function isTimeline(value: unknown): value is UnifiedRequestTimeline {
  return (
    isRecord(value) &&
    hasExactKeys(value, ["event_type", "status", "occurred_at"]) &&
    typeof value.event_type === "string" &&
    typeof value.status === "string" &&
    isAwareDateTime(value.occurred_at)
  );
}

function isUnifiedRequest(value: unknown): value is UnifiedRequest {
  return (
    isRecord(value) &&
    hasExactKeys(value, [
      "id",
      "kind",
      "status",
      "title",
      "requester_employee_id",
      "requester_name",
      "submitted_at",
      "updated_at",
      "version",
      "start_date",
      "end_date",
      "counted_days",
      "changed_fields",
      "document_request_type",
      "timeline",
    ]) &&
    isUuid(value.id) &&
    REQUEST_KINDS.includes(value.kind as UnifiedRequestKind) &&
    typeof value.status === "string" &&
    typeof value.title === "string" &&
    isUuid(value.requester_employee_id) &&
    isNullableString(value.requester_name) &&
    isAwareDateTime(value.submitted_at) &&
    isAwareDateTime(value.updated_at) &&
    isPositiveInteger(value.version) &&
    (value.start_date === null || isDateOnly(value.start_date)) &&
    (value.end_date === null || isDateOnly(value.end_date)) &&
    (value.counted_days === null || isDecimal(value.counted_days)) &&
    isStringArray(value.changed_fields) &&
    isNullableString(value.document_request_type) &&
    Array.isArray(value.timeline) &&
    value.timeline.length <= 50 &&
    value.timeline.every(isTimeline)
  );
}

function isDocumentRequestTimeline(value: unknown): value is DocumentRequestTimeline {
  return (
    isRecord(value) &&
    hasExactKeys(value, ["event_type", "status", "occurred_at"]) &&
    ["submitted", "resolved", "rejected"].includes(String(value.event_type)) &&
    value.status === value.event_type &&
    isAwareDateTime(value.occurred_at)
  );
}

function isDocumentRequest(value: unknown): value is DocumentRequest {
  return (
    isRecord(value) &&
    hasExactKeys(value, [
      "id",
      "employee_id",
      "employee_name",
      "request_type",
      "status",
      "version",
      "resolution_reason",
      "decided_at",
      "created_at",
      "updated_at",
      "timeline",
    ]) &&
    isUuid(value.id) &&
    isUuid(value.employee_id) &&
    isNullableString(value.employee_name) &&
    DOCUMENT_REQUEST_TYPES.includes(value.request_type as DocumentRequestType) &&
    ["submitted", "resolved", "rejected"].includes(String(value.status)) &&
    isPositiveInteger(value.version) &&
    isNullableString(value.resolution_reason) &&
    isNullableDateTime(value.decided_at) &&
    isAwareDateTime(value.created_at) &&
    isAwareDateTime(value.updated_at) &&
    Array.isArray(value.timeline) &&
    value.timeline.length <= 50 &&
    value.timeline.every(isDocumentRequestTimeline)
  );
}

function isAnnouncementTargets(value: unknown): value is AnnouncementTargets {
  return (
    isRecord(value) &&
    hasExactKeys(value, ["role_ids", "department_ids", "branch_ids"]) &&
    isUuidArray(value.role_ids) &&
    isUuidArray(value.department_ids) &&
    isUuidArray(value.branch_ids)
  );
}

function isAnnouncementSummary(value: unknown): value is AnnouncementSummary {
  return (
    isRecord(value) &&
    hasExactKeys(value, [
      "id",
      "title",
      "is_critical",
      "status",
      "version",
      "published_at",
      "archived_at",
      "read_at",
      "acknowledged_at",
      "created_at",
      "updated_at",
    ]) &&
    isUuid(value.id) &&
    typeof value.title === "string" &&
    typeof value.is_critical === "boolean" &&
    ANNOUNCEMENT_STATUSES.includes(value.status as AnnouncementStatus) &&
    isPositiveInteger(value.version) &&
    isNullableDateTime(value.published_at) &&
    isNullableDateTime(value.archived_at) &&
    isNullableDateTime(value.read_at) &&
    isNullableDateTime(value.acknowledged_at) &&
    isAwareDateTime(value.created_at) &&
    isAwareDateTime(value.updated_at)
  );
}

function isAnnouncementDetail(value: unknown): value is AnnouncementDetail {
  if (!isRecord(value)) return false;
  const { body, targets, ...summary } = value;
  return (
    hasExactKeys(value, [
      "id",
      "title",
      "is_critical",
      "status",
      "version",
      "published_at",
      "archived_at",
      "read_at",
      "acknowledged_at",
      "created_at",
      "updated_at",
      "body",
      "targets",
    ]) &&
    isAnnouncementSummary(summary) &&
    typeof body === "string" &&
    (targets === null || isAnnouncementTargets(targets))
  );
}

function isTargetOption(value: unknown): value is TargetOption {
  return (
    isRecord(value) &&
    hasExactKeys(value, ["id", "label"]) &&
    isUuid(value.id) &&
    typeof value.label === "string"
  );
}

function isTargetOptions(value: unknown): value is AnnouncementTargetOptions {
  return (
    isRecord(value) &&
    hasExactKeys(value, ["roles", "departments", "branches"]) &&
    [value.roles, value.departments, value.branches].every(
      (items) => Array.isArray(items) && items.length <= 100 && items.every(isTargetOption),
    )
  );
}

function isNotification(value: unknown): value is NotificationItem {
  return (
    isRecord(value) &&
    hasExactKeys(value, [
      "id",
      "notification_type",
      "title",
      "body",
      "portal_path",
      "read_at",
      "version",
      "created_at",
    ]) &&
    isUuid(value.id) &&
    typeof value.notification_type === "string" &&
    typeof value.title === "string" &&
    typeof value.body === "string" &&
    typeof value.portal_path === "string" &&
    value.portal_path.startsWith("/") &&
    !value.portal_path.startsWith("//") &&
    isNullableDateTime(value.read_at) &&
    isPositiveInteger(value.version) &&
    isAwareDateTime(value.created_at)
  );
}

function isNotificationPage(
  value: unknown,
  expectedLimit: number,
): value is NotificationPage {
  return (
    isRecord(value) &&
    hasExactKeys(value, ["items", "next_cursor", "unread_count"]) &&
    Array.isArray(value.items) &&
    value.items.length <= expectedLimit &&
    value.items.every(isNotification) &&
    (value.next_cursor === null ||
      (typeof value.next_cursor === "string" &&
        value.next_cursor.length >= 1 &&
        value.next_cursor.length <= 2048)) &&
    isNonNegativeInteger(value.unread_count)
  );
}

function isDocumentSummary(value: unknown): value is DocumentChecklistSummary {
  return (
    isRecord(value) &&
    hasExactKeys(value, ["missing", "available", "expiring", "expired"]) &&
    isNonNegativeInteger(value.missing) &&
    isNonNegativeInteger(value.available) &&
    isNonNegativeInteger(value.expiring) &&
    isNonNegativeInteger(value.expired)
  );
}

function isWorkSummary(value: unknown): value is SelfServiceWorkSummary {
  return (
    isRecord(value) &&
    hasExactKeys(value, [
      "employee_id",
      "display_name",
      "employee_number",
      "status",
      "department_name",
      "branch_name",
      "position_title",
      "employment_start_date",
    ]) &&
    isUuid(value.employee_id) &&
    typeof value.display_name === "string" &&
    typeof value.employee_number === "string" &&
    typeof value.status === "string" &&
    isNullableString(value.department_name) &&
    isNullableString(value.branch_name) &&
    isNullableString(value.position_title) &&
    isDateOnly(value.employment_start_date)
  );
}

function isLeaveBalance(value: unknown): value is SelfServiceLeaveBalance {
  return (
    isRecord(value) &&
    hasExactKeys(value, [
      "leave_type_id",
      "leave_type_name",
      "period_year",
      "available_days",
    ]) &&
    isUuid(value.leave_type_id) &&
    typeof value.leave_type_name === "string" &&
    Number.isSafeInteger(value.period_year) &&
    Number(value.period_year) >= 1900 &&
    isDecimal(value.available_days)
  );
}

function isSelfServiceHome(value: unknown): value is SelfServiceHome {
  return (
    isRecord(value) &&
    hasExactKeys(value, [
      "work",
      "leave_balances",
      "leave_request_path",
      "requests_path",
      "recent_requests",
      "document_summary",
      "announcements",
      "unread_notification_count",
      "notifications",
    ]) &&
    isWorkSummary(value.work) &&
    Array.isArray(value.leave_balances) &&
    value.leave_balances.length <= 100 &&
    value.leave_balances.every(isLeaveBalance) &&
    value.leave_request_path === "/leave" &&
    value.requests_path === "/requests" &&
    Array.isArray(value.recent_requests) &&
    value.recent_requests.length <= 6 &&
    value.recent_requests.every(isUnifiedRequest) &&
    isDocumentSummary(value.document_summary) &&
    Array.isArray(value.announcements) &&
    value.announcements.length <= 4 &&
    value.announcements.every(isAnnouncementSummary) &&
    isNonNegativeInteger(value.unread_notification_count) &&
    Array.isArray(value.notifications) &&
    value.notifications.length <= 5 &&
    value.notifications.every(isNotification)
  );
}

function isResponseMeta(value: unknown): boolean {
  return (
    isRecord(value) &&
    hasExactKeys(value, ["request_id", "trace_id", "correlation_id"]) &&
    typeof value.request_id === "string" &&
    value.request_id.length >= 1 &&
    value.request_id.length <= 128 &&
    typeof value.trace_id === "string" &&
    value.trace_id.length >= 1 &&
    value.trace_id.length <= 128 &&
    value.correlation_id === value.request_id
  );
}

function isPageMeta(
  value: unknown,
  expectedLimit: number,
): value is { limit: number; next_cursor: string | null } {
  if (!isRecord(value)) return false;
  const { limit: _limit, next_cursor: _cursor, ...responseMeta } = value;
  void _limit;
  void _cursor;
  return (
    isResponseMeta(responseMeta) &&
    hasExactKeys(value, [
      "request_id",
      "trace_id",
      "correlation_id",
      "limit",
      "next_cursor",
    ]) &&
    value.limit === expectedLimit &&
    (value.next_cursor === null ||
      (typeof value.next_cursor === "string" &&
        value.next_cursor.length >= 1 &&
        value.next_cursor.length <= 2048))
  );
}

function invalidResponse(): never {
  throw new ApiClientError({ status: 200, code: "invalid_response" });
}

async function readValidated<TValue>(
  path: `/api/${string}`,
  guard: (value: unknown) => value is TValue,
): Promise<TValue> {
  const envelope = await requestAuthenticatedApiEnvelope<unknown, unknown>(path);
  const data = envelope.data;
  const meta = envelope.meta;
  if (
    !isRecord(envelope) ||
    !hasExactKeys(envelope, ["data", "meta"]) ||
    !isResponseMeta(meta) ||
    !guard(data)
  ) {
    return invalidResponse();
  }
  return data;
}

async function writeValidated<TValue>(
  path: `/api/${string}`,
  body: object,
  guard: (value: unknown) => value is TValue,
  method: "POST" | "PATCH" = "POST",
  idempotencyKey: string = crypto.randomUUID(),
): Promise<TValue> {
  const envelope = await requestAuthenticatedApiEnvelope<unknown, unknown>(path, {
    method,
    body,
    idempotencyKey,
  });
  const data = envelope.data;
  const meta = envelope.meta;
  if (
    !isRecord(envelope) ||
    !hasExactKeys(envelope, ["data", "meta"]) ||
    !isResponseMeta(meta) ||
    !guard(data)
  ) {
    return invalidResponse();
  }
  return data;
}

async function readPage<TItem>(
  path: `/api/${string}`,
  guard: (value: unknown) => value is TItem,
  expectedLimit: number,
): Promise<CursorPage<TItem>> {
  const envelope = await requestAuthenticatedApiEnvelope<unknown, unknown>(path);
  const data = envelope.data;
  const meta = envelope.meta;
  if (
    !isRecord(envelope) ||
    !hasExactKeys(envelope, ["data", "meta"]) ||
    !Array.isArray(data) ||
    data.length > expectedLimit ||
    !data.every(guard) ||
    !isPageMeta(meta, expectedLimit)
  ) {
    return invalidResponse();
  }
  return { items: data, nextCursor: meta.next_cursor };
}

export function decimalNumber(value: DecimalValue): number {
  return Number(value);
}

export function readSelfServiceHome(): Promise<SelfServiceHome> {
  return readValidated("/api/v1/self-service/home", isSelfServiceHome);
}

export function listUnifiedRequests(options: {
  cursor?: string;
  kind?: UnifiedRequestKind;
  limit?: number;
} = {}): Promise<CursorPage<UnifiedRequest>> {
  const limit = options.limit ?? 30;
  const query = new URLSearchParams({ limit: String(limit) });
  if (options.cursor) query.set("cursor", options.cursor);
  if (options.kind) query.set("kind", options.kind);
  return readPage(`/api/v1/requests?${query.toString()}`, isUnifiedRequest, limit);
}

export function readUnifiedRequest(requestId: string): Promise<UnifiedRequest> {
  return readValidated(
    `/api/v1/requests/${encodeURIComponent(requestId)}`,
    isUnifiedRequest,
  );
}

export function createDocumentRequest(
  requestType: DocumentRequestType,
  idempotencyKey: string,
): Promise<DocumentRequest> {
  return writeValidated(
    "/api/v1/document-requests",
    { request_type: requestType },
    isDocumentRequest,
    "POST",
    idempotencyKey,
  );
}

export function listDocumentRequests(options: {
  scope: "own" | "hr";
  cursor?: string;
  status?: DocumentRequestStatus;
}): Promise<CursorPage<DocumentRequest>> {
  const query = new URLSearchParams({ scope: options.scope, limit: "30" });
  if (options.cursor) query.set("cursor", options.cursor);
  if (options.status) query.set("status", options.status);
  return readPage(
    `/api/v1/document-requests?${query.toString()}`,
    isDocumentRequest,
    30,
  );
}

export function decideDocumentRequest(
  requestId: string,
  action: "resolve" | "reject",
  expectedVersion: number,
  reason: string,
  idempotencyKey: string,
): Promise<DocumentRequest> {
  return writeValidated(
    `/api/v1/document-requests/${encodeURIComponent(requestId)}/${action}`,
    { expected_version: expectedVersion, reason },
    isDocumentRequest,
    "POST",
    idempotencyKey,
  );
}

export function listAnnouncements(options: {
  scope: "own" | "manage";
  cursor?: string;
  status?: AnnouncementStatus;
}): Promise<CursorPage<AnnouncementSummary>> {
  const query = new URLSearchParams({ scope: options.scope, limit: "30" });
  if (options.cursor) query.set("cursor", options.cursor);
  if (options.status) query.set("status", options.status);
  return readPage(
    `/api/v1/announcements?${query.toString()}`,
    isAnnouncementSummary,
    30,
  );
}

export function readAnnouncement(
  announcementId: string,
  scope: "own" | "manage",
): Promise<AnnouncementDetail> {
  return readValidated(
    `/api/v1/announcements/${encodeURIComponent(announcementId)}?scope=${scope}`,
    isAnnouncementDetail,
  );
}

export function readAnnouncementTargetOptions(): Promise<AnnouncementTargetOptions> {
  return readValidated("/api/v1/announcements/target-options", isTargetOptions);
}

export function createAnnouncement(
  input: AnnouncementCreateInput,
  idempotencyKey: string,
): Promise<AnnouncementDetail> {
  return writeValidated(
    "/api/v1/announcements",
    input,
    isAnnouncementDetail,
    "POST",
    idempotencyKey,
  );
}

export function updateAnnouncement(
  announcementId: string,
  expectedVersion: number,
  input: AnnouncementCreateInput,
  idempotencyKey: string,
): Promise<AnnouncementDetail> {
  return writeValidated(
    `/api/v1/announcements/${encodeURIComponent(announcementId)}`,
    { expected_version: expectedVersion, ...input },
    isAnnouncementDetail,
    "PATCH",
    idempotencyKey,
  );
}

export function actOnAnnouncement(
  announcementId: string,
  action: "publish" | "archive" | "read" | "ack",
  expectedVersion: number,
  idempotencyKey?: string,
): Promise<AnnouncementDetail> {
  return writeValidated(
    `/api/v1/announcements/${encodeURIComponent(announcementId)}/${action}`,
    { expected_version: expectedVersion },
    isAnnouncementDetail,
    "POST",
    idempotencyKey,
  );
}

export function listNotifications(options: {
  cursor?: string;
  limit?: number;
  unreadOnly?: boolean;
} = {}): Promise<NotificationPage> {
  const limit = options.limit ?? 30;
  const query = new URLSearchParams({ limit: String(limit) });
  if (options.cursor) query.set("cursor", options.cursor);
  if (options.unreadOnly) query.set("unread_only", "true");
  return readValidated(
    `/api/v1/notifications?${query.toString()}`,
    (value): value is NotificationPage => isNotificationPage(value, limit),
  );
}

export async function markNotificationRead(
  notificationId: string,
  expectedVersion: number,
): Promise<NotificationItem> {
  const item = await writeValidated(
    `/api/v1/notifications/${encodeURIComponent(notificationId)}/read`,
    { expected_version: expectedVersion },
    isNotification,
  );
  window.dispatchEvent(new Event("wf:notifications-changed"));
  return item;
}

function isReadAllResult(value: unknown): value is NotificationReadAllResult {
  return (
    isRecord(value) &&
    hasExactKeys(value, ["id", "updated_count", "has_more"]) &&
    isUuid(value.id) &&
    isNonNegativeInteger(value.updated_count) &&
    value.updated_count <= 100 &&
    typeof value.has_more === "boolean"
  );
}

export async function markAllNotificationsRead(): Promise<NotificationReadAllResult> {
  const result = await writeValidated(
    "/api/v1/notifications/read-all",
    {},
    isReadAllResult,
  );
  window.dispatchEvent(new Event("wf:notifications-changed"));
  return result;
}
