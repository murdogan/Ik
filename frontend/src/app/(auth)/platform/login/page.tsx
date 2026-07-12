import type { Metadata } from "next";

import { AuthShell } from "@/components/auth/auth-shell";
import { PlatformLoginForm } from "@/components/auth/platform-login-form";

export const metadata: Metadata = {
  title: "Platform yönetimi girişi",
};

export default function PlatformLoginPage() {
  return (
    <AuthShell
      surface="platform"
      eyebrow="Ayrı platform güvenlik alanı"
      title="Platform yönetimine giriş"
      description="Yalnız yetkili platform yöneticileri için ayrılmış oturum alanı. Kurum veya organizasyon seçimi yapılmaz."
    >
      <PlatformLoginForm />
    </AuthShell>
  );
}
