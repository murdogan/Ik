import type { ReactNode } from "react";

import { TenantShell } from "@/components/dashboard/tenant-shell";
import { WorkspaceBoundary } from "@/components/session/authorization-boundary";
import { SessionProvider } from "@/components/session/session-provider";

export default function TenantLayout({ children }: Readonly<{ children: ReactNode }>) {
  return (
    <SessionProvider>
      <WorkspaceBoundary scope="tenant">
        <TenantShell>{children}</TenantShell>
      </WorkspaceBoundary>
    </SessionProvider>
  );
}
