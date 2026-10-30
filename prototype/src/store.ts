import { create } from "zustand";
import { api, disruptionBody, get, post, shipmentBody } from "./api";
import type { Alert, AlertQueue, ConditionsIn, CropId, Disruption, Place, Plan, Shipment } from "./types";

export type Page = "shipment" | "route" | "crops" | "whatif" | "wastage" | "outcomes";

export interface Buffers { communication: number; acknowledgement: number; manoeuvre: number; review: number }

interface Replay {
  running: boolean;
  started: boolean;
  done: boolean;
  nowH: number;
  speed: number;              // simulated hours per real second
  history: number[];          // arcs already driven
  remaining: number[];        // arcs still ahead (index 0 = current)
  coords: number[][];
  arcT: number[];
  arcIdx: number[];
  edges: number[];            // edge id of each remaining arc
  held: boolean;              // stopped in front of a closure
  trail: number[][];
  truck: [number, number] | null;
  pos: number;                // index into `remaining`
  progress: number;
  lastAlertEvalH: number;
  pendingAck: { alertId: string; atH: number } | null;
  log: { h: number; text: string }[];
}

const emptyReplay: Replay = {
  running: false, started: false, done: false, nowH: 0, speed: 0.15, history: [], remaining: [], coords: [], arcT: [],
  arcIdx: [], edges: [], held: false, trail: [], truck: null, pos: 0, progress: 0, lastAlertEvalH: -1, pendingAck: null, log: [],
};

let seq = Math.floor(Math.random() * 9000) + 1000;
export const newShipmentId = () => `SHP-${new Date().getFullYear()}-${String(++seq).padStart(5, "0")}`;

const today = () => new Date().toISOString().slice(0, 10);

export function presetShipment(crop: CropId, cfg: any): Shipment {
  const c = cfg?.crops?.[crop];
  return {
    shipment_id: newShipmentId(), crop, kg: crop === "grapes" ? 8000 : 10000,
    condition: c?.default_condition ?? null, packaging: c?.default_packaging ?? null, loading: "proper",
    vehicle: c?.default_vehicle ?? null, refrigeration_ok: true, reefer_fail_at_h: null, handling_events: 2,
    pre_dispatch_h: 0, market_wait_h: 2, dispatch_hour: 20, dispatch_date: today(), price_rs_kg: null, q10: null,
    breakdown_h: 0,
  };
}

export const defaultConditions: ConditionsIn = { ambient_c: 32, rh: 60, traffic: 2, extra_delay_h: 0, road_quality: 10, vibration: 5 };

interface State {
  page: Page;
  cfg: any;
  presets: Record<string, { origin: Place; destination: Place; research: { origin: Place; destination: Place }[] }> | null;
  shipment: Shipment;
  origin: Place | null;
  destination: Place | null;
  conditions: ConditionsIn;
  disruptions: Disruption[];
  plan: Plan | null;
  originalArcs: number[] | null;
  busy: boolean;
  error: string | null;
  layers: { original: boolean; optimised: boolean; alternatives: boolean; markets: boolean };
  pickRoad: boolean;
  editing: string | null;
  focus: [number, number, number, number] | null;
  replay: Replay;
  buffers: Buffers;
  queue: AlertQueue | null;
  openAlert: string | null;
  messages: Record<string, string> | null;
  autoOptimise: boolean;

  set: (p: Partial<State>) => void;
  init: () => Promise<void>;
  choosePreset: (crop: CropId) => void;
  updateShipment: (p: Partial<Shipment>) => void;
  setConditions: (p: Partial<ConditionsIn>) => void;
  optimise: (opts?: { resetOriginal?: boolean }) => Promise<void>;
  addDisruptionAt: (lon: number, lat: number) => Promise<void>;
  updateDisruption: (id: string, p: Partial<Disruption>) => void;
  removeDisruption: (id: string) => void;
  clearDisruptions: () => void;
  startTrip: () => Promise<void>;
  stopTrip: () => void;
  tick: (dtSec: number) => void;
  evaluateAlerts: () => Promise<void>;
  actOnAlert: (a: Alert, action: string, extra?: { option?: number; until_h?: number }) => Promise<void>;
}

let optimiseTimer: ReturnType<typeof setTimeout> | null = null;

export const useStore = create<State>((set, getState) => ({
  page: "shipment",
  cfg: null,
  presets: null,
  shipment: presetShipment("grapes", null),
  origin: null,
  destination: null,
  conditions: { ...defaultConditions },
  disruptions: [],
  plan: null,
  originalArcs: null,
  busy: false,
  error: null,
  layers: { original: true, optimised: true, alternatives: true, markets: false },
  pickRoad: false,
  editing: null,
  focus: null,
  replay: { ...emptyReplay, speed: 0.15 },
  buffers: { communication: 3, acknowledgement: 5, manoeuvre: 2, review: 4 },
  queue: null,
  openAlert: null,
  messages: null,
  autoOptimise: true,

  set: (p) => set(p),

  init: async () => {
    const [cfg, presets] = await Promise.all([api.crops(), api.presets()]);
    set({ cfg, presets });
    getState().choosePreset("grapes");
  },

  choosePreset: (crop) => {
    const { cfg, presets } = getState();
    const p = presets?.[crop];
    const shipment = presetShipment(crop, cfg);
    if (crop === "tomato") shipment.dispatch_hour = 18;
    set({
      shipment, origin: p?.origin ?? null, destination: p?.destination ?? null, plan: null, originalArcs: null,
      disruptions: [], replay: { ...emptyReplay }, messages: null,
      conditions: crop === "grapes" ? { ...defaultConditions, ambient_c: 34 } : { ...defaultConditions },
    });
  },

  updateShipment: (p) => {
    set({ shipment: { ...getState().shipment, ...p } });
    scheduleRefresh();
  },

  setConditions: (p) => {
    set({ conditions: { ...getState().conditions, ...p } });
    scheduleRefresh();
  },

  optimise: async (opts) => {
    const s = getState();
    if (!s.origin || !s.destination) return set({ error: "Choose an origin and a destination first." });
    set({ busy: true, error: null });
    try {
      const keep = opts?.resetOriginal ? null : s.originalArcs;
      const plan = await api.optimise(s.shipment, s.origin, s.destination, s.conditions, s.disruptions, keep);
      const orig = plan.candidates.find((c) => c.id === plan.original_id);
      const all = plan.candidates.flatMap((c) => c.coords);
      const lons = all.map((c) => c[0]), lats = all.map((c) => c[1]);
      set({
        plan, originalArcs: keep ?? orig?.arcs ?? null, busy: false,
        focus: all.length && (!s.plan || opts?.resetOriginal) ? [Math.min(...lons), Math.min(...lats), Math.max(...lons), Math.max(...lats)] : s.focus,
      });
    } catch (e) {
      set({ busy: false, error: (e as Error).message });
    }
  },

  addDisruptionAt: async (lon, lat) => {
    try {
      const info = await api.edgeAt(lon, lat);
      const id = `D${Date.now().toString(36).slice(-5)}`;
      const name = info.ref || info.name || info.highway;
      const d: Disruption = {
        id, type: "closure", edges: info.way_edges, severity: 7, start_h: 0, end_h: null, heavy_only: true,
        alt_access: false, confirmed: true, label: `${name} (${info.way_len_km} km stretch)`, coords: info.way_coords,
      };
      set({ disruptions: [...getState().disruptions, d], editing: id, pickRoad: false });
      afterDisruptionChange();
    } catch (e) {
      set({ error: (e as Error).message, pickRoad: false });
    }
  },

  updateDisruption: (id, p) => {
    set({ disruptions: getState().disruptions.map((d) => (d.id === id ? { ...d, ...p } : d)) });
    afterDisruptionChange();
  },
  removeDisruption: (id) => {
    set({ disruptions: getState().disruptions.filter((d) => d.id !== id), editing: null });
    afterDisruptionChange();
  },
  clearDisruptions: () => {
    set({ disruptions: [], editing: null });
    afterDisruptionChange();
  },

  startTrip: async () => {
    const s = getState();
    if (!s.plan) return;
    const route = s.plan.candidates.find((c) => c.id === s.plan!.recommended_id) ?? s.plan.candidates.find((c) => c.id === s.plan!.original_id);
    if (!route) return;
    await fetch("/api/alerts", { method: "DELETE" });
    const tl = await api.timeline(s.shipment, route.arcs, s.plan.destination.node, 0, s.conditions);
    set({
      replay: { ...emptyReplay, running: true, started: true, speed: s.replay.speed, remaining: route.arcs, coords: tl.coords,
        arcT: tl.arc_t, arcIdx: tl.arc_coord_idx, edges: tl.edges, truck: tl.coords[0] as [number, number],
        log: [{ h: 0, text: `Dispatched on ${route.label.toLowerCase()}` }] },
      queue: null, messages: null,
    });
  },

  stopTrip: () => set({ replay: { ...getState().replay, running: !getState().replay.running } }),

  tick: (dtSec) => {
    const s = getState();
    const r = s.replay;
    if (!r.running || r.done || !r.arcT.length) return;
    // While a dispatcher decision is open, simulated time slows to one minute per second.
    const deciding = (s.queue?.alerts ?? []).some((a) => ["ALERTED", "UNDER_REVIEW", "APPROVED", "MODIFIED", "SENT_TO_DRIVER"].includes(a.state));
    const dh = dtSec * (deciding ? Math.min(r.speed, 1 / 60) : r.speed);
    const nowH = r.nowH + dh;
    let T = r.arcT;
    let pos = r.pos;
    while (pos < r.remaining.length - 1 && T[pos + 1] <= nowH) {
      if (blockedAt(s.disruptions, r.edges[pos + 1], T[pos + 1])) break;
      pos++;
    }
    // A closure on the next arc holds the truck at the junction: everything after it slips by the elapsed time.
    let held = false;
    if (pos < r.remaining.length - 1 && T[pos + 1] <= nowH && blockedAt(s.disruptions, r.edges[pos + 1], nowH)) {
      held = true;
      const slip = nowH - T[pos + 1];
      T = T.map((t, i) => (i > pos ? t + slip : t));
    }
    const done = nowH >= T[T.length - 1];
    const t0 = T[pos], t1 = T[pos + 1] ?? t0;
    const progress = done ? 1 : Math.min(1, Math.max(0, (nowH - t0) / Math.max(1e-6, t1 - t0)));
    const i0 = r.arcIdx[pos], i1 = r.arcIdx[pos + 1] ?? r.coords.length - 1;
    const fi = i0 + (i1 - i0) * progress;
    const a = r.coords[Math.floor(fi)], b = r.coords[Math.min(r.coords.length - 1, Math.floor(fi) + 1)];
    const f = fi - Math.floor(fi);
    const truck: [number, number] = done ? (r.coords[r.coords.length - 1] as [number, number]) : [a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f];
    const trail = r.coords.slice(0, Math.floor(fi) + 1);
    let log = done && !r.done ? [...r.log, { h: nowH, text: "Arrived at destination" }] : r.log;
    if (held && !r.held) log = [...log, { h: nowH, text: "Truck stopped: road closed ahead" }];
    if (!held && r.held) log = [...log, { h: nowH, text: "Road reopened, truck moving" }];
    set({ replay: { ...r, nowH, pos, progress, truck, trail, done, held, arcT: T, running: !done && r.running, log } });
    if (r.pendingAck && nowH >= r.pendingAck.atH) {
      const pa = r.pendingAck;
      set({ replay: { ...getState().replay, pendingAck: null } });
      const al = getState().queue?.alerts.find((x) => x.id === pa.alertId);
      if (al) void getState().actOnAlert(al, "acknowledge");
    }
    if (!done && nowH - r.lastAlertEvalH >= 0.25) {
      set({ replay: { ...getState().replay, lastAlertEvalH: nowH } });
      void getState().evaluateAlerts();
    }
  },

  evaluateAlerts: async () => {
    const s = getState();
    const r = s.replay;
    if (!s.plan || !r.started || r.done) return;
    try {
      const res = await post<{ queue: AlertQueue }>("/api/alerts/evaluate", {
        trucks: [{ shipment: shipmentBody(s.shipment), route_arcs: [...r.history, ...r.remaining], pos: r.history.length + r.pos,
          progress: r.progress, destination_node: s.plan.destination.node }],
        conditions: s.conditions, disruptions: s.disruptions.map(disruptionBody), now_h: r.nowH, buffers: s.buffers,
      });
      set({ queue: res.queue });
    } catch (e) {
      set({ error: (e as Error).message });
    }
  },

  actOnAlert: async (a, action, extra) => {
    const s = getState();
    const nowH = s.replay.nowH;
    try {
      const res = await fetch(`/api/alerts/${a.id}`, {
        method: "PATCH", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action, now_h: nowH, dest_name: s.destination?.market ?? "destination", ...extra }),
      });
      const j = await res.json();
      if (!res.ok) throw new Error(j.detail ?? res.statusText);
      const log = [...s.replay.log, { h: nowH, text: `${action[0].toUpperCase()}${action.slice(1)}: ${a.pnr_label ?? a.id}` }];
      if (action === "approve" || action === "modify") {
        set({ replay: { ...getState().replay, log } });
        await getState().actOnAlert(j.alert, "send");
        return;
      }
      if (action === "send") {
        set({ messages: j.messages, replay: { ...getState().replay, log,
          pendingAck: { alertId: a.id, atH: nowH + s.buffers.acknowledgement / 60 } } });
      } else if (action === "acknowledge" && j.new_route_arcs) {
        const r = getState().replay;
        const ahead: number[] = j.new_route_arcs;
        const history = [...r.history, ...r.remaining.slice(0, r.pos)];
        const tl = await api.timeline(s.shipment, ahead, s.plan!.destination.node, nowH, s.conditions);
        set({ replay: { ...r, history, remaining: ahead, coords: tl.coords, arcT: tl.arc_t, arcIdx: tl.arc_coord_idx, edges: tl.edges, held: false, pos: 0,
          progress: 0, trail: [], log: [...log, { h: nowH, text: "Driver acknowledged; truck now on the new route" }] } });
        await fetch(`/api/alerts/${a.id}`, { method: "PATCH", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ action: "execute", now_h: nowH }) });
      } else {
        set({ replay: { ...getState().replay, log } });
      }
      const q = await get<AlertQueue>(`/api/alerts?now_h=${nowH}&review_min=${s.buffers.review}`);
      set({ queue: q });
    } catch (e) {
      set({ error: (e as Error).message });
      const q = await get<AlertQueue>(`/api/alerts?now_h=${nowH}&review_min=${s.buffers.review}`);
      set({ queue: q });
    }
  },
}));

const BLOCKING = new Set(["closure", "vehicle_restriction"]);
function blockedAt(dis: Disruption[], edge: number | undefined, t: number): boolean {
  if (edge === undefined) return false;
  return dis.some((d) => d.edges.includes(edge) && t >= d.start_h && (d.end_h == null || t < d.end_h) && !d.alt_access &&
    (BLOCKING.has(d.type) ? d.type !== "vehicle_restriction" || d.heavy_only : d.type === "accident" && d.severity >= 7));
}

function scheduleRefresh() {
  const s = useStore.getState();
  if (!s.plan || !s.autoOptimise) return;
  if (optimiseTimer) clearTimeout(optimiseTimer);
  optimiseTimer = setTimeout(() => void useStore.getState().optimise(), 350);
}

function afterDisruptionChange() {
  const s = useStore.getState();
  if (s.replay.started && !s.replay.done) void s.evaluateAlerts();
  else scheduleRefresh();
}

if (import.meta.env.DEV) (window as unknown as { __store: typeof useStore }).__store = useStore;
