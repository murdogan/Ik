export const TENANT_FEATURES = {
  organization: "organization",
  leave: "leave",
} as const;

export type TenantFeatureKey =
  (typeof TENANT_FEATURES)[keyof typeof TENANT_FEATURES];
