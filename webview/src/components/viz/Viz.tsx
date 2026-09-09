import { useId, type ReactNode } from "react";
import s from "./viz.module.css";

/**
 * Data-visualisation primitives.
 *
 * Hand-drawn SVG rather than a charting library: every one of these is a few
 * dozen lines, the bundle stays small, and — the part that matters — each can
 * be made properly accessible. A chart nobody can read with a screen reader
 * is decoration, so every component here carries a text alternative that
 * states the same fact the picture does, and none of them uses colour as the
 * only signal.
 *
 * All geometry is computed from the data with no animation of layout: what
 * moves is `stroke-dashoffset`, `opacity` or `transform`, so drawing stays on
 * the compositor and a panel of twenty sparklines does not cost a frame.
 */

/** Health, shared by every primitive that colours by state. */
export type Signal = "ok" | "warn" | "fail" | "idle" | "accent";

const SIGNAL_VAR: Readonly<Record<Signal, string>> = {
  ok: "var(--ml-signal-ok)",
  warn: "var(--ml-signal-warn)",
  fail: "var(--ml-signal-fail)",
  idle: "var(--ml-signal-idle)",
  accent: "var(--ml-accent)",
};

export function signalColor(signal: Signal): string {
  return SIGNAL_VAR[signal];
}

/**
 * A trend line. Reads the shape of a series at a glance; the accessible name
 * carries the numbers the shape is standing in for.
 */
export function Sparkline({
  values,
  label,
  signal = "accent",
  width = 96,
  height = 26,
  fill = true,
}: {
  values: readonly number[];
  /** Stated to assistive technology in place of the drawing. */
  label: string;
  signal?: Signal;
  width?: number;
  height?: number;
  fill?: boolean;
}) {
  const gradientId = useId();
  if (values.length < 2)
    return (
      <span className={s.sparkEmpty} role="img" aria-label={`${label}: not enough data to plot`}>
        —
      </span>
    );

  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = max - min || 1;
  const step = width / (values.length - 1);
  // 1px inset top and bottom so a flat maximum is not clipped by the viewBox.
  const points = values.map((value, index) => {
    const x = index * step;
    const y = height - 1 - ((value - min) / span) * (height - 2);
    return `${x.toFixed(2)},${y.toFixed(2)}`;
  });
  const line = `M${points.join(" L")}`;
  const area = `${line} L${width},${height} L0,${height} Z`;
  const last = values[values.length - 1];
  const first = values[0];
  const direction = last > first ? "rising" : last < first ? "falling" : "flat";

  return (
    <svg
      className={s.spark}
      viewBox={`0 0 ${width} ${height}`}
      width={width}
      height={height}
      preserveAspectRatio="none"
      role="img"
      aria-label={`${label}: ${direction}, from ${first} to ${last}, low ${min}, high ${max}`}
    >
      {fill ? (
        <>
          <defs>
            <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={signalColor(signal)} stopOpacity="0.34" />
              <stop offset="100%" stopColor={signalColor(signal)} stopOpacity="0" />
            </linearGradient>
          </defs>
          <path d={area} fill={`url(#${gradientId})`} />
        </>
      ) : null}
      <path
        d={line}
        fill="none"
        stroke={signalColor(signal)}
        strokeWidth="1.5"
        strokeLinecap="round"
        strokeLinejoin="round"
        vectorEffect="non-scaling-stroke"
      />
    </svg>
  );
}

/**
 * A progress ring. Used wherever a count is really "n of m" — phases covered,
 * pods ready, gate conditions passing — because the fraction is the fact and
 * two bare numbers make the reader do the division.
 */
export function Ring({
  value,
  total,
  label,
  signal,
  size = 46,
  caption,
}: {
  value: number;
  total: number;
  label: string;
  signal?: Signal;
  size?: number;
  /** Drawn in the middle. Defaults to the value. */
  caption?: string;
}) {
  const safeTotal = total > 0 ? total : 1;
  const fraction = Math.max(0, Math.min(1, value / safeTotal));
  const radius = (size - 6) / 2;
  const circumference = 2 * Math.PI * radius;
  const tone: Signal =
    signal ?? (fraction >= 1 ? "ok" : fraction >= 0.5 ? "warn" : fraction > 0 ? "fail" : "idle");

  return (
    <svg
      className={s.ring}
      viewBox={`0 0 ${size} ${size}`}
      width={size}
      height={size}
      role="img"
      aria-label={`${label}: ${value} of ${total}`}
    >
      <circle
        cx={size / 2}
        cy={size / 2}
        r={radius}
        fill="none"
        stroke="var(--ml-hairline)"
        strokeWidth="3"
      />
      <circle
        className={s.ringValue}
        cx={size / 2}
        cy={size / 2}
        r={radius}
        fill="none"
        stroke={signalColor(tone)}
        strokeWidth="3"
        strokeLinecap="round"
        strokeDasharray={circumference}
        strokeDashoffset={circumference * (1 - fraction)}
        transform={`rotate(-90 ${size / 2} ${size / 2})`}
      />
      <text
        className={s.ringText}
        x="50%"
        y="50%"
        dominantBaseline="central"
        textAnchor="middle"
        fill="var(--ml-text-primary)"
      >
        {caption ?? value}
      </text>
    </svg>
  );
}

export interface BarSegment {
  label: string;
  value: number;
  /** An explicit colour wins; otherwise the signal decides. */
  color?: string;
  signal?: Signal;
}

/**
 * A single stacked bar with a legend. The legend is the accessible version —
 * it lists every segment with its number, so nothing is only in the picture.
 */
export function StackedBar({
  segments,
  label,
  height = 8,
  legend = true,
}: {
  segments: readonly BarSegment[];
  label: string;
  height?: number;
  legend?: boolean;
}) {
  const total = segments.reduce((sum, segment) => sum + segment.value, 0);
  if (total <= 0)
    return (
      <p className={s.legendEmpty} role="img" aria-label={`${label}: nothing to show`}>
        Nothing recorded yet.
      </p>
    );
  return (
    <div className={s.stack}>
      <div
        className={s.stackTrack}
        style={{ height }}
        role="img"
        aria-label={`${label}: ${segments
          .filter((segment) => segment.value > 0)
          .map((segment) => `${segment.label} ${segment.value}`)
          .join(", ")}`}
      >
        {segments
          .filter((segment) => segment.value > 0)
          .map((segment) => (
            <span
              key={segment.label}
              className={s.stackSegment}
              style={{
                width: `${(segment.value / total) * 100}%`,
                background: segment.color ?? signalColor(segment.signal ?? "accent"),
              }}
            />
          ))}
      </div>
      {legend ? (
        <ul className={s.legend}>
          {segments.map((segment) => (
            <li key={segment.label} className={s.legendItem}>
              <span
                className={s.legendSwatch}
                style={{
                  background: segment.color ?? signalColor(segment.signal ?? "accent"),
                }}
                aria-hidden="true"
              />
              {segment.label}
              <strong>{segment.value}</strong>
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}

/**
 * A row of state cells — one per run, pod, build or job. Each carries a title
 * and a shape as well as a hue, so the strip is readable in monochrome and by
 * anyone who cannot separate red from green.
 */
export function HeatStrip({
  cells,
  label,
  max = 40,
}: {
  cells: readonly { id: string; signal: Signal; title: string }[];
  label: string;
  max?: number;
}) {
  const shown = cells.slice(0, max);
  if (!shown.length)
    return <p className={s.legendEmpty}>Nothing recorded yet.</p>;
  return (
    <div className={s.heat} role="img" aria-label={`${label}: ${summarise(shown)}`}>
      {shown.map((cell) => (
        <span
          key={cell.id}
          className={`${s.heatCell} ${s[`heat_${cell.signal}`]}`}
          title={cell.title}
        />
      ))}
    </div>
  );
}

function summarise(cells: readonly { signal: Signal }[]): string {
  const counts = new Map<Signal, number>();
  for (const cell of cells) counts.set(cell.signal, (counts.get(cell.signal) ?? 0) + 1);
  return (
    [...counts]
      .map(([signal, count]) => `${count} ${signal}`)
      .join(", ") || "nothing"
  );
}

/** A labelled horizontal meter, for a single 0–1 measure. */
export function Meter({
  value,
  label,
  caption,
  signal = "accent",
}: {
  value: number;
  label: string;
  caption?: string;
  signal?: Signal;
}) {
  const fraction = Math.max(0, Math.min(1, value));
  return (
    <div className={s.meter}>
      <div className={s.meterHead}>
        <span>{label}</span>
        <strong>{caption ?? `${Math.round(fraction * 100)}%`}</strong>
      </div>
      <div
        className={s.meterTrack}
        role="meter"
        aria-valuenow={Math.round(fraction * 100)}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-label={label}
      >
        <span
          className={s.meterFill}
          style={{ width: `${fraction * 100}%`, background: signalColor(signal) }}
        />
      </div>
    </div>
  );
}

/**
 * A status dot that is also a shape. `●` full, `◐` half, `○` ring, `▲`
 * warning — so the state survives greyscale, and the title says it in words.
 */
export function Dot({ signal, title }: { signal: Signal; title: string }) {
  const glyph =
    signal === "ok" ? "●" : signal === "warn" ? "▲" : signal === "fail" ? "■" : "○";
  return (
    <span className={`${s.dot} ${s[`dot_${signal}`]}`} title={title} role="img" aria-label={title}>
      {glyph}
    </span>
  );
}

/** A number with its label, used across every stat row in the product. */
export function Stat({
  label,
  value,
  hint,
  visual,
  onClick,
  accent,
}: {
  label: string;
  value: ReactNode;
  hint?: string;
  visual?: ReactNode;
  onClick?: () => void;
  /** A CSS colour for the card's left rule and value. */
  accent?: string;
}) {
  const body = (
    <>
      <span className={s.statLabel}>{label}</span>
      <span className={s.statValue} style={accent ? { color: accent } : undefined}>
        {value}
      </span>
      {hint ? <span className={s.statHint}>{hint}</span> : null}
      {visual ? <span className={s.statVisual}>{visual}</span> : null}
    </>
  );
  const style = accent ? ({ "--stat-accent": accent } as React.CSSProperties) : undefined;
  return onClick ? (
    <button type="button" className={`${s.stat} ${s.statButton}`} style={style} onClick={onClick}>
      {body}
    </button>
  ) : (
    <div className={s.stat} style={style}>
      {body}
    </div>
  );
}
