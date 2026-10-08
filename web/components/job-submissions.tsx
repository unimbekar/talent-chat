"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";

import { SubmissionForm } from "@/components/submission-form";
import { StageBadge } from "@/components/stage-badge";
import { money, personName, when, type SubmissionCard } from "@/lib/pipeline";

export type SubmissionIndex = Record<string, { id: string; label: string }>;

export function JobSubmissions({
  code,
  reload,
  onIndex,
}: {
  code: string;
  reload: number;
  onIndex: (index: SubmissionIndex) => void;
}) {
  const [rows, setRows] = useState<SubmissionCard[]>([]);
  const [loaded, setLoaded] = useState(false);
  const [open, setOpen] = useState(false);
  const [error, setError] = useState("");
  const onIndexRef = useRef(onIndex);
  onIndexRef.current = onIndex;

  const load = useCallback(() => {
    fetch(`/api/admin/jobs/${encodeURIComponent(code)}/submissions`).then(async (response) => {
      if (!response.ok) {
        setError("Submissions for this job could not be loaded.");
        setLoaded(true);
        return;
      }
      const data = await response.json();
      const submissions = (data.submissions || []) as SubmissionCard[];
      setRows(submissions);
      setLoaded(true);
      setError("");
      const index: SubmissionIndex = {};
      for (const row of submissions) index[row.candidate.id] = { id: row.id, label: row.stage_label };
      onIndexRef.current(index);
    });
  }, [code]);

  useEffect(() => {
    setLoaded(false);
    load();
  }, [load, reload]);

  const active = rows.filter((row) => row.stage !== "rejected" && row.stage !== "withdrawn").length;

  return (
    <section id="submissions" className="scroll-mt-6 panel p-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h2 className="font-serif text-xl">Submissions</h2>
          <p className="page-lead">
            {!loaded
              ? "Loading the people sent for this job."
              : rows.length === 0
                ? "No one has been submitted for this job yet."
                : `${rows.length} submitted · ${active} still in progress. Rejected and withdrawn stay in the history.`}
          </p>
        </div>
        <button type="button" className="text-sm text-pine underline" onClick={() => setOpen((value) => !value)}>
          {open ? "Hide form" : "Submit a candidate"}
        </button>
      </div>
      {error && <p className="mt-3 text-sm text-red-700">{error}</p>}
      {open && (
        <div className="mt-4 rounded-xl border border-line bg-desk/50 p-4">
          <SubmissionForm
            jobCode={code}
            onCreated={() => {
              setOpen(false);
              load();
            }}
          />
        </div>
      )}
      <ul className="mt-4 flex flex-col gap-2">
        {rows.map((row) => (
          <li key={row.id}>
            <Link href={`/admin/submissions/${row.id}`} className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-line px-3 py-3 transition hover:border-pine/40 hover:bg-desk/40">
              <span>
                <span className="block text-sm font-medium">{personName(row.candidate)}</span>
                <span className="block text-xs text-ink/60">
                  {row.candidate.email || "No email"} · {row.candidate.location || "No location"} · {when(row.updated_at)}
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
    </section>
  );
}
