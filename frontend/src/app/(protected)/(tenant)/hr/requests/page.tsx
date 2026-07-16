import type { Metadata } from "next";

import { PermissionBoundary } from "@/components/session/authorization-boundary";
import { TenantFeatureBoundary } from "@/components/session/tenant-feature-provider";
import { HrRequestWorkspace } from "@/components/self-service/hr-request-workspace";
import { AUTHORIZATION_PERMISSIONS } from "@/lib/authorization";
import { TENANT_FEATURES } from "@/lib/feature-rollout";

export const metadata: Metadata = {
  title: "HR talepleri",
};

export default function HrRequestsPage() {
  return (
    <PermissionBoundary permission={AUTHORIZATION_PERMISSIONS.manageTenantDocumentRequests}>
      <PermissionBoundary permission={AUTHORIZATION_PERMISSIONS.readTenantRequests}>
        <TenantFeatureBoundary feature={TENANT_FEATURES.selfService}>
          <HrRequestWorkspace />
        </TenantFeatureBoundary>
      </PermissionBoundary>
    </PermissionBoundary>
  );
}
