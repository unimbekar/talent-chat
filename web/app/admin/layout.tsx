"use client";

import { type ReactNode, useEffect, useState } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { BarChart3, BookOpen, Briefcase, Calculator, ClipboardCheck, FolderInput, Gift, KeyRound, LayoutDashboard, LogOut, Route, Search, Settings, Target, UserCog, Users } from "lucide-react";

import { AdminOnly, RoleBadge } from "@/components/admin-only";
import { AssistantPanel, type PanelMode } from "@/components/assistant/assistant-panel";
import { BrandMark, useBrand } from "@/components/brand";
import { InstallButton, isActive, MobileTabs, type NavItem } from "@/components/mobile-nav";
import { AlertsButton } from "@/components/push-alerts";
import { QuickSearch } from "@/components/quick-search";
import { type Capability, type DeskAccount, DeskProvider, readAccount, shownName } from "@/lib/desk";

const PANEL_KEY = "talent-assistant-mode";

const NAV: (NavItem & { needs?: Capability })[] = [
  { href: "/admin/dashboard", label: "Dashboard", icon: LayoutDashboard },
  { href: "/admin/jobs", label: "Jobs", icon: Briefcase },
  { href: "/admin/candidates", label: "Candidates", icon: Users },
  { href: "/admin/pipeline", label: "Pipeline", icon: Route },
  { href: "/admin/burden", label: "Burden", icon: Calculator, needs: "burden" },
  { href: "/admin/reports", label: "Reports", icon: BarChart3 },
  { href: "/admin/find", label: "Find", icon: Search },
  { href: "/admin/match", label: "Match", icon: Target },
  { href: "/admin/review", label: "Review", icon: ClipboardCheck },
  { href: "/admin/ingest", label: "Ingest", icon: FolderInput, needs: "bulk_ingest" },
  { href: "/admin/knowledge", label: "Knowledge", icon: BookOpen },
  { href: "/admin/benefits", label: "Benefits", icon: Gift },
  { href: "/admin/team", label: "Team", icon: UserCog, needs: "team" },
  { href: "/admin/settings", label: "Settings", icon: Settings, needs: "settings" },
  { href: "/admin/password", label: "Password", icon: KeyRound },
];

export default function AdminLayout({ children }: { children: ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const brand = useBrand();
  const signingIn = pathname === "/admin/login";
  const [panel, setPanel] = useState<PanelMode>("closed");
  const [account, setAccount] = useState<DeskAccount | null>(null);

  useEffect(() => {
    const saved = sessionStorage.getItem(PANEL_KEY);
    if (saved === "open" || saved === "wide") setPanel(saved);
    if (signingIn) return;
    let live = true;
    fetch("/api/admin/session")
      .then(async (response) => (response.ok ? response.json() : null))
      .then((data) => {
        if (live) setAccount(readAccount(data));
      })
      .catch(() => undefined);
    return () => {
      live = false;
    };
  }, [signingIn]);

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

  const allowed = (item: { needs?: Capability }) => !item.needs || Boolean(account?.can[item.needs]);
  const nav = NAV.filter(allowed);
  const current = NAV.find((item) => isActive(pathname, item.href));
  const blocked = account && current?.needs && !allowed(current) ? current.needs : null;
  const who = account ? shownName(account) : "";

  return (
    <div className={`admin flex min-h-screen flex-col transition-[padding] ${room}`}>
      <div className="admin-atmosphere" aria-hidden="true">
        <div className="careers-glow careers-glow-a" />
        <div className="careers-glow careers-glow-b" />
        <div className="careers-grid" />
        <div className="careers-noise" />
      </div>
      <header className="careers-bar sticky top-0 z-30 pt-[env(safe-area-inset-top)] text-ink">
        <div className="mx-auto flex w-full max-w-7xl items-center gap-x-6 gap-y-2 px-4 py-2.5 lg:flex-wrap">
          <Link href="/admin/dashboard" className="flex min-w-0 items-center gap-2.5">
            <BrandMark className="size-8 shrink-0 rounded-xl ring-1 ring-white/10" />
            <span className="min-w-0 leading-tight">
              <span className="block truncate text-base font-medium tracking-tight">
                <span className="lg:hidden">{current?.label || brand.company_name}</span>
                <span className="hidden lg:inline">{brand.company_name}</span>
              </span>
              <span className="careers-kicker">Recruiter desk</span>
            </span>
          </Link>
          <span className="flex-1 lg:hidden" />
          <nav className="-mx-1 hidden flex-1 flex-wrap items-center gap-1 text-sm lg:flex">
            {nav.map(({ href, label, icon: Icon }) => {
              const active = isActive(pathname, href);
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
          <span className="hidden lg:contents">
            <AlertsButton />
            <InstallButton />
            {account && (
              <span className="inline-flex max-w-60 items-center gap-2 text-xs text-white/50" title={account.email}>
                <RoleBadge role={account.role} />
                <span className="truncate">{who}</span>
              </span>
            )}
            <button
              type="button"
              onClick={logout}
              className="inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-sm text-white/60 transition hover:bg-white/5 hover:text-white"
            >
              <LogOut className="size-4" /> Log out
            </button>
          </span>
        </div>
      </header>
      <main className="mx-auto w-full max-w-7xl flex-1 px-4 pb-32 pt-5 sm:pt-8 lg:pb-8">
        <DeskProvider account={account}>
          {blocked ? <AdminOnly capability={blocked} /> : current?.needs && !account ? null : children}
        </DeskProvider>
      </main>
      {brand.footer && (
        <footer className="border-t border-white/10 pb-[calc(env(safe-area-inset-bottom)+4rem)] lg:pb-0">
          <p className="mx-auto w-full max-w-7xl px-4 py-4 text-xs leading-5 text-white/40">{brand.footer}</p>
        </footer>
      )}
      <MobileTabs pathname={pathname} primary={nav.slice(0, 4)} more={nav.slice(4)} onLogout={logout} account={account} />
      <AssistantPanel mode={panel} onMode={changePanel} />
    </div>
  );
}
