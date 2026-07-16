import type { ReactNode } from "react";

import { AnyPermissionBoundary } from "@/components/session/authorization-boundary";
import { TenantFeatureBoundary } from "@/components/session/tenant-feature-provider";
import { AUTHORIZATION_PERMISSIONS } from "@/lib/authorization";
import { TENANT_FEATURES } from "@/lib/feature-rollout";

export default function RequestsLayout({ children }: Readonly<{ children: ReactNode }>) {
  return (
    <AnyPermissionBoundary
      permissions={[
        AUTHORIZATION_PERMISSIONS.readOwnRequests,
        AUTHORIZATION_PERMISSIONS.readTeamRequests,
        AUTHORIZATION_PERMISSIONS.readTenantRequests,
      ]}
    >
      <TenantFeatureBoundary feature={TENANT_FEATURES.selfService}>
        {children}
      </TenantFeatureBoundary>
    </AnyPermissionBoundary>
  );
}
