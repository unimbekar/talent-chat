"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { Download, Mail, MessageSquare, Phone } from "lucide-react";

import { BackButton } from "@/components/back-button";
import { CommentThread } from "@/components/comment-thread";
import { SubmissionForm } from "@/components/submission-form";
import { StageBadge } from "@/components/stage-badge";
import { Button } from "@/components/ui/button";
import { errorMessage, money, personName, resumeFileUrl, when, type Note, type SubmissionCard } from "@/lib/pipeline";

type Profile = {
  id: string;
  full_name: string | null;
  email: string | null;
  phone: string | null;
  location: string | null;
  status: string;
  titles: string[];
  summary: string | null;
  clearance: string | null;
  original_filename: string | null;
  has_file: boolean;
};

export default function CandidateProfilePage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const id = params.id;
  const [profile, setProfile] = useState<Profile | null>(null);
  const [submissions, setSubmissions] = useState<SubmissionCard[]>([]);
  const [comments, setComments] = useState<Note[]>([]);
  const [composer, setComposer] = useState(false);
  const [error, setError] = useState("");

  const load = useCallback(() => {
    fetch(`/api/admin/resumes/${id}`).then(async (response) => {
      if (response.status === 401) {
        router.push("/admin/login");
        return;
      }
      if (!response.ok) {
        setError("That candidate is not on file.");
        return;
      }
      const data = await response.json();
      setProfile(data.candidate);
      setError("");
    });
    fetch(`/api/admin/resumes/${id}/submissions`).then(async (response) => {
      if (response.ok) {
        const data = await response.json();
        setSubmissions(data.submissions || []);
      }
    });
    fetch(`/api/admin/resumes/${id}/comments`).then(async (response) => {
      if (response.ok) {
        const data = await response.json();
        setComments(data.comments || []);
      }
    });
  }, [id, router]);

  useEffect(() => {
    load();
  }, [load]);

  async function comment(method: string, path: string, body?: string) {
    const response = await fetch(path, {
      method,
      headers: body ? { "Content-Type": "application/json" } : undefined,
      body: body ? JSON.stringify({ body }) : undefined,
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(errorMessage(data, "The comment was not saved."));
    load();
  }

  if (error && !profile) return <p className="text-sm text-red-700">{error}</p>;
  if (!profile) return <p className="text-sm">Loading candidate…</p>;

  const inProgress = submissions.filter((row) => row.stage !== "rejected" && row.stage !== "withdrawn");

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <div className="flex items-center gap-4">
            <BackButton fallback="/admin/candidates" />
            <Link href="/admin/candidates" className="text-sm text-pine underline">
              All candidates
            </Link>
          </div>
          <h1 className="page-title mt-3">{personName(profile)}</h1>
          <p className="page-lead">
            {[profile.email, profile.phone, profile.location, profile.titles.join(", ")].filter(Boolean).join(" · ") || "No contact details on file yet."}
          </p>
          {(profile.phone || profile.email) && (
            <div className="mt-3 flex flex-wrap gap-2">
              {profile.phone && (
                <>
                  <a href={`tel:${dialable(profile.phone)}`} className="inline-flex items-center gap-1.5 rounded-full bg-night px-4 py-2 text-sm font-medium text-white active:scale-95">
                    <Phone className="size-4 text-pine-soft" /> Call
                  </a>
                  <a href={`sms:${dialable(profile.phone)}`} className="inline-flex items-center gap-1.5 rounded-full border border-line bg-card px-4 py-2 text-sm font-medium active:scale-95">
                    <MessageSquare className="size-4 text-pine" /> Text
                  </a>
                </>
              )}
              {profile.email && (
                <a href={`mailto:${profile.email}`} className="inline-flex items-center gap-1.5 rounded-full border border-line bg-card px-4 py-2 text-sm font-medium active:scale-95">
                  <Mail className="size-4 text-pine" /> Email
                </a>
              )}
            </div>
          )}
        </div>
        <div className="flex flex-wrap gap-2">
          {profile.has_file && (
            <Button asChild variant="outline">
              <a href={resumeFileUrl(profile.id, true)} title={profile.original_filename || undefined}>
                <Download /> Download résumé
              </a>
            </Button>
          )}
          <Button asChild variant="outline">
            <Link href={`/admin/match?id=${profile.id}`}>Rank against jobs</Link>
          </Button>
          <Button type="button" onClick={() => setComposer((value) => !value)}>
            Submit to a job
          </Button>
        </div>
      </div>

      {profile.summary && (
        <section className="panel p-4">
          <h2 className="font-serif text-xl">Summary</h2>
          <p className="mt-2 whitespace-pre-wrap text-sm leading-6">{profile.summary}</p>
          {profile.clearance && <p className="mt-2 text-sm text-ink/65">Clearance: {profile.clearance}</p>}
        </section>
      )}

      {composer && (
        <section className="panel p-4">
          <h2 className="font-serif text-xl">Submit to a job</h2>
          <div className="mt-3">
            <SubmissionForm
              candidateId={profile.id}
              candidateName={personName(profile)}
              onCreated={() => {
                setComposer(false);
                load();
              }}
            />
          </div>
        </section>
      )}

      <section className="panel p-4">
        <h2 className="font-serif text-xl">Jobs submitted</h2>
        <p className="page-lead">
          {submissions.length === 0
            ? "This person has not been submitted for a job yet."
            : `${submissions.length} ${submissions.length === 1 ? "job" : "jobs"} in the history, ${inProgress.length} still in progress.`}
        </p>
        <ul className="mt-4 flex flex-col gap-2">
          {submissions.map((row) => (
            <li key={row.id}>
              <Link
                href={`/admin/submissions/${row.id}`}
                className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-line px-3 py-3 transition hover:border-pine/40 hover:bg-desk/50"
              >
                <span>
                  <span className="block text-sm font-medium">
                    <span className="font-mono text-pine">{row.job.requisition_code}</span> {row.job.title || "Untitled job"}
                  </span>
                  <span className="block text-xs text-ink/60">
                    {row.job.location || "No city"} · {row.job.status} · updated {when(row.updated_at)}
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

      <CommentThread
        comments={comments}
        heading="Notes on this person"
        hint="These follow the candidate across every job. A note about one submission belongs on that submission."
        empty="No notes on this person yet."
        onCreate={(body) => comment("POST", `/api/admin/resumes/${id}/comments`, body)}
        onEdit={(commentId, body) => comment("PATCH", `/api/admin/resumes/${id}/comments/${commentId}`, body)}
        onDelete={(commentId) => comment("DELETE", `/api/admin/resumes/${id}/comments/${commentId}`)}
      />
    </div>
  );
}

function dialable(phone: string): string {
  const digits = phone.replace(/[^\d+]/g, "");
  return digits.length === 10 ? `+1${digits}` : digits;
}
