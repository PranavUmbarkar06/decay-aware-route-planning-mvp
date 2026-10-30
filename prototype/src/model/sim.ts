// Live simulation: each consignment runs twice.
//   smart    — spoilage-aware: edge weight = time cost + km cost + λ·k·t, picks the buyer with the best expected net,
//              re-plans on every environment change and every 30 sim-minutes, switches if the gain beats a margin.
//   baseline — status quo: picks the buyer by price minus transport cost (ignores spoilage) at dispatch,
//              drives the fastest route and never re-plans.
import { CROPS } from "../data/crops";
import { BUYERS, COST, CONSIGNMENTS, type Consignment, type Offer } from "../data/consignments";
import { sellableFraction } from "./arrhenius";
import { CALM, computeConditions, reeferRate, type Conditions, type EnvState } from "./env";
import { nearestNode, type Graph } from "./graph";
import { dijkstra, pathTo, sameSteps, type Step } from "./router";

export const START_HOUR = 6;
const REPLAN_EVERY_H = 0.5;
const MARGIN_FRAC = 0.01;     // switch only if expected net improves by > 1 % of cargo value
const OPERATING_H = 12;       // operating day for the throughput metric (ASSUMPTION)
const UNLOAD_H = 1;

export interface Outcome {
  buyer: string;
  hours: number;       // total trip hours (incl. already driven)
  km: number;
  qArr: number;
  sellFrac: number;
  sellKg: number;
  revenue: number;
  cost: number;
  net: number;
  profile: [number, number][]; // [trip hour, quality]
}

export interface Candidate extends Outcome { steps: Step[] }

export interface Truck {
  id: string;
  c: Consignment;
  smart: boolean;
  q: number;
  km: number;
  hours: number;
  steps: Step[];
  si: number;
  prog: number;        // km into steps[si]
  buyer: string;
  done: Outcome | null;
  lon: number;
  lat: number;
  reroutes: number;
  candidates: Candidate[];
  fastest: Candidate | null;   // Route A: fastest path to the current buyer
}

export interface SimEvent { id: number; t: number; truck: string; kind: "reroute" | "arrive" | "info"; text: string; hi?: string; mr?: string; color: string }

export interface Kpis {
  foodSavedKg: number;
  rupeesSaved: number;
  meals: number;
  smartTpd: number;
  baseTpd: number;
  smartCo2PerT: number;
  baseCo2PerT: number;
  smartSellKg: number;
  baseSellKg: number;
  totalKg: number;
  reeferSellKg: number;
  farmerGainPerTrip: number;
  reroutes: number;
  delivered: number;
}

export class Sim {
  g: Graph;
  env: EnvState = { ...CALM };
  cond: Conditions;
  hour = START_HOUR;
  trucks: Truck[] = [];
  events: SimEvent[] = [];
  version = 0;
  private buyerNode = new Map<string, number>();
  private originNode = new Map<string, number>();
  private lastReplan = START_HOUR;
  private lastCond = START_HOUR;
  private evId = 0;
  private cum = new Map<number, Float32Array>();

  constructor(g: Graph) {
    this.g = g;
    for (const b of Object.values(BUYERS)) this.buyerNode.set(b.id, nearestNode(g, b.lon, b.lat));
    for (const c of CONSIGNMENTS) this.originNode.set(c.id, nearestNode(g, c.origin.lon, c.origin.lat));
    this.cond = computeConditions(g, this.env, this.hour);
    this.reset();
  }

  get started() { return this.hour > START_HOUR; }

  reset() {
    this.hour = START_HOUR;
    this.lastReplan = this.lastCond = START_HOUR;
    this.events = [];
    this.cond = computeConditions(this.g, this.env, this.hour);
    this.trucks = [];
    for (const c of CONSIGNMENTS) {
      for (const smart of [true, false]) {
        const o = this.originNode.get(c.id)!;
        this.trucks.push({
          id: smart ? c.id : c.id + "·base", c, smart, q: c.q0, km: 0, hours: 0, steps: [], si: 0, prog: 0,
          buyer: "", done: null, lon: this.g.lon[o], lat: this.g.lat[o], reroutes: 0, candidates: [], fastest: null,
        });
      }
    }
    this.dispatchAll();
    this.log("info", "", `Dispatch 06:00 — 3 consignments loaded (${CONSIGNMENTS.map((c) => CROPS[c.crop].label).join(", ")})`, "#8aa0b8");
    this.version++;
  }

  setEnv(patch: Partial<EnvState>) {
    this.env = { ...this.env, ...patch };
    this.cond = computeConditions(this.g, this.env, this.hour);
    if (!this.started) this.dispatchAll();
    else for (const t of this.trucks) if (t.smart && !t.done) this.replan(t, "env");
    this.version++;
  }

  // ---------- planning ----------

  private offer(c: Consignment, buyer: string): Offer { return c.offers.find((o) => o.buyer === buyer)!; }

  private dispatchAll() {
    for (const t of this.trucks) {
      t.steps = []; t.si = 0; t.prog = 0;
      if (t.smart) this.replan(t, "dispatch");
      else this.dispatchBaseline(t);
    }
  }

  private dispatchBaseline(t: Truck) {
    const src = this.originNode.get(t.c.id)!;
    const tree = dijkstra(this.g, src, this.cond.hours);
    let best: { buyer: string; steps: Step[]; naive: number } | null = null;
    for (const o of t.c.offers) {
      const steps = pathTo(this.g, tree, this.buyerNode.get(o.buyer)!);
      if (!steps) continue;
      let km = 0, h = 0;
      for (const s of steps) { km += this.g.lenKm[s.e]; h += this.cond.hours[s.e]; }
      const naive = o.priceKg * t.c.kg * (1 - CROPS[t.c.crop].handlingPer100km * km / 100) - h * COST.perHour - km * COST.perKm;
      if (!best || naive > best.naive) best = { buyer: o.buyer, steps, naive };
    }
    t.buyer = best!.buyer; t.steps = best!.steps;
    const ev = this.evaluate(t, t.steps, 0, 0, t.buyer);
    t.fastest = { ...ev, steps: t.steps };
    t.candidates = [];
  }

  /** Outcome of driving `steps` (starting at index `from`, `prog` km into it) from the truck's current state. */
  evaluate(t: Truck, steps: Step[], from: number, prog: number, buyer: string, kOverride?: number): Outcome {
    const k = this.cond.k[t.c.crop], g = this.g;
    let q = t.q, km = 0, h = 0;
    const profile: [number, number][] = [[t.hours, q]];
    for (let i = from; i < steps.length; i++) {
      const e = steps[i].e;
      const frac = i === from ? Math.max(0, 1 - prog / g.lenKm[e]) : 1;
      const th = this.cond.hours[e] * frac;
      q *= Math.exp(-(kOverride ?? k[e]) * th);
      km += g.lenKm[e] * frac; h += th;
      if (i % 4 === 0 || i === steps.length - 1) profile.push([t.hours + h, q]);
    }
    return this.outcome(t, buyer, q, t.km + km, t.hours + h, profile, kOverride !== undefined);
  }

  private outcome(t: Truck, buyer: string, q: number, km: number, hours: number, profile: [number, number][], reefer = false): Outcome {
    const o = this.offer(t.c, buyer);
    const sellFrac = sellableFraction(CROPS[t.c.crop], q, km, o.tolerance ?? 1);
    const sellKg = sellFrac * t.c.kg;
    const revenue = sellKg * o.priceKg;
    const cost = hours * (COST.perHour + (reefer ? COST.reeferPerHour : 0)) + km * COST.perKm;
    return { buyer, hours, km, qArr: q, sellFrac, sellKg, revenue, cost, net: revenue - cost, profile };
  }

  private replan(t: Truck, why: "env" | "periodic" | "dispatch") {
    const g = this.g, cond = this.cond, k = cond.k[t.c.crop];
    // Commit to the edge in progress; plan from its far end.
    const prefix: Step[] = [];
    let root = this.originNode.get(t.c.id)!;
    if (t.si < t.steps.length && why !== "dispatch") {
      const s = t.steps[t.si];
      prefix.push(s);
      root = s.fwd ? g.ev[s.e] : g.eu[s.e];
    }
    const prog = prefix.length ? t.prog : 0;
    const current = t.steps.length ? this.evaluate(t, t.steps, t.si, t.prog, t.buyer) : null;

    const cargoValue = t.c.kg * Math.max(...t.c.offers.map((o) => o.priceKg));
    const lambdaFor = (ref: Outcome | null) => {
      if (!ref) return cargoValue * 0.5;
      const crop = CROPS[t.c.crop], o = this.offer(t.c, ref.buyer), eps = 0.05;
      const ds = sellableFraction(crop, ref.qArr, ref.km, o.tolerance ?? 1) -
        sellableFraction(crop, ref.qArr * Math.exp(-eps), ref.km, o.tolerance ?? 1);
      return Math.max(cargoValue * 0.05, (o.priceKg * t.c.kg * ds) / eps);
    };

    const search = (lambda: number) => {
      const w = new Float32Array(g.m);
      for (let e = 0; e < g.m; e++) w[e] = COST.perHour * cond.hours[e] + COST.perKm * g.lenKm[e] + lambda * k[e] * cond.hours[e];
      const tree = dijkstra(g, root, w);
      const cands: Candidate[] = [];
      for (const o of t.c.offers) {
        const p = pathTo(g, tree, this.buyerNode.get(o.buyer)!);
        if (!p) continue;
        const steps = [...prefix, ...p];
        cands.push({ ...this.evaluate(t, steps, 0, prog, o.buyer), steps });
      }
      cands.sort((a, b) => b.net - a.net);
      return cands;
    };

    let cands = search(lambdaFor(current));
    cands = search(lambdaFor(cands[0]));
    const best = cands[0];
    t.candidates = cands;

    const switchTo = (c: Candidate) => {
      t.steps = c.steps; t.si = 0; t.prog = prog; t.buyer = c.buyer;
    };

    if (!current || why === "dispatch") switchTo(best);
    else if (best.net > current.net + MARGIN_FRAC * cargoValue && !(best.buyer === t.buyer && sameSteps(best.steps.slice(prefix.length), t.steps.slice(t.si + 1)))) {
      const crop = CROPS[t.c.crop];
      const from = BUYERS[t.buyer].short, to = BUYERS[best.buyer].short;
      const gain = best.net - current.net;
      const destChange = best.buyer !== t.buyer;
      const text = destChange
        ? `${t.c.id} ${crop.label}: diverted ${from} → ${to}. Sellable ${pct(current.sellFrac)} → ${pct(best.sellFrac)}, ETA ${fmtH(current.hours - t.hours)} → ${fmtH(best.hours - t.hours)}, +₹${fmtK(gain)}`
        : `${t.c.id} ${crop.label}: new road to ${to}. ETA ${fmtH(current.hours - t.hours)} → ${fmtH(best.hours - t.hours)}, sellable ${pct(current.sellFrac)} → ${pct(best.sellFrac)}, +₹${fmtK(gain)}`;
      const hi = destChange
        ? `मार्ग बदला: ${crop.hi} अब ${to} मंडी जाएगा। अनुमानित बचत ₹${fmtK(gain)}`
        : `नया रास्ता: ${to} के लिए आगे का मार्ग बदला गया। बचत ₹${fmtK(gain)}`;
      const mr = destChange
        ? `मार्ग बदलला: ${crop.mr} आता ${to} बाजारात न्या. अंदाजे बचत ₹${fmtK(gain)}`
        : `नवीन रस्ता: ${to} कडे जाण्याचा मार्ग बदलला. बचत ₹${fmtK(gain)}`;
      switchTo(best);
      t.reroutes++;
      this.log("reroute", t.id, text, crop.color, hi, mr);
    }

    // Route A for the compare panel: fastest path to the chosen buyer.
    const fast = pathTo(g, dijkstra(g, root, cond.hours), this.buyerNode.get(t.buyer)!);
    if (fast) { const steps = [...prefix, ...fast]; t.fastest = { ...this.evaluate(t, steps, 0, prog, t.buyer), steps }; }
  }

  // ---------- time ----------

  step(dtH: number) {
    if (this.trucks.every((t) => t.done)) return;
    this.hour += dtH;
    if (this.hour - this.lastCond >= 0.25) {
      this.lastCond = this.hour;
      this.cond = computeConditions(this.g, this.env, this.hour);
    }
    for (const t of this.trucks) if (!t.done) this.move(t, dtH);
    if (this.hour - this.lastReplan >= REPLAN_EVERY_H) {
      this.lastReplan = this.hour;
      for (const t of this.trucks) if (t.smart && !t.done) this.replan(t, "periodic");
    }
    this.version++;
  }

  private move(t: Truck, dt: number) {
    const g = this.g, k = this.cond.k[t.c.crop];
    let rem = dt;
    while (rem > 1e-9 && t.si < t.steps.length) {
      const e = t.steps[t.si].e, v = this.cond.speed[e];
      const left = g.lenKm[e] - t.prog, tLeft = left / v;
      if (tLeft <= rem) {
        t.q *= Math.exp(-k[e] * tLeft); t.km += left; t.hours += tLeft; rem -= tLeft; t.si++; t.prog = 0;
      } else {
        const d = v * rem;
        t.q *= Math.exp(-k[e] * rem); t.km += d; t.hours += rem; t.prog += d; rem = 0;
      }
    }
    this.position(t);
    if (t.si >= t.steps.length) {
      t.done = this.outcome(t, t.buyer, t.q, t.km, t.hours, []);
      const b = BUYERS[t.buyer];
      this.log("arrive", t.id, `${t.smart ? t.c.id : t.c.id + " baseline"} arrived ${b.short}: ${pct(t.done.sellFrac)} sellable (${(t.done.sellKg / 1000).toFixed(1)} t), net ₹${fmtK(t.done.net)}`,
        t.smart ? CROPS[t.c.crop].color : "#6b7a90");
    }
  }

  private position(t: Truck) {
    const g = this.g;
    if (t.si >= t.steps.length) {
      const b = BUYERS[t.buyer]; t.lon = b.lon; t.lat = b.lat; return;
    }
    const s = t.steps[t.si], geom = g.geoms[s.e];
    let cum = this.cum.get(s.e);
    if (!cum) {
      cum = new Float32Array(geom.length / 2);
      for (let i = 1; i < cum.length; i++) cum[i] = cum[i - 1] + Math.hypot(geom[2 * i] - geom[2 * i - 2], geom[2 * i + 1] - geom[2 * i - 1]);
      this.cum.set(s.e, cum);
    }
    let f = Math.min(1, t.prog / g.lenKm[s.e]);
    if (!s.fwd) f = 1 - f;
    const target = f * cum[cum.length - 1];
    let i = 1;
    while (i < cum.length - 1 && cum[i] < target) i++;
    const seg = cum[i] - cum[i - 1] || 1, a = (target - cum[i - 1]) / seg;
    t.lon = geom[2 * i - 2] + (geom[2 * i] - geom[2 * i - 2]) * a;
    t.lat = geom[2 * i - 1] + (geom[2 * i + 1] - geom[2 * i - 1]) * a;
  }

  // ---------- reporting ----------

  projection(t: Truck): Outcome {
    return t.done ?? this.evaluate(t, t.steps, t.si, t.prog, t.buyer);
  }

  remainingCoords(t: Truck, steps = t.steps, from = t.si): number[][] {
    const out: number[][] = [];
    if (!t.done) out.push([t.lon, t.lat]);
    for (let i = from; i < steps.length; i++) {
      const s = steps[i], g = this.g.geoms[s.e];
      const n = g.length / 2;
      for (let j = 0; j < n; j++) {
        const idx = s.fwd ? j : n - 1 - j;
        if (i === from && j === 0) continue;
        out.push([g[2 * idx], g[2 * idx + 1]]);
      }
    }
    return out;
  }

  kpis(): Kpis {
    let smartSell = 0, baseSell = 0, smartNet = 0, baseNet = 0, smartKm = 0, baseKm = 0;
    let smartTpd = 0, baseTpd = 0, reefer = 0, total = 0, reroutes = 0, delivered = 0;
    for (const t of this.trucks) {
      const p = this.projection(t);
      const tpd = (p.sellKg / 1000) * (OPERATING_H / (2 * p.hours + UNLOAD_H));
      if (t.smart) {
        smartSell += p.sellKg; smartNet += p.net; smartKm += p.km; smartTpd += tpd; total += t.c.kg; reroutes += t.reroutes;
        if (t.done) delivered++;
      } else {
        baseSell += p.sellKg; baseNet += p.net; baseKm += p.km; baseTpd += tpd;
        // Reefer what-if: same baseline route, cargo held at set point from dispatch.
        const ghost: Truck = { ...t, q: t.c.q0, km: 0, hours: 0 };
        const steps = t.fastest?.steps ?? t.steps;
        reefer += this.evaluate(ghost, steps, 0, 0, t.buyer, reeferRate(t.c.crop, this.env.q10)).sellKg;
      }
    }
    const n = CONSIGNMENTS.length;
    return {
      foodSavedKg: smartSell - baseSell,
      rupeesSaved: smartNet - baseNet,
      meals: (smartSell - baseSell) / 0.4,
      smartTpd: smartTpd / n,
      baseTpd: baseTpd / n,
      smartCo2PerT: (smartKm * COST.co2PerKm) / Math.max(0.1, smartSell / 1000),
      baseCo2PerT: (baseKm * COST.co2PerKm) / Math.max(0.1, baseSell / 1000),
      smartSellKg: smartSell,
      baseSellKg: baseSell,
      totalKg: total,
      reeferSellKg: reefer,
      farmerGainPerTrip: (smartNet - baseNet) / n,
      reroutes,
      delivered,
    };
  }

  private log(kind: SimEvent["kind"], truck: string, text: string, color: string, hi?: string, mr?: string) {
    this.events.unshift({ id: ++this.evId, t: this.hour, truck, kind, text, hi, mr, color });
    if (this.events.length > 60) this.events.pop();
  }
}

export const pct = (x: number) => `${Math.round(x * 100)}%`;
export const fmtH = (h: number) => (h < 1 ? `${Math.round(h * 60)} min` : `${Math.floor(h)}h ${String(Math.round((h % 1) * 60)).padStart(2, "0")}m`);
export const fmtK = (x: number) => (Math.abs(x) >= 1e5 ? `${(x / 1e5).toFixed(2)} L` : Math.abs(x) >= 1000 ? `${(x / 1000).toFixed(1)}k` : `${Math.round(x)}`);
export const clock = (h: number) => `${String(Math.floor(h % 24)).padStart(2, "0")}:${String(Math.floor((h % 1) * 60)).padStart(2, "0")}`;
