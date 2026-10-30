// Environment: global sliders + local weather cells + closed roads -> per-edge travel time and cargo climate.
// Speeds per road class from config/speeds.yaml; peak hours from config/simulation.yaml. Cell effects are ASSUMPTIONS.
import { CROPS, type CropId } from "../data/crops";
import { eaFromQ10, rate } from "./arrhenius";
import { kmBetween, type Graph } from "./graph";

export type CellKind = "heat" | "storm" | "jam";
export interface Cell { id: number; kind: CellKind; lon: number; lat: number; radiusKm: number }

export interface EnvState {
  ambientC: number;   // 15–48
  rh: number;         // 20–100 %
  rain: number;       // 0–1
  traffic: number;    // 1–3 multiplier
  q10: number;        // 2–3
  cells: Cell[];
  closed: number[];   // edge ids
}

export const CALM: EnvState = { ambientC: 30, rh: 60, rain: 0, traffic: 1, q10: 2.5, cells: [], closed: [] };

const CLASS_KMH: Record<string, number> = {
  motorway: 55, motorway_link: 30, trunk: 45, trunk_link: 25, primary: 40, primary_link: 25,
  secondary: 35, secondary_link: 20, tertiary: 30, tertiary_link: 20,
};
const PEAKS: [number, number][] = [[8, 11], [17, 21]];
const PEAK_EXTRA = 0.3;
const FLOOD_KMH = 3;
const CLOSED_KMH = 0.5;

export function isPeak(hourOfDay: number): boolean {
  const h = ((hourOfDay % 24) + 24) % 24;
  return PEAKS.some(([a, b]) => h >= a && h < b);
}

export interface Conditions {
  speed: Float32Array;    // km/h
  hours: Float32Array;    // traversal time
  tempC: Float32Array;    // cargo temperature in an open truck
  rh: Float32Array;
  stress: Float32Array;   // 0..1 for map colouring
  flooded: Uint8Array;
  k: Record<CropId, Float32Array>; // spoilage rate per hour
  freeHours: Float32Array;
}

export function computeConditions(g: Graph, env: EnvState, hourOfDay: number): Conditions {
  const m = g.m;
  const speed = new Float32Array(m), hours = new Float32Array(m), tempC = new Float32Array(m);
  const rh = new Float32Array(m), stress = new Float32Array(m), flooded = new Uint8Array(m), freeHours = new Float32Array(m);
  const peak = isPeak(hourOfDay) ? 1 + PEAK_EXTRA : 1;
  const sun = hourOfDay % 24 >= 9 && hourOfDay % 24 < 17 ? 4 * (1 - env.rain) : 1;
  const closed = new Set(env.closed);
  const baseTemp = env.ambientC + sun - 3 * env.rain;
  const baseRh = Math.min(100, env.rh + 25 * env.rain);
  const baseMult = (1 - 0.4 * env.rain) / (env.traffic * peak);
  const baseIdle = 1.5 * (env.traffic * peak - 1);

  for (let e = 0; e < m; e++) {
    const free = CLASS_KMH[g.classes[g.cls[e]]] ?? 25;
    let mult = baseMult, t = baseTemp + baseIdle, h = baseRh, flood = 0;
    for (const c of env.cells) {
      const d = kmBetween(c.lon, c.lat, g.midLon[e], g.midLat[e]);
      if (d >= c.radiusKm) continue;
      const w = 1 - (d / c.radiusKm) ** 2;
      if (c.kind === "heat") { t += 9 * w; h -= 10 * w; }
      else if (c.kind === "storm") {
        mult *= 1 - 0.6 * w; h = h + (100 - h) * w; t -= 3 * w;
        if (d < 0.45 * c.radiusKm) flood = 1;
      } else { mult *= 1 - 0.8 * w; t += 5 * w; }
    }
    let v = free * mult;
    if (flood) v = FLOOD_KMH;
    if (closed.has(e)) v = CLOSED_KMH;
    speed[e] = v;
    hours[e] = g.lenKm[e] / v;
    freeHours[e] = g.lenKm[e] / free;
    tempC[e] = t;
    rh[e] = Math.max(5, Math.min(100, h));
    flooded[e] = flood;
    stress[e] = closed.has(e) ? 1 : Math.min(1, Math.max(1 - v / free, (t - 32) / 18, flood));
  }

  const ea = eaFromQ10(env.q10);
  const k = {} as Record<CropId, Float32Array>;
  for (const id of Object.keys(CROPS) as CropId[]) {
    const arr = new Float32Array(m);
    for (let e = 0; e < m; e++) arr[e] = rate(CROPS[id], tempC[e], rh[e], ea);
    k[id] = arr;
  }
  return { speed, hours, tempC, rh, stress, flooded, k, freeHours };
}

/** Spoilage rate in a refrigerated truck held at the crop's set point (for the reefer what-if). */
export function reeferRate(crop: CropId, q10: number): number {
  const c = CROPS[crop];
  return rate(c, c.reeferSetC, c.rhOpt, eaFromQ10(q10));
}
