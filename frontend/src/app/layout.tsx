import type { Metadata, Viewport } from "next";
import type { ReactNode } from "react";

import { OrganizationSelectionProvider } from "@/components/auth/organization-selection-provider";
import { ServiceWorkerRegistration } from "@/components/pwa/service-worker-registration";

import "./globals.css";

export const metadata: Metadata = {
  applicationName: "Wealthy Falcon HR",
  title: {
    default: "Wealthy Falcon HR",
    template: "%s | Wealthy Falcon HR",
  },
  description: "Wealthy Falcon HR güvenli hesap erişimi",
  manifest: "/manifest.webmanifest",
  icons: {
    icon: [
      { url: "/icon-192.png", sizes: "192x192", type: "image/png" },
      { url: "/icon-512.png", sizes: "512x512", type: "image/png" },
    ],
    apple: [{ url: "/icon-192.png", sizes: "192x192", type: "image/png" }],
  },
  appleWebApp: {
    capable: true,
    title: "Wealthy Falcon HR",
    statusBarStyle: "default",
  },
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  themeColor: "#1f7a56",
  viewportFit: "cover",
};

export default function RootLayout({ children }: Readonly<{ children: ReactNode }>) {
  return (
    <html lang="tr">
      <body>
        <ServiceWorkerRegistration />
        <OrganizationSelectionProvider>{children}</OrganizationSelectionProvider>
      </body>
    </html>
  );
}
