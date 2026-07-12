import type { ReactNode } from "react";

import { TenantShell } from "@/components/dashboard/tenant-shell";
import { SessionProvider } from "@/components/session/session-provider";

export default function ProtectedLayout({ children }: Readonly<{ children: ReactNode }>) {
  return (
    <SessionProvider>
      <TenantShell>{children}</TenantShell>
    </SessionProvider>
  );
}
