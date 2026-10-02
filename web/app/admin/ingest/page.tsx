"use client";

import { FormEvent, useEffect, useState } from "react";
import { useRouter } from "next/navigation";

import { IngestProgress, IngestProgressView } from "@/components/ingest-progress";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

type Scan = {
  folder: string;
  people: number;
  older: number;
  ignored: number;
  preview: { label: string; file: string; older: number }[];
};

type Progress = IngestProgress & {
  older: number;
  ignored: number;
};

type Notice = { tone: "error" | "info" | "ok"; text: string };

export default function IngestPage() {
  const router = useRouter();
  const [path, setPath] = useState("/mnt/synology/janus-soft/Candidates");
  const [scan, setScan] = useState<Scan | null>(null);
  const [progress, setProgress] = useState<Progress | null>(null);
  const [notice, setNotice] = useState<Notice | null>(null);
  const [checking, setChecking] = useState(false);

  useEffect(() => {
    if (!progress?.running) return;
    const handle = window.setInterval(() => {
      fetch("/api/admin/ingest/status").then(async (response) => {
        if (!response.ok) return;
        const data = await response.json();
        setProgress(data);
        if (data.finished && !data.running) {
          setNotice(
            data.failed
              ? { tone: "info", text: `Import finished. ${data.failed} ${data.failed === 1 ? "résumé is" : "résumés are"} listed under Unparsed résumés.` }
              : { tone: "ok", text: "Import finished. The newest résumé for each person is on file." },
          );
        }
      });
    }, 500);
    return () => window.clearInterval(handle);
  }, [progress?.running]);

  async function readBody(response: Response) {
    const text = await response.text();
    if (!text) return {};
    try {
      return JSON.parse(text);
    } catch {
      return { detail: "The server did not answer in a readable form." };
    }
  }

  function detailOf(data: { detail?: unknown }): string {
    if (typeof data.detail === "string" && data.detail) return data.detail;
    return "";
  }

  async function checkFolder(event?: FormEvent) {
    event?.preventDefault();
    const folder = path.trim();
    if (!folder) {
      setNotice({ tone: "error", text: "Enter a folder path first." });
      return;
    }
    setChecking(true);
    setNotice(null);
    setScan(null);
    try {
      const response = await fetch(`/api/admin/ingest/scan?path=${encodeURIComponent(folder)}`);
      if (response.status === 401) {
        router.push("/admin/login");
        return;
      }
      const data = await readBody(response);
      if (!response.ok) {
        setNotice({ tone: "error", text: detailOf(data) || "That folder could not be read." });
        return;
      }
      setScan(data);
      setNotice({
        tone: "ok",
        text: data.people
          ? `Found ${data.people} people in ${data.folder}. Older copies and files that are not résumés stay out.`
          : `No résumés were found in ${data.folder}.`,
      });
    } catch {
      setNotice({ tone: "error", text: "The folder check did not finish." });
    } finally {
      setChecking(false);
    }
  }

  async function startImport() {
    const folder = path.trim();
    if (!folder || !scan) {
      setNotice({ tone: "error", text: "Check the folder before starting the import." });
      return;
    }
    setNotice(null);
    try {
      const response = await fetch("/api/admin/ingest/start", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ path: folder }),
      });
      if (response.status === 401) {
        router.push("/admin/login");
        return;
      }
      const data = await readBody(response);
      if (!response.ok) {
        setNotice({ tone: "error", text: detailOf(data) || "Import did not start." });
        return;
      }
      setProgress({
        running: true,
        finished: false,
        total: scan.people,
        done: 0,
        imported: 0,
        already: 0,
        failed: 0,
        older: scan.older,
        ignored: scan.ignored,
        current: "Starting",
        current_file: "",
        current_label: "",
        current_path: "",
        errors: [],
        unparsed: [],
      });
      setNotice({ tone: "info", text: "Import is running. Each person keeps the newest PDF, DOC, DOCX, or TXT." });
    } catch {
      setNotice({ tone: "error", text: "Import did not start." });
    }
  }

  return (
    <div className="flex flex-col gap-5">
      <div>
        <h1 className="font-serif text-3xl">Ingest résumés</h1>
        <p className="mt-1 max-w-2xl text-sm text-ink/70">
          Point at a folder on the résumé library. The import keeps the newest PDF, DOC, DOCX, or TXT for each person. Offer letters and invoices stay out. Nothing is emailed.
        </p>
      </div>

      <form onSubmit={checkFolder} className="rounded-xl border border-line bg-card p-4">
        <label className="block text-sm">
          Folder
          <Input
            value={path}
            onChange={(event) => {
              setPath(event.target.value);
              setScan(null);
            }}
            placeholder="/mnt/synology/janus-soft/Candidates"
            className="mt-1 font-mono"
            aria-label="Folder"
            autoComplete="off"
          />
        </label>
        <p className="mt-2 text-xs text-ink/60">
          A full path such as /mnt/synology/janus-soft/Resume-Refined, or a short name such as Upender under Candidates.
        </p>
        <div className="mt-3 flex flex-wrap gap-2">
          <Button type="submit" variant="outline" disabled={checking || progress?.running}>
            {checking ? "Checking…" : "Check folder"}
          </Button>
          <Button type="button" onClick={startImport} disabled={!scan || scan.people === 0 || progress?.running}>
            {progress?.running ? "Importing…" : "Ingest résumés"}
          </Button>
        </div>
      </form>

      {notice && <Notice tone={notice.tone} text={notice.text} />}

      {scan && (
        <section className="rounded-xl border border-line bg-card p-4 text-sm">
          <p>
            {scan.people} people · {scan.older} older copies left out · {scan.ignored} other files skipped
          </p>
          <p className="mt-1 font-mono text-xs text-ink/60">{scan.folder}</p>
          {scan.preview.length > 0 && (
            <ul className="mt-3 flex flex-wrap gap-2 text-xs text-ink/70">
              {scan.preview.map((item) => (
                <li key={item.file} className="rounded-full bg-desk px-2 py-1">
                  {item.label}
                </li>
              ))}
            </ul>
          )}
        </section>
      )}

      {progress && (progress.running || progress.finished) && <IngestProgressView progress={progress} />}
    </div>
  );
}

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
