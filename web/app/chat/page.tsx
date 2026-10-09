"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { MapPin, MessageCircle, Search } from "lucide-react";

import { ApplyDialog, type OpenRole } from "@/components/careers/apply-dialog";
import { AskDesk } from "@/components/careers/ask-desk";
import { BrandMark, useBrand } from "@/components/brand";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

export default function ChatPage() {
  const brand = useBrand();
  const [jobs, setJobs] = useState<OpenRole[]>([]);
  const [query, setQuery] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [applyCode, setApplyCode] = useState("");
  const [desk, setDesk] = useState(false);
  const [deskAsk, setDeskAsk] = useState<{ id: number; text: string } | null>(null);

  useEffect(() => {
    fetch("/api/public/jobs")
      .then(async (response) => {
        const body = await response.json().catch(() => ({ jobs: [] }));
        if (!response.ok) {
          setError(body.message || "Open roles could not be loaded.");
          return;
        }
        setJobs(body.jobs || []);
      })
      .catch(() => setError("Open roles could not be loaded."))
      .finally(() => setLoading(false));
  }, []);

  const shown = useMemo(() => {
    const needle = query.trim().toLowerCase();
    if (!needle) return jobs;
    return jobs.filter((job) =>
      [job.requisition_code, job.title, job.location, job.blurb].filter(Boolean).some((value) => String(value).toLowerCase().includes(needle)),
    );
  }, [jobs, query]);

  const applying = jobs.find((job) => job.requisition_code === applyCode) || null;

  return (
    <main className="flex h-[100dvh] flex-col bg-desk text-ink">
      <header className="flex items-center justify-between gap-4 border-b border-line bg-card/90 px-4 py-3 backdrop-blur sm:px-6">
        <div className="flex min-w-0 items-center gap-3">
          <BrandMark className="size-10 rounded-2xl" />
          <div className="min-w-0">
            <p className="truncate font-serif text-lg leading-tight">{brand.company_name}</p>
            <p className="text-[11px] uppercase tracking-[0.18em] text-ink/45">Careers</p>
          </div>
        </div>
        <div className="flex items-center gap-3">
          <a href={brand.careers_url} className="hidden text-sm text-ink/60 hover:text-pine-deep sm:inline">
            Company site
          </a>
          <Button asChild variant="outline" size="sm">
            <Link href="/admin/login">Recruiter sign in</Link>
          </Button>
        </div>
      </header>

      <div className="flex min-h-0 flex-1">
        <div className="min-w-0 flex-1 overflow-y-auto">
          <section className="relative isolate overflow-hidden">
            <img src={brand.hero_url} alt="" className="absolute inset-0 h-full w-full object-cover" />
            <div className="absolute inset-0 bg-gradient-to-r from-night/85 via-night/55 to-night/20" />
            <div className="relative mx-auto flex max-w-5xl flex-col gap-3 px-5 py-12 text-white sm:px-8 sm:py-16">
              <p className="text-xs uppercase tracking-[0.22em] text-white/70">Open roles</p>
              <h1 className="max-w-xl font-serif text-4xl leading-tight sm:text-5xl">{brand.tagline}</h1>
              <p className="max-w-lg text-sm leading-6 text-white/80">
                Browse every open posting, ask the desk a question, and apply with your résumé. A current TS/SCI with Full Scope Polygraph is required.
              </p>
            </div>
          </section>

          <div className="mx-auto flex w-full max-w-5xl flex-col gap-4 px-4 py-6 sm:px-8">
            <div className="flex flex-wrap items-end justify-between gap-3">
              <div>
                <h2 className="font-serif text-2xl">All open jobs</h2>
                <p className="text-sm text-ink/55">{loading ? "Loading…" : `${shown.length} of ${jobs.length}`}</p>
              </div>
              <label className="relative w-full sm:w-72">
                <span className="sr-only">Filter jobs</span>
                <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-ink/40" />
                <Input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Title, city, or code" className="pl-9" />
              </label>
            </div>
            {error && <p className="rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800">{error}</p>}
            {!loading && shown.length === 0 && <p className="text-sm text-ink/55">No open role matches that filter.</p>}
            <ul className="grid gap-3 md:grid-cols-2">
              {shown.map((job) => (
                <li key={job.requisition_code} className="flex flex-col rounded-2xl border border-line bg-card p-4 shadow-card">
                  <p className="font-serif text-xl leading-snug">{job.title || "Untitled role"}</p>
                  <p className="mt-1 flex flex-wrap items-center gap-2 text-sm text-ink/55">
                    <span className="font-mono text-xs">{job.requisition_code}</span>
                    {job.location && (
                      <span className="inline-flex items-center gap-1">
                        <MapPin className="size-3.5" /> {job.location}
                      </span>
                    )}
                  </p>
                  {job.blurb && <p className="mt-3 line-clamp-3 text-sm leading-6 text-ink/70">{job.blurb}</p>}
                  <div className="mt-4 flex items-center gap-3">
                    <Button type="button" size="sm" onClick={() => setApplyCode(job.requisition_code)}>
                      Apply
                    </Button>
                    <button
                      type="button"
                      className="text-sm text-ink/55 underline-offset-2 hover:underline"
                      onClick={() => {
                        setDesk(true);
                        setDeskAsk({ id: Date.now(), text: `What does ${job.requisition_code} require?` });
                      }}
                    >
                      Ask about this
                    </button>
                  </div>
                </li>
              ))}
            </ul>
            <p className="pb-16 text-center text-[11px] text-ink/40 lg:pb-4">
              {brand.footer || `© ${new Date().getFullYear()} ${brand.company_name}`}
              {" · "}This tool is not authorized for classified processing and is not a FedRAMP system; do not upload classified documents or CUI.
            </p>
          </div>
        </div>

        <aside
          className={
            desk
              ? "fixed inset-0 z-40 flex bg-card lg:static lg:inset-auto lg:z-auto lg:block lg:w-[24rem] lg:shrink-0 lg:border-l lg:border-line"
              : "hidden lg:block lg:w-[24rem] lg:shrink-0 lg:border-l lg:border-line"
          }
        >
          <AskDesk
            open
            onClose={() => setDesk(false)}
            onApply={(code) => {
              setApplyCode(code);
              setDesk(false);
            }}
            question={deskAsk?.text}
            questionId={deskAsk?.id}
          />
        </aside>
      </div>

      <button
        type="button"
        onClick={() => setDesk(true)}
        className="fixed bottom-4 right-4 inline-flex items-center gap-2 rounded-full bg-night px-4 py-3 text-sm text-white shadow-lift lg:hidden"
      >
        <MessageCircle className="size-4" /> Ask the Desk
      </button>

      {applying && <ApplyDialog job={applying} onClose={() => setApplyCode("")} />}
    </main>
  );
}
