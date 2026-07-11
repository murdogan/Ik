import type { Metadata } from "next";

import { TenantShell } from "@/components/dashboard/tenant-shell";

export const metadata: Metadata = {
  title: "Genel bakış",
};

export default function DashboardPage() {
  return <TenantShell />;
}
