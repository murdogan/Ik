import type { Metadata } from "next";

import { ActivationForm } from "@/components/auth/activation-form";
import { AuthShell } from "@/components/auth/auth-shell";

export const metadata: Metadata = {
  title: "Hesabı etkinleştir",
};

export default function ActivatePage() {
  return (
    <AuthShell
      eyebrow="Kurum daveti"
      title="Davetinizi tamamlayın"
      description="İlk kez hesap oluşturuyorsanız yeni bir parola seçin; mevcut hesabınız varsa kullandığınız parolayı girin. Davet bağlantısı üyeliğinizi doğru kurumla eşleştirir."
    >
      <ActivationForm />
    </AuthShell>
  );
}
