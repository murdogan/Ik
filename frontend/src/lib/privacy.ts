import { ApiClientError } from "./api-client";
import { requestAuthenticatedApiEnvelope } from "./session";

export const PRIVACY_NOTICE_STATUSES = [
  "draft",
  "published",
  "superseded",
] as const;
export const CONSENT_ACTIONS = ["grant", "withdraw"] as const;
export const RETENTION_DATA_CATEGORIES = [
  "employee_records",
  "employee_documents",
  "leave_requests",
  "audit_events",
] as const;
export const RETENTION_ANCHORS = [
  "employment_end_date",
  "archived_at",
  "created_at",
  "occurred_at",
] as const;
export const RETENTION_ACTIONS = ["review", "delete", "anonymize"] as const;
export const RETENTION_POLICY_STATUSES = ["draft", "active", "inactive"] as const;

export type PrivacyNoticeStatus = (typeof PRIVACY_NOTICE_STATUSES)[number];
export type ConsentAction = (typeof CONSENT_ACTIONS)[number];
export type RetentionDataCategory = (typeof RETENTION_DATA_CATEGORIES)[number];
export type RetentionAnchor = (typeof RETENTION_ANCHORS)[number];
export type RetentionAction = (typeof RETENTION_ACTIONS)[number];
export type RetentionPolicyStatus = (typeof RETENTION_POLICY_STATUSES)[number];

export interface PrivacyNoticeVersion {
  id: string;
  notice_kind: "employee";
  locale: string;
  notice_version: number;
  revision: number;
  title: string;
  content_hash: string;
  status: PrivacyNoticeStatus;
  published_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface PrivacyNoticeSummary extends PrivacyNoticeVersion {
  acknowledged_count: number;
  eligible_count: number;
}

export interface PrivacyNoticeDetail extends PrivacyNoticeSummary {
  body: string;
}

export interface EmployeePrivacyNoticeDetail extends PrivacyNoticeVersion {
  body: string;
}

export interface OwnPrivacyNoticeState {
  notice: EmployeePrivacyNoticeDetail | null;
  acknowledged_at: string | null;
}

export interface ConsentHistoryEvent {
  id: string;
  action: ConsentAction;
  purpose_version: number;
  occurred_at: string;
}

export interface ConsentPurposeState {
  id: string;
  code: string;
  version: number;
  title: string;
  description: string;
  is_active: boolean;
  granted: boolean;
  state_version: number;
  updated_at: string | null;
  history: ConsentHistoryEvent[];
}

export interface OwnConsentState {
  purposes: ConsentPurposeState[];
}

export interface PrivacyNoticeDraftInput {
  title: string;
  body: string;
  locale: string;
}

export interface RetentionPolicy {
  id: string;
  data_category: RetentionDataCategory;
  legal_basis_note: string;
  retention_days: number;
  anchor: RetentionAnchor;
  action: RetentionAction;
  status: RetentionPolicyStatus;
  version: number;
  created_at: string;
  updated_at: string;
}

export interface RetentionPolicyInput {
  data_category: RetentionDataCategory;
  legal_basis_note: string;
  retention_days: number;
  anchor: RetentionAnchor;
  action: RetentionAction;
  status: RetentionPolicyStatus;
}

export interface RetentionDryRunItem {
  policy_id: string;
  data_category: RetentionDataCategory;
  retention_days: number;
  anchor: RetentionAnchor;
  action: RetentionAction;
  status: RetentionPolicyStatus;
  policy_version: number;
  cutoff_at: string;
  count: number;
}

export interface RetentionDryRunResult {
  as_of: string;
  items: RetentionDryRunItem[];
}

const UUID_PATTERN =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
const SHA256_PATTERN = /^[0-9a-f]{64}$/;
const LOCALE_PATTERN = /^[A-Za-z]{2,3}(?:-(?:[A-Za-z]{2}|[A-Za-z]{4}))?$/;
const PURPOSE_CODE_PATTERN = /^[a-z][a-z0-9_]{0,63}$/;
const MAX_NOTICE_TITLE_LENGTH = 200;
const MAX_NOTICE_BODY_LENGTH = 20_000;
const MAX_PURPOSES = 20;
const MAX_PURPOSE_CODE_LENGTH = 64;
const MAX_PURPOSE_TITLE_LENGTH = 200;
const MAX_PURPOSE_DESCRIPTION_LENGTH = 1_000;
const MAX_HISTORY_EVENTS = 50;
const MANAGED_NOTICE_LIMIT = 50;
const MAX_RETENTION_POLICIES = 20;
const MAX_LEGAL_BASIS_LENGTH = 1_000;
const MAX_RETENTION_DAYS = 36_500;
const RETENTION_ANCHOR_BY_CATEGORY: Record<
  RetentionDataCategory,
  RetentionAnchor
> = {
  employee_records: "employment_end_date",
  employee_documents: "archived_at",
  leave_requests: "created_at",
  audit_events: "occurred_at",
};

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

function isNullableDateTime(value: unknown): value is string | null {
  return value === null || isAwareDateTime(value);
}

function isBoundedString(
  value: unknown,
  minimum: number,
  maximum: number,
): value is string {
  return (
    typeof value === "string" &&
    value.length >= minimum &&
    value.length <= maximum
  );
}

function isNonNegativeInteger(value: unknown): value is number {
  return typeof value === "number" && Number.isSafeInteger(value) && value >= 0;
}

function isPositiveInteger(value: unknown): value is number {
  return typeof value === "number" && Number.isSafeInteger(value) && value >= 1;
}

function isPrivacyNoticeVersion(value: unknown): value is PrivacyNoticeVersion {
  return (
    isRecord(value) &&
    hasExactKeys(value, [
      "id",
      "notice_kind",
      "locale",
      "notice_version",
      "revision",
      "title",
      "content_hash",
      "status",
      "published_at",
      "created_at",
      "updated_at",
    ]) &&
    isUuid(value.id) &&
    value.notice_kind === "employee" &&
    typeof value.locale === "string" &&
    value.locale.length <= 16 &&
    LOCALE_PATTERN.test(value.locale) &&
    isPositiveInteger(value.notice_version) &&
    isPositiveInteger(value.revision) &&
    isBoundedString(value.title, 1, MAX_NOTICE_TITLE_LENGTH) &&
    typeof value.content_hash === "string" &&
    SHA256_PATTERN.test(value.content_hash) &&
    PRIVACY_NOTICE_STATUSES.includes(value.status as PrivacyNoticeStatus) &&
    isNullableDateTime(value.published_at) &&
    ((value.status === "draft" && value.published_at === null) ||
      (value.status !== "draft" && value.published_at !== null)) &&
    isAwareDateTime(value.created_at) &&
    isAwareDateTime(value.updated_at)
  );
}

function isPrivacyNoticeSummary(value: unknown): value is PrivacyNoticeSummary {
  if (!isRecord(value)) return false;
  const { acknowledged_count, eligible_count, ...version } = value;
  return (
    hasExactKeys(value, [
      "id",
      "notice_kind",
      "locale",
      "notice_version",
      "revision",
      "title",
      "content_hash",
      "status",
      "published_at",
      "created_at",
      "updated_at",
      "acknowledged_count",
      "eligible_count",
    ]) &&
    isPrivacyNoticeVersion(version) &&
    isNonNegativeInteger(acknowledged_count) &&
    isNonNegativeInteger(eligible_count) &&
    acknowledged_count <= eligible_count
  );
}

function isEmployeePrivacyNoticeDetail(
  value: unknown,
): value is EmployeePrivacyNoticeDetail {
  if (!isRecord(value)) return false;
  const { body, ...version } = value;
  return (
    hasExactKeys(value, [
      "id",
      "notice_kind",
      "locale",
      "notice_version",
      "revision",
      "title",
      "body",
      "content_hash",
      "status",
      "published_at",
      "created_at",
      "updated_at",
    ]) &&
    isPrivacyNoticeVersion(version) &&
    isBoundedString(body, 1, MAX_NOTICE_BODY_LENGTH)
  );
}

function isPrivacyNoticeDetail(value: unknown): value is PrivacyNoticeDetail {
  if (!isRecord(value)) return false;
  const { body, ...summary } = value;
  return (
    hasExactKeys(value, [
      "id",
      "notice_kind",
      "locale",
      "notice_version",
      "revision",
      "title",
      "body",
      "content_hash",
      "status",
      "published_at",
      "created_at",
      "updated_at",
      "acknowledged_count",
      "eligible_count",
    ]) &&
    isPrivacyNoticeSummary(summary) &&
    isBoundedString(body, 1, MAX_NOTICE_BODY_LENGTH)
  );
}

function isOwnPrivacyNoticeState(value: unknown): value is OwnPrivacyNoticeState {
  return (
    isRecord(value) &&
    hasExactKeys(value, ["notice", "acknowledged_at"]) &&
    (value.notice === null || isEmployeePrivacyNoticeDetail(value.notice)) &&
    isNullableDateTime(value.acknowledged_at) &&
    (value.notice !== null || value.acknowledged_at === null)
  );
}

function isCurrentPrivacyNoticeState(value: unknown): value is OwnPrivacyNoticeState {
  return (
    isOwnPrivacyNoticeState(value) &&
    (value.notice === null || value.notice.status === "published")
  );
}

function isAcknowledgedPrivacyNoticeState(
  value: unknown,
): value is OwnPrivacyNoticeState & {
  notice: EmployeePrivacyNoticeDetail;
  acknowledged_at: string;
} {
  return (
    isOwnPrivacyNoticeState(value) &&
    value.notice !== null &&
    value.acknowledged_at !== null
  );
}

function isConsentHistoryEvent(value: unknown): value is ConsentHistoryEvent {
  return (
    isRecord(value) &&
    hasExactKeys(value, ["id", "action", "purpose_version", "occurred_at"]) &&
    isUuid(value.id) &&
    CONSENT_ACTIONS.includes(value.action as ConsentAction) &&
    isPositiveInteger(value.purpose_version) &&
    isAwareDateTime(value.occurred_at)
  );
}

function isConsentPurposeState(value: unknown): value is ConsentPurposeState {
  return (
    isRecord(value) &&
    hasExactKeys(value, [
      "id",
      "code",
      "version",
      "title",
      "description",
      "is_active",
      "granted",
      "state_version",
      "updated_at",
      "history",
    ]) &&
    isUuid(value.id) &&
    isBoundedString(value.code, 1, MAX_PURPOSE_CODE_LENGTH) &&
    PURPOSE_CODE_PATTERN.test(value.code) &&
    isPositiveInteger(value.version) &&
    isBoundedString(value.title, 1, MAX_PURPOSE_TITLE_LENGTH) &&
    isBoundedString(value.description, 1, MAX_PURPOSE_DESCRIPTION_LENGTH) &&
    typeof value.is_active === "boolean" &&
    typeof value.granted === "boolean" &&
    isNonNegativeInteger(value.state_version) &&
    isNullableDateTime(value.updated_at) &&
    Array.isArray(value.history) &&
    value.history.length <= MAX_HISTORY_EVENTS &&
    value.history.every(isConsentHistoryEvent)
  );
}

function isOwnConsentState(value: unknown): value is OwnConsentState {
  return (
    isRecord(value) &&
    hasExactKeys(value, ["purposes"]) &&
    Array.isArray(value.purposes) &&
    value.purposes.length <= MAX_PURPOSES &&
    value.purposes.every(isConsentPurposeState)
  );
}

function isRetentionPolicy(value: unknown): value is RetentionPolicy {
  return (
    isRecord(value) &&
    hasExactKeys(value, [
      "id",
      "data_category",
      "legal_basis_note",
      "retention_days",
      "anchor",
      "action",
      "status",
      "version",
      "created_at",
      "updated_at",
    ]) &&
    isUuid(value.id) &&
    RETENTION_DATA_CATEGORIES.includes(
      value.data_category as RetentionDataCategory,
    ) &&
    isBoundedString(value.legal_basis_note, 1, MAX_LEGAL_BASIS_LENGTH) &&
    isPositiveInteger(value.retention_days) &&
    Number(value.retention_days) <= MAX_RETENTION_DAYS &&
    RETENTION_ANCHORS.includes(value.anchor as RetentionAnchor) &&
    value.anchor ===
      RETENTION_ANCHOR_BY_CATEGORY[value.data_category as RetentionDataCategory] &&
    RETENTION_ACTIONS.includes(value.action as RetentionAction) &&
    RETENTION_POLICY_STATUSES.includes(value.status as RetentionPolicyStatus) &&
    isPositiveInteger(value.version) &&
    isAwareDateTime(value.created_at) &&
    isAwareDateTime(value.updated_at)
  );
}

function isRetentionDryRunItem(value: unknown): value is RetentionDryRunItem {
  return (
    isRecord(value) &&
    hasExactKeys(value, [
      "policy_id",
      "data_category",
      "retention_days",
      "anchor",
      "action",
      "status",
      "policy_version",
      "cutoff_at",
      "count",
    ]) &&
    isUuid(value.policy_id) &&
    RETENTION_DATA_CATEGORIES.includes(
      value.data_category as RetentionDataCategory,
    ) &&
    isPositiveInteger(value.retention_days) &&
    Number(value.retention_days) <= MAX_RETENTION_DAYS &&
    RETENTION_ANCHORS.includes(value.anchor as RetentionAnchor) &&
    value.anchor ===
      RETENTION_ANCHOR_BY_CATEGORY[value.data_category as RetentionDataCategory] &&
    RETENTION_ACTIONS.includes(value.action as RetentionAction) &&
    RETENTION_POLICY_STATUSES.includes(value.status as RetentionPolicyStatus) &&
    isPositiveInteger(value.policy_version) &&
    isAwareDateTime(value.cutoff_at) &&
    isNonNegativeInteger(value.count)
  );
}

function isRetentionDryRunResult(value: unknown): value is RetentionDryRunResult {
  return (
    isRecord(value) &&
    hasExactKeys(value, ["as_of", "items"]) &&
    isAwareDateTime(value.as_of) &&
    Array.isArray(value.items) &&
    value.items.length <= MAX_RETENTION_POLICIES &&
    value.items.every(isRetentionDryRunItem)
  );
}

function isResponseMeta(value: unknown): boolean {
  return (
    isRecord(value) &&
    hasExactKeys(value, ["request_id", "trace_id", "correlation_id"]) &&
    isBoundedString(value.request_id, 1, 128) &&
    isBoundedString(value.trace_id, 1, 128) &&
    value.correlation_id === value.request_id
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
  if (
    !isRecord(envelope) ||
    !hasExactKeys(envelope, ["data", "meta"]) ||
    !isResponseMeta(envelope.meta) ||
    !guard(envelope.data)
  ) {
    return invalidResponse();
  }
  return envelope.data;
}

async function readList<TValue>(
  path: `/api/${string}`,
  guard: (value: unknown) => value is TValue,
  maximum: number,
): Promise<TValue[]> {
  const envelope = await requestAuthenticatedApiEnvelope<unknown, unknown>(path);
  if (
    !isRecord(envelope) ||
    !hasExactKeys(envelope, ["data", "meta"]) ||
    !isResponseMeta(envelope.meta) ||
    !Array.isArray(envelope.data) ||
    envelope.data.length > maximum ||
    !envelope.data.every(guard)
  ) {
    return invalidResponse();
  }
  return envelope.data;
}

async function writeValidated<TValue>(
  path: `/api/${string}`,
  body: object,
  guard: (value: unknown) => value is TValue,
  idempotencyKey: string | undefined,
  method: "POST" | "PATCH" = "POST",
): Promise<TValue> {
  const envelope = await requestAuthenticatedApiEnvelope<unknown, unknown>(path, {
    method,
    body,
    idempotencyKey,
  });
  if (
    !isRecord(envelope) ||
    !hasExactKeys(envelope, ["data", "meta"]) ||
    !isResponseMeta(envelope.meta) ||
    !guard(envelope.data)
  ) {
    return invalidResponse();
  }
  return envelope.data;
}

export function readOwnPrivacyNotice(): Promise<OwnPrivacyNoticeState> {
  return readValidated("/api/v1/privacy/notice", isCurrentPrivacyNoticeState);
}

export function acknowledgeOwnPrivacyNotice(
  noticeId: string,
  noticeContentHash: string,
  idempotencyKey: string,
): Promise<OwnPrivacyNoticeState> {
  return writeValidated(
    "/api/v1/privacy/notice/acknowledge",
    { notice_id: noticeId, notice_content_hash: noticeContentHash },
    (value): value is OwnPrivacyNoticeState & {
      notice: EmployeePrivacyNoticeDetail;
      acknowledged_at: string;
    } =>
      isAcknowledgedPrivacyNoticeState(value) &&
      value.notice.id === noticeId &&
      value.notice.content_hash === noticeContentHash,
    idempotencyKey,
  );
}

export function readOwnConsentState(): Promise<OwnConsentState> {
  return readValidated("/api/v1/privacy/consents", isOwnConsentState);
}

export function transitionOwnConsent(
  purposeId: string,
  action: ConsentAction,
  idempotencyKey: string,
): Promise<ConsentPurposeState> {
  return writeValidated(
    `/api/v1/privacy/consents/${encodeURIComponent(purposeId)}/${action}`,
    {},
    (value): value is ConsentPurposeState =>
      isConsentPurposeState(value) &&
      value.id === purposeId &&
      value.granted === (action === "grant"),
    idempotencyKey,
  );
}

export function listManagedPrivacyNotices(): Promise<PrivacyNoticeSummary[]> {
  return readList(
    `/api/v1/privacy/manage/notices?limit=${MANAGED_NOTICE_LIMIT}`,
    isPrivacyNoticeSummary,
    MANAGED_NOTICE_LIMIT,
  );
}

export function readManagedPrivacyNotice(
  noticeId: string,
): Promise<PrivacyNoticeDetail> {
  return readValidated(
    `/api/v1/privacy/manage/notices/${encodeURIComponent(noticeId)}`,
    isPrivacyNoticeDetail,
  );
}

export function createPrivacyNoticeDraft(
  input: PrivacyNoticeDraftInput,
  idempotencyKey: string,
): Promise<PrivacyNoticeDetail> {
  return writeValidated(
    "/api/v1/privacy/manage/notices",
    input,
    (value): value is PrivacyNoticeDetail =>
      isPrivacyNoticeDetail(value) && value.status === "draft",
    idempotencyKey,
  );
}

export function updatePrivacyNoticeDraft(
  noticeId: string,
  expectedRevision: number,
  input: PrivacyNoticeDraftInput,
  idempotencyKey: string,
): Promise<PrivacyNoticeDetail> {
  return writeValidated(
    `/api/v1/privacy/manage/notices/${encodeURIComponent(noticeId)}`,
    { expected_revision: expectedRevision, ...input },
    (value): value is PrivacyNoticeDetail =>
      isPrivacyNoticeDetail(value) &&
      value.id === noticeId &&
      value.status === "draft",
    idempotencyKey,
    "PATCH",
  );
}

export function publishPrivacyNotice(
  noticeId: string,
  expectedRevision: number,
  idempotencyKey: string,
): Promise<PrivacyNoticeDetail> {
  return writeValidated(
    `/api/v1/privacy/manage/notices/${encodeURIComponent(noticeId)}/publish`,
    { expected_revision: expectedRevision },
    (value): value is PrivacyNoticeDetail =>
      isPrivacyNoticeDetail(value) &&
      value.id === noticeId &&
      (value.status === "published" || value.status === "superseded"),
    idempotencyKey,
  );
}

export function listRetentionPolicies(): Promise<RetentionPolicy[]> {
  return readList(
    "/api/v1/privacy/manage/retention-policies",
    isRetentionPolicy,
    MAX_RETENTION_POLICIES,
  );
}

export function createRetentionPolicy(
  input: RetentionPolicyInput,
  idempotencyKey: string,
): Promise<RetentionPolicy> {
  return writeValidated(
    "/api/v1/privacy/manage/retention-policies",
    input,
    isRetentionPolicy,
    idempotencyKey,
  );
}

export function updateRetentionPolicy(
  policyId: string,
  expectedVersion: number,
  input: RetentionPolicyInput,
  idempotencyKey: string,
): Promise<RetentionPolicy> {
  return writeValidated(
    `/api/v1/privacy/manage/retention-policies/${encodeURIComponent(policyId)}`,
    { expected_version: expectedVersion, ...input },
    (value): value is RetentionPolicy =>
      isRetentionPolicy(value) && value.id === policyId,
    idempotencyKey,
    "PATCH",
  );
}

export function runRetentionDryRun(
  policyIds: string[],
): Promise<RetentionDryRunResult> {
  return writeValidated(
    "/api/v1/privacy/manage/retention-policies/dry-run",
    { policy_ids: policyIds },
    isRetentionDryRunResult,
    undefined,
  );
}
