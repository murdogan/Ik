import type { Metadata } from "next";

import { SetupReadinessScreen } from "@/components/setup/setup-readiness-screen";

export const metadata: Metadata = {
  title: "Kurulum hazırlığı",
};

export default function SetupPage() {
  return <SetupReadinessScreen />;
}
