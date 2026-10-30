import { NumberField, PlacePicker, Select, Slider, Toggle } from "../components/controls";
import { newShipmentId, useStore } from "../store";
import type { CropId } from "../types";

const CROP_CARDS: { id: CropId; title: string; line: string }[] = [
  { id: "grapes", title: "Grapes", line: "Breaks under vibration, browns in dry heat. Smooth highways and a working reefer matter most." },
  { id: "tomato", title: "Tomatoes", line: "Bruise in crates and ripen fast in heat. Time on the road and road quality both cost." },
  { id: "onion", title: "Onions", line: "Cured bulbs shrug off bumps but rot in humid, unventilated bodies. Rarely worth a detour." },
];

const LABELS: Record<string, string> = {
  pre_cooled: "Pre-cooled", field_fresh: "Field fresh", delayed_1d: "Held a day before loading",
  mature_green: "Mature green", turning: "Turning", red_ripe: "Red ripe",
  cured: "Fully cured", partly_cured: "Partly cured", uncured: "Uncured",
  good: "Good (vented, cushioned)", standard: "Standard", poor: "Poor (overfilled, no liners)",
  proper: "Properly stacked", loose: "Loose", overloaded: "Overloaded",
};

export function ShipmentPage() {
  const s = useStore();
  const cfg = s.cfg;
  const crop = cfg?.crops?.[s.shipment.crop];
  const destPrice = s.destination?.[`${s.shipment.crop}_price_rs_q` as "tomato_price_rs_q"];
  const go = async () => {
    s.set({ page: "route" });
    await s.optimise({ resetOriginal: true });
  };
  if (!cfg) return <p className="empty-state">Loading crop profiles…</p>;
  const up = s.updateShipment;
  const sh = s.shipment;
  return (
    <div className="page page-shipment">
      <h1>New shipment</h1>
      <p className="lede">Pick a crop to load its sensitivity profile and default corridor. Change anything for this load only; the crop profile stays as it is.</p>
      <div className="crop-cards" role="radiogroup" aria-label="Crop">
        {CROP_CARDS.map((c) => (
          <button key={c.id} role="radio" aria-checked={sh.crop === c.id} className={`crop-card c-${c.id} ${sh.crop === c.id ? "on" : ""}`}
            onClick={() => s.choosePreset(c.id)}>
            <span className="crop-name">{c.title}</span>
            <span className="crop-line">{c.line}</span>
            <span className="crop-corridor">{cfg.crops[c.id].default_corridor.origin} to {cfg.crops[c.id].default_corridor.destination}</span>
          </button>
        ))}
      </div>

      <div className="form-grid">
        <section className="panel">
          <h2>Route</h2>
          <PlacePicker label="Origin" value={s.origin} onChange={(p) => s.set({ origin: p, plan: null, originalArcs: null })} crop={sh.crop} />
          <PlacePicker label="Destination" value={s.destination} onChange={(p) => s.set({ destination: p, plan: null, originalArcs: null })} />
          {s.presets && (
            <div className="research">
              <span>Research corridors:</span>
              {s.presets[sh.crop].research.map((r) => (
                <button key={r.destination.market} className="btn quiet small" onClick={() => s.set({ origin: r.origin, destination: r.destination, plan: null, originalArcs: null })}>
                  {r.origin.market.replace(" APMC", "")} to {r.destination.market.replace("APMC ", "")}
                </button>
              ))}
            </div>
          )}
        </section>

        <section className="panel">
          <h2>Load</h2>
          <div className="row2">
            <div className="field"><label>Shipment ID</label><div className="readonly">{sh.shipment_id}
              <button className="btn quiet small" onClick={() => up({ shipment_id: newShipmentId() })}>New ID</button></div></div>
            <NumberField label="Quantity" unit="kg" value={sh.kg} min={500} step={500} onChange={(v) => up({ kg: v })} />
          </div>
          <div className="row2">
            <Select label={crop.label === "Tomato" ? "Harvest maturity" : crop.label === "Onion" ? "Curing" : "Condition at loading"}
              value={sh.condition ?? crop.default_condition} onChange={(v) => up({ condition: v })}
              options={Object.keys(crop.initial_quality).map((k) => ({ value: k, label: LABELS[k] ?? k }))} />
            <Select label="Packaging" value={sh.packaging ?? crop.default_packaging} onChange={(v) => up({ packaging: v })}
              options={Object.keys(cfg.packaging_factor).map((k) => ({ value: k, label: LABELS[k] ?? k }))} hint={crop.packaging_note} />
          </div>
          <div className="row2">
            <Select label="Vehicle" value={sh.vehicle ?? crop.default_vehicle} onChange={(v) => up({ vehicle: v })}
              options={Object.entries(cfg.vehicles).map(([k, v]: [string, any]) => ({ value: k, label: v.label }))} />
            <Select label="Loading" value={sh.loading} onChange={(v) => up({ loading: v })}
              options={Object.keys(cfg.loading_factor).map((k) => ({ value: k, label: LABELS[k] ?? k }))} />
          </div>
          {(sh.vehicle ?? crop.default_vehicle) === "reefer" && (
            <Toggle label="Refrigeration working" checked={sh.refrigeration_ok} onChange={(v) => up({ refrigeration_ok: v })} />
          )}
        </section>

        <section className="panel">
          <h2>Timing and price</h2>
          <div className="row2">
            <div className="field"><label htmlFor="dd">Dispatch date</label><input id="dd" type="date" value={sh.dispatch_date} onChange={(e) => up({ dispatch_date: e.target.value })} /></div>
            <div className="field"><label htmlFor="dt">Dispatch time</label>
              <input id="dt" type="time" value={`${String(Math.floor(sh.dispatch_hour)).padStart(2, "0")}:${String(Math.round((sh.dispatch_hour % 1) * 60)).padStart(2, "0")}`}
                onChange={(e) => { const [h, m] = e.target.value.split(":").map(Number); up({ dispatch_hour: h + m / 60 }); }} /></div>
          </div>
          <Slider label="Waiting at the farm before loading" value={sh.pre_dispatch_h} min={0} max={12} step={0.5} unit=" h" onChange={(v) => up({ pre_dispatch_h: v })} />
          <Slider label="Waiting at the market to unload" value={sh.market_wait_h} min={0} max={24} step={0.5} unit=" h" onChange={(v) => up({ market_wait_h: v })} />
          <NumberField label="Selling price" unit="₹/kg" step={0.5}
            value={sh.price_rs_kg ?? (destPrice ? +(destPrice / 100).toFixed(1) : cfg.crops[sh.crop].default_price_rs_kg.value)}
            onChange={(v) => up({ price_rs_kg: v })} />
          <p className="hint">{sh.price_rs_kg == null && destPrice ? "Median Agmarknet modal price at the destination over the past year (historical)." : "Edited price; used for every value figure."}</p>
        </section>
      </div>
      <div className="cta-row">
        <button className="btn primary big" disabled={!s.origin || !s.destination} onClick={() => void go()}>Plan route</button>
        {s.error && <p className="warn">{s.error}</p>}
      </div>
    </div>
  );
}
