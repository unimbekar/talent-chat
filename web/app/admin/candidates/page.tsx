"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";

import { CandidateMailBar, selectedEmails, shown } from "@/components/candidate-mail";
import { IngestProgress, IngestProgressView } from "@/components/ingest-progress";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { resumeFileUrl } from "@/lib/pipeline";

type CandidateRow = {
  id: string;
  full_name: string | null;
  email: string | null;
  location: string | null;
  original_filename: string | null;
  has_file: boolean;
  status: string;
  titles: string[];
  skills: string[];
};

type Page = {
  candidates: CandidateRow[];
  total: number;
  page: number;
  page_size: number;
};

type Scan = {
  people: number;
  older: number;
  ignored: number;
  preview: { label: string; file: string; older: number }[];
};

type Progress = IngestProgress & {
  older: number;
  ignored: number;
};

const PAGE_SIZE = 25;

export default function CandidatesPage() {
  const router = useRouter();
  const [query, setQuery] = useState("");
  const [category, setCategory] = useState("");
  const [copied, setCopied] = useState("");
  const [allEmails, setAllEmails] = useState("");
  const [allEmailCount, setAllEmailCount] = useState(0);
  const [emailBusy, setEmailBusy] = useState(false);
  const [page, setPage] = useState(1);
  const [screen, setScreen] = useState<Page | null>(null);
  const [scan, setScan] = useState<Scan | null>(null);
  const [progress, setProgress] = useState<Progress | null>(null);
  const [error, setError] = useState("");
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [copyNote, setCopyNote] = useState("");

  useEffect(() => {
    const handle = window.setTimeout(() => {
      const params = new URLSearchParams({
        q: query,
        category,
        page: String(page),
        page_size: String(PAGE_SIZE),
      });
      fetch(`/api/admin/resumes?${params}`).then(async (response) => {
        if (response.status === 401) {
          router.push("/admin/login");
          return;
        }
        if (!response.ok) {
          setError("Could not load candidates.");
          return;
        }
        setError("");
        setScreen(await response.json());
      });
    }, 200);
    return () => window.clearTimeout(handle);
  }, [query, category, page, router, progress?.done, progress?.finished]);

  useEffect(() => {
    setSelected(new Set());
    setCopyNote("");
  }, [query, category, page]);

  function copyText(value: string, label: string) {
    const area = document.createElement("textarea");
    area.value = value;
    document.body.appendChild(area);
    area.select();
    document.execCommand("copy");
    area.remove();
    if (navigator.clipboard?.writeText) {
      void navigator.clipboard.writeText(value).catch(() => undefined);
    }
    setCopied(label);
  }

  useEffect(() => {
    if (!progress?.running) return;
    const handle = window.setInterval(() => {
      fetch("/api/admin/ingest/status").then(async (response) => {
        if (response.ok) setProgress(await response.json());
      });
    }, 500);
    return () => window.clearInterval(handle);
  }, [progress?.running]);

  async function copyAllEmails() {
    setEmailBusy(true);
    setError("");
    try {
      const response = await fetch("/api/admin/candidates/emails");
      if (response.status === 401) {
        router.push("/admin/login");
        return;
      }
      const data = await response.json();
      if (!response.ok) {
        setError(data.detail || "Could not load email addresses.");
        return;
      }
      const list = data.emails || "";
      setAllEmails(list);
      setAllEmailCount(data.count || 0);
      if (!list) {
        setError("No email addresses are on file.");
        return;
      }
      copyText(list, "all");
    } catch {
      setError("Could not load email addresses.");
    } finally {
      setEmailBusy(false);
    }
  }

  async function scanFolder() {
    setError("");
    const response = await fetch("/api/admin/ingest/scan");
    if (response.status === 401) {
      router.push("/admin/login");
      return;
    }
    const data = await response.json();
    if (!response.ok) {
      setError(data.detail || "The résumé folder could not be read.");
      return;
    }
    setScan(data);
  }

  async function startImport() {
    setError("");
    const response = await fetch("/api/admin/ingest/start", { method: "POST" });
    const data = await response.json();
    if (!response.ok) {
      setError(data.detail || "Import did not start.");
      return;
    }
    setProgress({
      running: true,
      finished: false,
      total: scan?.people || 0,
      done: 0,
      imported: 0,
      already: 0,
      failed: 0,
      older: scan?.older || 0,
      ignored: scan?.ignored || 0,
      current: "Starting",
      errors: [],
    });
  }

  const total = screen?.total || 0;
  const pages = Math.max(1, Math.ceil(total / PAGE_SIZE));
  const from = total === 0 ? 0 : (page - 1) * PAGE_SIZE + 1;
  const to = Math.min(page * PAGE_SIZE, total);

  return (
    <div className="flex flex-col gap-5">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="page-title">Candidates</h1>
          <p className="page-lead">Latest résumé on file for each person. Confirm a profile from Match when you want job scores.</p>
        </div>
        <p className="text-sm text-ink/60">{total === 0 ? "No one on file yet" : `${total} on file`}</p>
      </div>

      <section className="panel p-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h2 className="font-serif text-xl">Import from the Candidates folder</h2>
            <p className="mt-1 max-w-2xl text-sm text-ink/70">
              Reads the mounted résumé folder and keeps the newest PDF, DOC, DOCX, or TXT for each person. Older copies, offer letters, and invoices stay out.
            </p>
          </div>
          <div className="flex gap-2">
            <Button type="button" variant="outline" onClick={scanFolder} disabled={progress?.running}>
              Scan folder
            </Button>
            <Button type="button" onClick={startImport} disabled={!scan || progress?.running}>
              {progress?.running ? "Importing…" : "Import latest"}
            </Button>
          </div>
        </div>
        {scan && (
          <p className="mt-3 text-sm">
            {scan.people} people, {scan.older} older copies left out, {scan.ignored} other files skipped.
          </p>
        )}
        {scan && scan.preview.length > 0 && (
          <ul className="mt-2 flex flex-wrap gap-2 text-xs text-ink/70">
            {scan.preview.map((item) => (
              <li key={item.file} className="rounded-full bg-desk px-2 py-1">
                {item.label}
              </li>
            ))}
          </ul>
        )}
        {progress && (progress.running || progress.finished) && (
          <div className="mt-4">
            <IngestProgressView progress={progress} />
          </div>
        )}
      </section>

      <div className="grid gap-3 sm:grid-cols-2">
        <label className="text-sm">
          Search by name, skill, city, or file
          <Input
            value={query}
            onChange={(event) => {
              setQuery(event.target.value);
              setPage(1);
            }}
            placeholder="Start typing, for example Aur or Java"
            className="mt-1"
            autoComplete="off"
          />
        </label>
        <label className="text-sm">
          Category
          <Input
            value={category}
            onChange={(event) => {
              setCategory(event.target.value);
              setPage(1);
            }}
            placeholder="Software Tester, Cybersecurity Engineer"
            className="mt-1"
            autoComplete="off"
          />
        </label>
      </div>
      <div className="flex flex-col gap-3">
        <div className="flex flex-wrap items-center gap-3">
          <Button type="button" onClick={copyAllEmails} disabled={emailBusy}>
            {emailBusy ? "Collecting emails…" : "Copy all candidate emails"}
          </Button>
          {copied === "all" && <span className="text-sm text-pine">Copied {allEmailCount} addresses</span>}
          {screen && screen.candidates.some((candidate) => candidate.email) && (
            <Button
              type="button"
              variant="outline"
              onClick={() =>
                copyText(
                  screen.candidates
                    .map((candidate) => candidate.email)
                    .filter((email): email is string => Boolean(email))
                    .join("\n"),
                  "page",
                )
              }
            >
              Copy emails on this page
            </Button>
          )}
          {copied === "page" && <span className="text-sm text-pine">Copied</span>}
          <CandidateMailBar
            total={screen?.candidates.length || 0}
            selectedCount={(screen?.candidates || []).filter((candidate) => selected.has(candidate.id)).length}
            allSelected={(screen?.candidates ?? []).length > 0 && (screen?.candidates ?? []).every((candidate) => selected.has(candidate.id))}
            onToggleAll={() => {
              setCopied("");
              const rows = screen?.candidates || [];
              setSelected(rows.every((candidate) => selected.has(candidate.id)) ? new Set() : new Set(rows.map((candidate) => candidate.id)));
            }}
            onCopy={() => {
              const rows = screen?.candidates || [];
              const list = selectedEmails(rows, selected);
              const missing = rows.filter((candidate) => selected.has(candidate.id) && !(candidate.email || "").includes("@")).length;
              setCopyNote(missing ? `${missing} selected ${missing === 1 ? "candidate has" : "candidates have"} no email, so ${missing === 1 ? "that address was" : "those addresses were"} left out.` : "");
              if (!list) return;
              copyText(list, "selected");
            }}
            copied={copied === "selected"}
            note={copyNote}
          />
        </div>
        {allEmails && (
          <label className="text-sm">
            All candidate emails, one address each, separated by commas
            <textarea
              readOnly
              value={allEmails}
              rows={4}
              aria-label="All candidate emails"
              className="mt-1 w-full rounded-md border border-line bg-desk px-3 py-2 text-sm leading-6"
            />
          </label>
        )}
      </div>
      {error && <p className="text-sm text-red-700">{error}</p>}

      <div className="overflow-hidden panel">
        {screen && screen.candidates.length === 0 ? (
          <p className="px-4 py-8 text-sm text-ink/70">{query ? "No candidate matches that search." : "Import the folder, or upload one résumé from Match."}</p>
        ) : (
          <ul className="divide-y divide-line">
            {(screen?.candidates || []).map((candidate) => (
              <li key={candidate.id} className="flex flex-col gap-2 px-4 py-3">
                <div className="flex items-start justify-between gap-4">
                  <div className="flex min-w-0 items-start gap-3">
                    <input
                      type="checkbox"
                      className="mt-1"
                      aria-label={`Select ${candidate.full_name || "candidate"}`}
                      checked={selected.has(candidate.id)}
                      onChange={() => {
                        setCopied("");
                        setSelected((current) => {
                          const next = new Set(current);
                          if (next.has(candidate.id)) next.delete(candidate.id);
                          else next.add(candidate.id);
                          return next;
                        });
                      }}
                    />
                    <div className="min-w-0">
                    <Link href={`/admin/candidates/${candidate.id}`} className="truncate font-medium hover:text-pine">
                      {candidate.full_name || candidate.original_filename || "Unnamed résumé"}
                    </Link>
                    <p className="truncate text-xs text-ink/60">
                      {[candidate.titles?.join(", "), candidate.original_filename].filter(Boolean).join(" · ")}
                    </p>
                    <p className="text-xs text-ink/80">Email: {shown(candidate.email)}</p>
                    <p className="text-xs text-ink/80">Location: {shown(candidate.location)}</p>
                    <p className="mt-1 flex gap-3 text-xs">
                      <Link href={`/admin/match?id=${candidate.id}`} className="text-pine hover:underline">
                        Rank against jobs
                      </Link>
                      {candidate.has_file && (
                        <a href={resumeFileUrl(candidate.id, true)} className="text-pine hover:underline">
                          Download résumé
                        </a>
                      )}
                    </p>
                    {candidate.skills.length > 0 && (
                      <p className="mt-1 truncate text-xs text-ink/50">{candidate.skills.join(" · ")}</p>
                    )}
                    </div>
                  </div>
                  <span className="shrink-0 rounded-full bg-desk px-2 py-1 text-xs text-ink/70">
                    {candidate.status === "confirmed" ? "Ranked" : "Needs review"}
                  </span>
                </div>
                {candidate.email && (
                  <div className="flex flex-wrap items-center gap-2">
                    <Input readOnly value={candidate.email} aria-label={`Email for ${candidate.full_name || "candidate"}`} className="max-w-md" />
                    <Button type="button" variant="outline" size="sm" onClick={() => copyText(candidate.email || "", candidate.id)}>
                      {copied === candidate.id ? "Copied" : "Copy email"}
                    </Button>
                  </div>
                )}
              </li>
            ))}
          </ul>
        )}
      </div>

      {total > PAGE_SIZE && (
        <div className="flex items-center justify-between text-sm">
          <p className="text-ink/60">
            {from}–{to} of {total}
          </p>
          <div className="flex gap-2">
            <Button type="button" variant="outline" disabled={page <= 1} onClick={() => setPage((current) => current - 1)}>
              Previous
            </Button>
            <Button type="button" variant="outline" disabled={page >= pages} onClick={() => setPage((current) => current + 1)}>
              Next
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}
