"use client";

import { FormEvent, KeyboardEvent, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { ArrowUp, Briefcase, ExternalLink, MapPin, Sparkles } from "lucide-react";

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
  closed?: boolean;
};

type ChatResponse = {
  refusal?: boolean;
  notice?: string | null;
  answer?: string;
  explain_pending?: boolean;
  message?: string;
  error?: string;
  jobs?: JobCard[];
  closed_jobs?: JobCard[];
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
  const latest = useRef<HTMLElement>(null);
  const composer = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    latest.current?.scrollIntoView({ behavior: "smooth", block: "start" });
  }, [turns, busy]);

  function patchTurn(index: number, patch: Partial<ChatResponse>) {
    setTurns((current) => current.map((turn, at) => (at === index ? { ...turn, response: { ...turn.response, ...patch } } : turn)));
  }

  async function ask(message: string) {
    const text = message.trim();
    if (!text || busy) return;
    setBusy(true);
    setDraft("");
    if (composer.current) composer.current.style.height = "auto";
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
          .then((body: { answer?: string; notice?: string | null }) => {
            const patch: Partial<ChatResponse> = { notice: body.notice || null, explain_pending: false };
            if (body.answer) patch.answer = body.answer;
            patchTurn(index, patch);
          })
          .catch(() => patchTurn(index, { explain_pending: false }));
      }
    } catch {
      setTurns((current) => [...current, { question: text, response: { error: "database", message: "The job list is unavailable right now.", jobs: [] } }]);
    } finally {
      setBusy(false);
      composer.current?.focus();
    }
  }

  function onSubmit(event: FormEvent) {
    event.preventDefault();
    void ask(draft);
  }

  function onKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      void ask(draft);
    }
  }

  const started = turns.length > 0;

  return (
    <main className="flex h-[100dvh] flex-col bg-desk text-ink">
      <header className="flex items-center justify-between gap-4 border-b border-line bg-card/90 px-4 py-3 backdrop-blur sm:px-6">
        <div className="flex min-w-0 items-center gap-3">
          <BrandMark className="size-9" />
          <div className="min-w-0">
            <p className="truncate font-serif text-lg leading-tight">{brand.company_name}</p>
            <p className="text-[11px] uppercase tracking-[0.18em] text-ink/45">Careers assistant</p>
          </div>
        </div>
        <div className="flex items-center gap-3">
          <a href={brand.careers_url} className="hidden text-sm text-ink/60 hover:text-pine-deep sm:inline">
            All openings
          </a>
          <Button asChild variant="outline" size="sm">
            <Link href="/admin/login">Recruiter sign in</Link>
          </Button>
        </div>
      </header>

      <div className="flex-1 overflow-y-auto">
        <div className="mx-auto flex w-full max-w-3xl flex-col gap-8 px-4 py-8 sm:px-6">
          {!started && <Welcome examples={brand.examples} tagline={brand.tagline} onAsk={(example) => void ask(example)} />}
          {turns.map((turn, index) => (
            <section key={index} ref={index === turns.length - 1 ? latest : undefined} className="flex animate-fade-up flex-col gap-4">
              <p className="max-w-[85%] self-end rounded-2xl rounded-br-md bg-night px-4 py-2.5 text-sm leading-6 text-white shadow-card">{turn.question}</p>
              <div className="flex gap-3">
                <BrandMark className="mt-1 size-8" />
                <div className="min-w-0 flex-1">
                  <Answer response={turn.response} />
                </div>
              </div>
            </section>
          ))}
          {busy && (
            <div className="flex gap-3" aria-live="polite">
              <BrandMark className="mt-1 size-8" />
              <p className="rounded-2xl rounded-bl-md border border-line bg-card px-4 py-3 text-sm text-ink/60 shadow-card">Looking through open roles…</p>
            </div>
          )}
        </div>
      </div>

      <div className="border-t border-line bg-desk/95 backdrop-blur">
        <form onSubmit={onSubmit} className="mx-auto w-full max-w-3xl px-4 py-3 sm:px-6">
          <div className="flex items-end gap-2 rounded-2xl border border-line bg-card p-2 shadow-card focus-within:border-pine/50 focus-within:ring-4 focus-within:ring-pine/10">
            <label className="sr-only" htmlFor="question">
              Question
            </label>
            <textarea
              ref={composer}
              id="question"
              value={draft}
              rows={1}
              onChange={(event) => {
                setDraft(event.target.value);
                event.target.style.height = "auto";
                event.target.style.height = `${Math.min(event.target.scrollHeight, 140)}px`;
              }}
              onKeyDown={onKeyDown}
              placeholder={started ? "Ask a follow-up" : "Ask about a skill, a city, or a requisition code"}
              maxLength={2000}
              autoComplete="off"
              className="max-h-36 min-h-11 flex-1 resize-none bg-transparent px-2 py-2.5 text-base leading-6 text-ink outline-none placeholder:text-ink/40"
            />
            <Button type="submit" size="icon" disabled={busy || !draft.trim()} aria-label="Send" className="mb-0.5 rounded-xl">
              <ArrowUp />
            </Button>
          </div>
          <p className="mt-2 text-center text-[11px] leading-5 text-ink/45">Answers come from published job postings. Enter sends. Shift+Enter adds a line.</p>
        </form>
        <footer className="border-t border-line/80 px-4 py-2 text-center text-[11px] text-ink/40">
          {brand.footer || `© ${new Date().getFullYear()} ${brand.company_name}`}
        </footer>
      </div>
    </main>
  );
}

function Welcome({ examples, tagline, onAsk }: { examples: string[]; tagline: string; onAsk: (example: string) => void }) {
  return (
    <div className="mx-auto flex max-w-xl flex-col items-center px-2 pt-10 text-center sm:pt-16">
      <p className="inline-flex items-center gap-2 rounded-full border border-line bg-card px-3 py-1 text-xs text-pine-deep shadow-card">
        <Sparkles className="size-3.5" /> Open roles
      </p>
      <h1 className="mt-5 font-serif text-4xl leading-tight">{tagline}</h1>
      <p className="mt-3 max-w-md text-sm leading-6 text-ink/65">
        Ask which jobs require a tool, which are in a city, or what a requisition code is for. Each card quotes the posting line that matched.
      </p>
      <div className="mt-6 flex flex-wrap justify-center gap-2">
        {examples.map((example) => (
          <button
            key={example}
            type="button"
            onClick={() => onAsk(example)}
            className="rounded-full border border-line bg-card px-3 py-1.5 text-left text-sm text-ink/80 shadow-card transition hover:border-pine/40 hover:text-ink"
          >
            {example}
          </button>
        ))}
      </div>
    </div>
  );
}

function Answer({ response }: { response: ChatResponse }) {
  if (response.limited || response.refusal) {
    return <p className="rounded-2xl rounded-bl-md border border-line bg-card px-4 py-3 text-sm leading-6 shadow-card">{response.message || response.answer}</p>;
  }
  if (response.error === "database") {
    return (
      <p className="rounded-2xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800" role="alert">
        {response.message || "The job list is unavailable right now."}
      </p>
    );
  }
  const jobs = response.jobs || [];
  const closed = response.closed_jobs || [];
  return (
    <div className="flex flex-col gap-3">
      {response.notice && <p className="rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-950">{response.notice}</p>}
      {response.answer && (
        <div className="rounded-2xl rounded-bl-md border border-line bg-card px-4 py-4 text-sm leading-7 shadow-card">
          <p className="mb-1 flex items-center gap-2 text-xs font-medium uppercase tracking-wide text-pine-deep">
            <Sparkles className="size-3.5" /> Summary
          </p>
          {response.answer}
          {response.explain_pending && <p className="mt-2 text-xs text-ink/45">Checking the posting lines…</p>}
        </div>
      )}
      {jobs.length > 0 && (
        <p className="text-xs font-medium uppercase tracking-[0.14em] text-ink/45">
          {jobs.length} open {jobs.length === 1 ? "role" : "roles"}
        </p>
      )}
      {jobs.map((job) => (
        <JobArticle key={job.requisition_code} job={job} />
      ))}
      {closed.length > 0 && (
        <div className="mt-2 flex flex-col gap-3">
          <p className="text-xs font-medium uppercase tracking-[0.14em] text-ink/45">Closed postings that name this</p>
          {closed.map((job) => (
            <JobArticle key={job.requisition_code} job={{ ...job, closed: true }} />
          ))}
        </div>
      )}
    </div>
  );
}

function JobArticle({ job }: { job: JobCard }) {
  return (
    <article className={`rounded-2xl border bg-card p-4 shadow-card sm:p-5 ${job.closed ? "border-dashed border-line" : "border-line"}`}>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="inline-flex items-center gap-1.5 font-mono text-xs text-pine-deep">
            <Briefcase className="size-3.5" /> {job.requisition_code}
            {job.closed && <span className="rounded-full bg-desk px-2 py-0.5 font-sans text-[10px] uppercase tracking-wide text-ink/55">Closed</span>}
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
      {job.quote && (
        <blockquote className="mt-3 border-l-2 border-pine/40 pl-3 text-sm leading-6 text-ink/75">
          <span className="mb-1 block text-[11px] font-medium uppercase tracking-[0.14em] text-ink/40">From the posting</span>
          {job.quote}
        </blockquote>
      )}
    </article>
  );
}
