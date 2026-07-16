import type { Metadata } from "next";

import { PermissionBoundary } from "@/components/session/authorization-boundary";
import { AnnouncementsScreen } from "@/components/self-service/announcements-screen";
import { AUTHORIZATION_PERMISSIONS } from "@/lib/authorization";

export const metadata: Metadata = {
  title: "Duyurular",
};

export default function AnnouncementsPage() {
  return (
    <PermissionBoundary permission={AUTHORIZATION_PERMISSIONS.readOwnAnnouncements}>
      <AnnouncementsScreen />
    </PermissionBoundary>
  );
}
