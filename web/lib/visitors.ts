import { endExclusive, startOf } from "@/lib/reports";

export type VisitorDay = {
  date: string;
  visitors: number;
  views: number;
  postings: number;
  new: number;
  applications: number;
  total: number;
};

export type Counted = { key: string; label: string; count: number };

export type VisitorReport = {
  start: string;
  end: string;
  timezone: string;
  all_time: { visitors: number; views: number; since: string | null };
  today: { visitors: number; views: number };
  live: number;
  live_minutes: number;
  range: {
    visitors: number;
    views: number;
    new: number;
    returning: number;
    views_per_visitor: number;
    daily_average: number;
    peak: { date: string; visitors: number } | null;
    applications: number;
    visitors_change: number | null;
    views_change: number | null;
  };
  days: VisitorDay[];
  funnel: Counted[];
  pages: { key: string; label: string; views: number; visitors: number }[];
  postings: { code: string; title: string; views: number; visitors: number; applying: number }[];
  sources: Counted[];
  devices: Counted[];
};

export function visitorQuery(from: string, to: string): URLSearchParams {
  return new URLSearchParams({
    start: startOf(from),
    end: endExclusive(to),
    tz: Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC",
  });
}

const SHORT = new Intl.DateTimeFormat(undefined, { month: "short", day: "numeric" });
const LONG = new Intl.DateTimeFormat(undefined, { weekday: "short", month: "short", day: "numeric", year: "numeric" });

function local(day: string): Date {
  return new Date(`${day}T00:00:00`);
}

export function shortDay(day: string): string {
  return SHORT.format(local(day));
}

export function longDay(day: string): string {
  return LONG.format(local(day));
}

export function count(value: number): string {
  return value.toLocaleString();
}

export function percent(part: number, whole: number): string {
  if (!whole) return "0%";
  const value = (part / whole) * 100;
  return `${value >= 10 || value === 0 ? Math.round(value) : value.toFixed(1)}%`;
}
