"use client";

import { FormEvent, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { ArrowRight, Briefcase, ExternalLink, LogIn, MapPin, Search, Sparkles } from "lucide-react";

import { BrandMark, useBrand } from "@/components/brand";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";

type JobCard = {
  requisition_code: string;
  title: string | null;
  location: string | null;
  matched_skills: string[];
  confidence: string;
  description_on_file: boolean;
  description_note: string | null;
  quote: string;
  source_url: string | null;
  distance_miles?: number | null;
  near_place?: string | null;
};

type ChatResponse = {
  refusal?: boolean;
  notice?: string | null;
  answer?: string;
  explain_pending?: boolean;
  message?: string;
  error?: string;
  jobs?: JobCard[];
  prior_codes?: string[];
  limited?: boolean;
};

type Turn = { question: string; response: ChatResponse };

export default function ChatPage() {
  const brand = useBrand();
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [prior, setPrior] = useState<string[]>([]);
  const [turns, setTurns] = useState<Turn[]>([]);
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (turns.length) endRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
  }, [turns.length]);

  function patchTurn(index: number, patch: Partial<ChatResponse>) {
    setTurns((current) => current.map((turn, at) => (at === index ? { ...turn, response: { ...turn.response, ...patch } } : turn)));
  }

  async function ask(message: string) {
    const text = message.trim();
    if (!text || busy) return;
    setBusy(true);
    setDraft("");
    const priorCodes = prior;
    const index = turns.length;
    try {
      const response = await fetch("/api/public/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: text, prior_codes: priorCodes, explain: false }),
      });
      const data = (await response.json()) as ChatResponse;
      if (!response.ok && !data.message && !data.error) {
        data.error = "database";
        data.message = "The job list is unavailable right now.";
      }
      setPrior(data.prior_codes || []);
      setTurns((current) => [...current, { question: text, response: data }]);
      const codes = (data.jobs || []).map((job) => job.requisition_code);
      if (data.explain_pending && codes.length) {
        fetch("/api/public/explain", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ message: text, prior_codes: priorCodes, codes }),
        })
          .then((reply) => reply.json())
          .then((body: { answer?: string; notice?: string | null }) => patchTurn(index, { answer: body.answer || "", notice: body.notice || null, explain_pending: false }))
          .catch(() => patchTurn(index, { explain_pending: false }));
      }
    } catch {
      setTurns((current) => [...current, { question: text, response: { error: "database", message: "The job list is unavailable right now.", jobs: [] } }]);
    } finally {
      setBusy(false);
    }
  }

  function onSubmit(event: FormEvent) {
    event.preventDefault();
    void ask(draft);
  }

  const started = turns.length > 0;

  return (
    <main className="flex min-h-screen flex-col">
      <section
        className={`relative overflow-hidden bg-night text-white transition-[min-height] duration-500 ${started ? "min-h-0" : "min-h-[78vh]"}`}
        style={{ backgroundImage: `url("${brand.hero_url}")`, backgroundSize: "cover", backgroundPosition: "70% center" }}
      >
        <div className="absolute inset-0 bg-gradient-to-r from-night via-night/85 to-night/20" aria-hidden="true" />
        <div className="relative mx-auto flex w-full max-w-6xl flex-col px-5 py-5">
          <header className="flex items-center justify-between gap-4">
            <div className="flex items-center gap-3">
              <BrandMark className="size-10" />
              <div>
                <p className="font-serif text-lg leading-tight">{brand.company_name}</p>
                <p className="text-[11px] uppercase tracking-[0.22em] text-pine-soft">Careers</p>
              </div>
            </div>
            <Button asChild variant="outline" size="sm" className="border-white/20 bg-white/5 text-white hover:border-pine-soft hover:bg-white/10 hover:text-white">
              <Link href="/admin/login">
                <LogIn /> Recruiter sign in
              </Link>
            </Button>
          </header>

          <div className={`max-w-2xl ${started ? "py-6" : "py-16 sm:py-24"}`}>
            {!started && (
              <>
                <p className="inline-flex items-center gap-2 rounded-full border border-pine-soft/30 bg-white/5 px-3 py-1 text-xs text-pine-soft">
                  <Sparkles className="size-3.5" /> AI job search
                </p>
                <h1 className="mt-5 font-serif text-4xl leading-tight sm:text-5xl">{brand.tagline}</h1>
                <p className="mt-4 max-w-xl text-base leading-7 text-white/75">
                  Ask in your own words about skills, a city, or a requisition code. Every answer comes from the job descriptions we have on file.
                </p>
              </>
            )}
            <SearchBox draft={draft} setDraft={setDraft} busy={busy} onSubmit={onSubmit} dark />
            {!started && (
              <div className="mt-4 flex flex-wrap gap-2">
                {brand.examples.map((example) => (
                  <button
                    key={example}
                    type="button"
                    onClick={() => void ask(example)}
                    className="rounded-full border border-white/15 bg-white/5 px-3 py-1.5 text-xs text-white/80 transition hover:border-pine-soft hover:bg-white/10 hover:text-white"
                  >
                    {example}
                  </button>
                ))}
              </div>
            )}
          </div>
        </div>
      </section>

      {started && (
        <div className="mx-auto flex w-full max-w-3xl flex-1 flex-col gap-8 px-5 py-8">
          {turns.map((turn, index) => (
            <section key={index} className="flex animate-fade-up flex-col gap-4" ref={index === turns.length - 1 ? endRef : undefined}>
              <p className="self-end rounded-2xl rounded-br-md bg-night px-4 py-2.5 text-sm text-white shadow-card">{turn.question}</p>
              <Answer response={turn.response} />
            </section>
          ))}
          {busy && <p className="text-sm text-ink/60">Searching open jobs…</p>}
        </div>
      )}

      {started && (
        <div className="sticky bottom-0 border-t border-line bg-desk/90 backdrop-blur">
          <div className="mx-auto w-full max-w-3xl px-5 py-3">
            <SearchBox draft={draft} setDraft={setDraft} busy={busy} onSubmit={onSubmit} placeholder="Ask a follow-up, such as “which of these are remote?”" />
          </div>
        </div>
      )}

      <footer className="border-t border-line bg-desk">
        <div className="mx-auto flex w-full max-w-6xl flex-wrap items-center justify-between gap-2 px-5 py-4 text-xs text-ink/55">
          <p>
            © {new Date().getFullYear()} {brand.company_name}
          </p>
          <a href={brand.careers_url} className="hover:text-pine-deep">
            All openings on our careers page
          </a>
        </div>
      </footer>
    </main>
  );
}

function SearchBox({
  draft,
  setDraft,
  busy,
  onSubmit,
  dark = false,
  placeholder = "Java developer jobs near Chantilly",
}: {
  draft: string;
  setDraft: (value: string) => void;
  busy: boolean;
  onSubmit: (event: FormEvent) => void;
  dark?: boolean;
  placeholder?: string;
}) {
  return (
    <form onSubmit={onSubmit} className={`flex items-center gap-2 rounded-2xl p-1.5 shadow-lift ${dark ? "mt-8 bg-white" : "border border-line bg-card"}`}>
      <Search className="ml-3 size-5 shrink-0 text-ink/40" aria-hidden="true" />
      <label className="sr-only" htmlFor={dark ? "question" : "follow-up"}>
        Question
      </label>
      <input
        id={dark ? "question" : "follow-up"}
        value={draft}
        onChange={(event) => setDraft(event.target.value)}
        placeholder={placeholder}
        maxLength={2000}
        autoComplete="off"
        className="h-11 min-w-0 flex-1 bg-transparent text-base text-ink outline-none placeholder:text-ink/40"
      />
      <Button type="submit" disabled={busy || !draft.trim()} variant={dark ? "gold" : "default"} className="h-11 px-5">
        {busy ? "Searching…" : "Search"} <ArrowRight />
      </Button>
    </form>
  );
}

function Answer({ response }: { response: ChatResponse }) {
  if (response.limited || response.refusal) {
    return <p className="panel px-4 py-3 text-sm leading-6">{response.message || response.answer}</p>;
  }
  if (response.error === "database") {
    return (
      <p className="rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800" role="alert">
        {response.message || "The job list is unavailable right now."}
      </p>
    );
  }
  const jobs = response.jobs || [];
  return (
    <div className="flex flex-col gap-3">
      {response.notice && <p className="rounded-xl border border-line bg-card px-4 py-3 text-sm text-ink/70">{response.notice}</p>}
      {response.explain_pending ? (
        <div className="panel flex flex-col gap-2 px-4 py-4" aria-live="polite">
          <p className="flex items-center gap-2 text-xs font-medium uppercase tracking-wide text-pine-deep">
            <Sparkles className="size-3.5" /> Writing a short summary
          </p>
          <div className="h-3 w-11/12 animate-pulse rounded bg-desk" />
          <div className="h-3 w-3/4 animate-pulse rounded bg-desk" />
        </div>
      ) : (
        response.answer && (
          <div className="panel px-4 py-4 text-sm leading-7">
            <p className="mb-1 flex items-center gap-2 text-xs font-medium uppercase tracking-wide text-pine-deep">
              <Sparkles className="size-3.5" /> Summary
            </p>
            {response.answer}
          </div>
        )
      )}
      {jobs.length > 0 && (
        <p className="text-xs font-medium uppercase tracking-wide text-ink/50">
          {jobs.length} {jobs.length === 1 ? "opening" : "openings"}
        </p>
      )}
      {jobs.map((job) => (
        <article key={job.requisition_code} className="panel group p-5 transition hover:-translate-y-0.5 hover:shadow-lift">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div className="min-w-0">
              <p className="inline-flex items-center gap-1.5 font-mono text-xs text-pine-deep">
                <Briefcase className="size-3.5" /> {job.requisition_code}
              </p>
              <h3 className="mt-1 font-serif text-xl leading-snug">{job.title}</h3>
              {job.location && (
                <p className="mt-1 inline-flex items-center gap-1 text-sm text-ink/65">
                  <MapPin className="size-3.5" /> {job.location}
                  {job.distance_miles != null && job.near_place && (
                    <span className="text-ink/50">
                      {" "}
                      · {job.distance_miles} mi from {job.near_place}
                    </span>
                  )}
                </p>
              )}
            </div>
            {job.source_url && (
              <Button asChild variant="outline" size="sm">
                <a href={job.source_url} target="_blank" rel="noreferrer">
                  View posting <ExternalLink />
                </a>
              </Button>
            )}
          </div>
          {(job.matched_skills || []).length > 0 && (
            <div className="mt-3 flex flex-wrap gap-1.5">
              {job.matched_skills.map((skill) => (
                <Badge key={skill}>{skill}</Badge>
              ))}
            </div>
          )}
          {job.description_note && <p className="mt-3 text-sm text-ink/60">{job.description_note}</p>}
          {job.quote && <p className="mt-3 line-clamp-4 text-sm leading-6 text-ink/75">{job.quote}</p>}
        </article>
      ))}
    </div>
  );
}
