import type { Metadata } from "next";
import type { CSSProperties, ReactNode } from "react";
import "./globals.css";

import { BrandProvider } from "@/components/brand";
import { brandStyle, loadBrand } from "@/lib/brand-server";

export async function generateMetadata(): Promise<Metadata> {
  const brand = await loadBrand();
  return {
    title: { default: `${brand.company_name} · Careers`, template: `%s · ${brand.company_name}` },
    description: `${brand.tagline}. Ask about open roles at ${brand.company_name}.`,
    icons: { icon: brand.logo_url },
  };
}

export default async function RootLayout({ children }: { children: ReactNode }) {
  const brand = await loadBrand();
  return (
    <html lang="en" style={brandStyle(brand.accent) as CSSProperties}>
      <body className="min-h-screen bg-desk font-sans text-ink antialiased">
        <BrandProvider brand={brand}>{children}</BrandProvider>
      </body>
    </html>
  );
}
