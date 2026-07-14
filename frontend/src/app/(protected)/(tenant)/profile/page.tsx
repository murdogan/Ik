import type { Metadata } from "next";

import { SelfProfileScreen } from "@/components/profile/self-profile-screen";

export const metadata: Metadata = {
  title: "Profilim",
};

export default function ProfilePage() {
  return <SelfProfileScreen />;
}
