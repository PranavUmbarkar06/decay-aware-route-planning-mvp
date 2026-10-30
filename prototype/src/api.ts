import type { ConditionsIn, Disruption, Place, Plan, Shipment } from "./types";

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const r = await fetch(path, { headers: { "Content-Type": "application/json" }, ...init });
  if (!r.ok) {
    let msg = `${r.status} ${r.statusText}`;
    try {
      const j = await r.json();
      msg = typeof j.detail === "string" ? j.detail : JSON.stringify(j.detail);
    } catch { /* keep status text */ }
    throw new Error(msg);
  }
  return r.json() as Promise<T>;
}

export const post = <T>(path: string, body: unknown) => req<T>(path, { method: "POST", body: JSON.stringify(body) });
export const get = <T>(path: string) => req<T>(path);

export function shipmentBody(s: Shipment) {
  const { dispatch_date: _d, ...rest } = s;
  return rest;
}

export function disruptionBody(d: Disruption) {
  const { label: _l, coords: _c, ...rest } = d;
  return rest;
}

export function placeBody(p: Place) {
  return p.market_id ? { market_id: p.market_id } : { lon: p.lon, lat: p.lat };
}

export const api = {
  presets: () => get<Record<string, { origin: Place; destination: Place; research: { origin: Place; destination: Place }[] }>>("/api/presets"),
  crops: () => get<any>("/api/crops"),
  meta: () => get<any>("/api/meta"),
  states: () => get<{ state: string; markets: number }[]>("/api/states"),
  districts: (state: string) => get<{ district: string; markets: number }[]>(`/api/districts?state=${encodeURIComponent(state)}`),
  places: (q: string, state?: string, district?: string, crop?: string) => {
    const p = new URLSearchParams({ q });
    if (state) p.set("state", state);
    if (district) p.set("district", district);
    if (crop) p.set("crop", crop);
    return get<Place[]>(`/api/places?${p}`);
  },
  optimise: (s: Shipment, o: Place, d: Place, c: ConditionsIn, dis: Disruption[], originalArcs: number[] | null) =>
    post<Plan>("/api/optimise", {
      shipment: shipmentBody(s), origin: placeBody(o), destination: placeBody(d), conditions: c,
      disruptions: dis.map(disruptionBody), original_arcs: originalArcs,
    }),
  evaluate: (s: Shipment, c: ConditionsIn, dis: Disruption[], cands: { id: string; label: string; arcs: number[] }[]) =>
    post<Omit<Plan, "origin" | "destination">>("/api/evaluate", {
      shipment: shipmentBody(s), conditions: c, disruptions: dis.map(disruptionBody), candidates: cands,
    }),
  edgeAt: (lon: number, lat: number) => get<any>(`/api/edge-at?lon=${lon}&lat=${lat}`),
  timeline: (s: Shipment, arcs: number[], destNode: number, nowH: number, c: ConditionsIn) =>
    post<{ coords: number[][]; arc_coord_idx: number[]; arc_t: number[]; edges: number[] }>(
      `/api/route/timeline?now_h=${nowH}&ambient_c=${c.ambient_c}&traffic=${c.traffic}`,
      { shipment: shipmentBody(s), route_arcs: arcs, pos: 0, progress: 0, destination_node: destNode }),
  sensitivity: () => get<any>("/api/sensitivity"),
  marketsSummary: (crop: string, state?: string) =>
    get<any>(`/api/markets/summary?crop=${crop}${state ? `&state=${encodeURIComponent(state)}` : ""}`),
  arrivals: (marketId: string, crop: string) => get<any>(`/api/markets/${marketId}/arrivals?crop=${crop}`),
  batch: (body: unknown) => post<any>("/api/batch", body),
  outcomes: () => get<any[]>("/api/outcomes"),
  addOutcome: (p: unknown) => post<any>("/api/outcomes", p),
  decisionLog: () => get<any[]>("/api/decision-log"),
};
