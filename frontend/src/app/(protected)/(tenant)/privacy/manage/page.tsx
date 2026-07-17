import type { Metadata } from "next";

import { PrivacyManagementWorkspace } from "@/components/privacy/privacy-management-workspace";
import { AnyPermissionBoundary } from "@/components/session/authorization-boundary";
import { AUTHORIZATION_PERMISSIONS } from "@/lib/authorization";

export const metadata: Metadata = {
  title: "Gizlilik uyumu",
};

export default function PrivacyManagementPage() {
  return (
    <AnyPermissionBoundary
      permissions={[
        AUTHORIZATION_PERMISSIONS.readTenantPrivacyCompliance,
        AUTHORIZATION_PERMISSIONS.manageTenantPrivacyNotices,
        AUTHORIZATION_PERMISSIONS.manageTenantRetentionPolicies,
      ]}
    >
      <PrivacyManagementWorkspace />
    </AnyPermissionBoundary>
  );
}
