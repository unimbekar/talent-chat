"use client";

import { Suspense, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";

import { BackButton } from "@/components/back-button";
import { copyText, shown } from "@/components/candidate-mail";
import { Button } from "@/components/ui/button";
import { Download } from "lucide-react";

import { downloadCsv, percent } from "@/lib/csv";
import { readCache, writeCache } from "@/lib/page-cache";

type JobOption = { requisition_code: string; title: string | null; status: string };
type CandidateOption = { id: string; full_name: string | null; original_filename: string | null; email: string | null; location: string | null };
type Review = {
  job: { requisition_code: string; title: string | null; location: string | null };
  candidate: CandidateOption;
  mandatory_pct: number | null;
  mandatory_hit: number;
  mandatory_total: number;
  desired_pct: number | null;
  desired_hit: number;
  desired_total: number;
  meets_bar: boolean;
  title_missing: string[];
  role_missing: string[];
  candidate_roles: string[];
  mandatory_matched: string[];
  mandatory_missing: string[];
  desired_matched: string[];
  desired_missing: string[];
};
type Outcome = { reviews: Review[]; failed: string[] };

const MAX_CANDIDATES = 25;
const PICKED_KEY = "talent-review-picked";

export default function ReviewRoute() {
  return (
    <Suspense fallback={<p className="text-sm">Loading the review screen…</p>}>
      <ReviewPage />
    </Suspense>
  );
}

function idsFromParams(params: URLSearchParams): string[] {
  const list = (params.get("candidates") || "").split(",");
  const single = params.get("candidate");
  if (single) list.push(single);
  return [...new Set(list.map((id) => id.trim()).filter(Boolean))];
}

function rank(reviews: Review[]): Review[] {
  return [...reviews].sort(
    (a, b) =>
      Number(b.meets_bar) - Number(a.meets_bar) ||
      (b.mandatory_pct ?? -1) - (a.mandatory_pct ?? -1) ||
      (b.desired_pct ?? -1) - (a.desired_pct ?? -1),
  );
}

function ReviewPage() {
  const router = useRouter();
  const params = useSearchParams();
  const job = params.get("job") || "";
  const reviewedIds = useMemo(() => idsFromParams(params), [params]);
  const reviewedKey = reviewedIds.join(",");

  const [jobs, setJobs] = useState<JobOption[]>([]);
  const [draftJob, setDraftJob] = useState(job);
  const [picked, setPicked] = useState<CandidateOption[]>([]);
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState(false);
  const [hits, setHits] = useState<CandidateOption[]>([]);
  const [outcome, setOutcome] = useState<Outcome | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const [copied, setCopied] = useState(false);
  const [runCount, setRunCount] = useState(0);

  useEffect(() => setDraftJob(job), [job]);

  useEffect(() => {
    const saved = readCache<CandidateOption[]>(PICKED_KEY) || [];
    const byId = new Map(saved.map((item) => [item.id, item]));
    setPicked(reviewedIds.length ? reviewedIds.map((id) => byId.get(id) || { id, full_name: null, original_filename: null, email: null, location: null }) : saved);
  }, [reviewedKey]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    writeCache(PICKED_KEY, picked);
  }, [picked]);

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
  }, [router]);

  useEffect(() => {
    if (!query.trim()) {
      setHits([]);
      return;
    }
    const handle = window.setTimeout(() => {
      const search = new URLSearchParams({ q: query, page_size: "10" });
      fetch(`/api/admin/resumes?${search}`).then(async (response) => {
        if (response.status === 401) {
          router.push("/admin/login");
          return;
        }
        if (!response.ok) return;
        const data = await response.json();
        setHits(data.candidates || []);
      });
    }, 200);
    return () => window.clearTimeout(handle);
  }, [query, router]);

  useEffect(() => {
    if (!job || reviewedIds.length === 0) {
      setOutcome(null);
      return;
    }
    const cacheKey = `talent-review:${job}:${reviewedKey}`;
    const saved = readCache<Outcome>(cacheKey);
    setOutcome(saved);
    setLoading(true);
    setError("");
    let cancelled = false;
    Promise.all(
      reviewedIds.map(async (id) => {
        const response = await fetch(`/api/admin/review?${new URLSearchParams({ code: job, candidate_id: id })}`);
        if (response.status === 401) throw new Error("login");
        return response.ok ? ((await response.json()) as Review) : id;
      }),
    )
      .then((results) => {
        if (cancelled) return;
        const next: Outcome = {
          reviews: results.filter((item): item is Review => typeof item !== "string"),
          failed: results.filter((item): item is string => typeof item === "string"),
        };
        setOutcome(next);
        writeCache(cacheKey, next);
        setPicked((current) => current.map((item) => next.reviews.find((review) => review.candidate.id === item.id)?.candidate || item));
        setExpanded(next.reviews.length === 1 ? new Set([next.reviews[0].candidate.id]) : new Set());
      })
      .catch((reason) => {
        if (cancelled) return;
        if (reason instanceof Error && reason.message === "login") router.push("/admin/login");
        else setError("The comparison did not finish. Try Review again.");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [job, reviewedKey, runCount, router]); // eslint-disable-line react-hooks/exhaustive-deps

  function toggle(item: CandidateOption) {
    setPicked((current) =>
      current.some((entry) => entry.id === item.id) ? current.filter((entry) => entry.id !== item.id) : [...current, item].slice(0, MAX_CANDIDATES),
    );
  }

  function runReview() {
    if (!draftJob || picked.length === 0) return;
    const nextKey = picked.map((item) => item.id).join(",");
    setCopied(false);
    if (draftJob === job && nextKey === reviewedKey) {
      setRunCount((count) => count + 1);
      return;
    }
    router.push(`/admin/review?${new URLSearchParams({ job: draftJob, candidates: nextKey })}`);
  }

  const pickedIds = new Set(picked.map((item) => item.id));
  const ranked = rank(outcome?.reviews || []);
  const strongCount = ranked.filter((review) => review.meets_bar).length;
  const jobInfo = ranked[0]?.job;
  const emails = [...new Set(ranked.map((review) => (review.candidate.email || "").trim().toLowerCase()).filter((email) => email.includes("@")))];
  const dirty = draftJob !== job || picked.map((item) => item.id).join(",") !== reviewedKey;

  return (
    <div className="flex flex-col gap-5">
      <div>
        <BackButton fallback="/admin/jobs" />
        <h1 className="page-title mt-2">Review a match</h1>
        <p className="page-lead">
          Pick a job and one or more résumés, then press Review. With several résumés the list is ranked by mandatory coverage, and each row opens to show
          the covered and missing posting lines.
        </p>
      </div>

      <div className="grid gap-3 sm:grid-cols-2">
        <label className="text-sm">
          Job
          <select
            aria-label="Job"
            value={draftJob}
            onChange={(event) => setDraftJob(event.target.value)}
            className="mt-1 field"
          >
            <option value="">Choose a job</option>
            {jobs.map((item) => (
              <option key={item.requisition_code} value={item.requisition_code}>
                {item.requisition_code} · {item.title}
              </option>
            ))}
          </select>
        </label>
        <div className="relative text-sm">
          Résumés
          <input
            aria-label="Résumés"
            value={query}
            onChange={(event) => {
              setQuery(event.target.value);
              setOpen(true);
            }}
            onFocus={() => setOpen(true)}
            onKeyDown={(event) => {
              if (event.key === "Escape") setOpen(false);
            }}
            placeholder="Type a few letters of a name, then tick résumés"
            className="mt-1 field"
          />
          {open && query.trim() && (
            <div className="absolute z-10 mt-1 w-full rounded-md border border-line bg-card shadow-lg">
              {hits.length === 0 ? (
                <p className="px-3 py-2 text-ink/60">No résumé matches “{query}”.</p>
              ) : (
                <>
                  <div className="flex items-center justify-between gap-2 border-b border-line px-3 py-2">
                    <button
                      type="button"
                      className="text-xs text-pine hover:underline"
                      onClick={() =>
                        setPicked((current) => {
                          const missing = hits.filter((item) => !current.some((entry) => entry.id === item.id));
                          return [...current, ...missing].slice(0, MAX_CANDIDATES);
                        })
                      }
                    >
                      Tick all {hits.length} shown
                    </button>
                    <button type="button" className="text-xs font-medium text-pine hover:underline" onClick={() => setOpen(false)}>
                      Done
                    </button>
                  </div>
                  <ul className="max-h-72 overflow-y-auto">
                    {hits.map((item) => (
                      <li key={item.id} className="border-t border-line first:border-0">
                        <label className="flex cursor-pointer items-start gap-2 px-3 py-2 hover:bg-desk">
                          <input type="checkbox" className="mt-1" checked={pickedIds.has(item.id)} onChange={() => toggle(item)} />
                          <span className="min-w-0 flex-1">
                            <span className="block">{item.full_name || item.original_filename || "Unnamed résumé"}</span>
                            <span className="block text-xs text-ink/70">
                              {shown(item.email)} · {shown(item.location)}
                            </span>
                          </span>
                        </label>
                      </li>
                    ))}
                  </ul>
                </>
              )}
            </div>
          )}
        </div>
      </div>

      <div className="flex flex-col gap-3 panel p-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex min-w-0 flex-wrap items-center gap-1.5">
          {picked.length === 0 ? (
            <span className="text-sm text-ink/60">No résumés picked yet.</span>
          ) : (
            <>
              <span className="mr-1 text-xs text-ink/60">
                {picked.length} picked{picked.length >= MAX_CANDIDATES ? ` (limit ${MAX_CANDIDATES})` : ""}:
              </span>
              {picked.map((item) => (
                <span key={item.id} className="inline-flex items-center gap-1 rounded-full border border-line bg-desk py-0.5 pl-2.5 pr-1 text-xs">
                  {item.full_name || item.original_filename || "Loading…"}
                  <button
                    type="button"
                    aria-label={`Remove ${item.full_name || "résumé"}`}
                    className="rounded-full px-1 text-ink/50 hover:bg-line hover:text-ink"
                    onClick={() => toggle(item)}
                  >
                    ×
                  </button>
                </span>
              ))}
              <button type="button" className="ml-1 text-xs text-pine hover:underline" onClick={() => setPicked([])}>
                Clear
              </button>
            </>
          )}
        </div>
        <Button type="button" onClick={runReview} disabled={!draftJob || picked.length === 0 || loading} className="shrink-0">
          {loading ? "Reviewing…" : picked.length > 1 ? `Review ${picked.length} résumés` : "Review"}
        </Button>
      </div>
      {!draftJob && picked.length > 0 && <p className="-mt-3 text-xs text-ink/60">Choose a job to enable Review.</p>}
      {dirty && outcome && <p className="-mt-3 text-xs text-ink/60">The selection changed. Press Review to update the results below.</p>}

      {error && <p className="text-sm text-red-700">{error}</p>}
      {loading && !outcome && <p className="text-sm">Comparing…</p>}
      {(outcome?.failed.length || 0) > 0 && (
        <p className="text-sm text-red-700">
          {outcome?.failed.length} {outcome?.failed.length === 1 ? "résumé" : "résumés"} could not be compared with this job.
        </p>
      )}

      {ranked.length > 0 && jobInfo && (
        <section className="flex flex-col gap-3">
          <div className="flex flex-wrap items-end justify-between gap-3">
            <div>
              <Link href={`/admin/jobs/${jobInfo.requisition_code}`} className="font-mono text-sm text-pine hover:underline">
                {jobInfo.requisition_code}
              </Link>
              <h2 className="font-serif text-2xl">{jobInfo.title}</h2>
              {ranked.length > 1 && (
                <p className="text-sm text-ink/70">
                  {ranked.length} résumés compared · {strongCount} strong {strongCount === 1 ? "match" : "matches"}
                </p>
              )}
            </div>
            {ranked.length > 0 && (
              <div className="flex flex-wrap gap-2">
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={() =>
                    downloadCsv(
                      `review-${jobInfo.requisition_code}.csv`,
                      ["Rank", "Name", "Email", "Location", "Mandatory", "Desired", "Strong match", "Missing mandatory"],
                      ranked.map((review, index) => [
                        index + 1,
                        review.candidate.full_name,
                        review.candidate.email,
                        review.candidate.location,
                        percent(review.mandatory_pct),
                        percent(review.desired_pct),
                        review.meets_bar ? "yes" : "no",
                        review.mandatory_missing.join("; "),
                      ]),
                    )
                  }
                >
                  <Download /> Export CSV
                </Button>
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={() => setExpanded(expanded.size === ranked.length ? new Set() : new Set(ranked.map((review) => review.candidate.id)))}
                >
                  {expanded.size === ranked.length ? "Collapse all" : "Expand all"}
                </Button>
                {emails.length > 0 && (
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    onClick={() => {
                      copyText(emails.join(", "));
                      setCopied(true);
                    }}
                  >
                    {copied ? "Copied" : `Copy ${emails.length} emails`}
                  </Button>
                )}
              </div>
            )}
          </div>
          {ranked.map((review, index) => (
            <ReviewRow
              key={review.candidate.id}
              review={review}
              position={ranked.length > 1 ? index + 1 : null}
              open={expanded.has(review.candidate.id)}
              onToggle={() =>
                setExpanded((current) => {
                  const next = new Set(current);
                  if (next.has(review.candidate.id)) next.delete(review.candidate.id);
                  else next.add(review.candidate.id);
                  return next;
                })
              }
            />
          ))}
        </section>
      )}
    </div>
  );
}

function ReviewRow({ review, position, open, onToggle }: { review: Review; position: number | null; open: boolean; onToggle: () => void }) {
  const name = review.candidate.full_name || "Unnamed résumé";
  return (
    <article className={`rounded-xl border bg-card ${review.meets_bar ? "border-pine" : "border-line"}`}>
      <div className="flex flex-col gap-3 p-4 sm:flex-row sm:items-center">
        {position != null && <span className="w-6 shrink-0 font-mono text-sm text-ink/50">{position}</span>}
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <Link href={`/admin/match?id=${review.candidate.id}`} className="truncate font-medium hover:text-pine">
              {name}
            </Link>
            {review.meets_bar && <span className="rounded-full bg-pine/10 px-2 py-0.5 text-xs font-medium text-pine">Strong match</span>}
          </div>
          <p className="truncate text-xs text-ink/70">
            {shown(review.candidate.email)} · {shown(review.candidate.location)}
            {review.candidate.original_filename ? ` · ${review.candidate.original_filename}` : ""}
          </p>
        </div>
        <div className="flex shrink-0 items-center gap-2">
          <ScorePill label="Mandatory" percent={review.mandatory_pct} hit={review.mandatory_hit} total={review.mandatory_total} strong={review.meets_bar} />
          <ScorePill label="Desired" percent={review.desired_pct} hit={review.desired_hit} total={review.desired_total} strong={false} />
          <Button type="button" variant="ghost" size="sm" onClick={onToggle} aria-expanded={open}>
            {open ? "Hide details" : "Details"}
          </Button>
        </div>
      </div>
      {open && (
        <div className="border-t border-line p-4">
          {review.title_missing.length > 0 && <p className="text-sm">The job title asks for {review.title_missing.join(", ")}, which is not on this résumé.</p>}
          {(review.role_missing || []).length > 0 && (
            <p className="mt-2 text-sm">
              This résumé is {(review.candidate_roles || []).join(" and ") || "a different kind of role"}. The job is {review.role_missing.join(" and ")}, so
              shared wording is not counted as a match.
            </p>
          )}
          <div className="mt-3 grid gap-4 sm:grid-cols-2">
            <LineList title="Missing mandatory" lines={review.mandatory_missing} empty="No mandatory lines are missing." />
            <LineList title="Covered mandatory" lines={review.mandatory_matched} empty="No mandatory lines are covered." />
            <LineList
              title="Missing desired"
              lines={review.desired_missing}
              empty={review.desired_total === 0 ? "This posting has no desired skills." : "No desired lines are missing."}
            />
            <LineList
              title="Covered desired"
              lines={review.desired_matched}
              empty={review.desired_total === 0 ? "This posting has no desired skills." : "No desired lines are covered."}
            />
          </div>
        </div>
      )}
    </article>
  );
}

function ScorePill({ label, percent, hit, total, strong }: { label: string; percent: number | null; hit: number; total: number; strong: boolean }) {
  return (
    <div className="w-28 rounded-lg bg-desk px-3 py-1.5" title={total === 0 ? `No ${label.toLowerCase()} skills on file` : `${hit} of ${total} lines`}>
      <p className="text-[10px] font-medium uppercase tracking-wide text-ink/50">{label}</p>
      <p className={`font-serif text-xl leading-tight ${strong ? "text-pine" : "text-ink"}`}>{percent == null ? "—" : `${Math.round(percent * 100)}%`}</p>
      <p className="text-[10px] text-ink/60">{total === 0 ? "none on file" : `${hit} of ${total} lines`}</p>
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
