"use client";

import { FormEvent, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";

import { JobSubmissions, type SubmissionIndex } from "@/components/job-submissions";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { BackButton } from "@/components/back-button";
import { CandidateMailBar, copyText, selectedEmails, shown } from "@/components/candidate-mail";
import { Download } from "lucide-react";

import { downloadCsv, percent } from "@/lib/csv";
import { readCache, writeCache } from "@/lib/page-cache";
import { resumeFileUrl } from "@/lib/pipeline";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";

type JobCandidate = {
  id: string;
  full_name: string | null;
  original_filename: string | null;
  has_file?: boolean;
  email: string | null;
  location: string | null;
  mandatory_pct: number | null;
  mandatory_hit: number;
  mandatory_total: number;
  desired_pct: number | null;
  desired_hit: number;
  desired_total: number;
  meets_bar: boolean;
};

type JobDetail = {
  requisition_code: string;
  title: string | null;
  location: string | null;
  status: string;
  close_note: string | null;
  description_source: string;
  description_text: string | null;
  description_note: string | null;
  needs_review: boolean;
  must_have_skills: string[];
  nice_to_have_skills: string[];
  must_have_quotes: string[];
  nice_to_have_quotes: string[];
  clearance_required: string | null;
  polygraph_required: string | null;
  source_url: string | null;
};

export default function JobDetailPage() {
  const params = useParams<{ code: string }>();
  const router = useRouter();
  const code = decodeURIComponent(params.code);
  const [job, setJob] = useState<JobDetail | null>(null);
  const [location, setLocation] = useState("");
  const [clearance, setClearance] = useState("");
  const [must, setMust] = useState<string[]>([]);
  const [desired, setDesired] = useState<string[]>([]);
  const [replacement, setReplacement] = useState("");
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [candidates, setCandidates] = useState<JobCandidate[]>([]);
  const [candidatesLoaded, setCandidatesLoaded] = useState(false);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [copiedSel, setCopiedSel] = useState(false);
  const [copyNote, setCopyNote] = useState("");
  const [closeNote, setCloseNote] = useState("");
  const [closing, setClosing] = useState(false);
  const [submitted, setSubmitted] = useState<SubmissionIndex>({});
  const [submissionReload, setSubmissionReload] = useState(0);
  const [submittingId, setSubmittingId] = useState<string | null>(null);

  useEffect(() => {
    function showJob(data: JobDetail) {
      setJob(data);
      setLocation(data.location || "");
      setClearance(data.clearance_required || "");
      setMust(postedSkills(data.must_have_quotes, data.must_have_skills));
      setDesired(postedSkills(data.nice_to_have_quotes, data.nice_to_have_skills));
      setReplacement(adminDescription(data));
    }
    const savedJob = readCache<JobDetail>(`talent-job:${code}`);
    if (savedJob) showJob(savedJob);
    const savedCandidates = readCache<JobCandidate[]>(`talent-job-candidates:${code}`);
    if (savedCandidates) {
      setCandidates(savedCandidates);
      setCandidatesLoaded(true);
    }
    fetch(`/api/admin/jobs/${code}`).then(async (response) => {
      if (response.status === 401) {
        router.push("/admin/login");
        return;
      }
      if (!response.ok) {
        setError("Job not found.");
        return;
      }
      showJob((await response.json()) as JobDetail);
    });
    fetch(`/api/admin/jobs/${code}/candidates`).then(async (response) => {
      if (!response.ok) return;
      const data = await response.json();
      setCandidates(data.candidates || []);
      setCandidatesLoaded(true);
      writeCache(`talent-job-candidates:${code}`, data.candidates || []);
    });
  }, [code, router]);

  useEffect(() => {
    if (job) writeCache(`talent-job:${code}`, job);
  }, [job, code]);

  function toggle(id: string) {
    setCopiedSel(false);
    setSelected((current) => {
      const next = new Set(current);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  function toggleAll() {
    setCopiedSel(false);
    setSelected(candidates.every((candidate) => selected.has(candidate.id)) ? new Set() : new Set(candidates.map((candidate) => candidate.id)));
  }

  function copySelected() {
    const list = selectedEmails(candidates, selected);
    const missing = candidates.filter((candidate) => selected.has(candidate.id) && !(candidate.email || "").includes("@")).length;
    setCopyNote(missing ? `${missing} selected ${missing === 1 ? "résumé has" : "résumés have"} no email, so ${missing === 1 ? "it was" : "they were"} left out.` : "");
    if (!list) return;
    copyText(list);
    setCopiedSel(true);
  }

  async function reopenJob() {
    setClosing(true);
    setMessage("");
    try {
      const response = await fetch(`/api/admin/jobs/${code}/reopen`, { method: "POST" });
      const data = await response.json().catch(() => ({}));
      if (response.status === 401) {
        router.push("/admin/login");
        return;
      }
      if (!response.ok) {
        setMessage(data.detail || "The job was not reopened.");
        return;
      }
      setJob(data);
      setMessage("Open again.");
    } catch {
      setMessage("The job was not reopened.");
    } finally {
      setClosing(false);
    }
  }

  async function closeJob(event: FormEvent) {
    event.preventDefault();
    setClosing(true);
    setMessage("");
    try {
      const response = await fetch(`/api/admin/jobs/${code}/close`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ note: closeNote }),
      });
      const data = await response.json().catch(() => ({}));
      if (response.status === 401) {
        router.push("/admin/login");
        return;
      }
      if (!response.ok) {
        setMessage(data.detail || "The job was not closed.");
        return;
      }
      setJob(data);
      setCloseNote("");
      setMessage("Closed. It is listed with the other closed jobs.");
    } catch {
      setMessage("The job was not closed.");
    } finally {
      setClosing(false);
    }
  }

  async function submitMatch(candidateId: string) {
    setSubmittingId(candidateId);
    setMessage("");
    try {
      const response = await fetch("/api/admin/submissions", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ candidate_id: candidateId, requisition_code: code }),
      });
      if (response.status === 401) {
        router.push("/admin/login");
        return;
      }
      if (!response.ok && response.status !== 409) {
        const data = await response.json().catch(() => ({}));
        setMessage(data.detail?.message || data.detail || "The submission was not created.");
        return;
      }
      setSubmissionReload((value) => value + 1);
      setMessage("Submitted for this job.");
    } catch {
      setMessage("The submission was not created.");
    } finally {
      setSubmittingId(null);
    }
  }

  async function save(event: FormEvent) {
    event.preventDefault();
    if (saving || !job) return;
    const description = replacement.trim();
    const descriptionChanged = Boolean(description) && description !== adminDescription(job).trim();
    setSaving(true);
    setMessage("Saving…");
    try {
      const response = await fetch(`/api/admin/jobs/${code}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          location,
          clearance_required: clearance,
          must_have_quotes: must.map((skill) => skill.trim()).filter(Boolean),
          nice_to_have_quotes: desired.map((skill) => skill.trim()).filter(Boolean),
          description_text: descriptionChanged ? description : undefined,
        }),
      });
      if (response.status === 401) {
        router.push("/admin/login");
        return;
      }
      if (!response.ok) {
        const detail = await response.json().catch(() => null);
        setMessage(detail?.detail || detail?.message || "Save failed. Reload the page to see what was stored.");
        return;
      }
      const data = (await response.json()) as JobDetail;
      setJob(data);
      setMust(postedSkills(data.must_have_quotes, data.must_have_skills));
      setDesired(postedSkills(data.nice_to_have_quotes, data.nice_to_have_skills));
      setReplacement(adminDescription(data));
      setMessage(
        descriptionChanged
          ? `Saved ${code}. The description above now shows your text. The summary and search index update within a minute.`
          : `Saved ${code}.`,
      );
    } catch {
      setMessage("Save did not finish. Reload the page to see what was stored.");
    } finally {
      setSaving(false);
    }
  }

  if (error) {
    return <p className="text-sm text-red-700">{error}</p>;
  }
  if (!job) {
    return <p className="text-sm">Loading job…</p>;
  }

  return (
    <div className="flex flex-col gap-5">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <div className="flex items-center gap-4">
            <BackButton fallback="/admin/jobs" />
            <Link href="/admin/jobs" className="text-sm text-pine underline">
              All jobs
            </Link>
          </div>
          <p className="mt-2 font-mono text-sm text-pine">{job.requisition_code}</p>
          <h1 className="page-title">{job.title}</h1>
          <p className="text-sm text-ink/70">
            {job.location} · {job.status} · {job.description_source}
          </p>
        </div>
        {job.needs_review && <Badge>Needs review</Badge>}
      </div>

      {job.status !== "closed" ? (
        <form onSubmit={closeJob} className="panel p-4">
          <h2 className="font-serif text-xl">Close this job</h2>
          <p className="page-lead">It moves to the closed list on the jobs page. A later recrawl will not open it again.</p>
          <label className="mt-3 block text-sm">
            Why is it closing?
            <Textarea value={closeNote} onChange={(event) => setCloseNote(event.target.value)} rows={3} className="mt-1" required />
          </label>
          <Button type="submit" className="mt-3" disabled={closing}>
            {closing ? "Closing…" : "Close job"}
          </Button>
        </form>
      ) : (
        <section className="panel p-4">
          <h2 className="font-serif text-xl">Closed</h2>
          <p className="mt-2 text-sm leading-6">{job.close_note || "No note was saved."}</p>
          <Button type="button" variant="outline" className="mt-3" disabled={closing} onClick={reopenJob}>
            {closing ? "Reopening…" : "Reopen job"}
          </Button>
        </section>
      )}

      <JobSubmissions code={code} reload={submissionReload} onIndex={setSubmitted} />

      <section id="candidates" className="scroll-mt-6 panel p-4">
        <h2 className="font-serif text-xl">Matching candidates</h2>
        <p className="page-lead">Résumés that cover at least 50% of the mandatory lines. A strong match covers at least 90%.</p>
        <CandidateMailBar
          total={candidates.length}
          selectedCount={selected.size}
          allSelected={candidates.length > 0 && candidates.every((candidate) => selected.has(candidate.id))}
          onToggleAll={toggleAll}
          onCopy={copySelected}
          copied={copiedSel}
          note={copyNote}
        />
        <div className="mt-2 flex flex-wrap gap-2">
          {selected.size > 0 && (
            <Button
              type="button"
              size="sm"
              onClick={() => router.push(`/admin/review?job=${job.requisition_code}&candidates=${[...selected].join(",")}`)}
            >
              Review {selected.size} selected
            </Button>
          )}
          {candidates.length > 0 && (
            <Button
              type="button"
              size="sm"
              variant="outline"
              onClick={() =>
                downloadCsv(
                  `matches-${job.requisition_code}.csv`,
                  ["Name", "Email", "Location", "Mandatory", "Desired", "Strong match", "File"],
                  candidates.map((candidate) => [
                    candidate.full_name,
                    candidate.email,
                    candidate.location,
                    percent(candidate.mandatory_pct),
                    percent(candidate.desired_pct),
                    candidate.meets_bar ? "yes" : "no",
                    candidate.original_filename,
                  ]),
                )
              }
            >
              <Download /> Export CSV
            </Button>
          )}
        </div>
        <div className="mt-3 flex flex-col gap-2">
          {!candidatesLoaded && <p className="text-sm text-ink/60">Scoring résumés against this job…</p>}
          {candidatesLoaded && candidates.length === 0 && <p className="text-sm text-ink/60">No résumé covers at least 50% of the mandatory lines.</p>}
          {candidates.map((candidate) => {
            const existing = submitted[candidate.id];
            return (
            <article key={candidate.id} className={`rounded-lg border px-3 py-3 ${candidate.meets_bar ? "border-pine" : "border-line"}`}>
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div className="flex min-w-0 items-start gap-3">
                  <input
                    type="checkbox"
                    className="mt-1"
                    aria-label={`Select ${candidate.full_name || "candidate"}`}
                    checked={selected.has(candidate.id)}
                    onChange={() => toggle(candidate.id)}
                  />
                  <div className="min-w-0">
                    <p className="truncate text-sm font-medium">{candidate.full_name || "Unnamed résumé"}</p>
                    <p className="truncate text-xs text-ink/60">{candidate.original_filename || "No file name"}</p>
                    <p className="mt-1 text-xs text-ink/80">Email: {shown(candidate.email)}</p>
                    <p className="text-xs text-ink/80">Location: {shown(candidate.location)}</p>
                  </div>
                </div>
                <div className="flex gap-3 text-sm">
                  {existing ? (
                    <Link href={`/admin/submissions/${existing.id}`} className="text-pine hover:underline">
                      {existing.label}
                    </Link>
                  ) : (
                    <button
                      type="button"
                      className="text-pine hover:underline disabled:opacity-50"
                      disabled={submittingId === candidate.id}
                      onClick={() => submitMatch(candidate.id)}
                    >
                      {submittingId === candidate.id ? "Submitting…" : "Submit"}
                    </button>
                  )}
                  <Link href={`/admin/candidates/${candidate.id}`} className="text-pine hover:underline">
                    Profile
                  </Link>
                  <Link href={`/admin/review?job=${job.requisition_code}&candidate=${candidate.id}`} className="text-pine hover:underline">
                    Review
                  </Link>
                  <Link href={`/admin/match?id=${candidate.id}`} className="text-pine hover:underline">
                    Open résumé
                  </Link>
                  {candidate.has_file && (
                    <a href={resumeFileUrl(candidate.id, true)} className="text-pine hover:underline">
                      Download
                    </a>
                  )}
                </div>
              </div>
              <div className="mt-2 grid grid-cols-2 items-stretch gap-2">
                <CandidateScore label="Mandatory" percent={candidate.mandatory_pct} hit={candidate.mandatory_hit} total={candidate.mandatory_total} strong={candidate.meets_bar} />
                <CandidateScore label="Desired" percent={candidate.desired_pct} hit={candidate.desired_hit} total={candidate.desired_total} strong={false} />
              </div>
            </article>
            );
          })}
        </div>
      </section>

      <section className="panel p-4">
        <h2 className="font-serif text-xl">Description</h2>
        {job.description_note && <p className="mt-2 text-sm">{job.description_note}</p>}
        <p className="mt-3 whitespace-pre-wrap text-sm leading-6">{job.description_text || "No description on file."}</p>
        {job.source_url && (
          <a className="mt-3 inline-block text-sm text-pine underline" href={job.source_url}>
            Source posting
          </a>
        )}
      </section>

      <form onSubmit={save} className="flex flex-col gap-4">
        <div className="grid gap-4 sm:grid-cols-2">
          <SkillList label="Mandatory skills" skills={must} onChange={setMust} />
          <SkillList label="Desired skills" skills={desired} onChange={setDesired} />
        </div>
        <div className="grid gap-4 sm:grid-cols-2">
          <label className="text-sm">
            City
            <Input value={location} onChange={(event) => setLocation(event.target.value)} className="mt-1" />
          </label>
          <label className="text-sm">
            Clearance
            <Input value={clearance} onChange={(event) => setClearance(event.target.value)} className="mt-1" />
          </label>
        </div>
        <label className="text-sm">
          Internal description (replaces the careers-page text)
          <Textarea value={replacement} onChange={(event) => setReplacement(event.target.value)} rows={6} className="mt-1" />
        </label>
        <div className="flex items-center gap-3">
          <Button type="submit" disabled={saving}>
            {saving ? "Saving…" : "Save"}
          </Button>
          {message && <p className="text-sm" role="status">{message}</p>}
        </div>
      </form>
    </div>
  );
}

function CandidateScore({
  label,
  percent,
  hit,
  total,
  strong,
}: {
  label: string;
  percent: number | null;
  hit: number;
  total: number;
  strong: boolean;
}) {
  return (
    <div className="flex h-full min-h-20 flex-col justify-between rounded-lg bg-desk px-3 py-2">
      <p className="text-xs font-medium uppercase tracking-wide text-ink/50">{label}</p>
      <p className={`font-serif text-2xl leading-none ${strong ? "text-pine" : "text-ink"}`}>{percent == null ? "—" : `${Math.round(percent * 100)}%`}</p>
      <p className="text-xs text-ink/70">{total === 0 ? `No ${label.toLowerCase()} skills` : `${hit} of ${total} lines`}</p>
    </div>
  );
}

function adminDescription(job: JobDetail): string {
  return job.description_source === "admin" ? job.description_text || "" : "";
}

function postedSkills(quotes: string[] | undefined, names: string[] | undefined): string[] {
  const lines = (quotes || []).map((line) => line.trim()).filter(Boolean);
  if (lines.length) return lines;
  return (names || []).map((line) => line.trim()).filter(Boolean);
}

function SkillList({ label, skills, onChange }: { label: string; skills: string[]; onChange: (skills: string[]) => void }) {
  const [text, setText] = useState(formatSkills(skills));
  const focused = useRef(false);

  useEffect(() => {
    if (!focused.current) setText(formatSkills(skills));
  }, [skills.join("\n")]);

  return (
    <label className="block">
      <span className="text-sm font-medium">{label}</span>
      <textarea
        aria-label={label}
        value={text}
        rows={Math.max(skills.length, 3)}
        placeholder={"• "}
        onFocus={() => {
          focused.current = true;
        }}
        onChange={(event) => {
          setText(event.target.value);
          onChange(parseSkills(event.target.value));
        }}
        onBlur={() => {
          focused.current = false;
          const next = parseSkills(text);
          setText(formatSkills(next));
          onChange(next);
        }}
        className="mt-1 w-full resize-y rounded-md border border-line bg-card px-3 py-2 text-sm leading-6 outline-none focus:ring-2 focus:ring-pine"
      />
    </label>
  );
}

function formatSkills(skills: string[]): string {
  return skills.map((skill) => `• ${skill}`).join("\n");
}

function parseSkills(value: string): string[] {
  return value
    .split("\n")
    .map((line) => line.replace(/^[\s•\-\*]+/, "").trim())
    .filter(Boolean);
}
