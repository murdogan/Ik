import type { Metadata } from "next";

import { AuthShell } from "@/components/auth/auth-shell";
import { LoginForm } from "@/components/auth/login-form";
import { validatedTenantSlug } from "@/lib/auth-contracts";

export const metadata: Metadata = {
  title: "Giriş yap",
};

interface LoginPageProps {
  searchParams: Promise<{ tenant?: string | string[] }>;
}

export default async function LoginPage({ searchParams }: LoginPageProps) {
  const tenant = validatedTenantSlug((await searchParams).tenant);

  return (
    <AuthShell
      eyebrow="Güvenli kurum girişi"
      title="Tekrar hoş geldiniz"
      description="Kurum kodunuz ve çalışma e-postanızla Wealthy Falcon HR hesabınıza giriş yapın."
    >
      <LoginForm initialTenantSlug={tenant} />
    </AuthShell>
  );
}
