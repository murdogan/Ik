import type { ReactNode } from "react";

import { AnyPermissionBoundary } from "@/components/session/authorization-boundary";
import { TenantFeatureBoundary } from "@/components/session/tenant-feature-provider";
import { AUTHORIZATION_PERMISSIONS } from "@/lib/authorization";
import { TENANT_FEATURES } from "@/lib/feature-rollout";

export default function ReportsLayout({ children }: Readonly<{ children: ReactNode }>) {
  return (
    <AnyPermissionBoundary
      permissions={[
        AUTHORIZATION_PERMISSIONS.readTenantReports,
        AUTHORIZATION_PERMISSIONS.readTeamReports,
        AUTHORIZATION_PERMISSIONS.manageEmployeeImports,
      ]}
    >
      <TenantFeatureBoundary feature={TENANT_FEATURES.reporting}>
        {children}
      </TenantFeatureBoundary>
    </AnyPermissionBoundary>
  );
}
