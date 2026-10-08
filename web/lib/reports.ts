export type Person = {
  id: string;
  full_name: string;
  email: string | null;
  location: string | null;
  state: string | null;
  clearance_label: string;
  polygraph_label: string;
  created_at?: string | null;
};

export type SubmissionRow = {
  id: string;
  stage_label: string;
  salary_usd: number | null;
  salary_note: string | null;
  created_at: string | null;
  candidate: Person;
  job: { requisition_code: string; title: string | null; location?: string | null };
};

export type CountPoint = { label: string; date: string; count: number };
export type LabeledCount = { key: string; label: string; count: number };

export type Report = {
  start: string;
  end: string;
  timezone: string;
  ingested: {
    total: number;
    shown: number;
    also_submitted: number;
    by_day: CountPoint[];
    candidates: Person[];
  };
  submitted: {
    total: number;
    shown: number;
    by_day: CountPoint[];
    by_stage: LabeledCount[];
    by_job: { requisition_code: string; title: string | null; count: number }[];
    rows: SubmissionRow[];
  };
  outcomes: {
    selected: number;
    rejected: number;
    withdrawn: number;
    rows: {
      at: string | null;
      to_label: string | null;
      from_label: string | null;
      submission_id: string;
      candidate: Person;
      job: { requisition_code: string; title: string | null };
    }[];
  };
  clearance: {
    poly: string;
    clearance: string;
    scope: string;
    total: number;
    shown: number;
    poly_mix: LabeledCount[];
    clearance_mix: LabeledCount[];
    candidates: Person[];
  };
  salary: {
    greater_than: number | null;
    scope: string;
    with_salary: number;
    above: number;
    shown: number;
    buckets: { label: string; count: number }[];
    rows: SubmissionRow[];
  };
  pipeline: { key: string; label: string; terminal: boolean; count: number }[];
};

export function ymd(date: Date): string {
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${date.getFullYear()}-${month}-${day}`;
}

export function startOf(day: string): string {
  return new Date(`${day}T00:00:00`).toISOString();
}

export function endExclusive(day: string): string {
  const date = new Date(`${day}T00:00:00`);
  date.setDate(date.getDate() + 1);
  return date.toISOString();
}

export function shiftDays(day: string, delta: number): string {
  const date = new Date(`${day}T00:00:00`);
  date.setDate(date.getDate() + delta);
  return ymd(date);
}

export function reportQuery(input: {
  from: string;
  to: string;
  poly: string;
  clearance: string;
  salaryGt: string;
  salaryScope: string;
  clearanceScope: string;
  format?: string;
  sheet?: string;
}): URLSearchParams {
  const params = new URLSearchParams({
    start: startOf(input.from),
    end: endExclusive(input.to),
    tz: Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC",
    poly: input.poly,
    clearance: input.clearance,
    salary_scope: input.salaryScope,
    clearance_scope: input.clearanceScope,
  });
  const amount = input.salaryGt.trim();
  if (amount) params.set("salary_gt", amount);
  if (input.format) params.set("format", input.format);
  if (input.sheet) params.set("sheet", input.sheet);
  return params;
}
