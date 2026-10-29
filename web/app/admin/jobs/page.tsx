"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";

import { copyText } from "@/components/candidate-mail";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { useCan } from "@/lib/desk";
import { Textarea } from "@/components/ui/textarea";

type JobRow = {
  requisition_code: string;
  external_req: string | null;
  funding: string | null;
  title: string | null;
  location: string | null;
  status: string;
  close_note: string | null;
  description_source: string;
  needs_review: boolean;
  last_seen_at: string | null;
  description_note: string | null;
  source_url: string | null;
  detail_error: string | null;
  submission_count?: number;
  must_have_skills: string[];
  nice_to_have_skills: string[];
  clearance_required: string | null;
  polygraph_required: string | null;
};

type Screen = {
  crawl: { last_ok: boolean | null; last_error: string | null; last_finished_at: string | null; last_rows: number | null };
  jobs: JobRow[];
};

function fundingLabel(job: { funding: string | null }): string {
  return job.funding === "proposed" ? "Proposed" : "Funded";
}

function jobShareLabel(job: JobRow): string {
  return [job.requisition_code, job.title || "Untitled", job.location || ""].filter(Boolean).join(" — ");
}

/** Candidates on the internet use the public Spark address. An office or tailnet address stays on this machine. */
const PUBLIC_CAREERS = "https://spark-42c4.tail55e197.ts.net";

function isPrivateHost(host: string): boolean {
  if (host === "localhost" || host === "127.0.0.1" || host === "::1" || host === "[::1]") return true;
  if (host.startsWith("10.") || host.startsWith("192.168.")) return true;
  const second = /^172\.(\d+)\./.exec(host);
  if (second && Number(second[1]) >= 16 && Number(second[1]) <= 31) return true;
  return /^100\.(6[4-9]|[7-9]\d|1[01]\d|12[0-7])\./.test(host);
}

function candidateBase(): string {
  if (typeof window === "undefined") return PUBLIC_CAREERS;
  return isPrivateHost(window.location.hostname) ? PUBLIC_CAREERS : window.location.origin;
}

function candidateJobUrl(code: string): string {
  return `${candidateBase()}/jobs?job=${encodeURIComponent(code)}`;
}

function escapeHtml(value: string): string {
  return value.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}

async function copyJobList(jobs: JobRow[]): Promise<void> {
  const plain = jobs.map((job) => `${jobShareLabel(job)}\n${candidateJobUrl(job.requisition_code)}`).join("\n\n");
  const html =
    "<ul>" +
    jobs
      .map((job) => {
        const href = escapeHtml(candidateJobUrl(job.requisition_code));
        return `<li><a href="${href}">${escapeHtml(jobShareLabel(job))}</a></li>`;
      })
      .join("") +
    "</ul>";
  try {
    if (navigator.clipboard?.write && typeof ClipboardItem !== "undefined") {
      await navigator.clipboard.write([
        new ClipboardItem({
          "text/html": new Blob([html], { type: "text/html" }),
          "text/plain": new Blob([plain], { type: "text/plain" }),
        }),
      ]);
      return;
    }
  } catch {
    // The plain-text copy below still puts the list on the clipboard.
  }
  copyText(plain);
}

export default function JobsPage() {
  const router = useRouter();
  const canEdit = useCan("edit_jobs");
  const canDelete = useCan("delete");
  const [screen, setScreen] = useState<Screen | null>(null);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const [query, setQuery] = useState("");
  const [closing, setClosing] = useState<string | null>(null);
  const [note, setNote] = useState("");
  const [closeBusy, setCloseBusy] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState<string | null>(null);
  const [listOpen, setListOpen] = useState(false);
  const [listCopied, setListCopied] = useState(false);

  async function load() {
    const response = await fetch("/api/admin/jobs");
    if (response.status === 401) {
      router.push("/admin/login");
      return;
    }
    if (!response.ok) {
      setError("Could not load jobs.");
      return;
    }
    setScreen(await response.json());
  }

  useEffect(() => {
    load();
  }, []);

  async function recrawl() {
    setBusy(true);
    setMessage("Recrawling the careers page. This takes about a minute.");
    try {
      const response = await fetch("/api/admin/jobs/recrawl", { method: "POST" });
      const data = await response.json();
      const closed = (data.closed_codes || []).join(", ");
      if (data.last_error) {
        setMessage(data.last_error);
      } else if (data.last_ok) {
        setMessage(`Crawl loaded ${data.last_rows} rows.${closed ? ` Closed ${closed}.` : ""}`);
      } else {
        setMessage("Crawl failed.");
      }
    } catch {
      setMessage("The recrawl did not finish in the browser. The jobs list will refresh.");
    } finally {
      setBusy(false);
      await load();
    }
  }

  async function reopenJob(code: string) {
    setCloseBusy(true);
    setMessage("");
    try {
      const response = await fetch(`/api/admin/jobs/${code}/reopen`, { method: "POST" });
      if (response.status === 401) {
        router.push("/admin/login");
        return;
      }
      if (!response.ok) {
        setMessage("The job was not reopened.");
        return;
      }
      setMessage(`${code} is open again.`);
      await load();
    } catch {
      setMessage("The job was not reopened.");
    } finally {
      setCloseBusy(false);
    }
  }

  async function deleteJob(code: string) {
    setCloseBusy(true);
    setMessage("");
    try {
      const response = await fetch(`/api/admin/jobs/${code}`, { method: "DELETE" });
      const data = await response.json().catch(() => ({}));
      if (response.status === 401) {
        router.push("/admin/login");
        return;
      }
      if (!response.ok) {
        setMessage(typeof data.detail === "string" ? data.detail : "The job was not deleted.");
        return;
      }
      setConfirmDelete(null);
      setMessage(`${code} was deleted.`);
      await load();
    } catch {
      setMessage("The job was not deleted.");
    } finally {
      setCloseBusy(false);
    }
  }

  async function closeJob(code: string) {
    setCloseBusy(true);
    setMessage("");
    try {
      const response = await fetch(`/api/admin/jobs/${code}/close`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ note }),
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
      setClosing(null);
      setNote("");
      setMessage(`${code} is closed.`);
      await load();
    } catch {
      setMessage("The job was not closed.");
    } finally {
      setCloseBusy(false);
    }
  }

  const openJobs = (screen?.jobs || [])
    .filter((job) => job.status !== "closed")
    .filter((job) => {
      const haystack = `${job.requisition_code} ${job.external_req || ""} ${fundingLabel(job)} ${job.title || ""} ${job.location || ""}`.toLowerCase();
      return haystack.includes(query.trim().toLowerCase());
    });

  function closeControl(job: JobRow) {
    if (!canEdit) return null;
    if (closing !== job.requisition_code) {
      return (
        <Button
          type="button"
          variant="outline"
          onClick={() => {
            setClosing(job.requisition_code);
            setNote("");
          }}
        >
          Close
        </Button>
      );
    }
    return (
      <div className="flex w-full min-w-56 flex-col gap-2">
        <Textarea
          aria-label={`Why close ${job.requisition_code}`}
          value={note}
          rows={3}
          placeholder="Why is this job closing?"
          onChange={(event) => setNote(event.target.value)}
        />
        <div className="flex gap-2">
          <Button type="button" disabled={closeBusy || !note.trim()} onClick={() => closeJob(job.requisition_code)}>
            {closeBusy ? "Closing…" : "Confirm close"}
          </Button>
          <Button type="button" variant="outline" onClick={() => { setClosing(null); setNote(""); }}>
            Cancel
          </Button>
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="page-title">Jobs</h1>
        <div className="flex flex-wrap gap-2">
          <Button
            type="button"
            variant="outline"
            onClick={() => {
              setListCopied(false);
              setListOpen((open) => !open);
            }}
          >
            {listOpen ? "Hide job list" : "Job list for email"}
          </Button>
          {canEdit && (
            <Button type="button" onClick={recrawl} disabled={busy}>
              {busy ? "Recrawling…" : "Recrawl now"}
            </Button>
          )}
        </div>
      </div>
      {listOpen && (
        <section className="panel p-4">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <h2 className="font-serif text-xl">Jobs to send</h2>
              <p className="page-lead">
                Open postings{query.trim() ? " matching the filter" : ""}. Copy the list into an email. Each link opens that role on this site, where the candidate can apply.
              </p>
            </div>
            <Button
              type="button"
              disabled={openJobs.length === 0}
              onClick={() => {
                void copyJobList(openJobs).then(() => setListCopied(true));
              }}
            >
              {listCopied ? "Copied" : "Copy list"}
            </Button>
          </div>
          {openJobs.length === 0 ? (
            <p className="mt-3 text-sm text-ink/70">No open jobs to list.</p>
          ) : (
            <ul className="mt-3 flex list-disc flex-col gap-2 pl-5 text-sm">
              {openJobs.map((job) => (
                <li key={job.requisition_code}>
                  <a href={candidateJobUrl(job.requisition_code)} target="_blank" rel="noopener noreferrer" className="text-pine underline">
                    {jobShareLabel(job)}
                  </a>
                </li>
              ))}
            </ul>
          )}
        </section>
      )}
      {screen?.crawl.last_error && (
        <p className="rounded-md border border-red-300 bg-red-50 px-3 py-2 text-sm" data-testid="crawl-error">
          {screen.crawl.last_error}
        </p>
      )}
      {screen?.crawl.last_ok && !screen.crawl.last_error && (
        <p className="text-sm text-ink/70">Last crawl loaded {screen.crawl.last_rows} rows.</p>
      )}
      {error && <p className="text-sm text-red-700">{error}</p>}
      {message && <p className="text-sm">{message}</p>}
      <input
        value={query}
        onChange={(event) => setQuery(event.target.value)}
        placeholder="Filter by code, internal code, proposed, title, or city"
        aria-label="Filter jobs"
        className="field"
      />
      <ul className="flex flex-col gap-2 lg:hidden">
        {openJobs.map((job) => (
          <li key={job.requisition_code} className="panel p-4">
            <Link href={`/admin/jobs/${job.requisition_code}`} className="block active:opacity-70">
              <span className="flex items-center gap-2">
                <span className="font-mono text-sm text-pine">{job.requisition_code}</span>
                {job.external_req && <span className="font-mono text-sm text-ink/70">{job.external_req}</span>}
                <span className="text-xs text-ink/60">{fundingLabel(job)}</span>
                {job.needs_review && <Badge>Needs review</Badge>}
              </span>
              <span className="mt-0.5 block font-serif text-lg leading-snug">{job.title}</span>
              <span className="block text-xs text-ink/60">{job.location}</span>
            </Link>
            <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-2 text-sm">
              <Link href={`/admin/jobs/${job.requisition_code}#submissions`} className="text-pine underline">
                {job.submission_count || 0} submitted
              </Link>
              <Link href={`/admin/jobs/${job.requisition_code}#candidates`} className="text-pine underline">
                Candidates
              </Link>
              {job.source_url && (
                <a href={job.source_url} target="_blank" rel="noopener noreferrer" className="text-pine underline">
                  Posting
                </a>
              )}
              <span className={closing === job.requisition_code ? "w-full" : "ml-auto"}>{closeControl(job)}</span>
            </div>
          </li>
        ))}
      </ul>
      <div className="hidden overflow-x-auto rounded-lg border border-line bg-card lg:block">
        <table className="w-full min-w-[640px] text-left text-sm">
          <thead className="border-b border-line text-xs uppercase tracking-wide text-ink/60">
            <tr>
              <th className="px-3 py-2">Code</th>
              <th className="px-3 py-2">Internal code</th>
              <th className="px-3 py-2">Proposed / funded</th>
              <th className="px-3 py-2">Title</th>
              <th className="px-3 py-2">City</th>
              <th className="px-3 py-2">Status</th>
              <th className="px-3 py-2">Submitted</th>
              <th className="px-3 py-2">Posting</th>
              <th className="px-3 py-2">Review</th>
              {canEdit && <th className="px-3 py-2">Close</th>}
            </tr>
          </thead>
          <tbody>
            {openJobs.map((job) => (
              <tr key={job.requisition_code} className="border-b border-line last:border-0">
                <td className="px-3 py-2 font-mono">
                  <Link href={`/admin/jobs/${job.requisition_code}`} className="text-pine underline">
                    {job.requisition_code}
                  </Link>
                </td>
                <td className="px-3 py-2 font-mono whitespace-nowrap">{job.external_req || "—"}</td>
                <td className="px-3 py-2 whitespace-nowrap">{fundingLabel(job)}</td>
                <td className="px-3 py-2">{job.title}</td>
                <td className="px-3 py-2">{job.location}</td>
                <td className="px-3 py-2">{job.status}</td>
                <td className="px-3 py-2">
                  <Link href={`/admin/jobs/${job.requisition_code}#submissions`} className="text-pine underline">
                    {job.submission_count || 0}
                  </Link>
                </td>
                <td className="px-3 py-2">
                  {job.source_url ? (
                    <a href={job.source_url} target="_blank" rel="noopener noreferrer" className="whitespace-nowrap text-pine underline">
                      View on janus-soft.com
                    </a>
                  ) : (
                    <span className="text-ink/50">Not linked</span>
                  )}
                </td>
                <td className="px-3 py-2">{job.needs_review ? <Badge>Needs review</Badge> : ""}</td>
                {canEdit && <td className="px-3 py-2">{closeControl(job)}</td>}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {(screen?.jobs || []).some((job) => job.status === "closed") && (
        <section className="text-sm text-ink/70">
          <h2 className="font-medium text-ink">Closed jobs</h2>
          <ul className="mt-2 flex flex-col gap-2">
            {screen?.jobs
              .filter((job) => job.status === "closed")
              .map((job) => (
                <li key={job.requisition_code}>
                  <Link href={`/admin/jobs/${job.requisition_code}`} className="font-mono text-pine underline">
                    {job.requisition_code}
                  </Link>
                  {job.external_req ? <span className="font-mono"> {job.external_req}</span> : null}{" "}
                  {job.title} · {job.location} · {fundingLabel(job)} · closed
                  <p className="text-ink">{job.close_note || "No note was saved."}</p>
                  {(canEdit || canDelete) && (
                    <div className="mt-1 flex flex-wrap items-center gap-2">
                      {canEdit && (
                        <Button type="button" variant="outline" disabled={closeBusy} onClick={() => reopenJob(job.requisition_code)}>
                          Reopen
                        </Button>
                      )}
                      {canDelete && confirmDelete === job.requisition_code ? (
                        <>
                          <span className="text-ink">Delete {job.requisition_code}? Its submissions go with it. If the careers page still lists it, the next recrawl brings it back.</span>
                          <Button type="button" variant="danger" disabled={closeBusy} onClick={() => deleteJob(job.requisition_code)}>
                            Delete permanently
                          </Button>
                          <Button type="button" variant="outline" disabled={closeBusy} onClick={() => setConfirmDelete(null)}>
                            Cancel
                          </Button>
                        </>
                      ) : canDelete ? (
                        <Button type="button" variant="danger" disabled={closeBusy} onClick={() => setConfirmDelete(job.requisition_code)}>
                          Delete
                        </Button>
                      ) : null}
                    </div>
                  )}
                </li>
              ))}
          </ul>
        </section>
      )}
    </div>
  );
}
