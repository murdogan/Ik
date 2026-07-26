import { ApiClientError } from "./api-client";
import { requestAuthenticatedApi } from "./session";

export const TENANT_READINESS_ITEM_KEYS = [
  "default_legal_entity",
  "organization_structure",
  "active_tenant_administrator",
  "employee_master_data",
  "leave_configuration",
  "document_configuration",
  "privacy_notice",
  "feature_dependencies",
  "notification_delivery",
] as const;

export const TENANT_READINESS_ITEM_STATES = [
  "ready",
  "action_required",
  "not_applicable",
] as const;

export type TenantReadinessItemKey =
  (typeof TENANT_READINESS_ITEM_KEYS)[number];
export type TenantReadinessItemState =
  (typeof TENANT_READINESS_ITEM_STATES)[number];
export type TenantReadinessOverallState = "ready" | "action_required";
export type TenantReadinessRemediationRoute =
  | "/organization"
  | "/users"
  | "/employees"
  | "/leave/admin"
  | "/document-types"
  | "/privacy/manage";

export interface TenantReadinessItem {
  key: TenantReadinessItemKey;
  state: TenantReadinessItemState;
  count: number | null;
  remediation_route: TenantReadinessRemediationRoute | null;
  evaluated_at: string;
}

export interface TenantReadiness {
  overall_state: TenantReadinessOverallState;
  evaluated_at: string;
  items: TenantReadinessItem[];
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function hasExactKeys(
  value: Record<string, unknown>,
  expected: readonly string[],
): boolean {
  const actual = Object.keys(value);
  return (
    actual.length === expected.length &&
    expected.every((key) => Object.hasOwn(value, key))
  );
}

function isUtcDateTime(value: unknown): value is string {
  return (
    typeof value === "string" &&
    /(?:Z|[+-]00:00)$/.test(value) &&
    Number.isFinite(Date.parse(value))
  );
}

function isItemState(value: unknown): value is TenantReadinessItemState {
  return (
    typeof value === "string" &&
    TENANT_READINESS_ITEM_STATES.includes(
      value as TenantReadinessItemState,
    )
  );
}

function isOverallState(value: unknown): value is TenantReadinessOverallState {
  return value === "ready" || value === "action_required";
}

function isCountForItem(
  key: TenantReadinessItemKey,
  value: unknown,
): value is number | null {
  if (value === null) {
    return (
      key === "organization_structure" ||
      key === "leave_configuration" ||
      key === "feature_dependencies" ||
      key === "notification_delivery"
    );
  }
  if (
    typeof value !== "number" ||
    !Number.isSafeInteger(value) ||
    value < 0
  ) {
    return false;
  }

  switch (key) {
    case "default_legal_entity":
    case "privacy_notice":
      return value <= 1;
    case "active_tenant_administrator":
    case "employee_master_data":
    case "document_configuration":
      return true;
    case "organization_structure":
    case "leave_configuration":
    case "feature_dependencies":
    case "notification_delivery":
      return false;
  }
}

function isStateAllowedForItem(
  key: TenantReadinessItemKey,
  state: TenantReadinessItemState,
): boolean {
  if (key === "notification_delivery" && state === "ready") {
    return false;
  }
  if (state !== "not_applicable") {
    return true;
  }
  return (
    key === "leave_configuration" ||
    key === "document_configuration" ||
    key === "notification_delivery"
  );
}

function isRouteForItem(
  key: TenantReadinessItemKey,
  value: unknown,
  count: number | null,
): value is TenantReadinessRemediationRoute | null {
  switch (key) {
    case "default_legal_entity":
    case "organization_structure":
      return value === "/organization";
    case "active_tenant_administrator":
      return value === "/users";
    case "employee_master_data":
      return value === "/employees";
    case "leave_configuration":
      return value === "/leave/admin";
    case "document_configuration":
      return count === 0
        ? value === "/document-types"
        : value === null;
    case "privacy_notice":
      return value === "/privacy/manage";
    case "feature_dependencies":
    case "notification_delivery":
      return value === null;
  }
}

function isStateConsistentWithCount(
  key: TenantReadinessItemKey,
  state: TenantReadinessItemState,
  count: number | null,
): boolean {
  switch (key) {
    case "default_legal_entity":
      return (count === 1) === (state === "ready");
    case "active_tenant_administrator":
    case "employee_master_data":
    case "privacy_notice":
      return ((count ?? 0) > 0) === (state === "ready");
    case "document_configuration":
      return count !== 0 || state !== "ready";
    case "organization_structure":
    case "leave_configuration":
    case "feature_dependencies":
    case "notification_delivery":
      return true;
  }
}

function isReadinessItem(
  value: unknown,
  expectedKey: TenantReadinessItemKey,
  evaluatedAt: string,
): value is TenantReadinessItem {
  if (
    !isRecord(value) ||
    !hasExactKeys(value, [
      "key",
      "state",
      "count",
      "remediation_route",
      "evaluated_at",
    ]) ||
    value.key !== expectedKey ||
    !isItemState(value.state) ||
    !isStateAllowedForItem(expectedKey, value.state) ||
    !isCountForItem(expectedKey, value.count) ||
    !isRouteForItem(expectedKey, value.remediation_route, value.count) ||
    !isStateConsistentWithCount(expectedKey, value.state, value.count) ||
    !isUtcDateTime(value.evaluated_at)
  ) {
    return false;
  }
  return value.evaluated_at === evaluatedAt;
}

function isTenantReadiness(value: unknown): value is TenantReadiness {
  if (
    !isRecord(value) ||
    !hasExactKeys(value, ["overall_state", "evaluated_at", "items"]) ||
    !isOverallState(value.overall_state) ||
    !isUtcDateTime(value.evaluated_at) ||
    !Array.isArray(value.items) ||
    value.items.length !== TENANT_READINESS_ITEM_KEYS.length
  ) {
    return false;
  }

  for (let index = 0; index < TENANT_READINESS_ITEM_KEYS.length; index += 1) {
    if (
      !isReadinessItem(
        value.items[index],
        TENANT_READINESS_ITEM_KEYS[index],
        value.evaluated_at,
      )
    ) {
      return false;
    }
  }

  const items = value.items as TenantReadinessItem[];
  const expectedOverallState: TenantReadinessOverallState = items.every(
    (item) => item.state === "ready" || item.state === "not_applicable",
  )
    ? "ready"
    : "action_required";
  return value.overall_state === expectedOverallState;
}

export async function readTenantReadiness(): Promise<TenantReadiness> {
  const data = await requestAuthenticatedApi<unknown>(
    "/api/v1/tenant/readiness",
  );
  if (!isTenantReadiness(data)) {
    throw new ApiClientError({ status: 200, code: "invalid_response" });
  }
  return data;
}
