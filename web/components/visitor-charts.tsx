"use client";

import { type KeyboardEvent, type PointerEvent, type ReactNode, useEffect, useId, useRef, useState } from "react";

import { count, percent, shortDay } from "@/lib/visitors";

export const TONES = {
  brand: "var(--brand)",
  sky: "56 189 248",
  emerald: "16 185 129",
  amber: "245 158 11",
  violet: "139 92 246",
  rose: "244 63 94",
} as const;

export type Tone = keyof typeof TONES;

function rgb(tone: Tone, alpha = 1): string {
  return `rgb(${TONES[tone]} / ${alpha})`;
}

function useWidth<T extends HTMLElement>() {
  const ref = useRef<T>(null);
  const [width, setWidth] = useState(0);
  useEffect(() => {
    const node = ref.current;
    if (!node) return;
    const update = () => setWidth(node.clientWidth);
    update();
    const observer = new ResizeObserver(update);
    observer.observe(node);
    return () => observer.disconnect();
  }, []);
  return [ref, width] as const;
}

/** Whole-number gridlines: 1, 2, or 5 times a power of ten, at least four steps tall. */
function scale(max: number): { step: number; top: number; ticks: number } {
  const value = Math.max(4, max);
  const raw = value / 4;
  const power = 10 ** Math.floor(Math.log10(raw));
  const step = Math.max(1, [1, 2, 5, 10].map((multiple) => multiple * power).find((candidate) => candidate >= raw) ?? 10 * power);
  const ticks = Math.ceil(value / step);
  return { step, top: step * ticks, ticks };
}

/** Monotone cubic curve (Fritsch–Carlson), so the line never dips below zero between days. */
function monotone(points: [number, number][]): string {
  const n = points.length;
  if (n === 0) return "";
  if (n === 1) return `M${points[0][0]},${points[0][1]}`;
  const dx: number[] = [];
  const slope: number[] = [];
  for (let i = 0; i < n - 1; i++) {
    dx[i] = points[i + 1][0] - points[i][0];
    slope[i] = (points[i + 1][1] - points[i][1]) / dx[i];
  }
  const m: number[] = [slope[0]];
  for (let i = 1; i < n - 1; i++) m[i] = slope[i - 1] * slope[i] <= 0 ? 0 : (slope[i - 1] + slope[i]) / 2;
  m[n - 1] = slope[n - 2];
  for (let i = 0; i < n - 1; i++) {
    if (slope[i] === 0) {
      m[i] = 0;
      m[i + 1] = 0;
      continue;
    }
    const a = m[i] / slope[i];
    const b = m[i + 1] / slope[i];
    const h = a * a + b * b;
    if (h > 9) {
      const t = 3 / Math.sqrt(h);
      m[i] = t * a * slope[i];
      m[i + 1] = t * b * slope[i];
    }
  }
  let path = `M${points[0][0]},${points[0][1]}`;
  for (let i = 0; i < n - 1; i++) {
    const third = dx[i] / 3;
    path += ` C${points[i][0] + third},${points[i][1] + m[i] * third} ${points[i + 1][0] - third},${points[i + 1][1] - m[i + 1] * third} ${points[i + 1][0]},${points[i + 1][1]}`;
  }
  return path;
}

const PAD = { left: 40, right: 14, top: 22, bottom: 30 };

export function TrendChart({
  dates,
  values,
  label,
  tone = "brand",
  variant = "area",
  height = 260,
  showAverage = true,
  emptyText = "Nothing to show for this range yet.",
  markLabel = "Peak",
  tooltip,
}: {
  dates: string[];
  values: number[];
  label: string;
  tone?: Tone;
  variant?: "area" | "bars";
  height?: number;
  showAverage?: boolean;
  emptyText?: string;
  /** Words before the highest value's marker. */
  markLabel?: string;
  tooltip: (index: number) => ReactNode;
}) {
  const [box, width] = useWidth<HTMLDivElement>();
  const [active, setActive] = useState<number | null>(null);
  const gradient = `fill-${useId().replace(/[^a-zA-Z0-9_-]/g, "")}`;
  const n = values.length;
  const max = Math.max(0, ...values);
  const { step, top, ticks } = scale(max);
  const plotW = Math.max(0, width - PAD.left - PAD.right);
  const plotH = height - PAD.top - PAD.bottom;
  const band = n ? plotW / n : 0;
  const x = (index: number) => PAD.left + band * (index + 0.5);
  const y = (value: number) => PAD.top + plotH - (value / top) * plotH;
  const total = values.reduce((sum, value) => sum + value, 0);
  const average = n ? total / n : 0;
  const peakIndex = values.indexOf(max);
  const empty = total === 0;

  const labelCount = Math.max(2, Math.min(n, Math.floor(plotW / 72)));
  const stride = Math.max(1, Math.ceil((n - 1) / (labelCount - 1)));
  const labelIndexes = Array.from({ length: Math.floor((n - 1) / stride) + 1 }, (_, k) => n - 1 - k * stride).reverse();

  const points: [number, number][] = values.map((value, index) => [x(index), y(value)]);
  const line = monotone(points);
  const area = n ? `${line} L${x(n - 1)},${y(0)} L${x(0)},${y(0)} Z` : "";

  function pick(event: PointerEvent<SVGSVGElement>) {
    if (!n || !band) return;
    const bounds = event.currentTarget.getBoundingClientRect();
    const index = Math.floor((event.clientX - bounds.left - PAD.left) / band);
    setActive(Math.min(n - 1, Math.max(0, index)));
  }

  function onKey(event: KeyboardEvent<SVGSVGElement>) {
    if (!n) return;
    if (event.key === "ArrowRight" || event.key === "ArrowLeft") {
      event.preventDefault();
      const delta = event.key === "ArrowRight" ? 1 : -1;
      setActive((current) => Math.min(n - 1, Math.max(0, (current ?? (delta > 0 ? -1 : n)) + delta)));
    } else if (event.key === "Home") {
      setActive(0);
    } else if (event.key === "End") {
      setActive(n - 1);
    } else if (event.key === "Escape") {
      setActive(null);
    }
  }

  const tipX = active == null ? 0 : x(active);
  const tipShift = tipX > width / 2 ? "calc(-100% - 14px)" : "14px";

  return (
    <div ref={box} className="relative w-full select-none" style={{ height }}>
      {width > 0 && (
        <svg
          width={width}
          height={height}
          role="img"
          aria-label={`${label}: ${count(total)} across ${n} days, peak ${count(max)}. Use the arrow keys to read each day.`}
          tabIndex={0}
          className="rounded-lg outline-none focus-visible:ring-2 focus-visible:ring-pine/40"
          onPointerMove={pick}
          onPointerDown={pick}
          onPointerLeave={() => setActive(null)}
          onKeyDown={onKey}
          onBlur={() => setActive(null)}
        >
          <defs>
            <linearGradient id={gradient} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={rgb(tone, 0.32)} />
              <stop offset="100%" stopColor={rgb(tone, 0)} />
            </linearGradient>
          </defs>
          {Array.from({ length: ticks + 1 }, (_, tick) => {
            const value = tick * step;
            return (
              <g key={tick}>
                <line x1={PAD.left} x2={width - PAD.right} y1={y(value)} y2={y(value)} stroke="rgb(var(--line))" strokeDasharray={tick ? "3 4" : undefined} />
                <text x={PAD.left - 8} y={y(value)} dy="0.32em" textAnchor="end" fontSize="11" fill="rgb(var(--ink) / 0.45)">
                  {count(value)}
                </text>
              </g>
            );
          })}
          {labelIndexes.map((index) => (
            <text key={index} x={x(index)} y={height - 8} textAnchor="middle" fontSize="11" fill="rgb(var(--ink) / 0.5)">
              {dates[index] ? shortDay(dates[index]) : ""}
            </text>
          ))}

          {variant === "bars"
            ? values.map((value, index) => {
                const barW = Math.max(2, Math.min(28, band * 0.62));
                const barH = Math.max(value ? 3 : 0, y(0) - y(value));
                return (
                  <rect
                    key={index}
                    x={x(index) - barW / 2}
                    y={y(0) - barH}
                    width={barW}
                    height={barH}
                    rx={Math.min(4, barW / 3)}
                    fill={rgb(tone, active == null || active === index ? 0.9 : 0.45)}
                  />
                );
              })
            : !empty && (
                <>
                  <path d={area} fill={`url(#${gradient})`} />
                  <path d={line} fill="none" stroke={rgb(tone)} strokeWidth={2.25} strokeLinecap="round" strokeLinejoin="round" />
                  {n <= 31 &&
                    points.map(([px, py], index) => (
                      <circle key={index} cx={px} cy={py} r={2.6} fill="rgb(var(--card))" stroke={rgb(tone)} strokeWidth={1.6} />
                    ))}
                </>
              )}

          {showAverage && !empty && n > 1 && (
            <g>
              <line x1={PAD.left} x2={width - PAD.right} y1={y(average)} y2={y(average)} stroke="rgb(var(--ink) / 0.4)" strokeDasharray="6 5" />
              <text x={width - PAD.right} y={y(average) - 6} textAnchor="end" fontSize="10.5" fill="rgb(var(--ink) / 0.55)">
                avg {average >= 10 ? Math.round(average) : average.toFixed(1)}/day
              </text>
            </g>
          )}

          {!empty && max > 0 && active == null && (
            <g>
              <circle cx={x(peakIndex)} cy={y(max)} r={4.5} fill={rgb(tone)} stroke="rgb(var(--card))" strokeWidth={2} />
              <text
                x={x(peakIndex)}
                y={y(max) - 10}
                textAnchor={x(peakIndex) < 60 ? "start" : x(peakIndex) > width - 60 ? "end" : "middle"}
                fontSize="11"
                fontWeight="600"
                fill={rgb(tone)}
              >
                {markLabel} {count(max)}
              </text>
            </g>
          )}

          {active != null && !empty && (
            <g pointerEvents="none">
              <line x1={x(active)} x2={x(active)} y1={PAD.top} y2={y(0)} stroke="rgb(var(--ink) / 0.25)" />
              {variant === "area" && <circle cx={x(active)} cy={y(values[active])} r={5} fill={rgb(tone)} stroke="rgb(var(--card))" strokeWidth={2} />}
            </g>
          )}

          {empty && (
            <text x={PAD.left + plotW / 2} y={PAD.top + plotH / 2} textAnchor="middle" fontSize="13" fill="rgb(var(--ink) / 0.5)">
              {emptyText}
            </text>
          )}
        </svg>
      )}
      {active != null && width > 0 && !empty && (
        <div
          className="pointer-events-none absolute z-10 min-w-44 rounded-xl border border-line bg-card px-3 py-2 text-xs shadow-lift"
          style={{ left: tipX, top: PAD.top, transform: `translateX(${tipShift})` }}
          role="status"
        >
          {tooltip(active)}
        </div>
      )}
      <table className="sr-only">
        <caption>{label}</caption>
        <tbody>
          {dates.map((date, index) => (
            <tr key={date}>
              <th scope="row">{date}</th>
              <td>{values[index]}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function Sparkline({ values, tone = "brand", height = 44 }: { values: number[]; tone?: Tone; height?: number }) {
  const [box, width] = useWidth<HTMLDivElement>();
  const gradient = `spark-${useId().replace(/[^a-zA-Z0-9_-]/g, "")}`;
  const n = values.length;
  const max = Math.max(1, ...values);
  const x = (index: number) => (n <= 1 ? width / 2 : (index * (width - 4)) / (n - 1) + 2);
  const y = (value: number) => height - 3 - (value / max) * (height - 8);
  const line = monotone(values.map((value, index) => [x(index), y(value)]));
  return (
    <div ref={box} className="w-full" style={{ height }} aria-hidden="true">
      {width > 0 && n > 0 && (
        <svg width={width} height={height}>
          <defs>
            <linearGradient id={gradient} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={rgb(tone, 0.3)} />
              <stop offset="100%" stopColor={rgb(tone, 0)} />
            </linearGradient>
          </defs>
          <path d={`${line} L${x(n - 1)},${height} L${x(0)},${height} Z`} fill={`url(#${gradient})`} />
          <path d={line} fill="none" stroke={rgb(tone)} strokeWidth={2} strokeLinecap="round" />
          <circle cx={x(n - 1)} cy={y(values[n - 1])} r={3} fill={rgb(tone)} />
        </svg>
      )}
    </div>
  );
}

const DONUT_TONES: Tone[] = ["brand", "sky", "emerald", "amber", "violet", "rose"];

export function Donut({ items, center, empty }: { items: { label: string; count: number }[]; center: string; empty: string }) {
  const total = items.reduce((sum, item) => sum + item.count, 0);
  if (!total) return <p className="text-sm text-ink/55">{empty}</p>;
  const radius = 54;
  const circumference = 2 * Math.PI * radius;
  let offset = 0;
  return (
    <div className="flex flex-wrap items-center gap-6">
      <svg width={148} height={148} viewBox="0 0 148 148" role="img" aria-label={items.map((item) => `${item.label} ${percent(item.count, total)}`).join(", ")}>
        <g transform="rotate(-90 74 74)">
          <circle cx={74} cy={74} r={radius} fill="none" stroke="rgb(var(--line))" strokeWidth={16} />
          {items.map((item, index) => {
            const length = (item.count / total) * circumference;
            const gap = items.length > 1 ? Math.min(2, length / 4) : 0;
            const segment = (
              <circle
                key={item.label}
                cx={74}
                cy={74}
                r={radius}
                fill="none"
                stroke={rgb(DONUT_TONES[index % DONUT_TONES.length])}
                strokeWidth={16}
                strokeDasharray={`${Math.max(0, length - gap)} ${circumference}`}
                strokeDashoffset={-offset}
              />
            );
            offset += length;
            return segment;
          })}
        </g>
        <text x={74} y={70} textAnchor="middle" fontSize="22" fontWeight="600" fill="rgb(var(--ink))">
          {count(total)}
        </text>
        <text x={74} y={90} textAnchor="middle" fontSize="11" fill="rgb(var(--ink) / 0.55)">
          {center}
        </text>
      </svg>
      <ul className="flex min-w-40 flex-1 flex-col gap-2 text-sm">
        {items.map((item, index) => (
          <li key={item.label} className="flex items-center justify-between gap-3">
            <span className="inline-flex items-center gap-2">
              <span className="inline-block size-2.5 rounded-full" style={{ background: rgb(DONUT_TONES[index % DONUT_TONES.length]) }} />
              {item.label}
            </span>
            <span className="tabular-nums text-ink/60">
              {count(item.count)} · {percent(item.count, total)}
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}

export function VisitorFunnel({ steps }: { steps: { key: string; label: string; count: number }[] }) {
  const first = steps[0]?.count || 0;
  if (!first) return <p className="text-sm text-ink/55">No visits in this range yet, so there is nothing to follow through.</p>;
  return (
    <ol className="flex flex-col gap-3">
      {steps.map((step, index) => {
        const previous = index ? steps[index - 1].count : 0;
        const share = Math.min(100, (step.count / first) * 100);
        return (
          <li key={step.key}>
            <div className="mb-1 flex items-baseline justify-between gap-3 text-sm">
              <span>{step.label}</span>
              <span className="tabular-nums">
                <span className="font-medium">{count(step.count)}</span>
                <span className="text-ink/50"> · {percent(step.count, first)} of visitors</span>
              </span>
            </div>
            <div className="h-8 overflow-hidden rounded-lg bg-desk">
              <div
                className="h-full rounded-lg transition-[width] duration-500"
                style={{ width: `${Math.max(step.count ? 6 : 0, share)}%`, background: rgb(DONUT_TONES[index % DONUT_TONES.length], 0.9) }}
              />
            </div>
            {index > 0 && previous > 0 && (
              <p className="mt-1 text-xs text-ink/50">{percent(step.count, previous)} of the step before</p>
            )}
          </li>
        );
      })}
    </ol>
  );
}
