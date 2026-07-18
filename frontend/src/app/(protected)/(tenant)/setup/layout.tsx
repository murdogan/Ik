import type { ReactNode } from "react";

import { PermissionBoundary } from "@/components/session/authorization-boundary";
import { AUTHORIZATION_PERMISSIONS } from "@/lib/authorization";

export default function SetupLayout({
  children,
}: Readonly<{ children: ReactNode }>) {
  return (
    <PermissionBoundary permission={AUTHORIZATION_PERMISSIONS.updateOrganization}>
      {children}
    </PermissionBoundary>
  );
}
