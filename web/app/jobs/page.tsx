"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { FileText, Gift, LayoutGrid, List, MapPin, MessageCircle, Search } from "lucide-react";

import { ApplyDialog, type OpenRole } from "@/components/careers/apply-dialog";
import { AskDesk } from "@/components/careers/ask-desk";
import { JobDetailDialog } from "@/components/careers/job-detail";
import { BrandMark, useBrand } from "@/components/brand";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { trackVisit } from "@/lib/visit";

export default function ChatPage() {
  const brand = useBrand();
  const [jobs, setJobs] = useState<OpenRole[]>([]);
  const [query, setQuery] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [applyCode, setApplyCode] = useState("");
  const [viewCode, setViewCode] = useState("");
  const closeView = useCallback(() => setViewCode(""), []);
  const [desk, setDesk] = useState(false);
  const [deskAsk, setDeskAsk] = useState<{ id: number; text: string } | null>(null);
  const [view, setView] = useState<"cards" | "list">("cards");

  useEffect(() => {
    const saved = sessionStorage.getItem("jobs-view");
    if (saved === "list" || saved === "cards") setView(saved);
    trackVisit("page", "/jobs");
  }, []);

  useEffect(() => {
    if (viewCode) trackVisit("posting", viewCode);
  }, [viewCode]);

  useEffect(() => {
    if (applyCode) trackVisit("apply", applyCode);
  }, [applyCode]);

  function chooseView(next: "cards" | "list") {
    setView(next);
    sessionStorage.setItem("jobs-view", next);
  }

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

  function askAbout(text: string) {
    setDesk(true);
    setDeskAsk({ id: Date.now(), text });
  }

  return (
    <main className="careers relative flex h-[100dvh] flex-col">
      <div className="careers-atmosphere" aria-hidden="true">
        <div className="careers-glow careers-glow-a" />
        <div className="careers-glow careers-glow-b" />
        <div className="careers-grid" />
        <div className="careers-noise" />
      </div>

      <header className="careers-bar relative z-20 flex items-center justify-between gap-4 px-4 py-3 sm:px-6">
        <div className="flex min-w-0 items-center gap-3">
          <BrandMark className="size-10 rounded-2xl ring-1 ring-white/10" />
          <div className="min-w-0">
            <p className="truncate text-[15px] font-medium tracking-tight">{brand.company_name}</p>
            <p className="careers-kicker">Careers</p>
          </div>
        </div>
        <div className="flex items-center gap-3">
          <Link href="/jobs/benefits" className="inline-flex items-center gap-1.5 text-sm text-white/70 underline-offset-4 hover:text-white hover:underline">
            <Gift className="size-3.5" /> Benefits
          </Link>
          <a href={brand.careers_url} className="hidden text-sm text-white/55 hover:text-white sm:inline">
            Company site
          </a>
          <Button asChild variant="outline" size="sm" className="careers-quiet">
            <Link href="/admin/login">Recruiter sign in</Link>
          </Button>
        </div>
      </header>

      <div className="relative z-10 flex min-h-0 flex-1">
        <div className="min-w-0 flex-1 overflow-y-auto">
          <section className="mx-auto grid w-full max-w-5xl gap-6 px-5 py-8 sm:px-8 sm:py-16 lg:grid-cols-[1.3fr_0.7fr] lg:items-end lg:gap-10 lg:py-20">
            <div className="flex flex-col gap-5">
              <p className="careers-kicker">Open roles</p>
              <h1 className="careers-display">{brand.tagline}</h1>
              <p className="careers-lead">
                Browse every open posting, ask about a skill, a city, or a company document, and apply with your résumé.
              </p>
              <Link href="/jobs/benefits" className="inline-flex w-fit items-center gap-2 text-sm text-white/80 underline-offset-4 hover:text-white hover:underline">
                <Gift className="size-4" /> See the full benefits guide
              </Link>
              <div className="careers-trace" aria-hidden="true" />
              <p className="max-w-lg text-xs leading-5 text-white/45">
                A current TS/SCI with Full Scope Polygraph is required.
              </p>
            </div>
            <div className="careers-card rounded-2xl p-5 lg:hidden">
              <p className="careers-kicker">Ask in plain language</p>
              <div className="mt-4 flex flex-col gap-2">
                {brand.examples.slice(0, 3).map((example) => (
                  <button key={example} type="button" onClick={() => askAbout(example)} className="careers-chip rounded-xl px-3 py-2 text-left text-sm">
                    {example}
                  </button>
                ))}
              </div>
            </div>
            <div className="careers-card hidden rounded-2xl p-5 lg:block">
              <p className="careers-kicker">On this page</p>
              <ol className="mt-4 space-y-3 text-sm text-white/75">
                <li className="flex gap-3"><span className="careers-index">01</span> Browse every open posting</li>
                <li className="flex gap-3"><span className="careers-index">02</span> Ask about a skill, a city, or a document</li>
                <li className="flex gap-3"><span className="careers-index">03</span> Apply with your résumé</li>
              </ol>
            </div>
          </section>

          <div className="mx-auto flex w-full max-w-5xl flex-col gap-4 px-4 pb-6 sm:px-8">
            <div className="flex flex-wrap items-end justify-between gap-3">
              <div>
                <h2 className="text-2xl font-medium tracking-tight">All open jobs</h2>
                <p className="mt-1 font-mono text-xs tracking-wide text-white/45">
                  {loading ? "Loading" : `${shown.length} of ${jobs.length}`}
                </p>
              </div>
              <div className="flex w-full flex-col gap-2 sm:w-auto sm:flex-row sm:items-center">
                <div className="flex rounded-xl border border-white/10 p-0.5" role="group" aria-label="Job layout">
                  <button
                    type="button"
                    aria-pressed={view === "cards"}
                    onClick={() => chooseView("cards")}
                    className={`inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-sm ${view === "cards" ? "bg-white/10 text-white" : "text-white/45 hover:text-white"}`}
                  >
                    <LayoutGrid className="size-4" /> Cards
                  </button>
                  <button
                    type="button"
                    aria-pressed={view === "list"}
                    onClick={() => chooseView("list")}
                    className={`inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-sm ${view === "list" ? "bg-white/10 text-white" : "text-white/45 hover:text-white"}`}
                  >
                    <List className="size-4" /> List
                  </button>
                </div>
                <label className="relative w-full sm:w-72">
                  <span className="sr-only">Filter jobs</span>
                  <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-white/35" />
                  <Input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Title, city, or code" className="pl-9" />
                </label>
              </div>
            </div>
            {error && <p className="rounded-xl border border-red-400/30 bg-red-500/10 px-4 py-3 text-sm text-red-100">{error}</p>}
            {loading && (
              <ul className={view === "list" ? "flex flex-col gap-2" : "grid gap-3 md:grid-cols-2"} aria-label="Loading open roles">
                {[0, 1, 2, 3].map((item) => (
                  <li key={item} className={`careers-card animate-pulse rounded-2xl ${view === "list" ? "h-16" : "h-40"}`} />
                ))}
              </ul>
            )}
            {!loading && shown.length === 0 && (
              <p className="careers-card rounded-2xl px-4 py-8 text-center text-sm text-white/55">No open role matches that filter.</p>
            )}
            <ul className={view === "list" ? "flex flex-col gap-2" : "grid gap-3 md:grid-cols-2"}>
              {shown.map((job, index) => (
                <li
                  key={job.requisition_code}
                  className={
                    view === "list"
                      ? "careers-card flex flex-col gap-3 rounded-xl px-4 py-3 sm:flex-row sm:items-center"
                      : "careers-card flex flex-col rounded-2xl p-4"
                  }
                >
                  <div className={view === "list" ? "min-w-0 flex-1" : ""}>
                    <div className="flex items-start justify-between gap-3">
                      <button
                        type="button"
                        onClick={() => setViewCode(job.requisition_code)}
                        className="text-left text-lg font-medium leading-snug tracking-tight hover:text-[#9ce2ff]"
                      >
                        {job.title || "Untitled role"}
                      </button>
                      {view === "cards" && <span className="careers-index">{String(index + 1).padStart(2, "0")}</span>}
                    </div>
                    <p className="mt-1 flex flex-wrap items-center gap-2 text-sm text-white/50">
                      <span className="careers-code font-mono text-xs tracking-wide">{job.requisition_code}</span>
                      {job.location && (
                        <span className="inline-flex items-center gap-1">
                          <MapPin className="size-3.5" /> {job.location}
                        </span>
                      )}
                    </p>
                    {view === "cards" && job.blurb && <p className="mt-3 line-clamp-3 text-sm leading-6 text-white/65">{job.blurb}</p>}
                  </div>
                  <div className={`flex flex-wrap items-center gap-3 ${view === "list" ? "sm:shrink-0" : "mt-auto pt-4"}`}>
                    <Button type="button" size="sm" className="careers-action" onClick={() => setApplyCode(job.requisition_code)}>
                      Apply
                    </Button>
                    <Button type="button" size="sm" variant="outline" className="careers-quiet" onClick={() => setViewCode(job.requisition_code)}>
                      <FileText /> Full description
                    </Button>
                    <button
                      type="button"
                      className="text-sm text-white/50 underline-offset-2 hover:text-white hover:underline"
                      onClick={() => askAbout(`What does ${job.requisition_code} require?`)}
                    >
                      Ask about this
                    </button>
                  </div>
                </li>
              ))}
            </ul>
            <p className="pb-16 text-center text-[11px] leading-5 text-white/35 lg:pb-6">
              {brand.footer || `© ${new Date().getFullYear()} ${brand.company_name}`}
              {" · "}This tool is not authorized for classified processing and is not a FedRAMP system; do not upload classified documents or CUI.
            </p>
          </div>
        </div>

        <aside
          className={
            desk
              ? "careers-aside fixed inset-0 z-40 flex lg:static lg:inset-auto lg:z-auto lg:block lg:w-[24rem] lg:shrink-0 lg:border-l"
              : "careers-aside hidden lg:block lg:w-[24rem] lg:shrink-0 lg:border-l"
          }
        >
          <AskDesk
            open
            onClose={() => setDesk(false)}
            onApply={(code) => {
              setApplyCode(code);
              setDesk(false);
            }}
            onView={setViewCode}
            question={deskAsk?.text}
            questionId={deskAsk?.id}
          />
        </aside>
      </div>

      <button
        type="button"
        onClick={() => setDesk(true)}
        className="careers-action fixed bottom-4 right-4 z-30 inline-flex items-center gap-2 rounded-full px-4 py-3 text-sm font-medium lg:hidden"
      >
        <MessageCircle className="size-4" /> Ask the Desk
      </button>

      {viewCode && (
        <JobDetailDialog
          code={viewCode}
          onClose={closeView}
          onApply={(code) => {
            setViewCode("");
            setDesk(false);
            setApplyCode(code);
          }}
          onAsk={(code) => {
            setViewCode("");
            askAbout(`What does ${code} require?`);
          }}
        />
      )}
      {applying && <ApplyDialog job={applying} onClose={() => setApplyCode("")} />}
    </main>
  );
}
