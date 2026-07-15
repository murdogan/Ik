import type { Metadata } from "next";

import { DocumentTypesScreen } from "@/components/documents/document-types-screen";

export const metadata: Metadata = {
  title: "Belge türleri",
};

export default function DocumentTypesPage() {
  return <DocumentTypesScreen />;
}
