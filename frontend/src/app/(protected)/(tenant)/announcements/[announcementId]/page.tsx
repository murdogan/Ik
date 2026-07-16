import type { Metadata } from "next";

import { PermissionBoundary } from "@/components/session/authorization-boundary";
import { AnnouncementDetailScreen } from "@/components/self-service/announcement-detail";
import { AUTHORIZATION_PERMISSIONS } from "@/lib/authorization";

export const metadata: Metadata = {
  title: "Duyuru",
};

export default async function AnnouncementDetailPage({
  params,
}: {
  params: Promise<{ announcementId: string }>;
}) {
  const { announcementId } = await params;
  return (
    <PermissionBoundary permission={AUTHORIZATION_PERMISSIONS.readOwnAnnouncements}>
      <AnnouncementDetailScreen
        key={announcementId}
        announcementId={announcementId}
      />
    </PermissionBoundary>
  );
}
