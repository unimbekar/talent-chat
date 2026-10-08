import { STAGE_TONE } from "@/lib/pipeline";

export function StageBadge({ stage, label }: { stage: string; label: string }) {
  return (
    <span className={`inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-medium ${STAGE_TONE[stage] || STAGE_TONE.submitted}`}>
      {label}
    </span>
  );
}
