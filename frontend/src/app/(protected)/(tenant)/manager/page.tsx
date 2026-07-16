import type { Metadata } from "next";

import { PermissionBoundary } from "@/components/session/authorization-boundary";
import { TenantFeatureBoundary } from "@/components/session/tenant-feature-provider";
import { ManagerPortalScreen } from "@/components/self-service/manager-portal";
import { AUTHORIZATION_PERMISSIONS } from "@/lib/authorization";
import { TENANT_FEATURES } from "@/lib/feature-rollout";

export const metadata: Metadata = {
  title: "Yönetici alanı",
};

export default function ManagerPortalPage() {
  return (
    <PermissionBoundary permission={AUTHORIZATION_PERMISSIONS.readTeamLeave}>
      <PermissionBoundary permission={AUTHORIZATION_PERMISSIONS.approveTeamLeave}>
        <PermissionBoundary permission={AUTHORIZATION_PERMISSIONS.readTeamEmployees}>
          <TenantFeatureBoundary feature={TENANT_FEATURES.selfService}>
            <TenantFeatureBoundary feature={TENANT_FEATURES.leave}>
              <ManagerPortalScreen />
            </TenantFeatureBoundary>
          </TenantFeatureBoundary>
        </PermissionBoundary>
      </PermissionBoundary>
    </PermissionBoundary>
  );
}
