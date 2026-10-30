import { useEffect, useId, useRef, useState } from "react";
import { api } from "../api";
import type { Place } from "../types";

export function Slider({ label, value, min, max, step = 1, unit = "", onChange, hint, format }: {
  label: string; value: number; min: number; max: number; step?: number; unit?: string;
  onChange: (v: number) => void; hint?: string; format?: (v: number) => string;
}) {
  const id = useId();
  return (
    <div className="field slider">
      <div className="field-head">
        <label htmlFor={id}>{label}</label>
        <output htmlFor={id}>{format ? format(value) : `${Number.isInteger(step) ? value : value.toFixed(1)}${unit}`}</output>
      </div>
      <input id={id} type="range" min={min} max={max} step={step} value={value} onChange={(e) => onChange(+e.target.value)} />
      {hint && <p className="hint">{hint}</p>}
    </div>
  );
}

export function Select<T extends string>({ label, value, options, onChange, hint }: {
  label: string; value: T; options: { value: T; label: string }[]; onChange: (v: T) => void; hint?: string;
}) {
  const id = useId();
  return (
    <div className="field">
      <label htmlFor={id}>{label}</label>
      <select id={id} value={value} onChange={(e) => onChange(e.target.value as T)}>
        {options.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
      </select>
      {hint && <p className="hint">{hint}</p>}
    </div>
  );
}

export function Toggle({ label, checked, onChange, hint }: { label: string; checked: boolean; onChange: (v: boolean) => void; hint?: string }) {
  return (
    <div className="field toggle-field">
      <label className="toggle">
        <input type="checkbox" checked={checked} onChange={(e) => onChange(e.target.checked)} />
        <span className="track" aria-hidden />
        <span>{label}</span>
      </label>
      {hint && <p className="hint">{hint}</p>}
    </div>
  );
}

export function NumberField({ label, value, onChange, unit, min, step = 1 }: {
  label: string; value: number; onChange: (v: number) => void; unit?: string; min?: number; step?: number;
}) {
  const id = useId();
  return (
    <div className="field">
      <label htmlFor={id}>{label}</label>
      <div className="with-unit">
        <input id={id} type="number" value={value} min={min} step={step} onChange={(e) => onChange(+e.target.value)} />
        {unit && <span>{unit}</span>}
      </div>
    </div>
  );
}

const SOURCE_TEXT: Record<string, string> = {
  "MAPPED ROAD": "Road geometry and class from OpenStreetMap",
  HISTORICAL: "Agmarknet daily arrivals and prices, Nov 2025 to Oct 2026",
  SIMULATED: "Produced by this model, not observed",
  ASSUMPTION: "Illustrative value awaiting calibration",
  SOURCED: "Taken from a cited source; hover the value for the citation",
  FORECAST: "Open-Meteo forecast",
};
export function Badge({ kind }: { kind: keyof typeof SOURCE_TEXT }) {
  return <span className={`badge b-${kind.split(" ")[0].toLowerCase()}`} title={SOURCE_TEXT[kind]}>{kind.charAt(0) + kind.slice(1).toLowerCase()}</span>;
}

/** Searchable market picker with state → district filtering. */
export function PlacePicker({ label, value, onChange, crop }: { label: string; value: Place | null; onChange: (p: Place) => void; crop?: string }) {
  const [states, setStates] = useState<{ state: string; markets: number }[]>([]);
  const [districts, setDistricts] = useState<{ district: string }[]>([]);
  const [state, setState] = useState("");
  const [district, setDistrict] = useState("");
  const [q, setQ] = useState("");
  const [hits, setHits] = useState<Place[]>([]);
  const [open, setOpen] = useState(false);
  const box = useRef<HTMLDivElement>(null);
  const id = useId();

  useEffect(() => { void api.states().then(setStates); }, []);
  useEffect(() => {
    setDistrict("");
    if (state) void api.districts(state).then(setDistricts);
    else setDistricts([]);
  }, [state]);
  useEffect(() => {
    if (!open) return;
    const t = setTimeout(() => void api.places(q, state || undefined, district || undefined, crop).then(setHits), 180);
    return () => clearTimeout(t);
  }, [q, state, district, open, crop]);
  useEffect(() => {
    const close = (e: MouseEvent) => { if (box.current && !box.current.contains(e.target as Node)) setOpen(false); };
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, []);

  return (
    <div className="place-picker" ref={box}>
      <span className="pp-label" id={id}>{label}</span>
      <div className="pp-filters">
        <select aria-label={`${label} state`} value={state} onChange={(e) => setState(e.target.value)}>
          <option value="">All states</option>
          {states.map((s) => <option key={s.state} value={s.state}>{s.state}</option>)}
        </select>
        <select aria-label={`${label} district`} value={district} onChange={(e) => setDistrict(e.target.value)} disabled={!state}>
          <option value="">All districts</option>
          {districts.map((d) => <option key={d.district} value={d.district}>{d.district}</option>)}
        </select>
      </div>
      <input aria-labelledby={id} className="pp-input" placeholder={value ? `${value.market}${value.district ? `, ${value.district}` : ""}` : "Search a market or district"}
        value={q} onFocus={() => setOpen(true)} onChange={(e) => { setQ(e.target.value); setOpen(true); }} />
      {value && !open && (
        <p className="hint">{value.state ? `${value.state}. ` : ""}{value.geocode_method === "district_centroid" ? "Location approximate (district centre)." : value.geocode_method === "manual_override" ? "Hand-placed yard location, needs verification." : "Located at the market town."}</p>
      )}
      {open && (
        <ul className="pp-list" role="listbox">
          {hits.length === 0 && <li className="empty">No market matches. Try a district name.</li>}
          {hits.map((h) => (
            <li key={h.market_id ?? h.market} role="option" aria-selected={value?.market_id === h.market_id}
              onMouseDown={() => { onChange(h); setOpen(false); setQ(""); }}>
              <span>{h.market}</span>
              <small>{h.district}, {h.state}{h.geocode_method === "district_centroid" ? " (approx.)" : ""}</small>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export const rs = (x: number | null | undefined) =>
  x == null || !isFinite(x) ? "n/a" : `₹${Math.round(x).toLocaleString("en-IN")}`;
export const kg = (x: number | null | undefined) =>
  x == null || !isFinite(x) ? "n/a" : x >= 1000 ? `${(x / 1000).toLocaleString("en-IN", { maximumFractionDigits: 2 })} t` : `${Math.round(x)} kg`;
export const hrs = (h: number) => (h < 1 ? `${Math.round(h * 60)} min` : `${Math.floor(h)} h ${String(Math.round((h % 1) * 60)).padStart(2, "0")} min`);
export const clock = (dispatchHour: number, h: number) => {
  const t = dispatchHour + h;
  const day = Math.floor(t / 24);
  const hh = Math.floor(t % 24), mm = Math.floor((t % 1) * 60);
  return `${day ? `Day ${day + 1}, ` : ""}${String(hh).padStart(2, "0")}:${String(mm).padStart(2, "0")}`;
};
