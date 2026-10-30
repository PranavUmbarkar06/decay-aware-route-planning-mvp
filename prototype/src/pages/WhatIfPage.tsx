import { useState } from "react";
import { CompareTable, DecisionBanner, QualityChart } from "../components/Compare";
import { Badge, Select, Slider } from "../components/controls";
import { useStore } from "../store";
import type { ConditionsIn, CropId, Disruption, DisruptionType, Shipment } from "../types";

type Knobs = {
  roadClass: "as_mapped" | "national" | "state" | "district" | "rural";
  refrigeration: "working" | "failed" | "fails_mid";
  demand: "normal" | "low" | "oversupplied";
  disruption: "none" | DisruptionType;
  breakdown: "none" | "short" | "long";
};

const ROAD_Q: Record<Knobs["roadClass"], number> = { as_mapped: 10, national: 10, state: 8, district: 6, rural: 3.5 };
const DEMAND: Record<Knobs["demand"], { price: number; wait: number }> = {
  normal: { price: 1, wait: 0 }, low: { price: 0.85, wait: 4 }, oversupplied: { price: 0.7, wait: 10 },
};

type Scenario = { id: string; label: string; cond?: Partial<ConditionsIn>; ship?: Partial<Shipment>; knobs?: Partial<Knobs> };
const SCENARIOS: Scenario[] = [
  { id: "traffic", label: "Heavy traffic", cond: { traffic: 8 }, knobs: { disruption: "congestion" } },
  { id: "closure", label: "Road closure", knobs: { disruption: "closure" } },
  { id: "partial", label: "Partial blockage", knobs: { disruption: "partial_blockage" } },
  { id: "poorroad", label: "Poor road quality", knobs: { roadClass: "rural", disruption: "poor_road" } },
  { id: "heat", label: "Extreme heat", cond: { ambient_c: 46, rh: 30 } },
  { id: "reefer", label: "Refrigeration failure", ship: { vehicle: "reefer" }, knobs: { refrigeration: "fails_mid" } },
  { id: "vibration", label: "Excessive vibration", cond: { vibration: 10 } },
  { id: "packaging", label: "Poor packaging", ship: { packaging: "poor", loading: "loose" } },
  { id: "breakdown", label: "Vehicle breakdown", knobs: { breakdown: "long" } },
  { id: "oversupply", label: "Market oversupply", knobs: { demand: "oversupplied" } },
  { id: "unloading", label: "Delayed unloading", ship: { market_wait_h: 14 } },
  { id: "multi", label: "Several at once", cond: { ambient_c: 41, traffic: 7, vibration: 8 }, knobs: { disruption: "partial_blockage", breakdown: "short", demand: "low" } },
];

const DEFAULT_KNOBS: Knobs = { roadClass: "as_mapped", refrigeration: "working", demand: "normal", disruption: "none", breakdown: "none" };

export function WhatIfPage() {
  const s = useStore();
  const [knobs, setKnobs] = useState<Knobs>(DEFAULT_KNOBS);
  const [active, setActive] = useState<string | null>(null);
  const cfg = s.cfg;
  const plan = s.plan;
  if (!cfg) return null;
  const sh = s.shipment, c = s.conditions;
  const crop = cfg.crops[sh.crop];

  // Demand scenarios scale the destination's historical price, never an already-scaled price.
  const destPrice = s.destination?.[`${sh.crop}_price_rs_q` as "tomato_price_rs_q"];
  const basePrice = destPrice ? destPrice / 100 : crop.default_price_rs_kg.value;

  function apply(k: Knobs, condPatch: Partial<ConditionsIn> = {}, shipPatch: Partial<Shipment> = {}) {
    setKnobs(k);
    const orig = plan?.candidates.find((x) => x.id === plan.original_id);
    let dis: Disruption[] = s.disruptions.filter((d) => !d.id.startsWith("WI"));
    if (k.disruption !== "none" && orig) {
      // a 30 km stretch starting 40% along the original route
      let i = Math.floor(orig.edges.length * 0.4), km = 0;
      const edges: number[] = [];
      while (i < orig.edges.length && km < 30) { edges.push(orig.edges[i]); km += orig.edge_km[i]; i++; }
      dis = [...dis, { id: "WI-1", type: k.disruption, edges, severity: 8, start_h: 0, end_h: k.disruption === "closure" ? null : null,
        heavy_only: true, alt_access: false, confirmed: true, label: "What-if stretch, 40% along the original route", coords: [] }];
      void fetch(`/api/edges?ids=${edges.join(",")}`).then((r) => r.json()).then((g: { coords: number[][] }[]) =>
        useStore.setState({ disruptions: useStore.getState().disruptions.map((d) => (d.id === "WI-1" ? { ...d, coords: g.map((x) => x.coords) } : d)) }));
    }
    const d = DEMAND[k.demand];
    useStore.setState({
      disruptions: dis,
      conditions: { ...c, road_quality: ROAD_Q[k.roadClass], ...condPatch },
      shipment: {
        ...sh, ...shipPatch,
        refrigeration_ok: k.refrigeration !== "failed",
        reefer_fail_at_h: k.refrigeration === "fails_mid" ? 3 : null,
        breakdown_h: k.breakdown === "none" ? 0 : k.breakdown === "short" ? 2 : 6,
        price_rs_kg: +(basePrice * d.price).toFixed(2),
        market_wait_h: Math.max(shipPatch.market_wait_h ?? sh.market_wait_h, d.wait),
      },
    });
    void s.optimise();
  }

  // Each scenario starts from the baseline so clicks never accumulate.
  const BASE_COND: Partial<ConditionsIn> = { ambient_c: 32, rh: 60, traffic: 2, extra_delay_h: 0, road_quality: 10, vibration: 5 };
  const BASE_SHIP: Partial<Shipment> = { packaging: null, loading: "proper", market_wait_h: 2, vehicle: null, pre_dispatch_h: 0 };
  const scenario = (x: Scenario) => {
    setActive(x.id);
    apply({ ...DEFAULT_KNOBS, ...x.knobs }, { ...BASE_COND, ...x.cond }, { ...BASE_SHIP, ...x.ship });
  };
  const k = (p: Partial<Knobs>) => { setActive(null); apply({ ...knobs, ...p }); };

  return (
    <div className="page page-whatif">
      <div className="whatif-controls">
        <h1>What-if simulator</h1>
        <p className="lede">Every control below re-runs the same routing and decay engine as the route planner. Same inputs, same answer.</p>
        {!plan && <p className="warn">Plan a route first on the Shipment page; the simulator works on that shipment.</p>}
        <div className="scenarios" role="group" aria-label="Scenarios">
          {SCENARIOS.map((x) => <button key={x.id} className={`chip ${active === x.id ? "on" : ""}`} onClick={() => scenario(x)}>{x.label}</button>)}
          <button className="chip quiet" onClick={() => { setActive(null); apply(DEFAULT_KNOBS, BASE_COND, BASE_SHIP); }}>Reset</button>
        </div>
        <div className="cols2">
          <div>
            <Slider label="Cargo surroundings temperature" value={c.ambient_c} min={0} max={50} unit=" °C" onChange={(v) => s.setConditions({ ambient_c: v })} />
            <Slider label="Relative humidity" value={c.rh} min={20} max={100} unit="%" onChange={(v) => s.setConditions({ rh: v })} />
            <Slider label="Additional traffic delay" value={c.extra_delay_h} min={0} max={12} step={0.5} unit=" h" onChange={(v) => s.setConditions({ extra_delay_h: v })} />
            <Slider label="Road vibration severity" value={c.vibration} min={0} max={10} step={0.5} onChange={(v) => s.setConditions({ vibration: v })} hint="5 is the mapped baseline" />
            <Slider label="Traffic severity" value={c.traffic} min={0} max={10} step={0.5} onChange={(v) => s.setConditions({ traffic: v })} />
            <Slider label="Road quality" value={c.road_quality} min={0} max={10} step={0.5} onChange={(v) => s.setConditions({ road_quality: v })} hint="10 is as mapped" />
            <Slider label="Market waiting time" value={sh.market_wait_h} min={0} max={24} step={0.5} unit=" h" onChange={(v) => s.updateShipment({ market_wait_h: v })} />
            <Slider label="Cargo exposure before loading" value={sh.pre_dispatch_h} min={0} max={12} step={0.5} unit=" h" onChange={(v) => s.updateShipment({ pre_dispatch_h: v })} />
          </div>
          <div>
            <Select label="Crop" value={sh.crop} onChange={(v) => { s.updateShipment({ crop: v as CropId, condition: null, packaging: null, vehicle: null }); }}
              options={[{ value: "grapes", label: "Grapes" }, { value: "tomato", label: "Tomatoes" }, { value: "onion", label: "Onions" }]} />
            <Select label="Packaging quality" value={sh.packaging ?? crop.default_packaging} onChange={(v) => s.updateShipment({ packaging: v })}
              options={[{ value: "good", label: "Good" }, { value: "standard", label: "Standard" }, { value: "poor", label: "Poor" }]} />
            <Select label="Road classification" value={knobs.roadClass} onChange={(v) => k({ roadClass: v })}
              options={[{ value: "as_mapped", label: "As mapped" }, { value: "national", label: "National highways" }, { value: "state", label: "State highways" }, { value: "district", label: "District roads" }, { value: "rural", label: "Rural roads" }]} />
            <Select label="Vehicle type" value={sh.vehicle ?? crop.default_vehicle} onChange={(v) => s.updateShipment({ vehicle: v })}
              options={Object.entries(cfg.vehicles).map(([key, v]: [string, any]) => ({ value: key, label: v.label }))} />
            <Select label="Refrigeration" value={knobs.refrigeration} onChange={(v) => k({ refrigeration: v })}
              options={[{ value: "working", label: "Working" }, { value: "fails_mid", label: "Fails 3 h into the trip" }, { value: "failed", label: "Not working" }]} />
            <Select label={sh.crop === "onion" ? "Curing" : "Harvest maturity"} value={sh.condition ?? crop.default_condition} onChange={(v) => s.updateShipment({ condition: v })}
              options={Object.keys(crop.initial_quality).map((x) => ({ value: x, label: x.replace(/_/g, " ") }))} />
            <Select label="Destination market demand" value={knobs.demand} onChange={(v) => k({ demand: v })}
              options={[{ value: "normal", label: "Normal" }, { value: "low", label: "Low (price −15%, 4 h queue)" }, { value: "oversupplied", label: "Oversupplied (price −30%, 10 h queue)" }]} />
            <Select label="Disruption on the route" value={knobs.disruption} onChange={(v) => k({ disruption: v })}
              options={[{ value: "none", label: "None" }, { value: "congestion", label: "Congestion" }, { value: "closure", label: "Closure" }, { value: "partial_blockage", label: "Partial blockage" }, { value: "construction", label: "Construction" }, { value: "accident", label: "Accident" }, { value: "poor_road", label: "Poor road" }]} />
            <Select label="Vehicle breakdown" value={knobs.breakdown} onChange={(v) => k({ breakdown: v })}
              options={[{ value: "none", label: "None" }, { value: "short", label: "2 h roadside repair" }, { value: "long", label: "6 h wait for a mechanic" }]} />
            <Select label="Loading condition" value={sh.loading} onChange={(v) => s.updateShipment({ loading: v })}
              options={[{ value: "proper", label: "Properly stacked" }, { value: "loose", label: "Loose" }, { value: "overloaded", label: "Overloaded" }]} />
          </div>
        </div>
        <p className="hint">Demand effects on price and queue time are assumptions <Badge kind="ASSUMPTION" />. Arrival data is not used as demand.</p>
      </div>
      <div className="whatif-results">
        {s.busy && <p className="hint">Recomputing…</p>}
        {plan ? (
          <>
            <DecisionBanner plan={plan} />
            <section className="panel">
              <h2>Result <Badge kind="SIMULATED" /></h2>
              <CompareTable plan={plan} dispatchHour={sh.dispatch_hour} />
              <h3>Quality during the trip</h3>
              <QualityChart plan={plan} height={150} />
            </section>
          </>
        ) : <p className="empty-state">No shipment planned yet.</p>}
      </div>
    </div>
  );
}
