import type { ReactNode } from "react";

import { SessionProvider } from "@/components/session/session-provider";

export default function ProtectedLayout({ children }: Readonly<{ children: ReactNode }>) {
  return <SessionProvider>{children}</SessionProvider>;
}
