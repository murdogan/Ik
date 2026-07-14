import type { Metadata } from "next";

import { ProfileChangeRequestDetailScreen } from "@/components/profile-change-requests/profile-change-request-detail-screen";

export const metadata: Metadata = {
  title: "Değişiklik talebi",
};

export default async function ProfileChangeRequestDetailPage({
  params,
}: {
  params: Promise<{ requestId: string }>;
}) {
  const { requestId } = await params;
  return (
    <ProfileChangeRequestDetailScreen key={requestId} requestId={requestId} />
  );
}
