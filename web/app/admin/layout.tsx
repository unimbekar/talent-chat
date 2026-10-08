"use client";

import { type ReactNode, useEffect, useState } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { BarChart3, Briefcase, ClipboardCheck, FolderInput, LayoutDashboard, LogOut, Route, Search, Target, Users } from "lucide-react";

import { AssistantPanel, type PanelMode } from "@/components/assistant/assistant-panel";
import { BrandMark, useBrand } from "@/components/brand";
import { QuickSearch } from "@/components/quick-search";

const PANEL_KEY = "talent-assistant-mode";

const NAV = [
  { href: "/admin/dashboard", label: "Dashboard", icon: LayoutDashboard },
  { href: "/admin/jobs", label: "Jobs", icon: Briefcase },
  { href: "/admin/candidates", label: "Candidates", icon: Users },
  { href: "/admin/pipeline", label: "Pipeline", icon: Route },
  { href: "/admin/reports", label: "Reports", icon: BarChart3 },
  { href: "/admin/find", label: "Find", icon: Search },
  { href: "/admin/match", label: "Match", icon: Target },
  { href: "/admin/review", label: "Review", icon: ClipboardCheck },
  { href: "/admin/ingest", label: "Ingest", icon: FolderInput },
];

export default function AdminLayout({ children }: { children: ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const brand = useBrand();
  const signingIn = pathname === "/admin/login";
  const [panel, setPanel] = useState<PanelMode>("closed");

  useEffect(() => {
    const saved = sessionStorage.getItem(PANEL_KEY);
    if (saved === "open" || saved === "wide") setPanel(saved);
  }, []);

  function changePanel(mode: PanelMode) {
    setPanel(mode);
    sessionStorage.setItem(PANEL_KEY, mode);
  }

  async function logout() {
    await fetch("/api/admin/logout", { method: "POST" });
    router.push("/admin/login");
  }

  if (signingIn) return <>{children}</>;

  // On wide screens the page makes room for the open assistant instead of sitting under it.
  const room = panel === "wide" ? "xl:pr-[720px]" : panel === "open" ? "xl:pr-[440px]" : "";

  return (
    <div className={`flex min-h-screen flex-col transition-[padding] ${room}`}>
      <header className="sticky top-0 z-30 border-b border-black/20 bg-night text-white shadow-lift">
        <div className="mx-auto flex w-full max-w-7xl flex-wrap items-center gap-x-6 gap-y-2 px-4 py-2.5">
          <Link href="/admin/dashboard" className="flex items-center gap-2.5">
            <BrandMark className="size-8" />
            <span className="leading-tight">
              <span className="block font-serif text-base">{brand.company_name}</span>
              <span className="block text-[10px] uppercase tracking-[0.22em] text-pine-soft">Recruiter desk</span>
            </span>
          </Link>
          <nav className="-mx-1 flex flex-1 flex-wrap items-center gap-1 text-sm">
            {NAV.map(({ href, label, icon: Icon }) => {
              const active = pathname === href || pathname.startsWith(`${href}/`);
              return (
                <Link
                  key={href}
                  href={href}
                  className={`inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 transition ${
                    active ? "bg-white/10 text-white shadow-inner" : "text-white/60 hover:bg-white/5 hover:text-white"
                  }`}
                >
                  <Icon className={`size-4 ${active ? "text-pine-soft" : ""}`} />
                  {label}
                </Link>
              );
            })}
          </nav>
          <QuickSearch />
          <button
            type="button"
            onClick={logout}
            className="inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-sm text-white/60 transition hover:bg-white/5 hover:text-white"
          >
            <LogOut className="size-4" /> Log out
          </button>
        </div>
      </header>
      <main className="mx-auto w-full max-w-7xl flex-1 px-4 py-8">{children}</main>
      {brand.footer && (
        <footer className="border-t border-line">
          <p className="mx-auto w-full max-w-7xl px-4 py-4 text-xs leading-5 text-ink/55">{brand.footer}</p>
        </footer>
      )}
      <AssistantPanel mode={panel} onMode={changePanel} />
    </div>
  );
}
