// Investor view: scale-up extrapolation, ROI, and reefer what-if. Every multiplier here is an ASSUMPTION shown on screen.
import { useState } from "react";
import { COST } from "../data/consignments";
import { fmtK, type Kpis } from "../model/sim";

const DAYS = 300, TRIPS_PER_DAY = 1.5, SUB_PER_MONTH = 1500;

export function ImpactPanel({ k }: { k: Kpis }) {
  const [trucks, setTrucks] = useState(1000);
  const [share, setShare] = useState(20);
  const perTripRs = Math.max(0, k.rupeesSaved / 3), perTripKg = Math.max(0, k.foodSavedKg / 3);
  const trips = trucks * DAYS * TRIPS_PER_DAY * (share / 100);
  const tonnesYr = (trips * perTripKg) / 1000;
  const rsYr = trips * perTripRs;
  const perTruckMonth = 25 * TRIPS_PER_DAY * (share / 100) * perTripRs;
  const payback = perTruckMonth > 0 ? (SUB_PER_MONTH / perTruckMonth) * 30 : Infinity;
  const reeferGain = k.reeferSellKg - k.baseSellKg, smartGain = k.smartSellKg - k.baseSellKg;

  return (
    <section className="card impact">
      <h3>Scale it up <small>extrapolation</small></h3>
      <label className="slider">
        <div className="slider-head"><span>Trucks on FreshRoute</span><b>{trucks.toLocaleString("en-IN")}</b></div>
        <input type="range" min={100} max={10000} step={100} value={trucks} onChange={(e) => setTrucks(+e.target.value)} />
      </label>
      <label className="slider">
        <div className="slider-head"><span>Trips hit by a disruption like this</span><b>{share}%</b></div>
        <input type="range" min={5} max={60} step={5} value={share} onChange={(e) => setShare(+e.target.value)} />
      </label>
      <div className="big-row">
        <div><b>{tonnesYr >= 1000 ? `${(tonnesYr / 1000).toFixed(1)}k` : tonnesYr.toFixed(0)} t</b><span>food saved / yr</span></div>
        <div><b>₹{rsYr >= 1e7 ? `${(rsYr / 1e7).toFixed(1)} Cr` : fmtK(rsYr)}</b><span>extra farmer income / yr</span></div>
      </div>
      {perTripRs < 1 && <div className="hint warn">Run a scenario (flood, heatwave, jam) to see savings. On a clear day both trucks do about the same.</div>}

      <h3>Unit economics</h3>
      <div className="roi">
        <div><span>Subscription</span><b>₹{SUB_PER_MONTH.toLocaleString("en-IN")}/truck-mo</b></div>
        <div><span>Saving</span><b>₹{fmtK(perTruckMonth)}/truck-mo</b></div>
        <div><span>Payback</span><b>{isFinite(payback) ? (payback < 1 ? "< 1 day" : `${payback.toFixed(0)} days`) : "—"}</b></div>
      </div>

      <h3>Reefer truck vs smart routing</h3>
      <div className="vs">
        <div><span>❄️ Reefer upgrade</span><b>+{fmtK(Math.max(0, reeferGain))} kg</b><small>₹{fmtK(COST.reeferCapex)} capex per truck</small></div>
        <div className="hl"><span>🧭 FreshRoute</span><b>+{fmtK(Math.max(0, smartGain))} kg</b><small>software only, no new trucks</small></div>
      </div>
      <div className="hint">Assumptions: {DAYS} operating days, {TRIPS_PER_DAY} trips/day, savings per affected trip as in this run, 400 g/meal*. Prices are Agmarknet medians (indicative).</div>
    </section>
  );
}
