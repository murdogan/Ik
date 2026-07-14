import { ApiClientError } from "./api-client";
import {
  EMPLOYEE_STATUSES,
  type EmployeeStatus,
} from "./employees";
import {
  EMPLOYEE_CONTRACT_TYPES,
  EMPLOYEE_WORK_TYPES,
  type EmployeeContractType,
  type EmployeeWorkType,
} from "./employee-profile";
import { requestAuthenticatedApi } from "./session";

export interface SelfEmployeeProfileCore {
  id: string;
  employee_number: string;
  first_name: string;
  last_name: string;
  email: string | null;
  status: EmployeeStatus;
}

export interface SelfEmployeePersonalProfile {
  preferred_name: string | null;
  birth_date: SelfEmployeeProtectedValue;
  phone: SelfEmployeeProtectedValue;
}

export type SelfEmployeeProtectedValue =
  | {
      visibility: "masked";
      display_value: string;
    }
  | {
      visibility: "unavailable";
      display_value: null;
    };

export interface SelfEmployeeEmploymentProfile {
  employment_start_date: string;
  contract_type: EmployeeContractType | null;
  work_type: EmployeeWorkType | null;
}

export interface SelfEmployeeOrganizationReference {
  code: string;
  name: string;
}

export interface SelfEmployeePositionReference {
  code: string;
  title: string;
}

export interface SelfEmployeeCurrentAssignment {
  legal_entity: SelfEmployeeOrganizationReference;
  branch: SelfEmployeeOrganizationReference;
  department: SelfEmployeeOrganizationReference;
  position: SelfEmployeePositionReference;
  manager: { full_name: string } | null;
}

export interface SelfEmployeeProfile {
  core: SelfEmployeeProfileCore;
  personal: SelfEmployeePersonalProfile;
  employment: SelfEmployeeEmploymentProfile;
  organization: {
    current_assignment: SelfEmployeeCurrentAssignment | null;
  };
}

export type SelfEmployeeProfileResult =
  | {
      availability: "available";
      membership_id: string;
      employee_id: string;
      profile: SelfEmployeeProfile;
    }
  | {
      availability: "unavailable";
      membership_id: null;
      employee_id: null;
      profile: null;
    };

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

function isCore(value: unknown): value is SelfEmployeeProfileCore {
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
    isString(value.status) &&
    EMPLOYEE_STATUSES.includes(value.status as EmployeeStatus)
  );
}

function isPersonal(value: unknown): value is SelfEmployeePersonalProfile {
  return (
    isRecord(value) &&
    hasExactKeys(value, ["preferred_name", "birth_date", "phone"]) &&
    isNullableString(value.preferred_name) &&
    isProtectedValue(value.birth_date) &&
    isProtectedValue(value.phone)
  );
}

function isProtectedValue(value: unknown): value is SelfEmployeeProtectedValue {
  if (
    !isRecord(value) ||
    !hasExactKeys(value, ["visibility", "display_value"])
  ) {
    return false;
  }
  return value.visibility === "masked"
    ? isString(value.display_value)
    : value.visibility === "unavailable" && value.display_value === null;
}

function isEmployment(value: unknown): value is SelfEmployeeEmploymentProfile {
  return (
    isRecord(value) &&
    hasExactKeys(value, ["employment_start_date", "contract_type", "work_type"]) &&
    isString(value.employment_start_date) &&
    (value.contract_type === null ||
      (isString(value.contract_type) &&
        EMPLOYEE_CONTRACT_TYPES.includes(value.contract_type as EmployeeContractType))) &&
    (value.work_type === null ||
      (isString(value.work_type) &&
        EMPLOYEE_WORK_TYPES.includes(value.work_type as EmployeeWorkType)))
  );
}

function isOrganizationReference(
  value: unknown,
): value is SelfEmployeeOrganizationReference {
  return (
    isRecord(value) &&
    hasExactKeys(value, ["code", "name"]) &&
    isString(value.code) &&
    isString(value.name)
  );
}

function isPositionReference(
  value: unknown,
): value is SelfEmployeePositionReference {
  return (
    isRecord(value) &&
    hasExactKeys(value, ["code", "title"]) &&
    isString(value.code) &&
    isString(value.title)
  );
}

function isCurrentAssignment(
  value: unknown,
): value is SelfEmployeeCurrentAssignment {
  return (
    isRecord(value) &&
    hasExactKeys(value, [
      "legal_entity",
      "branch",
      "department",
      "position",
      "manager",
    ]) &&
    isOrganizationReference(value.legal_entity) &&
    isOrganizationReference(value.branch) &&
    isOrganizationReference(value.department) &&
    isPositionReference(value.position) &&
    (value.manager === null ||
      (isRecord(value.manager) &&
        hasExactKeys(value.manager, ["full_name"]) &&
        isString(value.manager.full_name)))
  );
}

function isProfile(value: unknown): value is SelfEmployeeProfile {
  return (
    isRecord(value) &&
    hasExactKeys(value, ["core", "personal", "employment", "organization"]) &&
    isCore(value.core) &&
    isPersonal(value.personal) &&
    isEmployment(value.employment) &&
    isRecord(value.organization) &&
    hasExactKeys(value.organization, ["current_assignment"]) &&
    (value.organization.current_assignment === null ||
      isCurrentAssignment(value.organization.current_assignment))
  );
}

function isResult(
  value: unknown,
  expectedMembershipId: string,
): value is SelfEmployeeProfileResult {
  if (
    !isRecord(value) ||
    !hasExactKeys(value, [
      "availability",
      "membership_id",
      "employee_id",
      "profile",
    ])
  ) {
    return false;
  }
  if (value.availability === "unavailable") {
    return (
      value.membership_id === null &&
      value.employee_id === null &&
      value.profile === null
    );
  }
  return (
    value.availability === "available" &&
    value.membership_id === expectedMembershipId &&
    isString(value.employee_id) &&
    isProfile(value.profile) &&
    value.profile.core.id === value.employee_id
  );
}

export function invalidSelfEmployeeProfileResponse(): ApiClientError {
  return new ApiClientError({ status: 200, code: "invalid_response" });
}

export async function readOwnEmployeeProfile(
  expectedMembershipId: string,
): Promise<SelfEmployeeProfileResult> {
  const data = await requestAuthenticatedApi<unknown>("/api/v1/me/employee-profile");
  if (!isResult(data, expectedMembershipId)) {
    throw invalidSelfEmployeeProfileResponse();
  }
  return data;
}
