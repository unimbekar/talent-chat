"use client";

import { createContext, useContext, type ReactNode } from "react";

import { DEFAULT_BRAND, type Brand } from "@/lib/brand-defaults";

const BrandContext = createContext<Brand>(DEFAULT_BRAND);

export function BrandProvider({ brand, children }: { brand: Brand; children: ReactNode }) {
  return <BrandContext.Provider value={brand}>{children}</BrandContext.Provider>;
}

export function useBrand(): Brand {
  return useContext(BrandContext);
}

export function BrandMark({ className = "size-9" }: { className?: string }) {
  const brand = useBrand();
  // eslint-disable-next-line @next/next/no-img-element
  return <img src={brand.logo_url} alt="" className={`${className} shrink-0 rounded-xl`} />;
}
