import type { Metadata } from "next";

import { ProfileChangeRequestQueueScreen } from "@/components/profile-change-requests/profile-change-request-queue-screen";

export const metadata: Metadata = {
  title: "Değişiklik talepleri",
};

export default function ProfileChangeRequestsPage() {
  return <ProfileChangeRequestQueueScreen />;
}
