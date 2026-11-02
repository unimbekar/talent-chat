"use client";

import { Suspense, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Download, FilePenLine } from "lucide-react";

import { BackButton } from "@/components/back-button";
import { Button } from "@/components/ui/button";
import { resumeFileUrl } from "@/lib/pipeline";

type JobOption = { requisition_code: string; title: string | null; status: string };
type Person = { id: string; full_name: string | null; original_filename: string | null; email: string | null };
type Missing = { line: string; kind: string; justification: string; ready: boolean };
type UpdateView = {
  job: { requisition_code: string; title: string | null; location: string | null };
  candidate: { id: string; full_name: string | null; original_filename: string | null; has_file?: boolean };
  missing: Missing[];
  complete: boolean;
  updated_at: string | null;
  updated_by: string;
  has_file: boolean;
};

export default function ResumeUpdateRoute() {
  return (
    <Suspense fallback={<p className="text-sm">Loading the résumé update…</p>}>
      <ResumeUpdatePage />
    </Suspense>
  );
}

function ResumeUpdatePage() {
  const router = useRouter();
  const params = useSearchParams();
  const code = params.get("job") || "";
  const candidateId = params.get("candidate") || "";

  const [jobs, setJobs] = useState<JobOption[]>([]);
  const [draftJob, setDraftJob] = useState(code);
  const [query, setQuery] = useState("");
  const [hits, setHits] = useState<Person[]>([]);
  const [picked, setPicked] = useState<Person | null>(null);
  const [view, setView] = useState<UpdateView | null>(null);
  const [drafts, setDrafts] = useState<Record<string, string>>({});
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [downloading, setDownloading] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  useEffect(() => setDraftJob(code), [code]);

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
      fetch(`/api/admin/resumes?${new URLSearchParams({ q: query, page_size: "8" })}`).then(async (response) => {
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
    if (!code || !candidateId) {
      setView(null);
      return;
    }
    let live = true;
    setLoading(true);
    setError("");
    fetch(`/api/admin/resume-update?${new URLSearchParams({ code, candidate_id: candidateId })}`).then(async (response) => {
      if (!live) return;
      if (response.status === 401) {
        router.push("/admin/login");
        return;
      }
      if (!response.ok) {
        setError("This résumé and job could not be opened.");
        setView(null);
        return;
      }
      const data = (await response.json()) as UpdateView;
      setView(data);
      setDrafts(Object.fromEntries(data.missing.map((item) => [item.line, item.justification || ""])));
      setPicked({
        id: data.candidate.id,
        full_name: data.candidate.full_name,
        original_filename: data.candidate.original_filename,
        email: null,
      });
    }).finally(() => {
      if (live) setLoading(false);
    });
    return () => {
      live = false;
    };
  }, [code, candidateId, router]);

  const dirty = useMemo(() => {
    if (!view) return false;
    return view.missing.some((item) => (drafts[item.line] || "") !== (item.justification || ""));
  }, [view, drafts]);

  const written = view?.missing.filter((item) => (drafts[item.line] || "").trim().length >= 20).length ?? 0;

  function openPair(nextJob: string, nextCandidate: string) {
    setMessage("");
    setError("");
    router.push(`/admin/resume-update?${new URLSearchParams({ job: nextJob, candidate: nextCandidate })}`);
  }

  async function save() {
    if (!view) return;
    setSaving(true);
    setError("");
    setMessage("");
    try {
      const response = await fetch("/api/admin/resume-update", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          requisition_code: view.job.requisition_code,
          candidate_id: view.candidate.id,
          items: view.missing.map((item) => ({ line: item.line, justification: drafts[item.line] || "" })),
        }),
      });
      const data = await response.json().catch(() => ({}));
      if (response.status === 401) {
        router.push("/admin/login");
        return;
      }
      if (!response.ok) {
        setError(typeof data.detail === "string" ? data.detail : "The justifications were not saved.");
        return;
      }
      setView(data);
      setDrafts(Object.fromEntries((data.missing || []).map((item: Missing) => [item.line, item.justification || ""])));
      setMessage(data.complete ? "Saved. The updated résumé is ready to download." : "Saved. Finish every missing requirement before downloading.");
    } catch {
      setError("The justifications were not saved.");
    } finally {
      setSaving(false);
    }
  }

  async function download() {
    if (!view?.complete || dirty) return;
    setDownloading(true);
    setError("");
    try {
      const response = await fetch(`/api/admin/resume-update/file?${new URLSearchParams({ code: view.job.requisition_code, candidate_id: view.candidate.id })}`);
      if (response.status === 401) {
        router.push("/admin/login");
        return;
      }
      if (!response.ok) {
        const data = await response.json().catch(() => ({}));
        setError(typeof data.detail === "string" ? data.detail : "The updated résumé could not be built.");
        return;
      }
      const blob = await response.blob();
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `${view.candidate.full_name || "resume"} - ${view.job.requisition_code} - updated.docx`;
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(url);
    } catch {
      setError("The updated résumé could not be built.");
    } finally {
      setDownloading(false);
    }
  }

  const personLabel = picked?.full_name || picked?.original_filename || "Search résumés";

  return (
    <div className="flex flex-col gap-5">
      <div>
        <BackButton fallback="/admin/review" />
        <h1 className="page-title mt-2">Update a résumé</h1>
        <p className="page-lead">
          Write a justification for each requirement this résumé does not cover. Admins and recruiters can save the notes and download a résumé that includes them. The file the candidate uploaded stays as it is.
        </p>
      </div>

      <div className="grid gap-3 sm:grid-cols-2">
        <label className="text-sm">
          Job
          <select
            aria-label="Job"
            value={draftJob}
            onChange={(event) => {
              setDraftJob(event.target.value);
              if (candidateId && event.target.value) openPair(event.target.value, candidateId);
            }}
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
          Résumé
          <input
            aria-label="Résumé"
            value={picked && !query ? personLabel : query}
            onChange={(event) => {
              setPicked(null);
              setQuery(event.target.value);
            }}
            placeholder="Search by name or email"
            className="field mt-1"
          />
          {hits.length > 0 && (
            <ul className="absolute z-10 mt-1 w-full overflow-hidden rounded-md border border-line bg-card shadow-lg">
              {hits.map((hit) => (
                <li key={hit.id}>
                  <button
                    type="button"
                    className="block w-full px-3 py-2 text-left hover:bg-desk"
                    onClick={() => {
                      setPicked(hit);
                      setHits([]);
                      setQuery("");
                      if (draftJob) openPair(draftJob, hit.id);
                    }}
                  >
                    <span className="block text-sm">{hit.full_name || hit.original_filename || "Unnamed résumé"}</span>
                    <span className="block text-xs text-ink/55">{hit.email || ""}</span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>

      {error && <p className="text-sm text-red-700">{error}</p>}
      {loading && <p className="text-sm">Reading the missing requirements…</p>}

      {view && !loading && view.missing.length === 0 && (
        <section className="panel p-4">
          <h2 className="font-serif text-xl">{view.candidate.full_name || "This résumé"}</h2>
          <p className="mt-2 text-sm text-ink/70">
            Every listed requirement for {view.job.requisition_code} is already on this résumé. There is nothing to justify.
          </p>
          {view.has_file && (
            <a href={resumeFileUrl(view.candidate.id, true)} className="mt-3 inline-flex items-center gap-1 text-sm font-medium text-pine hover:underline">
              <Download className="size-4" /> Download the original résumé
            </a>
          )}
        </section>
      )}

      {view && !loading && view.missing.length > 0 && (
        <section className="panel flex flex-col gap-4 p-4">
          <div className="flex flex-wrap items-end justify-between gap-3">
            <div>
              <Link href={`/admin/review?job=${encodeURIComponent(view.job.requisition_code)}&candidate=${view.candidate.id}`} className="font-mono text-sm text-pine hover:underline">
                {view.job.requisition_code}
              </Link>
              <h2 className="font-serif text-2xl">{view.candidate.full_name || "Unnamed résumé"}</h2>
              <p className="text-sm text-ink/65">
                {view.job.title || "Untitled job"} · {written} of {view.missing.length} justifications written
                {view.updated_by ? ` · last saved by ${view.updated_by}` : ""}
              </p>
            </div>
            <div className="flex flex-wrap gap-2">
              {view.has_file && (
                <Button asChild variant="outline" size="sm">
                  <a href={resumeFileUrl(view.candidate.id, true)}>
                    <Download /> Original
                  </a>
                </Button>
              )}
              <Button type="button" variant="outline" size="sm" onClick={save} disabled={saving || !dirty}>
                <FilePenLine /> {saving ? "Saving…" : "Save"}
              </Button>
              <Button type="button" size="sm" onClick={download} disabled={downloading || dirty || !view.complete}>
                <Download /> {downloading ? "Building…" : "Download updated résumé"}
              </Button>
            </div>
          </div>
          {message && <p className="text-sm text-pine">{message}</p>}
          {dirty && <p className="text-sm text-ink/60">Save before downloading so the file matches what is on screen.</p>}
          {!dirty && !view.complete && <p className="text-sm text-ink/60">Each missing requirement needs a full sentence before the updated résumé can be downloaded.</p>}
          <ul className="flex flex-col gap-4">
            {view.missing.map((item) => (
              <li key={item.line}>
                <label className="block text-sm">
                  <span className="flex flex-wrap items-center gap-2">
                    <span className="rounded-full bg-desk px-2 py-0.5 text-[10px] font-medium uppercase tracking-wide text-ink/55">{item.kind}</span>
                    <span className="font-medium">{item.line}</span>
                  </span>
                  <textarea
                    value={drafts[item.line] || ""}
                    onChange={(event) => setDrafts((current) => ({ ...current, [item.line]: event.target.value }))}
                    rows={3}
                    placeholder="Explain how this person meets the requirement, or why the gap is acceptable."
                    className="field mt-2 min-h-24"
                    aria-label={`Justification for ${item.line}`}
                  />
                </label>
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}
