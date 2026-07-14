import { ApiClientError, type ApiSuccessEnvelope } from "./api-client";
import {
  requestAuthenticatedApi,
  requestAuthenticatedApiEnvelope,
} from "./session";

export type EmployeeLifecycleStatus = "active" | "on_leave" | "terminated";
export type AssignmentRecordStatus = "active" | "inactive" | "archived";
export type AssignmentManagerStatus = "invited" | "active" | "locked" | "disabled";

const EMPLOYEE_LIFECYCLE_STATUSES: readonly EmployeeLifecycleStatus[] = [
  "active",
  "on_leave",
  "terminated",
];

export interface AssignmentEmployeeOption {
  id: string;
  employee_number: string;
  full_name: string;
  email: string | null;
  status: EmployeeLifecycleStatus;
  current_assignment_id: string | null;
}

export interface AssignmentManagerOption {
  id: string;
  full_name: string;
  email: string | null;
}

export interface EmployeeAssignmentOptions {
  employees: AssignmentEmployeeOption[];
  managers: AssignmentManagerOption[];
}

export interface AssignmentEmployeeSummary {
  id: string;
  employee_number: string;
  first_name: string;
  last_name: string;
  email: string | null;
  status: EmployeeLifecycleStatus;
}

export interface AssignmentOrganizationSummary {
  id: string;
  code: string;
  name: string;
  status: AssignmentRecordStatus;
}

export interface AssignmentPositionSummary {
  id: string;
  code: string;
  title: string;
  status: AssignmentRecordStatus;
}

export interface AssignmentManagerSummary {
  id: string;
  full_name: string;
  email: string | null;
  status: AssignmentManagerStatus;
}

export interface EmployeeAssignment {
  id: string;
  employee: AssignmentEmployeeSummary;
  legal_entity: AssignmentOrganizationSummary;
  branch: AssignmentOrganizationSummary;
  department: AssignmentOrganizationSummary;
  position: AssignmentPositionSummary;
  manager: AssignmentManagerSummary | null;
  effective_from: string;
  effective_to: string | null;
  supersedes_assignment_id: string | null;
  change_reason: string | null;
  is_current: boolean;
  created_at: string;
  updated_at: string;
}

export interface TeamMemberEmployee {
  id: string;
  employee_number: string;
  first_name: string;
  last_name: string;
  preferred_name: string | null;
  email: string | null;
  status: EmployeeLifecycleStatus;
}

export interface TeamMemberOrganizationReference {
  code: string;
  name: string;
}

export interface TeamMemberPositionReference {
  code: string;
  title: string;
}

export interface TeamMemberAssignment {
  legal_entity: TeamMemberOrganizationReference;
  branch: TeamMemberOrganizationReference;
  department: TeamMemberOrganizationReference;
  position: TeamMemberPositionReference;
  effective_from: string;
}

export interface TeamMember {
  employee: TeamMemberEmployee;
  assignment: TeamMemberAssignment;
}

export interface EmployeeAssignmentCreateRequest {
  employee_id: string;
  legal_entity_id: string;
  branch_id: string;
  department_id: string;
  position_id: string;
  manager_id: string | null;
  effective_from: string;
  change_reason: string | null;
}

export interface EmployeeAssignmentChangeRequest {
  legal_entity_id?: string;
  branch_id?: string;
  department_id?: string;
  position_id?: string;
  manager_id?: string | null;
  effective_from: string;
  change_reason: string;
}

export interface AssignmentListMeta {
  request_id?: string;
  trace_id?: string;
  correlation_id?: string;
  limit: number;
  next_cursor: string | null;
}

function assertListEnvelope<T>(
  envelope: ApiSuccessEnvelope<T[], AssignmentListMeta>,
): void {
  if (
    !Array.isArray(envelope.data) ||
    !Number.isInteger(envelope.meta.limit) ||
    envelope.meta.limit < 1 ||
    envelope.meta.limit > 100 ||
    !(
      envelope.meta.next_cursor === null ||
      typeof envelope.meta.next_cursor === "string"
    )
  ) {
    throw new ApiClientError({ status: 200, code: "invalid_response" });
  }
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

function isTeamOrganizationReference(
  value: unknown,
): value is TeamMemberOrganizationReference {
  return (
    isRecord(value) &&
    hasExactKeys(value, ["code", "name"]) &&
    isString(value.code) &&
    isString(value.name)
  );
}

function isTeamPositionReference(
  value: unknown,
): value is TeamMemberPositionReference {
  return (
    isRecord(value) &&
    hasExactKeys(value, ["code", "title"]) &&
    isString(value.code) &&
    isString(value.title)
  );
}

function isTeamMemberEmployee(value: unknown): value is TeamMemberEmployee {
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
    isString(value.id) &&
    isString(value.employee_number) &&
    isString(value.first_name) &&
    isString(value.last_name) &&
    isNullableString(value.preferred_name) &&
    isNullableString(value.email) &&
    isString(value.status) &&
    EMPLOYEE_LIFECYCLE_STATUSES.includes(value.status as EmployeeLifecycleStatus)
  );
}

function isTeamMemberAssignment(
  value: unknown,
): value is TeamMemberAssignment {
  return (
    isRecord(value) &&
    hasExactKeys(value, [
      "legal_entity",
      "branch",
      "department",
      "position",
      "effective_from",
    ]) &&
    isTeamOrganizationReference(value.legal_entity) &&
    isTeamOrganizationReference(value.branch) &&
    isTeamOrganizationReference(value.department) &&
    isTeamPositionReference(value.position) &&
    isDateOnly(value.effective_from)
  );
}

function isTeamMember(value: unknown): value is TeamMember {
  return (
    isRecord(value) &&
    hasExactKeys(value, ["employee", "assignment"]) &&
    isTeamMemberEmployee(value.employee) &&
    isTeamMemberAssignment(value.assignment)
  );
}

export async function listEmployeeAssignmentOptions(
  search?: string,
): Promise<EmployeeAssignmentOptions> {
  const query = new URLSearchParams({ limit: "100" });
  if (search) query.set("search", search);
  const options = await requestAuthenticatedApi<EmployeeAssignmentOptions>(
    `/api/v1/employee-assignments/options?${query.toString()}`,
  );
  if (!Array.isArray(options.employees) || !Array.isArray(options.managers)) {
    throw new ApiClientError({ status: 200, code: "invalid_response" });
  }
  return options;
}

export async function listEmployeeAssignments(
  employeeId: string,
  cursor?: string,
): Promise<ApiSuccessEnvelope<EmployeeAssignment[], AssignmentListMeta>> {
  const query = new URLSearchParams({
    employee_id: employeeId,
    include_history: "true",
    limit: "50",
  });
  if (cursor) query.set("cursor", cursor);
  const envelope = await requestAuthenticatedApiEnvelope<
    EmployeeAssignment[],
    AssignmentListMeta
  >(`/api/v1/employee-assignments?${query.toString()}`);
  assertListEnvelope(envelope);
  return envelope;
}

export function createEmployeeAssignment(
  assignment: EmployeeAssignmentCreateRequest,
): Promise<EmployeeAssignment> {
  return requestAuthenticatedApi<EmployeeAssignment>(
    "/api/v1/employee-assignments",
    { method: "POST", body: assignment },
  );
}

export function changeEmployeeAssignment(
  assignmentId: string,
  change: EmployeeAssignmentChangeRequest,
): Promise<EmployeeAssignment> {
  return requestAuthenticatedApi<EmployeeAssignment>(
    `/api/v1/employee-assignments/${encodeURIComponent(assignmentId)}`,
    { method: "PATCH", body: change },
  );
}

export async function listMyTeam(
  cursor?: string,
): Promise<
  ApiSuccessEnvelope<TeamMember[], AssignmentListMeta>
> {
  const query = new URLSearchParams({ limit: "50" });
  if (cursor) query.set("cursor", cursor);
  const envelope = await requestAuthenticatedApiEnvelope<
    unknown[],
    AssignmentListMeta
  >(`/api/v1/teams/me/members?${query.toString()}`);
  assertListEnvelope(envelope);
  if (
    !envelope.data.every(isTeamMember) ||
    new Set(envelope.data.map((item) => item.employee.id)).size !==
      envelope.data.length
  ) {
    throw new ApiClientError({ status: 200, code: "invalid_response" });
  }
  return envelope as ApiSuccessEnvelope<TeamMember[], AssignmentListMeta>;
}
