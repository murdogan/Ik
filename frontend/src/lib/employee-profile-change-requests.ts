import { ApiClientError } from "./api-client";
import { EMPLOYEE_STATUSES, type EmployeeStatus } from "./employees";
import { requestAuthenticatedApiEnvelope } from "./session";

export const PROFILE_CHANGE_REQUEST_STATUSES = [
  "submitted",
  "approved",
  "rejected",
  "cancelled",
] as const;

export const PROFILE_CHANGE_FIELDS = [
  "preferred_name",
  "phone",
  "birth_date",
] as const;

export type ProfileChangeRequestStatus =
  (typeof PROFILE_CHANGE_REQUEST_STATUSES)[number];
export type ProfileChangeField = (typeof PROFILE_CHANGE_FIELDS)[number];

export interface ProfileChangeRequestCreate {
  preferred_name?: string | null;
  phone?: string | null;
  birth_date?: string | null;
}

export type OwnProfileProtectedValue =
  | {
      visibility: "masked";
      display_value: string;
    }
  | {
      visibility: "unavailable";
      display_value: null;
    };

export interface OwnPreferredNameChange {
  previous_value: string | null;
  proposed_value: string | null;
}

export interface OwnProtectedChange {
  previous_value: OwnProfileProtectedValue;
  proposed_value: OwnProfileProtectedValue;
}

export interface OwnProfileChanges {
  preferred_name: OwnPreferredNameChange | null;
  phone: OwnProtectedChange | null;
  birth_date: OwnProtectedChange | null;
}

export interface ProfileChangeRequestCommon {
  id: string;
  status: ProfileChangeRequestStatus;
  version: number;
  submitted_at: string;
  decided_at: string | null;
  cancelled_at: string | null;
  rejection_reason: string | null;
  changed_fields: ProfileChangeField[];
}

export interface OwnProfileChangeRequest extends ProfileChangeRequestCommon {
  employee_id: string;
  changes: OwnProfileChanges;
}

export interface HrProfileChangeEmployee {
  id: string;
  employee_number: string;
  first_name: string;
  last_name: string;
  email: string | null;
  status: EmployeeStatus;
}

export interface HrRawProfileChange {
  base_value: string | null;
  current_value: string | null;
  proposed_value: string | null;
  current_matches_base: boolean;
}

export interface HrRawProfileChanges {
  preferred_name: HrRawProfileChange | null;
  phone: HrRawProfileChange | null;
  birth_date: HrRawProfileChange | null;
}

export interface HrProfileChangeRequestSummary extends ProfileChangeRequestCommon {
  employee: HrProfileChangeEmployee;
  base_profile_version: number;
  current_profile_version: number;
  profile_is_stale: boolean;
}

export interface HrProfileChangeRequestDetail
  extends HrProfileChangeRequestSummary {
  changes: HrRawProfileChanges;
}

export interface ProfileChangeRequestPage<T> {
  data: T[];
  meta: {
    request_id: string;
    trace_id: string;
    correlation_id: string;
    limit: number;
    next_cursor: string | null;
  };
}

export interface ProfileChangeRequestListOptions {
  limit: number;
  cursor?: string | null;
}

export interface HrProfileChangeRequestListOptions
  extends ProfileChangeRequestListOptions {
  status: ProfileChangeRequestStatus;
}

const UUID_PATTERN =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
const DATE_ONLY_PATTERN = /^(\d{4})-(\d{2})-(\d{2})$/;
const TIMEZONE_DATETIME_PATTERN =
  /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$/;
const MASK_CHARACTER_PATTERN = /[•●·▪◦*]/u;
const CONTROL_CHARACTER_PATTERN = /[\u0000-\u001f\u007f-\u009f]/u;
const OWN_MASKED_PHONE_PATTERN = /^•{8}\d{2}$/u;
const OWN_MASKED_BIRTH_DATE_PATTERN =
  /^•{4}-(?:0[1-9]|1[0-2])-(?:0[1-9]|[12]\d|3[01])$/u;
const MAX_REJECTION_REASON_LENGTH = 500;

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

function isString(value: unknown): value is string {
  return typeof value === "string";
}

function isNullableString(value: unknown): value is string | null {
  return value === null || isString(value);
}

function isPositiveInteger(value: unknown): value is number {
  return Number.isInteger(value) && Number(value) >= 1;
}

export function isProfileChangeRequestId(value: string): boolean {
  return UUID_PATTERN.test(value);
}

export function isProfileChangeDate(value: string): boolean {
  const match = DATE_ONLY_PATTERN.exec(value);
  if (!match) return false;
  const year = Number(match[1]);
  const month = Number(match[2]);
  const day = Number(match[3]);
  const date = new Date(Date.UTC(year, month - 1, day));
  return (
    date.getUTCFullYear() === year &&
    date.getUTCMonth() === month - 1 &&
    date.getUTCDate() === day
  );
}

export function isProfileChangePhone(value: string): boolean {
  if (
    value.length < 7 ||
    value.length > 32 ||
    value !== value.trim() ||
    MASK_CHARACTER_PATTERN.test(value) ||
    !/^\+?[0-9][0-9 ()-]*[0-9]$/.test(value) ||
    !hasStructuredPhoneSeparators(value)
  ) {
    return false;
  }
  const digits = value.replace(/\D/g, "");
  return digits.length >= 7 && digits.length <= 15;
}

function hasStructuredPhoneSeparators(value: string): boolean {
  const body = value.startsWith("+") ? value.slice(1) : value;
  let parenthesized = false;
  let groupDigits = 0;
  for (let index = 0; index < body.length; index += 1) {
    const character = body[index];
    const previous = index > 0 ? body[index - 1] : null;
    const following = index + 1 < body.length ? body[index + 1] : null;
    if (/^[0-9]$/.test(character)) {
      if (parenthesized) groupDigits += 1;
      continue;
    }
    if (character === "(") {
      if (
        parenthesized ||
        following === null ||
        !/^[0-9]$/.test(following) ||
        (previous !== null && !/^[0-9 ]$/.test(previous))
      ) {
        return false;
      }
      parenthesized = true;
      groupDigits = 0;
      continue;
    }
    if (character === ")") {
      if (
        !parenthesized ||
        groupDigits === 0 ||
        (following !== null && !/^[0-9 -]$/.test(following))
      ) {
        return false;
      }
      parenthesized = false;
      continue;
    }
    if (character === " " || character === "-") {
      if (
        parenthesized ||
        previous === null ||
        following === null ||
        !/^[0-9)]$/.test(previous) ||
        !/^[0-9(]$/.test(following)
      ) {
        return false;
      }
      continue;
    }
    return false;
  }
  return !parenthesized;
}

export function containsMaskedDisplay(value: string): boolean {
  return MASK_CHARACTER_PATTERN.test(value);
}

export function normalizeProfileChangeText(value: string): string {
  return value.trim().split(/\s+/u).filter(Boolean).join(" ");
}

function isTimezoneDatetime(value: unknown): value is string {
  return (
    isString(value) &&
    TIMEZONE_DATETIME_PATTERN.test(value) &&
    Number.isFinite(Date.parse(value))
  );
}

function isStatus(value: unknown): value is ProfileChangeRequestStatus {
  return (
    isString(value) &&
    PROFILE_CHANGE_REQUEST_STATUSES.includes(
      value as ProfileChangeRequestStatus,
    )
  );
}

function isChangedFields(value: unknown): value is ProfileChangeField[] {
  return (
    Array.isArray(value) &&
    value.length >= 1 &&
    value.length <= PROFILE_CHANGE_FIELDS.length &&
    value.every(
      (field) =>
        isString(field) &&
        PROFILE_CHANGE_FIELDS.includes(field as ProfileChangeField),
    ) &&
    new Set(value).size === value.length
  );
}

function hasCoherentTerminalState(
  value: Record<string, unknown>,
  status: ProfileChangeRequestStatus,
): boolean {
  const decidedAt = value.decided_at;
  const cancelledAt = value.cancelled_at;
  const reason = value.rejection_reason;
  if (status === "submitted") {
    return decidedAt === null && cancelledAt === null && reason === null;
  }
  if (status === "approved") {
    return isTimezoneDatetime(decidedAt) && cancelledAt === null && reason === null;
  }
  if (status === "rejected") {
    return (
      isTimezoneDatetime(decidedAt) &&
      cancelledAt === null &&
      isString(reason) &&
      reason.length >= 1 &&
      reason.length <= MAX_REJECTION_REASON_LENGTH
    );
  }
  return decidedAt === null && isTimezoneDatetime(cancelledAt) && reason === null;
}

function isCommon(
  value: unknown,
  extraKeys: readonly string[],
): value is Record<string, unknown> & ProfileChangeRequestCommon {
  if (
    !isRecord(value) ||
    !hasExactKeys(value, [
      "id",
      "status",
      "version",
      "submitted_at",
      "decided_at",
      "cancelled_at",
      "rejection_reason",
      "changed_fields",
      ...extraKeys,
    ]) ||
    !isString(value.id) ||
    !isProfileChangeRequestId(value.id) ||
    !isStatus(value.status) ||
    !isPositiveInteger(value.version) ||
    !isTimezoneDatetime(value.submitted_at) ||
    !(value.decided_at === null || isTimezoneDatetime(value.decided_at)) ||
    !(value.cancelled_at === null || isTimezoneDatetime(value.cancelled_at)) ||
    !(
      value.rejection_reason === null ||
      (isString(value.rejection_reason) &&
        value.rejection_reason.length >= 1 &&
        value.rejection_reason.length <= MAX_REJECTION_REASON_LENGTH)
    ) ||
    !isChangedFields(value.changed_fields)
  ) {
    return false;
  }
  return hasCoherentTerminalState(value, value.status);
}

function isProtectedValue(
  field: "phone" | "birth_date",
  value: unknown,
): value is OwnProfileProtectedValue {
  if (
    !isRecord(value) ||
    !hasExactKeys(value, ["visibility", "display_value"])
  ) {
    return false;
  }
  if (value.visibility === "unavailable") return value.display_value === null;
  if (value.visibility !== "masked" || !isString(value.display_value)) {
    return false;
  }
  return field === "phone"
    ? OWN_MASKED_PHONE_PATTERN.test(value.display_value)
    : OWN_MASKED_BIRTH_DATE_PATTERN.test(value.display_value);
}

function isOwnPreferredChange(value: unknown): value is OwnPreferredNameChange {
  return (
    isRecord(value) &&
    hasExactKeys(value, ["previous_value", "proposed_value"]) &&
    isNullableString(value.previous_value) &&
    isNullableString(value.proposed_value) &&
    (value.previous_value === null || value.previous_value.length <= 200) &&
    (value.proposed_value === null || value.proposed_value.length <= 200)
  );
}

function isOwnProtectedChange(
  field: "phone" | "birth_date",
  value: unknown,
): value is OwnProtectedChange {
  return (
    isRecord(value) &&
    hasExactKeys(value, ["previous_value", "proposed_value"]) &&
    isProtectedValue(field, value.previous_value) &&
    isProtectedValue(field, value.proposed_value)
  );
}

function fieldsMatchChanges(
  changedFields: readonly ProfileChangeField[],
  changes: Record<ProfileChangeField, unknown>,
): boolean {
  return PROFILE_CHANGE_FIELDS.every((field) =>
    changedFields.includes(field) ? changes[field] !== null : changes[field] === null,
  );
}

function isOwnChanges(
  value: unknown,
  changedFields: readonly ProfileChangeField[],
): value is OwnProfileChanges {
  return (
    isRecord(value) &&
    hasExactKeys(value, PROFILE_CHANGE_FIELDS) &&
    (value.preferred_name === null || isOwnPreferredChange(value.preferred_name)) &&
    (value.phone === null || isOwnProtectedChange("phone", value.phone)) &&
    (value.birth_date === null ||
      isOwnProtectedChange("birth_date", value.birth_date)) &&
    fieldsMatchChanges(
      changedFields,
      value as Record<ProfileChangeField, unknown>,
    )
  );
}

function isOwnRequest(value: unknown): value is OwnProfileChangeRequest {
  return (
    isCommon(value, ["employee_id", "changes"]) &&
    isString(value.employee_id) &&
    isProfileChangeRequestId(value.employee_id) &&
    isOwnChanges(value.changes, value.changed_fields)
  );
}

function isEmployee(value: unknown): value is HrProfileChangeEmployee {
  return (
    isRecord(value) &&
    hasExactKeys(value, [
      "id",
      "employee_number",
      "first_name",
      "last_name",
      "email",
      "status",
    ]) &&
    isString(value.id) &&
    isProfileChangeRequestId(value.id) &&
    isString(value.employee_number) &&
    isString(value.first_name) &&
    isString(value.last_name) &&
    isNullableString(value.email) &&
    isString(value.status) &&
    EMPLOYEE_STATUSES.includes(value.status as EmployeeStatus)
  );
}

function isHrSummary(value: unknown): value is HrProfileChangeRequestSummary {
  if (
    !isCommon(value, [
      "employee",
      "base_profile_version",
      "current_profile_version",
      "profile_is_stale",
    ])
  ) {
    return false;
  }
  if (
    !isEmployee(value.employee) ||
    !isPositiveInteger(value.base_profile_version) ||
    !isPositiveInteger(value.current_profile_version) ||
    typeof value.profile_is_stale !== "boolean"
  ) {
    return false;
  }
  if (value.status !== "submitted") return value.profile_is_stale === false;
  return (
    value.base_profile_version === value.current_profile_version ||
    value.profile_is_stale === true
  );
}

function isRawFieldValue(field: ProfileChangeField, value: unknown): boolean {
  if (value === null) return true;
  if (!isString(value)) return false;
  if (field === "birth_date") return isProfileChangeDate(value);
  if (field === "phone") return isProfileChangePhone(value);
  return (
    value.length >= 1 &&
    value.length <= 200 &&
    !containsMaskedDisplay(value) &&
    !CONTROL_CHARACTER_PATTERN.test(value)
  );
}

function isHrRawChange(
  field: ProfileChangeField,
  value: unknown,
): value is HrRawProfileChange {
  if (
    !isRecord(value) ||
    !hasExactKeys(value, [
      "base_value",
      "current_value",
      "proposed_value",
      "current_matches_base",
    ]) ||
    !isRawFieldValue(field, value.base_value) ||
    !isRawFieldValue(field, value.current_value) ||
    !isRawFieldValue(field, value.proposed_value) ||
    typeof value.current_matches_base !== "boolean"
  ) {
    return false;
  }
  return value.current_matches_base === (value.current_value === value.base_value);
}

function isHrChanges(
  value: unknown,
  changedFields: readonly ProfileChangeField[],
): value is HrRawProfileChanges {
  if (!isRecord(value) || !hasExactKeys(value, PROFILE_CHANGE_FIELDS)) return false;
  for (const field of PROFILE_CHANGE_FIELDS) {
    const change = value[field];
    if (change !== null && !isHrRawChange(field, change)) return false;
  }
  return fieldsMatchChanges(
    changedFields,
    value as Record<ProfileChangeField, unknown>,
  );
}

function isHrDetail(value: unknown): value is HrProfileChangeRequestDetail {
  if (!isRecord(value)) return false;
  const { changes: _changes, ...summaryCandidate } = value;
  void _changes;
  const changes = value.changes;
  if (
    !isHrSummary(summaryCandidate) ||
    !isHrChanges(changes, summaryCandidate.changed_fields)
  ) {
    return false;
  }
  const selectedValueChanged = PROFILE_CHANGE_FIELDS.some((field) => {
    const change = changes[field];
    return change !== null && !change.current_matches_base;
  });
  const expectedStale =
    summaryCandidate.status === "submitted" &&
    (summaryCandidate.base_profile_version !==
      summaryCandidate.current_profile_version ||
      selectedValueChanged);
  return summaryCandidate.profile_is_stale === expectedStale;
}

function isResponseMeta(value: unknown): boolean {
  return (
    isRecord(value) &&
    hasExactKeys(value, ["request_id", "trace_id", "correlation_id"]) &&
    isString(value.request_id) &&
    value.request_id.length >= 1 &&
    isString(value.trace_id) &&
    value.trace_id.length >= 1 &&
    value.correlation_id === value.request_id
  );
}

function isPageMeta(value: unknown, expectedLimit: number): boolean {
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
      (isString(value.next_cursor) && value.next_cursor.length >= 1))
  );
}

function invalidResponse(): ApiClientError {
  return new ApiClientError({ status: 200, code: "invalid_response" });
}

function invalidRequest(): ApiClientError {
  return new ApiClientError({ status: 422, code: "invalid_change_request" });
}

function assertRequestId(requestId: string): void {
  if (!isProfileChangeRequestId(requestId)) throw invalidRequest();
}

function isCreatePayload(payload: ProfileChangeRequestCreate): boolean {
  const keys = Object.keys(payload);
  if (
    keys.length < 1 ||
    keys.length > PROFILE_CHANGE_FIELDS.length ||
    !keys.every((key) =>
      PROFILE_CHANGE_FIELDS.includes(key as ProfileChangeField),
    )
  ) {
    return false;
  }
  return keys.every((key) => {
    const field = key as ProfileChangeField;
    return isRawFieldValue(field, payload[field]);
  });
}

async function readDataEnvelope<T>(
  path: `/api/${string}`,
  validator: (value: unknown) => value is T,
  options: { method?: "GET" | "POST"; body?: object } = {},
): Promise<T> {
  const envelope = await requestAuthenticatedApiEnvelope<unknown, unknown>(
    path,
    options,
  );
  if (
    !isRecord(envelope) ||
    !hasExactKeys(envelope, ["data", "meta"]) ||
    !isResponseMeta(envelope.meta) ||
    !validator(envelope.data)
  ) {
    throw invalidResponse();
  }
  return envelope.data;
}

async function readListEnvelope<T>(
  path: `/api/${string}`,
  expectedLimit: number,
  validator: (value: unknown) => value is T,
): Promise<ProfileChangeRequestPage<T>> {
  const envelope = await requestAuthenticatedApiEnvelope<unknown, unknown>(path);
  if (
    !isRecord(envelope) ||
    !hasExactKeys(envelope, ["data", "meta"]) ||
    !Array.isArray(envelope.data) ||
    envelope.data.length > expectedLimit ||
    !envelope.data.every(validator) ||
    new Set(
      envelope.data.map((item) =>
        isRecord(item) && isString(item.id) ? item.id : "",
      ),
    ).size !== envelope.data.length ||
    !isPageMeta(envelope.meta, expectedLimit)
  ) {
    throw invalidResponse();
  }
  return envelope as unknown as ProfileChangeRequestPage<T>;
}

function listQuery(options: ProfileChangeRequestListOptions): URLSearchParams {
  if (!Number.isInteger(options.limit) || options.limit < 1 || options.limit > 100) {
    throw invalidRequest();
  }
  const query = new URLSearchParams({ limit: String(options.limit) });
  if (options.cursor) query.set("cursor", options.cursor);
  return query;
}

export async function submitOwnProfileChangeRequest(
  payload: ProfileChangeRequestCreate,
  expectedEmployeeId: string,
): Promise<OwnProfileChangeRequest> {
  if (!isCreatePayload(payload)) throw invalidRequest();
  assertRequestId(expectedEmployeeId);
  const result = await readDataEnvelope(
    "/api/v1/me/profile-change-requests",
    isOwnRequest,
    { method: "POST", body: payload },
  );
  const submittedFields = Object.keys(payload).sort();
  if (
    result.employee_id !== expectedEmployeeId ||
    result.status !== "submitted" ||
    result.changed_fields.length !== submittedFields.length ||
    [...result.changed_fields].sort().some(
      (field, index) => field !== submittedFields[index],
    )
  ) {
    throw invalidResponse();
  }
  return result;
}

export async function listOwnProfileChangeRequests(
  options: ProfileChangeRequestListOptions,
  expectedEmployeeId: string,
): Promise<ProfileChangeRequestPage<OwnProfileChangeRequest>> {
  assertRequestId(expectedEmployeeId);
  const query = listQuery(options);
  const page = await readListEnvelope(
    `/api/v1/me/profile-change-requests?${query.toString()}`,
    options.limit,
    isOwnRequest,
  );
  if (!page.data.every((request) => request.employee_id === expectedEmployeeId)) {
    throw invalidResponse();
  }
  return page;
}

export async function readOwnProfileChangeRequest(
  requestId: string,
  expectedEmployeeId: string,
): Promise<OwnProfileChangeRequest> {
  assertRequestId(requestId);
  assertRequestId(expectedEmployeeId);
  const result = await readDataEnvelope(
    `/api/v1/me/profile-change-requests/${encodeURIComponent(requestId)}`,
    isOwnRequest,
  );
  if (result.id !== requestId || result.employee_id !== expectedEmployeeId) {
    throw invalidResponse();
  }
  return result;
}

export async function cancelOwnProfileChangeRequest(
  requestId: string,
  expectedVersion: number,
  expectedEmployeeId: string,
): Promise<OwnProfileChangeRequest> {
  assertRequestId(requestId);
  assertRequestId(expectedEmployeeId);
  if (!isPositiveInteger(expectedVersion)) throw invalidRequest();
  const result = await readDataEnvelope(
    `/api/v1/me/profile-change-requests/${encodeURIComponent(requestId)}/cancel`,
    isOwnRequest,
    { method: "POST", body: { expected_version: expectedVersion } },
  );
  if (
    result.id !== requestId ||
    result.employee_id !== expectedEmployeeId ||
    result.status !== "cancelled" ||
    result.version !== expectedVersion + 1
  ) {
    throw invalidResponse();
  }
  return result;
}

export async function listHrProfileChangeRequests(
  options: HrProfileChangeRequestListOptions,
): Promise<ProfileChangeRequestPage<HrProfileChangeRequestSummary>> {
  const query = listQuery(options);
  query.set("status", options.status);
  const page = await readListEnvelope(
    `/api/v1/employee-profile-change-requests?${query.toString()}`,
    options.limit,
    isHrSummary,
  );
  if (!page.data.every((request) => request.status === options.status)) {
    throw invalidResponse();
  }
  return page;
}

export async function readHrProfileChangeRequest(
  requestId: string,
): Promise<HrProfileChangeRequestDetail> {
  assertRequestId(requestId);
  const result = await readDataEnvelope(
    `/api/v1/employee-profile-change-requests/${encodeURIComponent(requestId)}`,
    isHrDetail,
  );
  if (result.id !== requestId) throw invalidResponse();
  return result;
}

export async function approveHrProfileChangeRequest(
  requestId: string,
  expectedVersion: number,
): Promise<HrProfileChangeRequestDetail> {
  return decideHrProfileChangeRequest(
    requestId,
    expectedVersion,
    "approve",
    { expected_version: expectedVersion },
    "approved",
  );
}

export async function rejectHrProfileChangeRequest(
  requestId: string,
  expectedVersion: number,
  reason: string,
): Promise<HrProfileChangeRequestDetail> {
  const normalizedReason = normalizeProfileChangeText(reason);
  if (
    normalizedReason.length < 1 ||
    normalizedReason.length > MAX_REJECTION_REASON_LENGTH ||
    CONTROL_CHARACTER_PATTERN.test(normalizedReason)
  ) {
    throw invalidRequest();
  }
  return decideHrProfileChangeRequest(
    requestId,
    expectedVersion,
    "reject",
    { expected_version: expectedVersion, reason: normalizedReason },
    "rejected",
  );
}

async function decideHrProfileChangeRequest(
  requestId: string,
  expectedVersion: number,
  action: "approve" | "reject",
  body: { expected_version: number; reason?: string },
  expectedStatus: "approved" | "rejected",
): Promise<HrProfileChangeRequestDetail> {
  assertRequestId(requestId);
  if (!isPositiveInteger(expectedVersion)) throw invalidRequest();
  const result = await readDataEnvelope(
    `/api/v1/employee-profile-change-requests/${encodeURIComponent(requestId)}/${action}`,
    isHrDetail,
    { method: "POST", body },
  );
  if (
    result.id !== requestId ||
    result.status !== expectedStatus ||
    result.version !== expectedVersion + 1
  ) {
    throw invalidResponse();
  }
  return result;
}
