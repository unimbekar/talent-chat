export type PayType = "w2_salary" | "w2_hourly" | "1099" | "c2c";
export type Tier = "employee" | "employee_spouse" | "employee_children" | "family";

export type BurdenInputs = {
  pay_type: PayType;
  salary: number | null;
  pay_rate: number | null;
  hours: number;
  paid_hours: number;
  medical: boolean;
  dental: boolean;
  vision: boolean;
  tier: Tier;
  dependent_share_pct: number;
  medical_monthly: number | null;
  dental_monthly: number | null;
  vision_monthly: number | null;
  medical_dependents_monthly: number | null;
  dental_dependents_monthly: number | null;
  vision_dependents_monthly: number | null;
  life_disability: boolean;
  life_monthly: number;
  std_monthly: number;
  ltd_monthly: number;
  training_annual: number;
  wellness_annual: number;
  other_annual: number;
  retirement: boolean;
  match_pct: number;
  employee_deferral_pct: number | null;
  state: "VA" | "MD" | "DC" | "other";
  suta_rate: number | null;
  suta_wage_base: number | null;
  futa_rate: number;
  workers_comp_pct: number;
  filing_status: "single" | "married";
  federal_mode: "estimate" | "flat";
  federal_rate_pct: number;
  state_mode: "va" | "flat" | "none";
  state_rate_pct: number;
  bill_rate: number | null;
  fee_pct: number;
  overhead_pct: number;
  target_margin_pct: number;
};

export type Line = { key: string; label: string; amount: number; rate?: number; base?: number; note?: string };

export type HealthRow = {
  key: string;
  label: string;
  monthly_premium: number;
  employer_monthly: number;
  employee_monthly: number;
  employer_annual: number;
  employee_annual: number;
};

export type BurdenStatus = "profit" | "thin" | "loss" | "unpriced";

export type BurdenResult = {
  tax_year: number;
  pay_type: PayType;
  pay_type_label: string;
  w2: boolean;
  wages: number;
  pay_hourly: number;
  hours: number;
  paid_hours: number;
  unbilled_hours: number;
  unbilled_value: number;
  employer_taxes: { rows: Line[]; total: number; taxable_wages: number };
  retirement: {
    enabled: boolean;
    total: number;
    match_pct: number;
    employee_deferral_pct?: number;
    employee_deferral: number;
    matched_on?: number;
    effective_pct?: number;
    notes?: string[];
  };
  health: { tier: Tier; tier_label: string; rows: HealthRow[]; total: number; employee_total: number };
  other_benefits: { rows: Line[]; total: number };
  overhead: { pct: number; amount: number };
  burden: { total: number; pct: number };
  cost: { annual: number; hourly: number; monthly: number };
  billing: {
    bill_rate: number | null;
    fee_pct: number;
    fee?: number;
    net_revenue?: number;
    break_even_rate: number | null;
    target_margin_pct: number;
    target_rate: number | null;
    ladder: { margin_pct: number; rate: number | null }[];
    revenue: number | null;
    profit: number | null;
    profit_hourly: number | null;
    margin_pct: number | null;
    markup_pct: number | null;
    multiplier: number | null;
    status: BurdenStatus;
  };
  employee: {
    gross: number;
    rows: Line[];
    taxes_total: number;
    effective_rate_pct: number;
    deductions: Line[];
    take_home: number;
    monthly: number;
    biweekly: number;
  } | null;
  composition: { key: string; label: string; amount: number; pct: number }[];
  notes: string[];
};

export type BurdenDefaults = {
  tax_year: number;
  inputs: BurdenInputs;
  pay_types: Record<PayType, string>;
  tiers: Record<Tier, string>;
  plans: Record<string, string>;
  premiums: Record<string, Record<Tier, number>>;
  states: Record<string, { label: string; suta_rate: number; suta_wage_base: number }>;
  match_minimum: number;
  limits: { ss_wage_base: number; futa_wage_base: number; deferral_limit: number; comp_limit: number };
};

export type SavedBurden = {
  saved: boolean;
  saved_at: string | null;
  inputs: BurdenInputs;
  result: BurdenResult | null;
};

export type BurdenSummary = {
  bill_rate: number | null;
  cost_hourly: number;
  profit_hourly: number | null;
  margin_pct: number | null;
  status: BurdenStatus;
};

export function usd(amount: number | null | undefined, cents = false): string {
  if (amount == null || Number.isNaN(amount)) return "—";
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    minimumFractionDigits: cents ? 2 : 0,
    maximumFractionDigits: cents ? 2 : 0,
  }).format(amount);
}

export function signedUsd(amount: number | null | undefined, cents = false): string {
  if (amount == null) return "—";
  const text = usd(Math.abs(amount), cents);
  return amount < 0 ? `−${text}` : `+${text}`;
}

export function pct(value: number | null | undefined, digits = 1): string {
  if (value == null || Number.isNaN(value)) return "—";
  return `${value.toFixed(digits).replace(/\.0+$/, "")}%`;
}

export const STATUS_TONE: Record<BurdenStatus, string> = {
  profit: "border-emerald-500/35 bg-emerald-500/10 text-emerald-600",
  thin: "border-amber-500/40 bg-amber-500/10 text-amber-600",
  loss: "border-red-500/40 bg-red-500/10 text-red-600",
  unpriced: "border-line bg-desk text-ink/60",
};

export const STATUS_LABEL: Record<BurdenStatus, string> = {
  profit: "Profitable",
  thin: "Thin margin",
  loss: "Loss",
  unpriced: "No rate yet",
};
