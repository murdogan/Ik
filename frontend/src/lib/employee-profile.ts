import { ApiClientError } from "./api-client";
import type { EmployeeAssignment } from "./employee-assignments";
import { EMPLOYEE_STATUSES, type EmployeeStatus } from "./employees";
import { requestAuthenticatedApi } from "./session";

export const EMPLOYEE_CONTRACT_TYPES = ["indefinite", "fixed_term"] as const;
export const EMPLOYEE_WORK_TYPES = ["full_time", "part_time"] as const;

export type EmployeeContractType = (typeof EMPLOYEE_CONTRACT_TYPES)[number];
export type EmployeeWorkType = (typeof EMPLOYEE_WORK_TYPES)[number];

export interface EmployeeProfileCore {
  id: string;
  employee_number: string;
  first_name: string;
  last_name: string;
  email: string | null;
  status: EmployeeStatus;
  employee_version: number;
}

export interface EmployeePersonalProfile {
  preferred_name: string | null;
  birth_date: string | null;
  phone: string | null;
  version: number;
}

export interface EmployeeEmploymentProfile {
  employment_start_date: string;
  contract_type: EmployeeContractType | null;
  work_type: EmployeeWorkType | null;
  version: number;
}

export interface EmployeeProfileOrganization {
  current_assignment: EmployeeAssignment | null;
  history: EmployeeAssignment[];
  history_limit: 50;
  history_truncated: boolean;
}

export interface EmployeeProfile {
  core: EmployeeProfileCore;
  personal: EmployeePersonalProfile;
  employment: EmployeeEmploymentProfile;
  organization: EmployeeProfileOrganization;
}

export interface EmployeePersonalProfileUpdate {
  expected_version: number;
  expected_employee_version?: number;
  first_name?: string;
  last_name?: string;
  email?: string | null;
  preferred_name?: string | null;
  birth_date?: string | null;
  phone?: string | null;
}

export interface EmployeeEmploymentProfileUpdate {
  expected_version: number;
  expected_employee_version?: number;
  employment_start_date?: string;
  contract_type?: EmployeeContractType | null;
  work_type?: EmployeeWorkType | null;
}

export interface EmployeePersonalProfileUpdateResult {
  core: EmployeeProfileCore;
  personal: EmployeePersonalProfile;
}

export interface EmployeeEmploymentProfileUpdateResult {
  core: EmployeeProfileCore;
  employment: EmployeeEmploymentProfile;
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

function isNullableString(value: unknown): value is string | null {
  return value === null || isString(value);
}

function isPositiveInteger(value: unknown): value is number {
  return Number.isInteger(value) && Number(value) >= 1;
}

function isProfileCore(
  value: unknown,
  expectedEmployeeId: string,
): value is EmployeeProfileCore {
  return (
    isRecord(value) &&
    hasExactKeys(value, [
      "id",
      "employee_number",
      "first_name",
      "last_name",
      "email",
      "status",
      "employee_version",
    ]) &&
    value.id === expectedEmployeeId &&
    isString(value.employee_number) &&
    isString(value.first_name) &&
    isString(value.last_name) &&
    isNullableString(value.email) &&
    isString(value.status) &&
    EMPLOYEE_STATUSES.includes(value.status as EmployeeStatus) &&
    isPositiveInteger(value.employee_version)
  );
}

function isPersonalProfile(value: unknown): value is EmployeePersonalProfile {
  return (
    isRecord(value) &&
    hasExactKeys(value, ["preferred_name", "birth_date", "phone", "version"]) &&
    isNullableString(value.preferred_name) &&
    isNullableString(value.birth_date) &&
    isNullableString(value.phone) &&
    isPositiveInteger(value.version)
  );
}

function isContractType(value: unknown): value is EmployeeContractType | null {
  return (
    value === null ||
    (isString(value) && EMPLOYEE_CONTRACT_TYPES.includes(value as EmployeeContractType))
  );
}

function isWorkType(value: unknown): value is EmployeeWorkType | null {
  return (
    value === null ||
    (isString(value) && EMPLOYEE_WORK_TYPES.includes(value as EmployeeWorkType))
  );
}

function isEmploymentProfile(value: unknown): value is EmployeeEmploymentProfile {
  return (
    isRecord(value) &&
    hasExactKeys(value, [
      "employment_start_date",
      "contract_type",
      "work_type",
      "version",
    ]) &&
    isString(value.employment_start_date) &&
    isContractType(value.contract_type) &&
    isWorkType(value.work_type) &&
    isPositiveInteger(value.version)
  );
}

function isAssignmentOrganizationSummary(value: unknown): boolean {
  return (
    isRecord(value) &&
    hasExactKeys(value, ["id", "code", "name", "status"]) &&
    isString(value.id) &&
    isString(value.code) &&
    isString(value.name) &&
    isString(value.status)
  );
}

function isAssignmentPositionSummary(value: unknown): boolean {
  return (
    isRecord(value) &&
    hasExactKeys(value, ["id", "code", "title", "status"]) &&
    isString(value.id) &&
    isString(value.code) &&
    isString(value.title) &&
    isString(value.status)
  );
}

function isAssignmentEmployeeSummary(value: unknown): boolean {
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
    isString(value.employee_number) &&
    isString(value.first_name) &&
    isString(value.last_name) &&
    isNullableString(value.email) &&
    isString(value.status)
  );
}

function isAssignmentManagerSummary(value: unknown): boolean {
  return (
    isRecord(value) &&
    hasExactKeys(value, ["id", "full_name", "email", "status"]) &&
    isString(value.id) &&
    isString(value.full_name) &&
    isNullableString(value.email) &&
    isString(value.status)
  );
}

function isEmployeeAssignment(value: unknown): value is EmployeeAssignment {
  return (
    isRecord(value) &&
    hasExactKeys(value, [
      "id",
      "employee",
      "legal_entity",
      "branch",
      "department",
      "position",
      "manager",
      "effective_from",
      "effective_to",
      "supersedes_assignment_id",
      "change_reason",
      "is_current",
      "created_at",
      "updated_at",
    ]) &&
    isString(value.id) &&
    isAssignmentEmployeeSummary(value.employee) &&
    isAssignmentOrganizationSummary(value.legal_entity) &&
    isAssignmentOrganizationSummary(value.branch) &&
    isAssignmentOrganizationSummary(value.department) &&
    isAssignmentPositionSummary(value.position) &&
    (value.manager === null || isAssignmentManagerSummary(value.manager)) &&
    isString(value.effective_from) &&
    isNullableString(value.effective_to) &&
    isNullableString(value.supersedes_assignment_id) &&
    isNullableString(value.change_reason) &&
    typeof value.is_current === "boolean" &&
    isString(value.created_at) &&
    isString(value.updated_at)
  );
}

function isOrganization(value: unknown): value is EmployeeProfileOrganization {
  return (
    isRecord(value) &&
    hasExactKeys(value, [
      "current_assignment",
      "history",
      "history_limit",
      "history_truncated",
    ]) &&
    (value.current_assignment === null || isEmployeeAssignment(value.current_assignment)) &&
    Array.isArray(value.history) &&
    value.history.length <= 50 &&
    value.history.every(isEmployeeAssignment) &&
    value.history_limit === 50 &&
    typeof value.history_truncated === "boolean"
  );
}

function isEmployeeProfile(
  value: unknown,
  expectedEmployeeId: string,
): value is EmployeeProfile {
  if (
    !isRecord(value) ||
    !hasExactKeys(value, ["core", "personal", "employment", "organization"]) ||
    !isProfileCore(value.core, expectedEmployeeId) ||
    !isPersonalProfile(value.personal) ||
    !isEmploymentProfile(value.employment) ||
    !isOrganization(value.organization)
  ) {
    return false;
  }
  return (
    (value.organization.current_assignment === null ||
      value.organization.current_assignment.employee.id === expectedEmployeeId) &&
    value.organization.history.every(
      (assignment) => assignment.employee.id === expectedEmployeeId,
    )
  );
}

function isPersonalUpdateResult(
  value: unknown,
  expectedEmployeeId: string,
): value is EmployeePersonalProfileUpdateResult {
  return (
    isRecord(value) &&
    hasExactKeys(value, ["core", "personal"]) &&
    isProfileCore(value.core, expectedEmployeeId) &&
    isPersonalProfile(value.personal)
  );
}

function isEmploymentUpdateResult(
  value: unknown,
  expectedEmployeeId: string,
): value is EmployeeEmploymentProfileUpdateResult {
  return (
    isRecord(value) &&
    hasExactKeys(value, ["core", "employment"]) &&
    isProfileCore(value.core, expectedEmployeeId) &&
    isEmploymentProfile(value.employment)
  );
}

function invalidResponse(): ApiClientError {
  return new ApiClientError({ status: 200, code: "invalid_response" });
}

export async function readEmployeeProfile(employeeId: string): Promise<EmployeeProfile> {
  const data = await requestAuthenticatedApi<unknown>(
    `/api/v1/employees/${encodeURIComponent(employeeId)}/profile`,
  );
  if (!isEmployeeProfile(data, employeeId)) throw invalidResponse();
  return data;
}

export async function updateEmployeePersonalProfile(
  employeeId: string,
  payload: EmployeePersonalProfileUpdate,
): Promise<EmployeePersonalProfileUpdateResult> {
  const data = await requestAuthenticatedApi<unknown>(
    `/api/v1/employees/${encodeURIComponent(employeeId)}/profile/personal`,
    { method: "PATCH", body: payload },
  );
  if (!isPersonalUpdateResult(data, employeeId)) throw invalidResponse();
  return data;
}

export async function updateEmployeeEmploymentProfile(
  employeeId: string,
  payload: EmployeeEmploymentProfileUpdate,
): Promise<EmployeeEmploymentProfileUpdateResult> {
  const data = await requestAuthenticatedApi<unknown>(
    `/api/v1/employees/${encodeURIComponent(employeeId)}/profile/employment`,
    { method: "PATCH", body: payload },
  );
  if (!isEmploymentUpdateResult(data, employeeId)) throw invalidResponse();
  return data;
}
