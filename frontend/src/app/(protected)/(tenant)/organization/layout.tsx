import type { ReactNode } from "react";

import { PermissionBoundary } from "@/components/session/authorization-boundary";
import { TenantFeatureBoundary } from "@/components/session/tenant-feature-provider";
import { AUTHORIZATION_PERMISSIONS } from "@/lib/authorization";
import { TENANT_FEATURES } from "@/lib/feature-rollout";

export default function OrganizationLayout({
  children,
}: Readonly<{ children: ReactNode }>) {
  return (
    <PermissionBoundary permission={AUTHORIZATION_PERMISSIONS.readOrganization}>
      <TenantFeatureBoundary feature={TENANT_FEATURES.organization}>
        {children}
      </TenantFeatureBoundary>
    </PermissionBoundary>
  );
}
