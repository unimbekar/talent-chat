"use client";

import { ChangeEvent, FormEvent, useEffect, useRef, useState } from "react";
import { Check, ChevronDown, FileUp, Info, RefreshCw, X } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

export type OpenRole = {
  requisition_code: string;
  title: string | null;
  location: string | null;
  blurb?: string;
};

type Tool = { name: string; have: boolean };
type Item = { label: string | null; text: string; met: boolean; tools: Tool[] };
type Coverage = { pct: number | null; hit: number; total: number; items: Item[] };
type Check = {
  verdict: "strong" | "partial" | "low" | "unknown";
  required: Coverage;
  desired: Coverage;
  title_tools: Tool[];
  title_ok: boolean;
  missing_tools: string[];
  found_skills: string[];
};

function tomorrow(): string {
  const date = new Date();
  date.setDate(date.getDate() + 14);
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${date.getFullYear()}-${month}-${day}`;
}

function size(bytes: number): string {
  return bytes > 1024 * 1024 ? `${(bytes / 1024 / 1024).toFixed(1)} MB` : `${Math.max(1, Math.round(bytes / 1024))} KB`;
}

export function ApplyDialog({ job, onClose }: { job: OpenRole; onClose: () => void }) {
  const [fsp, setFsp] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [done, setDone] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [checking, setChecking] = useState(false);
  const [check, setCheck] = useState<Check | null>(null);
  const [checkError, setCheckError] = useState("");
  const [claims, setClaims] = useState<Record<string, string>>({});
  const fileInput = useRef<HTMLInputElement>(null);
  const eligible = fsp === "yes";

  async function runCheck(chosen: File) {
    setChecking(true);
    setCheck(null);
    setCheckError("");
    const form = new FormData();
    form.set("requisition_code", job.requisition_code);
    form.set("file", chosen);
    try {
      const response = await fetch("/api/public/apply/check", { method: "POST", body: form });
      const body = await response.json().catch(() => ({}));
      if (!response.ok) {
        setCheckError(body?.message || "The résumé could not be checked. You can still apply.");
        return;
      }
      setCheck(body as Check);
    } catch {
      setCheckError("The résumé could not be checked. You can still apply.");
    } finally {
      setChecking(false);
    }
  }

  function onFile(event: ChangeEvent<HTMLInputElement>) {
    const chosen = event.target.files?.[0] || null;
    setFile(chosen);
    setClaims({});
    if (chosen) void runCheck(chosen);
    else {
      setCheck(null);
      setCheckError("");
    }
  }

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!eligible || busy) return;
    setBusy(true);
    setError("");
    const form = new FormData(event.currentTarget);
    form.set("requisition_code", job.requisition_code);
    form.set("fsp", "yes");
    const fitNote = Object.entries(claims)
      .filter(([, text]) => text != null)
      .map(([line, text]) => (text.trim() ? `${line}: ${text.trim()}` : line))
      .join("; ");
    if (fitNote) {
      const written = String(form.get("note") || "").trim();
      const combined = [written, `Job match: the candidate says these lines are on the résumé. ${fitNote}`].filter(Boolean).join(" ");
      form.set("note", combined.slice(0, 1000));
    }
    try {
      const response = await fetch("/api/public/apply", { method: "POST", body: form });
      const body = await response.json().catch(() => ({}));
      if (!response.ok) {
        setError(body?.detail?.message || body?.message || "The application was not sent.");
        return;
      }
      setDone(body.message || "You are submitted for this role.");
    } catch {
      setError("The application was not sent.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center bg-black/70 p-0 backdrop-blur-sm sm:items-center sm:p-6" role="dialog" aria-modal="true" aria-labelledby="apply-title">
      <div className="careers-sheet max-h-[100dvh] w-full overflow-y-auto rounded-t-3xl sm:max-w-2xl sm:rounded-3xl">
        <div className="desk-line flex items-start justify-between gap-3 border-b px-5 py-4">
          <div>
            <p className="careers-kicker">Apply</p>
            <h2 id="apply-title" className="desk-text mt-2 text-2xl font-medium tracking-tight">
              {job.title || "Open role"}
            </h2>
            <p className="desk-faint text-sm">
              <span className="careers-code font-mono">{job.requisition_code}</span>
              {job.location ? ` · ${job.location}` : ""}
            </p>
          </div>
          <button type="button" onClick={onClose} className="desk-faint desk-hover rounded-lg p-1" aria-label="Close">
            <X className="size-5" />
          </button>
        </div>
        {done ? (
          <div className="px-5 py-8">
            <p className="desk-text text-2xl font-medium tracking-tight">Application received</p>
            <p className="desk-muted mt-2 text-sm leading-6">{done}</p>
            <Button type="button" className="careers-action mt-6" onClick={onClose}>
              Back to open roles
            </Button>
          </div>
        ) : (
          <form onSubmit={onSubmit} className="grid gap-4 px-5 py-5">
            <section aria-labelledby="resume-step" className="grid gap-3">
              <div className="flex items-baseline justify-between gap-3">
                <p id="resume-step" className="desk-text text-sm font-medium">
                  Résumé
                </p>
                <p className="desk-faint text-[11px]">PDF, DOC, DOCX, or TXT</p>
              </div>
              <label
                className={`desk-field flex cursor-pointer items-center gap-3 rounded-2xl px-4 ${file ? "py-3" : "py-5"}`}
                style={file ? undefined : { borderStyle: "dashed" }}
                htmlFor="apply-resume"
              >
                <span className="desk-surface grid size-10 shrink-0 place-items-center rounded-xl">
                  <FileUp className="desk-accent size-5" />
                </span>
                <span className="min-w-0 flex-1">
                  {file ? (
                    <>
                      <span className="desk-text block truncate text-sm font-medium">{file.name}</span>
                      <span className="desk-faint block text-xs">{size(file.size)} · checked against this role</span>
                    </>
                  ) : (
                    <>
                      <span className="desk-text block text-sm font-medium">Choose your résumé</span>
                      <span className="desk-faint block text-xs">Janus Soft Job Matching runs as soon as the file is chosen.</span>
                    </>
                  )}
                </span>
                {file && (
                  <span className="desk-accent inline-flex items-center gap-1 text-xs font-medium">
                    <RefreshCw className="size-3.5" /> Replace
                  </span>
                )}
                <input
                  ref={fileInput}
                  id="apply-resume"
                  name="file"
                  type="file"
                  required
                  accept=".pdf,.doc,.docx,.txt,application/pdf"
                  className="sr-only"
                  onChange={onFile}
                />
              </label>
              {checking && <CheckSkeleton />}
              {checkError && <p className="desk-warn desk-surface rounded-xl px-3 py-2 text-sm">{checkError}</p>}
              {check && (
                <CheckPanel
                  check={check}
                  claims={claims}
                  onClaim={(key, note) =>
                    setClaims((current) => {
                      const next = { ...current };
                      if (note == null) delete next[key];
                      else next[key] = note;
                      return next;
                    })
                  }
                  onReplace={() => fileInput.current?.click()}
                />
              )}
            </section>
            <div className="grid gap-3 sm:grid-cols-2">
              <Field label="Full name" name="full_name" required autoComplete="name" />
              <Field label="Email" name="email" type="email" required autoComplete="email" />
              <Field label="Phone" name="phone" type="tel" required autoComplete="tel" />
              <Field label="City" name="location" required autoComplete="address-level2" placeholder="Chantilly, VA" />
            </div>
            <div className="grid gap-3 sm:grid-cols-3">
              <Field label="Desired salary" name="salary_usd" inputMode="numeric" required placeholder="165000" />
              <Field label="Can start" name="start_on" type="date" required defaultValue={tomorrow()} />
              <Field label="Years of experience" name="years_experience" inputMode="numeric" required placeholder="8" />
            </div>
            <fieldset className="desk-surface rounded-2xl px-4 py-3">
              <legend className="desk-text px-1 text-sm font-medium">TS/SCI with Full Scope Polygraph</legend>
              <p className="desk-muted mt-1 text-sm leading-5">This is required. Without a current FSP, the application cannot be sent.</p>
              <div className="mt-3 flex gap-3">
                <label className={`desk-text flex-1 cursor-pointer rounded-xl px-3 py-2 text-sm ${fsp === "yes" ? "desk-bubble" : "desk-surface"}`}>
                  <input className="mr-2" type="radio" name="fsp-choice" checked={fsp === "yes"} onChange={() => setFsp("yes")} />
                  Yes, I hold FSP
                </label>
                <label className={`desk-text flex-1 cursor-pointer rounded-xl px-3 py-2 text-sm ${fsp === "no" ? "desk-pill-miss" : "desk-surface"}`}>
                  <input className="mr-2" type="radio" name="fsp-choice" checked={fsp === "no"} onChange={() => setFsp("no")} />
                  No
                </label>
              </div>
              {fsp === "no" && (
                <p className="desk-miss mt-3 text-sm" role="alert">
                  You are not eligible for this role. Janus Soft submits candidates who currently hold TS/SCI with a Full Scope Polygraph.
                </p>
              )}
            </fieldset>
            <div className="grid gap-3 sm:grid-cols-2">
              <Field label="Last TS/SCI date" name="last_tssci_on" type="date" />
              <Field label="Last FSP date" name="last_fsp_on" type="date" />
            </div>
            <label className="text-sm">
              <span className="desk-muted mb-1 block">Note</span>
              <textarea name="note" maxLength={1000} rows={3} placeholder="Optional. A sentence on why this role." className="field w-full rounded-xl px-3 py-2 text-sm outline-none" />
            </label>
            {error && <p className="desk-pill-miss rounded-xl px-3 py-2 text-sm">{error}</p>}
            <div className="flex items-center justify-end gap-2">
              <Button type="button" variant="outline" className="careers-quiet" onClick={onClose}>
                Cancel
              </Button>
              <Button type="submit" className="careers-action" disabled={!eligible || busy}>
                {busy ? "Sending…" : "Submit application"}
              </Button>
            </div>
          </form>
        )}
      </div>
    </div>
  );
}

function CheckSkeleton() {
  return (
    <div className="desk-surface flex items-center gap-4 rounded-2xl px-4 py-4" aria-label="Matching your résumé to this role">
      <span className="desk-shimmer size-14 shrink-0 rounded-full" />
      <span className="flex-1 space-y-2">
        <span className="desk-faint text-[11px] font-medium uppercase tracking-[0.16em]">Janus Soft Job Matching</span>
        <span className="desk-shimmer block h-3 w-1/2 rounded" />
        <span className="desk-shimmer block h-3 w-4/5 rounded" />
      </span>
    </div>
  );
}

const VERDICT: Record<Check["verdict"], string> = {
  strong: "Strong match",
  partial: "Partial match",
  low: "Several requirements are missing",
  unknown: "No separate requirements",
};

function verdictDetail(check: Check): string {
  const { hit, total } = check.required;
  if (check.verdict === "unknown" || !total) return "This posting does not list requirements line by line.";
  if (hit === total) return `Your résumé shows all ${total} required qualifications for this role.`;
  return `Your résumé shows ${hit} of ${total} required qualifications. The ones it does not show are listed first.`;
}

function Ring({ hit, total }: { hit: number; total: number }) {
  const share = total ? hit / total : 0;
  const radius = 24;
  const length = 2 * Math.PI * radius;
  const tone = share >= 0.9 ? "desk-ok" : share >= 0.5 ? "desk-accent" : "desk-miss";
  return (
    <span className={`relative grid size-16 shrink-0 place-items-center ${tone}`} role="img" aria-label={`${hit} of ${total} requirements shown`}>
      <svg viewBox="0 0 56 56" className="absolute inset-0 size-16 -rotate-90">
        <circle cx="28" cy="28" r={radius} fill="none" stroke="currentColor" strokeOpacity="0.16" strokeWidth="5" />
        <circle
          cx="28"
          cy="28"
          r={radius}
          fill="none"
          stroke="currentColor"
          strokeWidth="5"
          strokeLinecap="round"
          strokeDasharray={`${length * share} ${length}`}
          style={{ transition: "stroke-dasharray 600ms ease" }}
        />
      </svg>
      <span className="desk-text text-sm font-semibold tabular-nums">
        {hit}/{total}
      </span>
    </span>
  );
}

function itemKey(item: Item): string {
  const name = item.label ? `${item.label}: ${item.text}` : item.text;
  return name.slice(0, 180);
}

function CheckPanel({
  check,
  claims,
  onClaim,
  onReplace,
}: {
  check: Check;
  claims: Record<string, string>;
  onClaim: (key: string, note: string | null) => void;
  onReplace: () => void;
}) {
  const [showCoveredDesired, setShowCoveredDesired] = useState(false);
  const panel = useRef<HTMLDivElement>(null);
  const missingTitle = check.title_tools.filter((tool) => !tool.have);
  const required = [...check.required.items].sort((a, b) => Number(a.met) - Number(b.met));
  const desiredMissing = check.desired.items.filter((item) => !item.met);
  const desiredCovered = check.desired.items.filter((item) => item.met);

  useEffect(() => {
    panel.current?.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }, []);

  return (
    <div ref={panel} className="desk-surface-strong animate-fade-up overflow-hidden rounded-2xl">
      <div className="flex items-center gap-4 px-4 py-4">
        {check.required.total > 0 ? <Ring hit={check.required.hit} total={check.required.total} /> : null}
        <div className="min-w-0">
          <p className="desk-accent text-[11px] font-medium uppercase tracking-[0.16em]">Janus Soft Job Matching</p>
          <p className="desk-text mt-1 font-medium">{VERDICT[check.verdict]}</p>
          <p className="desk-muted text-sm leading-5">{verdictDetail(check)}</p>
          {check.desired.total > 0 && (
            <p className="desk-faint mt-1 text-xs">
              Desired skills: {check.desired.hit} of {check.desired.total}
            </p>
          )}
        </div>
      </div>
      {missingTitle.length > 0 && (
        <p className="desk-pill-miss mx-4 mb-3 rounded-xl px-3 py-2 text-sm">
          The job title names {missingTitle.map((tool) => tool.name).join(", ")}. Your résumé does not mention {missingTitle.length === 1 ? "it" : "them"}.
        </p>
      )}
      {required.length > 0 && (
        <div>
          <p className="desk-muted px-4 pb-1 text-[11px] font-medium uppercase tracking-[0.14em]">Required</p>
          <ul className="desk-line divide-y border-t">
            {required.map((item) => (
              <Requirement key={itemKey(item)} item={item} claim={claims[itemKey(item)]} onClaim={(note) => onClaim(itemKey(item), note)} />
            ))}
          </ul>
        </div>
      )}
      {desiredMissing.length > 0 && (
        <div className="desk-line border-t">
          <p className="desk-muted px-4 pb-1 pt-3 text-[11px] font-medium uppercase tracking-[0.14em]">Desired, not shown</p>
          <ul className="desk-line divide-y border-t">
            {desiredMissing.map((item) => (
              <Requirement key={itemKey(item)} item={item} claim={claims[itemKey(item)]} onClaim={(note) => onClaim(itemKey(item), note)} />
            ))}
          </ul>
        </div>
      )}
      {desiredCovered.length > 0 && (
        <div className="desk-line border-t">
          <button type="button" onClick={() => setShowCoveredDesired((value) => !value)} aria-expanded={showCoveredDesired} className="desk-hover flex w-full items-center justify-between px-4 py-2.5 text-left text-sm">
            <span className="desk-muted">Desired skills your résumé shows ({desiredCovered.length})</span>
            <ChevronDown className={`desk-faint size-4 transition ${showCoveredDesired ? "rotate-180" : ""}`} />
          </button>
          {showCoveredDesired && (
            <ul className="desk-line divide-y border-t">
              {desiredCovered.map((item) => (
                <Requirement key={itemKey(item)} item={item} />
              ))}
            </ul>
          )}
        </div>
      )}
      <div className="desk-line flex gap-2.5 border-t px-4 py-3">
        <Info className="desk-faint mt-0.5 size-4 shrink-0" />
        <p className="desk-faint text-xs leading-5">
          Job Matching reads the words on your résumé. Update the file and{" "}
          <button type="button" onClick={onReplace} className="desk-accent font-medium underline-offset-2 hover:underline">
            replace it
          </button>{" "}
          to score again. If a missing line is really there, say so beside it. That note goes with the application. The résumé is kept only when you submit.
        </p>
      </div>
    </div>
  );
}

function Requirement({ item, claim, onClaim }: { item: Item; claim?: string; onClaim?: (note: string | null) => void }) {
  return (
    <li className="desk-line flex gap-3 px-4 py-3">
      <span className={`mt-0.5 grid size-5 shrink-0 place-items-center rounded-full ${item.met ? "desk-pill-ok" : "desk-pill-miss"}`}>
        {item.met ? <Check className="size-3" /> : <X className="size-3" />}
      </span>
      <div className="min-w-0 flex-1">
        <p className="desk-text text-sm leading-5">
          {item.label && <span className="font-medium">{item.label}. </span>}
          <span className={item.label ? "desk-muted" : undefined}>{item.text}</span>
        </p>
        {item.tools.length > 0 && (
          <div className="mt-1.5 flex flex-wrap gap-1.5">
            {item.tools.map((tool) => (
              <span key={tool.name} className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-medium ${tool.have ? "desk-pill-ok" : "desk-pill-miss"}`}>
                {tool.have ? <Check className="size-3" /> : <X className="size-3" />}
                {tool.name}
              </span>
            ))}
          </div>
        )}
        {!item.met && onClaim && (
          <div className="mt-2">
            <label className="desk-muted inline-flex cursor-pointer items-center gap-2 text-xs">
              <input
                type="checkbox"
                checked={claim != null}
                onChange={(event) => onClaim(event.target.checked ? "" : null)}
              />
              I have this
            </label>
            {claim != null && (
              <input
                value={claim}
                maxLength={160}
                onChange={(event) => onClaim(event.target.value)}
                placeholder="Where it shows, if you want to say"
                className="desk-field mt-2 w-full rounded-lg px-2.5 py-1.5 text-xs outline-none"
              />
            )}
          </div>
        )}
      </div>
    </li>
  );
}

function Field({
  label,
  name,
  type = "text",
  required,
  placeholder,
  autoComplete,
  inputMode,
  defaultValue,
}: {
  label: string;
  name: string;
  type?: string;
  required?: boolean;
  placeholder?: string;
  autoComplete?: string;
  inputMode?: "numeric" | "text";
  defaultValue?: string;
}) {
  return (
    <label className="text-sm">
      <span className="desk-muted mb-1 block">
        {label}
        {required ? "" : " (optional)"}
      </span>
      <Input name={name} type={type} required={required} placeholder={placeholder} autoComplete={autoComplete} inputMode={inputMode} defaultValue={defaultValue} />
    </label>
  );
}
