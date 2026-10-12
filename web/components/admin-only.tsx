"use client";

import Link from "next/link";
import { ShieldCheck } from "lucide-react";

import { Button } from "@/components/ui/button";
import { CAPABILITY_LABEL, type Capability } from "@/lib/desk";

export function AdminOnly({ capability }: { capability: Capability }) {
  return (
    <section className="mx-auto mt-6 max-w-lg animate-fade-up rounded-3xl border border-line bg-card p-8 text-center shadow-lift">
      <span className="mx-auto mb-4 grid size-12 place-items-center rounded-2xl bg-pine/10 text-pine">
        <ShieldCheck className="size-6" />
      </span>
      <h1 className="font-serif text-2xl text-ink">Admin only</h1>
      <p className="mt-2 text-sm leading-6 text-ink/70">
        Only admins can {CAPABILITY_LABEL[capability]}. Your recruiter account can still work jobs, candidates, the pipeline, and reports. Ask an
        admin if you need this changed.
      </p>
      <Button asChild className="mt-6">
        <Link href="/admin/dashboard">Back to the dashboard</Link>
      </Button>
    </section>
  );
}

export function RoleBadge({ role }: { role: "admin" | "recruiter" }) {
  return (
    <span
      className={`shrink-0 rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider text-[#0b1220] ${
        role === "admin" ? "bg-amber-300" : "bg-pine-soft"
      }`}
    >
      {role === "admin" ? "Admin" : "Recruiter"}
    </span>
  );
}
