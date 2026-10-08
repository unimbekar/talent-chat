"use client";

import { FormEvent, useEffect, useState } from "react";
import Link from "next/link";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  errorMessage,
  existingSubmissionId,
  parseSalary,
  personName,
  type JobBrief,
  type PersonBrief,
} from "@/lib/pipeline";

type Hit = PersonBrief;

type Props = {
  jobCode?: string;
  candidateId?: string;
  candidateName?: string;
  onCreated: () => void;
};

export function SubmissionForm({ jobCode, candidateId, candidateName, onCreated }: Props) {
  const [query, setQuery] = useState("");
  const [hits, setHits] = useState<Hit[]>([]);
  const [picked, setPicked] = useState<Hit | null>(null);
  const [jobs, setJobs] = useState<JobBrief[]>([]);
  const [jobQuery, setJobQuery] = useState("");
  const [pickedJob, setPickedJob] = useState("");
  const [salary, setSalary] = useState("");
  const [salaryNote, setSalaryNote] = useState("");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [existing, setExisting] = useState<string | null>(null);

  useEffect(() => {
    if (jobCode) return;
    fetch("/api/admin/jobs").then(async (response) => {
      if (!response.ok) return;
      const data = await response.json();
      setJobs(
        (data.jobs || [])
          .filter((job: JobBrief) => job.status !== "closed")
          .map((job: JobBrief) => ({
            requisition_code: job.requisition_code,
            title: job.title,
            location: job.location,
            status: job.status,
          })),
      );
    });
  }, [jobCode]);

  useEffect(() => {
    if (candidateId) return;
    const term = query.trim();
    if (term.length < 2) {
      setHits([]);
      return;
    }
    const handle = window.setTimeout(() => {
      const params = new URLSearchParams({ q: term, page_size: "6" });
      fetch(`/api/admin/resumes?${params}`).then(async (response) => {
        if (!response.ok) return;
        const data = await response.json();
        setHits(data.candidates || []);
      });
    }, 200);
    return () => window.clearTimeout(handle);
  }, [query, candidateId]);

  const jobChoices = jobs.filter((job) => {
    const haystack = `${job.requisition_code} ${job.title || ""} ${job.location || ""}`.toLowerCase();
    return haystack.includes(jobQuery.trim().toLowerCase());
  });

  async function submit(event: FormEvent) {
    event.preventDefault();
    setError("");
    setExisting(null);
    const person = candidateId || picked?.id;
    const code = jobCode || pickedJob;
    if (!person || !code) {
      setError("Choose a candidate and a job.");
      return;
    }
    const amount = parseSalary(salary);
    if (amount === "invalid") {
      setError("Enter a yearly salary in dollars, or leave it blank.");
      return;
    }
    setBusy(true);
    try {
      const response = await fetch("/api/admin/submissions", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          candidate_id: person,
          requisition_code: code,
          salary_usd: amount,
          salary_note: salaryNote.trim() || null,
          note: note.trim() || null,
        }),
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) {
        setExisting(existingSubmissionId(data));
        setError(errorMessage(data, "The submission was not created."));
        return;
      }
      setQuery("");
      setHits([]);
      setPicked(null);
      setPickedJob("");
      setSalary("");
      setSalaryNote("");
      setNote("");
      onCreated();
    } catch {
      setError("The submission was not created.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={submit} className="flex flex-col gap-3">
      {!candidateId && (
        <div>
          <label className="text-sm">
            Candidate
            <Input
              value={picked ? personName(picked) : query}
              onChange={(event) => {
                setPicked(null);
                setQuery(event.target.value);
              }}
              placeholder="Search by name or email"
              className="mt-1"
              aria-label="Search candidates to submit"
            />
          </label>
          {!picked && hits.length > 0 && (
            <ul className="mt-1 overflow-hidden rounded-lg border border-line bg-card">
              {hits.map((hit) => (
                <li key={hit.id}>
                  <button
                    type="button"
                    className="block w-full px-3 py-2 text-left text-sm hover:bg-desk"
                    onClick={() => {
                      setPicked(hit);
                      setHits([]);
                    }}
                  >
                    <span className="font-medium">{personName(hit)}</span>
                    <span className="ml-2 text-ink/55">{hit.email || hit.location || ""}</span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
      {candidateId && <p className="text-sm text-ink/70">Submitting {candidateName || "this candidate"}.</p>}
      {!jobCode && (
        <div>
          <label className="text-sm">
            Job
            <Input
              value={jobQuery}
              onChange={(event) => setJobQuery(event.target.value)}
              placeholder="Filter by code, title, or city"
              className="mt-1"
              aria-label="Filter jobs to submit"
            />
          </label>
          <div className="mt-1 max-h-40 overflow-auto rounded-lg border border-line">
            {jobChoices.slice(0, 8).map((job) => (
              <label key={job.requisition_code} className="flex cursor-pointer items-start gap-2 border-b border-line px-3 py-2 text-sm last:border-0 hover:bg-desk">
                <input
                  type="radio"
                  name="submission-job"
                  className="mt-1"
                  checked={pickedJob === job.requisition_code}
                  onChange={() => setPickedJob(job.requisition_code)}
                />
                <span>
                  <span className="font-mono text-pine">{job.requisition_code}</span> {job.title}
                  <span className="block text-xs text-ink/55">{job.location}</span>
                </span>
              </label>
            ))}
            {jobChoices.length === 0 && <p className="px-3 py-3 text-sm text-ink/60">No open job matches that filter.</p>}
          </div>
        </div>
      )}
      <div className="grid gap-3 sm:grid-cols-2">
        <label className="text-sm">
          Yearly salary, optional
          <Input value={salary} onChange={(event) => setSalary(event.target.value)} placeholder="165000" className="mt-1" inputMode="numeric" />
        </label>
        <label className="text-sm">
          Salary note
          <Input value={salaryNote} onChange={(event) => setSalaryNote(event.target.value)} placeholder="W2, negotiable" className="mt-1" />
        </label>
      </div>
      <label className="text-sm">
        Note for the history
        <textarea value={note} onChange={(event) => setNote(event.target.value)} rows={2} className="field mt-1" placeholder="Sent to the hiring manager" />
      </label>
      <div className="flex flex-wrap items-center gap-3">
        <Button type="submit" disabled={busy}>
          {busy ? "Submitting…" : "Submit"}
        </Button>
        {error && <p className="text-sm text-red-700">{error}</p>}
        {existing && (
          <Link href={`/admin/submissions/${existing}`} className="text-sm text-pine underline">
            Open the existing submission
          </Link>
        )}
      </div>
    </form>
  );
}
