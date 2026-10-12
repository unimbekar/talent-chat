"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { Activity, ArrowRight } from "lucide-react";

import { Sparkline } from "@/components/visitor-charts";
import { shiftDays, ymd } from "@/lib/reports";
import { count, type VisitorReport, visitorQuery } from "@/lib/visitors";

const DAYS = 14;

/** Dashboard panel for admins: today, the last two weeks, and the all-time total. */
export function VisitorsGlance() {
  const today = useMemo(() => ymd(new Date()), []);
  const [report, setReport] = useState<VisitorReport | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let live = true;
    fetch(`/api/admin/visitors?${visitorQuery(shiftDays(today, -(DAYS - 1)), today)}`)
      .then(async (response) => {
        if (!live) return;
        if (!response.ok) {
          setFailed(true);
          return;
        }
        setReport(await response.json());
      })
      .catch(() => live && setFailed(true));
    return () => {
      live = false;
    };
  }, [today]);

  if (failed) return null;

  return (
    <section className="panel flex flex-col gap-4 p-5 sm:flex-row sm:items-center">
      <div className="flex items-center gap-3 sm:w-56">
        <span className="grid size-10 shrink-0 place-items-center rounded-xl bg-pine/10 text-pine">
          <Activity className="size-5" />
        </span>
        <div>
          <h2 className="font-serif text-xl leading-tight">Careers site visitors</h2>
          <p className="text-xs text-ink/55">{report ? `${count(report.live)} in the last ${report.live_minutes} minutes` : "Loading…"}</p>
        </div>
      </div>
      <dl className="grid flex-none grid-cols-3 gap-4 text-center sm:text-left">
        <Figure label="Today" value={report ? count(report.today.visitors) : "—"} />
        <Figure label={`Last ${DAYS} days`} value={report ? count(report.range.visitors) : "—"} />
        <Figure label="All time" value={report ? count(report.all_time.visitors) : "—"} />
      </dl>
      <div className="min-w-0 flex-1">{report && <Sparkline values={report.days.map((day) => day.visitors)} />}</div>
      <Link href="/admin/visitors" className="inline-flex shrink-0 items-center gap-1 text-sm text-pine-deep hover:underline">
        See the charts <ArrowRight className="size-4" />
      </Link>
    </section>
  );
}

function Figure({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="text-[11px] uppercase tracking-wide text-ink/50">{label}</dt>
      <dd className="font-serif text-2xl tabular-nums">{value}</dd>
    </div>
  );
}
