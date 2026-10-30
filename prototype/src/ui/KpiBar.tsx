import { fmtK, type Kpis } from "../model/sim";

export function KpiBar({ k }: { k: Kpis }) {
  const uplift = k.baseTpd > 0 ? (k.smartTpd / k.baseTpd - 1) * 100 : 0;
  return (
    <header className="kpis">
      <div className="brand">
        <b>FreshRoute</b><span>live spoilage-aware dispatch · Nagpur Division</span>
      </div>
      <Kpi label="Food saved vs status quo" value={`${fmtK(Math.max(0, k.foodSavedKg))} kg`} sub={`${Math.round(Math.max(0, k.meals)).toLocaleString("en-IN")} meals*`} good={k.foodSavedKg > 1} />
      <Kpi label="Value saved" value={`₹${fmtK(k.rupeesSaved)}`} sub="net of fuel + time" good={k.rupeesSaved > 1} />
      <Kpi label="Sellable throughput" value={`${k.smartTpd.toFixed(1)} t/truck-day`} sub={`${uplift >= 0 ? "+" : ""}${uplift.toFixed(1)}% vs ${k.baseTpd.toFixed(1)}`} good={uplift > 0.1} />
      <Kpi label="CO₂ per sellable tonne" value={`${k.smartCo2PerT.toFixed(0)} kg`} sub={`status quo ${k.baseCo2PerT.toFixed(0)} kg`} good={k.smartCo2PerT < k.baseCo2PerT - 0.5} />
      <Kpi label="Live reroutes" value={`${k.reroutes}`} sub={`${k.delivered}/3 delivered`} />
    </header>
  );
}

function Kpi({ label, value, sub, good }: { label: string; value: string; sub: string; good?: boolean }) {
  return (
    <div className={`kpi ${good ? "good" : ""}`}>
      <span className="l">{label}</span>
      <b>{value}</b>
      <small>{sub}</small>
    </div>
  );
}
