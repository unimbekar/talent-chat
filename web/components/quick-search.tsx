"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { Briefcase, Route, Search, Sparkles, User } from "lucide-react";

import { askAssistant } from "@/lib/assistant";

type Hit = { key: string; group: string; title: string; detail: string; href?: string; ask?: string };

type SearchResponse = {
  jobs: { code: string; title: string | null; location: string | null; status: string; href: string }[];
  candidates: { id: string; name: string | null; email: string | null; location: string | null; title: string | null; href: string }[];
  submissions: { id: string; candidate: string | null; code: string; title: string | null; stage: string; href: string }[];
};

const ICONS: Record<string, typeof Search> = { Jobs: Briefcase, Candidates: User, Submissions: Route, Assistant: Sparkles };

export function QuickSearch() {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [data, setData] = useState<SearchResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [active, setActive] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        setOpen((value) => !value);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  useEffect(() => {
    if (open) {
      setActive(0);
      setTimeout(() => inputRef.current?.focus(), 20);
    }
  }, [open]);

  useEffect(() => {
    const term = query.trim();
    if (term.length < 2) {
      setData(null);
      return;
    }
    const controller = new AbortController();
    const timer = setTimeout(() => {
      setLoading(true);
      fetch(`/api/admin/search?q=${encodeURIComponent(term)}`, { signal: controller.signal })
        .then((response) => (response.ok ? response.json() : null))
        .then((body) => {
          setData(body);
          setActive(0);
        })
        .catch(() => undefined)
        .finally(() => setLoading(false));
    }, 140);
    return () => {
      clearTimeout(timer);
      controller.abort();
    };
  }, [query]);

  const hits = useMemo<Hit[]>(() => {
    const out: Hit[] = [];
    for (const job of data?.jobs || []) {
      out.push({ key: `j${job.code}`, group: "Jobs", title: `${job.code} · ${job.title || ""}`, detail: [job.location, job.status !== "open" ? job.status : ""].filter(Boolean).join(" · "), href: job.href });
    }
    for (const person of data?.candidates || []) {
      out.push({ key: `c${person.id}`, group: "Candidates", title: person.name || "Unnamed résumé", detail: [person.title, person.location, person.email].filter(Boolean).join(" · "), href: person.href });
    }
    for (const row of data?.submissions || []) {
      out.push({ key: `s${row.id}`, group: "Submissions", title: `${row.candidate || "Candidate"} → ${row.code}`, detail: [row.title, row.stage].filter(Boolean).join(" · "), href: row.href });
    }
    const term = query.trim();
    if (term) out.push({ key: "ask", group: "Assistant", title: `Ask the assistant: “${term}”`, detail: "Answers from your data, with filters and counts", ask: term });
    return out;
  }, [data, query]);

  function choose(hit: Hit | undefined) {
    if (!hit) return;
    setOpen(false);
    setQuery("");
    if (hit.ask) askAssistant(hit.ask);
    else if (hit.href) router.push(hit.href);
  }

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="inline-flex items-center gap-2 rounded-lg border border-white/10 bg-white/5 px-3 py-1.5 text-sm text-white/60 transition hover:bg-white/10 hover:text-white"
        title="Quick search (Ctrl+K)"
      >
        <Search className="size-4" />
        <span className="hidden lg:inline">Search</span>
        <kbd className="hidden rounded bg-white/10 px-1.5 py-0.5 font-sans text-[10px] lg:inline">Ctrl K</kbd>
      </button>
      {open && (
        <div className="fixed inset-0 z-50 flex items-start justify-center bg-night/40 px-4 pt-[12vh] backdrop-blur-[2px]" onMouseDown={() => setOpen(false)}>
          <div className="w-full max-w-xl overflow-hidden rounded-2xl border border-line bg-white shadow-lift" onMouseDown={(event) => event.stopPropagation()}>
            <div className="flex items-center gap-2 border-b border-line px-4">
              <Search className="size-4 text-ink/40" />
              <input
                ref={inputRef}
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === "ArrowDown") {
                    event.preventDefault();
                    setActive((value) => Math.min(value + 1, hits.length - 1));
                  } else if (event.key === "ArrowUp") {
                    event.preventDefault();
                    setActive((value) => Math.max(value - 1, 0));
                  } else if (event.key === "Enter") {
                    event.preventDefault();
                    choose(hits[active]);
                  } else if (event.key === "Escape") {
                    setOpen(false);
                  }
                }}
                placeholder="Job code, title, candidate name, email, skill…"
                className="h-12 flex-1 bg-transparent text-sm text-ink outline-none placeholder:text-ink/40"
              />
              {loading && <span className="size-3 animate-spin rounded-full border-2 border-pine/30 border-t-pine" />}
            </div>
            <ul className="max-h-[50vh] overflow-y-auto py-1">
              {query.trim().length < 2 && <li className="px-4 py-6 text-center text-sm text-ink/45">Type two letters to search jobs, candidates, and submissions.</li>}
              {hits.map((hit, index) => {
                const Icon = ICONS[hit.group] || Search;
                const first = index === 0 || hits[index - 1].group !== hit.group;
                return (
                  <li key={hit.key}>
                    {first && <p className="px-4 pb-1 pt-2 text-[10px] font-semibold uppercase tracking-[0.14em] text-ink/40">{hit.group}</p>}
                    <button
                      type="button"
                      onMouseEnter={() => setActive(index)}
                      onClick={() => choose(hit)}
                      className={`flex w-full items-center gap-3 px-4 py-2 text-left ${index === active ? "bg-pine/10" : ""}`}
                    >
                      <Icon className={`size-4 shrink-0 ${hit.ask ? "text-pine" : "text-ink/40"}`} />
                      <span className="min-w-0 flex-1">
                        <span className="block truncate text-sm text-ink">{hit.title}</span>
                        {hit.detail && <span className="block truncate text-xs text-ink/50">{hit.detail}</span>}
                      </span>
                    </button>
                  </li>
                );
              })}
            </ul>
            <p className="border-t border-line px-4 py-2 text-[11px] text-ink/40">↑↓ to move · Enter to open · Esc to close · Ctrl+J opens the assistant</p>
          </div>
        </div>
      )}
    </>
  );
}
