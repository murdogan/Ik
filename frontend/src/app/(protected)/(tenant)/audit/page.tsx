import type { Metadata } from "next";

import { AuditExplorer } from "@/components/audit/audit-explorer";

export const metadata: Metadata = {
  title: "Denetim kayıtları",
};

export default function AuditPage() {
  return <AuditExplorer scope="tenant" />;
}
