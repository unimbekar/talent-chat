"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";

type JobRow = {
  requisition_code: string;
  title: string | null;
  location: string | null;
  status: string;
  description_source: string;
  needs_review: boolean;
  last_seen_at: string | null;
  description_note: string | null;
  detail_error: string | null;
  must_have_skills: string[];
  nice_to_have_skills: string[];
  clearance_required: string | null;
  polygraph_required: string | null;
};

type Screen = {
  crawl: { last_ok: boolean | null; last_error: string | null; last_finished_at: string | null; last_rows: number | null };
  jobs: JobRow[];
};

export default function JobsPage() {
  const router = useRouter();
  const [screen, setScreen] = useState<Screen | null>(null);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);

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

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="font-serif text-2xl">Jobs</h1>
        <Button type="button" onClick={recrawl} disabled={busy}>
          {busy ? "Recrawling…" : "Recrawl now"}
        </Button>
      </div>
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
      <div className="overflow-x-auto rounded-lg border border-line bg-card">
        <table className="w-full min-w-[640px] text-left text-sm">
          <thead className="border-b border-line text-xs uppercase tracking-wide text-ink/60">
            <tr>
              <th className="px-3 py-2">Code</th>
              <th className="px-3 py-2">Title</th>
              <th className="px-3 py-2">City</th>
              <th className="px-3 py-2">Status</th>
              <th className="px-3 py-2">Description</th>
              <th className="px-3 py-2">Review</th>
            </tr>
          </thead>
          <tbody>
            {(screen?.jobs || []).filter((job) => job.status !== "closed").map((job) => (
              <tr key={job.requisition_code} className="border-b border-line last:border-0">
                <td className="px-3 py-2 font-mono">
                  <Link href={`/admin/jobs/${job.requisition_code}`} className="text-pine underline">
                    {job.requisition_code}
                  </Link>
                </td>
                <td className="px-3 py-2">{job.title}</td>
                <td className="px-3 py-2">{job.location}</td>
                <td className="px-3 py-2">{job.status}</td>
                <td className="px-3 py-2">{job.description_note || job.description_source}</td>
                <td className="px-3 py-2">{job.needs_review ? <Badge>Needs review</Badge> : ""}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {(screen?.jobs || []).some((job) => job.status === "closed") && (
        <section className="text-sm text-ink/70">
          <h2 className="font-medium text-ink">No longer on the careers page</h2>
          <ul className="mt-2 flex flex-col gap-1">
            {screen?.jobs
              .filter((job) => job.status === "closed")
              .map((job) => (
                <li key={job.requisition_code}>
                  <Link href={`/admin/jobs/${job.requisition_code}`} className="font-mono text-pine underline">
                    {job.requisition_code}
                  </Link>{" "}
                  {job.title} · {job.location} · closed
                </li>
              ))}
          </ul>
        </section>
      )}
    </div>
  );
}
