import type { ReactNode } from "react";

import { TenantShell } from "@/components/dashboard/tenant-shell";
import { WorkspaceBoundary } from "@/components/session/authorization-boundary";

export default function TenantLayout({ children }: Readonly<{ children: ReactNode }>) {
  return (
    <WorkspaceBoundary scope="tenant">
      <TenantShell>{children}</TenantShell>
    </WorkspaceBoundary>
  );
}
