import { useEffect, useRef, useState } from "react";
import maplibregl, { type Map as MLMap } from "maplibre-gl";
import { Bar, BarChart, CartesianGrid, Cell, Legend, Pie, PieChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api } from "../api";
import { Badge, kg, rs } from "../components/controls";
import { useStore } from "../store";

const norm = (s: string) => s.normalize("NFKD").replace(/[^\w]/g, "").toLowerCase();
const STATE_FIX: Record<string, string> = { nctofdelhi: "delhi", keralam: "kerala", chattisgarh: "chhattisgarh", andamanandnicobar: "andamanandnicobarislands" };

function Single() {
  const plan = useStore((s) => s.plan);
  const sh = useStore((s) => s.shipment);
  if (!plan) return <p className="empty-state">Plan a shipment to see its before-and-after analysis.</p>;
  const o = plan.candidates.find((c) => c.id === plan.original_id)?.metrics;
  const r = plan.candidates.find((c) => c.id === plan.recommended_id)?.metrics;
  if (!r) return <p className="empty-state">{plan.explanation.join(" ")}</p>;
  const base = o?.feasible ? o : null;
  const saved = base ? base.wastage_kg - r.wastage_kg : null;
  const rows: [string, string, string][] = [
    ["Physical loss (bruising, vibration, handling)", base ? kg(base.physical_loss_kg) : "route blocked", kg(r.physical_loss_kg)],
    ["Rejected at market (past saleable quality)", base ? kg(base.rejected_kg) : "", kg(r.rejected_kg)],
    ["Quality downgrade (sold at half price)", base ? kg(base.downgraded_kg) : "", kg(r.downgraded_kg)],
    ["Projected wastage", base ? kg(base.wastage_kg) : "whole load at risk", kg(r.wastage_kg)],
    ["Saleable quantity", base ? kg(base.saleable_kg) : "", kg(r.saleable_kg)],
  ];
  return (
    <section className="panel single">
      <h2>This shipment <Badge kind="SIMULATED" /></h2>
      <p className="hint">{sh.shipment_id}: {kg(sh.kg)} loaded.</p>
      <table className="compare">
        <thead><tr><th scope="col"><span className="sr">Measure</span></th><th scope="col">Original route</th><th scope="col">Optimised</th></tr></thead>
        <tbody>{rows.map(([a, b, c]) => <tr key={a}><th scope="row">{a}</th><td>{b}</td><td>{c}</td></tr>)}</tbody>
      </table>
      <div className="saved-line">
        {saved != null ? (
          <><strong>{saved > 0.5 ? `${kg(saved)} saved` : "Nothing saved"}</strong>
            <span>{saved > 0.5 && base!.wastage_kg > 0 ? `${((100 * saved) / base!.wastage_kg).toFixed(1)}% less projected wastage` : "The original route is already the best choice."}</span></>
        ) : <strong>The original route cannot be completed; the optimised route delivers {kg(r.saleable_kg)}.</strong>}
      </div>
    </section>
  );
}

function ChoroMap({ result }: { result: any }) {
  const el = useRef<HTMLDivElement>(null);
  const map = useRef<MLMap | null>(null);
  useEffect(() => {
    if (!el.current) return;
    const m = new maplibregl.Map({
      container: el.current, center: [79, 22.5], zoom: 3.4, attributionControl: { compact: true },
      style: { version: 8, sources: {}, layers: [{ id: "bg", type: "background", paint: { "background-color": "#f3f4ef" } }] },
    });
    map.current = m;
    m.on("load", async () => {
      const states = await (await fetch("/geo/states")).json();
      m.addSource("states", { type: "geojson", data: states });
      m.addSource("routes", { type: "geojson", data: { type: "FeatureCollection", features: [] } });
      m.addLayer({ id: "states", type: "fill", source: "states", paint: { "fill-color": ["coalesce", ["get", "fill"], "#e7e9e2"], "fill-outline-color": "#ffffff" } });
      m.addLayer({ id: "routes", type: "line", source: "routes",
        paint: { "line-color": ["interpolate", ["linear"], ["get", "risk"], 0, "#1e9e5a", 5, "#e3a21a", 15, "#d93a30"], "line-width": 2.5 } });
      paint();
    });
    return () => m.remove();
  }, []);
  useEffect(() => { paint(); }, [result]);
  function paint() {
    const m = map.current;
    if (!m || !m.getSource("states") || !result) return;
    const byState: Record<string, number> = {};
    for (const s of result.by_state) byState[STATE_FIX[norm(s.state)] ?? norm(s.state)] = s.saved_kg;
    const max = Math.max(1, ...Object.values(byState));
    void fetch("/geo/states").then((r) => r.json()).then((fc) => {
      for (const f of fc.features) {
        const v = byState[norm(f.properties.state_name)];
        f.properties.fill = v == null ? "#e7e9e2" : `rgba(23,115,74,${0.15 + 0.85 * (v / max)})`;
      }
      (m.getSource("states") as maplibregl.GeoJSONSource).setData(fc);
    });
    const risk: Record<string, number> = {};
    for (const r of result.by_route) risk[r.route_id] = r.base_wastage_pct;
    (m.getSource("routes") as maplibregl.GeoJSONSource).setData({ type: "FeatureCollection", features: result.routes.map((r: any) => (
      { type: "Feature", properties: { risk: risk[r.route_id] ?? 0 }, geometry: { type: "LineString", coordinates: r.coords } })) });
  }
  return <div ref={el} className="mini-map" aria-label="State-wise kilograms saved and route risk" />;
}

function Batch() {
  const [states, setStates] = useState<string[]>([]);
  const [allStates, setAll] = useState<string[]>([]);
  const [crops, setCrops] = useState<string[]>(["grapes", "tomato", "onion"]);
  const [days, setDays] = useState(30);
  const [perCorr, setPer] = useState(10);
  const [nCorr, setN] = useState(6);
  const [res, setRes] = useState<any>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => { void api.states().then((s) => setAll(s.map((x) => x.state))); }, []);
  const run = async () => {
    setBusy(true); setErr(null);
    try {
      setRes(await api.batch({ crops, states: states.length ? states : null, shipments_per_corridor: perCorr, corridors_per_crop: nCorr, days, seed: 7 }));
    } catch (e) { setErr((e as Error).message); }
    setBusy(false);
  };
  const t = res?.total;
  return (
    <section className="panel batch">
      <h2>India-wide simulation <Badge kind="SIMULATED" /></h2>
      <p className="hint">Corridors come from real Agmarknet arrival volumes (largest producing markets to the largest terminal markets). Shipment sizes, weather, traffic and disruptions are synthetic and seeded, so the same settings always give the same totals. These are model projections, not observed reductions.</p>
      <div className="batch-controls">
        <fieldset><legend>Crops</legend>
          {["grapes", "tomato", "onion"].map((c) => (
            <label key={c} className="check"><input type="checkbox" checked={crops.includes(c)} onChange={(e) => setCrops(e.target.checked ? [...crops, c] : crops.filter((x) => x !== c))} />{c}</label>
          ))}
        </fieldset>
        <label className="field">States of origin
          <select multiple value={states} onChange={(e) => setStates([...e.target.selectedOptions].map((o) => o.value))} size={5}>
            {allStates.map((s) => <option key={s}>{s}</option>)}
          </select>
          <span className="hint">None selected means all of India.</span>
        </label>
        <label className="field">Period
          <select value={days} onChange={(e) => setDays(+e.target.value)}><option value={7}>1 week</option><option value={30}>1 month</option><option value={90}>1 quarter</option></select>
        </label>
        <label className="field">Corridors per crop<input type="number" min={2} max={15} value={nCorr} onChange={(e) => setN(+e.target.value)} /></label>
        <label className="field">Shipments per corridor<input type="number" min={2} max={40} value={perCorr} onChange={(e) => setPer(+e.target.value)} /></label>
        <button className="btn primary" disabled={busy || crops.length === 0} onClick={() => void run()}>{busy ? "Simulating shipments…" : "Run batch optimisation"}</button>
      </div>
      {err && <p className="warn">{err}</p>}
      {t && (
        <>
          <div className="totals">
            <div><span>Shipments simulated</span><b>{t.shipments}</b></div>
            <div><span>Quantity transported</span><b>{kg(t.kg)}</b></div>
            <div><span>Baseline projected wastage</span><b>{kg(t.base_wastage_kg)}</b><small>{t.base_wastage_pct}%</small></div>
            <div><span>Optimised projected wastage</span><b>{kg(t.opt_wastage_kg)}</b><small>{t.opt_wastage_pct}%</small></div>
            <div className="hl"><span>Potentially saved</span><b>{kg(t.saved_kg)}</b><small>{t.reduction_pct}% less wastage, {t.rerouted} reroutes</small></div>
            <div><span>Net benefit</span><b>{rs(t.net_benefit_rs)}</b></div>
          </div>
          <div className="chart-grid">
            <figure>
              <figcaption>Wastage before and after, by crop</figcaption>
              <ResponsiveContainer width="100%" height={220}>
                <BarChart data={res.by_crop} margin={{ left: 0, right: 8 }}>
                  <CartesianGrid stroke="#e6e7e1" vertical={false} /><XAxis dataKey="crop" fontSize={12} /><YAxis fontSize={11} tickFormatter={(v) => `${(v / 1000).toFixed(0)} t`} />
                  <Tooltip formatter={(v) => kg(Number(v))} /><Legend />
                  <Bar dataKey="base_wastage_kg" name="Original routes" fill="#2f6feb" /><Bar dataKey="opt_wastage_kg" name="Optimised" fill="#1e9e5a" />
                </BarChart>
              </ResponsiveContainer>
            </figure>
            <figure>
              <figcaption>What the wastage is made of</figcaption>
              <ResponsiveContainer width="100%" height={220}>
                <PieChart>
                  <Pie data={[{ n: "Physical loss", v: t.base_phys_kg }, { n: "Rejected at market", v: t.base_rejected_kg }]} dataKey="v" nameKey="n" innerRadius={42} outerRadius={62} cx="30%">
                    <Cell fill="#8a1c14" /><Cell fill="#e3a21a" />
                  </Pie>
                  <Pie data={[{ n: "Physical loss", v: t.opt_phys_kg }, { n: "Rejected at market", v: t.opt_rejected_kg }]} dataKey="v" nameKey="n" innerRadius={42} outerRadius={62} cx="72%">
                    <Cell fill="#8a1c14" /><Cell fill="#e3a21a" />
                  </Pie>
                  <Tooltip formatter={(v) => kg(Number(v))} /><Legend />
                </PieChart>
              </ResponsiveContainer>
              <p className="hint center">Left: original routes. Right: optimised.</p>
            </figure>
            <figure>
              <figcaption>Saleable quantity</figcaption>
              <ResponsiveContainer width="100%" height={220}>
                <BarChart data={res.by_crop} layout="vertical" margin={{ left: 10, right: 8 }}>
                  <XAxis type="number" fontSize={11} tickFormatter={(v) => `${(v / 1000).toFixed(0)} t`} /><YAxis type="category" dataKey="crop" fontSize={12} width={60} />
                  <Tooltip formatter={(v) => kg(Number(v))} /><Legend />
                  <Bar dataKey="base_saleable_kg" name="Original" fill="#9db7ef" /><Bar dataKey="opt_saleable_kg" name="Optimised" fill="#1e9e5a" />
                </BarChart>
              </ResponsiveContainer>
            </figure>
            <figure>
              <figcaption>Kilograms saved by state of origin, and route risk</figcaption>
              <ChoroMap result={res} />
              <p className="hint">Darker green: more saved. Lines: baseline wastage per corridor (green low, red high).</p>
            </figure>
          </div>
          <div className="cols2">
            <div>
              <h3>Highest-risk corridors</h3>
              <ol className="rank">{res.highest_risk.map((r: any) => <li key={r.route_id}><b>{r.origin} to {r.destination}</b><span>{r.crop}, {r.distance_km} km, {r.base_wastage_pct}% projected wastage</span></li>)}</ol>
            </div>
            <div>
              <h3>Most improved corridors</h3>
              <ol className="rank">{res.most_improved.map((r: any) => <li key={r.route_id}><b>{r.origin} to {r.destination}</b><span>{r.crop}, {kg(r.saved_kg)} saved ({r.reduction_pct}%)</span></li>)}</ol>
            </div>
          </div>
          <details>
            <summary>State-wise and route-wise tables</summary>
            <table className="data">
              <thead><tr><th>State</th><th>Shipments</th><th>Baseline wastage</th><th>Optimised</th><th>Saved</th></tr></thead>
              <tbody>{res.by_state.map((s: any) => <tr key={s.state}><td>{s.state}</td><td>{s.shipments}</td><td>{kg(s.base_wastage_kg)}</td><td>{kg(s.opt_wastage_kg)}</td><td>{kg(s.saved_kg)}</td></tr>)}</tbody>
            </table>
            <table className="data">
              <thead><tr><th>Corridor</th><th>Crop</th><th>km</th><th>Baseline</th><th>Optimised</th><th>Reroutes</th></tr></thead>
              <tbody>{res.by_route.map((r: any) => <tr key={r.route_id}><td>{r.origin} to {r.destination}</td><td>{r.crop}</td><td>{r.distance_km}</td><td>{r.base_wastage_pct}%</td><td>{r.opt_wastage_pct}%</td><td>{r.rerouted}</td></tr>)}</tbody>
            </table>
          </details>
        </>
      )}
    </section>
  );
}

function Arrivals() {
  const crop = useStore((s) => s.shipment.crop);
  const [d, setD] = useState<any>(null);
  useEffect(() => { void api.marketsSummary(crop).then(setD); }, [crop]);
  if (!d) return null;
  return (
    <section className="panel">
      <h2>Where {crop} arrives <Badge kind="HISTORICAL" /></h2>
      <p className="hint">Agmarknet arrivals, November 2025 to October 2026. Arrival volume shows supply reaching a market, not demand or stock.</p>
      <div className="cols2">
        <ResponsiveContainer width="100%" height={260}>
          <BarChart data={d.by_state.slice(0, 12)} layout="vertical" margin={{ left: 20 }}>
            <XAxis type="number" fontSize={11} tickFormatter={(v) => `${(v / 1000).toFixed(0)}k t`} /><YAxis type="category" dataKey="state" width={110} fontSize={11} />
            <Tooltip formatter={(v) => `${Math.round(Number(v)).toLocaleString("en-IN")} t`} /><Bar dataKey="arrival_t" fill="#5a6b5f" />
          </BarChart>
        </ResponsiveContainer>
        <ol className="rank">{d.top_markets.slice(0, 10).map((m: any) => (
          <li key={m.market_id}><b>{m.market}</b><span>{m.district}, {m.state}: {Math.round(m.arrival_t).toLocaleString("en-IN")} t, median ₹{Math.round((m.median_modal_rs_q ?? 0) / 100)}/kg</span></li>
        ))}</ol>
      </div>
    </section>
  );
}

export function WastagePage() {
  return (
    <div className="page page-wastage">
      <h1>Wastage analysis</h1>
      <p className="lede">Projected wastage on the original route against the optimised one, for this shipment and across many simulated shipments.</p>
      <Single />
      <Batch />
      <Arrivals />
    </div>
  );
}
