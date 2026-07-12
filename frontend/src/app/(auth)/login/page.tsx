import type { Metadata } from "next";

import { AuthShell } from "@/components/auth/auth-shell";
import { LoginForm } from "@/components/auth/login-form";

export const metadata: Metadata = {
  title: "Giriş yap",
};

export default function LoginPage() {
  return (
    <AuthShell
      eyebrow="Güvenli kurum girişi"
      title="Tekrar hoş geldiniz"
      description="Çalışma e-postanız ve parolanızla Wealthy Falcon HR hesabınıza giriş yapın."
    >
      <LoginForm />
    </AuthShell>
  );
}
