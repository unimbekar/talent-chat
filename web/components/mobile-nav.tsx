"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Download, LogOut, MoreHorizontal, Share, X, type LucideIcon } from "lucide-react";

import { install, usePwa } from "@/lib/pwa";

export type NavItem = { href: string; label: string; icon: LucideIcon };

export function isActive(pathname: string, href: string): boolean {
  return pathname === href || pathname.startsWith(`${href}/`);
}

export function MobileTabs({
  pathname,
  primary,
  more,
  onLogout,
}: {
  pathname: string;
  primary: NavItem[];
  more: NavItem[];
  onLogout: () => void;
}) {
  const [open, setOpen] = useState(false);
  const moreActive = more.some((item) => isActive(pathname, item.href));

  useEffect(() => setOpen(false), [pathname]);

  return (
    <>
      <nav
        aria-label="Main"
        className="fixed inset-x-0 bottom-0 z-40 border-t border-black/10 bg-night/95 pb-[env(safe-area-inset-bottom)] text-white backdrop-blur-md lg:hidden"
      >
        <ul className="mx-auto grid max-w-lg grid-cols-5">
          {primary.map(({ href, label, icon: Icon }) => {
            const active = isActive(pathname, href);
            return (
              <li key={href}>
                <Link
                  href={href}
                  aria-current={active ? "page" : undefined}
                  className={`flex h-16 flex-col items-center justify-center gap-1 text-[11px] font-medium transition active:scale-95 ${
                    active ? "text-white" : "text-white/55"
                  }`}
                >
                  <span className={`rounded-full px-4 py-1 transition ${active ? "bg-pine/30" : ""}`}>
                    <Icon className={`size-5 ${active ? "text-pine-soft" : ""}`} />
                  </span>
                  {label}
                </Link>
              </li>
            );
          })}
          <li>
            <button
              type="button"
              onClick={() => setOpen(true)}
              aria-expanded={open}
              className={`flex h-16 w-full flex-col items-center justify-center gap-1 text-[11px] font-medium transition active:scale-95 ${
                moreActive ? "text-white" : "text-white/55"
              }`}
            >
              <span className={`rounded-full px-4 py-1 transition ${moreActive ? "bg-pine/30" : ""}`}>
                <MoreHorizontal className={`size-5 ${moreActive ? "text-pine-soft" : ""}`} />
              </span>
              More
            </button>
          </li>
        </ul>
      </nav>
      {open && <MoreSheet pathname={pathname} items={more} onClose={() => setOpen(false)} onLogout={onLogout} />}
    </>
  );
}

function MoreSheet({
  pathname,
  items,
  onClose,
  onLogout,
}: {
  pathname: string;
  items: NavItem[];
  onClose: () => void;
  onLogout: () => void;
}) {
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => event.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    const overflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      window.removeEventListener("keydown", onKey);
      document.body.style.overflow = overflow;
    };
  }, [onClose]);

  return (
    <div className="fixed inset-0 z-50 lg:hidden" role="dialog" aria-modal="true" aria-label="More">
      <button type="button" aria-label="Close" onClick={onClose} className="absolute inset-0 animate-fade-in bg-night/50 backdrop-blur-[2px]" />
      <div className="absolute inset-x-0 bottom-0 animate-sheet-up rounded-t-3xl bg-desk px-4 pb-[calc(env(safe-area-inset-bottom)+1rem)] pt-2 shadow-lift">
        <div className="mx-auto mb-3 h-1.5 w-10 rounded-full bg-ink/15" />
        <div className="mb-3 flex items-center justify-between px-1">
          <p className="font-serif text-lg">More</p>
          <button type="button" onClick={onClose} className="rounded-full p-2 text-ink/60 hover:bg-ink/5" aria-label="Close">
            <X className="size-5" />
          </button>
        </div>
        <ul className="grid grid-cols-3 gap-2">
          {items.map(({ href, label, icon: Icon }) => {
            const active = isActive(pathname, href);
            return (
              <li key={href}>
                <Link
                  href={href}
                  className={`flex flex-col items-center gap-2 rounded-2xl border px-2 py-4 text-sm transition active:scale-95 ${
                    active ? "border-pine/50 bg-pine/10 text-ink" : "border-line bg-card text-ink/75"
                  }`}
                >
                  <Icon className={`size-5 ${active ? "text-pine" : "text-ink/55"}`} />
                  {label}
                </Link>
              </li>
            );
          })}
        </ul>
        <div className="mt-3 flex flex-col gap-2">
          <InstallRow />
          <button
            type="button"
            onClick={onLogout}
            className="flex items-center gap-3 rounded-2xl border border-line bg-card px-4 py-3 text-left text-sm text-ink/75 active:scale-[0.99]"
          >
            <LogOut className="size-5 text-ink/55" /> Log out
          </button>
        </div>
      </div>
    </div>
  );
}

function InstallRow() {
  const { installPrompt, installed, ios } = usePwa();
  if (installed) return null;
  if (installPrompt) {
    return (
      <button
        type="button"
        onClick={() => install()}
        className="flex items-center gap-3 rounded-2xl bg-night px-4 py-3 text-left text-sm font-medium text-white active:scale-[0.99]"
      >
        <Download className="size-5 text-pine-soft" />
        <span className="flex-1">Install the desk app</span>
        <span className="text-xs text-white/50">Home screen</span>
      </button>
    );
  }
  if (ios) {
    return (
      <p className="flex items-center gap-3 rounded-2xl border border-line bg-card px-4 py-3 text-sm text-ink/70">
        <Share className="size-5 shrink-0 text-ink/55" />
        To install, tap Share in Safari, then Add to Home Screen.
      </p>
    );
  }
  return null;
}

export function InstallButton() {
  const { installPrompt, installed } = usePwa();
  if (installed || !installPrompt) return null;
  return (
    <button
      type="button"
      onClick={() => install()}
      className="inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-sm text-white/60 transition hover:bg-white/5 hover:text-white"
      title="Install the recruiter desk as an app"
    >
      <Download className="size-4" /> Install
    </button>
  );
}
