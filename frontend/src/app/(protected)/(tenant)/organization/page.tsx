import type { Metadata } from "next";

import { OrganizationScreen } from "@/components/organization/organization-screen";

export const metadata: Metadata = {
  title: "Organizasyon",
};

export default function OrganizationPage() {
  return <OrganizationScreen />;
}
