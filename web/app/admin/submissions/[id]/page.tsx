"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";

import { BackButton } from "@/components/back-button";
import { CommentThread } from "@/components/comment-thread";
import { StageBadge } from "@/components/stage-badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  errorMessage,
  eventSentence,
  money,
  parseSalary,
  personName,
  whenExact,
  type StageInfo,
  type SubmissionDetail,
} from "@/lib/pipeline";

export default function SubmissionPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const id = params.id;
  const [row, setRow] = useState<SubmissionDetail | null>(null);
  const [stages, setStages] = useState<StageInfo[]>([]);
  const [salary, setSalary] = useState("");
  const [salaryNote, setSalaryNote] = useState("");
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState<"stage" | "salary" | "delete" | null>(null);
  const [error, setError] = useState("");
  const [confirmDelete, setConfirmDelete] = useState(false);

  const load = useCallback(() => {
    fetch(`/api/admin/submissions/${id}`).then(async (response) => {
      if (response.status === 401) {
        router.push("/admin/login");
        return;
      }
      if (!response.ok) {
        setError("That submission is not on file.");
        return;
      }
      const data = (await response.json()) as SubmissionDetail;
      setRow(data);
      setSalary(data.salary_usd ? String(data.salary_usd) : "");
      setSalaryNote(data.salary_note || "");
      setError("");
    });
    fetch("/api/admin/pipeline/stages").then(async (response) => {
      if (response.ok) {
        const data = await response.json();
        setStages(data.stages || []);
      }
    });
  }, [id, router]);

  useEffect(() => {
    load();
  }, [load]);

  async function move(stage: string) {
    if (!row || busy || stage === row.stage) return;
    setBusy("stage");
    setError("");
    try {
      const response = await fetch(`/api/admin/submissions/${id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ stage, note: reason.trim() || null }),
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) {
        setError(errorMessage(data, "The stage was not changed."));
        return;
      }
      setRow(data);
      setReason("");
    } catch {
      setError("The stage was not changed.");
    } finally {
      setBusy(null);
    }
  }

  async function saveSalary(event: FormEvent) {
    event.preventDefault();
    if (!row || busy) return;
    const amount = parseSalary(salary);
    if (amount === "invalid") {
      setError("Enter a yearly salary in dollars, or clear the field.");
      return;
    }
    const nextNote = salaryNote.trim() || null;
    if (amount === row.salary_usd && nextNote === (row.salary_note || null) && !reason.trim()) {
      setError("That salary is already on file.");
      return;
    }
    setBusy("salary");
    setError("");
    try {
      const response = await fetch(`/api/admin/submissions/${id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          salary_usd: amount,
          salary_note: salaryNote.trim() || null,
          note: reason.trim() || null,
        }),
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) {
        setError(errorMessage(data, "The salary was not saved."));
        return;
      }
      setRow(data);
      setReason("");
    } catch {
      setError("The salary was not saved.");
    } finally {
      setBusy(null);
    }
  }

  async function comment(method: string, path: string, body?: string) {
    const response = await fetch(path, {
      method,
      headers: body ? { "Content-Type": "application/json" } : undefined,
      body: body ? JSON.stringify({ body }) : undefined,
    });
    const data = await response.json().catch(() => ({}));
    if (response.status === 401) {
      router.push("/admin/login");
      throw new Error("Sign in required.");
    }
    if (!response.ok) throw new Error(errorMessage(data, "The comment was not saved."));
    load();
  }

  async function remove() {
    setBusy("delete");
    const response = await fetch(`/api/admin/submissions/${id}`, { method: "DELETE" });
    if (response.ok) {
      router.push("/admin/pipeline");
      return;
    }
    setBusy(null);
    setError("The submission was not removed.");
  }

  if (error && !row) return <p className="text-sm text-red-700">{error}</p>;
  if (!row) return <p className="text-sm">Loading submission…</p>;

  const byKey = Object.fromEntries(stages.map((stage) => [stage.key, stage]));
  const flow = row.flow.map((key) => byKey[key]).filter(Boolean);
  const exits = row.exits.map((key) => byKey[key]).filter(Boolean);

  return (
    <div className="flex flex-col gap-6">
      <div>
        <div className="flex items-center gap-4">
          <BackButton fallback="/admin/pipeline" />
          <Link href="/admin/pipeline" className="text-sm text-pine underline">
            Pipeline
          </Link>
        </div>
        <div className="mt-3 flex flex-wrap items-start justify-between gap-3">
          <div>
            <p className="text-sm text-ink/60">
              <Link href={`/admin/candidates/${row.candidate.id}`} className="text-pine underline">
                {personName(row.candidate)}
              </Link>
              {" · "}
              <Link href={`/admin/jobs/${row.job.requisition_code}#submissions`} className="text-pine underline">
                <span className="font-mono">{row.job.requisition_code}</span> {row.job.title}
              </Link>
            </p>
            <h1 className="page-title mt-1">{personName(row.candidate)}</h1>
            <p className="text-sm text-ink/65">
              {row.job.location || "No city"} · submitted {whenExact(row.created_at)}
            </p>
          </div>
          <StageBadge stage={row.stage} label={row.stage_label} />
        </div>
      </div>

      <section className="panel p-4">
        <h2 className="font-serif text-xl">Stage</h2>
        <p className="page-lead">{byKey[row.stage]?.detail || "Choose the stage this submission is in now."}</p>
        <ol className="mt-4 grid gap-2 sm:grid-cols-5">
          {flow.map((stage, index) => {
            const current = stage.key === row.stage;
            return (
              <li key={stage.key}>
                <button
                  type="button"
                  disabled={busy === "stage" || current}
                  onClick={() => move(stage.key)}
                  className={`flex h-full w-full flex-col rounded-xl border px-3 py-3 text-left transition ${current ? "border-pine bg-pine/10" : "border-line hover:border-pine/40"}`}
                >
                  <span className="text-[11px] uppercase tracking-wide text-ink/45">Step {index + 1}</span>
                  <span className="mt-1 text-sm font-medium">{stage.label}</span>
                </button>
              </li>
            );
          })}
        </ol>
        <div className="mt-3 flex flex-wrap gap-2">
          {exits.map((stage) => (
            <Button key={stage.key} type="button" variant={stage.key === "rejected" ? "danger" : "outline"} size="sm" disabled={busy === "stage" || row.stage === stage.key} onClick={() => move(stage.key)}>
              {stage.label}
            </Button>
          ))}
        </div>
        <label className="mt-4 block text-sm">
          Why this change? Saved on the history.
          <textarea value={reason} onChange={(event) => setReason(event.target.value)} rows={2} className="field mt-1" placeholder="Client asked for a Thursday panel" />
        </label>
        {error && <p className="mt-2 text-sm text-red-700">{error}</p>}
      </section>

      <form onSubmit={saveSalary} className="panel p-4">
        <h2 className="font-serif text-xl">Salary for this job</h2>
        <p className="page-lead">Yearly dollars for {row.job.requisition_code}. It stays with this submission, not with the person’s other jobs.</p>
        <div className="mt-3 grid gap-3 sm:grid-cols-2">
          <label className="text-sm">
            Yearly salary
            <Input value={salary} onChange={(event) => setSalary(event.target.value)} placeholder="165000" className="mt-1" inputMode="numeric" />
          </label>
          <label className="text-sm">
            Note
            <Input value={salaryNote} onChange={(event) => setSalaryNote(event.target.value)} placeholder="W2, negotiable to 180" className="mt-1" />
          </label>
        </div>
        <p className="mt-2 text-sm text-ink/60">On file: {money(row.salary_usd)}{row.salary_note ? ` · ${row.salary_note}` : ""}</p>
        <Button type="submit" className="mt-3" disabled={busy === "salary" || busy === "stage"}>
          {busy === "salary" ? "Saving…" : "Save salary"}
        </Button>
      </form>

      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_20rem]">
        <CommentThread
          comments={row.comments}
          heading="Comments"
          hint="Notes about this submission. Editing a comment does not rewrite the stage history."
          empty="No comments on this submission yet."
          onCreate={(body) => comment("POST", `/api/admin/submissions/${id}/comments`, body)}
          onEdit={(commentId, body) => comment("PATCH", `/api/admin/submissions/${id}/comments/${commentId}`, body)}
          onDelete={(commentId) => comment("DELETE", `/api/admin/submissions/${id}/comments/${commentId}`)}
        />
        <section className="panel p-4">
          <h2 className="font-serif text-xl">History</h2>
          <ol className="mt-3 flex flex-col gap-3">
            {[...row.events].reverse().map((event) => (
              <li key={event.id} className="border-l-2 border-pine/30 pl-3">
                <p className="text-sm">{eventSentence(event)}</p>
                {event.body && <p className="mt-1 text-sm text-ink/70">{event.body}</p>}
                <p className="mt-1 text-xs text-ink/45">{whenExact(event.at)}</p>
              </li>
            ))}
          </ol>
        </section>
      </div>

      <section className="rounded-2xl border border-red-200 bg-red-50/40 p-4">
        <h2 className="font-serif text-lg text-red-900">Remove this record</h2>
        <p className="mt-1 max-w-2xl text-sm text-red-900/80">
          Withdraw keeps the history. Delete is for a submission that should never have been created. The stage history and comments go with it.
        </p>
        {confirmDelete ? (
          <div className="mt-3 flex gap-2">
            <Button type="button" variant="danger" disabled={busy === "delete"} onClick={remove}>
              Delete permanently
            </Button>
            <Button type="button" variant="outline" onClick={() => setConfirmDelete(false)}>
              Cancel
            </Button>
          </div>
        ) : (
          <Button type="button" variant="danger" className="mt-3" onClick={() => setConfirmDelete(true)}>
            Delete submission
          </Button>
        )}
      </section>
    </div>
  );
}
