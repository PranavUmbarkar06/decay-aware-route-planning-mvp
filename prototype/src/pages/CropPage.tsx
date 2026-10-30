import { useEffect, useState } from "react";
import { CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api } from "../api";
import { Badge } from "../components/controls";
import { useStore } from "../store";

const COLORS = { grapes: "#6b3fa0", tomato: "#c8402f", onion: "#b08a2e" };
const ROWS: { key: string; label: string; unit?: string }[] = [
  { key: "ref_life_h", label: "Reference shelf life", unit: "h" },
  { key: "ref_temp_c", label: "at temperature", unit: "°C" },
  { key: "rh_opt", label: "Ideal humidity", unit: "%" },
  { key: "rot_alpha", label: "Rot when wetter than ideal" },
  { key: "dry_beta", label: "Loss when drier than ideal" },
  { key: "beta_vib", label: "Vibration damage coefficient" },
  { key: "handling_loss", label: "Damage per handling" },
  { key: "reefer_set_c", label: "Reefer set point", unit: "°C" },
];

const val = (x: any) => (x && typeof x === "object" && "value" in x ? x.value : x);
const status = (x: any) => (x && typeof x === "object" ? x.status : undefined);
const src = (x: any) => (x && typeof x === "object" ? x.source ?? x.note ?? x.choice : undefined);

function Sens({ data, var: v, xLabel }: { data: any[]; var: string; xLabel: string }) {
  return (
    <figure className="sens">
      <figcaption>{xLabel}</figcaption>
      <ResponsiveContainer width="100%" height={180}>
        <LineChart data={data} margin={{ top: 6, right: 10, bottom: 0, left: -16 }}>
          <CartesianGrid stroke="#e6e7e1" vertical={false} />
          <XAxis dataKey="x" stroke="#8a8f94" fontSize={11} />
          <YAxis stroke="#8a8f94" fontSize={11} tickFormatter={(t) => `${t}%`} />
          <Tooltip formatter={(n) => `${Number(n).toFixed(1)}%`} labelFormatter={(l) => `${xLabel}: ${l}`} />
          <Legend iconType="plainline" />
          {(["grapes", "tomato", "onion"] as const).map((c) => (
            <Line key={c} dataKey={c} stroke={COLORS[c]} strokeWidth={2} dot={false} isAnimationActive={false} name={c[0].toUpperCase() + c.slice(1)} />
          ))}
        </LineChart>
      </ResponsiveContainer>
      <p className="hint">Value lost after 24 h and 600 km in an open truck ({v === "roughness" ? "32 °C, 60% RH" : v === "temperature" ? "60% RH, roughness 3" : "32 °C, roughness 3"}).</p>
    </figure>
  );
}

export function CropPage() {
  const cfg = useStore((s) => s.cfg);
  const [sens, setSens] = useState<any>(null);
  useEffect(() => { void api.sensitivity().then(setSens); }, []);
  if (!cfg) return null;
  const crops = cfg.crops;
  return (
    <div className="page page-crops">
      <h1>Crop intelligence</h1>
      <p className="lede">One routing engine, three sensitivity profiles. These numbers are the only place crops differ; there is no crop-specific routing rule.</p>
      <table className="profile-table">
        <thead><tr><th scope="col">Parameter</th>{Object.entries(crops).map(([k, c]: [string, any]) => <th key={k} scope="col" style={{ color: COLORS[k as keyof typeof COLORS] }}>{c.label}</th>)}</tr></thead>
        <tbody>
          {ROWS.map((r) => (
            <tr key={r.key}>
              <th scope="row">{r.label}</th>
              {Object.entries(crops).map(([k, c]: [string, any]) => (
                <td key={k} title={src(c[r.key])}>
                  {val(c[r.key])}{r.unit ? ` ${r.unit}` : ""}
                  {status(c[r.key]) && <Badge kind={status(c[r.key]) === "SOURCED" ? "SOURCED" : "ASSUMPTION"} />}
                </td>
              ))}
            </tr>
          ))}
          <tr><th scope="row">Default packaging</th>{Object.entries(crops).map(([k, c]: [string, any]) => <td key={k}>{c.packaging_note}</td>)}</tr>
        </tbody>
      </table>
      <p className="hint">Hover any number for its citation or note.</p>

      <h2>How each crop responds</h2>
      {sens ? (
        <div className="sens-grid">
          <Sens data={sens.series.temperature} var="temperature" xLabel="Ambient temperature (°C)" />
          <Sens data={sens.series.humidity} var="humidity" xLabel="Relative humidity (%)" />
          <Sens data={sens.series.roughness} var="roughness" xLabel="Road roughness (0 smooth to 10 very poor)" />
        </div>
      ) : <p className="empty-state">Computing sensitivity curves…</p>}

      <section className="method">
        <h2>Methodology</h2>
        <div className="method-cols">
          <div>
            <h3>Mechanisms, counted once each</h3>
            <ol>
              <li><b>Physiological decay.</b> One time integral of an Arrhenius rate, k = k_ref · exp(Ea/R · (1/T_ref − 1/T)) · f(RH). Quality Q = Q₀ · exp(−∫k dt). Waiting before loading and at the market are extra time in the same integral, not separate terms.</li>
              <li><b>Mechanical damage.</b> D = 1 − exp(−β · packaging · loading · Σ (roughness/10)² · km).</li>
              <li><b>Handling damage.</b> 1 − (1 − h)<sup>events</sup>, two events by default.</li>
              <li><b>Grading.</b> Surviving units are split by a lognormal unit spread (σ = 0.25) into saleable, downgraded (sold at half price) and rejected.</li>
            </ol>
            <p>Survival fractions multiply, so a unit lost to bruising cannot also be counted as rotten.</p>
          </div>
          <div>
            <h3>Routing</h3>
            <p>Edge cost in rupees = transport cost per km and per hour + the marginal value of quality lost to decay + the marginal value lost to vibration. Marginal values come from the shipment's own expected arrival state, so a near-ripe load weighs time more than a fresh one.</p>
            <p>A detour is recommended only if net value beats the original route by more than ₹500 or 1% of cargo value, whichever is larger.</p>
            <h3>Limitations</h3>
            <ul>
              <li>Q10 = 2 is fitted to FAO 152 Table 1; real crops vary by cultivar.</li>
              <li>Vibration, humidity and handling coefficients are illustrative. No measured values for Indian roads exist in this project yet; shipment outcomes are recorded to calibrate them.</li>
              <li>Most road roughness is a default by road class; OSM tags cover about 4% of edges.</li>
              <li>Traffic and disruptions are simulated. No live traffic feed is used.</li>
              <li>National post-harvest loss figures (NABCONS 2022) cover the whole chain, not transport alone, and are not used as outputs.</li>
            </ul>
          </div>
        </div>
      </section>
    </div>
  );
}
