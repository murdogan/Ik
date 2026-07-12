import type { ReactNode } from "react";

import { PlatformShell } from "@/components/platform/platform-shell";
import { PlatformWorkspaceBoundary } from "@/components/session/platform-authorization-boundary";
import { PlatformSessionProvider } from "@/components/session/platform-session-provider";

export default function PlatformLayout({ children }: Readonly<{ children: ReactNode }>) {
  return (
    <PlatformSessionProvider>
      <PlatformWorkspaceBoundary>
        <PlatformShell>{children}</PlatformShell>
      </PlatformWorkspaceBoundary>
    </PlatformSessionProvider>
  );
}
