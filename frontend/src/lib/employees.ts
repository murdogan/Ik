import { ApiClientError } from "./api-client";
import {
  requestAuthenticatedApiPlainCursorSuccess,
  requestAuthenticatedApiPlainSuccess,
} from "./session";

export const EMPLOYEE_STATUSES = ["active", "on_leave", "terminated"] as const;
export const EMPLOYEE_CREATE_STATUSES = ["active", "on_leave"] as const;

export type EmployeeStatus = (typeof EMPLOYEE_STATUSES)[number];
export type EmployeeCreateStatus = (typeof EMPLOYEE_CREATE_STATUSES)[number];

export interface EmployeeOrganizationReference {
  id: string;
  code: string;
  name: string;
}

export interface EmployeePositionReference {
  id: string;
  code: string;
  title: string;
}

export interface EmployeeCurrentAssignment {
  id: string;
  legal_entity: EmployeeOrganizationReference;
  branch: EmployeeOrganizationReference;
  department: EmployeeOrganizationReference;
  position: EmployeePositionReference;
  effective_from: string;
}

export interface Employee {
  id: string;
  employee_number: string;
  first_name: string;
  last_name: string;
  email: string | null;
  department: string | null;
  position: string | null;
  status: EmployeeStatus;
  employment_start_date: string;
  employment_end_date: string | null;
  version: number;
  current_assignment: EmployeeCurrentAssignment | null;
}

export interface EmployeeListOptions {
  q?: string;
  status?: EmployeeStatus | "";
  legalEntityId?: string;
  branchId?: string;
  departmentId?: string;
  positionId?: string;
  limit: number;
  cursor?: string | null;
}

export interface EmployeeListPage {
  data: Employee[];
  meta: {
    limit: number;
    next_cursor: string | null;
  };
}

export interface EmployeeCreateRequest {
  employee_number: string;
  first_name: string;
  last_name: string;
  email: string | null;
  status: EmployeeCreateStatus;
  employment_start_date: string;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function isString(value: unknown): value is string {
  return typeof value === "string";
}

function isNullableString(value: unknown): value is string | null {
  return value === null || isString(value);
}

function isOrganizationReference(
  value: unknown,
): value is EmployeeOrganizationReference {
  return (
    isRecord(value) &&
    isString(value.id) &&
    isString(value.code) &&
    isString(value.name)
  );
}

function isPositionReference(value: unknown): value is EmployeePositionReference {
  return (
    isRecord(value) &&
    isString(value.id) &&
    isString(value.code) &&
    isString(value.title)
  );
}

function isCurrentAssignment(value: unknown): value is EmployeeCurrentAssignment {
  return (
    isRecord(value) &&
    isString(value.id) &&
    isOrganizationReference(value.legal_entity) &&
    isOrganizationReference(value.branch) &&
    isOrganizationReference(value.department) &&
    isPositionReference(value.position) &&
    isString(value.effective_from)
  );
}

function isEmployee(value: unknown): value is Employee {
  return (
    isRecord(value) &&
    isString(value.id) &&
    isString(value.employee_number) &&
    isString(value.first_name) &&
    isString(value.last_name) &&
    isNullableString(value.email) &&
    isNullableString(value.department) &&
    isNullableString(value.position) &&
    isString(value.status) &&
    EMPLOYEE_STATUSES.includes(value.status as EmployeeStatus) &&
    isString(value.employment_start_date) &&
    isNullableString(value.employment_end_date) &&
    Number.isInteger(value.version) &&
    Number(value.version) >= 1 &&
    (value.current_assignment === null || isCurrentAssignment(value.current_assignment))
  );
}

function invalidResponse(status: number, headers: Headers): ApiClientError {
  return new ApiClientError({
    status,
    code: "invalid_response",
    correlationId: headers.get("x-request-id"),
  });
}

export async function listEmployees(
  options: EmployeeListOptions,
): Promise<EmployeeListPage> {
  const query = new URLSearchParams({ limit: String(options.limit) });
  const normalizedQuery = options.q?.trim();
  if (normalizedQuery) query.set("q", normalizedQuery);
  if (options.status) query.set("status", options.status);
  if (options.legalEntityId) query.set("legal_entity_id", options.legalEntityId);
  if (options.branchId) query.set("branch_id", options.branchId);
  if (options.departmentId) query.set("department_id", options.departmentId);
  if (options.positionId) query.set("position_id", options.positionId);
  if (options.cursor) query.set("cursor", options.cursor);

  const response = await requestAuthenticatedApiPlainCursorSuccess<unknown>(
    `/api/v1/employees?${query.toString()}`,
  );
  if (!Array.isArray(response.data) || !response.data.every(isEmployee)) {
    throw invalidResponse(response.status, response.headers);
  }
  return {
    data: response.data,
    meta: {
      limit: options.limit,
      next_cursor: response.nextCursor,
    },
  };
}

export async function readEmployee(employeeId: string): Promise<Employee> {
  const response = await requestAuthenticatedApiPlainSuccess<unknown>(
    `/api/v1/employees/${encodeURIComponent(employeeId)}`,
  );
  if (!isEmployee(response.data)) {
    throw invalidResponse(response.status, response.headers);
  }
  return response.data;
}

export async function createEmployee(
  employee: EmployeeCreateRequest,
): Promise<Employee> {
  const response = await requestAuthenticatedApiPlainSuccess<unknown>(
    "/api/v1/employees",
    { method: "POST", body: employee },
  );
  if (!isEmployee(response.data)) {
    throw invalidResponse(response.status, response.headers);
  }
  return response.data;
}
