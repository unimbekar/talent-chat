"use client";

import { type ReactNode, useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { ArrowDownRight, ArrowUpRight, ExternalLink, RefreshCw } from "lucide-react";

import { Bars } from "@/components/report-charts";
import { Donut, TONES, type Tone, TrendChart, VisitorFunnel } from "@/components/visitor-charts";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { shiftDays, ymd } from "@/lib/reports";
import { count, longDay, percent, shortDay, type VisitorDay, type VisitorReport, visitorQuery } from "@/lib/visitors";

const PRESETS = [
  { id: "7", label: "Last 7 days", days: 7 },
  { id: "30", label: "Last 30 days", days: 30 },
  { id: "90", label: "Last 90 days", days: 90 },
  { id: "365", label: "Last 12 months", days: 365 },
  { id: "custom", label: "Custom", days: 0 },
] as const;

const METRICS: { id: keyof VisitorDay; label: string; tone: Tone; variant: "area" | "bars"; blurb: string }[] = [
  { id: "visitors", label: "Visitors", tone: "brand", variant: "area", blurb: "Different browsers that opened the careers site each day." },
  { id: "views", label: "Page views", tone: "sky", variant: "area", blurb: "Every time the jobs list or the benefits page was opened." },
  { id: "new", label: "New visitors", tone: "emerald", variant: "bars", blurb: "Browsers seen for the first time that day." },
  { id: "postings", label: "Postings opened", tone: "violet", variant: "bars", blurb: "Times a visitor opened a job posting." },
  { id: "applications", label: "Applications", tone: "amber", variant: "bars", blurb: "Applications received each day." },
];

const REFRESH_MS = 60_000;

export default function VisitorsPage() {
  const router = useRouter();
  const today = useMemo(() => ymd(new Date()), []);
  const [preset, setPreset] = useState("30");
  const [from, setFrom] = useState(shiftDays(today, -29));
  const [to, setTo] = useState(today);
  const [metric, setMetric] = useState<keyof VisitorDay>("visitors");
  const [report, setReport] = useState<VisitorReport | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [updatedAt, setUpdatedAt] = useState<Date | null>(null);

  const load = useCallback(
    async (quiet = false) => {
      if (from > to) {
        setError("The end date has to be on or after the start date.");
        setLoading(false);
        return;
      }
      if (!quiet) setLoading(true);
      try {
        const response = await fetch(`/api/admin/visitors?${visitorQuery(from, to)}`);
        if (response.status === 401) {
          router.push("/admin/login");
          return;
        }
        const body = await response.json().catch(() => ({}));
        if (!response.ok) {
          setError(body?.detail?.message || "Visitor numbers could not be loaded.");
          return;
        }
        setError("");
        setReport(body as VisitorReport);
        setUpdatedAt(new Date());
      } catch {
        if (!quiet) setError("The server did not answer. Try again.");
      } finally {
        setLoading(false);
      }
    },
    [from, to, router],
  );

  useEffect(() => {
    const handle = window.setTimeout(() => void load(), 150);
    return () => window.clearTimeout(handle);
  }, [load]);

  useEffect(() => {
    const handle = window.setInterval(() => {
      if (document.visibilityState === "visible") void load(true);
    }, REFRESH_MS);
    return () => window.clearInterval(handle);
  }, [load]);

  function choose(id: string) {
    setPreset(id);
    const found = PRESETS.find((item) => item.id === id);
    if (!found || !found.days) return;
    setFrom(shiftDays(today, -(found.days - 1)));
    setTo(today);
  }

  const chosen = METRICS.find((item) => item.id === metric) || METRICS[0];
  const days = report?.days || [];
  const totals = report?.range;

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="page-title">Visitors</h1>
          <p className="page-lead">
            Who opens the careers site, day by day and in total. A visitor is one browser. Each one keeps the IP address it connected from and a city when
            that address is on the public internet. Names and emails are not kept, and desk staff are left out.
          </p>
        </div>
        <div className="flex items-center gap-3">
          {report && (
            <span className="inline-flex items-center gap-2 rounded-full border border-line bg-card px-3 py-1.5 text-sm">
              <span className="relative flex size-2.5">
                {report.live > 0 && <span className="absolute inline-flex size-full animate-ping rounded-full bg-emerald-500/60" />}
                <span className={`relative inline-flex size-2.5 rounded-full ${report.live > 0 ? "bg-emerald-500" : "bg-ink/25"}`} />
              </span>
              {count(report.live)} on the site in the last {report.live_minutes} minutes
            </span>
          )}
          <Button type="button" variant="outline" size="sm" onClick={() => void load()} disabled={loading} aria-label="Refresh visitor numbers">
            <RefreshCw className={loading ? "animate-spin" : ""} /> Refresh
          </Button>
        </div>
      </div>

      <section className="panel flex flex-col gap-3 p-4">
        <div className="flex flex-wrap gap-2">
          {PRESETS.map((item) => (
            <button
              key={item.id}
              type="button"
              onClick={() => choose(item.id)}
              aria-pressed={preset === item.id}
              className={`rounded-full px-3 py-1 text-sm transition ${preset === item.id ? "bg-night text-white" : "bg-desk text-ink/70 hover:text-ink"}`}
            >
              {item.label}
            </button>
          ))}
        </div>
        {preset === "custom" && (
          <div className="flex flex-wrap items-end gap-3">
            <label className="text-sm">
              <span className="mb-1 block text-ink/60">From</span>
              <Input type="date" value={from} max={to} onChange={(event) => setFrom(event.target.value)} />
            </label>
            <label className="text-sm">
              <span className="mb-1 block text-ink/60">Through</span>
              <Input type="date" value={to} min={from} max={today} onChange={(event) => setTo(event.target.value)} />
            </label>
          </div>
        )}
        <p className="text-sm text-ink/60">
          {longDay(from)} through {longDay(to)}
          {updatedAt ? ` · updated ${updatedAt.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" })}, refreshes every minute` : ""}
        </p>
      </section>

      {error && <p className="rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800">{error}</p>}
      {!report && loading && <Skeleton />}

      {report && totals && (
        <>
          <div className="grid grid-cols-2 gap-3 sm:gap-4 xl:grid-cols-4">
            <Tile
              label="Total visitors"
              value={count(report.all_time.visitors)}
              note={report.all_time.since ? `All time, since ${shortDay(report.all_time.since)} · ${count(report.all_time.views)} page views` : "No visits recorded yet"}
              accent
            />
            <Tile label="Visitors in range" value={count(totals.visitors)} change={totals.visitors_change} note={`${totals.daily_average} a day on average`} />
            <Tile label="Page views" value={count(totals.views)} change={totals.views_change} note={`${totals.views_per_visitor} per visitor`} />
            <Tile label="Today" value={count(report.today.visitors)} note={`${count(report.today.views)} page views so far`} />
          </div>

          <section className="panel p-4 sm:p-5">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <h2 className="font-serif text-xl">Per day</h2>
                <p className="mt-1 text-sm text-ink/60">{chosen.blurb} Hover or use the arrow keys to read a day.</p>
              </div>
              <div className="flex flex-wrap gap-1 rounded-xl border border-line bg-desk p-1" role="tablist" aria-label="Daily metric">
                {METRICS.map((item) => (
                  <button
                    key={item.id}
                    type="button"
                    role="tab"
                    aria-selected={metric === item.id}
                    onClick={() => setMetric(item.id)}
                    className={`inline-flex items-center gap-1.5 rounded-lg px-2.5 py-1 text-xs font-medium transition ${
                      metric === item.id ? "bg-card text-ink shadow-sm" : "text-ink/60 hover:text-ink"
                    }`}
                  >
                    <span className="inline-block size-2 rounded-full" style={{ background: `rgb(${TONES[item.tone]})` }} />
                    {item.label}
                  </button>
                ))}
              </div>
            </div>
            <div className="mt-4">
              <TrendChart
                key={`${metric}-${days.length}`}
                dates={days.map((day) => day.date)}
                values={days.map((day) => Number(day[metric]) || 0)}
                label={`${chosen.label} per day`}
                tone={chosen.tone}
                variant={days.length > 120 ? "area" : chosen.variant}
                emptyText={`No ${chosen.label.toLowerCase()} in this range yet.`}
                tooltip={(index) => <DayTip day={days[index]} focus={metric} />}
              />
            </div>
            {totals.peak && (
              <p className="mt-2 text-xs text-ink/55">
                Busiest day: {longDay(totals.peak.date)} with {count(totals.peak.visitors)} visitors.
              </p>
            )}
          </section>

          <div className="grid grid-cols-1 gap-4 lg:grid-cols-[minmax(0,1.6fr)_minmax(0,1fr)]">
            <section className="panel p-4 sm:p-5">
              <h2 className="font-serif text-xl">Total visitors over time</h2>
              <p className="mt-1 text-sm text-ink/60">Every browser that has ever visited, counted on the day it first arrived.</p>
              <div className="mt-4">
                <TrendChart
                  dates={days.map((day) => day.date)}
                  values={days.map((day) => day.total)}
                  label="Total visitors, all time"
                  tone="violet"
                  height={220}
                  showAverage={false}
                  markLabel="Total"
                  emptyText="The running total starts with the first visit."
                  tooltip={(index) => (
                    <>
                      <p className="font-medium">{longDay(days[index].date)}</p>
                      <p className="mt-1 flex justify-between gap-4">
                        <span className="text-ink/60">Total so far</span>
                        <span className="tabular-nums font-medium">{count(days[index].total)}</span>
                      </p>
                      <p className="flex justify-between gap-4">
                        <span className="text-ink/60">New that day</span>
                        <span className="tabular-nums">+{count(days[index].new)}</span>
                      </p>
                    </>
                  )}
                />
              </div>
            </section>
            <section className="panel flex flex-col gap-4 p-4 sm:p-5">
              <div>
                <h2 className="font-serif text-xl">New and returning</h2>
                <p className="mt-1 text-sm text-ink/60">Returning visitors came before this range and came back.</p>
              </div>
              <Donut
                items={[
                  { label: "New", count: totals.new },
                  { label: "Returning", count: totals.returning },
                ]}
                center="visitors"
                empty="No visitors in this range yet."
              />
              <div className="mt-auto rounded-xl bg-desk p-3 text-sm">
                <p className="text-ink/60">Visitors who started an application</p>
                <p className="mt-1 font-serif text-2xl">{percent(report.funnel[2]?.count ?? 0, totals.visitors)}</p>
                <p className="text-xs text-ink/50">
                  {count(totals.applications)} {totals.applications === 1 ? "application" : "applications"} received in this range
                </p>
              </div>
            </section>
          </div>

          <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
            <section className="panel p-4 sm:p-5">
              <h2 className="font-serif text-xl">From visit to application</h2>
              <p className="mt-1 text-sm text-ink/60">How far visitors went in this range.</p>
              <div className="mt-4">
                <VisitorFunnel steps={report.funnel} />
              </div>
              <p className="mt-4 border-t border-line pt-3 text-sm text-ink/70">
                <span className="font-medium tabular-nums">{count(totals.applications)}</span>{" "}
                {totals.applications === 1 ? "application was" : "applications were"} received in this range. That count also includes people the
                counter skips, such as visitors with Do Not Track turned on.
              </p>
            </section>
            <section className="panel p-4 sm:p-5">
              <h2 className="font-serif text-xl">Where visitors came from</h2>
              <p className="mt-1 text-sm text-ink/60">
                The referring site, or the <span className="font-mono text-xs">utm_source</span> on your link. Add{" "}
                <span className="font-mono text-xs">?utm_source=email</span> to links you send so they show up here.
              </p>
              <div className="mt-4">
                <Bars points={report.sources.map((item) => ({ label: item.label, count: item.count }))} empty="No visitors in this range yet." />
              </div>
            </section>
          </div>

          <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
            <section className="panel p-4 sm:p-5 lg:col-span-1">
              <h2 className="font-serif text-xl">Devices</h2>
              <div className="mt-4">
                <Donut items={report.devices} center="visitors" empty="No visitors in this range yet." />
              </div>
            </section>
            <section className="panel p-4 sm:p-5">
              <h2 className="font-serif text-xl">Pages</h2>
              <p className="mt-1 text-sm text-ink/60">How often each careers page was opened.</p>
              <div className="mt-4">
                <Bars points={report.pages.map((item) => ({ label: item.label, count: item.views }))} empty="No page views in this range yet." />
              </div>
            </section>
            <section className="panel p-4 sm:p-5">
              <h2 className="font-serif text-xl">Most-viewed postings</h2>
              <p className="mt-1 text-sm text-ink/60">Times opened, and how many visitors started applying.</p>
              {report.postings.length === 0 ? (
                <p className="mt-4 text-sm text-ink/55">No postings opened in this range yet.</p>
              ) : (
                <ol className="mt-4 flex flex-col gap-3">
                  {report.postings.map((item) => {
                    const peak = report.postings[0].views || 1;
                    return (
                      <li key={item.code}>
                        <div className="mb-1 flex items-baseline justify-between gap-3 text-sm">
                          <Link href={`/admin/jobs/${encodeURIComponent(item.code)}`} className="min-w-0 truncate hover:text-pine-deep hover:underline">
                            <span className="font-mono text-xs text-pine">{item.code}</span> {item.title}
                          </Link>
                          <span className="shrink-0 tabular-nums text-ink/60">
                            {count(item.views)}
                            {item.applying ? ` · ${count(item.applying)} applying` : ""}
                          </span>
                        </div>
                        <div className="h-2 overflow-hidden rounded-full bg-line">
                          <div className="h-full rounded-full" style={{ width: `${(item.views / peak) * 100}%`, background: `rgb(${TONES.violet})` }} />
                        </div>
                      </li>
                    );
                  })}
                </ol>
              )}
            </section>
          </div>

          <section className="panel p-4 sm:p-5">
            <h2 className="font-serif text-xl">Where they were</h2>
            <p className="mt-1 text-sm text-ink/60">
              A public address shows a city. An address on your own network stays labeled as local, with the IP beside it.
            </p>
            <div className="mt-4">
              <Bars points={(report.places || []).map((item) => ({ label: item.label, count: item.count }))} empty="No visitors in this range yet." />
            </div>
            {(report.people || []).length > 0 && (
              <div className="mt-5 overflow-x-auto">
                <table className="w-full min-w-[36rem] text-left text-sm">
                  <thead>
                    <tr className="border-b border-line text-xs uppercase tracking-wide text-ink/45">
                      <th className="py-2 pr-3 font-medium">Location</th>
                      <th className="py-2 pr-3 font-medium">IP address</th>
                      <th className="py-2 pr-3 font-medium">First seen</th>
                      <th className="py-2 pr-3 font-medium">Last seen</th>
                      <th className="py-2 text-right font-medium">Views</th>
                    </tr>
                  </thead>
                  <tbody>
                    {report.people.map((person) => (
                      <tr key={`${person.ip}-${person.first_at}-${person.last_at}-${person.views}`} className="border-b border-line/70 last:border-0">
                        <td className="py-2.5 pr-3">{person.location}</td>
                        <td className="py-2.5 pr-3 font-mono text-xs">{person.ip}</td>
                        <td className="py-2.5 pr-3 text-ink/70">{seenAt(person.first_at)}</td>
                        <td className="py-2.5 pr-3 text-ink/70">{seenAt(person.last_at)}</td>
                        <td className="py-2.5 text-right tabular-nums">{count(person.views)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>

          <p className="flex flex-wrap items-center gap-1.5 text-xs text-ink/50">
            Counts browsers that allow it: visitors with Do Not Track or Global Privacy Control turned on, and search-engine bots, are not counted.
            <a href="/jobs" target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 text-pine-deep hover:underline">
              Open the careers site <ExternalLink className="size-3" />
            </a>
          </p>
        </>
      )}
    </div>
  );
}

function seenAt(value: string | null): string {
  if (!value) return "—";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return "—";
  return parsed.toLocaleString(undefined, { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });
}

function Tile({ label, value, note, change, accent }: { label: string; value: string; note: string; change?: number | null; accent?: boolean }) {
  return (
    <div className={`panel flex flex-col gap-1 p-4 ${accent ? "ring-1 ring-pine/40" : ""}`}>
      <p className="text-xs font-medium uppercase tracking-wide text-ink/55">{label}</p>
      <div className="flex flex-wrap items-baseline gap-2">
        <p className="font-serif text-3xl tabular-nums">{value}</p>
        {change != null && <Change value={change} />}
      </div>
      <p className="text-xs text-ink/55">{note}</p>
    </div>
  );
}

function Change({ value }: { value: number }) {
  const up = value >= 0;
  return (
    <span
      className={`inline-flex items-center gap-0.5 rounded-full px-1.5 py-0.5 text-[11px] font-semibold ${
        up ? "bg-emerald-500/15 text-emerald-500" : "bg-rose-500/15 text-rose-500"
      }`}
      title="Compared with the period of the same length just before"
    >
      {up ? <ArrowUpRight className="size-3" /> : <ArrowDownRight className="size-3" />}
      {Math.abs(value) >= 1000 ? "999+" : Math.abs(value).toFixed(Math.abs(value) < 10 ? 1 : 0)}%
    </span>
  );
}

function DayTip({ day, focus }: { day: VisitorDay; focus: keyof VisitorDay }) {
  const rows: [keyof VisitorDay, string][] = [
    ["visitors", "Visitors"],
    ["views", "Page views"],
    ["new", "New visitors"],
    ["postings", "Postings opened"],
    ["applications", "Applications"],
  ];
  return (
    <>
      <p className="font-medium">{longDay(day.date)}</p>
      <dl className="mt-1 flex flex-col gap-0.5">
        {rows.map(([key, label]) => (
          <div key={key} className={`flex justify-between gap-4 ${key === focus ? "font-semibold" : ""}`}>
            <dt className="text-ink/60">{label}</dt>
            <dd className="tabular-nums">{count(Number(day[key]) || 0)}</dd>
          </div>
        ))}
      </dl>
      {day.visitors > 0 && <p className="mt-1 text-[11px] text-ink/50">{percent(day.new, day.visitors)} were new</p>}
    </>
  );
}

function Skeleton(): ReactNode {
  return (
    <div className="grid gap-4" aria-label="Loading visitor numbers">
      <div className="grid grid-cols-2 gap-3 xl:grid-cols-4">
        {Array.from({ length: 4 }, (_, index) => (
          <div key={index} className="panel h-24 animate-pulse p-4" />
        ))}
      </div>
      <div className="panel h-80 animate-pulse" />
    </div>
  );
}
