import type { Metadata } from "next";

import { PermissionBoundary } from "@/components/session/authorization-boundary";
import { TenantFeatureBoundary } from "@/components/session/tenant-feature-provider";
import { NotificationsScreen } from "@/components/self-service/notifications-screen";
import { AUTHORIZATION_PERMISSIONS } from "@/lib/authorization";
import { TENANT_FEATURES } from "@/lib/feature-rollout";

export const metadata: Metadata = {
  title: "Bildirimler",
};

export default function NotificationsPage() {
  return (
    <PermissionBoundary permission={AUTHORIZATION_PERMISSIONS.readOwnNotifications}>
      <TenantFeatureBoundary feature={TENANT_FEATURES.notifications}>
        <NotificationsScreen />
      </TenantFeatureBoundary>
    </PermissionBoundary>
  );
}
