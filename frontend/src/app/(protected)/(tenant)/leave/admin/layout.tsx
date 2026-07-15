import type { ReactNode } from "react";

import { PermissionBoundary } from "@/components/session/authorization-boundary";
import { AUTHORIZATION_PERMISSIONS } from "@/lib/authorization";

export default function LeaveAdminLayout({ children }: Readonly<{ children: ReactNode }>) {
  return (
    <PermissionBoundary permission={AUTHORIZATION_PERMISSIONS.readTenantLeave}>
      <PermissionBoundary permission={AUTHORIZATION_PERMISSIONS.manageTenantLeave}>
        {children}
      </PermissionBoundary>
    </PermissionBoundary>
  );
}
