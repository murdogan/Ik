import type { ReactNode } from "react";

import { PermissionBoundary } from "@/components/session/authorization-boundary";
import { AUTHORIZATION_PERMISSIONS } from "@/lib/authorization";

export default function ProfileChangeRequestsLayout({
  children,
}: Readonly<{ children: ReactNode }>) {
  return (
    <PermissionBoundary permission={AUTHORIZATION_PERMISSIONS.readTenantEmployees}>
      <PermissionBoundary permission={AUTHORIZATION_PERMISSIONS.updateEmployees}>
        {children}
      </PermissionBoundary>
    </PermissionBoundary>
  );
}
