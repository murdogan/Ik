import type { ReactNode } from "react";

import { PlatformShell } from "@/components/platform/platform-shell";
import { WorkspaceBoundary } from "@/components/session/authorization-boundary";

export default function PlatformLayout({ children }: Readonly<{ children: ReactNode }>) {
  return (
    <WorkspaceBoundary scope="platform">
      <PlatformShell>{children}</PlatformShell>
    </WorkspaceBoundary>
  );
}
