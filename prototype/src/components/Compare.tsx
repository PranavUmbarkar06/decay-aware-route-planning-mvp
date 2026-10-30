import { CartesianGrid, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { CandidateRoute, Plan } from "../types";
import { clock, hrs, kg, rs } from "./controls";

type Row = { label: string; get: (c: CandidateRoute) => string; num: (c: CandidateRoute) => number; better: "low" | "high" };
const ROWS: Row[] = [
  { label: "Distance", get: (c) => `${c.metrics.distance_km.toFixed(0)} km`, num: (c) => c.metrics.distance_km, better: "low" },
  { label: "Travel time", get: (c) => hrs(c.metrics.travel_h), num: (c) => c.metrics.travel_h, better: "low" },
  { label: "Expected delay", get: (c) => hrs(c.metrics.delay_h + c.metrics.wait_h), num: (c) => c.metrics.delay_h + c.metrics.wait_h, better: "low" },
  { label: "Road quality", get: (c) => `${c.metrics.road_quality.toFixed(1)} / 10`, num: (c) => c.metrics.road_quality, better: "high" },
  { label: "Vibration damage", get: (c) => `${c.metrics.vibration_risk_pct.toFixed(1)}%`, num: (c) => c.metrics.vibration_risk_pct, better: "low" },
  { label: "Heat exposure", get: (c) => `${c.metrics.heat_degree_h.toFixed(0)} °C·h (max ${c.metrics.max_cargo_temp_c.toFixed(0)} °C)`, num: (c) => c.metrics.heat_degree_h, better: "low" },
  { label: "Wastage", get: (c) => `${kg(c.metrics.wastage_kg)} (${c.metrics.wastage_pct.toFixed(1)}%)`, num: (c) => c.metrics.wastage_kg, better: "low" },
  { label: "Saleable produce", get: (c) => `${kg(c.metrics.saleable_kg)}, ${kg(c.metrics.downgraded_kg)} downgraded`, num: (c) => c.metrics.saleable_kg, better: "high" },
  { label: "Transport cost", get: (c) => rs(c.metrics.transport_cost_rs), num: (c) => c.metrics.transport_cost_rs, better: "low" },
  { label: "Net value", get: (c) => rs(c.metrics.net_value_rs), num: (c) => c.metrics.net_value_rs, better: "high" },
];

export function CompareTable({ plan, dispatchHour, compact = false }: { plan: Plan; dispatchHour: number; compact?: boolean }) {
  const orig = plan.candidates.find((c) => c.id === plan.original_id);
  const rec = plan.candidates.find((c) => c.id === plan.recommended_id);
  if (!rec) return <p className="empty-state">{plan.explanation.join(" ")}</p>;
  const same = orig?.id === rec.id;
  const cols = [orig, same ? null : rec].filter(Boolean) as CandidateRoute[];
  const win = (r: Row, c: CandidateRoute) => {
    if (same || !orig || !orig.feasible || !rec.feasible) return false;
    const a = r.num(orig), b = r.num(rec);
    if (Math.abs(a - b) < 1e-6) return false;
    const recBetter = r.better === "low" ? b < a : b > a;
    return c === rec ? recBetter : !recBetter;
  };
  const rows = compact ? ROWS.filter((r) => ["Travel time", "Wastage", "Saleable produce", "Net value"].includes(r.label)) : ROWS;
  return (
    <table className="compare">
      <thead>
        <tr>
          <th scope="col"><span className="sr">Metric</span></th>
          {cols.map((c) => (
            <th key={c.id} scope="col" className={c === orig ? "col-orig" : "col-rec"}>
              <i className={`sw ${c === orig ? "sw-orig" : "sw-opt"}`} />{c === orig ? (same ? "Original (recommended)" : "Original") : "Optimised"}
              <small>{c.label}</small>
            </th>
          ))}
        </tr>
      </thead>
      <tbody>
        {rows.map((r) => (
          <tr key={r.label}>
            <th scope="row">{r.label}</th>
            {cols.map((c) => <td key={c.id} className={win(r, c) ? "win" : ""}>{c.feasible ? r.get(c) : (r.label === "Distance" ? c.reason : "")}</td>)}
          </tr>
        ))}
        {!compact && (
          <tr>
            <th scope="row">Arrival</th>
            {cols.map((c) => <td key={c.id}>{c.feasible ? clock(dispatchHour, c.metrics.total_h) : "n/a"}</td>)}
          </tr>
        )}
      </tbody>
    </table>
  );
}

export function QualityChart({ plan, height = 170 }: { plan: Plan; height?: number }) {
  const orig = plan.candidates.find((c) => c.id === plan.original_id);
  const rec = plan.candidates.find((c) => c.id === plan.recommended_id);
  const series = [orig, rec !== orig ? rec : undefined].filter((c): c is CandidateRoute => !!c && c.feasible);
  const data: Record<string, number>[] = [];
  for (const c of series) for (const [t, q] of c.metrics.profile) data.push({ t: +t.toFixed(2), [c.id]: q });
  data.sort((a, b) => a.t - b.t);
  return (
    <ResponsiveContainer width="100%" height={height}>
      <LineChart data={data} margin={{ top: 8, right: 12, bottom: 0, left: -18 }}>
        <CartesianGrid stroke="#e6e7e1" vertical={false} />
        <XAxis dataKey="t" type="number" domain={[0, "dataMax"]} tickFormatter={(v) => `${Math.round(v)} h`} stroke="#8a8f94" fontSize={11} />
        <YAxis domain={["auto", 1]} tickFormatter={(v) => v.toFixed(2)} stroke="#8a8f94" fontSize={11} />
        <ReferenceLine y={0.6} stroke="#d93a30" strokeDasharray="4 3" label={{ value: "half unsellable", position: "insideBottomRight", fontSize: 10, fill: "#8a1c14" }} />
        <Tooltip formatter={(v) => Number(v).toFixed(3)} labelFormatter={(v) => `${Number(v).toFixed(1)} h after dispatch`} />
        {series.map((c) => (
          <Line key={c.id} dataKey={c.id} name={c.id === plan.original_id ? "Original" : "Optimised"} connectNulls dot={false}
            stroke={c.id === plan.original_id ? "#2f6feb" : "#1e9e5a"} strokeWidth={2} isAnimationActive={false} />
        ))}
      </LineChart>
    </ResponsiveContainer>
  );
}

export function DecisionBanner({ plan }: { plan: Plan }) {
  const tone = { reroute: "go", continue: "hold", no_feasible_route: "stop", original_blocked: "go" }[plan.decision];
  const head = {
    reroute: "Reroute recommended",
    continue: "Continue on the original route",
    no_feasible_route: "No feasible route",
    original_blocked: "Original route blocked, use the alternative",
  }[plan.decision];
  return (
    <div className={`decision d-${tone}`} role="status">
      <strong>{head}</strong>
      {plan.explanation.map((x, i) => <p key={i}>{x}</p>)}
    </div>
  );
}
