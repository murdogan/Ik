import { ApiClientError, type ApiSuccessEnvelope } from "./api-client";
import {
  requestAuthenticatedApi,
  requestAuthenticatedApiEnvelope,
} from "./session";

export type AuditScope = "tenant" | "platform";
export type AuditMetadataScalar = string | number | boolean | null;
export type AuditMetadataValue = AuditMetadataScalar | AuditMetadataScalar[];

export interface AuditEvent {
  id: string;
  occurred_at: string;
  scope_type: AuditScope;
  tenant_id: string | null;
  actor_type: string;
  actor_user_id: string | null;
  event_type: string;
  category: string;
  severity: string;
  resource_type: string | null;
  resource_id: string | null;
  action: string;
  result: string;
  request_id: string;
  trace_id: string;
  session_id: string | null;
  ip_address: string | null;
  user_agent: string | null;
  changed_fields: string[];
  metadata: Record<string, AuditMetadataValue>;
  data_classification: string;
  visibility_class: string;
}

export interface AuditListMeta {
  limit: number;
  next_cursor: string | null;
}

export interface AuditListOptions {
  category?: string;
  eventType?: string;
  result?: string;
  limit: number;
  cursor?: string | null;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function isNullableString(value: unknown): value is string | null {
  return value === null || typeof value === "string";
}

function isMetadataScalar(value: unknown): value is AuditMetadataScalar {
  return (
    value === null ||
    typeof value === "string" ||
    typeof value === "number" ||
    typeof value === "boolean"
  );
}

function isMetadataValue(value: unknown): value is AuditMetadataValue {
  return (
    isMetadataScalar(value) ||
    (Array.isArray(value) && value.every(isMetadataScalar))
  );
}

function isAuditEvent(value: unknown, expectedScope: AuditScope): value is AuditEvent {
  if (!isRecord(value) || value.scope_type !== expectedScope) {
    return false;
  }
  if (
    (expectedScope === "tenant" && typeof value.tenant_id !== "string") ||
    (expectedScope === "platform" && value.tenant_id !== null)
  ) {
    return false;
  }

  const requiredStrings = [
    "id",
    "occurred_at",
    "actor_type",
    "event_type",
    "category",
    "severity",
    "action",
    "result",
    "request_id",
    "trace_id",
    "data_classification",
    "visibility_class",
  ] as const;
  if (requiredStrings.some((field) => typeof value[field] !== "string")) {
    return false;
  }

  const nullableStrings = [
    "actor_user_id",
    "resource_type",
    "resource_id",
    "session_id",
    "ip_address",
    "user_agent",
  ] as const;
  if (nullableStrings.some((field) => !isNullableString(value[field]))) {
    return false;
  }
  if (
    !Array.isArray(value.changed_fields) ||
    !value.changed_fields.every((field) => typeof field === "string") ||
    !isRecord(value.metadata) ||
    !Object.values(value.metadata).every(isMetadataValue)
  ) {
    return false;
  }
  return true;
}

function listPath(scope: AuditScope, options: AuditListOptions): `/api/${string}` {
  const query = new URLSearchParams({ limit: String(options.limit) });
  const category = options.category?.trim();
  const eventType = options.eventType?.trim();
  const result = options.result?.trim();
  if (category) {
    query.set("category", category);
  }
  if (eventType) {
    query.set("event_type", eventType);
  }
  if (result) {
    query.set("result", result);
  }
  if (options.cursor) {
    query.set("cursor", options.cursor);
  }

  const basePath =
    scope === "tenant" ? "/api/v1/audit-events" : "/api/v1/platform/audit-events";
  return `${basePath}?${query.toString()}`;
}

async function listAuditEvents(
  scope: AuditScope,
  options: AuditListOptions,
): Promise<ApiSuccessEnvelope<AuditEvent[], AuditListMeta>> {
  const envelope = await requestAuthenticatedApiEnvelope<
    unknown,
    Record<string, unknown>
  >(listPath(scope, options));
  if (
    !Array.isArray(envelope.data) ||
    !envelope.data.every((event) => isAuditEvent(event, scope)) ||
    !Number.isInteger(envelope.meta.limit) ||
    Number(envelope.meta.limit) < 1 ||
    Number(envelope.meta.limit) > 100 ||
    !(
      envelope.meta.next_cursor === null ||
      typeof envelope.meta.next_cursor === "string"
    )
  ) {
    throw new ApiClientError({ status: 200, code: "invalid_response" });
  }

  return {
    data: envelope.data,
    meta: {
      limit: Number(envelope.meta.limit),
      next_cursor: envelope.meta.next_cursor,
    },
  };
}

export function listTenantAuditEvents(
  options: AuditListOptions,
): Promise<ApiSuccessEnvelope<AuditEvent[], AuditListMeta>> {
  return listAuditEvents("tenant", options);
}

export function listPlatformAuditEvents(
  options: AuditListOptions,
): Promise<ApiSuccessEnvelope<AuditEvent[], AuditListMeta>> {
  return listAuditEvents("platform", options);
}

export async function readTenantAuditEvent(eventId: string): Promise<AuditEvent> {
  const event = await requestAuthenticatedApi<unknown>(
    `/api/v1/audit-events/${encodeURIComponent(eventId)}`,
  );
  if (!isAuditEvent(event, "tenant")) {
    throw new ApiClientError({ status: 200, code: "invalid_response" });
  }
  return event;
}
