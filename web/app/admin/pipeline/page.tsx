"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";

import { SubmissionForm } from "@/components/submission-form";
import { StageBadge } from "@/components/stage-badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { money, personName, when, type StageInfo, type SubmissionCard } from "@/lib/pipeline";

type Board = {
  stages: StageInfo[];
  active: number;
  total: number;
  submissions: SubmissionCard[];
};

export default function PipelinePage() {
  const router = useRouter();
  const [board, setBoard] = useState<Board | null>(null);
  const [stage, setStage] = useState("");
  const [scope, setScope] = useState<"active" | "closed" | "all">("active");
  const [query, setQuery] = useState("");
  const [composer, setComposer] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    const params = new URLSearchParams();
    if (stage) params.set("stage", stage);
    else params.set("scope", scope);
    if (query.trim()) params.set("q", query.trim());
    const handle = window.setTimeout(() => {
      fetch(`/api/admin/pipeline?${params}`).then(async (response) => {
        if (response.status === 401) {
          router.push("/admin/login");
          return;
        }
        if (!response.ok) {
          setError("The pipeline could not be loaded.");
          return;
        }
        setError("");
        setBoard(await response.json());
      });
    }, 180);
    return () => window.clearTimeout(handle);
  }, [stage, scope, query, router, composer]);

  function chooseStage(key: string) {
    setStage((current) => (current === key ? "" : key));
  }

  const rows = board?.submissions || [];

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="page-title">Pipeline</h1>
          <p className="page-lead">
            Every person sent for a job. Move them from submitted, through salary and interview, to selected. Ended submissions stay on the candidate’s history.
          </p>
        </div>
        <Button type="button" onClick={() => setComposer((value) => !value)}>
          {composer ? "Close" : "New submission"}
        </Button>
      </div>

      {composer && (
        <section className="panel p-4">
          <h2 className="font-serif text-xl">Submit a candidate</h2>
          <div className="mt-3">
            <SubmissionForm
              onCreated={() => {
                setComposer(false);
                setScope("active");
                setStage("");
              }}
            />
          </div>
        </section>
      )}

      <div className="-mx-4 flex snap-x gap-2 overflow-x-auto px-4 pb-1 [scrollbar-width:none] sm:mx-0 sm:grid sm:grid-cols-2 sm:overflow-visible sm:px-0 sm:pb-0 lg:grid-cols-4 xl:grid-cols-7">
        {(board?.stages || []).map((item) => {
          const selected = stage === item.key;
          return (
            <button
              key={item.key}
              type="button"
              onClick={() => chooseStage(item.key)}
              className={`min-w-[7.5rem] shrink-0 snap-start rounded-2xl border px-3 py-2.5 text-left transition active:scale-95 sm:min-w-0 sm:py-3 ${selected ? "border-pine bg-pine/10 shadow-card" : "border-line bg-card hover:border-pine/40"}`}
            >
              <span className="block text-xs uppercase tracking-wide text-ink/50">{item.label}</span>
              <span className="mt-1 block font-serif text-2xl">{item.count ?? 0}</span>
            </button>
          );
        })}
      </div>

      <div className="flex flex-wrap items-center gap-2">
        {(
          [
            ["active", "In progress"],
            ["closed", "Ended"],
            ["all", "All history"],
          ] as const
        ).map(([key, label]) => (
          <button
            key={key}
            type="button"
            onClick={() => {
              setScope(key);
              setStage("");
            }}
            className={`rounded-full px-3 py-1 text-sm ${!stage && scope === key ? "bg-night text-white" : "bg-card text-ink/70 ring-1 ring-line"}`}
          >
            {label}
          </button>
        ))}
        <span className="text-sm text-ink/55">
          {board ? `${board.active} in progress · ${board.total} ever submitted` : ""}
        </span>
      </div>

      <Input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search by name, email, job code, or title" aria-label="Search submissions" />
      {error && <p className="text-sm text-red-700">{error}</p>}

      <div className="overflow-hidden panel">
        {board && rows.length === 0 && (
          <p className="px-4 py-10 text-sm text-ink/65">
            {query ? "No submission matches that search." : "Nothing in this view. Submit someone from a job, or switch to All history."}
          </p>
        )}
        <ul className="divide-y divide-line">
          {rows.map((row) => (
            <li key={row.id}>
              <Link href={`/admin/submissions/${row.id}`} className="flex flex-wrap items-center justify-between gap-4 px-4 py-4 transition hover:bg-desk/70">
                <span className="min-w-0">
                  <span className="block truncate font-medium">{personName(row.candidate)}</span>
                  <span className="mt-0.5 block truncate text-sm text-ink/65">
                    <span className="font-mono text-pine">{row.job.requisition_code}</span> · {row.job.title || "Untitled job"} · {row.job.location || "No city"}
                  </span>
                  <span className="mt-1 block text-xs text-ink/50">
                    Updated {when(row.updated_at)}
                    {row.comment_count ? ` · ${row.comment_count} ${row.comment_count === 1 ? "comment" : "comments"}` : ""}
                  </span>
                </span>
                <span className="flex items-center gap-3">
                  <span className="text-sm text-ink/70">{money(row.salary_usd)}</span>
                  <StageBadge stage={row.stage} label={row.stage_label} />
                </span>
              </Link>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}
