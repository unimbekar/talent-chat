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
type Source = "folder" | "drive" | "s3";

export default function IngestPage() {
  const router = useRouter();
  const [library, setLibrary] = useState("/library");
  const [path, setPath] = useState("");
  const [source, setSource] = useState<Source>("folder");
  const [driveReady, setDriveReady] = useState(false);
  const [googleOn, setGoogleOn] = useState(false);
  const [s3Ready, setS3Ready] = useState(false);
  const [signedInAs, setSignedInAs] = useState("");
  const [inbox, setInbox] = useState("inbox");

  useEffect(() => {
    fetch("/api/admin/overview").then(async (response) => {
      if (response.status === 401) {
        router.push("/admin/login");
        return;
      }
      if (!response.ok) return;
      const data = await response.json();
      if (data.library_host) {
        setLibrary(data.library_host);
        setPath((current) => current || `${data.library_host}/Candidates`);
      }
    });
    fetch("/api/admin/session").then(async (response) => {
      if (!response.ok) return;
      const data = await response.json();
      setDriveReady(Boolean(data.drive));
      setGoogleOn(Boolean(data.google));
      setS3Ready(Boolean(data.s3));
      setSignedInAs(data.email || "");
      if (data.s3_prefix) setInbox(data.s3_prefix);
    });
  }, [router]);
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
      const response = await fetch(`/api/admin/ingest/scan?${new URLSearchParams({ path: folder, source })}`);
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
        body: JSON.stringify({ path: folder, source }),
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
        <h1 className="page-title">Ingest résumés</h1>
        <p className="page-lead">
          Import the newest PDF, DOC, DOCX, or TXT for each person from a server folder, a Google Drive folder, or the S3 inbox. Offer letters and invoices stay out. Nothing is emailed.
        </p>
      </div>

      <form onSubmit={checkFolder} className="panel p-4">
        <div className="flex flex-wrap gap-2" role="tablist" aria-label="Import source">
          {(
            [
              ["folder", "Server folder"],
              ["drive", "Google Drive"],
              ["s3", "Amazon S3"],
            ] as const
          ).map(([value, label]) => (
            <button
              key={value}
              type="button"
              role="tab"
              aria-selected={source === value}
              className={`rounded-full px-3 py-1 text-sm ${source === value ? "bg-ink text-white" : "bg-desk text-ink/70"}`}
              onClick={() => {
                setSource(value);
                setScan(null);
                setPath(value === "folder" ? `${library}/Candidates` : value === "s3" ? `${inbox}/` : "");
              }}
            >
              {label}
            </button>
          ))}
        </div>
        <label className="mt-4 block text-sm">
          {source === "drive" ? "Drive folder" : source === "s3" ? "S3 prefix" : "Folder"}
          <Input
            value={path}
            onChange={(event) => {
              setPath(event.target.value);
              setScan(null);
            }}
            placeholder={source === "drive" ? "https://drive.google.com/drive/folders/…" : source === "s3" ? `${inbox}/` : `${library}/Candidates`}
            className="mt-1 font-mono"
            aria-label={source === "drive" ? "Drive folder" : source === "s3" ? "S3 prefix" : "Folder"}
            autoComplete="off"
          />
        </label>
        <p className="mt-2 text-xs text-ink/60">
          {source === "drive" && (driveReady
            ? `Reads folders your Google account can open${signedInAs ? ` (${signedInAs})` : ""}.`
            : googleOn
              ? "Sign in with your janus-soft.com Google account before reading Drive."
              : "Google sign-in is not configured on this server yet.")}
          {source === "s3" && (s3Ready
            ? `Files already in s3 under ${inbox}/. originals and database dumps are not imported from here.`
            : "S3 import runs on the AWS site, where the private résumé bucket is configured.")}
          {source === "folder" && `A full path inside ${library}, or the short name of a folder under Candidates.`}
        </p>
        {source === "drive" && !driveReady && googleOn && (
          <a href="/api/admin/login/google" className="mt-2 inline-block text-sm text-pine-deep underline">
            Sign in with Google
          </a>
        )}
        <div className="mt-3 flex flex-wrap gap-2">
          <Button type="submit" variant="outline" disabled={checking || progress?.running || (source === "drive" && !driveReady) || (source === "s3" && !s3Ready)}>
            {checking ? "Checking…" : "Check folder"}
          </Button>
          <Button type="button" onClick={startImport} disabled={!scan || scan.people === 0 || progress?.running}>
            {progress?.running ? "Importing…" : "Ingest résumés"}
          </Button>
        </div>
      </form>

      {notice && <Notice tone={notice.tone} text={notice.text} />}

      {scan && (
        <section className="panel p-4 text-sm">
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
