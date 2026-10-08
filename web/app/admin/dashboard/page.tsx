"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import type { LucideIcon } from "lucide-react";
import { AlertTriangle, ArrowRight, Briefcase, CheckCircle2, ClipboardCheck, FolderInput, MapPin, RefreshCw, Route, Search, Sparkles, UserPlus, Users } from "lucide-react";

import { Button } from "@/components/ui/button";
import { readCache, writeCache } from "@/lib/page-cache";

type Overview = {
  jobs: { open: number; closed: number; needs_review: number; no_description: number };
  candidates: { total: number; ranked: number; added_this_week: number; no_location: number };
  crawl: { last_ok: boolean | null; last_finished_at: string | null; last_rows: number | null; last_error: string | null };
  top_skills: { name: string; count: number }[];
  top_states: { state: string; count: number }[];
  recent_candidates: { id: string; full_name: string | null; location: string | null; title: string | null; created_at: string | null }[];
  pipeline?: { active: number; selected: number; rejected: number; withdrawn: number };
};

const CACHE_KEY = "talent-overview";

export default function DashboardPage() {
  const router = useRouter();
  const [data, setData] = useState<Overview | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    setData(readCache<Overview>(CACHE_KEY));
    fetch("/api/admin/overview").then(async (response) => {
      if (response.status === 401) {
        router.push("/admin/login");
        return;
      }
      if (!response.ok) {
        setError("The dashboard could not load. The other pages still work.");
        return;
      }
      const next = (await response.json()) as Overview;
      setData(next);
      writeCache(CACHE_KEY, next);
    });
  }, [router]);

  const maxSkill = Math.max(1, ...(data?.top_skills || []).map((item) => item.count));
  const maxState = Math.max(1, ...(data?.top_states || []).map((item) => item.count));

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="page-title">Dashboard</h1>
          <p className="page-lead">Open jobs, the candidate pool, and what needs attention today.</p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button asChild variant="outline">
            <Link href="/admin/ingest">
              <FolderInput /> Import résumés
            </Link>
          </Button>
          <Button asChild>
            <Link href="/admin/find">
              <Search /> Find candidates
            </Link>
          </Button>
        </div>
      </div>

      {error && <p className="rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800">{error}</p>}

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-5">
        <Stat icon={Briefcase} label="Open jobs" value={data?.jobs.open} note={data ? `${data.jobs.closed} closed` : ""} href="/admin/jobs" />
        <Stat icon={Users} label="Candidates" value={data?.candidates.total} note={data ? `${data.candidates.ranked} ranked against jobs` : ""} href="/admin/candidates" />
        <Stat
          icon={Route}
          label="In the pipeline"
          value={data?.pipeline?.active}
          note={data?.pipeline ? `${data.pipeline.selected} selected · ${data.pipeline.rejected} rejected` : ""}
          href="/admin/pipeline"
        />
        <Stat icon={UserPlus} label="Added this week" value={data?.candidates.added_this_week} note="New résumés on file" href="/admin/candidates" />
        <Stat
          icon={AlertTriangle}
          label="Needs attention"
          value={data ? data.jobs.needs_review + data.jobs.no_description : undefined}
          note={data ? `${data.jobs.needs_review} jobs to review · ${data.jobs.no_description} without a description` : ""}
          href="/admin/jobs"
          warn={Boolean(data && data.jobs.needs_review + data.jobs.no_description > 0)}
        />
      </div>

      <div className="grid gap-4 lg:grid-cols-3">
        <section className="panel p-5 lg:col-span-2">
          <div className="flex items-center justify-between gap-3">
            <h2 className="font-serif text-xl">Recently added</h2>
            <Link href="/admin/candidates" className="inline-flex items-center gap-1 text-sm text-pine-deep hover:underline">
              All candidates <ArrowRight className="size-4" />
            </Link>
          </div>
          <ul className="mt-3 divide-y divide-line">
            {(data?.recent_candidates || []).map((person) => (
              <li key={person.id} className="flex items-center justify-between gap-3 py-2.5">
                <div className="flex min-w-0 items-center gap-3">
                  <Initials name={person.full_name} />
                  <div className="min-w-0">
                    <Link href={`/admin/candidates/${person.id}`} className="block truncate text-sm font-medium hover:text-pine-deep">
                      {person.full_name || "Unnamed résumé"}
                    </Link>
                    <p className="truncate text-xs text-ink/55">{[person.title, person.location].filter(Boolean).join(" · ") || "No title or location yet"}</p>
                  </div>
                </div>
                <span className="shrink-0 text-xs text-ink/45">{ago(person.created_at)}</span>
              </li>
            ))}
            {data && data.recent_candidates.length === 0 && <li className="py-6 text-sm text-ink/60">No résumés yet. Import a folder to get started.</li>}
            {!data && <SkeletonRows />}
          </ul>
        </section>

        <section className="panel flex flex-col gap-4 p-5">
          <h2 className="font-serif text-xl">Careers page sync</h2>
          {data?.crawl.last_error ? (
            <p className="flex items-start gap-2 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-800">
              <AlertTriangle className="mt-0.5 size-4 shrink-0" /> {data.crawl.last_error}
            </p>
          ) : (
            <p className="flex items-center gap-2 text-sm text-ink/70">
              <CheckCircle2 className="size-4 text-emerald-600" />
              {data?.crawl.last_finished_at ? `Last read ${ago(data.crawl.last_finished_at)}, ${data.crawl.last_rows ?? 0} rows` : "Not read yet"}
            </p>
          )}
          <Button asChild variant="outline" size="sm" className="self-start">
            <Link href="/admin/jobs">
              <RefreshCw /> Open jobs to recrawl
            </Link>
          </Button>
          <div className="mt-auto rounded-xl bg-desk p-4">
            <p className="flex items-center gap-2 text-xs font-medium uppercase tracking-wide text-pine-deep">
              <Sparkles className="size-3.5" /> Quick start
            </p>
            <ol className="mt-2 list-decimal space-y-1 pl-4 text-sm text-ink/75">
              <li>Import résumés from a folder.</li>
              <li>Ask Find for people, in plain words.</li>
              <li>Review several people against one job.</li>
              <li>Submit the ones you send, and track salary, interviews, and the decision.</li>
            </ol>
            <Button asChild variant="ghost" size="sm" className="mt-2 px-0">
              <Link href="/admin/review">
                <ClipboardCheck /> Start a review
              </Link>
            </Button>
          </div>
        </section>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <section className="panel p-5">
          <h2 className="font-serif text-xl">Top skills in the pool</h2>
          <ul className="mt-4 flex flex-col gap-2">
            {(data?.top_skills || []).map((item) => (
              <li key={item.name} className="grid grid-cols-[8rem_1fr_2.5rem] items-center gap-3 text-sm">
                <span className="truncate">{item.name}</span>
                <span className="h-2 overflow-hidden rounded-full bg-desk">
                  <span className="block h-full rounded-full bg-gradient-to-r from-pine-soft to-pine" style={{ width: `${(item.count / maxSkill) * 100}%` }} />
                </span>
                <span className="text-right font-mono text-xs text-ink/55">{item.count}</span>
              </li>
            ))}
            {!data && <SkeletonRows />}
          </ul>
        </section>
        <section className="panel p-5">
          <h2 className="font-serif text-xl">Where candidates live</h2>
          <ul className="mt-4 flex flex-col gap-2">
            {(data?.top_states || []).map((item) => (
              <li key={item.state} className="grid grid-cols-[8rem_1fr_2.5rem] items-center gap-3 text-sm">
                <span className="inline-flex items-center gap-1.5">
                  <MapPin className="size-3.5 text-ink/40" /> {item.state}
                </span>
                <span className="h-2 overflow-hidden rounded-full bg-desk">
                  <span className="block h-full rounded-full bg-night/80" style={{ width: `${(item.count / maxState) * 100}%` }} />
                </span>
                <span className="text-right font-mono text-xs text-ink/55">{item.count}</span>
              </li>
            ))}
            {data && data.candidates.no_location > 0 && (
              <li className="pt-1 text-xs text-ink/55">{data.candidates.no_location} résumés have no known home state yet.</li>
            )}
            {!data && <SkeletonRows />}
          </ul>
        </section>
      </div>
    </div>
  );
}

function Stat({
  icon: Icon,
  label,
  value,
  note,
  href,
  warn = false,
}: {
  icon: LucideIcon;
  label: string;
  value: number | undefined;
  note: string;
  href: string;
  warn?: boolean;
}) {
  return (
    <Link href={href} className="panel group flex flex-col gap-3 p-5 transition hover:-translate-y-0.5 hover:shadow-lift">
      <span className={`inline-flex size-10 items-center justify-center rounded-xl ${warn ? "bg-amber-100 text-amber-700" : "bg-pine/10 text-pine-deep"}`}>
        <Icon className="size-5" />
      </span>
      <div>
        <p className="text-xs font-medium uppercase tracking-wide text-ink/50">{label}</p>
        <p className="mt-1 font-serif text-4xl leading-none">{value ?? "—"}</p>
        <p className="mt-2 truncate text-xs text-ink/55">{note || " "}</p>
      </div>
    </Link>
  );
}

function Initials({ name }: { name: string | null }) {
  const letters = (name || "?")
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase())
    .join("");
  return <span className="inline-flex size-9 shrink-0 items-center justify-center rounded-full bg-night text-xs font-medium text-pine-soft">{letters || "?"}</span>;
}

function SkeletonRows() {
  return (
    <>
      {[0, 1, 2, 3].map((row) => (
        <li key={row} className="h-6 animate-pulse rounded bg-desk" />
      ))}
    </>
  );
}

function ago(iso: string | null): string {
  if (!iso) return "";
  const seconds = Math.max(0, (Date.now() - new Date(iso).getTime()) / 1000);
  if (seconds < 90) return "just now";
  if (seconds < 3600) return `${Math.round(seconds / 60)} min ago`;
  if (seconds < 86400) return `${Math.round(seconds / 3600)} h ago`;
  const days = Math.round(seconds / 86400);
  return days === 1 ? "yesterday" : `${days} days ago`;
}
