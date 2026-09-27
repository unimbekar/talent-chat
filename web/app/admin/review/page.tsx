"use client";

import { Suspense, useEffect, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";

type JobOption = { requisition_code: string; title: string | null; status: string };
type CandidateOption = { id: string; full_name: string | null; original_filename: string | null };
type Review = {
  job: { requisition_code: string; title: string | null; location: string | null };
  candidate: { id: string; full_name: string | null; original_filename: string | null };
  mandatory_pct: number | null;
  mandatory_hit: number;
  mandatory_total: number;
  desired_pct: number | null;
  desired_hit: number;
  desired_total: number;
  meets_bar: boolean;
  title_missing: string[];
  mandatory_matched: string[];
  mandatory_missing: string[];
  desired_matched: string[];
  desired_missing: string[];
};

export default function ReviewRoute() {
  return (
    <Suspense fallback={<p className="text-sm">Loading the review screen…</p>}>
      <ReviewPage />
    </Suspense>
  );
}

function ReviewPage() {
  const router = useRouter();
  const params = useSearchParams();
  const [jobs, setJobs] = useState<JobOption[]>([]);
  const [candidates, setCandidates] = useState<CandidateOption[]>([]);
  const [review, setReview] = useState<Review | null>(null);
  const [error, setError] = useState("");
  const job = params.get("job") || "";
  const candidate = params.get("candidate") || "";

  useEffect(() => {
    fetch("/api/admin/jobs").then(async (response) => {
      if (response.status === 401) {
        router.push("/admin/login");
        return;
      }
      if (!response.ok) return;
      const data = await response.json();
      setJobs((data.jobs || []).filter((item: JobOption) => item.status !== "closed"));
    });
    fetch("/api/admin/resumes").then(async (response) => {
      if (response.status === 401) {
        router.push("/admin/login");
        return;
      }
      if (!response.ok) return;
      const data = await response.json();
      setCandidates(data.candidates || []);
    });
  }, [router]);

  useEffect(() => {
    if (!job || !candidate) {
      setReview(null);
      return;
    }
    const query = new URLSearchParams({ code: job, candidate_id: candidate });
    fetch(`/api/admin/review?${query}`).then(async (response) => {
      if (response.status === 401) {
        router.push("/admin/login");
        return;
      }
      if (!response.ok) {
        setError("That job and résumé could not be compared.");
        setReview(null);
        return;
      }
      setError("");
      setReview(await response.json());
    });
  }, [job, candidate, router]);

  function choose(nextJob: string, nextCandidate: string) {
    const query = new URLSearchParams();
    if (nextJob) query.set("job", nextJob);
    if (nextCandidate) query.set("candidate", nextCandidate);
    router.replace(query.size ? `/admin/review?${query}` : "/admin/review");
  }

  return (
    <div className="flex flex-col gap-5">
      <div>
        <h1 className="font-serif text-3xl">Review a match</h1>
        <p className="mt-1 text-sm text-ink/70">Compare one job with one résumé. The lists show which posting lines are covered and which are still missing.</p>
      </div>
      <div className="grid gap-3 sm:grid-cols-2">
        <label className="text-sm">
          Job
          <select
            aria-label="Job"
            value={job}
            onChange={(event) => choose(event.target.value, candidate)}
            className="mt-1 w-full rounded-md border border-line bg-card px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-pine"
          >
            <option value="">Choose a job</option>
            {jobs.map((item) => (
              <option key={item.requisition_code} value={item.requisition_code}>
                {item.requisition_code} · {item.title}
              </option>
            ))}
          </select>
        </label>
        <label className="text-sm">
          Résumé
          <select
            aria-label="Résumé"
            value={candidate}
            onChange={(event) => choose(job, event.target.value)}
            className="mt-1 w-full rounded-md border border-line bg-card px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-pine"
          >
            <option value="">Choose a résumé</option>
            {candidates.map((item) => (
              <option key={item.id} value={item.id}>
                {item.full_name || "Unnamed résumé"}
                {item.original_filename ? ` · ${item.original_filename}` : ""}
              </option>
            ))}
          </select>
        </label>
      </div>
      {error && <p className="text-sm text-red-700">{error}</p>}
      {job && candidate && !review && !error && <p className="text-sm">Comparing…</p>}
      {review && (
        <section className={`rounded-xl border bg-card p-4 ${review.meets_bar ? "border-pine" : "border-line"}`}>
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <Link href={`/admin/jobs/${review.job.requisition_code}`} className="font-mono text-sm text-pine hover:underline">
                {review.job.requisition_code}
              </Link>
              <h2 className="font-serif text-2xl">{review.job.title}</h2>
              <p className="text-sm text-ink/70">
                {review.candidate.full_name || "Unnamed résumé"}
                {review.candidate.original_filename ? ` · ${review.candidate.original_filename}` : ""}
              </p>
            </div>
            {review.meets_bar && <span className="rounded-full bg-pine/10 px-2.5 py-1 text-xs font-medium text-pine">Strong match</span>}
          </div>
          {review.title_missing.length > 0 && (
            <p className="mt-3 text-sm">The job title asks for {review.title_missing.join(", ")}, which is not on this résumé.</p>
          )}
          <div className="mt-4 grid gap-3 sm:grid-cols-2">
            <Score label="Mandatory" percent={review.mandatory_pct} hit={review.mandatory_hit} total={review.mandatory_total} strong={review.meets_bar} />
            <Score label="Desired" percent={review.desired_pct} hit={review.desired_hit} total={review.desired_total} strong={false} />
          </div>
          <div className="mt-4 grid gap-4 sm:grid-cols-2">
            <LineList title="Missing mandatory" lines={review.mandatory_missing} empty="No mandatory lines are missing." />
            <LineList title="Covered mandatory" lines={review.mandatory_matched} empty="No mandatory lines are covered." />
            <LineList title="Missing desired" lines={review.desired_missing} empty={review.desired_total === 0 ? "This posting has no desired skills." : "No desired lines are missing."} />
            <LineList title="Covered desired" lines={review.desired_matched} empty={review.desired_total === 0 ? "This posting has no desired skills." : "No desired lines are covered."} />
          </div>
        </section>
      )}
    </div>
  );
}

function Score({ label, percent, hit, total, strong }: { label: string; percent: number | null; hit: number; total: number; strong: boolean }) {
  return (
    <div className="flex min-h-24 flex-col justify-between rounded-lg bg-desk px-3 py-2">
      <p className="text-xs font-medium uppercase tracking-wide text-ink/50">{label}</p>
      <p className={`font-serif text-3xl leading-none ${strong ? "text-pine" : "text-ink"}`}>{percent == null ? "—" : `${Math.round(percent * 100)}%`}</p>
      <p className="text-xs text-ink/70">{total === 0 ? `No ${label.toLowerCase()} skills on file` : `${hit} of ${total} lines`}</p>
    </div>
  );
}

function LineList({ title, lines, empty }: { title: string; lines: string[]; empty: string }) {
  return (
    <div>
      <h3 className="text-sm font-medium">{title}</h3>
      {lines.length === 0 ? (
        <p className="mt-1 text-sm text-ink/60">{empty}</p>
      ) : (
        <ul className="mt-1 flex list-disc flex-col gap-1 pl-5 text-sm leading-6">
          {lines.map((line) => (
            <li key={line}>{line}</li>
          ))}
        </ul>
      )}
    </div>
  );
}
