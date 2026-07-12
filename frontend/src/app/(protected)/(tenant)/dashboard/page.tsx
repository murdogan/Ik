import type { Metadata } from "next";

import { DashboardOverview } from "@/components/dashboard/dashboard-overview";

export const metadata: Metadata = {
  title: "Genel bakış",
};

export default function DashboardPage() {
  return <DashboardOverview />;
}
