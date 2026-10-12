"use client";

import { FormEvent, useState } from "react";
import { X } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

export type OpenRole = {
  requisition_code: string;
  title: string | null;
  location: string | null;
  blurb?: string;
};

function tomorrow(): string {
  const date = new Date();
  date.setDate(date.getDate() + 14);
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${date.getFullYear()}-${month}-${day}`;
}

export function ApplyDialog({
  job,
  onClose,
}: {
  job: OpenRole;
  onClose: () => void;
}) {
  const [fsp, setFsp] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [done, setDone] = useState("");
  const eligible = fsp === "yes";

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!eligible || busy) return;
    setBusy(true);
    setError("");
    const form = new FormData(event.currentTarget);
    form.set("requisition_code", job.requisition_code);
    form.set("fsp", "yes");
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
      <div className="careers-sheet max-h-[100dvh] w-full overflow-y-auto rounded-t-3xl sm:max-w-xl sm:rounded-3xl">
        <div className="flex items-start justify-between gap-3 border-b border-white/10 px-5 py-4">
          <div>
            <p className="careers-kicker">Apply</p>
            <h2 id="apply-title" className="mt-2 text-2xl font-medium tracking-tight">
              {job.title || "Open role"}
            </h2>
            <p className="text-sm text-white/55">
              <span className="font-mono text-[#9ce2ff]/80">{job.requisition_code}</span>
              {job.location ? ` · ${job.location}` : ""}
            </p>
          </div>
          <button type="button" onClick={onClose} className="rounded-lg p-1 text-white/50 hover:bg-white/10" aria-label="Close">
            <X className="size-5" />
          </button>
        </div>
        {done ? (
          <div className="px-5 py-8">
            <p className="text-2xl font-medium tracking-tight">Application received</p>
            <p className="mt-2 text-sm leading-6 text-white/70">{done}</p>
            <Button type="button" className="careers-action mt-6" onClick={onClose}>
              Back to open roles
            </Button>
          </div>
        ) : (
          <form onSubmit={onSubmit} className="grid gap-4 px-5 py-5">
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
            <fieldset className="rounded-2xl border border-white/10 bg-white/[0.03] px-4 py-3">
              <legend className="px-1 text-sm font-medium">TS/SCI with Full Scope Polygraph</legend>
              <p className="mt-1 text-sm leading-5 text-white/60">This is required. Without a current FSP, the application cannot be sent.</p>
              <div className="mt-3 flex gap-3">
                <label className={`flex-1 cursor-pointer rounded-xl border px-3 py-2 text-sm ${fsp === "yes" ? "border-[#9ce2ff]/50 bg-[#9ce2ff]/10" : "border-white/10 bg-white/[0.03]"}`}>
                  <input className="mr-2" type="radio" name="fsp-choice" checked={fsp === "yes"} onChange={() => setFsp("yes")} />
                  Yes, I hold FSP
                </label>
                <label className={`flex-1 cursor-pointer rounded-xl border px-3 py-2 text-sm ${fsp === "no" ? "border-red-400/40 bg-red-500/10" : "border-white/10 bg-white/[0.03]"}`}>
                  <input className="mr-2" type="radio" name="fsp-choice" checked={fsp === "no"} onChange={() => setFsp("no")} />
                  No
                </label>
              </div>
              {fsp === "no" && (
                <p className="mt-3 text-sm text-red-200" role="alert">
                  You are not eligible for this role. Janus Soft submits candidates who currently hold TS/SCI with a Full Scope Polygraph.
                </p>
              )}
            </fieldset>
            <div className="grid gap-3 sm:grid-cols-2">
              <Field label="Last TS/SCI date" name="last_tssci_on" type="date" />
              <Field label="Last FSP date" name="last_fsp_on" type="date" />
            </div>
            <label className="text-sm">
              <span className="mb-1 block text-white/60">Résumé</span>
              <input name="file" type="file" required accept=".pdf,.doc,.docx,.txt,application/pdf" className="block w-full text-sm text-white/70 file:mr-3 file:rounded-md file:border-0 file:bg-white/10 file:px-3 file:py-1.5 file:text-sm file:text-white/80" />
            </label>
            <label className="text-sm">
              <span className="mb-1 block text-white/60">Note</span>
              <textarea name="note" maxLength={1000} rows={3} placeholder="Optional. A sentence on why this role." className="field w-full rounded-xl px-3 py-2 text-sm outline-none" />
            </label>
            {error && <p className="rounded-xl border border-red-400/30 bg-red-500/10 px-3 py-2 text-sm text-red-100">{error}</p>}
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
      <span className="mb-1 block text-white/60">
        {label}
        {required ? "" : " (optional)"}
      </span>
      <Input name={name} type={type} required={required} placeholder={placeholder} autoComplete={autoComplete} inputMode={inputMode} defaultValue={defaultValue} />
    </label>
  );
}
