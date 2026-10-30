import type { EnvState } from "../model/env";
import type { Tool } from "./MapPane";

export type PresetId = "calm" | "heatwave" | "flood" | "festival";

const PRESETS: { id: PresetId; icon: string; label: string; sub: string }[] = [
  { id: "flood", icon: "🌧️", label: "Monsoon flood", sub: "NH-44 under water at Jamtha" },
  { id: "heatwave", icon: "🔥", label: "Vidarbha heatwave", sub: "46 °C, dry wind" },
  { id: "festival", icon: "🎆", label: "Festival traffic", sub: "Nagpur city gridlock" },
  { id: "calm", icon: "🌤️", label: "Clear day", sub: "reset conditions" },
];

const TOOLS: { id: Tool; icon: string; label: string }[] = [
  { id: "pan", icon: "✋", label: "Move" },
  { id: "storm", icon: "⛈️", label: "Storm" },
  { id: "heat", icon: "🔥", label: "Heat" },
  { id: "jam", icon: "🚦", label: "Jam" },
  { id: "close", icon: "⛔", label: "Close road" },
  { id: "erase", icon: "🧽", label: "Erase" },
];

function Slider({ label, value, min, max, step, unit, onChange, hint }: {
  label: string; value: number; min: number; max: number; step: number; unit: string; onChange: (v: number) => void; hint?: string;
}) {
  return (
    <label className="slider">
      <div className="slider-head"><span>{label}</span><b>{unit === "%" ? Math.round(value) : value.toFixed(step < 1 ? 1 : 0)}{unit}</b></div>
      <input type="range" min={min} max={max} step={step} value={value} onChange={(e) => onChange(+e.target.value)} />
      {hint && <div className="hint">{hint}</div>}
    </label>
  );
}

export function ControlPanel({ env, onEnv, playing, onPlay, speed, onSpeed, onReset, tool, onTool, cellRadius, onCellRadius, onPreset, clockText, peak }: {
  env: EnvState; onEnv: (p: Partial<EnvState>) => void;
  playing: boolean; onPlay: () => void; speed: number; onSpeed: (s: number) => void; onReset: () => void;
  tool: Tool; onTool: (t: Tool) => void; cellRadius: number; onCellRadius: (r: number) => void;
  onPreset: (p: PresetId) => void; clockText: string; peak: boolean;
}) {
  return (
    <aside className="panel left">
      <section className="card">
        <div className="clock-row">
          <button className={`play ${playing ? "on" : ""}`} onClick={onPlay}>{playing ? "❚❚ Pause" : "▶ Run trucks"}</button>
          <button className="ghost-btn" onClick={onReset} title="Reset trucks to the depot">↺</button>
          <div className="clock"><span>{clockText}</span>{peak && <em>peak</em>}</div>
        </div>
        <div className="seg">
          {[0.1, 0.25, 0.5, 1].map((s) => (
            <button key={s} className={speed === s ? "on" : ""} onClick={() => onSpeed(s)}>{s * 60} min/s</button>
          ))}
        </div>
      </section>

      <section className="card">
        <h3>One-click scenarios</h3>
        <div className="presets">
          {PRESETS.map((p) => (
            <button key={p.id} className="preset" onClick={() => onPreset(p.id)}>
              <span className="ico">{p.icon}</span><span><b>{p.label}</b><small>{p.sub}</small></span>
            </button>
          ))}
        </div>
      </section>

      <section className="card">
        <h3>Conditions</h3>
        <Slider label="Temperature" value={env.ambientC} min={15} max={48} step={1} unit="°C" onChange={(v) => onEnv({ ambientC: v })} />
        <Slider label="Humidity" value={env.rh} min={20} max={100} step={1} unit="%" onChange={(v) => onEnv({ rh: v })} />
        <Slider label="Rain" value={env.rain * 100} min={0} max={100} step={5} unit="%" onChange={(v) => onEnv({ rain: v / 100 })} hint="slows every road, raises humidity" />
        <Slider label="Traffic" value={env.traffic} min={1} max={3} step={0.1} unit="×" onChange={(v) => onEnv({ traffic: v })} hint="slower trucks + idling heat in the cargo" />
        <Slider label="Q10 (Arrhenius)" value={env.q10} min={2} max={3} step={0.1} unit="" onChange={(v) => onEnv({ q10: v })} hint="rot speeds up Q10× per +10 °C (FAO 152: 2–3)" />
      </section>

      <section className="card">
        <h3>Draw on the map</h3>
        <div className="tools">
          {TOOLS.map((t) => (
            <button key={t.id} className={tool === t.id ? "on" : ""} onClick={() => onTool(t.id)}>
              <span>{t.icon}</span>{t.label}
            </button>
          ))}
        </div>
        <Slider label="Cell radius" value={cellRadius} min={4} max={30} step={1} unit=" km" onChange={onCellRadius} />
        <div className="hint">Click the map to drop a cell, then drag it onto a truck's road. Use "Close road" for an accident.</div>
      </section>
    </aside>
  );
}
