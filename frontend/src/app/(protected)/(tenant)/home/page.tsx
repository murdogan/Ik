import type { Metadata } from "next";

import { PermissionBoundary } from "@/components/session/authorization-boundary";
import { TenantFeatureBoundary } from "@/components/session/tenant-feature-provider";
import { SelfServiceHomeScreen } from "@/components/self-service/self-service-home";
import { AUTHORIZATION_PERMISSIONS } from "@/lib/authorization";
import { TENANT_FEATURES } from "@/lib/feature-rollout";

export const metadata: Metadata = {
  title: "Çalışan ana sayfası",
};

export default function SelfServiceHomePage() {
  return (
    <PermissionBoundary permission={AUTHORIZATION_PERMISSIONS.readOwnSelfService}>
      <TenantFeatureBoundary feature={TENANT_FEATURES.selfService}>
        <SelfServiceHomeScreen />
      </TenantFeatureBoundary>
    </PermissionBoundary>
  );
}
