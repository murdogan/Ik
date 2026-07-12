import type { Metadata } from "next";

import { AuditExplorer } from "@/components/audit/audit-explorer";

export const metadata: Metadata = {
  title: "Platform denetim kayıtları",
};

export default function PlatformAuditPage() {
  return <AuditExplorer scope="platform" />;
}
