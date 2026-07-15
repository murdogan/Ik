import type { ReactNode } from "react";

import { PermissionBoundary } from "@/components/session/authorization-boundary";
import { AUTHORIZATION_PERMISSIONS } from "@/lib/authorization";

export default function LeaveApprovalsLayout({ children }: Readonly<{ children: ReactNode }>) {
  return (
    <PermissionBoundary permission={AUTHORIZATION_PERMISSIONS.readTeamLeave}>
      <PermissionBoundary permission={AUTHORIZATION_PERMISSIONS.approveTeamLeave}>
        {children}
      </PermissionBoundary>
    </PermissionBoundary>
  );
}
