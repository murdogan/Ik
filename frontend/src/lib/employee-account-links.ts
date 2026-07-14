import { ApiClientError } from "./api-client";
import { requestAuthenticatedApi } from "./session";

export const ACCOUNT_MEMBERSHIP_STATUSES = [
  "invited",
  "active",
  "locked",
  "disabled",
] as const;
export const ACCOUNT_USER_STATUSES = [
  "invited",
  "active",
  "locked",
  "disabled",
] as const;

export type AccountMembershipStatus = (typeof ACCOUNT_MEMBERSHIP_STATUSES)[number];
export type AccountUserStatus = (typeof ACCOUNT_USER_STATUSES)[number];

export interface EmployeeAccountMembership {
  membership_id: string;
  full_name: string;
  email: string;
  membership_status: AccountMembershipStatus;
  user_status: AccountUserStatus;
  eligible: boolean;
}

export interface EmployeeAccountLink {
  id: string;
  membership: EmployeeAccountMembership;
  version: number;
  created_at: string;
  updated_at: string;
}

export interface EmployeeAccountLinkState {
  employee_id: string;
  link: EmployeeAccountLink | null;
}

export interface EmployeeAccountLinkPatch {
  membership_id: string | null;
  expected_version: number | null;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function hasExactKeys(value: Record<string, unknown>, keys: readonly string[]): boolean {
  const actual = Object.keys(value).sort();
  const expected = [...keys].sort();
  return actual.length === expected.length && actual.every((key, index) => key === expected[index]);
}

function isString(value: unknown): value is string {
  return typeof value === "string";
}

function isPositiveInteger(value: unknown): value is number {
  return Number.isInteger(value) && Number(value) >= 1;
}

function isAccountMembership(value: unknown): value is EmployeeAccountMembership {
  return (
    isRecord(value) &&
    hasExactKeys(value, [
      "membership_id",
      "full_name",
      "email",
      "membership_status",
      "user_status",
      "eligible",
    ]) &&
    isString(value.membership_id) &&
    isString(value.full_name) &&
    isString(value.email) &&
    isString(value.membership_status) &&
    ACCOUNT_MEMBERSHIP_STATUSES.includes(
      value.membership_status as AccountMembershipStatus,
    ) &&
    isString(value.user_status) &&
    ACCOUNT_USER_STATUSES.includes(value.user_status as AccountUserStatus) &&
    typeof value.eligible === "boolean"
  );
}

function isAccountLink(value: unknown): value is EmployeeAccountLink {
  return (
    isRecord(value) &&
    hasExactKeys(value, [
      "id",
      "membership",
      "version",
      "created_at",
      "updated_at",
    ]) &&
    isString(value.id) &&
    isAccountMembership(value.membership) &&
    isPositiveInteger(value.version) &&
    isString(value.created_at) &&
    isString(value.updated_at)
  );
}

function isAccountLinkState(
  value: unknown,
  expectedEmployeeId: string,
): value is EmployeeAccountLinkState {
  return (
    isRecord(value) &&
    hasExactKeys(value, ["employee_id", "link"]) &&
    value.employee_id === expectedEmployeeId &&
    (value.link === null || isAccountLink(value.link))
  );
}

function invalidResponse(): ApiClientError {
  return new ApiClientError({ status: 200, code: "invalid_response" });
}

export async function readEmployeeAccountLink(
  employeeId: string,
): Promise<EmployeeAccountLinkState> {
  const data = await requestAuthenticatedApi<unknown>(
    `/api/v1/employees/${encodeURIComponent(employeeId)}/account-link`,
  );
  if (!isAccountLinkState(data, employeeId)) throw invalidResponse();
  return data;
}

export async function searchEligibleEmployeeMemberships(
  employeeId: string,
  search: string,
  limit = 20,
): Promise<EmployeeAccountMembership[]> {
  const query = new URLSearchParams({
    q: search.trim(),
    limit: String(limit),
  });
  const data = await requestAuthenticatedApi<unknown>(
    `/api/v1/employees/${encodeURIComponent(employeeId)}/account-link/eligible-memberships?${query.toString()}`,
  );
  if (
    !Array.isArray(data) ||
    data.length > limit ||
    !data.every(isAccountMembership) ||
    new Set(data.map((membership) => membership.membership_id)).size !== data.length
  ) {
    throw invalidResponse();
  }
  return data;
}

export async function updateEmployeeAccountLink(
  employeeId: string,
  patch: EmployeeAccountLinkPatch,
): Promise<EmployeeAccountLinkState> {
  const data = await requestAuthenticatedApi<unknown>(
    `/api/v1/employees/${encodeURIComponent(employeeId)}/account-link`,
    { method: "PATCH", body: patch },
  );
  if (!isAccountLinkState(data, employeeId)) throw invalidResponse();
  if (
    (patch.membership_id === null && data.link !== null) ||
    (patch.membership_id !== null &&
      data.link?.membership.membership_id !== patch.membership_id)
  ) {
    throw invalidResponse();
  }
  return data;
}
