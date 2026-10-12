"use client";

import { FormEvent, KeyboardEvent, useEffect, useRef, useState } from "react";
import { ArrowUp, BookOpen, Briefcase, ChevronDown, FileText, MapPin, Sparkles, X } from "lucide-react";

import { BrandMark, useBrand } from "@/components/brand";
import { AnswerText, SectionBody, type KbSource } from "@/components/knowledge/section-view";
import { Button } from "@/components/ui/button";

type JobCard = {
  requisition_code: string;
  title: string | null;
  location: string | null;
  quote: string;
  closed?: boolean;
};

type ChatResponse = {
  refusal?: boolean;
  notice?: string | null;
  answer?: string;
  explain_pending?: boolean;
  knowledge_pending?: boolean;
  written?: boolean;
  overview?: boolean;
  message?: string;
  error?: string;
  jobs?: JobCard[];
  closed_jobs?: JobCard[];
  jobs_note?: string;
  prior_codes?: string[];
  sources?: KbSource[];
  limited?: boolean;
};

type Turn = { question: string; response: ChatResponse };

const DOT = "bg-[rgb(var(--c-accent))]";

export function AskDesk({
  open,
  onClose,
  onApply,
  onView,
  question,
  questionId,
}: {
  open: boolean;
  onClose: () => void;
  onApply: (code: string) => void;
  onView: (code: string) => void;
  question?: string;
  questionId?: number;
}) {
  const brand = useBrand();
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [prior, setPrior] = useState<string[]>([]);
  const [turns, setTurns] = useState<Turn[]>([]);
  const scroller = useRef<HTMLDivElement>(null);
  const composer = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    const node = scroller.current;
    if (node) node.scrollTop = node.scrollHeight;
  }, [turns, busy]);

  function patchTurn(index: number, patch: Partial<ChatResponse>) {
    setTurns((current) => current.map((turn, at) => (at === index ? { ...turn, response: { ...turn.response, ...patch } } : turn)));
  }

  async function ask(message: string) {
    const text = message.trim();
    if (!text || busy) return;
    const history = turns.slice(-4).flatMap((turn) => [
      { role: "user", content: turn.question.slice(0, 800) },
      { role: "assistant", content: (turn.response.answer || turn.response.message || "").slice(0, 800) },
    ]);
    setBusy(true);
    setDraft("");
    if (composer.current) composer.current.style.height = "auto";
    const priorCodes = prior;
    const index = turns.length;
    try {
      const response = await fetch("/api/public/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: text, prior_codes: priorCodes, history, explain: false }),
      });
      const data = (await response.json()) as ChatResponse;
      if (!response.ok && !data.message && !data.error) {
        data.error = "database";
        data.message = "The job list is unavailable right now.";
      }
      setPrior(data.prior_codes || []);
      setTurns((current) => [...current, { question: text, response: data }]);
      const codes = (data.jobs || []).map((job) => job.requisition_code);
      if (data.knowledge_pending) {
        fetch("/api/public/knowledge/answer", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ message: text, history }),
        })
          .then((reply) => reply.json())
          .then((body: { answer?: string }) => {
            const patch: Partial<ChatResponse> = { knowledge_pending: false, explain_pending: false };
            if (body.answer) {
              patch.answer = body.answer;
              patch.written = true;
            }
            patchTurn(index, patch);
          })
          .catch(() => patchTurn(index, { knowledge_pending: false, explain_pending: false }));
      } else if (data.explain_pending && codes.length) {
        fetch("/api/public/explain", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ message: text, prior_codes: priorCodes, codes, history }),
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
      setTurns((current) => [
        ...current,
        { question: text, response: { error: "database", message: "The job list is unavailable right now.", jobs: [] } },
      ]);
    } finally {
      setBusy(false);
      composer.current?.focus();
    }
  }

  useEffect(() => {
    if (questionId && question) void ask(question);
    // Ask once for each button press. ask closes over the latest turns.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [questionId]);

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

  return (
    <section className={`${open ? "flex" : "hidden"} desk-text h-full min-h-0 w-full flex-col bg-transparent lg:flex`}>
      <header className="desk-line flex items-center justify-between gap-3 border-b px-4 py-3">
        <div className="flex items-center gap-2.5">
          <span className="desk-surface grid size-8 place-items-center rounded-xl">
            <Sparkles className="desk-accent size-4" />
          </span>
          <div>
            <p className="desk-text text-lg font-medium leading-tight tracking-tight">Ask the Desk</p>
            <p className="desk-faint text-[11px]">Open roles, benefits, and company documents</p>
          </div>
        </div>
        <button type="button" className="desk-faint desk-hover rounded-lg p-1 lg:hidden" onClick={onClose} aria-label="Close chat">
          <X className="size-4" />
        </button>
      </header>
      <div ref={scroller} className="flex min-h-0 flex-1 flex-col gap-5 overflow-y-auto px-4 py-4" aria-live="polite">
        {turns.length === 0 && (
          <div className="desk-surface rounded-2xl px-4 py-4">
            <p className="desk-muted text-sm leading-6">
              Ask which jobs need a tool, which are in a city, or what the benefits are. Job answers quote the postings. Benefit answers quote the company documents.
            </p>
            <div className="mt-3 flex flex-col gap-2">
              {[...brand.examples, "Show me the health benefits"].filter((item, at, all) => all.indexOf(item) === at).map((example) => (
                <button key={example} type="button" onClick={() => void ask(example)} className="careers-chip rounded-xl px-3 py-2 text-left text-sm">
                  {example}
                </button>
              ))}
            </div>
          </div>
        )}
        {turns.map((turn, index) => (
          <div key={index} className="flex flex-col gap-3">
            <p className="desk-bubble max-w-[90%] self-end rounded-2xl rounded-br-md px-3 py-2 text-sm leading-6">{turn.question}</p>
            <div className="flex gap-2.5">
              <BrandMark className="mt-0.5 size-7 shrink-0" />
              <Answer response={turn.response} onApply={onApply} onView={onView} onAsk={(text) => void ask(text)} />
            </div>
          </div>
        ))}
        {busy && (
          <p className="desk-faint inline-flex items-center gap-2 text-sm">
            <span className="careers-pulse" aria-hidden="true" /> Looking that up…
          </p>
        )}
      </div>
      <form onSubmit={onSubmit} className="desk-line border-t p-3">
        <div className="desk-field flex items-end gap-2 rounded-2xl p-2">
          <label className="sr-only" htmlFor="desk-question">
            Question
          </label>
          <textarea
            ref={composer}
            id="desk-question"
            value={draft}
            rows={1}
            maxLength={2000}
            placeholder="Ask about a skill, a city, or a benefit"
            onChange={(event) => {
              setDraft(event.target.value);
              event.target.style.height = "auto";
              event.target.style.height = `${Math.min(event.target.scrollHeight, 120)}px`;
            }}
            onKeyDown={onKeyDown}
            className="max-h-32 min-h-10 flex-1 resize-none bg-transparent px-2 py-2 text-sm leading-6 outline-none"
          />
          <Button type="submit" size="icon" disabled={busy || !draft.trim()} aria-label="Send" className="careers-action rounded-xl">
            <ArrowUp />
          </Button>
        </div>
        <p className="desk-faint mt-2 text-center text-[11px] leading-4">Enter sends. Shift+Enter adds a line. This desk cannot change recruiter records.</p>
      </form>
    </section>
  );
}

function Answer({
  response,
  onApply,
  onView,
  onAsk,
}: {
  response: ChatResponse;
  onApply: (code: string) => void;
  onView: (code: string) => void;
  onAsk: (text: string) => void;
}) {
  if (response.limited || response.refusal || response.error) {
    return <p className="desk-muted text-sm leading-6">{response.message || response.answer}</p>;
  }
  const jobs = response.jobs || [];
  const closed = response.closed_jobs || [];
  const sources = response.sources || [];
  const document = sources[0]?.title;
  return (
    <div className="min-w-0 flex-1 space-y-3">
      {response.notice && <p className="desk-warn desk-surface rounded-xl px-3 py-2 text-sm">{response.notice}</p>}
      {response.answer && (
        <div className="desk-text">
          <AnswerText text={response.answer} dotClassName={DOT} />
        </div>
      )}
      {response.knowledge_pending && (
        <div className="flex items-center gap-2" aria-label="Writing a plain-language answer">
          <span className="desk-shimmer h-1.5 w-24 rounded-full" />
          <span className="desk-faint text-xs">Writing a plain-language answer…</span>
        </div>
      )}
      {response.written && document && (
        <p className="desk-faint inline-flex items-center gap-1.5 text-[11px]">
          <Sparkles className="size-3" /> Written from {document}. Every figure is checked against the document.
        </p>
      )}
      {sources.length > 0 &&
        (response.overview ? (
          <OverviewGrid sources={sources} onAsk={onAsk} />
        ) : (
          <div className="space-y-2">
            {sources.map((source, index) => (
              <SourceCard key={`${source.title}-${source.section}-${index}`} source={source} />
            ))}
          </div>
        ))}
      {response.explain_pending && !response.knowledge_pending && !response.answer && <p className="desk-faint text-sm">Writing a short answer…</p>}
      {response.jobs_note && <p className="desk-faint text-xs">{response.jobs_note}</p>}
      {jobs.length > 0 && sources.length > 0 && <p className="desk-faint pt-1 text-[11px] font-medium uppercase tracking-[0.14em]">Matching roles</p>}
      {jobs.map((job) => (
        <article key={job.requisition_code} className="desk-surface rounded-xl px-3 py-3">
          <button
            type="button"
            onClick={() => onView(job.requisition_code)}
            className="desk-text text-left font-medium underline-offset-2 hover:underline"
          >
            {job.title || "Untitled role"}
          </button>
          <p className="desk-faint mt-1 flex flex-wrap gap-2 text-xs">
            <span className="careers-code font-mono">{job.requisition_code}</span>
            {job.location && (
              <span className="inline-flex items-center gap-1">
                <MapPin className="size-3" /> {job.location}
              </span>
            )}
          </p>
          {job.quote && <p className="desk-muted mt-2 line-clamp-4 text-xs leading-5">{job.quote}</p>}
          <div className="mt-2 flex items-center gap-4 text-sm">
            <button type="button" onClick={() => onView(job.requisition_code)} className="desk-muted inline-flex items-center gap-1 underline-offset-2 hover:underline">
              <FileText className="size-3.5" /> Full description
            </button>
            <button type="button" onClick={() => onApply(job.requisition_code)} className="desk-accent font-medium underline-offset-2 hover:underline">
              Apply
            </button>
          </div>
        </article>
      ))}
      {closed.length > 0 && (
        <p className="desk-faint flex items-center gap-1 text-xs">
          <Briefcase className="size-3" /> {closed.length} closed posting{closed.length === 1 ? "" : "s"} also named that.
        </p>
      )}
    </div>
  );
}

function SourceCard({ source }: { source: KbSource }) {
  const [open, setOpen] = useState(false);
  const blocks = source.blocks?.length ? source.blocks : [{ kind: "text" as const, text: source.excerpt }];
  return (
    <div className="desk-surface overflow-hidden rounded-xl">
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        aria-expanded={open}
        className="desk-hover flex w-full items-center gap-2 px-3 py-2 text-left"
      >
        <BookOpen className="desk-accent size-3.5 shrink-0" />
        <span className="min-w-0 flex-1">
          {source.kicker && <span className="careers-index mr-2">{source.kicker}</span>}
          <span className="desk-text text-xs font-medium">{source.section || source.title}</span>
          {source.section && <span className="desk-faint text-xs"> · {source.title}</span>}
        </span>
        <span className="desk-faint text-[11px]">{open ? "Hide" : "Source"}</span>
        <ChevronDown className={`desk-faint size-3.5 transition ${open ? "rotate-180" : ""}`} />
      </button>
      {open && (
        <div className="desk-line desk-text border-t px-3 py-3">
          <SectionBody blocks={blocks} dotClassName={DOT} />
          {source.anchor && (
            <a href={source.anchor} className="desk-accent mt-3 inline-flex text-xs font-medium underline-offset-2 hover:underline">
              Open in the benefits guide →
            </a>
          )}
        </div>
      )}
    </div>
  );
}

function OverviewGrid({ sources, onAsk }: { sources: KbSource[]; onAsk: (text: string) => void }) {
  return (
    <div>
      <p className="desk-faint mb-2 text-[11px]">Tap an area for its details.</p>
      <div className="grid gap-2 sm:grid-cols-2">
        {sources.map((source) => {
          const lead = source.blocks?.find((block) => block.kind === "text");
          return (
            <button
              key={`${source.title}-${source.section}`}
              type="button"
              onClick={() => onAsk(`Tell me about ${source.section || source.title}`)}
              className="careers-chip rounded-xl px-3 py-2.5 text-left"
            >
              {source.kicker && <span className="careers-index block">{source.kicker}</span>}
              <span className="desk-text mt-0.5 block text-sm font-medium">{source.section || source.title}</span>
              {lead && lead.kind === "text" && <span className="desk-faint mt-1 line-clamp-2 block text-xs leading-5">{lead.text}</span>}
            </button>
          );
        })}
      </div>
    </div>
  );
}
