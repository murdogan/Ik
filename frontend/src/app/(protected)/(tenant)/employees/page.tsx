import type { Metadata } from "next";

import { EmployeeDirectoryScreen } from "@/components/employees/employee-directory-screen";

export const metadata: Metadata = {
  title: "Çalışanlar",
};

export default function EmployeesPage() {
  return <EmployeeDirectoryScreen />;
}
