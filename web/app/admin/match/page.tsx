"use client";

import { FormEvent, Suspense, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";

import { Badge } from "@/components/ui/badge";
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
  const [message, setMessage] = useState("");
  const [ranking, setRanking] = useState(false);
  const loadGeneration = useRef(0);
  const candidateId = params.get("id") || "";

  async function openCandidate(id: string) {
    const response = await fetch(`/api/admin/resumes/${id}`);
    if (response.status === 401) {
      router.push("/admin/login");
      return;
    }
    if (!response.ok) return;
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
    fetch(`/api/admin/resumes/${candidateId}`).then(async (response) => {
      if (cancelled || generation !== loadGeneration.current) return;
      if (response.status === 401) {
        router.push("/admin/login");
        return;
      }
      if (!response.ok) return;
      const data = await response.json();
      if (cancelled || generation !== loadGeneration.current) return;
      setProfile(data.candidate);
      setMatches(data.matches || []);
    });
    return () => {
      cancelled = true;
    };
  }, [candidateId]);

  async function upload(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const response = await fetch("/api/admin/resumes", { method: "POST", body: form });
    if (response.status === 401) {
      router.push("/admin/login");
      return;
    }
    const data = await response.json();
    if (!response.ok) {
      setMessage(data.detail || "Upload failed.");
      return;
    }
    if (data.already_ingested) {
      await openCandidate(data.candidate_id);
      setMessage("This résumé is already on file. The saved profile is open below. Confirm and rank to refresh the matches.");
      return;
    }
    setProfile(data.candidate);
    setMatches([]);
    setMessage("");
    router.replace(`/admin/match?id=${data.candidate.id}`);
  }

  async function confirm() {
    if (!profile || ranking) return;
    const generation = ++loadGeneration.current;
    setRanking(true);
    setMessage("");
    try {
      const response = await fetch(`/api/admin/resumes/${profile.id}/confirm`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(profile),
      });
      const data = await response.json().catch(() => ({}));
      if (generation !== loadGeneration.current) return;
      if (!response.ok) {
        setMessage(data.detail || "Ranking did not finish. The candidate list is unchanged.");
        return;
      }
      setMatches(data.matches || []);
      setProfile(data.candidate);
      setMessage(data.matches?.length ? "" : "Ranking finished. No open job is on file.");
    } catch {
      if (generation === loadGeneration.current) {
        setMessage("Ranking did not finish. The candidate list is unchanged.");
      }
    } finally {
      if (generation === loadGeneration.current) setRanking(false);
    }
  }

  async function remove() {
    if (!profile) return;
    await fetch(`/api/admin/resumes/${profile.id}`, { method: "DELETE" });
    setProfile(null);
    setMatches([]);
    setMessage("");
    router.replace("/admin/match");
  }

  const resumeNames = (profile?.skills || []).map((skill) => skill.name);
  const visible = matches.filter((row) => row.mandatory_pct != null && row.mandatory_pct >= 0.5);
  const strong = visible.filter((row) => row.meets_bar && jobRequirementMet(row.requisition_code, requiredByJob, resumeNames));

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <h1 className="font-serif text-2xl">Match a résumé</h1>
        <Link href="/admin/find" className="text-sm text-pine underline-offset-2 hover:underline">
          Back to find
        </Link>
      </div>
      <form onSubmit={upload} className="flex flex-col gap-3 rounded-lg border border-line bg-card p-4 sm:flex-row sm:items-end">
        <label className="flex-1 text-sm">
          PDF, DOCX, or TXT
          <Input name="file" type="file" accept=".pdf,.docx,.txt,.doc" className="mt-1" required />
        </label>
        <Button type="submit">Upload</Button>
      </form>
      {message && <p className="text-sm">{message}</p>}
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
              <Button type="button" onClick={confirm} disabled={ranking}>
                {ranking ? "Ranking…" : "Confirm and rank"}
              </Button>
              <Button type="button" variant="outline" onClick={remove}>
                Delete
              </Button>
            </div>
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
            />
          ))}
        </section>
      )}
    </div>
  );
}

function MatchCard({
  row,
  requiredText,
  onRequiredChange,
  resumeNames,
}: {
  row: MatchRow;
  requiredText: string;
  onRequiredChange: (value: string) => void;
  resumeNames: string[];
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
        {strong && <span className="rounded-full bg-pine/10 px-2.5 py-1 text-xs font-medium text-pine">Strong match</span>}
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
