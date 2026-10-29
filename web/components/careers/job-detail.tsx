"use client";

import { useEffect, useRef, useState } from "react";
import { ExternalLink, MapPin, MessageCircle, X } from "lucide-react";

import { Button } from "@/components/ui/button";

type Posting = {
  requisition_code: string;
  title: string | null;
  location: string | null;
  paragraphs: string[];
  description_note: string | null;
  source_url: string | null;
};

type Block = { kind: "heading" | "item" | "text"; text: string };

const LIST_SECTION = /skill|qualification|requirement|responsibilit|desired|duties|experience|education/i;

const HEADING_WORDS = /skill|qualification|requirement|responsibilit|duties|overview|description|education|about|benefit|summary/i;

function isHeading(text: string, listing: boolean): boolean {
  if (text.length > 60 || /[.:;!?]$/.test(text) || text.includes(": ")) return false;
  return !listing || HEADING_WORDS.test(text);
}

function blocks(paragraphs: string[]): Block[] {
  let listing = false;
  return paragraphs.map((text) => {
    if (isHeading(text, listing)) {
      listing = LIST_SECTION.test(text);
      return { kind: "heading", text };
    }
    return { kind: listing ? "item" : "text", text };
  });
}

function Labeled({ text }: { text: string }) {
  const split = text.match(/^([^:]{2,40}):\s+([\s\S]+)$/);
  if (!split) return <>{text}</>;
  return (
    <>
      <span className="font-medium text-white">{split[1]}:</span> {split[2]}
    </>
  );
}

export function JobDetailDialog({
  code,
  onClose,
  onApply,
  onAsk,
}: {
  code: string;
  onClose: () => void;
  onApply: (code: string) => void;
  onAsk?: (code: string) => void;
}) {
  const [posting, setPosting] = useState<Posting | null>(null);
  const [error, setError] = useState("");
  const closeButton = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    let live = true;
    setPosting(null);
    setError("");
    fetch(`/api/public/jobs/${encodeURIComponent(code)}`)
      .then(async (response) => {
        const body = await response.json().catch(() => ({}));
        if (!live) return;
        if (!response.ok) setError(body.message || "This posting could not be loaded.");
        else setPosting(body as Posting);
      })
      .catch(() => live && setError("This posting could not be loaded."));
    return () => {
      live = false;
    };
  }, [code]);

  useEffect(() => {
    closeButton.current?.focus();
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    const overflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("keydown", onKey);
      document.body.style.overflow = overflow;
    };
  }, [onClose]);

  return (
    <div
      className="fixed inset-0 z-50 flex items-end justify-center bg-black/70 backdrop-blur-sm sm:items-center sm:p-6"
      role="dialog"
      aria-modal="true"
      aria-labelledby="posting-title"
      onClick={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
    >
      <div className="careers-sheet flex max-h-[92dvh] w-full flex-col overflow-hidden rounded-t-3xl animate-fade-in sm:max-h-[88dvh] sm:max-w-2xl sm:rounded-3xl">
        <div className="flex items-start justify-between gap-3 border-b border-white/10 px-5 py-4">
          <div className="min-w-0">
            <p className="careers-kicker">Open role</p>
            <h2 id="posting-title" className="mt-2 text-2xl font-medium leading-tight tracking-tight">
              {posting?.title || "Loading…"}
            </h2>
            <p className="mt-1 flex flex-wrap items-center gap-2 text-sm text-white/55">
              <span className="careers-code font-mono text-xs">{code}</span>
              {posting?.location && (
                <span className="inline-flex items-center gap-1">
                  <MapPin className="size-3.5" /> {posting.location}
                </span>
              )}
            </p>
          </div>
          <button ref={closeButton} type="button" onClick={onClose} className="rounded-lg p-1 text-white/50 hover:bg-white/10" aria-label="Close">
            <X className="size-5" />
          </button>
        </div>

        <div className="min-h-0 flex-1 overflow-y-auto overscroll-contain px-5 py-5">
          {error && <p className="rounded-xl border border-red-400/30 bg-red-500/10 px-4 py-3 text-sm text-red-100">{error}</p>}
          {!error && !posting && (
            <div className="space-y-3" aria-label="Loading posting">
              {[80, 95, 70, 90, 60].map((width, index) => (
                <div key={index} className="h-3 animate-pulse rounded bg-white/10" style={{ width: `${width}%` }} />
              ))}
            </div>
          )}
          {posting?.description_note && <p className="text-sm text-white/60">{posting.description_note}</p>}
          {posting && posting.paragraphs.length > 0 && (
            <div className="space-y-2 text-sm leading-6 text-white/75">
              {blocks(posting.paragraphs).map((block, index) =>
                block.kind === "heading" ? (
                  <h3 key={index} className="pt-3 text-lg font-medium tracking-tight text-white first:pt-0">
                    {block.text}
                  </h3>
                ) : block.kind === "item" ? (
                  <p key={index} className="relative pl-4 before:absolute before:left-0 before:top-[0.6rem] before:size-1.5 before:rounded-full before:bg-pine/60">
                    <Labeled text={block.text} />
                  </p>
                ) : (
                  <p key={index}>
                    <Labeled text={block.text} />
                  </p>
                ),
              )}
            </div>
          )}
        </div>

        <div className="border-t border-white/10 px-5 py-3 pb-[calc(env(safe-area-inset-bottom)+0.75rem)]">
          <p className="mb-2 text-[11px] leading-4 text-white/45">Apply and Janus Soft Job Matching scores your résumé as soon as you upload it.</p>
          <div className="flex flex-wrap items-center gap-3">
          <Button type="button" className="careers-action" onClick={() => onApply(code)} disabled={!!error}>
            Apply
          </Button>
          {onAsk && (
            <Button type="button" variant="outline" className="careers-quiet" onClick={() => onAsk(code)} disabled={!!error}>
              <MessageCircle /> Ask about this
            </Button>
          )}
          {posting?.source_url && (
            <a
              href={posting.source_url}
              target="_blank"
              rel="noopener noreferrer"
              className="ml-auto inline-flex items-center gap-1 text-sm text-white/55 underline-offset-2 hover:text-white hover:underline"
            >
              On the careers site <ExternalLink className="size-3.5" />
            </a>
          )}
          </div>
        </div>
      </div>
    </div>
  );
}
