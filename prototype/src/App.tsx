import { useCallback, useEffect, useRef, useState } from "react";
import { CALM, isPeak, type CellKind, type EnvState } from "./model/env";
import { loadGraph } from "./model/graph";
import { clock, Sim, type SimEvent } from "./model/sim";
import { ComparePanel } from "./ui/ComparePanel";
import { ControlPanel, type PresetId } from "./ui/ControlPanel";
import { DriverAlert, EventFeed } from "./ui/EventFeed";
import { ImpactPanel } from "./ui/ImpactPanel";
import { KpiBar } from "./ui/KpiBar";
import { MapPane, type Tool } from "./ui/MapPane";

const PRESETS: Record<PresetId, Partial<EnvState>> = {
  calm: { ...CALM },
  heatwave: { ambientC: 46, rh: 28, rain: 0, traffic: 1.1, cells: [{ id: 101, kind: "heat", lon: 79.0, lat: 20.95, radiusKm: 22 }], closed: [] },
  flood: { ambientC: 29, rh: 85, rain: 0.6, traffic: 1.2, cells: [{ id: 102, kind: "storm", lon: 79.02, lat: 21.04, radiusKm: 10 }], closed: [] },
  festival: { ambientC: 33, rh: 55, rain: 0, traffic: 1.8, cells: [{ id: 103, kind: "jam", lon: 79.11, lat: 21.15, radiusKm: 9 }], closed: [] },
};

export function App() {
  const [sim, setSim] = useState<Sim | null>(null);
  const [tick, setTick] = useState(0);
  const [envTick, setEnvTick] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [speed, setSpeed] = useState(0.25);
  const [tool, setTool] = useState<Tool>("pan");
  const [cellRadius, setCellRadius] = useState(12);
  const [selected, setSelected] = useState("T1");
  const [alert, setAlert] = useState<SimEvent | null>(null);
  const [tab, setTab] = useState<"compare" | "impact">("compare");
  const nextCell = useRef(1);
  const lastAlert = useRef(0);

  useEffect(() => {
    loadGraph().then((g) => {
      const s = new Sim(g);
      if (import.meta.env.DEV) (window as unknown as { __sim: Sim; __tick: () => void }).__sim = s;
      setSim(s);
    });
  }, []);
  if (import.meta.env.DEV) (window as unknown as { __tick: () => void }).__tick = () => setTick((t) => t + 1);

  // Simulation loop: advance sim time from real time; re-render ~10×/s.
  useEffect(() => {
    if (!sim || !playing) return;
    let raf = 0, last = performance.now(), lastPaint = 0;
    const loop = (now: number) => {
      const dt = Math.min(0.1, (now - last) / 1000);
      last = now;
      sim.step(dt * speed);
      if (now - lastPaint > 90) { lastPaint = now; setTick((t) => t + 1); }
      if (sim.trucks.every((t) => t.done)) { setPlaying(false); setTick((t) => t + 1); return; }
      raf = requestAnimationFrame(loop);
    };
    raf = requestAnimationFrame(loop);
    return () => cancelAnimationFrame(raf);
  }, [sim, playing, speed]);

  // Pop the driver phone for each new reroute.
  useEffect(() => {
    const ev = sim?.events.find((e) => e.kind === "reroute");
    if (ev && ev.id > lastAlert.current) {
      lastAlert.current = ev.id;
      setAlert(ev);
      const h = setTimeout(() => setAlert((a) => (a?.id === ev.id ? null : a)), 7000);
      return () => clearTimeout(h);
    }
  }, [tick, envTick, sim]);

  const pending = useRef<Partial<EnvState> | null>(null);
  const onEnv = useCallback((p: Partial<EnvState>) => {
    if (!sim) return;
    // Coalesce rapid slider moves into one recompute per frame.
    const first = !pending.current;
    pending.current = { ...(pending.current ?? {}), ...p };
    if (first) setTimeout(() => {
      if (!pending.current) return;
      sim.setEnv(pending.current);
      pending.current = null;
      setEnvTick((t) => t + 1);
    }, 30);
  }, [sim]);

  if (!sim) return <div className="loading">Loading Nagpur road network…</div>;

  const k = sim.kpis();
  const env = { ...sim.env, ...(pending.current ?? {}) };

  return (
    <div className="app">
      <KpiBar k={k} />
      <ControlPanel
        env={env} onEnv={onEnv}
        playing={playing} onPlay={() => { if (sim.trucks.every((t) => t.done)) { sim.reset(); } setPlaying((p) => !p); }}
        speed={speed} onSpeed={setSpeed}
        onReset={() => { setPlaying(false); sim.reset(); setAlert(null); setTick((t) => t + 1); }}
        tool={tool} onTool={setTool} cellRadius={cellRadius} onCellRadius={setCellRadius}
        onPreset={(p) => onEnv(PRESETS[p])}
        clockText={clock(sim.hour)} peak={isPeak(sim.hour)}
      />
      <main className="center">
        <MapPane
          sim={sim} tick={tick} envTick={envTick} tool={tool} cellRadius={cellRadius} selected={selected}
          onSelect={setSelected}
          onAddCell={(kind: CellKind, lon, lat) => onEnv({ cells: [...sim.env.cells, { id: nextCell.current++, kind, lon, lat, radiusKm: cellRadius }] })}
          onMoveCell={(id, lon, lat) => onEnv({ cells: sim.env.cells.map((c) => (c.id === id ? { ...c, lon, lat } : c)) })}
          onEraseCell={(id) => onEnv({ cells: sim.env.cells.filter((c) => c.id !== id) })}
          onToggleRoad={(e) => onEnv({ closed: sim.env.closed.includes(e) ? sim.env.closed.filter((x) => x !== e) : [...sim.env.closed, e] })}
        />
        <div className="map-legend">
          <span><i className="sw" style={{ background: "#ff5a5f" }} />solid = FreshRoute truck</span>
          <span><i className="sw dashed" />dashed = status-quo truck</span>
          <span><i className="sw dotted" />dotted = Route A (fastest)</span>
          <span className="grad">road stress <i /></span>
        </div>
        {alert && <DriverAlert event={alert} onClose={() => setAlert(null)} />}
      </main>
      <aside className="panel right">
        <div className="seg big">
          <button className={tab === "compare" ? "on" : ""} onClick={() => setTab("compare")}>Compare routes</button>
          <button className={tab === "impact" ? "on" : ""} onClick={() => setTab("impact")}>Investor view</button>
        </div>
        {tab === "compare" ? <ComparePanel sim={sim} selected={selected} onSelect={setSelected} /> : <ImpactPanel k={k} />}
        <EventFeed events={sim.events} />
      </aside>
    </div>
  );
}
