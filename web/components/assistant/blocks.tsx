"use client";

import { useState } from "react";
import Link from "next/link";
import { Check, Copy, Download, ExternalLink, X } from "lucide-react";

import { copyText } from "@/components/candidate-mail";
import { StageBadge } from "@/components/stage-badge";
import { downloadCsv } from "@/lib/csv";
import type { Block, CandidateRow, JobRow, RankedRow, SubmissionRow } from "@/lib/assistant";
import { money } from "@/lib/assistant";

const PREVIEW = 6;

function Shell({ title, total, actions, children }: { title: string; total?: number; actions?: React.ReactNode; children: React.ReactNode }) {
  return (
    <section className="overflow-hidden rounded-xl border border-line bg-white">
      <header className="flex items-center gap-2 border-b border-line bg-desk/60 px-3 py-2">
        <h4 className="min-w-0 flex-1 truncate text-xs font-semibold text-ink/80" title={title}>
          {title}
        </h4>
        {total != null && <span className="rounded-full bg-ink/5 px-2 py-0.5 text-[11px] font-medium text-ink/60">{total}</span>}
        {actions}
      </header>
      {children}
    </section>
  );
}

function IconAction({ label, onClick, children }: { label: string; onClick: () => void; children: React.ReactNode }) {
  return (
    <button
      type="button"
      onClick={onClick}
      title={label}
      aria-label={label}
      className="rounded-md p-1 text-ink/50 transition hover:bg-ink/5 hover:text-ink"
    >
      {children}
    </button>
  );
}

function CopyEmails({ rows }: { rows: { email: string | null }[] }) {
  const [done, setDone] = useState(false);
  const emails = [...new Set(rows.map((row) => (row.email || "").trim().toLowerCase()).filter((email) => email.includes("@")))];
  if (!emails.length) return null;
  return (
    <IconAction
      label={`Copy ${emails.length} email${emails.length === 1 ? "" : "s"}`}
      onClick={() => {
        copyText(emails.join(", "));
        setDone(true);
        setTimeout(() => setDone(false), 1500);
      }}
    >
      {done ? <Check className="size-3.5 text-emerald-600" /> : <Copy className="size-3.5" />}
    </IconAction>
  );
}

function More({ total, open, toggle }: { total: number; open: boolean; toggle: () => void }) {
  if (total <= PREVIEW) return null;
  return (
    <button type="button" onClick={toggle} className="w-full border-t border-line px-3 py-1.5 text-left text-xs font-medium text-pine hover:bg-desk/60">
      {open ? "Show fewer" : `Show all ${total}`}
    </button>
  );
}

function CandidatesBlock({ block }: { block: Extract<Block, { type: "candidates" }> }) {
  const [open, setOpen] = useState(false);
  const rows = open ? block.rows : block.rows.slice(0, PREVIEW);
  return (
    <Shell
      title={block.title}
      total={block.total}
      actions={
        <>
          <CopyEmails rows={block.rows} />
          <IconAction
            label="Download CSV"
            onClick={() =>
              downloadCsv(
                "candidates.csv",
                ["Name", "Email", "Location", "Titles", "Skills", "Clearance"],
                block.rows.map((row) => [row.name, row.email, row.location, (row.titles || []).join("; "), (row.skills || []).join("; "), row.clearance]),
              )
            }
          >
            <Download className="size-3.5" />
          </IconAction>
        </>
      }
    >
      {block.rows.length === 0 ? (
        <p className="px-3 py-3 text-xs text-ink/55">No one matched.</p>
      ) : (
        <ul className="divide-y divide-line">
          {rows.map((row: CandidateRow) => (
            <li key={row.id} className="px-3 py-2">
              <div className="flex items-baseline gap-2">
                <Link href={`/admin/candidates/${row.id}`} className="truncate text-sm font-medium text-ink hover:text-pine hover:underline">
                  {row.name}
                </Link>
                {row.clearance && <span className="shrink-0 rounded bg-pine/10 px-1.5 text-[10px] font-semibold uppercase tracking-wide text-pine-deep">{row.clearance}</span>}
                <span className="ml-auto shrink-0 text-[11px] text-ink/50">{row.location || "No location"}</span>
              </div>
              {(row.titles?.length || row.skills?.length) ? (
                <p className="mt-0.5 truncate text-[11px] text-ink/55">
                  {[row.titles?.[0], (row.skills || []).slice(0, 5).join(", ")].filter(Boolean).join(" · ")}
                </p>
              ) : null}
            </li>
          ))}
        </ul>
      )}
      {block.unknown_location ? (
        <p className="border-t border-line px-3 py-1.5 text-[11px] text-ink/50">
          {block.unknown_location} more match the skills but have no location on file.
        </p>
      ) : null}
      <More total={block.rows.length} open={open} toggle={() => setOpen(!open)} />
    </Shell>
  );
}

function pctTone(value: number | null, meets: boolean) {
  if (meets) return "bg-emerald-50 text-emerald-700 border-emerald-200";
  if (value != null && value >= 75) return "bg-amber-50 text-amber-700 border-amber-200";
  return "bg-ink/5 text-ink/60 border-line";
}

function RankedBlock({ block }: { block: Extract<Block, { type: "ranked" }> }) {
  const [open, setOpen] = useState(false);
  const rows = open ? block.rows : block.rows.slice(0, PREVIEW);
  return (
    <Shell
      title={block.title}
      total={block.total}
      actions={
        <>
          <CopyEmails rows={block.rows} />
          <IconAction
            label="Download CSV"
            onClick={() =>
              downloadCsv(
                `${block.code}-fits.csv`,
                ["Name", "Email", "Location", "Mandatory %", "Mandatory", "Desired", "Meets bar"],
                block.rows.map((row) => [row.name, row.email, row.location, row.mandatory_pct, row.mandatory, row.desired, row.meets_bar ? "yes" : "no"]),
              )
            }
          >
            <Download className="size-3.5" />
          </IconAction>
        </>
      }
    >
      {block.rows.length === 0 ? (
        <p className="px-3 py-3 text-xs text-ink/55">No résumé covers at least half of the mandatory skills.</p>
      ) : (
        <ul className="divide-y divide-line">
          {rows.map((row: RankedRow) => (
            <li key={row.id} className="flex items-center gap-2 px-3 py-2">
              <span className={`w-12 shrink-0 rounded-md border px-1 py-0.5 text-center text-xs font-semibold tabular-nums ${pctTone(row.mandatory_pct, row.meets_bar)}`}>
                {row.mandatory_pct == null ? "–" : `${row.mandatory_pct}%`}
              </span>
              <div className="min-w-0 flex-1">
                <Link href={`/admin/candidates/${row.id}`} className="block truncate text-sm font-medium text-ink hover:text-pine hover:underline">
                  {row.name}
                </Link>
                <p className="truncate text-[11px] text-ink/50">
                  {row.location || "No location"} · mandatory {row.mandatory} · desired {row.desired}
                </p>
              </div>
              <Link href={`/admin/review?job=${block.code}&candidate=${row.id}`} className="shrink-0 text-[11px] font-medium text-pine hover:underline">
                Review
              </Link>
            </li>
          ))}
        </ul>
      )}
      <More total={block.rows.length} open={open} toggle={() => setOpen(!open)} />
    </Shell>
  );
}

function JobsBlock({ block }: { block: Extract<Block, { type: "jobs" }> }) {
  const [open, setOpen] = useState(false);
  const rows = open ? block.rows : block.rows.slice(0, PREVIEW);
  return (
    <Shell title={block.title} total={block.total}>
      {block.rows.length === 0 ? (
        <p className="px-3 py-3 text-xs text-ink/55">No job matched.</p>
      ) : (
        <ul className="divide-y divide-line">
          {rows.map((row: JobRow) => (
            <li key={row.code} className="px-3 py-2">
              <div className="flex items-baseline gap-2">
                <Link href={`/admin/jobs/${row.code}`} className="shrink-0 font-mono text-xs font-semibold text-pine hover:underline">
                  {row.code}
                </Link>
                <span className="truncate text-sm text-ink">{row.title}</span>
                {row.posting_url && (
                  <a href={row.posting_url} target="_blank" rel="noopener noreferrer" title="Posting" className="ml-auto shrink-0 text-ink/40 hover:text-pine">
                    <ExternalLink className="size-3.5" />
                  </a>
                )}
              </div>
              <p className="mt-0.5 truncate text-[11px] text-ink/55">
                {[row.location, row.status !== "open" ? row.status : null, row.needs_review ? "needs review" : null, row.submissions ? `${row.submissions} submitted` : null, row.must_have.slice(0, 4).join(", ")]
                  .filter(Boolean)
                  .join(" · ")}
              </p>
            </li>
          ))}
        </ul>
      )}
      <More total={block.rows.length} open={open} toggle={() => setOpen(!open)} />
    </Shell>
  );
}

function SubmissionsBlock({ block }: { block: Extract<Block, { type: "submissions" }> }) {
  const [open, setOpen] = useState(false);
  const rows = open ? block.rows : block.rows.slice(0, PREVIEW);
  return (
    <Shell title={block.title} total={block.total}>
      {block.rows.length === 0 ? (
        <p className="px-3 py-3 text-xs text-ink/55">No submissions.</p>
      ) : (
        <ul className="divide-y divide-line">
          {rows.map((row: SubmissionRow) => (
            <li key={row.id} className="flex items-center gap-2 px-3 py-2">
              <div className="min-w-0 flex-1">
                <Link href={`/admin/submissions/${row.id}`} className="block truncate text-sm font-medium text-ink hover:text-pine hover:underline">
                  {row.candidate}
                </Link>
                <p className="truncate text-[11px] text-ink/55">
                  <Link href={`/admin/jobs/${row.code}`} className="font-mono text-pine hover:underline">
                    {row.code}
                  </Link>{" "}
                  {row.title}
                  {row.salary_usd ? ` · ${money(row.salary_usd)}` : ""}
                </p>
              </div>
              <StageBadge stage={row.stage_key} label={row.stage} />
            </li>
          ))}
        </ul>
      )}
      <More total={block.rows.length} open={open} toggle={() => setOpen(!open)} />
    </Shell>
  );
}

function StatsBlock({ block }: { block: Extract<Block, { type: "stats" }> }) {
  return (
    <Shell
      title={block.title}
      actions={
        block.href ? (
          <Link href={block.href} className="text-[11px] font-medium text-pine hover:underline">
            Open
          </Link>
        ) : null
      }
    >
      <div className="grid grid-cols-2 gap-px bg-line">
        {block.items.map((item) => {
          const body = (
            <>
              <span className="block text-lg font-semibold tabular-nums text-ink">{item.value.toLocaleString("en-US")}</span>
              <span className="block text-[11px] text-ink/55">{item.label}</span>
            </>
          );
          return item.href ? (
            <Link key={item.label} href={item.href} className="bg-white px-3 py-2 transition hover:bg-desk/60">
              {body}
            </Link>
          ) : (
            <div key={item.label} className="bg-white px-3 py-2">
              {body}
            </div>
          );
        })}
      </div>
    </Shell>
  );
}

function Chips({ items, tone }: { items: string[]; tone: "hit" | "miss" }) {
  if (!items?.length) return <span className="text-[11px] text-ink/40">None</span>;
  return (
    <div className="flex flex-wrap gap-1">
      {items.map((item) => (
        <span
          key={item}
          className={`inline-flex max-w-full items-center gap-1 truncate rounded-md border px-1.5 py-0.5 text-[11px] ${
            tone === "hit" ? "border-emerald-200 bg-emerald-50 text-emerald-800" : "border-rose-200 bg-rose-50 text-rose-800"
          }`}
          title={item}
        >
          {tone === "hit" ? <Check className="size-3 shrink-0" /> : <X className="size-3 shrink-0" />}
          <span className="truncate">{item}</span>
        </span>
      ))}
    </div>
  );
}

function FitBlock({ block }: { block: Extract<Block, { type: "fit" }> }) {
  const fit = block.fit;
  return (
    <Shell
      title={`${fit.candidate} · ${fit.code} ${fit.title || ""}`}
      actions={
        <Link href={`/admin/review?job=${fit.code}&candidate=${fit.candidate_id}`} className="text-[11px] font-medium text-pine hover:underline">
          Review
        </Link>
      }
    >
      <div className="space-y-2 px-3 py-2.5">
        <div className="flex items-center gap-2">
          <span className={`rounded-md border px-2 py-0.5 text-sm font-semibold tabular-nums ${pctTone(fit.mandatory_pct, fit.meets_bar)}`}>
            {fit.mandatory_pct == null ? "–" : `${fit.mandatory_pct}%`}
          </span>
          <span className="text-xs text-ink/60">
            Mandatory {fit.mandatory} · desired {fit.desired} · {fit.meets_bar ? "meets the bar" : "below the bar"}
          </span>
        </div>
        <div>
          <p className="mb-1 text-[11px] font-semibold uppercase tracking-wide text-ink/45">Mandatory matched</p>
          <Chips items={fit.mandatory_matched} tone="hit" />
        </div>
        <div>
          <p className="mb-1 text-[11px] font-semibold uppercase tracking-wide text-ink/45">Mandatory missing</p>
          <Chips items={fit.mandatory_missing} tone="miss" />
        </div>
        {(fit.title_tools_missing?.length || fit.role_conflict?.length) ? (
          <p className="text-[11px] text-rose-700">
            {[...(fit.title_tools_missing || []), ...(fit.role_conflict || [])].join(", ")} not shown on the résumé.
          </p>
        ) : null}
      </div>
    </Shell>
  );
}

function Fact({ label, value }: { label: string; value: React.ReactNode }) {
  if (value == null || value === "") return null;
  return (
    <div className="flex gap-2 text-xs">
      <dt className="w-20 shrink-0 text-ink/45">{label}</dt>
      <dd className="min-w-0 flex-1 text-ink/80">{value}</dd>
    </div>
  );
}

function ProfileBlock({ block }: { block: Extract<Block, { type: "profile" }> }) {
  const c = block.candidate;
  return (
    <Shell
      title={c.name || "Candidate"}
      actions={
        <Link href={`/admin/candidates/${c.id}`} className="text-[11px] font-medium text-pine hover:underline">
          Open
        </Link>
      }
    >
      <dl className="space-y-1 px-3 py-2.5">
        <Fact label="Email" value={c.email} />
        <Fact label="Location" value={c.location} />
        <Fact label="Titles" value={(c.titles || []).slice(0, 3).join(", ")} />
        <Fact label="Clearance" value={[c.clearance, c.polygraph !== "Not on file" ? c.polygraph : null].filter(Boolean).join(" · ")} />
        <Fact label="Skills" value={(c.skills || []).slice(0, 12).join(", ")} />
        <Fact
          label="Best jobs"
          value={(c.best_matching_jobs || []).slice(0, 4).map((job: any) => (
            <Link key={job.code} href={`/admin/review?job=${job.code}&candidate=${c.id}`} className="mr-2 font-mono text-pine hover:underline">
              {job.code}
              {job.mandatory_pct != null ? ` ${Math.round(job.mandatory_pct * 100)}%` : ""}
            </Link>
          ))}
        />
        <Fact
          label="Submitted"
          value={(c.submissions || []).map((row: any) => (
            <Link key={row.id} href={`/admin/submissions/${row.id}`} className="mr-2 text-pine hover:underline">
              {row.code} ({row.stage})
            </Link>
          ))}
        />
      </dl>
    </Shell>
  );
}

function JobBlock({ block }: { block: Extract<Block, { type: "job" }> }) {
  const job = block.job;
  return (
    <Shell
      title={`${job.code} · ${job.title || ""}`}
      actions={
        <>
          {job.posting_url && (
            <a href={job.posting_url} target="_blank" rel="noopener noreferrer" className="text-ink/40 hover:text-pine" title="Posting">
              <ExternalLink className="size-3.5" />
            </a>
          )}
          <Link href={`/admin/jobs/${job.code}`} className="text-[11px] font-medium text-pine hover:underline">
            Open
          </Link>
        </>
      }
    >
      <dl className="space-y-1 px-3 py-2.5">
        <Fact label="Location" value={job.location} />
        <Fact label="Status" value={job.status + (job.needs_review ? " · needs review" : "")} />
        <Fact label="Clearance" value={[job.clearance_required, job.polygraph_required].filter(Boolean).join(" · ")} />
        <Fact label="Must have" value={(job.must_have_skills || []).join(", ")} />
        <Fact label="Nice" value={(job.nice_to_have_skills || []).join(", ")} />
        <Fact
          label="Submitted"
          value={(job.submissions || []).map((row: any) => (
            <Link key={row.id} href={`/admin/submissions/${row.id}`} className="mr-2 text-pine hover:underline">
              {row.candidate} ({row.stage})
            </Link>
          ))}
        />
      </dl>
    </Shell>
  );
}

function SubmissionBlock({ block }: { block: Extract<Block, { type: "submission" }> }) {
  const s = block.submission;
  return (
    <Shell
      title={`${s.candidate} · ${s.code}`}
      actions={
        <Link href={`/admin/submissions/${s.id}`} className="text-[11px] font-medium text-pine hover:underline">
          Open
        </Link>
      }
    >
      <dl className="space-y-1 px-3 py-2.5">
        <Fact label="Stage" value={s.stage} />
        <Fact label="Salary" value={money(s.salary_usd)} />
        <Fact label="Job" value={`${s.code} ${s.title || ""}`} />
        <Fact label="Since" value={s.created_at} />
      </dl>
      {s.history?.length ? (
        <ol className="space-y-0.5 border-t border-line px-3 py-2 text-[11px] text-ink/60">
          {s.history.slice(-5).map((event: any, index: number) => (
            <li key={index}>
              <span className="tabular-nums text-ink/40">{event.at}</span> {event.from ? `${event.from} → ` : ""}
              {event.to || event.kind}
              {event.note ? ` · ${event.note}` : ""}
            </li>
          ))}
        </ol>
      ) : null}
    </Shell>
  );
}

export function ResultBlock({ block }: { block: Block }) {
  switch (block.type) {
    case "candidates":
      return <CandidatesBlock block={block} />;
    case "ranked":
      return <RankedBlock block={block} />;
    case "jobs":
      return <JobsBlock block={block} />;
    case "submissions":
      return <SubmissionsBlock block={block} />;
    case "stats":
      return <StatsBlock block={block} />;
    case "fit":
      return <FitBlock block={block} />;
    case "profile":
      return <ProfileBlock block={block} />;
    case "job":
      return <JobBlock block={block} />;
    case "submission":
      return <SubmissionBlock block={block} />;
    default:
      return null;
  }
}
