export const TENANT_FEATURES = {
  organization: "organization",
} as const;

export type TenantFeatureKey =
  (typeof TENANT_FEATURES)[keyof typeof TENANT_FEATURES];
