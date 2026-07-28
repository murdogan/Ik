import type { Metadata } from "next";

import { TenantDetailScreen } from "@/components/platform/tenant-detail-screen";

export const metadata: Metadata = {
  title: "Tenant ayrıntısı",
};

export default async function PlatformTenantDetailPage({
  params,
}: {
  params: Promise<{ tenantId: string }>;
}) {
  const { tenantId } = await params;
  return <TenantDetailScreen key={tenantId} tenantId={tenantId} />;
}
