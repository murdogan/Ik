import type { Metadata } from "next";

import { TeamMemberProfileScreen } from "@/components/team/team-member-profile-screen";

export const metadata: Metadata = {
  title: "Ekip profili",
};

export default async function TeamMemberProfilePage({
  params,
}: {
  params: Promise<{ employeeId: string }>;
}) {
  const { employeeId } = await params;
  return <TeamMemberProfileScreen key={employeeId} employeeId={employeeId} />;
}
