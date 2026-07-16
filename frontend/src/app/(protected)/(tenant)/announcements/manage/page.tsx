import type { Metadata } from "next";

import { PermissionBoundary } from "@/components/session/authorization-boundary";
import { AnnouncementManagementScreen } from "@/components/self-service/announcement-management";
import { AUTHORIZATION_PERMISSIONS } from "@/lib/authorization";

export const metadata: Metadata = {
  title: "Duyuru yönetimi",
};

export default function AnnouncementManagementPage() {
  return (
    <PermissionBoundary permission={AUTHORIZATION_PERMISSIONS.manageTenantAnnouncements}>
      <AnnouncementManagementScreen />
    </PermissionBoundary>
  );
}
