"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Download } from "lucide-react";

import { Bars, Columns, Funnel } from "@/components/report-charts";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { money } from "@/lib/pipeline";
import { reportQuery, shiftDays, ymd, type Report } from "@/lib/reports";

const PRESETS = [
  { id: "today", label: "Today" },
  { id: "7", label: "Last 7 days" },
  { id: "30", label: "Last 30 days" },
  { id: "custom", label: "Custom" },
] as const;

function rangeFor(preset: string, today: string): { from: string; to: string } {
  if (preset === "7") return { from: shiftDays(today, -6), to: today };
  if (preset === "30") return { from: shiftDays(today, -29), to: today };
  return { from: today, to: today };
}

export default function ReportsPage() {
  const router = useRouter();
  const today = useMemo(() => ymd(new Date()), []);
  const [preset, setPreset] = useState("today");
  const [from, setFrom] = useState(today);
  const [to, setTo] = useState(today);
  const [poly, setPoly] = useState("full_scope");
  const [clearance, setClearance] = useState("");
  const [clearanceScope, setClearanceScope] = useState("all");
  const [salaryGt, setSalaryGt] = useState("");
  const [salaryScope, setSalaryScope] = useState("all");
  const [report, setReport] = useState<Report | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [exporting, setExporting] = useState("");

  const filters = useMemo(
    () => ({ from, to, poly, clearance, salaryGt, salaryScope, clearanceScope }),
    [from, to, poly, clearance, salaryGt, salaryScope, clearanceScope],
  );

  useEffect(() => {
    if (from > to) {
      setError("The end date has to be on or after the start date.");
      setLoading(false);
      return;
    }
    const amount = salaryGt.trim();
    if (amount && (!/^\d+$/.test(amount) || Number(amount) > 5_000_000)) {
      setError("Salary has to be a whole number of dollars, up to 5,000,000.");
      setLoading(false);
      return;
    }
    let cancelled = false;
    const handle = window.setTimeout(() => {
      setLoading(true);
      fetch(`/api/admin/reports?${reportQuery(filters)}`).then(async (response) => {
        if (cancelled) return;
        if (response.status === 401) {
          router.push("/admin/login");
          return;
        }
        if (!response.ok) {
          const body = await response.json().catch(() => ({}));
          setError(body?.detail?.message || "The report could not be loaded.");
          setLoading(false);
          return;
        }
        setError("");
        setReport(await response.json());
        setLoading(false);
      });
    }, 200);
    return () => {
      cancelled = true;
      window.clearTimeout(handle);
    };
  }, [filters, router, from, to, salaryGt]);

  function applyPreset(id: string) {
    setPreset(id);
    if (id === "custom") return;
    const next = rangeFor(id, today);
    setFrom(next.from);
    setTo(next.to);
  }

  async function download(format: "csv" | "xlsx", sheet: string) {
    setExporting(`${format}-${sheet}`);
    setError("");
    try {
      const response = await fetch(`/api/admin/reports/export?${reportQuery({ ...filters, format, sheet })}`);
      if (response.status === 401) {
        router.push("/admin/login");
        return;
      }
      if (!response.ok) {
        const body = await response.json().catch(() => ({}));
        setError(body?.detail?.message || "The export could not be built.");
        return;
      }
      const blob = await response.blob();
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = format === "xlsx" ? "talent-report.xlsx" : `talent-${sheet}.csv`;
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(url);
    } finally {
      setExporting("");
    }
  }

  const ingested = report?.ingested.total || 0;
  const submittedPeople = report?.ingested.also_submitted || 0;
  const conversion = ingested ? Math.round((submittedPeople / ingested) * 100) : 0;

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="page-title">Reports</h1>
          <p className="page-lead">
            Ingest, submissions, clearance, and salary for a calendar range. Today follows this computer’s date. Salary is the amount saved on a submission, not a guess from the résumé.
          </p>
        </div>
        <Button type="button" onClick={() => download("xlsx", "all")} disabled={Boolean(exporting) || from > to}>
          <Download /> {exporting === "xlsx-all" ? "Building…" : "Excel workbook"}
        </Button>
      </div>

      <section className="panel flex flex-col gap-4 p-4">
        <div className="flex flex-wrap gap-2">
          {PRESETS.map((item) => (
            <button
              key={item.id}
              type="button"
              onClick={() => applyPreset(item.id)}
              className={`rounded-full px-3 py-1 text-sm ${preset === item.id ? "bg-night text-white" : "bg-desk text-ink/70"}`}
            >
              {item.label}
            </button>
          ))}
        </div>
        <p className="text-sm text-ink/60">
          Showing {from} through {to}.
          {loading && report ? " Updating…" : ""}
        </p>
        <div className="flex flex-wrap items-end gap-3">
          <label className="text-sm">
            <span className="mb-1 block text-ink/60">From</span>
            <Input
              type="date"
              value={from}
              onChange={(event) => {
                setPreset("custom");
                setFrom(event.target.value);
              }}
            />
          </label>
          <label className="text-sm">
            <span className="mb-1 block text-ink/60">Through</span>
            <Input
              type="date"
              value={to}
              onChange={(event) => {
                setPreset("custom");
                setTo(event.target.value);
              }}
            />
          </label>
        </div>
      </section>

      {error && <p className="rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800">{error}</p>}
      {loading && !report && <p className="text-sm text-ink/55">Building the report…</p>}

      {report && (
        <>
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
            <Metric label="Ingested" value={report.ingested.total} note={`${submittedPeople} of them have a submission · ${conversion}%`} />
            <Metric label="Submitted" value={report.submitted.total} note="Submissions opened in this range" />
            <Metric label="Selected" value={report.outcomes.selected} note={`${report.outcomes.rejected} rejected · ${report.outcomes.withdrawn} withdrawn`} />
            <Metric label="Above the salary line" value={report.salary.greater_than == null ? "—" : report.salary.above} note={report.salary.greater_than == null ? "Set an amount below" : `Greater than ${money(report.salary.greater_than)}`} />
          </div>

          <section className="panel p-4">
            <h2 className="font-serif text-xl">Activity</h2>
            <p className="mt-1 text-sm text-ink/60">Résumés added and submissions opened. Ranges longer than 45 days are grouped by week.</p>
            <div className="mt-4">
              <Columns
                empty="Nothing was ingested or submitted in this range."
                series={[
                  { name: "Ingested", tone: "bg-pine", points: report.ingested.by_day },
                  { name: "Submitted", tone: "bg-night", points: report.submitted.by_day },
                ]}
              />
            </div>
          </section>

          <div className="grid gap-4 lg:grid-cols-2">
            <section className="panel p-4">
              <div className="mb-3 flex items-center justify-between gap-3">
                <h2 className="font-serif text-xl">Candidates ingested</h2>
                <Exporting busy={exporting} onClick={() => download("csv", "ingested")} label="CSV" id="csv-ingested" />
              </div>
              <p className="mb-3 text-sm text-ink/60">{ingestedSentence(report.ingested.total, submittedPeople)}</p>
              <People rows={report.ingested.candidates} shown={report.ingested.shown} total={report.ingested.total} />
            </section>
            <section className="panel p-4">
              <div className="mb-3 flex items-center justify-between gap-3">
                <h2 className="font-serif text-xl">Candidates submitted</h2>
                <Exporting busy={exporting} onClick={() => download("csv", "submitted")} label="CSV" id="csv-submitted" />
              </div>
              <div className="mb-4 grid gap-4 sm:grid-cols-2">
                <Bars points={report.submitted.by_stage} empty="No submissions opened in this range." />
                <Bars
                  points={report.submitted.by_job.map((job) => ({ label: `${job.requisition_code} · ${job.title || "Untitled"}`, count: job.count }))}
                  empty="No job received a submission in this range."
                />
              </div>
              <Submissions rows={report.submitted.rows} shown={report.submitted.shown} total={report.submitted.total} />
            </section>
          </div>

          <section className="panel p-4">
            <div className="mb-3 flex items-center justify-between gap-3">
              <h2 className="font-serif text-xl">Outcomes in this range</h2>
              <Exporting busy={exporting} onClick={() => download("csv", "outcomes")} label="CSV" id="csv-outcomes" />
            </div>
            <p className="mb-3 text-sm text-ink/60">Each time a submission was marked selected, rejected, or withdrawn. Reopening later does not erase the earlier outcome.</p>
            {report.outcomes.rows.length === 0 ? (
              <p className="text-sm text-ink/55">No selected, rejected, or withdrawn moves in this range.</p>
            ) : (
              <ul className="divide-y divide-line">
                {report.outcomes.rows.map((row, index) => (
                  <li key={`${row.submission_id}-${index}`} className="flex flex-wrap items-baseline justify-between gap-2 py-2 text-sm">
                    <span>
                      <Link href={`/admin/candidates/${row.candidate.id}`} className="font-medium underline-offset-2 hover:underline">
                        {row.candidate.full_name}
                      </Link>
                      <span className="text-ink/55"> · {row.to_label}</span>
                      <span className="text-ink/45"> from {row.from_label || "the start"}</span>
                    </span>
                    <Link href={`/admin/jobs/${row.job.requisition_code}`} className="text-ink/60 hover:underline">
                      {row.job.requisition_code}
                    </Link>
                  </li>
                ))}
              </ul>
            )}
          </section>

          <section className="panel p-4">
            <div className="mb-3 flex flex-wrap items-end justify-between gap-3">
              <div>
                <h2 className="font-serif text-xl">Clearance and polygraph</h2>
                <p className="mt-1 text-sm text-ink/60">Full scope is the FSP / full-scope polygraph. The mix charts always cover the whole desk.</p>
              </div>
              <Exporting busy={exporting} onClick={() => download("csv", "clearance")} label="CSV" id="csv-clearance" />
            </div>
            <div className="mb-4 flex flex-wrap gap-3">
              <Select label="Polygraph" value={poly} onChange={setPoly} options={[["full_scope", "Full scope (FSP)"], ["ci", "CI polygraph"], ["any", "Any polygraph on file"], ["missing", "Polygraph not on file"], ["", "Any polygraph, including blank"]]} />
              <Select label="Clearance" value={clearance} onChange={setClearance} options={[["", "Any clearance"], ["ts_sci", "TS/SCI"], ["ts", "Top Secret"], ["secret", "Secret"], ["public_trust", "Public Trust"], ["any", "A clearance is on file"], ["missing", "Clearance not on file"]]} />
              <Select label="Who" value={clearanceScope} onChange={setClearanceScope} options={[["all", "Whole desk"], ["range", "Ingested in this range"]]} />
            </div>
            <div className="mb-4 grid gap-4 lg:grid-cols-2">
              <div>
                <h3 className="mb-2 text-sm font-medium text-ink/70">Polygraph on file</h3>
                <Bars points={report.clearance.poly_mix} empty="No polygraph values on file." />
              </div>
              <div>
                <h3 className="mb-2 text-sm font-medium text-ink/70">Clearance on file</h3>
                <Bars points={report.clearance.clearance_mix} empty="No clearance values on file." />
              </div>
            </div>
            <p className="mb-2 text-sm text-ink/60">
              {report.clearance.total === 1 ? "1 person matches these filters." : `${report.clearance.total} people match these filters.`}
            </p>
            <People rows={report.clearance.candidates} shown={report.clearance.shown} total={report.clearance.total} extra />
          </section>

          <section className="panel p-4">
            <div className="mb-3 flex flex-wrap items-end justify-between gap-3">
              <div>
                <h2 className="font-serif text-xl">Salary greater than</h2>
                <p className="mt-1 text-sm text-ink/60">The yearly amount recorded for that job. A submission at the exact amount is left out.</p>
              </div>
              <Exporting busy={exporting} onClick={() => download("csv", "salary")} label="CSV" id="csv-salary" />
            </div>
            <div className="mb-4 flex flex-wrap items-end gap-3">
              <label className="text-sm">
                <span className="mb-1 block text-ink/60">Greater than</span>
                <Input inputMode="numeric" placeholder="150000" value={salaryGt} onChange={(event) => setSalaryGt(event.target.value)} className="w-40" />
              </label>
              <Select label="Which submissions" value={salaryScope} onChange={setSalaryScope} options={[["all", "Every salary on file"], ["range", "Opened in this range"]]} />
            </div>
            <div className="mb-4">
              <Columns empty="No salaries are on file for this scope." series={[{ name: "Submissions", tone: "bg-pine", points: report.salary.buckets.map((bucket) => ({ label: bucket.label.replace(" and up", "+").replace("Under ", "<"), count: bucket.count })) }]} />
            </div>
            {report.salary.greater_than == null ? (
              <p className="text-sm text-ink/55">Enter an amount to list the submissions above it. {report.salary.with_salary} submissions already have a salary.</p>
            ) : (
              <>
                <p className="mb-2 text-sm text-ink/60">
                  {report.salary.above} submission{report.salary.above === 1 ? "" : "s"} above {money(report.salary.greater_than)}. {report.salary.with_salary} have a salary in this scope.
                </p>
                <Submissions rows={report.salary.rows} shown={report.salary.shown} total={report.salary.above} emphasizeSalary />
              </>
            )}
          </section>

          <section className="panel p-4">
            <h2 className="font-serif text-xl">Pipeline right now</h2>
            <p className="mt-1 mb-4 text-sm text-ink/60">A snapshot of every open submission, independent of the date range.</p>
            <Funnel points={report.pipeline.map((stage) => ({ label: stage.label, count: stage.count }))} />
          </section>
        </>
      )}
    </div>
  );
}

function ingestedSentence(total: number, submittedPeople: number): string {
  if (total === 0) return "No résumés were added in this range.";
  const resumes = `${total} résumé${total === 1 ? "" : "s"} added.`;
  const bench = total - submittedPeople;
  if (bench === 0) return `${resumes} Everyone ingested in this range has a submission.`;
  if (bench === 1) return `${resumes} 1 has never been submitted.`;
  return `${resumes} ${bench} have never been submitted.`;
}

function Metric({ label, value, note }: { label: string; value: number | string; note: string }) {
  return (
    <div className="panel p-4">
      <p className="text-xs uppercase tracking-[0.16em] text-ink/45">{label}</p>
      <p className="mt-1 font-serif text-3xl tabular-nums">{value}</p>
      <p className="mt-1 text-sm text-ink/55">{note}</p>
    </div>
  );
}

function Exporting({ busy, onClick, label, id }: { busy: string; onClick: () => void; label: string; id: string }) {
  return (
    <Button type="button" variant="outline" onClick={onClick} disabled={Boolean(busy)}>
      <Download /> {busy === id ? "Exporting…" : label}
    </Button>
  );
}

function Select({
  label,
  value,
  onChange,
  options,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  options: string[][];
}) {
  return (
    <label className="text-sm">
      <span className="mb-1 block text-ink/60">{label}</span>
      <select
        value={value}
        onChange={(event) => onChange(event.target.value)}
        className="h-10 rounded-lg border border-line bg-white px-3 text-sm"
      >
        {options.map(([key, text]) => (
          <option key={key || "blank"} value={key}>
            {text}
          </option>
        ))}
      </select>
    </label>
  );
}

function People({ rows, shown, total, extra }: { rows: Report["ingested"]["candidates"]; shown: number; total: number; extra?: boolean }) {
  if (!rows.length) return <p className="text-sm text-ink/55">No one matches.</p>;
  return (
    <>
      <ul className="divide-y divide-line">
        {rows.map((row) => (
          <li key={row.id} className="flex flex-wrap items-baseline justify-between gap-2 py-2 text-sm">
            <Link href={`/admin/candidates/${row.id}`} className="font-medium underline-offset-2 hover:underline">
              {row.full_name}
            </Link>
            <span className="text-ink/55">
              {extra ? `${row.clearance_label} · ${row.polygraph_label}` : row.location || row.email || ""}
            </span>
          </li>
        ))}
      </ul>
      {shown < total && <p className="mt-2 text-xs text-ink/45">Showing {shown} of {total}. The Excel and CSV exports include up to 5,000 rows.</p>}
    </>
  );
}

function Submissions({
  rows,
  shown,
  total,
  emphasizeSalary,
}: {
  rows: Report["submitted"]["rows"];
  shown: number;
  total: number;
  emphasizeSalary?: boolean;
}) {
  if (!rows.length) return <p className="text-sm text-ink/55">No submissions match.</p>;
  return (
    <>
      <ul className="divide-y divide-line">
        {rows.map((row) => (
          <li key={row.id} className="flex flex-wrap items-baseline justify-between gap-2 py-2 text-sm">
            <span>
              <Link href={`/admin/submissions/${row.id}`} className="font-medium underline-offset-2 hover:underline">
                {row.candidate.full_name}
              </Link>
              <span className="text-ink/55"> · {row.stage_label}</span>
            </span>
            <span className="text-ink/60">
              {emphasizeSalary ? money(row.salary_usd) : row.job.requisition_code}
              {emphasizeSalary ? ` · ${row.job.requisition_code}` : row.salary_usd != null ? ` · ${money(row.salary_usd)}` : ""}
            </span>
          </li>
        ))}
      </ul>
      {shown < total && <p className="mt-2 text-xs text-ink/45">Showing {shown} of {total}. Export the full list as CSV or Excel.</p>}
    </>
  );
}
