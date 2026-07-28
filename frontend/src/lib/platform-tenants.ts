import { ApiClientError, type ApiSuccessEnvelope } from "./api-client";
import { requestPlatformAuthenticatedApiEnvelope } from "./platform-session";

export const PLATFORM_TENANT_STATUSES = [
  "provisioning",
  "trial",
  "active",
  "suspended",
  "offboarding",
  "closed",
] as const;

export const PLATFORM_TENANT_PLANS = [
  "core",
  "professional",
  "enterprise",
] as const;

export const PLATFORM_TENANT_REGIONS = ["tr-1", "eu-1"] as const;
export const PLATFORM_TENANT_LOCALES = ["tr-TR", "en-US"] as const;
export const PLATFORM_FEATURE_KEYS = [
  "organization",
  "employees",
  "documents",
  "leave",
  "self_service",
  "reporting",
  "notifications",
] as const;

export type PlatformTenantStatus = (typeof PLATFORM_TENANT_STATUSES)[number];
export type PlatformTenantPlan = (typeof PLATFORM_TENANT_PLANS)[number];
export type PlatformTenantRegion = (typeof PLATFORM_TENANT_REGIONS)[number];
export type PlatformTenantLocale = (typeof PLATFORM_TENANT_LOCALES)[number];
export type PlatformFeatureKey = (typeof PLATFORM_FEATURE_KEYS)[number];
export type PlatformTenantHealth =
  | "provisioning"
  | "healthy"
  | "restricted"
  | "offboarding"
  | "closed";

export interface PlatformTenant {
  id: string;
  slug: string;
  name: string;
  status: PlatformTenantStatus;
  plan_code: PlatformTenantPlan | "premium";
  data_region: PlatformTenantRegion;
  locale: PlatformTenantLocale;
  timezone: string;
  health: PlatformTenantHealth;
  limits: {
    active_employees: number | null;
  };
  created_at: string;
  updated_at: string;
}

export interface PlatformTenantFeature {
  key: PlatformFeatureKey;
  enabled: boolean;
  source: "default" | "override";
}

export interface PlatformResponseMeta {
  request_id: string;
  trace_id: string;
  correlation_id: string;
}

export interface PlatformTenantListMeta extends PlatformResponseMeta {
  limit: number;
  next_cursor: string | null;
}

export interface PlatformTenantPage {
  data: PlatformTenant[];
  meta: PlatformTenantListMeta;
}

export interface PlatformTenantCollection {
  tenants: PlatformTenant[];
  pageCount: number;
  lastMeta: PlatformTenantListMeta;
}

export interface PlatformTenantCreateRequest {
  slug: string;
  name: string;
  plan_code: PlatformTenantPlan;
  data_region: PlatformTenantRegion;
  locale: PlatformTenantLocale;
  timezone: string;
  limits?: {
    active_employees: number | null;
  };
}

export interface PlatformTenantUpdateRequest {
  name?: string;
  status?: PlatformTenantStatus;
  plan_code?: PlatformTenantPlan;
  data_region?: PlatformTenantRegion;
  locale?: PlatformTenantLocale;
  timezone?: string;
  limits?: {
    active_employees: number;
  };
}

export interface PlatformTenantErrorPresentation {
  message: string;
  reference: string | null;
}

const TENANT_PAGE_LIMIT = 200;
const MAX_CURSOR_LENGTH = 2_048;
const MAX_TENANT_PAGES = 1_000;
const UUID_PATTERN =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

const HEALTH_BY_STATUS: Record<PlatformTenantStatus, PlatformTenantHealth> = {
  provisioning: "provisioning",
  trial: "healthy",
  active: "healthy",
  suspended: "restricted",
  offboarding: "offboarding",
  closed: "closed",
};

const FEATURE_DEFAULTS: Record<PlatformFeatureKey, boolean> = {
  organization: false,
  employees: true,
  documents: false,
  leave: true,
  self_service: true,
  reporting: true,
  notifications: true,
};

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function hasExactKeys(
  value: Record<string, unknown>,
  expectedKeys: readonly string[],
): boolean {
  const actualKeys = Object.keys(value);
  return (
    actualKeys.length === expectedKeys.length &&
    expectedKeys.every((key) => Object.hasOwn(value, key))
  );
}

function isBoundedString(
  value: unknown,
  { min = 1, max }: { min?: number; max: number },
): value is string {
  return (
    typeof value === "string" &&
    value.length >= min &&
    value.length <= max
  );
}

function isUtcDateTime(value: unknown): value is string {
  return (
    typeof value === "string" &&
    /(?:Z|[+-]\d{2}:\d{2})$/.test(value) &&
    Number.isFinite(Date.parse(value))
  );
}

function isStatus(value: unknown): value is PlatformTenantStatus {
  return (
    typeof value === "string" &&
    PLATFORM_TENANT_STATUSES.includes(value as PlatformTenantStatus)
  );
}

function isPlan(
  value: unknown,
): value is PlatformTenantPlan | "premium" {
  return (
    value === "premium" ||
    (typeof value === "string" &&
      PLATFORM_TENANT_PLANS.includes(value as PlatformTenantPlan))
  );
}

function isRegion(value: unknown): value is PlatformTenantRegion {
  return (
    typeof value === "string" &&
    PLATFORM_TENANT_REGIONS.includes(value as PlatformTenantRegion)
  );
}

function isLocale(value: unknown): value is PlatformTenantLocale {
  return (
    typeof value === "string" &&
    PLATFORM_TENANT_LOCALES.includes(value as PlatformTenantLocale)
  );
}

function isConfiguredLimit(value: unknown): value is number | null {
  return (
    value === null ||
    (typeof value === "number" &&
      Number.isSafeInteger(value) &&
      value >= 1 &&
      value <= 1_000_000)
  );
}

function isPlatformTenant(value: unknown): value is PlatformTenant {
  if (
    !isRecord(value) ||
    !hasExactKeys(value, [
      "id",
      "slug",
      "name",
      "status",
      "plan_code",
      "data_region",
      "locale",
      "timezone",
      "health",
      "limits",
      "created_at",
      "updated_at",
    ]) ||
    typeof value.id !== "string" ||
    !UUID_PATTERN.test(value.id) ||
    typeof value.slug !== "string" ||
    typeof value.name !== "string" ||
    !isStatus(value.status) ||
    !isPlan(value.plan_code) ||
    !isRegion(value.data_region) ||
    !isLocale(value.locale) ||
    typeof value.timezone !== "string" ||
    !isUtcDateTime(value.created_at) ||
    !isUtcDateTime(value.updated_at) ||
    !isRecord(value.limits) ||
    !hasExactKeys(value.limits, ["active_employees"]) ||
    !isConfiguredLimit(value.limits.active_employees)
  ) {
    return false;
  }

  return value.health === HEALTH_BY_STATUS[value.status];
}

function isResponseMeta(value: unknown): value is PlatformResponseMeta {
  return (
    isRecord(value) &&
    hasExactKeys(value, ["request_id", "trace_id", "correlation_id"]) &&
    isBoundedString(value.request_id, { max: 128 }) &&
    isBoundedString(value.trace_id, { max: 128 }) &&
    isBoundedString(value.correlation_id, { max: 128 })
  );
}

function isListMeta(value: unknown): value is PlatformTenantListMeta {
  return (
    isRecord(value) &&
    hasExactKeys(value, [
      "request_id",
      "trace_id",
      "correlation_id",
      "limit",
      "next_cursor",
    ]) &&
    isBoundedString(value.request_id, { max: 128 }) &&
    isBoundedString(value.trace_id, { max: 128 }) &&
    isBoundedString(value.correlation_id, { max: 128 }) &&
    typeof value.limit === "number" &&
    Number.isSafeInteger(value.limit) &&
    value.limit >= 1 &&
    value.limit <= TENANT_PAGE_LIMIT &&
    (value.next_cursor === null ||
      isBoundedString(value.next_cursor, { max: MAX_CURSOR_LENGTH }))
  );
}

function isFeature(value: unknown): value is PlatformTenantFeature {
  if (
    isRecord(value) &&
    hasExactKeys(value, ["key", "enabled", "source"]) &&
    typeof value.key === "string" &&
    PLATFORM_FEATURE_KEYS.includes(value.key as PlatformFeatureKey) &&
    typeof value.enabled === "boolean" &&
    (value.source === "default" || value.source === "override")
  ) {
    const expectedSource =
      value.enabled === FEATURE_DEFAULTS[value.key as PlatformFeatureKey]
        ? "default"
        : "override";
    return value.source === expectedSource;
  }
  return false;
}

function invalidResponse(
  meta?: unknown,
): ApiClientError {
  const correlationId =
    isRecord(meta) && typeof meta.correlation_id === "string"
      ? meta.correlation_id
      : null;
  return new ApiClientError({
    status: 200,
    code: "invalid_response",
    correlationId,
  });
}

function validateTenantEnvelope(
  envelope: ApiSuccessEnvelope<unknown, unknown>,
): ApiSuccessEnvelope<PlatformTenant, PlatformResponseMeta> {
  if (!isPlatformTenant(envelope.data) || !isResponseMeta(envelope.meta)) {
    throw invalidResponse(envelope.meta);
  }
  return { data: envelope.data, meta: envelope.meta };
}

function validateFeatureEnvelope(
  envelope: ApiSuccessEnvelope<unknown, unknown>,
): ApiSuccessEnvelope<
  { features: PlatformTenantFeature[] },
  PlatformResponseMeta
> {
  if (
    !isResponseMeta(envelope.meta) ||
    !isRecord(envelope.data) ||
    !hasExactKeys(envelope.data, ["features"]) ||
    !Array.isArray(envelope.data.features) ||
    envelope.data.features.length !== PLATFORM_FEATURE_KEYS.length ||
    !envelope.data.features.every(isFeature) ||
    !envelope.data.features.every(
      (feature, index) => feature.key === PLATFORM_FEATURE_KEYS[index],
    )
  ) {
    throw invalidResponse(envelope.meta);
  }
  return envelope as ApiSuccessEnvelope<
    { features: PlatformTenantFeature[] },
    PlatformResponseMeta
  >;
}

export async function listPlatformTenantPage({
  cursor = null,
  limit = TENANT_PAGE_LIMIT,
}: {
  cursor?: string | null;
  limit?: number;
} = {}): Promise<PlatformTenantPage> {
  const query = new URLSearchParams({ limit: String(limit) });
  if (cursor) {
    query.set("cursor", cursor);
  }
  const envelope = await requestPlatformAuthenticatedApiEnvelope<
    unknown,
    unknown
  >(`/api/v1/platform/tenants?${query.toString()}`);
  if (
    !Array.isArray(envelope.data) ||
    !envelope.data.every(isPlatformTenant) ||
    new Set(envelope.data.map((tenant) => tenant.id)).size !==
      envelope.data.length ||
    !isListMeta(envelope.meta) ||
    envelope.meta.limit !== limit
  ) {
    throw invalidResponse(envelope.meta);
  }
  return envelope as PlatformTenantPage;
}

export async function listAllPlatformTenants(): Promise<PlatformTenantCollection> {
  const tenants: PlatformTenant[] = [];
  const tenantIds = new Set<string>();
  const seenCursors = new Set<string>();
  let cursor: string | null = null;
  let pageCount = 0;
  let lastMeta: PlatformTenantListMeta | null = null;

  do {
    const page = await listPlatformTenantPage({ cursor });
    pageCount += 1;
    if (pageCount > MAX_TENANT_PAGES) {
      throw invalidResponse(page.meta);
    }
    for (const tenant of page.data) {
      if (tenantIds.has(tenant.id)) {
        throw invalidResponse(page.meta);
      }
      tenantIds.add(tenant.id);
      tenants.push(tenant);
    }
    lastMeta = page.meta;
    cursor = page.meta.next_cursor;
    if (cursor) {
      if (pageCount >= MAX_TENANT_PAGES) {
        throw invalidResponse(page.meta);
      }
      if (page.data.length === 0) {
        throw invalidResponse(page.meta);
      }
      if (seenCursors.has(cursor)) {
        throw invalidResponse(page.meta);
      }
      seenCursors.add(cursor);
    }
  } while (cursor !== null);

  if (!lastMeta) {
    throw invalidResponse();
  }
  return { tenants, pageCount, lastMeta };
}

export async function readPlatformTenant(
  tenantId: string,
): Promise<ApiSuccessEnvelope<PlatformTenant, PlatformResponseMeta>> {
  const envelope = await requestPlatformAuthenticatedApiEnvelope<
    unknown,
    unknown
  >(`/api/v1/platform/tenants/${encodeURIComponent(tenantId)}`);
  return validateTenantEnvelope(envelope);
}

export async function createPlatformTenant(
  payload: PlatformTenantCreateRequest,
): Promise<ApiSuccessEnvelope<PlatformTenant, PlatformResponseMeta>> {
  const envelope = await requestPlatformAuthenticatedApiEnvelope<
    unknown,
    unknown
  >("/api/v1/platform/tenants", {
    method: "POST",
    body: payload,
  });
  const validated = validateTenantEnvelope(envelope);
  if (validated.data.status !== "provisioning") {
    throw invalidResponse(validated.meta);
  }
  return validated;
}

export async function updatePlatformTenant(
  tenantId: string,
  payload: PlatformTenantUpdateRequest,
): Promise<ApiSuccessEnvelope<PlatformTenant, PlatformResponseMeta>> {
  const envelope = await requestPlatformAuthenticatedApiEnvelope<
    unknown,
    unknown
  >(`/api/v1/platform/tenants/${encodeURIComponent(tenantId)}`, {
    method: "PATCH",
    body: payload,
  });
  return validateTenantEnvelope(envelope);
}

export async function readPlatformTenantFeatures(
  tenantId: string,
): Promise<
  ApiSuccessEnvelope<
    { features: PlatformTenantFeature[] },
    PlatformResponseMeta
  >
> {
  const envelope = await requestPlatformAuthenticatedApiEnvelope<
    unknown,
    unknown
  >(`/api/v1/platform/tenants/${encodeURIComponent(tenantId)}/features`);
  return validateFeatureEnvelope(envelope);
}

export async function updatePlatformTenantFeatures(
  tenantId: string,
  features: { key: PlatformFeatureKey; enabled: boolean }[],
): Promise<
  ApiSuccessEnvelope<
    { features: PlatformTenantFeature[] },
    PlatformResponseMeta
  >
> {
  const envelope = await requestPlatformAuthenticatedApiEnvelope<
    unknown,
    unknown
  >(`/api/v1/platform/tenants/${encodeURIComponent(tenantId)}/features`, {
    method: "PATCH",
    body: { features },
  });
  return validateFeatureEnvelope(envelope);
}

export function platformTenantErrorPresentation(
  cause: unknown,
  fallback: string,
): PlatformTenantErrorPresentation {
  if (!(cause instanceof ApiClientError)) {
    return {
      message: fallback,
      reference: null,
    };
  }

  const code = cause.code.toLowerCase();
  let message = fallback;
  if (cause.status === null || code === "network_error") {
    message =
      "Sunucuya ulaşılamadı. Bağlantınızı kontrol edip yeniden deneyin.";
  } else if (cause.status === 403 || code.includes("access_denied")) {
    message =
      "Bu işlem mevcut platform yetkilerinizle kullanılamıyor. Yetkilerinizi yenileyip yeniden deneyin.";
  } else if (cause.status === 404 || code === "tenant_not_found") {
    message = "Tenant bulunamadı veya artık erişilebilir değil.";
  } else if (code.includes("slug_conflict")) {
    message = "Bu tenant kodu zaten kullanılıyor. Farklı bir kod girin.";
  } else if (code.includes("lifecycle")) {
    message =
      "İşlem tenant’ın güncel yaşam döngüsü durumuyla çakıştı. Veriyi yenileyip geçerli bir işlem seçin.";
  } else if (cause.status === 409 || code.includes("concurrent_write")) {
    message =
      "Tenant aynı anda başka bir işlemle güncellendi. Güncel veriyi yenileyip yeniden deneyin.";
  } else if (cause.status === 422 || code.includes("validation")) {
    message = "Gönderilen değerler doğrulanamadı. Alanları kontrol edip yeniden deneyin.";
  } else if (code === "invalid_response") {
    message =
      "Sunucudan beklenmeyen bir yanıt alındı. Güvenliğiniz için veri gösterilmedi.";
  }

  return { message, reference: cause.correlationId };
}
