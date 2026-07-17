import type { Metadata } from "next";

import { ReportingWorkspace } from "@/components/reporting/reporting-workspace";

export const metadata: Metadata = {
  title: "Raporlar ve aktarımlar",
};

export default function ReportsPage() {
  return <ReportingWorkspace />;
}
