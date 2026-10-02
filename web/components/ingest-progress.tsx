export type UnparsedResume = {
  file: string;
  reason: string;
};

export type IngestProgress = {
  running: boolean;
  finished: boolean;
  total: number;
  done: number;
  imported: number;
  already: number;
  failed: number;
  current?: string;
  current_file?: string;
  current_label?: string;
  current_path?: string;
  errors?: string[];
  unparsed?: UnparsedResume[];
};

function uniqueRows(progress: IngestProgress): UnparsedResume[] {
  const source = progress.unparsed?.length
    ? progress.unparsed
    : (progress.errors || []).map((item) => {
        const split = item.indexOf(": ");
        if (split === -1) return { file: item, reason: "Could not read this résumé." };
        return { file: item.slice(0, split), reason: item.slice(split + 2) };
      });
  const seen = new Set<string>();
  const rows: UnparsedResume[] = [];
  for (const row of source) {
    const key = row.file.trim().toLowerCase();
    if (!key || seen.has(key)) continue;
    seen.add(key);
    rows.push({ file: row.file, reason: row.reason });
  }
  return rows;
}

export function IngestProgressView({ progress }: { progress: IngestProgress }) {
  const percent = progress.total ? Math.min(100, Math.round((progress.done / progress.total) * 100)) : 0;
  const file = progress.current_file || (progress.running ? progress.current || "" : "");
  const folder = progress.current_path?.includes("/") ? progress.current_path.slice(0, progress.current_path.lastIndexOf("/")) : "";
  const person = progress.current_label && progress.current_label !== file ? progress.current_label : "";
  const unparsed = uniqueRows(progress);

  return (
    <div className="flex flex-col gap-4">
      <section className="rounded-xl border border-line bg-card p-5" role="status" aria-live="polite">
        <div className="flex items-baseline justify-between gap-4">
          <h2 className="font-serif text-xl">{progress.running ? "Reading résumés" : "Ingest complete"}</h2>
          <p className="font-mono text-sm tabular-nums text-ink/70">{percent}%</p>
        </div>
        <div className="mt-3 h-2.5 overflow-hidden rounded-full bg-desk" aria-hidden="true">
          <div className="h-full rounded-full bg-pine transition-[width] duration-300 ease-out" style={{ width: `${percent}%` }} />
        </div>
        <p className="mt-2 text-sm text-ink/60">
          {progress.done} of {progress.total}
        </p>
        {file && (
          <div className="mt-4 rounded-lg border border-line bg-[#f6f4ef] px-4 py-3">
            <p className="text-[11px] font-medium uppercase tracking-[0.14em] text-ink/45">{progress.running ? "Now reading" : "Last résumé"}</p>
            <p className="mt-1 truncate text-base font-medium text-ink" title={file}>
              {file}
            </p>
            {(person || folder) && (
              <p className="mt-0.5 truncate text-sm text-ink/60">
                {[person, folder].filter(Boolean).join(" · ")}
              </p>
            )}
          </div>
        )}
        <dl className="mt-4 grid grid-cols-3 gap-3 text-center">
          <div className="rounded-lg bg-desk px-2 py-2">
            <dt className="text-[11px] uppercase tracking-wide text-ink/45">Imported</dt>
            <dd className="mt-0.5 font-medium tabular-nums">{progress.imported}</dd>
          </div>
          <div className="rounded-lg bg-desk px-2 py-2">
            <dt className="text-[11px] uppercase tracking-wide text-ink/45">Already on file</dt>
            <dd className="mt-0.5 font-medium tabular-nums">{progress.already}</dd>
          </div>
          <div className="rounded-lg bg-desk px-2 py-2">
            <dt className="text-[11px] uppercase tracking-wide text-ink/45">Unparsed</dt>
            <dd className="mt-0.5 font-medium tabular-nums">{progress.failed}</dd>
          </div>
        </dl>
        {progress.finished && progress.failed === 0 && (
          <p className="mt-3 text-sm text-pine">The newest résumé for each person is on the Candidates page.</p>
        )}
      </section>

      {unparsed.length > 0 && (
        <section className="rounded-xl border border-amber-300 bg-amber-50 p-5">
          <div className="flex items-baseline justify-between gap-3">
            <h2 className="font-serif text-xl text-amber-950">Unparsed résumés</h2>
            <p className="text-sm tabular-nums text-amber-900">{unparsed.length}</p>
          </div>
          <p className="mt-1 text-sm text-amber-950/80">These files could not be read. Each file is listed once.</p>
          <ul className="mt-3 divide-y divide-amber-200">
            {unparsed.map((row) => (
              <li key={row.file} className="py-2">
                <p className="truncate font-medium text-amber-950" title={row.file}>
                  {row.file}
                </p>
                <p className="text-sm text-amber-950/75">{row.reason}</p>
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}
