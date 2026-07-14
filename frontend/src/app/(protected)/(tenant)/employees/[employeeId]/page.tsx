import type { Metadata } from "next";

import { Employee360Screen } from "@/components/employees/employee-360-screen";

export const metadata: Metadata = {
  title: "Çalışan 360",
};

export default async function EmployeeSummaryPage({
  params,
}: {
  params: Promise<{ employeeId: string }>;
}) {
  const { employeeId } = await params;
  return <Employee360Screen key={employeeId} employeeId={employeeId} />;
}
