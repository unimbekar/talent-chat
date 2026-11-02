"use client";

import { type ReactNode, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { Activity, BarChart3, BookOpen, Briefcase, Calculator, ChevronDown, ClipboardCheck, FilePenLine, FolderInput, Gift, KeyRound, LayoutDashboard, LogOut, Route, Search, Settings, Target, UserCog, Users } from "lucide-react";

import { AdminOnly, RoleBadge } from "@/components/admin-only";
import { AssistantPanel, type PanelMode } from "@/components/assistant/assistant-panel";
import { BrandMark, useBrand } from "@/components/brand";
import { InstallButton, isActive, MobileTabs, type NavItem } from "@/components/mobile-nav";
import { AlertsButton } from "@/components/push-alerts";
import { QuickSearch } from "@/components/quick-search";
import { type Capability, type DeskAccount, DeskProvider, readAccount, shownName } from "@/lib/desk";
import { markDeskBrowser } from "@/lib/visit";

const PANEL_KEY = "talent-assistant-mode";

const NAV: (NavItem & { needs?: Capability })[] = [
  { href: "/admin/dashboard", label: "Dashboard", icon: LayoutDashboard },
  { href: "/admin/jobs", label: "Jobs", icon: Briefcase },
  { href: "/admin/candidates", label: "Candidates", icon: Users },
  { href: "/admin/pipeline", label: "Pipeline", icon: Route },
  { href: "/admin/review", label: "Review", icon: ClipboardCheck },
  { href: "/admin/resume-update", label: "Update résumé", icon: FilePenLine },
  { href: "/admin/find", label: "Find", icon: Search },
  { href: "/admin/match", label: "Match", icon: Target },
  { href: "/admin/burden", label: "Burden", icon: Calculator, needs: "burden" },
  { href: "/admin/reports", label: "Reports", icon: BarChart3 },
  { href: "/admin/visitors", label: "Visitors", icon: Activity, needs: "visitors" },
  { href: "/admin/ingest", label: "Ingest", icon: FolderInput, needs: "bulk_ingest" },
  { href: "/admin/knowledge", label: "Knowledge", icon: BookOpen },
  { href: "/admin/benefits", label: "Benefits", icon: Gift },
  { href: "/admin/team", label: "Team", icon: UserCog, needs: "team" },
  { href: "/admin/settings", label: "Settings", icon: Settings, needs: "settings" },
  { href: "/admin/password", label: "Password", icon: KeyRound },
];

const PRIMARY = new Set(["/admin/dashboard", "/admin/jobs", "/admin/candidates", "/admin/pipeline", "/admin/review", "/admin/resume-update"]);

const MENU_GROUPS = [
  { label: "Search", hrefs: ["/admin/find", "/admin/match"] },
  { label: "Desk", hrefs: ["/admin/burden", "/admin/reports", "/admin/visitors", "/admin/ingest"] },
  { label: "Company", hrefs: ["/admin/knowledge", "/admin/benefits", "/admin/team", "/admin/settings", "/admin/password"] },
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
        if (!live) return;
        const next = readAccount(data);
        setAccount(next);
        if (next) markDeskBrowser();
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
  const top = nav.filter((item) => PRIMARY.has(item.href));
  const extra = nav.filter((item) => !PRIMARY.has(item.href));
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
        <div className="mx-auto flex w-full max-w-7xl flex-col gap-1 px-4 py-2.5">
          <div className="flex items-center gap-3">
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
            <span className="flex-1" />
            <QuickSearch />
            <span className="hidden items-center gap-1 lg:flex">
              <AlertsButton />
              <InstallButton />
              {account && (
                <span className="inline-flex max-w-60 items-center gap-2 px-1 text-xs text-white/50" title={account.email}>
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
          <nav className="hidden flex-wrap items-center gap-1 pb-0.5 text-sm lg:flex">
            {top.map(({ href, label, icon: Icon }) => {
              const active = isActive(pathname, href);
              return (
                <Link
                  key={href}
                  href={href}
                  className={`inline-flex shrink-0 items-center gap-1.5 rounded-lg px-2.5 py-1.5 transition ${
                    active ? "bg-white/10 text-white shadow-inner" : "text-white/60 hover:bg-white/5 hover:text-white"
                  }`}
                >
                  <Icon className={`size-4 ${active ? "text-pine-soft" : ""}`} />
                  {label}
                </Link>
              );
            })}
            {extra.length > 0 && <DeskMenu items={extra} pathname={pathname} />}
          </nav>
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
      <MobileTabs pathname={pathname} primary={top.slice(0, 4)} more={[...top.slice(4), ...extra]} onLogout={logout} account={account} />
      <AssistantPanel mode={panel} onMode={changePanel} />
    </div>
  );
}

function DeskMenu({ items, pathname }: { items: (NavItem & { needs?: Capability })[]; pathname: string }) {
  const [open, setOpen] = useState(false);
  const root = useRef<HTMLDivElement>(null);
  const active = items.some((item) => isActive(pathname, item.href));
  const grouped = MENU_GROUPS.map((group) => ({
    label: group.label,
    items: items.filter((item) => group.hrefs.includes(item.href)),
  })).filter((group) => group.items.length > 0);
  const placed = new Set(grouped.flatMap((group) => group.items.map((item) => item.href)));
  const rest = items.filter((item) => !placed.has(item.href));
  if (rest.length > 0) grouped.push({ label: "More", items: rest });

  useEffect(() => setOpen(false), [pathname]);

  useEffect(() => {
    if (!open) return;
    function onPointer(event: MouseEvent) {
      if (!root.current?.contains(event.target as Node)) setOpen(false);
    }
    function onKey(event: KeyboardEvent) {
      if (event.key === "Escape") setOpen(false);
    }
    document.addEventListener("mousedown", onPointer);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onPointer);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  return (
    <div ref={root} className="relative">
      <button
        type="button"
        aria-expanded={open}
        aria-haspopup="menu"
        onClick={() => setOpen((value) => !value)}
        className={`inline-flex items-center gap-1 rounded-lg px-2.5 py-1.5 transition ${
          active || open ? "bg-white/10 text-white" : "text-white/60 hover:bg-white/5 hover:text-white"
        }`}
      >
        More
        <ChevronDown className={`size-3.5 transition ${open ? "rotate-180" : ""}`} />
      </button>
      {open && (
        <div role="menu" className="absolute left-0 top-[calc(100%+0.4rem)] z-50 grid w-[28rem] max-w-[calc(100vw-1.5rem)] grid-cols-3 gap-3 rounded-2xl border border-line bg-card p-3 text-ink shadow-lift">
          {grouped.map((group) => (
            <div key={group.label}>
              <p className="px-2 pb-1 text-[10px] font-medium uppercase tracking-wide text-ink/45">{group.label}</p>
              <ul className="flex flex-col">
                {group.items.map(({ href, label, icon: Icon }) => {
                  const here = isActive(pathname, href);
                  return (
                    <li key={href}>
                      <Link
                        href={href}
                        role="menuitem"
                        className={`flex items-center gap-2 rounded-lg px-2 py-1.5 text-sm ${here ? "bg-pine/10 text-ink" : "text-ink/80 hover:bg-desk hover:text-ink"}`}
                      >
                        <Icon className={`size-4 ${here ? "text-pine" : "text-ink/45"}`} />
                        {label}
                      </Link>
                    </li>
                  );
                })}
              </ul>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
