import type { Metadata } from "next";

import { TenantManagementScreen } from "@/components/platform/tenant-management-screen";

export const metadata: Metadata = {
  title: "Tenant yönetimi",
};

export default function PlatformTenantsPage() {
  return <TenantManagementScreen />;
}
