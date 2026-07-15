import type { ReactNode } from "react";

import { TenantFeatureBoundary } from "@/components/session/tenant-feature-provider";
import { TENANT_FEATURES } from "@/lib/feature-rollout";

export default function LeaveLayout({ children }: Readonly<{ children: ReactNode }>) {
  return (
    <TenantFeatureBoundary feature={TENANT_FEATURES.leave}>
      {children}
    </TenantFeatureBoundary>
  );
}
