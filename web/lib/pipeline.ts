export type StageInfo = {
  key: string;
  label: string;
  terminal: boolean;
  detail: string;
  count?: number;
};

export type PersonBrief = {
  id: string;
  full_name: string | null;
  email: string | null;
  location: string | null;
  original_filename?: string | null;
};

export type JobBrief = {
  requisition_code: string;
  title: string | null;
  location: string | null;
  status: string;
};

export type SubmissionCard = {
  id: string;
  stage: string;
  stage_label: string;
  terminal: boolean;
  salary_usd: number | null;
  salary_note: string | null;
  created_at: string | null;
  updated_at: string | null;
  comment_count: number;
  candidate: PersonBrief;
  job: JobBrief;
};

export type SubmissionEvent = {
  id: string;
  kind: string;
  from_label: string | null;
  to_label: string | null;
  body: string | null;
  salary_usd: number | null;
  at: string | null;
};

export type Note = {
  id: string;
  body: string;
  created_at: string | null;
  updated_at: string | null;
  edited: boolean;
};

export type SiteApplication = {
  full_name: string;
  email: string;
  phone: string;
  location: string;
  salary_usd: number;
  start_on: string | null;
  years_experience: number;
  fsp: boolean;
  last_fsp_on: string | null;
  last_tssci_on: string | null;
  note: string | null;
  created_at: string | null;
};

export type SubmissionDetail = SubmissionCard & {
  events: SubmissionEvent[];
  comments: Note[];
  application?: SiteApplication | null;
  flow: string[];
  exits: string[];
};

export const STAGE_TONE: Record<string, string> = {
  submitted: "border-line bg-desk text-ink",
  salary: "border-amber-200 bg-amber-50 text-amber-950",
  interviewed: "border-pine/30 bg-pine/10 text-pine-deep",
  offer: "border-pine/40 bg-pine/20 text-pine-deep",
  selected: "border-emerald-200 bg-emerald-50 text-emerald-900",
  rejected: "border-red-200 bg-red-50 text-red-800",
  withdrawn: "border-line bg-white text-ink/55",
};

export function resumeFileUrl(candidateId: string, download = false): string {
  return `/api/admin/resumes/${candidateId}/file${download ? "?download=1" : ""}`;
}

export function money(amount: number | null | undefined): string {
  if (amount == null) return "No salary yet";
  return new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0 }).format(amount);
}

export function when(iso: string | null | undefined): string {
  if (!iso) return "";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "";
  return new Intl.DateTimeFormat("en-US", { month: "short", day: "numeric", year: "numeric" }).format(date);
}

export function whenExact(iso: string | null | undefined): string {
  if (!iso) return "";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "";
  return new Intl.DateTimeFormat("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
    hour: "numeric",
    minute: "2-digit",
  }).format(date);
}

export function personName(person: { full_name?: string | null; original_filename?: string | null } | null | undefined): string {
  return person?.full_name || person?.original_filename || "Unnamed résumé";
}

export function errorMessage(data: unknown, fallback: string): string {
  const detail = data && typeof data === "object" && "detail" in data ? (data as { detail?: unknown }).detail : undefined;
  if (typeof detail === "string" && detail) return detail;
  if (detail && typeof detail === "object" && "message" in detail) {
    const message = (detail as { message?: unknown }).message;
    if (typeof message === "string" && message) return message;
  }
  return fallback;
}

export function existingSubmissionId(data: unknown): string | null {
  const detail = data && typeof data === "object" && "detail" in data ? (data as { detail?: unknown }).detail : undefined;
  if (detail && typeof detail === "object" && "submission_id" in detail) {
    const id = (detail as { submission_id?: unknown }).submission_id;
    return typeof id === "string" ? id : null;
  }
  return null;
}

export function parseSalary(raw: string): number | null | "invalid" {
  const trimmed = raw.trim();
  if (!trimmed) return null;
  const digits = trimmed.replace(/[$,\s]/g, "");
  if (!/^\d+$/.test(digits)) return "invalid";
  const value = Number(digits);
  if (value < 1 || value > 5_000_000) return "invalid";
  return value;
}

export function eventSentence(event: SubmissionEvent): string {
  if (event.kind === "created") return "Submitted.";
  if (event.kind === "stage") return `Moved from ${event.from_label || "the previous stage"} to ${event.to_label || "a new stage"}.`;
  if (event.salary_usd) return `Salary set to ${money(event.salary_usd)}.`;
  return "Salary updated.";
}
