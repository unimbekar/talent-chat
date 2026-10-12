"use client";

import { BurdenCalculator } from "@/components/burden/burden-calculator";

export default function BurdenPage() {
  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="page-title">Burden calculator</h1>
        <p className="page-lead">
          Work out what a hire costs the company: employer taxes, the 401(k) match, health benefits, and the profit or loss at a candidate hourly rate. To keep a calculation with a candidate, open their submission from the pipeline.
        </p>
      </div>
      <BurdenCalculator initial={{}} />
    </div>
  );
}
