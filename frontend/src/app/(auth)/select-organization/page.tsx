import type { Metadata } from "next";

import { AuthShell } from "@/components/auth/auth-shell";
import { OrganizationSelectionForm } from "@/components/auth/organization-selection-form";

export const metadata: Metadata = {
  title: "Kurum seçin",
};

export default function SelectOrganizationPage() {
  return (
    <AuthShell
      eyebrow="Güvenli kurum seçimi"
      title="Çalışma alanınızı açın"
      description="Her kurum ayrı bir güvenli çalışma alanıdır. Devam etmek istediğiniz şirketi seçin."
    >
      <OrganizationSelectionForm />
    </AuthShell>
  );
}
