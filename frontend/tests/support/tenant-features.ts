const TENANT_FEATURE_KEYS = [
  "organization",
  "employees",
  "documents",
  "leave",
  "self_service",
  "reporting",
  "notifications",
] as const;

type TenantFeatureKey = (typeof TENANT_FEATURE_KEYS)[number];

export function tenantFeatureCatalog(
  overrides: Partial<Record<TenantFeatureKey, boolean>> = {},
) {
  return {
    features: TENANT_FEATURE_KEYS.map((key) => ({
      key,
      enabled: overrides[key] ?? true,
      source: key in overrides ? "override" : "default",
    })),
  };
}
