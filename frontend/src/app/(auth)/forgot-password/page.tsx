import type { Metadata } from "next";

import { AuthShell } from "@/components/auth/auth-shell";
import { ForgotPasswordForm } from "@/components/auth/forgot-password-form";

export const metadata: Metadata = {
  title: "Parolamı unuttum",
};

export default function ForgotPasswordPage() {
  return (
    <AuthShell
      eyebrow="Hesap kurtarma"
      title="Parolanızı yenileyin"
      description="Hesabınızda kullandığınız e-posta adresini girin. Bir hesap eşleşirse güvenli yenileme bağlantısını e-postayla göndeririz."
    >
      <ForgotPasswordForm />
    </AuthShell>
  );
}
