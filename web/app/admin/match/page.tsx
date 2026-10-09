"use client";

import { FormEvent, Suspense, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";

import { BackButton } from "@/components/back-button";
import { Badge } from "@/components/ui/badge";
import { readCache, writeCache } from "@/lib/page-cache";
import { resumeFileUrl } from "@/lib/pipeline";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";

type Skill = { name: string; years: number | null };
type Profile = {
  id: string;
  full_name: string | null;
  email: string | null;
  phone: string | null;
  location: string | null;
  skills: Skill[];
  titles: string[];
  clearance: string | null;
  polygraph: string | null;
  citizenship: string | null;
  summary: string | null;
  has_file?: boolean;
};
type MatchRow = {
  requisition_code: string;
  title: string | null;
  location: string | null;
  clearance_flag: string | null;
  mandatory_pct: number | null;
  mandatory_hit: number;
  mandatory_total: number;
  desired_pct: number | null;
  desired_hit: number;
  desired_total: number;
  desired_any: boolean;
  required_matched: string[];
  required_missing: string[];
  meets_bar: boolean;
};

export default function MatchRoute() {
  return (
    <Suspense fallback={<p className="text-sm">Loading the review screen…</p>}>
      <MatchPage />
    </Suspense>
  );
}

function MatchPage() {
  const router = useRouter();
  const params = useSearchParams();
  const [profile, setProfile] = useState<Profile | null>(null);
  const [requiredByJob, setRequiredByJob] = useState<Record<string, string>>({});
  const [matches, setMatches] = useState<MatchRow[]>([]);
  const [notice, setNotice] = useState<Notice | null>(null);
  const [uploading, setUploading] = useState(false);
  const [ranking, setRanking] = useState(false);
  const [rankPercent, setRankPercent] = useState(0);
  const [fileName, setFileName] = useState("");
  const loadGeneration = useRef(0);
  const candidateId = params.get("id") || "";
  const [submitted, setSubmitted] = useState<Record<string, SubmissionLink>>({});
  const [submittingCode, setSubmittingCode] = useState<string | null>(null);
  const [submissionReload, setSubmissionReload] = useState(0);

  useEffect(() => {
    const id = profile?.id;
    if (!id) {
      setSubmitted({});
      return;
    }
    let cancelled = false;
    fetch(`/api/admin/pipeline?scope=all&candidate_id=${id}`)
      .then((response) => (response.ok ? response.json() : null))
      .then((data) => {
        if (cancelled || !data) return;
        const index: Record<string, SubmissionLink> = {};
        for (const row of data.submissions || []) {
          if (row.job?.requisition_code) index[row.job.requisition_code] = { id: row.id, label: row.stage_label };
        }
        setSubmitted(index);
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [profile?.id, submissionReload]);

  async function submitTo(code: string) {
    if (!profile || submittingCode) return;
    setSubmittingCode(code);
    try {
      const response = await fetch("/api/admin/submissions", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ candidate_id: profile.id, requisition_code: code }),
      });
      if (response.status === 401) {
        router.push("/admin/login");
        return;
      }
      const data = await readBody(response);
      if (!response.ok && response.status !== 409) {
        setNotice({ tone: "error", text: submissionError(data) || "The submission was not created." });
        return;
      }
      setNotice({ tone: "ok", text: `${profile.full_name || "This candidate"} is submitted for ${code}.` });
      setSubmissionReload((value) => value + 1);
    } catch {
      setNotice({ tone: "error", text: "The submission was not created." });
    } finally {
      setSubmittingCode(null);
    }
  }

  async function openCandidate(id: string) {
    const response = await fetch(`/api/admin/resumes/${id}`);
    if (response.status === 401) {
      router.push("/admin/login");
      return;
    }
    if (!response.ok) {
      setNotice({ tone: "error", text: "That résumé could not be opened." });
      return;
    }
    const data = await response.json();
    setRequiredByJob({});
    setProfile(data.candidate);
    setMatches(data.matches || []);
    router.replace(`/admin/match?id=${id}`);
  }

  useEffect(() => {
    if (!candidateId) return;
    const generation = ++loadGeneration.current;
    let cancelled = false;
    const saved = readCache<{ profile: Profile; matches: MatchRow[] }>(`talent-resume:${candidateId}`);
    if (saved) {
      setProfile(saved.profile);
      setMatches(saved.matches);
    }
    fetch(`/api/admin/resumes/${candidateId}`).then(async (response) => {
      if (cancelled || generation !== loadGeneration.current) return;
      if (response.status === 401) {
        router.push("/admin/login");
        return;
      }
      if (!response.ok) {
        setNotice({ tone: "error", text: "That résumé could not be opened." });
        return;
      }
      const data = await response.json();
      if (cancelled || generation !== loadGeneration.current) return;
      setProfile(data.candidate);
      setMatches(data.matches || []);
    });
    return () => {
      cancelled = true;
    };
  }, [candidateId]);

  useEffect(() => {
    if (profile && profile.id === candidateId) writeCache(`talent-resume:${candidateId}`, { profile, matches });
  }, [profile, matches, candidateId]);

  async function upload(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const formEl = event.currentTarget;
    const chosen = formEl.querySelector<HTMLInputElement>('input[type="file"]')?.files?.[0];
    if (!chosen) {
      setNotice({ tone: "error", text: "Choose a PDF, DOC, DOCX, or TXT file first." });
      return;
    }
    const suffix = chosen.name.split(".").pop()?.toLowerCase() || "";
    if (!["pdf", "doc", "docx", "txt"].includes(suffix)) {
      setNotice({ tone: "error", text: "Upload a PDF, DOC, DOCX, or TXT file." });
      return;
    }
    if (chosen.size === 0) {
      setNotice({ tone: "error", text: "That file is empty." });
      return;
    }
    setUploading(true);
    setNotice({ tone: "info", text: `Reading ${chosen.name}…` });
    try {
      const response = await fetch("/api/admin/resumes", { method: "POST", body: new FormData(formEl) });
      if (response.status === 401) {
        router.push("/admin/login");
        return;
      }
      const data = await readBody(response);
      if (!response.ok) {
        setNotice({ tone: "error", text: detailOf(data) || "The upload did not finish. Try the file again." });
        return;
      }
      formEl.reset();
      setFileName("");
      if (data.already_ingested) {
        if (!data.candidate_id) {
          setNotice({ tone: "error", text: "This résumé is already on file, but the saved profile could not be opened." });
          return;
        }
        await openCandidate(data.candidate_id);
        setNotice({
          tone: "info",
          text: "This résumé is already on file. The saved profile is open below. Confirm and rank to refresh the matches.",
        });
        return;
      }
      if (!data.candidate?.id) {
        setNotice({ tone: "error", text: "The file was accepted, but no profile came back. Try the upload again." });
        return;
      }
      setProfile(data.candidate);
      setMatches([]);
      setNotice({ tone: "ok", text: `${data.candidate.full_name || chosen.name} is ready. Review the profile, then confirm and rank.` });
      router.replace(`/admin/match?id=${data.candidate.id}`);
    } catch {
      setNotice({ tone: "error", text: "The upload did not finish. Check the file and try again." });
    } finally {
      setUploading(false);
    }
  }

  async function confirm() {
    if (!profile || ranking) return;
    const generation = ++loadGeneration.current;
    const started = Date.now();
    setRanking(true);
    setRankPercent(8);
    setNotice({ tone: "info", text: "Comparing this résumé with each open job." });
    const timer = window.setInterval(() => {
      const elapsed = Date.now() - started;
      setRankPercent(Math.min(90, 8 + Math.round((elapsed / 25000) * 82)));
    }, 400);
    try {
      const response = await fetch(`/api/admin/resumes/${profile.id}/confirm`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(profile),
      });
      const data = await readBody(response);
      if (generation !== loadGeneration.current) return;
      if (!response.ok) {
        setNotice({ tone: "error", text: detailOf(data) || "Ranking did not finish. The job list is unchanged." });
        return;
      }
      const next = data.matches || [];
      setMatches(next);
      if (data.candidate) setProfile(data.candidate);
      setRankPercent(100);
      const visibleCount = next.filter((row) => row.mandatory_pct != null && row.mandatory_pct >= 0.5).length;
      setNotice(
        visibleCount
          ? { tone: "ok", text: `Ranking finished. ${visibleCount} ${visibleCount === 1 ? "job covers" : "jobs cover"} at least half of the mandatory lines.` }
          : { tone: "info", text: "Ranking finished. No open job covers at least half of the mandatory lines." },
      );
    } catch {
      if (generation === loadGeneration.current) {
        setNotice({ tone: "error", text: "Ranking did not finish. The job list is unchanged." });
      }
    } finally {
      window.clearInterval(timer);
      if (generation === loadGeneration.current) setRanking(false);
    }
  }

  async function remove() {
    if (!profile || ranking || uploading) return;
    if (!window.confirm(`Delete ${profile.full_name || "this résumé"} from the desk?`)) return;
    const response = await fetch(`/api/admin/resumes/${profile.id}`, { method: "DELETE" });
    if (!response.ok) {
      setNotice({ tone: "error", text: "The résumé was not deleted." });
      return;
    }
    setProfile(null);
    setMatches([]);
    setNotice({ tone: "ok", text: "The résumé was deleted." });
    router.replace("/admin/match");
  }

  const resumeNames = (profile?.skills || []).map((skill) => skill.name);
  const visible = matches.filter((row) => row.mandatory_pct != null && row.mandatory_pct >= 0.5);
  const strong = visible.filter((row) => row.meets_bar && jobRequirementMet(row.requisition_code, requiredByJob, resumeNames));

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <h1 className="page-title">Match a résumé</h1>
        <BackButton fallback="/admin/find" />
      </div>
      <form onSubmit={upload} className="flex flex-col gap-3 panel p-4 sm:flex-row sm:items-end">
        <label className="flex-1 text-sm">
          PDF, DOC, DOCX, or TXT
          <Input
            name="file"
            type="file"
            accept=".pdf,.doc,.docx,.txt,application/pdf,application/msword"
            className="mt-1"
            disabled={uploading}
            onChange={(event) => {
              setFileName(event.target.files?.[0]?.name || "");
              setNotice(null);
            }}
          />
          {fileName && <span className="mt-1 block text-xs text-ink/60">{fileName}</span>}
        </label>
        <Button type="submit" disabled={uploading}>
          {uploading ? "Reading…" : "Upload"}
        </Button>
      </form>
      {uploading && <WorkBar label="Reading the résumé and building a profile…" percent={null} />}
      {notice && <Notice tone={notice.tone} text={notice.text} />}
      {profile && (
        <Card>
          <CardHeader>
            <CardTitle>Review parsed profile</CardTitle>
          </CardHeader>
          <CardContent className="grid gap-3">
            <div className="grid gap-3 sm:grid-cols-2">
              <Field label="Name" value={profile.full_name || ""} onChange={(value) => setProfile({ ...profile, full_name: value })} />
              <Field label="Email" value={profile.email || ""} onChange={(value) => setProfile({ ...profile, email: value })} />
              <Field label="Phone" value={profile.phone || ""} onChange={(value) => setProfile({ ...profile, phone: value })} />
              <Field label="City" value={profile.location || ""} onChange={(value) => setProfile({ ...profile, location: value })} />
              <Field label="Clearance" value={profile.clearance || ""} onChange={(value) => setProfile({ ...profile, clearance: value })} />
              <Field label="Polygraph" value={profile.polygraph || ""} onChange={(value) => setProfile({ ...profile, polygraph: value })} />
            </div>
            <Field
              label="Titles"
              value={(profile.titles || []).join(", ")}
              onChange={(value) =>
                setProfile({
                  ...profile,
                  titles: value
                    .split(",")
                    .map((item) => item.trim())
                    .filter(Boolean),
                })
              }
            />
            <label className="text-sm">
              Summary
              <Textarea value={profile.summary || ""} onChange={(event) => setProfile({ ...profile, summary: event.target.value })} className="mt-1" rows={3} />
            </label>
            <BulletList
              label="Skills on this résumé"
              hint="Tools and languages only. Duties, dates, and other words are left out."
              skills={(profile.skills || []).map((skill) => skill.name)}
              onChange={(skills) =>
                setProfile({
                  ...profile,
                  skills: skills.map((name) => ({ name, years: null })),
                })
              }
            />
            <p className="text-sm text-ink/70">
              A strong match covers at least 90% of every mandatory line. Any desired skill is a plus and does not lower the mandatory score.
            </p>
            <div className="flex flex-wrap gap-2">
              <Button type="button" onClick={confirm} disabled={ranking || uploading}>
                {ranking ? "Ranking…" : "Confirm and rank"}
              </Button>
              {profile.has_file && (
                <Button asChild variant="outline">
                  <a href={resumeFileUrl(profile.id, true)}>Download résumé</a>
                </Button>
              )}
              <Button type="button" variant="outline" onClick={remove} disabled={ranking || uploading}>
                Delete
              </Button>
            </div>
            {ranking && <WorkBar label="Comparing this résumé with each open job…" percent={rankPercent} />}
          </CardContent>
        </Card>
      )}
      {matches.length > 0 && (
        <section className="flex flex-col gap-3">
          <div>
            <h2 className="font-serif text-xl">Job matches</h2>
            <p className="text-sm text-ink/70">
              {visible.length === 0
                ? "No job covers at least 50% of the mandatory lines."
                : `${strong.length} of ${visible.length} cover at least 90% of mandatory lines, plus any tool you require on that job alone.`}
            </p>
          </div>
          {visible.map((row) => (
            <MatchCard
              key={row.requisition_code}
              row={row}
              requiredText={requiredByJob[row.requisition_code] || ""}
              onRequiredChange={(value) => setRequiredByJob((current) => ({ ...current, [row.requisition_code]: value }))}
              resumeNames={resumeNames}
              candidateId={profile?.id || candidateId}
              submission={submitted[row.requisition_code]}
              submitting={submittingCode === row.requisition_code}
              onSubmit={() => submitTo(row.requisition_code)}
            />
          ))}
        </section>
      )}
    </div>
  );
}

type Notice = { tone: "error" | "info" | "ok"; text: string };

function Notice({ tone, text }: Notice) {
  const toneClass = {
    error: "border-red-300 bg-red-50 text-red-800",
    info: "border-amber-300 bg-amber-50 text-amber-950",
    ok: "border-emerald-300 bg-emerald-50 text-emerald-900",
  }[tone];
  return (
    <p className={`rounded-md border px-3 py-2 text-sm ${toneClass}`} role={tone === "error" ? "alert" : "status"}>
      {text}
    </p>
  );
}

function WorkBar({ label, percent }: { label: string; percent: number | null }) {
  return (
    <div className="rounded-lg border border-line bg-card px-4 py-3" role="status">
      <div className="flex items-center justify-between gap-3 text-sm">
        <p>{label}</p>
        {percent != null && <p className="font-mono text-xs text-ink/60">{percent}%</p>}
      </div>
      <div className="mt-2 h-2 overflow-hidden rounded-full bg-desk">
        {percent == null ? (
          <div className="h-full w-1/3 bg-pine" style={{ animation: "work-slide 1.2s ease-in-out infinite" }} />
        ) : (
          <div className="h-full bg-pine transition-all" style={{ width: `${percent}%` }} />
        )}
      </div>
    </div>
  );
}

type ApiBody = {
  detail?: unknown;
  already_ingested?: boolean;
  candidate_id?: string;
  candidate?: Profile;
  matches?: MatchRow[];
};

async function readBody(response: Response): Promise<ApiBody> {
  const text = await response.text();
  if (!text) return {};
  try {
    return JSON.parse(text);
  } catch {
    return { detail: "The server did not finish that request. Try again." };
  }
}

type SubmissionLink = { id: string; label: string };

function submissionError(data: { detail?: unknown }): string {
  const detail = data.detail as { message?: unknown } | undefined;
  if (detail && typeof detail === "object" && typeof detail.message === "string") return detail.message;
  return detailOf(data);
}

function detailOf(data: { detail?: unknown }): string {
  if (typeof data.detail === "string") return data.detail;
  if (Array.isArray(data.detail)) {
    return data.detail
      .map((item) => (typeof item === "string" ? item : item?.msg || ""))
      .filter(Boolean)
      .join(" ");
  }
  return "";
}

function MatchCard({
  row,
  requiredText,
  onRequiredChange,
  resumeNames,
  candidateId,
  submission,
  submitting,
  onSubmit,
}: {
  row: MatchRow;
  requiredText: string;
  onRequiredChange: (value: string) => void;
  resumeNames: string[];
  candidateId: string;
  submission?: SubmissionLink;
  submitting: boolean;
  onSubmit: () => void;
}) {
  const requirement = requirementStatus(requiredText, resumeNames);
  const strong = row.meets_bar && requirement.missing.length === 0;
  return (
    <article className={`rounded-xl border bg-card p-4 ${strong ? "border-pine" : "border-line"}`}>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
            <Link href={`/admin/jobs/${row.requisition_code}`} className="font-mono text-sm text-pine hover:underline">
              {row.requisition_code}
            </Link>
            <Link href={`/admin/jobs/${row.requisition_code}#candidates`} className="text-sm text-pine hover:underline">
              Matching candidates
            </Link>
          </div>
          <Link href={`/admin/jobs/${row.requisition_code}`} className="mt-1 block truncate font-serif text-lg hover:underline">
            {row.title}
          </Link>
          <p className="truncate text-xs text-ink/60">{row.location}</p>
        </div>
        <div className="flex flex-col items-end gap-2">
          {strong && <span className="rounded-full bg-pine/10 px-2.5 py-1 text-xs font-medium text-pine">Strong match</span>}
          {candidateId && (
            <div className="flex flex-wrap justify-end gap-3 text-sm">
              {submission ? (
                <Link href={`/admin/submissions/${submission.id}`} className="text-pine hover:underline">
                  {submission.label}
                </Link>
              ) : (
                <button type="button" className="text-pine hover:underline disabled:opacity-50" disabled={submitting} onClick={onSubmit}>
                  {submitting ? "Submitting…" : "Submit"}
                </button>
              )}
              <Link href={`/admin/candidates/${candidateId}`} className="text-pine hover:underline">
                Profile
              </Link>
              <Link href={`/admin/review?job=${row.requisition_code}&candidate=${candidateId}`} className="text-pine hover:underline">
                Review
              </Link>
              <a href={resumeFileUrl(candidateId)} target="_blank" rel="noopener noreferrer" className="text-pine hover:underline">
                Open résumé
              </a>
            </div>
          )}
        </div>
      </div>
      <div className="mt-3 grid grid-cols-2 items-stretch gap-2">
        <ScorePane
          label="Mandatory"
          percent={row.mandatory_pct}
          hit={row.mandatory_hit}
          total={row.mandatory_total}
          tone={strong ? "pine" : "ink"}
        />
        <ScorePane
          label="Desired"
          percent={row.desired_pct}
          hit={row.desired_hit}
          total={row.desired_total}
          note={row.desired_any ? "At least one desired skill" : ""}
          tone="ink"
        />
      </div>
      <label className="mt-3 block text-xs text-ink/70">
        Required for this job
        <input
          aria-label={`Required for ${row.requisition_code}`}
          value={requiredText}
          onChange={(event) => onRequiredChange(event.target.value)}
          className="mt-1 w-full rounded-md border border-line bg-desk px-2 py-1.5 text-sm text-ink outline-none focus:ring-2 focus:ring-pine"
        />
      </label>
      {(requirement.matched.length > 0 || requirement.missing.length > 0) && (
        <div className="mt-2 flex flex-wrap gap-1">
          {requirement.matched.map((skill) => (
            <Badge key={skill}>{skill} 100%</Badge>
          ))}
          {requirement.missing.map((skill) => (
            <Badge key={skill}>{skill} missing</Badge>
          ))}
        </div>
      )}
      {row.clearance_flag === "clearance_short" && <p className="mt-2 text-xs">Clearance on the résumé is below this job.</p>}
    </article>
  );
}

function ScorePane({
  label,
  percent,
  hit,
  total,
  note = "",
  tone,
}: {
  label: string;
  percent: number | null;
  hit: number;
  total: number;
  note?: string;
  tone: "pine" | "ink";
}) {
  return (
    <div className="flex h-full min-h-24 flex-col justify-between rounded-lg bg-desk px-3 py-2">
      <p className="text-xs font-medium uppercase tracking-wide text-ink/50">{label}</p>
      <p className={`font-serif text-3xl leading-none ${tone === "pine" ? "text-pine" : "text-ink"}`}>{percent == null ? "—" : `${Math.round(percent * 100)}%`}</p>
      <p className="text-xs text-ink/70">
        {total === 0 ? `No ${label.toLowerCase()} skills on file` : `${hit} of ${total} lines`}
        {note ? ` · ${note}` : ""}
      </p>
    </div>
  );
}

function jobRequirementMet(code: string, requiredByJob: Record<string, string>, resumeNames: string[]): boolean {
  return requirementStatus(requiredByJob[code] || "", resumeNames).missing.length === 0;
}

function requirementStatus(text: string, resumeNames: string[]): { matched: string[]; missing: string[] } {
  const needed = text
    .split(/[,•\n]/)
    .map((item) => item.trim())
    .filter(Boolean);
  const matched: string[] = [];
  const missing: string[] = [];
  for (const skill of needed) {
    if (resumeHas(skill, resumeNames)) matched.push(skill);
    else missing.push(skill);
  }
  return { matched, missing };
}

function resumeHas(skill: string, resumeNames: string[]): boolean {
  const pattern = new RegExp(`(?<!\\w)${skill.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}(?!\\w)`, "i");
  return resumeNames.some((name) => pattern.test(name));
}

function Field({ label, value, onChange }: { label: string; value: string; onChange: (value: string) => void }) {
  return (
    <label className="text-sm">
      {label}
      <Input value={value} onChange={(event) => onChange(event.target.value)} className="mt-1" />
    </label>
  );
}

function BulletList({
  label,
  hint,
  skills,
  onChange,
}: {
  label: string;
  hint: string;
  skills: string[];
  onChange: (skills: string[]) => void;
}) {
  const [text, setText] = useState(formatSkills(skills));
  const focused = useRef(false);

  useEffect(() => {
    if (!focused.current) setText(formatSkills(skills));
  }, [skills.join("\n")]);

  return (
    <label className="block">
      <span className="text-sm font-medium">{label}</span>
      <span className="mt-0.5 block text-xs text-ink/60">{hint}</span>
      <textarea
        aria-label={label}
        value={text}
        rows={Math.max(Math.min(skills.length + 1, 8), 4)}
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
        className="mt-1 w-full resize-y rounded-md border border-line bg-desk px-3 py-2 text-sm leading-6 outline-none focus:ring-2 focus:ring-pine"
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
    .map((line) => line.replace(/^\s*[•\-*]\s*/, "").trim())
    .filter(Boolean);
}
