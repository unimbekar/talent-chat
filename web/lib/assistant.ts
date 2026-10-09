// Recruiter assistant: message types, page context, suggestions, and the event stream.

export type Step = {
  id: string;
  tool: string;
  label: string;
  args: Record<string, unknown>;
  ok?: boolean;
  summary?: string;
  memo?: Record<string, unknown>;
};

export type CandidateRow = {
  id: string;
  name: string;
  email: string | null;
  location: string | null;
  titles?: string[];
  skills?: string[];
  clearance?: string | null;
};

export type RankedRow = {
  id: string;
  name: string;
  email: string | null;
  location: string | null;
  mandatory_pct: number | null;
  mandatory: string;
  desired: string;
  meets_bar: boolean;
};

export type JobRow = {
  code: string;
  title: string | null;
  location: string | null;
  status: string;
  needs_review: boolean;
  must_have: string[];
  clearance: string | null;
  posting_url: string | null;
  submissions?: number;
  evidence?: string;
};

export type SubmissionRow = {
  id: string;
  candidate: string;
  candidate_id: string;
  code: string;
  title: string | null;
  stage: string;
  stage_key: string;
  salary_usd: number | null;
  updated_at: string;
};

export type Block =
  | { type: "candidates"; title: string; total: number; rows: CandidateRow[]; unknown_location?: number }
  | { type: "ranked"; title: string; code: string; total: number; rows: RankedRow[] }
  | { type: "jobs"; title: string; total: number; rows: JobRow[] }
  | { type: "submissions"; title: string; total: number; rows: SubmissionRow[] }
  | { type: "stats"; title: string; items: { label: string; value: number; href?: string }[]; href?: string }
  | { type: "profile"; candidate: Record<string, any> }
  | { type: "job"; job: Record<string, any> }
  | { type: "fit"; fit: Record<string, any> }
  | { type: "submission"; submission: Record<string, any> };

export type UserMessage = { role: "user"; content: string };

export type AssistantMessage = {
  role: "assistant";
  content: string;
  steps: Step[];
  blocks: Block[];
  status: "streaming" | "done" | "error" | "stopped";
  error?: string;
  meta?: { elapsed_ms: number; model: string; tools: string[] };
};

export type Message = UserMessage | AssistantMessage;

export type PageContext = {
  path: string;
  label: string;
  code?: string;
  candidate_id?: string;
  submission_id?: string;
  view?: string;
};

const LABELS: Record<string, string> = {
  dashboard: "Dashboard",
  jobs: "Jobs",
  candidates: "Candidates",
  pipeline: "Pipeline",
  reports: "Reports",
  find: "Find candidates",
  match: "Match",
  review: "Review",
  ingest: "Ingest",
  submissions: "Submission",
};

export function pageContext(pathname: string, search: string): PageContext {
  const parts = pathname.split("/").filter(Boolean);
  const section = parts[1] || "dashboard";
  const detail = parts[2] ? decodeURIComponent(parts[2]) : "";
  const context: PageContext = { path: pathname, label: LABELS[section] || section };
  if (section === "jobs" && detail) {
    context.code = detail.toUpperCase();
    context.label = `Job ${context.code}`;
  } else if (section === "candidates" && detail) {
    context.candidate_id = detail;
    context.label = "Candidate profile";
  } else if (section === "submissions" && detail) {
    context.submission_id = detail;
    context.label = "Submission";
  }
  const params = new URLSearchParams(search);
  if (section === "review") {
    const job = params.get("job");
    const candidate = params.get("candidate");
    if (job) context.code = job.toUpperCase();
    if (candidate) context.candidate_id = candidate;
  }
  if (section === "match" && params.get("id")) context.candidate_id = params.get("id") || undefined;
  const view = [...params.entries()]
    .filter(([key]) => !["job", "candidate", "candidates", "id"].includes(key))
    .map(([key, value]) => `${key}=${value}`)
    .join(", ");
  if (view) context.view = view.slice(0, 300);
  return context;
}

export function suggestions(context: PageContext): string[] {
  const section = context.path.split("/").filter(Boolean)[1] || "dashboard";
  if (context.code && section === "jobs") {
    return ["Who fits this job?", "Summarize this job", "Who is submitted here?"];
  }
  if (context.candidate_id && section === "candidates") {
    return ["Summarize this candidate", "Best jobs for this candidate", "Is this candidate submitted anywhere?"];
  }
  if (context.submission_id) {
    return ["Summarize this submission", "What changed recently?", "Show other submissions for this job"];
  }
  switch (section) {
    case "jobs":
      return ["Which open jobs need review?", "Open jobs that need AWS", "Jobs without a full description"];
    case "candidates":
    case "find":
      return ["Java developers in Maryland", "TS/SCI with full scope poly", "Résumés added this week"];
    case "pipeline":
      return ["What is active right now?", "Who is at the offer stage?", "Salaries over $150k"];
    case "reports":
      return ["Activity this month", "Rejections in the last 30 days", "Salaries over $180k this year"];
    case "review":
    case "match":
      return ["Who fits A1001?", "Compare the top candidate with this job", "Best jobs for this candidate"];
    default:
      return ["How is the desk doing?", "What is in the pipeline?", "Résumés added this week"];
  }
}

export function historyForServer(messages: Message[]) {
  return messages
    .filter((message) => message.content.trim())
    .slice(-12)
    .map((message) =>
      message.role === "user"
        ? { role: "user", content: message.content }
        : {
            role: "assistant",
            content: message.content,
            tools: message.steps
              .filter((step) => step.ok)
              .slice(0, 6)
              .map((step) => ({ tool: step.tool, args: step.args, summary: step.summary, memo: step.memo })),
          },
    );
}

export type StreamEvent =
  | { type: "step"; id: string; tool: string; label: string; args: Record<string, unknown> }
  | { type: "step_done"; id: string; ok: boolean; summary: string; memo?: Record<string, unknown> }
  | { type: "block"; block: Block }
  | { type: "token"; text: string }
  | { type: "reset" }
  | { type: "final"; text: string }
  | { type: "done"; elapsed_ms: number; model: string; tools: string[] }
  | { type: "error"; message: string };

export async function streamAssistant(
  body: { messages: unknown[]; page: PageContext; timezone: string },
  onEvent: (event: StreamEvent) => void,
  signal: AbortSignal,
): Promise<void> {
  const response = await fetch("/api/admin/assistant", {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
    body: JSON.stringify(body),
    signal,
  });
  if (response.status === 401) throw new Error("Your session ended. Sign in again.");
  if (!response.ok || !response.body) throw new Error(`The assistant is unavailable (${response.status}).`);
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    let split = buffer.indexOf("\n\n");
    while (split >= 0) {
      const frame = buffer.slice(0, split);
      buffer = buffer.slice(split + 2);
      for (const line of frame.split("\n")) {
        if (!line.startsWith("data:")) continue;
        try {
          onEvent(JSON.parse(line.slice(5).trim()) as StreamEvent);
        } catch {
          // A malformed frame is skipped; the next one still renders.
        }
      }
      split = buffer.indexOf("\n\n");
    }
  }
}

export const ASSISTANT_STORE = "talent-assistant-v1";
export const ASK_EVENT = "talent-assistant:ask";

export function askAssistant(question: string) {
  window.dispatchEvent(new CustomEvent(ASK_EVENT, { detail: { question } }));
}

export function openAssistant() {
  window.dispatchEvent(new CustomEvent(ASK_EVENT, { detail: { question: "" } }));
}

export function money(value: number | null | undefined): string {
  return value == null ? "" : `$${value.toLocaleString("en-US")}`;
}
