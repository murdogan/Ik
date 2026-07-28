import type { ReactNode } from "react";

import { PlatformPermissionBoundary } from "@/components/session/platform-authorization-boundary";
import { AUTHORIZATION_PERMISSIONS } from "@/lib/authorization";

export default function PlatformTenantsLayout({
  children,
}: Readonly<{ children: ReactNode }>) {
  return (
    <PlatformPermissionBoundary
      permission={AUTHORIZATION_PERMISSIONS.readPlatformTenants}
    >
      {children}
    </PlatformPermissionBoundary>
  );
}
