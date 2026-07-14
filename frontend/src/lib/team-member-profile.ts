import { ApiClientError } from "./api-client";
import {
  EMPLOYEE_CONTRACT_TYPES,
  EMPLOYEE_WORK_TYPES,
  type EmployeeContractType,
  type EmployeeWorkType,
} from "./employee-profile";
import { EMPLOYEE_STATUSES, type EmployeeStatus } from "./employees";
import { requestAuthenticatedApi } from "./session";

export interface TeamMemberProfileCore {
  id: string;
  employee_number: string;
  first_name: string;
  last_name: string;
  preferred_name: string | null;
  email: string | null;
  status: EmployeeStatus;
}

export interface TeamMemberProfileEmployment {
  employment_start_date: string;
  contract_type: EmployeeContractType | null;
  work_type: EmployeeWorkType | null;
}

export interface TeamMemberProfileOrganizationReference {
  code: string;
  name: string;
}

export interface TeamMemberProfilePositionReference {
  code: string;
  title: string;
}

export interface TeamMemberProfileCurrentAssignment {
  legal_entity: TeamMemberProfileOrganizationReference;
  branch: TeamMemberProfileOrganizationReference;
  department: TeamMemberProfileOrganizationReference;
  position: TeamMemberProfilePositionReference;
  manager: { full_name: string } | null;
  effective_from: string;
}

export interface TeamMemberProfile {
  core: TeamMemberProfileCore;
  employment: TeamMemberProfileEmployment;
  organization: {
    current_assignment: TeamMemberProfileCurrentAssignment | null;
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

function isString(value: unknown): value is string {
  return typeof value === "string";
}

function isNullableString(value: unknown): value is string | null {
  return value === null || isString(value);
}

function isDateOnly(value: unknown): value is string {
  return isString(value) && /^\d{4}-\d{2}-\d{2}$/.test(value);
}

function isCore(
  value: unknown,
  expectedEmployeeId: string,
): value is TeamMemberProfileCore {
  return (
    isRecord(value) &&
    hasExactKeys(value, [
      "id",
      "employee_number",
      "first_name",
      "last_name",
      "preferred_name",
      "email",
      "status",
    ]) &&
    value.id === expectedEmployeeId &&
    isString(value.employee_number) &&
    isString(value.first_name) &&
    isString(value.last_name) &&
    isNullableString(value.preferred_name) &&
    isNullableString(value.email) &&
    isString(value.status) &&
    EMPLOYEE_STATUSES.includes(value.status as EmployeeStatus)
  );
}

function isEmployment(value: unknown): value is TeamMemberProfileEmployment {
  return (
    isRecord(value) &&
    hasExactKeys(value, [
      "employment_start_date",
      "contract_type",
      "work_type",
    ]) &&
    isDateOnly(value.employment_start_date) &&
    (value.contract_type === null ||
      (isString(value.contract_type) &&
        EMPLOYEE_CONTRACT_TYPES.includes(
          value.contract_type as EmployeeContractType,
        ))) &&
    (value.work_type === null ||
      (isString(value.work_type) &&
        EMPLOYEE_WORK_TYPES.includes(value.work_type as EmployeeWorkType)))
  );
}

function isOrganizationReference(
  value: unknown,
): value is TeamMemberProfileOrganizationReference {
  return (
    isRecord(value) &&
    hasExactKeys(value, ["code", "name"]) &&
    isString(value.code) &&
    isString(value.name)
  );
}

function isPositionReference(
  value: unknown,
): value is TeamMemberProfilePositionReference {
  return (
    isRecord(value) &&
    hasExactKeys(value, ["code", "title"]) &&
    isString(value.code) &&
    isString(value.title)
  );
}

function isCurrentAssignment(
  value: unknown,
): value is TeamMemberProfileCurrentAssignment {
  return (
    isRecord(value) &&
    hasExactKeys(value, [
      "legal_entity",
      "branch",
      "department",
      "position",
      "manager",
      "effective_from",
    ]) &&
    isOrganizationReference(value.legal_entity) &&
    isOrganizationReference(value.branch) &&
    isOrganizationReference(value.department) &&
    isPositionReference(value.position) &&
    (value.manager === null ||
      (isRecord(value.manager) &&
        hasExactKeys(value.manager, ["full_name"]) &&
        isString(value.manager.full_name))) &&
    isDateOnly(value.effective_from)
  );
}

function isProfile(
  value: unknown,
  expectedEmployeeId: string,
): value is TeamMemberProfile {
  return (
    isRecord(value) &&
    hasExactKeys(value, ["core", "employment", "organization"]) &&
    isCore(value.core, expectedEmployeeId) &&
    isEmployment(value.employment) &&
    isRecord(value.organization) &&
    hasExactKeys(value.organization, ["current_assignment"]) &&
    (value.organization.current_assignment === null ||
      isCurrentAssignment(value.organization.current_assignment))
  );
}

function invalidResponse(): ApiClientError {
  return new ApiClientError({ status: 200, code: "invalid_response" });
}

export async function readTeamMemberProfile(
  employeeId: string,
): Promise<TeamMemberProfile> {
  const data = await requestAuthenticatedApi<unknown>(
    `/api/v1/teams/me/members/${encodeURIComponent(employeeId)}/profile`,
  );
  if (!isProfile(data, employeeId)) throw invalidResponse();
  return data;
}
