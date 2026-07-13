import type { Metadata } from "next";

import { EmployeeDirectoryScreen } from "@/components/employees/employee-directory-screen";

export const metadata: Metadata = {
  title: "Çalışan özeti",
};

export default async function EmployeeSummaryPage({
  params,
}: {
  params: Promise<{ employeeId: string }>;
}) {
  const { employeeId } = await params;
  return <EmployeeDirectoryScreen selectedEmployeeId={employeeId} />;
}
