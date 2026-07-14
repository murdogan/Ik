import { ApiClientError } from "./api-client";
import { EMPLOYEE_STATUSES, type EmployeeStatus } from "./employees";
import { requestAuthenticatedApiPlainSuccess } from "./session";

export const EMPLOYEE_TERMINATION_REASONS = [
  "resignation",
  "dismissal",
  "retirement",
  "contract_end",
  "other",
] as const;

export type EmployeeTerminationReason =
  (typeof EMPLOYEE_TERMINATION_REASONS)[number];

export type EmployeeLifecycleTransitionRequest =
  | {
      target_status: "active" | "on_leave";
      expected_version: number;
    }
  | {
      target_status: "terminated";
      expected_version: number;
      effective_date: string;
      termination_reason: EmployeeTerminationReason;
    };

export interface EmployeeLifecycleState {
  id: string;
  status: EmployeeStatus;
  employment_start_date: string;
  employment_end_date: string | null;
  termination_reason: EmployeeTerminationReason | null;
  version: number;
  archived_at: string | null;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function isNullableString(value: unknown): value is string | null {
  return value === null || typeof value === "string";
}

function isLifecycleState(
  value: unknown,
  employeeId: string,
): value is EmployeeLifecycleState {
  return (
    isRecord(value) &&
    value.id === employeeId &&
    typeof value.status === "string" &&
    EMPLOYEE_STATUSES.includes(value.status as EmployeeStatus) &&
    typeof value.employment_start_date === "string" &&
    isNullableString(value.employment_end_date) &&
    (value.termination_reason === null ||
      (typeof value.termination_reason === "string" &&
        EMPLOYEE_TERMINATION_REASONS.includes(
          value.termination_reason as EmployeeTerminationReason,
        ))) &&
    Number.isInteger(value.version) &&
    Number(value.version) >= 1 &&
    isNullableString(value.archived_at)
  );
}

function invalidResponse(status: number, headers: Headers): ApiClientError {
  return new ApiClientError({
    status,
    code: "invalid_response",
    correlationId: headers.get("x-request-id"),
  });
}

export async function transitionEmployeeLifecycle(
  employeeId: string,
  payload: EmployeeLifecycleTransitionRequest,
): Promise<EmployeeLifecycleState> {
  const response = await requestAuthenticatedApiPlainSuccess<unknown>(
    `/api/v1/employees/${encodeURIComponent(employeeId)}/lifecycle-transitions`,
    { method: "POST", body: payload },
  );
  if (!isLifecycleState(response.data, employeeId)) {
    throw invalidResponse(response.status, response.headers);
  }
  return response.data;
}

export async function archiveEmployee(
  employeeId: string,
  expectedVersion: number,
): Promise<EmployeeLifecycleState> {
  const response = await requestAuthenticatedApiPlainSuccess<unknown>(
    `/api/v1/employees/${encodeURIComponent(employeeId)}/archive`,
    { method: "POST", body: { expected_version: expectedVersion } },
  );
  if (!isLifecycleState(response.data, employeeId)) {
    throw invalidResponse(response.status, response.headers);
  }
  return response.data;
}
