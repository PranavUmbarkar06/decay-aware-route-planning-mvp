import { useEffect, useState } from "react";
import { CartesianGrid, ReferenceLine, ResponsiveContainer, Scatter, ScatterChart, Tooltip, XAxis, YAxis } from "recharts";
import { api } from "../api";
import { kg, NumberField, Select } from "../components/controls";
import { useStore } from "../store";

const CAUSES = ["Heat", "Delay in traffic", "Road damage / vibration", "Rot / humidity", "Handling", "Market rejection", "Breakdown", "Other"];

export function OutcomesPage() {
  const { shipment, plan, replay } = useStore();
  const rec = plan?.candidates.find((c) => c.id === plan.recommended_id)?.metrics;
  const [rows, setRows] = useState<any[]>([]);
  const [log, setLog] = useState<any[]>([]);
  const blank = () => ({
    shipment_id: shipment.shipment_id, crop: shipment.crop, loaded_kg: shipment.kg, received_kg: shipment.kg,
    damaged_kg: 0, rejected_kg: 0, downgraded_kg: 0, sold_kg: shipment.kg, arrival: "", transit_h: rec ? +rec.total_h.toFixed(1) : 0,
    condition: "good", cause: CAUSES[0],
    predicted_wastage_kg: rec?.wastage_kg ?? null, predicted_saved_kg: null as number | null,
  });
  const [f, setF] = useState(blank);
  const load = () => { void api.outcomes().then(setRows); void api.decisionLog().then(setLog); };
  useEffect(load, []);
  useEffect(() => {
    const o = plan?.candidates.find((c) => c.id === plan.original_id)?.metrics;
    setF((x) => ({ ...blank(), ...(x.shipment_id === shipment.shipment_id ? {} : {}),
      predicted_saved_kg: o?.feasible && rec ? +(o.wastage_kg - rec.wastage_kg).toFixed(1) : null }));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [shipment.shipment_id, plan]);
  const up = (p: Partial<typeof f>) => setF({ ...f, ...p });
  const actualWaste = f.damaged_kg + f.rejected_kg + Math.max(0, f.loaded_kg - f.received_kg);
  const save = async () => {
    await api.addOutcome({ ...f, actual_wastage_kg: actualWaste, recorded_during_trip_h: replay.nowH });
    load();
  };
  const pts = rows.map((r) => ({ p: r.payload.predicted_wastage_kg, a: r.payload.actual_wastage_kg, id: r.shipment_id })).filter((x) => x.p != null);
  return (
    <div className="page page-outcomes">
      <h1>Shipment outcomes</h1>
      <p className="lede">Record what actually happened at the market. Predicted against actual loss is how the deterioration coefficients get calibrated.</p>
      <div className="cols2">
        <section className="panel">
          <h2>Record an outcome</h2>
          <div className="row2">
            <div className="field"><label htmlFor="sid">Shipment ID</label><input id="sid" value={f.shipment_id} onChange={(e) => up({ shipment_id: e.target.value })} /></div>
            <Select label="Crop" value={f.crop} onChange={(v) => up({ crop: v })} options={[{ value: "grapes", label: "Grapes" }, { value: "tomato", label: "Tomatoes" }, { value: "onion", label: "Onions" }]} />
          </div>
          <div className="row2">
            <NumberField label="Loaded" unit="kg" value={f.loaded_kg} onChange={(v) => up({ loaded_kg: v })} />
            <NumberField label="Received" unit="kg" value={f.received_kg} onChange={(v) => up({ received_kg: v })} />
          </div>
          <div className="row3">
            <NumberField label="Physically damaged" unit="kg" value={f.damaged_kg} onChange={(v) => up({ damaged_kg: v })} />
            <NumberField label="Rejected" unit="kg" value={f.rejected_kg} onChange={(v) => up({ rejected_kg: v })} />
            <NumberField label="Downgraded" unit="kg" value={f.downgraded_kg} onChange={(v) => up({ downgraded_kg: v })} />
          </div>
          <div className="row3">
            <NumberField label="Sold" unit="kg" value={f.sold_kg} onChange={(v) => up({ sold_kg: v })} />
            <div className="field"><label htmlFor="arr">Actual arrival</label><input id="arr" type="datetime-local" value={f.arrival} onChange={(e) => up({ arrival: e.target.value })} /></div>
            <NumberField label="Transit duration" unit="h" step={0.5} value={f.transit_h} onChange={(v) => up({ transit_h: v })} />
          </div>
          <div className="row2">
            <Select label="Condition on arrival" value={f.condition} onChange={(v) => up({ condition: v })}
              options={[{ value: "good", label: "Good" }, { value: "fair", label: "Fair" }, { value: "poor", label: "Poor" }]} />
            <Select label="Main cause of loss" value={f.cause} onChange={(v) => up({ cause: v })} options={CAUSES.map((c) => ({ value: c, label: c }))} />
          </div>
          <p className="hint">Actual wastage {kg(actualWaste)}; model predicted {f.predicted_wastage_kg == null ? "nothing yet (plan a route)" : kg(f.predicted_wastage_kg)} for the chosen route.</p>
          <button className="btn primary" onClick={() => void save()}>Save outcome</button>
        </section>
        <section className="panel">
          <h2>Predicted against actual wastage</h2>
          {pts.length === 0 ? <p className="empty-state">No outcomes recorded yet. Each saved outcome adds a point; points on the line mean the model was right.</p> : (
            <ResponsiveContainer width="100%" height={260}>
              <ScatterChart margin={{ top: 10, right: 10, bottom: 10, left: 0 }}>
                <CartesianGrid stroke="#e6e7e1" />
                <XAxis dataKey="p" name="Predicted" unit=" kg" fontSize={11} /><YAxis dataKey="a" name="Actual" unit=" kg" fontSize={11} />
                <ReferenceLine segment={[{ x: 0, y: 0 }, { x: Math.max(...pts.map((x) => Math.max(x.p, x.a))), y: Math.max(...pts.map((x) => Math.max(x.p, x.a))) }]} stroke="#8a8f94" strokeDasharray="4 3" />
                <Tooltip cursor={{ strokeDasharray: "3 3" }} />
                <Scatter data={pts} fill="#17734a" />
              </ScatterChart>
            </ResponsiveContainer>
          )}
          <table className="data">
            <thead><tr><th>Shipment</th><th>Crop</th><th>Predicted</th><th>Actual</th><th>Cause</th></tr></thead>
            <tbody>{rows.map((r) => <tr key={r.id}><td>{r.shipment_id}</td><td>{r.crop}</td><td>{kg(r.payload.predicted_wastage_kg)}</td><td>{kg(r.payload.actual_wastage_kg)}</td><td>{r.payload.cause}</td></tr>)}</tbody>
          </table>
        </section>
      </div>
      <section className="panel">
        <h2>Dispatcher decision log</h2>
        <p className="hint">Every alert, decision and deadline slack. Decision speed and missed deadlines will calibrate the review and acknowledgement buffers.</p>
        {log.length === 0 ? <p className="empty-state">No decisions yet. Run a live trip with a disruption on the route page.</p> : (
          <table className="data">
            <thead><tr><th>Trip time</th><th>Shipment</th><th>Who</th><th>Action</th><th>State</th><th>Slack</th></tr></thead>
            <tbody>{log.map((e) => (
              <tr key={e.id}><td>{e.at_h.toFixed(2)} h</td><td>{e.shipment_id}</td><td>{e.actor}</td><td>{e.action.replace(/_/g, " ")}</td>
                <td>{e.from_state ?? "new"} to {e.to_state}</td><td>{e.slack_min == null ? "" : `${Math.round(e.slack_min)} min`}</td></tr>
            ))}</tbody>
          </table>
        )}
      </section>
    </div>
  );
}
