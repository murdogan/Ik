import { ApiClientError } from "./api-client";
import { requestAuthenticatedApi } from "./session";

const TENANT_FEATURE_KEYS = [
  "organization",
  "employees",
  "documents",
  "leave",
  "self_service",
  "reporting",
  "notifications",
] as const;

type TenantFeatureCatalogKey = (typeof TENANT_FEATURE_KEYS)[number];

export interface TenantFeatureFlag {
  key: TenantFeatureCatalogKey;
  enabled: boolean;
  source: "default" | "override";
}

interface TenantFeatureCatalog {
  features: TenantFeatureFlag[];
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function isFeature(value: unknown): value is TenantFeatureFlag {
  return (
    isRecord(value) &&
    Object.keys(value).length === 3 &&
    typeof value.key === "string" &&
    TENANT_FEATURE_KEYS.includes(value.key as TenantFeatureCatalogKey) &&
    typeof value.enabled === "boolean" &&
    (value.source === "default" || value.source === "override")
  );
}

export async function readTenantFeatures(): Promise<TenantFeatureFlag[]> {
  const data = await requestAuthenticatedApi<unknown>("/api/v1/tenant/features");
  if (
    !isRecord(data) ||
    !Array.isArray(data.features) ||
    data.features.length > TENANT_FEATURE_KEYS.length ||
    !data.features.every(isFeature) ||
    new Set(data.features.map((feature) => feature.key)).size !==
      data.features.length
  ) {
    throw new ApiClientError({ status: 200, code: "invalid_response" });
  }
  return (data as unknown as TenantFeatureCatalog).features;
}
