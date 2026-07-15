import type { Metadata } from "next";

import { LeaveAdminScreen } from "@/components/leave/leave-admin-screen";

export const metadata: Metadata = {
  title: "İzin yönetimi",
};

export default function LeaveAdminPage() {
  return <LeaveAdminScreen />;
}
