import { useEffect, useRef } from "react";
import { CompareTable, DecisionBanner, QualityChart } from "../components/Compare";
import { Badge, kg, rs, Select, Slider, Toggle } from "../components/controls";
import { IndiaMap } from "../map/IndiaMap";
import { useStore } from "../store";
import type { DisruptionType } from "../types";

const TYPES: { value: DisruptionType; label: string }[] = [
  { value: "closure", label: "Complete closure" },
  { value: "partial_blockage", label: "Partial blockage" },
  { value: "congestion", label: "Traffic congestion" },
  { value: "reduced_speed", label: "Reduced speed" },
  { value: "construction", label: "Construction" },
  { value: "accident", label: "Accident" },
  { value: "poor_road", label: "Poor road condition" },
  { value: "vehicle_restriction", label: "Heavy-vehicle restriction" },
];

function DisruptionEditor() {
  const { disruptions, editing, set, updateDisruption, removeDisruption, clearDisruptions, pickRoad } = useStore();
  return (
    <section className="panel disruptions">
      <div className="panel-head">
        <h2>Disruptions</h2>
        <button className={`btn ${pickRoad ? "primary" : ""}`} aria-pressed={pickRoad} onClick={() => set({ pickRoad: !pickRoad })}>
          {pickRoad ? "Click a road on the map" : "Add on map"}
        </button>
      </div>
      {disruptions.length === 0 && <p className="hint">Click "Add on map", then click any road. The whole mapped stretch is selected, even roads hidden at this zoom.</p>}
      <ul className="dis-list">
        {disruptions.map((d) => (
          <li key={d.id} className={editing === d.id ? "open" : ""}>
            <button className="dis-row" onClick={() => set({ editing: editing === d.id ? null : d.id })}>
              <i className={`dot k-${d.type}`} /><span>{TYPES.find((t) => t.value === d.type)?.label}</span><small>{d.label}</small>
            </button>
            {editing === d.id && (
              <div className="dis-edit">
                <Select label="Type" value={d.type} options={TYPES} onChange={(v) => updateDisruption(d.id, { type: v })} />
                <Slider label="Severity" value={d.severity} min={1} max={10} onChange={(v) => updateDisruption(d.id, { severity: v })} />
                <div className="row2">
                  <Slider label="Starts" value={d.start_h} min={0} max={24} step={0.5} unit=" h" onChange={(v) => updateDisruption(d.id, { start_h: v })}
                    format={(v) => (v === 0 ? "at dispatch" : `+${v} h`)} />
                  <Slider label="Lasts" value={d.end_h == null ? 49 : d.end_h - d.start_h} min={1} max={49} step={1}
                    onChange={(v) => updateDisruption(d.id, { end_h: v >= 49 ? null : d.start_h + v })} format={(v) => (v >= 49 ? "until further notice" : `${v} h`)} />
                </div>
                <Toggle label="Applies to heavy vehicles only" checked={d.heavy_only} onChange={(v) => updateDisruption(d.id, { heavy_only: v })} />
                <Toggle label="Local alternative access" checked={d.alt_access} onChange={(v) => updateDisruption(d.id, { alt_access: v })}
                  hint="Trucks can get past slowly instead of being stopped." />
                <Toggle label="Confirmed" checked={d.confirmed} onChange={(v) => updateDisruption(d.id, { confirmed: v })}
                  hint="Unconfirmed reports let the dispatcher wait before deciding." />
                <button className="btn quiet small" onClick={() => removeDisruption(d.id)}>Remove disruption</button>
              </div>
            )}
          </li>
        ))}
      </ul>
      {disruptions.length > 1 && <button className="btn quiet small" onClick={clearDisruptions}>Remove all</button>}
    </section>
  );
}

function TripControls() {
  const { replay, plan, startTrip, stopTrip, set } = useStore();
  if (!plan || !plan.recommended_id) return null;
  return (
    <section className="panel trip">
      <h2>Live trip</h2>
      {!replay.started ? (
        <>
          <p className="hint">Drive the recommended route in simulated time. Add disruptions ahead of the truck and the dispatcher rail shows how long you have to decide.</p>
          <button className="btn primary" onClick={() => void startTrip()}>Start trip</button>
        </>
      ) : (
        <div className="trip-row">
          <button className="btn" onClick={stopTrip}>{replay.done ? "Arrived" : replay.running ? "Pause" : "Resume"}</button>
          <Select label="Speed" value={String(replay.speed)} onChange={(v) => set({ replay: { ...replay, speed: +v } })}
            options={[{ value: "0.05", label: "3 min per second" }, { value: "0.15", label: "9 min per second" }, { value: "0.5", label: "30 min per second" }, { value: "1", label: "1 h per second" }]} />
          <button className="btn quiet" onClick={() => void startTrip()}>Restart</button>
          {replay.held && <p className="warn trip-note">Truck stopped at a closure.</p>}
          {(useStore.getState().queue?.pending ?? 0) > 0 && <p className="hint trip-note">Time slowed to 1 min per second while a decision is open.</p>}
        </div>
      )}
    </section>
  );
}

export function RoutePage() {
  const s = useStore();
  const plan = s.plan;
  const tick = s.tick;
  const last = useRef(performance.now());
  useEffect(() => {
    let raf = 0;
    const loop = (t: number) => {
      const dt = Math.min(0.2, (t - last.current) / 1000);
      last.current = t;
      tick(dt);
      raf = requestAnimationFrame(loop);
    };
    raf = requestAnimationFrame(loop);
    return () => cancelAnimationFrame(raf);
  }, [tick]);

  return (
    <div className="page page-route">
      <div className="map-wrap">
        <IndiaMap />
        <div className="map-legend" aria-label="Map legend">
          <span><i className="sw sw-orig" />Original</span><span><i className="sw sw-opt" />Optimised</span>
          <span><i className="sw sw-alt" />Alternatives</span><span><i className="sw sw-cong" />Congested</span>
          <span><i className="sw sw-block" />Blocked</span><span><i className="sw sw-poor" />Poor road</span>
          <Badge kind="MAPPED ROAD" /><Badge kind="SIMULATED" />
        </div>
      </div>
      <div className="side">
        <section className="panel">
          <div className="panel-head">
            <h2>{s.origin?.market ?? "Origin"} to {s.destination?.market ?? "destination"}</h2>
          </div>
          <p className="hint">{s.shipment.shipment_id}, {kg(s.shipment.kg)} of {s.cfg?.crops?.[s.shipment.crop]?.label?.toLowerCase()}.
            {plan?.origin?.access_leg ? ` Origin is ${plan.origin.snap_km} km from the nearest mapped highway.` : ""}</p>
          <button className="btn primary big run" disabled={s.busy} onClick={() => void s.optimise()}>
            {s.busy ? "Optimising…" : "Run optimisation"}
          </button>
          <div className="layer-toggles">
            {(["original", "optimised", "alternatives", "markets"] as const).map((k) => (
              <Toggle key={k} label={{ original: "Original route", optimised: "Optimised route", alternatives: "Alternatives", markets: "Markets" }[k]}
                checked={s.layers[k]} onChange={(v) => s.set({ layers: { ...s.layers, [k]: v } })} />
            ))}
          </div>
          {s.error && <p className="warn">{s.error}</p>}
        </section>
        {plan && <DecisionBanner plan={plan} />}
        <DisruptionEditor />
        <TripControls />
        {plan && (
          <section className="panel">
            <h2>Original versus optimised</h2>
            <CompareTable plan={plan} dispatchHour={s.shipment.dispatch_hour} />
            {plan.economics && plan.decision === "reroute" && (
              <dl className="econ">
                <div><dt>Extra distance</dt><dd>{plan.economics.extra_km.toFixed(0)} km</dd></div>
                <div><dt>Extra transport cost</dt><dd>{rs(plan.economics.extra_transport_rs)}</dd></div>
                <div><dt>Produce value protected</dt><dd>{rs(plan.economics.produce_value_protected_rs)}</dd></div>
                <div><dt>Net benefit</dt><dd>{rs(plan.economics.net_benefit_rs)}</dd></div>
                <div><dt>Cost per kg saved</dt><dd>{plan.economics.cost_per_kg_saved_rs == null ? "n/a" : `₹${plan.economics.cost_per_kg_saved_rs}`}</dd></div>
              </dl>
            )}
            <h3>Quality during the trip</h3>
            <QualityChart plan={plan} />
          </section>
        )}
      </div>
    </div>
  );
}
