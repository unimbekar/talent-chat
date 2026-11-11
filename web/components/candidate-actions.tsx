"use client";

import { FormEvent, useState } from "react";
import Link from "next/link";

import { resumeUpdateHref, reviewHref } from "@/lib/pipeline";

export function CandidateActions({ id, job }: { id: string; job?: string }) {
  const [phase, setPhase] = useState<"ready" | "busy" | "sent" | "ask">("ready");
  const [submissionId, setSubmissionId] = useState("");
  const [code, setCode] = useState(job || "");
  const [error, setError] = useState("");

  async function submit(requisition: string) {
    const target = requisition.trim();
    if (!target) {
      setPhase("ask");
      return;
    }
    setPhase("busy");
    setError("");
    const response = await fetch("/api/admin/submissions", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ candidate_id: id, requisition_code: target }),
    });
    const body = await response.json().catch(() => ({}));
    if (response.ok && body.id) {
      setSubmissionId(String(body.id));
      setPhase("sent");
      return;
    }
    const detail = body.detail;
    const existing = detail && typeof detail === "object" ? detail.submission_id : "";
    if (response.status === 409 && existing) {
      setSubmissionId(String(existing));
      setPhase("sent");
      return;
    }
    setError(typeof detail === "string" ? detail : detail?.message || "The submission was not created.");
    setPhase("ready");
  }

  function onAsk(event: FormEvent) {
    event.preventDefault();
    void submit(code);
  }

  return (
    <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px]">
      <Link href={reviewHref(job, id)} className="font-medium text-pine hover:underline">
        Review
      </Link>
      {job ? (
        <Link href={resumeUpdateHref(job, id)} className="font-medium text-pine hover:underline">
          Update résumé
        </Link>
      ) : null}
      {phase === "sent" && submissionId ? (
        <Link href={`/admin/submissions/${submissionId}`} className="font-medium text-pine hover:underline">
          Open submission
        </Link>
      ) : (
        <button
          type="button"
          className="font-medium text-pine hover:underline disabled:opacity-50"
          disabled={phase === "busy"}
          onClick={() => void submit(job || code)}
        >
          {phase === "busy" ? "Submitting…" : "Submit"}
        </button>
      )}
      {!job && phase === "ask" && (
        <form className="flex items-center gap-1" onSubmit={onAsk}>
          <input
            className="field h-7 w-24 px-2 text-[11px]"
            value={code}
            onChange={(event) => setCode(event.target.value)}
            placeholder="Job code"
            aria-label="Job code"
          />
        </form>
      )}
      {error ? <span className="text-red-700">{error}</span> : null}
    </div>
  );
}
