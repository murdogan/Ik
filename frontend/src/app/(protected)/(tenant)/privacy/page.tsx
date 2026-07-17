import type { Metadata } from "next";

import { PrivacyCenter } from "@/components/privacy/privacy-center";
import { PermissionBoundary } from "@/components/session/authorization-boundary";
import { AUTHORIZATION_PERMISSIONS } from "@/lib/authorization";

export const metadata: Metadata = {
  title: "Gizlilik merkezi",
};

export default function PrivacyPage() {
  return (
    <PermissionBoundary permission={AUTHORIZATION_PERMISSIONS.readOwnPrivacyNotice}>
      <PrivacyCenter />
    </PermissionBoundary>
  );
}
