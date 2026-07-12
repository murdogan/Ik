import type { Metadata } from "next";

import { AuthShell } from "@/components/auth/auth-shell";
import { ResetPasswordForm } from "@/components/auth/reset-password-form";

export const metadata: Metadata = {
  title: "Yeni parola belirle",
};

export default function ResetPasswordPage() {
  return (
    <AuthShell
      eyebrow="Hesap kurtarma"
      title="Yeni parolanızı belirleyin"
      description="Parolanızı güvenli biçimde yenilemek için iki alana da aynı yeni parolayı yazın. Bu bağlantı yalnızca bir kez kullanılabilir."
    >
      <ResetPasswordForm />
    </AuthShell>
  );
}
