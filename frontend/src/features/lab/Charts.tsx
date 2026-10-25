import { useMemo, useState } from "react";

// Small dependency-free SVG charts following the data-viz rules: thin marks, recessive axes, legend + direct labels,
// hover tooltip, and a table view elsewhere on the page. Series colours: --series-1 (baseline), --series-2 (proposed).

export type Series = { key: string; label: string; color: "series-1" | "series-2"; points: { x: number; y: number | null }[] };

export function LineChart({ series, height = 220, yFormat = (v: number) => `${(v * 100).toFixed(1)}%`, xLabel, xFormat = (x: number) => String(x), title }: {
  series: Series[]; height?: number; yFormat?: (v: number) => string; xLabel?: string; xFormat?: (x: number) => string; title: string;
}) {
  const W = 640, H = height, L = 52, R = 112, T = 12, B = 30;
  const all = series.flatMap((s) => s.points.filter((p) => p.y !== null)) as { x: number; y: number }[];
  const xmax = Math.max(1, ...all.map((p) => p.x));
  const ymax = Math.max(0.01, ...all.map((p) => p.y)) * 1.1;
  const sx = (x: number) => L + (x / xmax) * (W - L - R);
  const sy = (y: number) => T + (1 - y / ymax) * (H - T - B);
  const [hover, setHover] = useState<number | null>(null);
  const ticks = useMemo(() => [0, 0.25, 0.5, 0.75, 1].map((f) => f * ymax), [ymax]);
  const hx = hover !== null ? hover : null;
  return (
    <figure className="w-full">
      <figcaption className="mb-1 text-sm font-semibold">{title}</figcaption>
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full touch-none" role="img" aria-label={title}
        onPointerMove={(e) => {
          const r = (e.currentTarget as SVGSVGElement).getBoundingClientRect();
          const x = ((e.clientX - r.left) / r.width) * W;
          setHover(Math.max(0, Math.min(xmax, Math.round(((x - L) / (W - L - R)) * xmax))));
        }} onPointerLeave={() => setHover(null)}>
        {ticks.map((v) => (
          <g key={v}>
            <line x1={L} x2={W - R} y1={sy(v)} y2={sy(v)} stroke="var(--line)" strokeWidth={1} />
            <text x={L - 6} y={sy(v) + 4} textAnchor="end" fontSize="11" fill="var(--muted)">{yFormat(v)}</text>
          </g>
        ))}
        {series.map((s) => {
          const pts = s.points.filter((p) => p.y !== null) as { x: number; y: number }[];
          if (!pts.length) return null;
          const d = pts.map((p, i) => `${i ? "L" : "M"}${sx(p.x).toFixed(1)},${sy(p.y).toFixed(1)}`).join("");
          const last = pts[pts.length - 1];
          return (
            <g key={s.key}>
              <path d={d} fill="none" stroke={`var(--${s.color})`} strokeWidth={2} strokeLinejoin="round" />
              <circle cx={sx(last.x)} cy={sy(last.y)} r={4} fill={`var(--${s.color})`} stroke="var(--surface-2)" strokeWidth={2} />
              <text x={sx(last.x) + 8} y={sy(last.y) + 4} fontSize="12" fill="var(--ink)">{s.label.split(":")[0]} {yFormat(last.y)}</text>
            </g>
          );
        })}
        {hx !== null ? (
          <g>
            <line x1={sx(hx)} x2={sx(hx)} y1={T} y2={H - B} stroke="var(--muted)" strokeDasharray="3 3" />
            {series.map((s, i) => {
              const p = s.points.find((q) => q.x === hx);
              return p && p.y !== null ? (
                <g key={s.key}>
                  <circle cx={sx(hx)} cy={sy(p.y)} r={4} fill={`var(--${s.color})`} stroke="var(--surface-2)" strokeWidth={2} />
                  <rect x={Math.min(sx(hx) + 6, W - 150)} y={T + i * 20} width={140} height={18} rx={4} fill="var(--surface-2)" stroke="var(--line)" />
                  <text x={Math.min(sx(hx) + 12, W - 144)} y={T + 13 + i * 20} fontSize="11" fill="var(--ink)">{s.label.split(":")[0]}: {yFormat(p.y)}</text>
                </g>
              ) : null;
            })}
          </g>
        ) : null}
        <line x1={L} x2={W - R} y1={H - B} y2={H - B} stroke="var(--line)" />
        <text x={L} y={H - 8} fontSize="11" fill="var(--muted)">{xFormat(0)}</text>
        <text x={W - R} y={H - 8} fontSize="11" fill="var(--muted)" textAnchor="end">{xFormat(xmax)}</text>
        {xLabel ? <text x={(L + W - R) / 2} y={H - 8} fontSize="11" fill="var(--muted)" textAnchor="middle">{xLabel}</text> : null}
      </svg>
      <Legend items={series.map((s) => ({ label: s.label, color: s.color }))} />
    </figure>
  );
}

export function Legend({ items }: { items: { label: string; color: string }[] }) {
  return (
    <ul className="mt-1 flex flex-wrap gap-4 text-sm" aria-label="Legend">
      {items.map((i) => <li key={i.label} className="flex items-center gap-2"><span className="inline-block h-1 w-5 rounded" style={{ background: `var(--${i.color})` }} />{i.label}</li>)}
    </ul>
  );
}

/** Per-seed dot plot with mean bars, grouped by category (season). */
export function DotPlot({ groups, title, yFormat = (v: number) => `${(v * 100).toFixed(1)}%` }: {
  groups: { label: string; baseline: number[]; proposed: number[] }[]; title: string; yFormat?: (v: number) => string;
}) {
  const W = 640, H = 240, L = 52, T = 10, B = 28;
  const vals = groups.flatMap((g) => [...g.baseline, ...g.proposed]);
  const ymax = Math.max(0.01, ...vals) * 1.1;
  const sy = (y: number) => T + (1 - y / ymax) * (H - T - B);
  const gw = (W - L - 10) / Math.max(1, groups.length);
  const [tip, setTip] = useState<string | null>(null);
  const mean = (a: number[]) => a.reduce((s, x) => s + x, 0) / Math.max(1, a.length);
  return (
    <figure className="w-full">
      <figcaption className="mb-1 text-sm font-semibold">{title}</figcaption>
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full" role="img" aria-label={title}>
        {[0, 0.5, 1].map((f) => (
          <g key={f}><line x1={L} x2={W - 10} y1={sy(f * ymax)} y2={sy(f * ymax)} stroke="var(--line)" />
            <text x={L - 6} y={sy(f * ymax) + 4} textAnchor="end" fontSize="11" fill="var(--muted)">{yFormat(f * ymax)}</text></g>
        ))}
        {groups.map((g, gi) => {
          const cx = L + gw * gi + gw / 2;
          return (
            <g key={g.label}>
              {([["baseline", -gw * 0.15, "series-1"], ["proposed", gw * 0.15, "series-2"]] as const).map(([k, dx, c]) => {
                const arr = g[k];
                return (
                  <g key={k}>
                    {arr.map((v, i) => (
                      <circle key={i} cx={cx + dx + ((i % 5) - 2) * 3} cy={sy(v)} r={4} fill={`var(--${c})`} fillOpacity={0.75} stroke="var(--surface-2)" strokeWidth={1.5}
                        onPointerEnter={() => setTip(`${g.label} · ${k} · seed #${i + 1}: ${yFormat(v)}`)} onPointerLeave={() => setTip(null)} />
                    ))}
                    <line x1={cx + dx - 14} x2={cx + dx + 14} y1={sy(mean(arr))} y2={sy(mean(arr))} stroke={`var(--${c})`} strokeWidth={3} strokeLinecap="round" />
                  </g>
                );
              })}
              <text x={cx} y={H - 8} textAnchor="middle" fontSize="12" fill="var(--ink)">{g.label}</text>
            </g>
          );
        })}
      </svg>
      <p className="h-5 text-xs text-muted" aria-live="polite">{tip ?? "Hover a dot for its value."}</p>
      <Legend items={[{ label: "Baseline: static shortest path", color: "series-1" }, { label: "Proposed: quality-aware dynamic", color: "series-2" }]} />
    </figure>
  );
}
