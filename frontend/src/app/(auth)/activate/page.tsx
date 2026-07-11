import type { Metadata } from "next";

import { ActivationForm } from "@/components/auth/activation-form";
import { AuthShell } from "@/components/auth/auth-shell";

export const metadata: Metadata = {
  title: "Hesabı etkinleştir",
};

export default function ActivatePage() {
  return (
    <AuthShell
      eyebrow="Hesap kurulumu"
      title="Davetinizi tamamlayın"
      description="Güçlü bir parola belirleyin. Davet bağlantınız hesabınızı doğru kurumla güvenli biçimde eşleştirir."
    >
      <ActivationForm />
    </AuthShell>
  );
}
