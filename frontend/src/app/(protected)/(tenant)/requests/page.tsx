import type { Metadata } from "next";

import { RequestsScreen } from "@/components/self-service/requests-screen";

export const metadata: Metadata = {
  title: "Talepler",
};

export default function RequestsPage() {
  return <RequestsScreen />;
}
