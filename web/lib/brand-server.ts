import { DEFAULT_BRAND, type Brand } from "@/lib/brand-defaults";

const api = process.env.API_INTERNAL_URL || "http://127.0.0.1:8000";

export async function loadBrand(): Promise<Brand> {
  try {
    const response = await fetch(`${api}/public/config`, { next: { revalidate: 300 } });
    if (!response.ok) return DEFAULT_BRAND;
    const data = (await response.json()) as Partial<Brand>;
    return { ...DEFAULT_BRAND, ...Object.fromEntries(Object.entries(data).filter(([, value]) => value != null && value !== "")) };
  } catch {
    return DEFAULT_BRAND;
  }
}

function rgb(hex: string): [number, number, number] | null {
  const match = /^#?([0-9a-f]{6})$/i.exec(hex.trim());
  if (!match) return null;
  const value = parseInt(match[1], 16);
  return [(value >> 16) & 255, (value >> 8) & 255, value & 255];
}

function mix(color: [number, number, number], target: number, amount: number): string {
  return color.map((channel) => Math.round(channel + (target - channel) * amount)).join(" ");
}

export function brandStyle(accent: string): Record<string, string> {
  const color = rgb(accent) || rgb(DEFAULT_BRAND.accent)!;
  return {
    "--brand": color.join(" "),
    "--brand-deep": mix(color, 0, 0.22),
    "--brand-soft": mix(color, 255, 0.45),
  };
}
