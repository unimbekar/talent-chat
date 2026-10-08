type Point = { label: string; count: number };

export function Columns({
  series,
  empty,
}: {
  series: { name: string; tone: string; points: Point[] }[];
  empty: string;
}) {
  const labels = series[0]?.points.map((point) => point.label) || [];
  const peak = Math.max(1, ...series.flatMap((item) => item.points.map((point) => point.count)));
  if (!labels.length || series.every((item) => item.points.every((point) => point.count === 0))) {
    return <p className="text-sm text-ink/55">{empty}</p>;
  }
  return (
    <div className="overflow-x-auto">
      <div className="flex min-w-max items-end gap-2" style={{ height: 160 }}>
        {labels.map((label, index) => (
          <div key={`${label}-${index}`} className="flex w-10 flex-col items-center justify-end gap-1">
            <div className="flex h-32 items-end gap-0.5">
              {series.map((item) => {
                const count = item.points[index]?.count || 0;
                return (
                  <div
                    key={item.name}
                    title={`${item.name}: ${count}`}
                    className={`w-3 rounded-t ${item.tone}`}
                    style={{ height: `${Math.max(count ? 6 : 0, (count / peak) * 128)}px` }}
                  />
                );
              })}
            </div>
            <span className="text-[10px] text-ink/45">{label}</span>
          </div>
        ))}
      </div>
      <div className="mt-2 flex flex-wrap gap-3 text-xs text-ink/60">
        {series.map((item) => (
          <span key={item.name} className="inline-flex items-center gap-1.5">
            <span className={`inline-block size-2.5 rounded-sm ${item.tone}`} />
            {item.name}
          </span>
        ))}
      </div>
    </div>
  );
}

export function Bars({ points, empty }: { points: Point[]; empty: string }) {
  const shown = points.filter((point) => point.count > 0);
  const peak = Math.max(1, ...shown.map((point) => point.count));
  if (!shown.length) return <p className="text-sm text-ink/55">{empty}</p>;
  return (
    <ul className="flex flex-col gap-2">
      {shown.map((point) => (
        <li key={point.label}>
          <div className="mb-1 flex items-baseline justify-between gap-3 text-sm">
            <span className="truncate">{point.label}</span>
            <span className="tabular-nums text-ink/60">{point.count}</span>
          </div>
          <div className="h-2 overflow-hidden rounded-full bg-line">
            <div className="h-full rounded-full bg-pine" style={{ width: `${(point.count / peak) * 100}%` }} />
          </div>
        </li>
      ))}
    </ul>
  );
}

export function Funnel({ points }: { points: Point[] }) {
  const peak = Math.max(1, ...points.map((point) => point.count));
  if (points.every((point) => point.count === 0)) {
    return <p className="text-sm text-ink/55">No one is in the pipeline right now.</p>;
  }
  return (
    <ol className="flex flex-col gap-2">
      {points.map((point) => (
        <li key={point.label} className="grid grid-cols-[7.5rem_1fr_2.5rem] items-center gap-3 text-sm">
          <span>{point.label}</span>
          <div className="h-7 overflow-hidden rounded-md bg-desk">
            <div
              className="flex h-full items-center rounded-md bg-night/90 px-2 text-xs text-white"
              style={{ width: `${Math.max(point.count ? 8 : 0, (point.count / peak) * 100)}%` }}
            >
              {point.count > 0 ? point.count : ""}
            </div>
          </div>
          <span className="text-right tabular-nums text-ink/55">{point.count}</span>
        </li>
      ))}
    </ol>
  );
}
