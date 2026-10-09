import type { Metadata, Viewport } from "next";
import type { CSSProperties, ReactNode } from "react";
import "./globals.css";

import { BrandProvider } from "@/components/brand";
import { AppShell } from "@/components/app-shell";
import { brandStyle, loadBrand } from "@/lib/brand-server";

export async function generateMetadata(): Promise<Metadata> {
  const brand = await loadBrand();
  return {
    title: { default: `${brand.company_name} · Careers`, template: `%s · ${brand.company_name}` },
    description: `${brand.tagline}. Ask about open roles at ${brand.company_name}.`,
    applicationName: `${brand.company_name} Recruiter Desk`,
    icons: {
      icon: [{ url: "/icons/icon-192.png", sizes: "192x192", type: "image/png" }, { url: brand.logo_url }],
      apple: [{ url: "/icons/apple-touch-icon.png", sizes: "180x180" }],
    },
    appleWebApp: { capable: true, title: "Recruiter Desk", statusBarStyle: "black-translucent" },
    formatDetection: { telephone: false },
  };
}

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  viewportFit: "cover",
  interactiveWidget: "resizes-content",
  themeColor: "#151413",
};

export default async function RootLayout({ children }: { children: ReactNode }) {
  const brand = await loadBrand();
  return (
    <html lang="en" style={brandStyle(brand.accent) as CSSProperties}>
      <body className="min-h-screen bg-desk font-sans text-ink antialiased">
        <BrandProvider brand={brand}>
          {children}
          <AppShell />
        </BrandProvider>
      </body>
    </html>
  );
}
