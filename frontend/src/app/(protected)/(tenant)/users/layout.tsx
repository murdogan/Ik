import type { ReactNode } from "react";

import { PermissionBoundary } from "@/components/session/authorization-boundary";
import { AUTHORIZATION_PERMISSIONS } from "@/lib/authorization";

export default function UsersLayout({ children }: Readonly<{ children: ReactNode }>) {
  return (
    <PermissionBoundary permission={AUTHORIZATION_PERMISSIONS.readUsers}>
      {children}
    </PermissionBoundary>
  );
}
