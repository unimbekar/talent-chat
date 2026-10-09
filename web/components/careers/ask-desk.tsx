"use client";

import { FormEvent, KeyboardEvent, useEffect, useRef, useState } from "react";
import { ArrowUp, Briefcase, MapPin, Sparkles, X } from "lucide-react";

import { BrandMark, useBrand } from "@/components/brand";
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
  message?: string;
  error?: string;
  jobs?: JobCard[];
  closed_jobs?: JobCard[];
  prior_codes?: string[];
  limited?: boolean;
};

type Turn = { question: string; response: ChatResponse };

export function AskDesk({
  open,
  onClose,
  onApply,
  question,
  questionId,
}: {
  open: boolean;
  onClose: () => void;
  onApply: (code: string) => void;
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
    const history = turns.slice(-6).flatMap((turn) => [
      { role: "user", content: turn.question },
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
      if (data.explain_pending && codes.length) {
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
    <section className={`${open ? "flex" : "hidden"} h-full min-h-0 w-full flex-col bg-card lg:flex`}>
      <header className="flex items-center justify-between gap-3 border-b border-line px-4 py-3">
        <div className="flex items-center gap-2">
          <Sparkles className="size-4 text-pine" />
          <div>
            <p className="font-serif text-lg leading-tight">Ask the Desk</p>
            <p className="text-[11px] text-ink/45">Questions about open roles</p>
          </div>
        </div>
        <button type="button" className="rounded-lg p-1 text-ink/50 hover:bg-desk lg:hidden" onClick={onClose} aria-label="Close chat">
          <X className="size-4" />
        </button>
      </header>
      <div ref={scroller} className="flex min-h-0 flex-1 flex-col gap-4 overflow-y-auto px-4 py-4">
        {turns.length === 0 && (
          <div className="rounded-2xl border border-line bg-desk px-4 py-4">
            <p className="text-sm leading-6 text-ink/70">
              Ask which jobs need a tool, which are in a city, or what a requisition code is for. Answers use the postings on file.
            </p>
            <div className="mt-3 flex flex-col gap-2">
              {brand.examples.map((example) => (
                <button
                  key={example}
                  type="button"
                  onClick={() => void ask(example)}
                  className="rounded-xl border border-line bg-card px-3 py-2 text-left text-sm text-ink/80 hover:border-pine/40"
                >
                  {example}
                </button>
              ))}
            </div>
          </div>
        )}
        {turns.map((turn, index) => (
          <div key={index} className="flex flex-col gap-3">
            <p className="max-w-[90%] self-end rounded-2xl rounded-br-md bg-night px-3 py-2 text-sm leading-6 text-white">{turn.question}</p>
            <div className="flex gap-2">
              <BrandMark className="mt-0.5 size-7" />
              <Answer response={turn.response} onApply={onApply} />
            </div>
          </div>
        ))}
        {busy && <p className="text-sm text-ink/50">Looking through open roles…</p>}
      </div>
      <form onSubmit={onSubmit} className="border-t border-line p-3">
        <div className="flex items-end gap-2 rounded-2xl border border-line bg-desk p-2 focus-within:border-pine/40">
          <label className="sr-only" htmlFor="desk-question">
            Question
          </label>
          <textarea
            ref={composer}
            id="desk-question"
            value={draft}
            rows={1}
            maxLength={2000}
            placeholder="Ask about a skill, a city, or a code"
            onChange={(event) => {
              setDraft(event.target.value);
              event.target.style.height = "auto";
              event.target.style.height = `${Math.min(event.target.scrollHeight, 120)}px`;
            }}
            onKeyDown={onKeyDown}
            className="max-h-32 min-h-10 flex-1 resize-none bg-transparent px-2 py-2 text-sm leading-6 outline-none placeholder:text-ink/40"
          />
          <Button type="submit" size="icon" disabled={busy || !draft.trim()} aria-label="Send" className="rounded-xl">
            <ArrowUp />
          </Button>
        </div>
        <p className="mt-2 text-center text-[11px] leading-4 text-ink/40">Enter sends. Shift+Enter adds a line. This desk cannot change recruiter records.</p>
      </form>
    </section>
  );
}

function Answer({ response, onApply }: { response: ChatResponse; onApply: (code: string) => void }) {
  if (response.limited || response.refusal || response.error) {
    return <p className="text-sm leading-6 text-ink/80">{response.message || response.answer}</p>;
  }
  const jobs = response.jobs || [];
  const closed = response.closed_jobs || [];
  return (
    <div className="min-w-0 flex-1 space-y-2">
      {response.notice && <p className="rounded-xl bg-amber-50 px-3 py-2 text-sm text-amber-950">{response.notice}</p>}
      {response.answer && <p className="text-sm leading-6 text-ink/80">{response.answer}</p>}
      {response.explain_pending && !response.answer && <p className="text-sm text-ink/45">Writing a short answer…</p>}
      {jobs.map((job) => (
        <article key={job.requisition_code} className="rounded-xl border border-line bg-white px-3 py-3">
          <p className="font-medium">{job.title || "Untitled role"}</p>
          <p className="mt-1 flex flex-wrap gap-2 text-xs text-ink/50">
            <span className="font-mono">{job.requisition_code}</span>
            {job.location && (
              <span className="inline-flex items-center gap-1">
                <MapPin className="size-3" /> {job.location}
              </span>
            )}
          </p>
          {job.quote && <p className="mt-2 text-xs leading-5 text-ink/60">{job.quote}</p>}
          <button type="button" onClick={() => onApply(job.requisition_code)} className="mt-2 text-sm text-pine-deep underline-offset-2 hover:underline">
            Apply
          </button>
        </article>
      ))}
      {closed.length > 0 && (
        <p className="flex items-center gap-1 text-xs text-ink/45">
          <Briefcase className="size-3" /> {closed.length} closed posting{closed.length === 1 ? "" : "s"} also named that.
        </p>
      )}
    </div>
  );
}
