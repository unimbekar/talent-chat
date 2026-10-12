"use client";

import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { useRouter } from "next/navigation";
import { Check, ChevronDown, Copy, Loader2, RotateCcw, Save, Trash2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { errorMessage, whenExact } from "@/lib/pipeline";
import {
  pct,
  signedUsd,
  STATUS_LABEL,
  STATUS_TONE,
  usd,
  type BurdenDefaults,
  type BurdenInputs,
  type BurdenResult,
  type PayType,
  type SavedBurden,
  type Tier,
} from "@/lib/burden";

const PAY_TYPES: [PayType, string, string][] = [
  ["w2_salary", "W2 salary", "Yearly salary with benefits"],
  ["w2_hourly", "W2 hourly", "Paid for hours worked"],
  ["1099", "1099", "Independent contractor"],
  ["c2c", "C2C", "Billed through a vendor's company"],
];
const TIERS: [Tier, string][] = [
  ["employee", "Employee"],
  ["employee_spouse", "+ Spouse"],
  ["employee_children", "+ Children"],
  ["family", "Family"],
];
const PLANS = [
  ["medical", "Medical"],
  ["dental", "Dental"],
  ["vision", "Vision"],
] as const;
const SEGMENT_COLORS: Record<string, string> = {
  wages: "bg-pine",
  employer_taxes: "bg-sky-500",
  retirement: "bg-violet-500",
  health: "bg-rose-500",
  other_benefits: "bg-amber-500",
  overhead: "bg-slate-500",
  profit: "bg-emerald-500",
};

type Props = {
  initial: Partial<BurdenInputs>;
  initialResult?: BurdenResult | null;
  savedAt?: string | null;
  saved?: boolean;
  onSave?: (inputs: BurdenInputs) => Promise<SavedBurden>;
  onClear?: () => Promise<SavedBurden>;
  subject?: string;
};

export function BurdenCalculator({ initial, initialResult = null, savedAt = null, saved = false, onSave, onClear, subject }: Props) {
  const router = useRouter();
  const [defaults, setDefaults] = useState<BurdenDefaults | null>(null);
  const [inputs, setInputs] = useState<BurdenInputs | null>(null);
  const [result, setResult] = useState<BurdenResult | null>(initialResult);
  const [pending, setPending] = useState(false);
  const [problem, setProblem] = useState("");
  const [savedInputs, setSavedInputs] = useState<string | null>(null);
  const [savedWhen, setSavedWhen] = useState<string | null>(savedAt);
  const [busy, setBusy] = useState<"save" | "clear" | null>(null);
  const [copied, setCopied] = useState(false);
  const [notice, setNotice] = useState("");

  useEffect(() => {
    fetch("/api/admin/burden/defaults").then(async (response) => {
      if (response.status === 401) {
        router.push("/admin/login");
        return;
      }
      if (!response.ok) {
        setProblem("The calculator defaults could not be loaded. Reload the page to try again.");
        return;
      }
      const data = (await response.json()) as BurdenDefaults;
      const start = { ...data.inputs, ...initial };
      setDefaults(data);
      setInputs(start);
      if (saved) setSavedInputs(stable(start));
    });
    // The starting inputs are read once; later changes come from the form.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (!inputs) return;
    const needsPay = inputs.pay_type === "w2_salary" ? !inputs.salary : !inputs.pay_rate && !inputs.salary;
    if (needsPay) {
      setResult(null);
      setProblem("");
      return;
    }
    const controller = new AbortController();
    const handle = window.setTimeout(async () => {
      setPending(true);
      try {
        const response = await fetch("/api/admin/burden", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(inputs),
          signal: controller.signal,
        });
        const data = await response.json().catch(() => ({}));
        if (!response.ok) {
          setProblem(errorMessage(data, "That combination could not be calculated."));
          return;
        }
        setProblem("");
        setResult(data.result as BurdenResult);
      } catch (error) {
        if ((error as Error).name !== "AbortError") setProblem("The calculator is not reachable right now.");
      } finally {
        if (!controller.signal.aborted) setPending(false);
      }
    }, 140);
    return () => {
      controller.abort();
      window.clearTimeout(handle);
    };
  }, [inputs]);

  const dirty = useMemo(() => {
    if (!onSave || !inputs) return false;
    return savedInputs !== stable(inputs);
  }, [inputs, savedInputs, onSave]);

  if (!inputs || !defaults) {
    if (problem) return <p className="panel p-5 text-sm text-red-600" role="alert">{problem}</p>;
    return (
      <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_26rem]" aria-busy="true">
        <div className="h-96 animate-pulse rounded-2xl bg-ink/5" />
        <div className="h-96 animate-pulse rounded-2xl bg-ink/5" />
      </div>
    );
  }

  const set = <K extends keyof BurdenInputs>(key: K, value: BurdenInputs[K]) =>
    setInputs((current) => (current ? { ...current, [key]: value } : current));
  const w2 = inputs.pay_type === "w2_salary" || inputs.pay_type === "w2_hourly";
  const state = defaults.states[inputs.state];

  async function save() {
    if (!onSave || !inputs) return;
    setBusy("save");
    setNotice("");
    try {
      const data = await onSave(inputs);
      setSavedInputs(stable(data.inputs));
      setInputs(data.inputs);
      setSavedWhen(data.saved_at);
      if (data.result) setResult(data.result);
      setNotice("Saved with this submission.");
    } catch (error) {
      setProblem((error as Error).message || "The calculation was not saved.");
    } finally {
      setBusy(null);
    }
  }

  async function clear() {
    if (!onClear) return;
    setBusy("clear");
    setNotice("");
    try {
      const data = await onClear();
      setSavedInputs(null);
      setSavedWhen(null);
      setInputs({ ...defaults!.inputs, ...data.inputs });
      setNotice("Cleared. The pipeline no longer shows a margin for this submission.");
    } catch (error) {
      setProblem((error as Error).message || "The calculation was not cleared.");
    } finally {
      setBusy(null);
    }
  }

  function reset() {
    setInputs({ ...defaults!.inputs, salary: inputs!.salary, pay_rate: inputs!.pay_rate, pay_type: inputs!.pay_type, bill_rate: inputs!.bill_rate });
    setNotice("Defaults restored. Pay and the hourly rate were kept.");
  }

  async function copy() {
    if (!result) return;
    await navigator.clipboard.writeText(summaryText(result, subject));
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1600);
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-xs text-ink/55">
          {defaults.tax_year} federal tax figures. Change any default to match your rate notices and plan.
          {onSave && (savedWhen ? ` Saved ${whenExact(savedWhen)}.` : " Not saved yet.")}
          {dirty && <span className="ml-1 font-medium text-amber-600">Unsaved changes.</span>}
        </p>
        <div className="flex flex-wrap gap-2">
          <Button type="button" variant="outline" size="sm" onClick={reset}>
            <RotateCcw /> Defaults
          </Button>
          <Button type="button" variant="outline" size="sm" onClick={copy} disabled={!result}>
            {copied ? <Check /> : <Copy />} {copied ? "Copied" : "Copy summary"}
          </Button>
          {onClear && savedWhen && (
            <Button type="button" variant="danger" size="sm" onClick={clear} disabled={busy !== null}>
              <Trash2 /> Clear
            </Button>
          )}
          {onSave && (
            <Button type="button" size="sm" onClick={save} disabled={busy !== null || !result || Boolean(problem) || (!dirty && Boolean(savedWhen))}>
              {busy === "save" ? <Loader2 className="animate-spin" /> : <Save />} {savedWhen && !dirty ? "Saved" : "Save"}
            </Button>
          )}
        </div>
      </div>
      {notice && <p className="text-sm text-pine-deep" role="status">{notice}</p>}

      <div className="grid items-start gap-4 lg:grid-cols-[minmax(0,1fr)_27rem]">
        <div className="flex flex-col gap-4">
          <Group step="1" title="Pay" hint="What the candidate is paid, and the hours the client is billed for.">
            <Segmented
              label="Pay type"
              value={inputs.pay_type}
              options={PAY_TYPES.map(([value, label, hint]) => ({ value, label, hint }))}
              onChange={(value) => set("pay_type", value as PayType)}
            />
            <div className="grid gap-3 sm:grid-cols-2">
              {inputs.pay_type === "w2_salary" ? (
                <NumberField label="Desired salary" prefix="$" suffix="/ yr" value={inputs.salary} onChange={(value) => set("salary", value)} placeholder="150,000" autoFocus={!inputs.salary} />
              ) : (
                <NumberField
                  label="Hourly pay"
                  prefix="$"
                  suffix="/ hr"
                  cents
                  value={inputs.pay_rate}
                  onChange={(value) => set("pay_rate", value)}
                  placeholder={inputs.salary ? (inputs.salary / inputs.paid_hours).toFixed(2) : "75.00"}
                  hint={inputs.salary && !inputs.pay_rate ? `Blank uses the salary ÷ ${inputs.paid_hours.toLocaleString()} hours.` : undefined}
                />
              )}
              <NumberField
                label="Minimum working hours"
                suffix="hrs / yr"
                value={inputs.hours}
                onChange={(value) => set("hours", value ?? 1860)}
                hint="Billable hours. Unlimited PTO requires at least this many."
              />
              {inputs.pay_type === "w2_salary" && (
                <NumberField
                  label="Paid hours"
                  suffix="hrs / yr"
                  value={inputs.paid_hours}
                  onChange={(value) => set("paid_hours", value ?? 2080)}
                  hint="Hours a salary covers, for the hourly equivalent."
                />
              )}
            </div>
          </Group>

          <Group step="2" title="Candidate hourly rate" hint="The rate billed to the client. Profit or loss follows it.">
            <div className="grid gap-3 sm:grid-cols-2">
              <NumberField label="Candidate hourly rate" prefix="$" suffix="/ hr" cents value={inputs.bill_rate} onChange={(value) => set("bill_rate", value)} placeholder={result?.billing.target_rate?.toFixed(2) || "120.00"} emphasis />
              <NumberField label="Target margin" suffix="%" value={inputs.target_margin_pct} onChange={(value) => set("target_margin_pct", value ?? 0)} />
            </div>
            {result && (
              <div className="flex flex-wrap gap-2 text-xs">
                {result.billing.break_even_rate != null && (
                  <Chip onClick={() => set("bill_rate", result.billing.break_even_rate)}>Break-even {usd(result.billing.break_even_rate, true)}</Chip>
                )}
                {result.billing.target_rate != null && (
                  <Chip onClick={() => set("bill_rate", result.billing.target_rate)} strong>
                    {pct(inputs.target_margin_pct)} margin {usd(result.billing.target_rate, true)}
                  </Chip>
                )}
              </div>
            )}
            <Disclosure title="Fees and overhead">
              <div className="grid gap-3 sm:grid-cols-2">
                <NumberField label="Client or MSP fee" suffix="% of bill" value={inputs.fee_pct} onChange={(value) => set("fee_pct", value ?? 0)} hint="Vendor-management or prime fee taken off the bill rate." />
                <NumberField label="Overhead and G&A" suffix="%" value={inputs.overhead_pct} onChange={(value) => set("overhead_pct", value ?? 0)} hint="Indirect cost added on pay plus burden." />
              </div>
            </Disclosure>
          </Group>

          <Group step="3" title="Medical, dental, and vision" hint="The company pays 100% for the employee and its share of the dependents' premium." disabled={!w2}>
            <div className="flex flex-wrap gap-2">
              {PLANS.map(([key, label]) => (
                <Toggle key={key} label={`${label} needed`} checked={inputs[key]} onChange={(value) => set(key, value)} />
              ))}
            </div>
            <Segmented label="Coverage" value={inputs.tier} options={TIERS.map(([value, label]) => ({ value, label }))} onChange={(value) => set("tier", value as Tier)} />
            {inputs.tier !== "employee" && (
              <NumberField label="Company share of dependents' premium" suffix="%" value={inputs.dependent_share_pct} onChange={(value) => set("dependent_share_pct", value ?? 0)} />
            )}
            <Disclosure title="Monthly premiums">
              <div className="grid gap-3 sm:grid-cols-3">
                {PLANS.map(([key, label]) => {
                  const table = defaults.premiums[key];
                  return (
                    <div key={key} className="flex flex-col gap-2">
                      <NumberField label={`${label}, employee`} prefix="$" suffix="/ mo" value={inputs[`${key}_monthly`]} onChange={(value) => set(`${key}_monthly`, value)} placeholder={String(table.employee)} disabled={!inputs[key]} />
                      {inputs.tier !== "employee" && (
                        <NumberField
                          label={`${label}, dependents`}
                          prefix="$"
                          suffix="/ mo"
                          value={inputs[`${key}_dependents_monthly`]}
                          onChange={(value) => set(`${key}_dependents_monthly`, value)}
                          placeholder={String(table[inputs.tier] - table.employee)}
                          disabled={!inputs[key]}
                        />
                      )}
                    </div>
                  );
                })}
              </div>
              <p className="text-xs text-ink/50">Blank fields use typical {defaults.tax_year} group-plan premiums. Enter your carrier&apos;s rates for exact figures.</p>
            </Disclosure>
          </Group>

          <Group step="4" title="401(k) match" hint="Dollar for dollar on the employee's own contribution." disabled={!w2}>
            <div className="flex flex-wrap items-end gap-3">
              <Toggle label="Offer 401(k)" checked={inputs.retirement} onChange={(value) => set("retirement", value)} />
            </div>
            {inputs.retirement && (
              <>
                <div className="grid gap-3 sm:grid-cols-2">
                  <NumberField
                    label="Company match"
                    suffix="%"
                    value={inputs.match_pct}
                    onChange={(value) => set("match_pct", value ?? defaults.match_minimum)}
                    min={defaults.match_minimum}
                    hint={`At least ${defaults.match_minimum}%.`}
                  />
                  <NumberField
                    label="Employee contribution"
                    suffix="%"
                    value={inputs.employee_deferral_pct}
                    onChange={(value) => set("employee_deferral_pct", value)}
                    placeholder={String(inputs.match_pct)}
                    hint="Blank assumes they contribute enough for the full match."
                  />
                </div>
                <div className="flex flex-wrap gap-2 text-xs">
                  {[6, 8, 10].map((value) => (
                    <Chip key={value} onClick={() => set("match_pct", value)} strong={inputs.match_pct === value}>
                      {value}% match
                    </Chip>
                  ))}
                </div>
              </>
            )}
          </Group>

          <Group step="5" title="Other benefits" hint="Company-paid insurance and allowances, budgeted at the plan amounts." disabled={!w2}>
            <Toggle label="Life and disability insurance" checked={inputs.life_disability} onChange={(value) => set("life_disability", value)} />
            {inputs.life_disability && (
              <div className="grid gap-3 sm:grid-cols-3">
                <NumberField label="Life insurance" prefix="$" suffix="/ mo" value={inputs.life_monthly} onChange={(value) => set("life_monthly", value ?? 0)} />
                <NumberField label="Short-term disability" prefix="$" suffix="/ mo" value={inputs.std_monthly} onChange={(value) => set("std_monthly", value ?? 0)} />
                <NumberField label="Long-term disability" prefix="$" suffix="/ mo" value={inputs.ltd_monthly} onChange={(value) => set("ltd_monthly", value ?? 0)} />
              </div>
            )}
            <div className="grid gap-3 sm:grid-cols-3">
              <NumberField label="Training and tuition" prefix="$" suffix="/ yr" value={inputs.training_annual} onChange={(value) => set("training_annual", value ?? 0)} hint="Plan allows up to $3,000." />
              <NumberField label="Health and technology" prefix="$" suffix="/ yr" value={inputs.wellness_annual} onChange={(value) => set("wellness_annual", value ?? 0)} hint="Plan allows up to $1,000." />
              <NumberField label="Other costs" prefix="$" suffix="/ yr" value={inputs.other_annual} onChange={(value) => set("other_annual", value ?? 0)} hint="Equipment, clearance, onboarding." />
            </div>
          </Group>

          <Group step="6" title="Employer taxes" hint="Payroll taxes the company pays on top of pay." disabled={!w2}>
            <div className="grid gap-3 sm:grid-cols-2">
              <label className="text-sm">
                <span className="text-ink/70">Work state</span>
                <select value={inputs.state} onChange={(event) => setInputs({ ...inputs, state: event.target.value as BurdenInputs["state"], suta_rate: null, suta_wage_base: null })} className="field mt-1 h-10">
                  {Object.entries(defaults.states).map(([key, item]) => (
                    <option key={key} value={key}>
                      {item.label}
                    </option>
                  ))}
                </select>
              </label>
              <NumberField label="Workers' compensation" suffix="% of pay" value={inputs.workers_comp_pct} onChange={(value) => set("workers_comp_pct", value ?? 0)} />
              <NumberField label="State unemployment rate" suffix="%" value={inputs.suta_rate} onChange={(value) => set("suta_rate", value)} placeholder={String(state.suta_rate)} hint="Blank uses the new-employer rate." />
              <NumberField label="State unemployment wage base" prefix="$" value={inputs.suta_wage_base} onChange={(value) => set("suta_wage_base", value)} placeholder={state.suta_wage_base.toLocaleString()} />
            </div>
            <Disclosure title="Federal unemployment">
              <NumberField label="FUTA rate" suffix="%" value={inputs.futa_rate} onChange={(value) => set("futa_rate", value ?? 0)} hint={`0.6% after the full state credit, on the first $${defaults.limits.futa_wage_base.toLocaleString()}.`} />
            </Disclosure>
          </Group>

          <Group step="7" title="Employee taxes" hint="Withheld from the candidate's pay. Used for the take-home estimate." disabled={inputs.pay_type === "c2c"}>
            <Segmented
              label="Filing status"
              value={inputs.filing_status}
              options={[
                { value: "single", label: "Single" },
                { value: "married", label: "Married, joint" },
              ]}
              onChange={(value) => set("filing_status", value as BurdenInputs["filing_status"])}
            />
            <div className="grid gap-3 sm:grid-cols-2">
              <div className="flex flex-col gap-2">
                <Segmented
                  label="Federal income tax"
                  value={inputs.federal_mode}
                  options={[
                    { value: "estimate", label: `${defaults.tax_year} brackets` },
                    { value: "flat", label: "Flat rate" },
                  ]}
                  onChange={(value) => set("federal_mode", value as BurdenInputs["federal_mode"])}
                />
                {inputs.federal_mode === "flat" && <NumberField label="Federal rate" suffix="%" value={inputs.federal_rate_pct} onChange={(value) => set("federal_rate_pct", value ?? 0)} />}
              </div>
              <div className="flex flex-col gap-2">
                <Segmented
                  label="State income tax"
                  value={inputs.state_mode}
                  options={[
                    { value: "va", label: "Virginia" },
                    { value: "flat", label: "Flat" },
                    { value: "none", label: "None" },
                  ]}
                  onChange={(value) => set("state_mode", value as BurdenInputs["state_mode"])}
                />
                {inputs.state_mode === "flat" && <NumberField label="State rate" suffix="%" value={inputs.state_rate_pct} onChange={(value) => set("state_rate_pct", value ?? 0)} />}
              </div>
            </div>
          </Group>
        </div>

        <Results result={result} inputs={inputs} pending={pending} problem={problem} onRate={(rate) => set("bill_rate", rate)} />
      </div>
    </div>
  );
}

function Results({
  result,
  inputs,
  pending,
  problem,
  onRate,
}: {
  result: BurdenResult | null;
  inputs: BurdenInputs;
  pending: boolean;
  problem: string;
  onRate: (rate: number) => void;
}) {
  if (!result) {
    return (
      <aside className="panel flex flex-col gap-2 p-5 lg:sticky lg:top-4">
        <p className="text-xs font-medium uppercase tracking-[0.14em] text-ink/45">Results</p>
        <p className="font-serif text-xl">{problem || (inputs.pay_type === "w2_salary" ? "Enter the desired salary." : "Enter the hourly pay.")}</p>
        <p className="text-sm text-ink/60">Costs, profit, and take-home pay appear here as you type.</p>
      </aside>
    );
  }
  const billing = result.billing;
  const hourly = (amount: number) => amount / result.hours;
  return (
    <aside className={`flex flex-col gap-3 transition-opacity lg:sticky lg:top-4 ${pending ? "opacity-80" : ""}`} aria-live="polite">
      {problem && <p className="rounded-xl border border-red-500/30 bg-red-500/10 px-3 py-2 text-sm text-red-600" role="alert">{problem}</p>}

      <section className="panel overflow-hidden">
        <div className="flex items-start justify-between gap-3 p-5 pb-3">
          <div>
            <p className="text-xs font-medium uppercase tracking-[0.14em] text-ink/45">{billing.bill_rate ? "Profit / loss" : "Loaded cost"}</p>
            {billing.bill_rate ? (
              <>
                <p className={`mt-1 font-serif text-4xl tabular-nums ${billing.status === "loss" ? "text-red-600" : billing.status === "thin" ? "text-amber-600" : "text-emerald-600"}`} data-testid="profit-hourly">
                  {signedUsd(billing.profit_hourly, true)}
                  <span className="ml-1 text-base text-ink/50">/ hr</span>
                </p>
                <p className="mt-1 text-sm text-ink/65 tabular-nums">
                  {signedUsd(billing.profit)} a year · {pct(billing.margin_pct)} margin
                </p>
              </>
            ) : (
              <>
                <p className="mt-1 font-serif text-4xl tabular-nums">
                  {usd(result.cost.hourly, true)}
                  <span className="ml-1 text-base text-ink/50">/ hr</span>
                </p>
                <p className="mt-1 text-sm text-ink/65">Enter the candidate hourly rate to see profit or loss.</p>
              </>
            )}
          </div>
          <span className={`inline-flex items-center gap-1 rounded-full border px-2.5 py-1 text-xs font-medium ${STATUS_TONE[billing.status]}`}>
            {pending && <Loader2 className="size-3 animate-spin" />}
            {STATUS_LABEL[billing.status]}
          </span>
        </div>
        <RateScale result={result} />
        <dl className="grid grid-cols-2 gap-px border-t border-line bg-line text-sm">
          <Stat label="Fully loaded cost" value={usd(result.cost.annual)} detail={`${usd(result.cost.hourly, true)} per billable hour`} />
          <Stat label="Burden" value={usd(result.burden.total)} detail={`${pct(result.burden.pct)} of pay`} />
          <Stat label="Pay per hour" value={usd(result.pay_hourly, true)} detail={result.pay_type_label} />
          <Stat
            label="Markup · multiplier"
            value={billing.markup_pct == null ? "—" : `${pct(billing.markup_pct)}`}
            detail={billing.multiplier == null ? "Needs a rate" : `${billing.multiplier.toFixed(2)}× pay rate`}
          />
        </dl>
      </section>

      <section className="panel p-4">
        <h3 className="text-sm font-medium">Where each billable hour goes</h3>
        <CostBar result={result} />
        <ul className="mt-3 grid grid-cols-2 gap-x-4 gap-y-1.5 text-xs">
          {result.composition.map((item) => (
            <li key={item.key} className="flex items-center justify-between gap-2">
              <span className="flex items-center gap-1.5 text-ink/70">
                <span className={`size-2 rounded-full ${SEGMENT_COLORS[item.key]}`} />
                {item.label}
              </span>
              <span className="tabular-nums">{usd(hourly(item.amount), true)}</span>
            </li>
          ))}
          {billing.profit != null && billing.profit > 0 && (
            <li className="flex items-center justify-between gap-2">
              <span className="flex items-center gap-1.5 text-ink/70">
                <span className="size-2 rounded-full bg-emerald-500" />
                Profit
              </span>
              <span className="tabular-nums">{usd(hourly(billing.profit), true)}</span>
            </li>
          )}
        </ul>
        {result.unbilled_hours > 0 && (
          <p className="mt-3 text-xs text-ink/55">
            Salary covers {result.paid_hours.toLocaleString()} hours; {result.hours.toLocaleString()} are billed. The {result.unbilled_hours.toLocaleString()}-hour gap ({usd(result.unbilled_value)} of pay for time off and holidays) is inside the cost per billable hour.
          </p>
        )}
      </section>

      {result.w2 && (
        <>
          <Breakdown title="Employer taxes" total={result.employer_taxes.total} open>
            {result.employer_taxes.rows.map((row) => (
              <Row key={row.key} label={row.label} note={row.note} amount={row.amount} />
            ))}
            {result.health.employee_total > 0 && (
              <p className="pt-1 text-xs text-ink/50">Taxed on {usd(result.employer_taxes.taxable_wages)}: the employee&apos;s premium share is pre-tax.</p>
            )}
          </Breakdown>

          <Breakdown title="401(k) burden" total={result.retirement.total}>
            {result.retirement.enabled ? (
              <>
                <Row label={`Company match (${pct(result.retirement.match_pct)})`} note={`On ${usd(result.retirement.matched_on)} of pay`} amount={result.retirement.total} />
                <Row label={`Employee contribution (${pct(result.retirement.employee_deferral_pct)})`} note="Paid by the employee" amount={result.retirement.employee_deferral} muted />
                {result.retirement.notes?.map((note) => (
                  <p key={note} className="text-xs text-amber-600">{note}</p>
                ))}
              </>
            ) : (
              <p className="text-sm text-ink/55">No 401(k) for this scenario.</p>
            )}
          </Breakdown>

          <Breakdown title={`Health benefits · ${result.health.tier_label}`} total={result.health.total} open>
            {result.health.rows.length ? (
              <table className="w-full text-sm tabular-nums">
                <thead>
                  <tr className="text-left text-[11px] uppercase tracking-wide text-ink/45">
                    <th className="pb-1 font-medium">Plan</th>
                    <th className="pb-1 text-right font-medium">Premium / mo</th>
                    <th className="pb-1 text-right font-medium">Company / mo</th>
                    <th className="pb-1 text-right font-medium">Company / yr</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-line">
                  {result.health.rows.map((row) => (
                    <tr key={row.key}>
                      <td className="py-1.5">{row.label}</td>
                      <td className="py-1.5 text-right text-ink/65">{usd(row.monthly_premium)}</td>
                      <td className="py-1.5 text-right">{usd(row.employer_monthly)}</td>
                      <td className="py-1.5 text-right font-medium">{usd(row.employer_annual)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            ) : (
              <p className="text-sm text-ink/55">No medical, dental, or vision coverage selected.</p>
            )}
            {result.health.employee_total > 0 && (
              <p className="pt-1 text-xs text-ink/55">The employee pays {usd(result.health.employee_total)} a year for dependents.</p>
            )}
          </Breakdown>

          {(result.other_benefits.total > 0 || result.overhead.amount > 0) && (
            <Breakdown title="Other benefits and overhead" total={result.other_benefits.total + result.overhead.amount}>
              {result.other_benefits.rows.map((row) => (
                <Row key={row.key} label={row.label} amount={row.amount} />
              ))}
              {result.overhead.amount > 0 && <Row label={`Overhead and G&A (${pct(result.overhead.pct)})`} amount={result.overhead.amount} />}
            </Breakdown>
          )}
        </>
      )}

      <Breakdown title="Rate for each margin" open>
        <ul className="flex flex-col gap-1">
          {billing.ladder.map((step) => {
            const current = billing.bill_rate != null && step.rate != null && billing.margin_pct != null && Math.abs(billing.margin_pct - step.margin_pct) < 2.5;
            return (
              <li key={step.margin_pct}>
                <button
                  type="button"
                  disabled={step.rate == null}
                  onClick={() => step.rate != null && onRate(step.rate)}
                  className={`flex w-full items-center justify-between rounded-lg px-2 py-1.5 text-sm tabular-nums transition hover:bg-pine/10 disabled:opacity-40 ${current ? "bg-pine/10 ring-1 ring-pine/30" : ""}`}
                >
                  <span className="text-ink/70">{step.margin_pct}% margin</span>
                  <span className="font-medium">{step.rate == null ? "Not reachable" : `${usd(step.rate, true)} / hr`}</span>
                </button>
              </li>
            );
          })}
        </ul>
        {billing.fee_pct > 0 && <p className="pt-1 text-xs text-ink/50">Includes the {pct(billing.fee_pct)} fee taken off the bill rate.</p>}
      </Breakdown>

      {result.employee && (
        <Breakdown title="Candidate take-home (estimate)" total={result.employee.take_home}>
          <Row label="Gross pay" amount={result.employee.gross} />
          {result.employee.rows.map((row) => (
            <Row key={row.key} label={row.label} amount={-row.amount} muted />
          ))}
          {result.employee.deductions.map((row) => (
            <Row key={row.key} label={row.label} amount={-row.amount} muted />
          ))}
          <div className="mt-1 grid grid-cols-3 gap-2 rounded-xl bg-desk p-2 text-center text-xs">
            <span>
              <span className="block font-medium tabular-nums">{usd(result.employee.monthly)}</span>
              <span className="text-ink/50">a month</span>
            </span>
            <span>
              <span className="block font-medium tabular-nums">{usd(result.employee.biweekly)}</span>
              <span className="text-ink/50">every two weeks</span>
            </span>
            <span>
              <span className="block font-medium tabular-nums">{pct(result.employee.effective_rate_pct)}</span>
              <span className="text-ink/50">tax rate</span>
            </span>
          </div>
        </Breakdown>
      )}

      {result.notes.map((note) => (
        <p key={note} className="text-xs text-ink/55">{note}</p>
      ))}
    </aside>
  );
}

function RateScale({ result }: { result: BurdenResult }) {
  const billing = result.billing;
  const marks = [
    { key: "pay", label: "Pay", value: result.pay_hourly, tone: "bg-ink/40" },
    { key: "cost", label: "Break-even", value: billing.break_even_rate, tone: "bg-red-500" },
    { key: "target", label: `${pct(billing.target_margin_pct)} target`, value: billing.target_rate, tone: "bg-emerald-500" },
  ].filter((mark): mark is { key: string; label: string; value: number; tone: string } => mark.value != null);
  const top = Math.max(...marks.map((mark) => mark.value), billing.bill_rate || 0) * 1.12;
  if (!top) return null;
  const left = (value: number) => `${Math.min(value / top, 1) * 100}%`;
  return (
    <div className="px-5 pb-5">
      <div className="relative mt-6 h-2 rounded-full bg-gradient-to-r from-red-500/25 via-amber-500/25 to-emerald-500/30">
        {marks.map((mark) => (
          <span key={mark.key} className="absolute top-1/2 -translate-x-1/2 -translate-y-1/2" style={{ left: left(mark.value) }}>
            <span className={`block h-4 w-0.5 rounded ${mark.tone}`} />
          </span>
        ))}
        {billing.bill_rate ? (
          <span className="absolute top-1/2 -translate-x-1/2 -translate-y-1/2 transition-all duration-300" style={{ left: left(billing.bill_rate) }}>
            <span className="block size-4 rounded-full border-2 border-card bg-pine shadow" />
            <span className="absolute bottom-5 left-1/2 -translate-x-1/2 whitespace-nowrap rounded-md bg-ink px-1.5 py-0.5 text-[11px] font-medium text-card tabular-nums">{usd(billing.bill_rate, true)}</span>
          </span>
        ) : null}
      </div>
      <div className="mt-2 flex flex-wrap gap-x-3 gap-y-1 text-[11px] text-ink/55">
        {marks.map((mark) => (
          <span key={mark.key} className="flex items-center gap-1 tabular-nums">
            <span className={`h-2.5 w-0.5 rounded ${mark.tone}`} />
            {mark.label} {usd(mark.value, true)}
          </span>
        ))}
      </div>
    </div>
  );
}

function CostBar({ result }: { result: BurdenResult }) {
  const profit = result.billing.profit != null && result.billing.profit > 0 ? result.billing.profit : 0;
  const whole = result.cost.annual + profit;
  const segments = [...result.composition.map((item) => ({ key: item.key, label: item.label, amount: item.amount })), ...(profit ? [{ key: "profit", label: "Profit", amount: profit }] : [])];
  return (
    <div className="mt-3 flex h-3 overflow-hidden rounded-full bg-ink/5" role="img" aria-label={segments.map((item) => `${item.label} ${usd(item.amount)}`).join(", ")}>
      {segments.map((item) => (
        <span key={item.key} className={`${SEGMENT_COLORS[item.key]} h-full transition-all duration-300`} style={{ width: `${(item.amount / whole) * 100}%` }} title={`${item.label}: ${usd(item.amount)}`} />
      ))}
    </div>
  );
}

function Stat({ label, value, detail }: { label: string; value: string; detail: string }) {
  return (
    <div className="bg-card px-4 py-3">
      <dt className="text-[11px] uppercase tracking-wide text-ink/45">{label}</dt>
      <dd className="mt-0.5 font-medium tabular-nums">{value}</dd>
      <dd className="text-xs text-ink/50">{detail}</dd>
    </div>
  );
}

function Breakdown({ title, total, open = false, children }: { title: string; total?: number; open?: boolean; children: ReactNode }) {
  return (
    <details open={open} className="panel group">
      <summary className="flex cursor-pointer list-none items-center justify-between gap-3 px-4 py-3 text-sm font-medium">
        <span>{title}</span>
        <span className="flex items-center gap-2 tabular-nums">
          {total != null && <span>{usd(total)}</span>}
          <ChevronDown className="size-4 text-ink/40 transition group-open:rotate-180" />
        </span>
      </summary>
      <div className="flex flex-col gap-1.5 border-t border-line px-4 py-3">{children}</div>
    </details>
  );
}

function Row({ label, note, amount, muted = false }: { label: string; note?: string; amount: number; muted?: boolean }) {
  return (
    <div className="flex items-baseline justify-between gap-3 text-sm">
      <span className="min-w-0">
        <span className={muted ? "text-ink/60" : ""}>{label}</span>
        {note && <span className="block text-xs text-ink/45">{note}</span>}
      </span>
      <span className={`shrink-0 tabular-nums ${muted ? "text-ink/60" : "font-medium"}`}>{amount < 0 ? `−${usd(-amount)}` : usd(amount)}</span>
    </div>
  );
}

function Group({ step, title, hint, disabled = false, children }: { step: string; title: string; hint: string; disabled?: boolean; children: ReactNode }) {
  return (
    <section className={`panel p-4 sm:p-5 ${disabled ? "opacity-60" : ""}`}>
      <div className="flex items-start gap-3">
        <span className="mt-0.5 grid size-6 shrink-0 place-items-center rounded-full bg-pine/15 text-xs font-semibold text-pine-deep">{step}</span>
        <div className="min-w-0">
          <h3 className="font-medium">{title}</h3>
          <p className="text-xs text-ink/55">{disabled ? "Not used for this pay type: no company benefits or employer taxes." : hint}</p>
        </div>
      </div>
      <fieldset disabled={disabled} className="mt-4 flex flex-col gap-3">
        {children}
      </fieldset>
    </section>
  );
}

function Disclosure({ title, children }: { title: string; children: ReactNode }) {
  return (
    <details className="group rounded-xl border border-line">
      <summary className="flex cursor-pointer list-none items-center justify-between px-3 py-2 text-sm text-ink/70">
        {title}
        <ChevronDown className="size-4 text-ink/40 transition group-open:rotate-180" />
      </summary>
      <div className="flex flex-col gap-3 border-t border-line p-3">{children}</div>
    </details>
  );
}

function Segmented({
  label,
  value,
  options,
  onChange,
}: {
  label: string;
  value: string;
  options: { value: string; label: string; hint?: string }[];
  onChange: (value: string) => void;
}) {
  return (
    <div role="radiogroup" aria-label={label} className="text-sm">
      <span className="text-ink/70">{label}</span>
      <div className="mt-1 flex flex-wrap gap-1 rounded-xl border border-line bg-desk/60 p-1">
        {options.map((option) => {
          const selected = option.value === value;
          return (
            <button
              key={option.value}
              type="button"
              role="radio"
              aria-checked={selected}
              title={option.hint}
              onClick={() => onChange(option.value)}
              className={`flex-1 whitespace-nowrap rounded-lg px-3 py-1.5 text-sm transition ${selected ? "bg-card font-medium text-ink shadow-sm ring-1 ring-line" : "text-ink/60 hover:text-ink"}`}
            >
              {option.label}
            </button>
          );
        })}
      </div>
    </div>
  );
}

function Toggle({ label, checked, onChange }: { label: string; checked: boolean; onChange: (value: boolean) => void }) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      onClick={() => onChange(!checked)}
      className={`inline-flex items-center gap-2 rounded-full border px-3 py-1.5 text-sm transition ${checked ? "border-pine/40 bg-pine/10 text-ink" : "border-line text-ink/60"}`}
    >
      <span className={`relative h-4 w-7 rounded-full transition ${checked ? "bg-pine" : "bg-ink/20"}`}>
        <span className={`absolute top-0.5 size-3 rounded-full bg-white shadow transition-all ${checked ? "left-3.5" : "left-0.5"}`} />
      </span>
      {label}
    </button>
  );
}

function Chip({ children, onClick, strong = false }: { children: ReactNode; onClick: () => void; strong?: boolean }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`rounded-full border px-2.5 py-1 tabular-nums transition hover:border-pine/50 ${strong ? "border-pine/40 bg-pine/10 text-pine-deep" : "border-line text-ink/70"}`}
    >
      {children}
    </button>
  );
}

function stable(inputs: Partial<BurdenInputs>): string {
  return JSON.stringify(Object.keys(inputs).sort().map((key) => [key, inputs[key as keyof BurdenInputs] ?? null]));
}

function formatNumber(value: number | null, cents: boolean): string {
  if (value == null) return "";
  return value.toLocaleString("en-US", { minimumFractionDigits: cents && value % 1 ? 2 : 0, maximumFractionDigits: 2 });
}

function NumberField({
  label,
  value,
  onChange,
  prefix,
  suffix,
  hint,
  placeholder,
  cents = false,
  min,
  disabled = false,
  emphasis = false,
  autoFocus = false,
}: {
  label: string;
  value: number | null;
  onChange: (value: number | null) => void;
  prefix?: string;
  suffix?: string;
  hint?: string;
  placeholder?: string;
  cents?: boolean;
  min?: number;
  disabled?: boolean;
  emphasis?: boolean;
  autoFocus?: boolean;
}) {
  const [text, setText] = useState(formatNumber(value, cents));
  const focused = useRef(false);

  useEffect(() => {
    if (!focused.current) setText(formatNumber(value, cents));
  }, [value, cents]);

  const below = min != null && value != null && value < min;
  return (
    <label className="text-sm">
      <span className="text-ink/70">{label}</span>
      <span
        className={`mt-1 flex h-10 items-center rounded-lg border bg-card px-3 shadow-sm transition focus-within:border-pine/60 focus-within:ring-4 focus-within:ring-pine/15 ${below ? "border-red-500/60" : "border-line"} ${emphasis ? "h-12 text-base" : ""} ${disabled ? "opacity-50" : ""}`}
      >
        {prefix && <span className="mr-1 text-ink/45">{prefix}</span>}
        <input
          value={text}
          inputMode="decimal"
          autoFocus={autoFocus}
          disabled={disabled}
          placeholder={placeholder}
          aria-label={label}
          aria-invalid={below || undefined}
          onFocus={() => {
            focused.current = true;
          }}
          onBlur={() => {
            focused.current = false;
            setText(formatNumber(value, cents));
          }}
          onChange={(event) => {
            const raw = event.target.value;
            setText(raw);
            const cleaned = raw.replace(/[$,\s%]/g, "");
            if (cleaned === "") {
              onChange(null);
              return;
            }
            const number = Number(cleaned);
            if (Number.isFinite(number) && number >= 0) onChange(number);
          }}
          className="w-full min-w-0 bg-transparent tabular-nums text-ink outline-none placeholder:text-ink/35"
        />
        {suffix && <span className="ml-2 shrink-0 whitespace-nowrap text-xs text-ink/45">{suffix}</span>}
      </span>
      {below ? <span className="mt-1 block text-xs text-red-600">Must be at least {min}%.</span> : hint && <span className="mt-1 block text-xs text-ink/50">{hint}</span>}
    </label>
  );
}

function summaryText(result: BurdenResult, subject?: string): string {
  const billing = result.billing;
  const lines = [
    subject ? `Burden: ${subject}` : "Burden calculation",
    `${result.pay_type_label}: ${usd(result.wages)} a year (${usd(result.pay_hourly, true)}/hr), ${result.hours.toLocaleString()} billable hours`,
    `Employer taxes ${usd(result.employer_taxes.total)} · 401(k) ${usd(result.retirement.total)} · Health ${usd(result.health.total)} · Other ${usd(result.other_benefits.total)}`,
    `Burden ${usd(result.burden.total)} (${pct(result.burden.pct)} of pay)`,
    `Fully loaded ${usd(result.cost.annual)} · ${usd(result.cost.hourly, true)} per billable hour`,
  ];
  if (billing.bill_rate) {
    lines.push(`Bill rate ${usd(billing.bill_rate, true)}/hr · profit ${signedUsd(billing.profit_hourly, true)}/hr (${signedUsd(billing.profit)} a year) · margin ${pct(billing.margin_pct)}`);
  }
  lines.push(`Break-even ${usd(billing.break_even_rate, true)}/hr · ${pct(billing.target_margin_pct)} margin needs ${usd(billing.target_rate, true)}/hr`);
  return lines.join("\n");
}
