import type { Metadata } from "next";

import { RequestDetailScreen } from "@/components/self-service/request-detail";

export const metadata: Metadata = {
  title: "Talep ayrıntısı",
};

export default async function RequestDetailPage({
  params,
}: {
  params: Promise<{ requestId: string }>;
}) {
  const { requestId } = await params;
  return <RequestDetailScreen key={requestId} requestId={requestId} />;
}
