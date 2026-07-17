export const TENANT_FEATURES = {
  organization: "organization",
  leave: "leave",
  selfService: "self_service",
  notifications: "notifications",
  reporting: "reporting",
} as const;

export type TenantFeatureKey =
  (typeof TENANT_FEATURES)[keyof typeof TENANT_FEATURES];
