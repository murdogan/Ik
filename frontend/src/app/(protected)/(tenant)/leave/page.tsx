import type { Metadata } from "next";

import { OwnLeaveScreen } from "@/components/leave/own-leave-screen";
import { PermissionBoundary } from "@/components/session/authorization-boundary";
import { AUTHORIZATION_PERMISSIONS } from "@/lib/authorization";

export const metadata: Metadata = {
  title: "İzinlerim",
};

export default function OwnLeavePage() {
  return (
    <PermissionBoundary permission={AUTHORIZATION_PERMISSIONS.readOwnLeave}>
      <OwnLeaveScreen />
    </PermissionBoundary>
  );
}
