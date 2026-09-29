"use client";

import type { ReactNode } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";

const FOOTER =
  "This tool is not authorized for classified processing and is not a FedRAMP system; do not upload classified documents or CUI.";

export default function AdminLayout({ children }: { children: ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const signingIn = pathname === "/admin/login";

  async function logout() {
    await fetch("/api/admin/logout", { method: "POST" });
    router.push("/admin/login");
  }

  return (
    <div className="mx-auto flex min-h-screen w-full max-w-6xl flex-col px-4 py-6">
      <header className="mb-6 flex flex-wrap items-center justify-between gap-3 border-b border-line pb-4">
        <p className="font-serif text-2xl">Recruiter desk</p>
        {!signingIn && (
          <nav className="flex flex-wrap items-center gap-x-5 gap-y-2 text-sm">
            <DeskLink href="/admin/jobs" pathname={pathname}>
              Jobs
            </DeskLink>
            <DeskLink href="/admin/candidates" pathname={pathname}>
              Candidates
            </DeskLink>
            <DeskLink href="/admin/find" pathname={pathname}>
              Find
            </DeskLink>
            <DeskLink href="/admin/match" pathname={pathname}>
              Match
            </DeskLink>
            <DeskLink href="/admin/review" pathname={pathname}>
              Review
            </DeskLink>
            <button type="button" onClick={logout} className="text-ink/50 underline-offset-2 hover:text-ink hover:underline">
              Log out
            </button>
          </nav>
        )}
      </header>
      <div className="flex-1">{children}</div>
      <footer className="mt-8 border-t border-line pt-4 text-xs leading-5 text-ink/70">{FOOTER}</footer>
    </div>
  );
}

function DeskLink({ href, pathname, children }: { href: string; pathname: string; children: ReactNode }) {
  const active = pathname === href || pathname.startsWith(`${href}/`);
  return (
    <Link href={href} className={active ? "font-medium text-pine" : "text-ink/60 hover:text-pine"}>
      {children}
    </Link>
  );
}
