import type { MetadataRoute } from "next";

import { loadBrand } from "@/lib/brand-server";

export default async function manifest(): Promise<MetadataRoute.Manifest> {
  const brand = await loadBrand();
  const shortName = brand.company_name.replace(/\b(Inc|LLC|Ltd|Corp)\.?$/i, "").trim() || brand.company_name;
  const shortcut = [{ src: "/icons/shortcut-96.png", sizes: "96x96", type: "image/png" }];
  return {
    id: "/admin/dashboard",
    name: `${brand.company_name} Recruiter Desk`,
    short_name: `${shortName} Desk`.slice(0, 24),
    description: `Jobs, candidates, the pipeline, and the desk assistant for ${brand.company_name.replace(/\.$/, "")}.`,
    start_url: "/admin/dashboard?source=app",
    scope: "/",
    display: "standalone",
    display_override: ["window-controls-overlay", "standalone"],
    orientation: "any",
    background_color: "#f7f4ee",
    theme_color: "#151413",
    categories: ["business", "productivity"],
    icons: [
      { src: "/icons/icon-192.png", sizes: "192x192", type: "image/png", purpose: "any" },
      { src: "/icons/icon-512.png", sizes: "512x512", type: "image/png", purpose: "any" },
      { src: "/icons/maskable-192.png", sizes: "192x192", type: "image/png", purpose: "maskable" },
      { src: "/icons/maskable-512.png", sizes: "512x512", type: "image/png", purpose: "maskable" },
    ],
    shortcuts: [
      { name: "Ask the desk", short_name: "Ask", url: "/admin/share?open=1", icons: shortcut },
      { name: "Pipeline", url: "/admin/pipeline", icons: shortcut },
      { name: "Candidates", url: "/admin/candidates", icons: shortcut },
      { name: "Jobs", url: "/admin/jobs", icons: shortcut },
    ],
    share_target: {
      action: "/admin/share",
      method: "GET",
      params: { title: "title", text: "text", url: "url" },
    },
  } as MetadataRoute.Manifest;
}
