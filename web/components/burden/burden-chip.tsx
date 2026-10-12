import { Calculator } from "lucide-react";

import { pct, signedUsd, STATUS_TONE, usd, type BurdenSummary } from "@/lib/burden";

export function BurdenChip({ summary }: { summary: BurdenSummary }) {
  const priced = summary.bill_rate != null && summary.profit_hourly != null;
  const text = priced
    ? `${signedUsd(summary.profit_hourly, true)}/hr · ${pct(summary.margin_pct)}`
    : `Cost ${usd(summary.cost_hourly, true)}/hr`;
  const title = priced
    ? `Bill ${usd(summary.bill_rate, true)}/hr, loaded cost ${usd(summary.cost_hourly, true)}/hr`
    : "No candidate hourly rate saved yet";
  return (
    <span title={title} className={`inline-flex items-center gap-1 whitespace-nowrap rounded-full border px-2 py-0.5 text-xs font-medium tabular-nums ${STATUS_TONE[summary.status]}`}>
      <Calculator className="size-3" />
      {text}
    </span>
  );
}
