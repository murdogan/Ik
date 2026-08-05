import { ApiClientError, type ApiSuccessEnvelope } from "./api-client";
import {
  isPostResponsePlatformSessionSupersededError,
  requestPlatformAuthenticatedApiEnvelope,
} from "./platform-session";

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
export const PLATFORM_TENANT_TIMEZONE_FALLBACK = [
  "Europe/Istanbul",
  "Africa/Cairo",
  "Africa/Johannesburg",
  "America/Argentina/Buenos_Aires",
  "America/Chicago",
  "America/Los_Angeles",
  "America/New_York",
  "America/Sao_Paulo",
  "Asia/Dubai",
  "Asia/Hong_Kong",
  "Asia/Kolkata",
  "Asia/Singapore",
  "Asia/Tokyo",
  "Australia/Sydney",
  "Europe/Amsterdam",
  "Europe/Athens",
  "Europe/Berlin",
  "Europe/London",
  "Europe/Paris",
  "Europe/Warsaw",
  "Pacific/Auckland",
  "UTC",
] as const;
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
export type PlatformTenantTimezone = string;
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

export interface PlatformTenantCreateReconciliation {
  tenant: PlatformTenant | null;
  meta: PlatformTenantListMeta;
}

export interface PlatformTenantCreateRequest {
  slug: string;
  name: string;
  initial_admin: {
    full_name: string;
    email: string;
  };
  plan_code: PlatformTenantPlan;
  data_region: PlatformTenantRegion;
  locale: PlatformTenantLocale;
  timezone: PlatformTenantTimezone;
  limits?: {
    active_employees: number | null;
  };
}

export interface PlatformTenantInitialAdminRead {
  status: "invitation_prepared";
}

export interface PlatformTenantInitialAdminManualLinkRead {
  status: "manual_link_ready";
  activation_url: string;
  expires_at: string;
}

export interface PlatformTenantInitialAdminCorrectionRequest {
  full_name: string;
  email: string;
}

export interface PlatformTenantCreateRead extends PlatformTenant {
  initial_admin: PlatformTenantInitialAdminRead;
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
const MANUAL_ACTIVATION_TOKEN_PATTERN =
  /^v1\.([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})\.[0-9a-f]{64}$/;
const RESPONSE_REQUEST_ID_PATTERN =
  /^[A-Za-z0-9](?:[A-Za-z0-9._-]{0,126}[A-Za-z0-9])?$/;
const RESPONSE_TRACE_ID_PATTERN = /^[0-9a-f]{32}$/;
const TENANT_SLUG_PATTERN =
  /^[a-z0-9](?:[a-z0-9-]{0,78}[a-z0-9])?$/;
const RFC3339_UTC_PATTERN =
  /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})(?:\.(\d{1,6}))?Z$/;
const IANA_TIMEZONE_PATTERN = /^(?:UTC|[A-Za-z0-9_+-]+(?:\/[A-Za-z0-9_+-]+)+)$/;
const RECOGNIZED_TIMEZONES = new Set<string>();
const PLATFORM_TENANT_KEYS = [
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
] as const;
const PLATFORM_TENANT_CREATE_REQUEST_KEYS = [
  "slug",
  "name",
  "initial_admin",
  "plan_code",
  "data_region",
  "locale",
  "timezone",
] as const;

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

function isTrimmedBoundedString(
  value: unknown,
  bounds: { min?: number; max: number },
): value is string {
  return isBoundedString(value, bounds) && value === value.trim();
}

function isTenantSlug(value: unknown): value is string {
  return (
    isTrimmedBoundedString(value, { min: 2, max: 80 }) &&
    TENANT_SLUG_PATTERN.test(value)
  );
}

function isTenantName(value: unknown): value is string {
  return isTrimmedBoundedString(value, { max: 200 });
}

function isTenantTimezone(value: unknown): value is string {
  if (
    !isTrimmedBoundedString(value, { max: 64 }) ||
    !IANA_TIMEZONE_PATTERN.test(value)
  ) {
    return false;
  }
  if (RECOGNIZED_TIMEZONES.has(value)) {
    return true;
  }
  try {
    new Intl.DateTimeFormat("en-US", { timeZone: value }).format(0);
    RECOGNIZED_TIMEZONES.add(value);
    return true;
  } catch {
    return false;
  }
}

export function isPlatformTenantTimezone(
  value: string,
): value is PlatformTenantTimezone {
  return isTenantTimezone(value);
}

export function platformTenantTimezoneOptions(
  currentTimezone?: string,
): string[] {
  let values: readonly string[] = PLATFORM_TENANT_TIMEZONE_FALLBACK;
  try {
    const supportedValuesOf = Intl.supportedValuesOf;
    if (typeof supportedValuesOf === "function") {
      values = supportedValuesOf.call(Intl, "timeZone");
    }
  } catch {
    values = PLATFORM_TENANT_TIMEZONE_FALLBACK;
  }

  const timezones = new Set<string>(["UTC", ...values]);
  if (currentTimezone && isTenantTimezone(currentTimezone)) {
    timezones.add(currentTimezone);
  }
  timezones.delete("Europe/Istanbul");
  return ["Europe/Istanbul", ...[...timezones].sort()];
}

function normalizeInitialAdminEmail(value: unknown): string | null {
  if (typeof value !== "string") {
    return null;
  }
  const normalized = value.trim().toLowerCase();
  if (
    normalized.length < 3 ||
    normalized.length > 320 ||
    normalized.split("@").length !== 2 ||
    normalized.startsWith("@") ||
    normalized.endsWith("@") ||
    /\s/.test(normalized)
  ) {
    return null;
  }
  return normalized;
}

function isUtcDateTime(value: unknown): value is string {
  if (typeof value !== "string") {
    return false;
  }
  const match = RFC3339_UTC_PATTERN.exec(value);
  if (!match) {
    return false;
  }
  const [year, month, day, hour, minute, second] = match
    .slice(1, 7)
    .map(Number);
  if (year === 0 || second > 59) {
    return false;
  }
  const parsed = new Date(0);
  parsed.setUTCFullYear(year, month - 1, day);
  parsed.setUTCHours(hour, minute, second, 0);
  return (
    Number.isFinite(parsed.getTime()) &&
    parsed.getUTCFullYear() === year &&
    parsed.getUTCMonth() === month - 1 &&
    parsed.getUTCDate() === day &&
    parsed.getUTCHours() === hour &&
    parsed.getUTCMinutes() === minute &&
    parsed.getUTCSeconds() === second
  );
}

function isFutureUtcDateTime(value: unknown): value is string {
  return isUtcDateTime(value) && new Date(value).getTime() > Date.now();
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
    !hasExactKeys(value, PLATFORM_TENANT_KEYS) ||
    typeof value.id !== "string" ||
    !UUID_PATTERN.test(value.id) ||
    !isTenantSlug(value.slug) ||
    !isTenantName(value.name) ||
    !isStatus(value.status) ||
    !isPlan(value.plan_code) ||
    !isRegion(value.data_region) ||
    !isLocale(value.locale) ||
    !isTenantTimezone(value.timezone) ||
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

function isInitialAdminRead(
  value: unknown,
): value is PlatformTenantInitialAdminRead {
  return (
    isRecord(value) &&
    hasExactKeys(value, ["status"]) &&
    value.status === "invitation_prepared"
  );
}

function isManualActivationUrlForTenant(
  value: unknown,
  tenantId: string,
): value is string {
  if (
    !isTrimmedBoundedString(value, { max: 4_096 }) ||
    !UUID_PATTERN.test(tenantId) ||
    /[\u0000-\u001f\u007f]/.test(value)
  ) {
    return false;
  }

  let activationUrl: URL;
  try {
    activationUrl = new URL(value);
  } catch {
    return false;
  }

  const currentFrontendOrigin =
    typeof window === "undefined" ? null : window.location.origin;

  if (
    currentFrontendOrigin === null ||
    activationUrl.origin !== currentFrontendOrigin ||
    (activationUrl.protocol !== "https:" &&
      activationUrl.protocol !== "http:") ||
    activationUrl.hostname.length === 0 ||
    activationUrl.username.length > 0 ||
    activationUrl.password.length > 0 ||
    !activationUrl.pathname.endsWith("/activate") ||
    activationUrl.search.length > 0
  ) {
    return false;
  }

  const fragment = activationUrl.hash.slice(1);
  if (!fragment.startsWith("token=")) {
    return false;
  }
  const token = fragment.slice("token=".length);
  const tokenMatch = MANUAL_ACTIVATION_TOKEN_PATTERN.exec(token);
  if (tokenMatch === null || tokenMatch[1] !== tenantId.toLowerCase()) {
    return false;
  }
  const tokenSecret = token.slice(token.lastIndexOf(".") + 1);

  const fragmentIndex = value.indexOf("#");
  if (fragmentIndex < 0) {
    return false;
  }
  const preFragmentUrl = value.slice(0, fragmentIndex);
  let decodedPreFragmentUrl: string;
  try {
    decodedPreFragmentUrl = decodeURIComponent(preFragmentUrl);
  } catch {
    return false;
  }
  return (
    !preFragmentUrl.includes(token) &&
    !preFragmentUrl.includes(tokenSecret) &&
    !decodedPreFragmentUrl.includes(token) &&
    !decodedPreFragmentUrl.includes(tokenSecret)
  );
}

function isInitialAdminManualLinkRead(
  value: unknown,
  tenantId: string,
): value is PlatformTenantInitialAdminManualLinkRead {
  return (
    isRecord(value) &&
    hasExactKeys(value, ["status", "activation_url", "expires_at"]) &&
    value.status === "manual_link_ready" &&
    isManualActivationUrlForTenant(value.activation_url, tenantId) &&
    isFutureUtcDateTime(value.expires_at)
  );
}

function hasSafeResponseIdentifiers(
  value: Record<string, unknown>,
): value is Record<string, unknown> & PlatformResponseMeta {
  return (
    isBoundedString(value.request_id, { max: 128 }) &&
    RESPONSE_REQUEST_ID_PATTERN.test(value.request_id) &&
    value.request_id.split(".").length < 3 &&
    typeof value.trace_id === "string" &&
    RESPONSE_TRACE_ID_PATTERN.test(value.trace_id) &&
    value.trace_id !== "0".repeat(32) &&
    value.correlation_id === value.request_id
  );
}

function responseMetaContainsManualCredential(
  meta: PlatformResponseMeta,
  activationUrl: string,
): boolean {
  const rawToken = new URL(activationUrl).hash.slice("#token=".length);
  const tokenSecret = rawToken.slice(rawToken.lastIndexOf(".") + 1);
  return [meta.request_id, meta.trace_id, meta.correlation_id].some(
    (identifier) =>
      identifier.includes(rawToken) || identifier.includes(tokenSecret),
  );
}

function isResponseMeta(value: unknown): value is PlatformResponseMeta {
  return (
    isRecord(value) &&
    hasExactKeys(value, ["request_id", "trace_id", "correlation_id"]) &&
    hasSafeResponseIdentifiers(value)
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
    hasSafeResponseIdentifiers(value) &&
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
    isRecord(meta) && hasSafeResponseIdentifiers(meta)
      ? meta.correlation_id
      : null;
  return new ApiClientError({
    status: 200,
    code: "invalid_response",
    correlationId,
  });
}

function invalidRequest(): ApiClientError {
  return new ApiClientError({
    status: null,
    code: "invalid_request",
  });
}

export function adaptPlatformTenantCreateRequest(
  value: unknown,
): PlatformTenantCreateRequest {
  if (!isRecord(value)) {
    throw invalidRequest();
  }
  const expectedKeys = Object.hasOwn(value, "limits")
    ? [...PLATFORM_TENANT_CREATE_REQUEST_KEYS, "limits"]
    : PLATFORM_TENANT_CREATE_REQUEST_KEYS;
  const normalizedEmail = isRecord(value.initial_admin)
    ? normalizeInitialAdminEmail(value.initial_admin.email)
    : null;

  if (
    !hasExactKeys(value, expectedKeys) ||
    !isTenantSlug(value.slug) ||
    !isTenantName(value.name) ||
    !isRecord(value.initial_admin) ||
    !hasExactKeys(value.initial_admin, ["full_name", "email"]) ||
    !isTrimmedBoundedString(value.initial_admin.full_name, {
      max: 200,
    }) ||
    normalizedEmail === null ||
    !isPlan(value.plan_code) ||
    value.plan_code === "premium" ||
    !isRegion(value.data_region) ||
    !isLocale(value.locale) ||
    typeof value.timezone !== "string" ||
    !isPlatformTenantTimezone(value.timezone) ||
    (Object.hasOwn(value, "limits") &&
      (!isRecord(value.limits) ||
        !hasExactKeys(value.limits, ["active_employees"]) ||
        !isConfiguredLimit(value.limits.active_employees)))
  ) {
    throw invalidRequest();
  }

  return {
    slug: value.slug,
    name: value.name,
    initial_admin: {
      full_name: value.initial_admin.full_name,
      email: normalizedEmail,
    },
    plan_code: value.plan_code,
    data_region: value.data_region,
    locale: value.locale,
    timezone: value.timezone,
    ...(isRecord(value.limits)
      ? {
          limits: {
            active_employees: value.limits.active_employees as number | null,
          },
        }
      : {}),
  };
}

export function adaptPlatformTenantInitialAdminCorrectionRequest(
  value: unknown,
): PlatformTenantInitialAdminCorrectionRequest {
  if (!isRecord(value)) {
    throw invalidRequest();
  }

  const fullName =
    typeof value.full_name === "string" ? value.full_name.trim() : null;
  const normalizedEmail = normalizeInitialAdminEmail(value.email);
  if (
    !hasExactKeys(value, ["full_name", "email"]) ||
    !isBoundedString(fullName, { max: 200 }) ||
    normalizedEmail === null
  ) {
    throw invalidRequest();
  }

  return {
    full_name: fullName,
    email: normalizedEmail,
  };
}

function validateTenantEnvelope(
  envelope: ApiSuccessEnvelope<unknown, unknown>,
): ApiSuccessEnvelope<PlatformTenant, PlatformResponseMeta> {
  if (!isPlatformTenant(envelope.data) || !isResponseMeta(envelope.meta)) {
    throw invalidResponse(envelope.meta);
  }
  return { data: envelope.data, meta: envelope.meta };
}

function validateTenantCreateEnvelope(
  envelope: ApiSuccessEnvelope<unknown, unknown>,
): ApiSuccessEnvelope<PlatformTenantCreateRead, PlatformResponseMeta> {
  if (
    !isRecord(envelope.data) ||
    !hasExactKeys(envelope.data, [
      ...PLATFORM_TENANT_KEYS,
      "initial_admin",
    ]) ||
    !isInitialAdminRead(envelope.data.initial_admin) ||
    !isResponseMeta(envelope.meta)
  ) {
    throw invalidResponse(envelope.meta);
  }

  const data = envelope.data;
  const initialAdmin = data.initial_admin;
  if (!isInitialAdminRead(initialAdmin)) {
    throw invalidResponse(envelope.meta);
  }
  const tenant = Object.fromEntries(
    PLATFORM_TENANT_KEYS.map((key) => [key, data[key]]),
  );
  if (!isPlatformTenant(tenant)) {
    throw invalidResponse(envelope.meta);
  }

  return {
    data: {
      ...tenant,
      initial_admin: initialAdmin,
    },
    meta: envelope.meta,
  };
}

function validateInitialAdminEnvelope(
  envelope: ApiSuccessEnvelope<unknown, unknown>,
): ApiSuccessEnvelope<
  PlatformTenantInitialAdminRead,
  PlatformResponseMeta
> {
  if (
    !isInitialAdminRead(envelope.data) ||
    !isResponseMeta(envelope.meta)
  ) {
    throw invalidResponse(envelope.meta);
  }
  return {
    data: envelope.data,
    meta: envelope.meta,
  };
}

function validateInitialAdminManualLinkEnvelope(
  envelope: ApiSuccessEnvelope<unknown, unknown>,
  tenantId: string,
): ApiSuccessEnvelope<
  PlatformTenantInitialAdminManualLinkRead,
  PlatformResponseMeta
> {
  if (
    !isRecord(envelope) ||
    !hasExactKeys(envelope, ["data", "meta"]) ||
    !isInitialAdminManualLinkRead(envelope.data, tenantId) ||
    !isResponseMeta(envelope.meta)
  ) {
    throw invalidResponse(envelope.meta);
  }
  if (
    responseMetaContainsManualCredential(
      envelope.meta,
      envelope.data.activation_url,
    )
  ) {
    throw invalidResponse();
  }
  return {
    data: envelope.data,
    meta: envelope.meta,
  };
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

export async function reconcilePlatformTenantCreateBySlug(
  slug: string,
): Promise<PlatformTenantCreateReconciliation> {
  if (!isTenantSlug(slug)) {
    throw invalidRequest();
  }

  const collection = await listAllPlatformTenants();
  const exactMatches = collection.tenants.filter(
    (tenant) => tenant.slug === slug,
  );
  if (exactMatches.length > 1) {
    throw invalidResponse(collection.lastMeta);
  }
  return {
    tenant: exactMatches[0] ?? null,
    meta: collection.lastMeta,
  };
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
): Promise<
  ApiSuccessEnvelope<PlatformTenantCreateRead, PlatformResponseMeta>
> {
  const requestPayload = adaptPlatformTenantCreateRequest(payload);
  const envelope = await requestPlatformAuthenticatedApiEnvelope<
    unknown,
    unknown
  >("/api/v1/platform/tenants", {
    method: "POST",
    body: requestPayload,
  });
  const validated = validateTenantCreateEnvelope(envelope);
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

export async function resendPlatformTenantInitialAdminInvitation(
  tenantId: string,
): Promise<
  ApiSuccessEnvelope<
    PlatformTenantInitialAdminRead,
    PlatformResponseMeta
  >
> {
  const envelope = await requestPlatformAuthenticatedApiEnvelope<
    unknown,
    unknown
  >(
    `/api/v1/platform/tenants/${encodeURIComponent(tenantId)}/initial-admin-invitation/resend`,
    { method: "POST" },
  );
  return validateInitialAdminEnvelope(envelope);
}

export async function createPlatformTenantInitialAdminManualLink(
  tenantId: string,
): Promise<
  ApiSuccessEnvelope<
    PlatformTenantInitialAdminManualLinkRead,
    PlatformResponseMeta
  >
> {
  const envelope = await requestPlatformAuthenticatedApiEnvelope<
    unknown,
    unknown
  >(
    `/api/v1/platform/tenants/${encodeURIComponent(tenantId)}/initial-admin-invitation/manual-link`,
    { method: "POST" },
  );
  return validateInitialAdminManualLinkEnvelope(envelope, tenantId);
}

export async function correctPlatformTenantInitialAdminInvitation(
  tenantId: string,
  payload: PlatformTenantInitialAdminCorrectionRequest,
): Promise<
  ApiSuccessEnvelope<
    PlatformTenantInitialAdminRead,
    PlatformResponseMeta
  >
> {
  const requestPayload =
    adaptPlatformTenantInitialAdminCorrectionRequest(payload);
  const envelope = await requestPlatformAuthenticatedApiEnvelope<
    unknown,
    unknown
  >(
    `/api/v1/platform/tenants/${encodeURIComponent(tenantId)}/initial-admin-invitation`,
    {
      method: "PATCH",
      body: requestPayload,
    },
  );
  return validateInitialAdminEnvelope(envelope);
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
  } else if (code === "tenant_initial_admin_unavailable") {
    message =
      "İlk yönetici işlemi mevcut durumda kullanılamıyor. Tenant ayrıntısını yenileyip daha sonra yeniden deneyin.";
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

export function isAmbiguousPlatformMutationOutcome(
  cause: unknown,
): boolean {
  if (isPostResponsePlatformSessionSupersededError(cause)) {
    return true;
  }
  if (!(cause instanceof ApiClientError)) {
    return false;
  }
  return (
    cause.code === "network_error" ||
    cause.code === "invalid_response" ||
    (cause.status !== null && cause.status >= 500 && cause.status < 600)
  );
}
