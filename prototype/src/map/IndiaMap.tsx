// India map with zoom-dependent level of detail (plan v2 §8b).
// Background roads come from a render-only PMTiles file: national highways from z4, state highways from z6,
// primary/secondary from z8, links from z11. Routing never depends on what is drawn here.
// Route, disruption and truck overlays are GeoJSON sources without zoom limits, so they are always visible.
// Everything is updated imperatively from the store, so zooming never re-renders React.
import { useEffect, useRef } from "react";
import maplibregl, { type GeoJSONSource, type Map as MLMap } from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import { Protocol } from "pmtiles";
import { api } from "../api";
import { useStore } from "../store";
import type { CandidateRoute } from "../types";

let protocolAdded = false;
const C = {
  road0: "#8e9590", road1: "#a4aaa5", road2: "#bcc1bc", poor: "#e3a21a",
  original: "#2f6feb", optimised: "#1e9e5a", alt: "#8f948d", congested: "#d93a30", blocked: "#8a1c14",
};
const FC = (features: GeoJSON.Feature[] = []): GeoJSON.FeatureCollection => ({ type: "FeatureCollection", features });
const line = (coords: number[][], props: Record<string, unknown> = {}): GeoJSON.Feature =>
  ({ type: "Feature", properties: props, geometry: { type: "LineString", coordinates: coords } });
const point = (c: number[], props: Record<string, unknown> = {}): GeoJSON.Feature =>
  ({ type: "Feature", properties: props, geometry: { type: "Point", coordinates: c } });

export function IndiaMap({ interactive = true }: { interactive?: boolean }) {
  const el = useRef<HTMLDivElement>(null);
  const mapRef = useRef<MLMap | null>(null);

  useEffect(() => {
    if (!el.current) return;
    if (!protocolAdded) {
      maplibregl.addProtocol("pmtiles", new Protocol().tile);
      protocolAdded = true;
    }
    const m = new maplibregl.Map({
      container: el.current,
      style: {
        version: 8,
        sources: {
          base: { type: "raster", tileSize: 256, maxzoom: 16,
            tiles: ["https://services.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Light_Gray_Base/MapServer/tile/{z}/{y}/{x}"],
            attribution: "Basemap © Esri" },
          roads: { type: "vector", url: `pmtiles://${location.origin}/tiles/roads.pmtiles`,
            attribution: "Roads © OpenStreetMap contributors (ODbL)" },
        },
        layers: [
          { id: "base", type: "raster", source: "base", paint: { "raster-saturation": -0.4, "raster-opacity": 0.9 } },
          { id: "roads-2", type: "line", source: "roads", "source-layer": "roads", minzoom: 8,
            filter: ["all", [">=", ["get", "rank"], 2], ["!=", ["get", "link"], 1]],
            paint: { "line-color": C.road2, "line-width": ["interpolate", ["linear"], ["zoom"], 8, 0.5, 12, 1.6] } },
          { id: "roads-links", type: "line", source: "roads", "source-layer": "roads", minzoom: 11,
            filter: ["==", ["get", "link"], 1], paint: { "line-color": C.road2, "line-width": 1 } },
          { id: "roads-1", type: "line", source: "roads", "source-layer": "roads", minzoom: 6,
            filter: ["==", ["get", "rank"], 1],
            paint: { "line-color": C.road1, "line-width": ["interpolate", ["linear"], ["zoom"], 6, 0.6, 12, 2.2] } },
          { id: "roads-0", type: "line", source: "roads", "source-layer": "roads", minzoom: 4,
            filter: ["==", ["get", "rank"], 0],
            paint: { "line-color": C.road0, "line-width": ["interpolate", ["linear"], ["zoom"], 4, 0.6, 7, 1.2, 12, 3] } },
          { id: "roads-poor", type: "line", source: "roads", "source-layer": "roads", minzoom: 8,
            filter: [">=", ["coalesce", ["get", "rough"], 0], 7],
            paint: { "line-color": C.poor, "line-width": ["interpolate", ["linear"], ["zoom"], 8, 1, 12, 3], "line-opacity": 0.8 } },
        ],
      },
      center: [79, 22.5], zoom: 4.3, minZoom: 3.5, maxZoom: 16,
      attributionControl: { compact: true },
    });
    m.addControl(new maplibregl.NavigationControl({ showCompass: false }), "bottom-right");
    m.addControl(new maplibregl.ScaleControl({ unit: "metric" }), "bottom-left");
    mapRef.current = m;
    if (import.meta.env.DEV) (window as unknown as { __map: MLMap }).__map = m;

    m.on("load", () => {
      const add = (id: string) => m.addSource(id, { type: "geojson", data: FC() });
      ["detail", "alts", "original", "optimised", "marks", "disruptions", "active", "trail", "points", "pnr", "truck"].forEach(add);
      m.addSource("markets", { type: "geojson", data: FC(), cluster: true, clusterRadius: 40, clusterMaxZoom: 8 });
      m.addLayer({ id: "markets-cluster", type: "circle", source: "markets", filter: ["has", "point_count"],
        layout: { visibility: "none" },
        paint: { "circle-color": "#d6dbd2", "circle-stroke-color": "#fff", "circle-stroke-width": 1.5,
          "circle-radius": ["step", ["get", "point_count"], 10, 20, 14, 80, 18] } });
      m.addLayer({ id: "markets-pt", type: "circle", source: "markets", filter: ["!", ["has", "point_count"]],
        layout: { visibility: "none" },
        paint: { "circle-color": ["case", ["==", ["get", "approx"], 1], "#ffffff", "#5a6b5f"], "circle-radius": 3.5,
          "circle-stroke-color": "#5a6b5f", "circle-stroke-width": 1 } });
      m.addLayer({ id: "detail", type: "line", source: "detail", minzoom: 11, paint: { "line-color": C.road2, "line-width": 1.2 } });
      m.addLayer({ id: "alts", type: "line", source: "alts", layout: { "line-join": "round", "line-cap": "round" },
        paint: { "line-color": C.alt, "line-width": ["interpolate", ["linear"], ["zoom"], 4, 2, 10, 4], "line-dasharray": [2, 1.5] } });
      m.addLayer({ id: "original", type: "line", source: "original", layout: { "line-join": "round", "line-cap": "round" },
        paint: { "line-color": C.original, "line-width": ["interpolate", ["linear"], ["zoom"], 4, 2.5, 10, 5], "line-opacity": 0.9 } });
      m.addLayer({ id: "optimised-casing", type: "line", source: "optimised", layout: { "line-join": "round", "line-cap": "round" },
        paint: { "line-color": "#ffffff", "line-width": ["interpolate", ["linear"], ["zoom"], 4, 5, 10, 9] } });
      m.addLayer({ id: "optimised", type: "line", source: "optimised", layout: { "line-join": "round", "line-cap": "round" },
        paint: { "line-color": C.optimised, "line-width": ["interpolate", ["linear"], ["zoom"], 4, 3, 10, 6] } });
      m.addLayer({ id: "marks", type: "line", source: "marks", layout: { "line-cap": "round" },
        paint: { "line-color": ["match", ["get", "kind"], "poor", C.poor, "congested", C.congested, C.blocked],
          "line-width": ["interpolate", ["linear"], ["zoom"], 4, 4, 10, 8] } });
      m.addLayer({ id: "disruptions", type: "line", source: "disruptions", layout: { "line-cap": "round" },
        paint: { "line-color": ["match", ["get", "kind"], "poor_road", C.poor, "construction", C.poor,
          "closure", C.blocked, "vehicle_restriction", C.blocked, C.congested],
          "line-width": ["interpolate", ["linear"], ["zoom"], 4, 5, 10, 9], "line-opacity": ["case", ["==", ["get", "editing"], 1], 1, 0.85] } });
      m.addLayer({ id: "active-casing", type: "line", source: "active", layout: { "line-join": "round", "line-cap": "round" },
        paint: { "line-color": "#ffffff", "line-width": ["interpolate", ["linear"], ["zoom"], 4, 6, 10, 10] } });
      m.addLayer({ id: "active", type: "line", source: "active", layout: { "line-join": "round", "line-cap": "round" },
        paint: { "line-color": C.optimised, "line-width": ["interpolate", ["linear"], ["zoom"], 4, 3.5, 10, 6.5] } });
      m.addLayer({ id: "trail", type: "line", source: "trail", paint: { "line-color": "#23262b", "line-width": 3, "line-opacity": 0.55 } });
      m.addLayer({ id: "points", type: "circle", source: "points",
        paint: { "circle-radius": 7, "circle-color": ["match", ["get", "kind"], "origin", "#23262b", "#ffffff"],
          "circle-stroke-color": "#23262b", "circle-stroke-width": 2.5 } });
      m.addLayer({ id: "pnr", type: "circle", source: "pnr",
        paint: { "circle-radius": ["match", ["get", "kind"], "pnr", 8, 5],
          "circle-color": ["match", ["get", "state"], "open", C.optimised, "closing", C.poor, "#9aa09b"],
          "circle-stroke-color": "#fff", "circle-stroke-width": 2 } });
      m.addLayer({ id: "truck", type: "circle", source: "truck",
        paint: { "circle-radius": 9, "circle-color": "#17734a", "circle-stroke-color": "#fff", "circle-stroke-width": 3 } });
      sync();
    });

    // Click a road → disruption (rendered feature first; otherwise the server snaps to ANY routing edge).
    m.on("click", (ev) => {
      if (!interactive || !useStore.getState().pickRoad) return;
      void useStore.getState().addDisruptionAt(ev.lngLat.lng, ev.lngLat.lat);
    });

    // Detail roads near the selected route at z ≥ 11, debounced and cancellable.
    let detailTimer: ReturnType<typeof setTimeout> | null = null;
    let ctrl: AbortController | null = null;
    m.on("moveend", () => {
      if (detailTimer) clearTimeout(detailTimer);
      detailTimer = setTimeout(async () => {
        const src = m.getSource("detail") as GeoJSONSource | undefined;
        const plan = useStore.getState().plan;
        if (!src || m.getZoom() < 11 || !plan) return src?.setData(FC());
        ctrl?.abort();
        ctrl = new AbortController();
        const b = m.getBounds();
        const rec = plan.candidates.find((c) => c.id === plan.recommended_id);
        const near = rec ? rec.arcs.slice(0, 4000).join(",") : "";
        try {
          const r = await fetch(`/api/roads/viewport?west=${b.getWest()}&south=${b.getSouth()}&east=${b.getEast()}&north=${b.getNorth()}${near ? `&near=${near}` : ""}`, { signal: ctrl.signal });
          if (r.ok) src.setData(await r.json());
        } catch { /* superseded */ }
      }, 250);
    });

    let lastFocus: unknown = null;
    let marketsLoaded = false;
    const seen = new Map<string, unknown[]>();
    // true when any of `deps` changed (by identity) since the last call with this key
    const changed = (key: string, deps: unknown[]) => {
      const prev = seen.get(key);
      if (prev && prev.length === deps.length && prev.every((v, i) => v === deps[i])) return false;
      seen.set(key, deps);
      return true;
    };
    function sync() {
      const s = useStore.getState();
      if (!m.getSource("original")) return;
      const plan = s.plan;
      const byId = (id: string | null) => plan?.candidates.find((c) => c.id === id) ?? null;
      const orig = byId(plan?.original_id ?? null);
      const rec = byId(plan?.recommended_id ?? null);
      const alts = (plan?.candidates ?? []).filter((c) => c !== orig && c !== rec && c.feasible);
      const setSrc = (id: string, f: GeoJSON.Feature[]) => (m.getSource(id) as GeoJSONSource).setData(FC(f));
      const routeFeat = (c: CandidateRoute | null) => (c && c.coords.length > 1 ? [line(c.coords, { id: c.id })] : []);
      const sameRoute = rec && orig && rec.id === orig.id;
      if (changed("routes", [plan, s.layers])) {
        setSrc("original", s.layers.original ? routeFeat(orig) : []);
        setSrc("optimised", s.layers.optimised && !sameRoute ? routeFeat(rec) : []);
        setSrc("alts", s.layers.alternatives ? alts.flatMap(routeFeat) : []);
        const marks = [...(orig?.marks ?? []), ...(rec?.marks ?? [])];
        setSrc("marks", marks.map((x) => line(x.coords, { kind: x.kind })));
      }
      if (changed("dis", [s.disruptions, s.editing])) {
        setSrc("disruptions", s.disruptions.flatMap((d) => d.coords.map((c) => line(c, { kind: d.type, editing: d.id === s.editing ? 1 : 0 }))));
      }
      const pts: GeoJSON.Feature[] = [];
      if (plan) {
        pts.push(point([plan.origin.lon, plan.origin.lat], { kind: "origin" }));
        pts.push(point([plan.destination.lon, plan.destination.lat], { kind: "destination" }));
      } else {
        if (s.origin) pts.push(point([s.origin.lon, s.origin.lat], { kind: "origin" }));
        if (s.destination) pts.push(point([s.destination.lon, s.destination.lat], { kind: "destination" }));
      }
      if (changed("pts", [plan, s.origin, s.destination])) setSrc("points", pts);
      const r = s.replay;
      if (changed("truck", [r.truck])) setSrc("truck", r.truck ? [point(r.truck)] : []);
      if (changed("trail", [r.trail.length, r.coords])) setSrc("trail", r.trail.length > 1 ? [line(r.trail)] : []);
      if (changed("active", [r.coords, r.started])) {
        // During a trip the route actually being driven is drawn on top; planned routes fade back.
        setSrc("active", r.started && r.coords.length > 1 ? [line(r.coords)] : []);
        for (const id of ["original", "optimised", "optimised-casing", "alts"]) m.setPaintProperty(id, "line-opacity", r.started ? 0.35 : 0.9);
      }
      // Diversion options + point of no return for the open alert
      const al = s.queue?.alerts.find((a) => a.id === s.openAlert) ?? s.queue?.alerts[0];
      const pnrFeats: GeoJSON.Feature[] = [];
      if (al && r.coords.length && al.state !== "EXECUTED") {
        for (const op of al.payload.options ?? []) {
          const nodeIdx = op.route_index - r.history.length;
          const ci = r.arcIdx[nodeIdx];
          if (ci === undefined) continue;
          const slack = (op.deadline_h - r.nowH) * 60;
          const state = slack < 0 ? "expired" : slack < 15 ? "closing" : "open";
          pnrFeats.push(point(r.coords[ci], { kind: al.payload.pnr && op.node === al.payload.pnr.node ? "pnr" : "option", state }));
        }
      }
      if (changed("pnr", [s.queue, s.openAlert, r.coords, Math.floor(r.nowH * 12)])) setSrc("pnr", pnrFeats);
      const vis = s.layers.markets ? "visible" : "none";
      m.setLayoutProperty("markets-cluster", "visibility", vis);
      m.setLayoutProperty("markets-pt", "visibility", vis);
      if (s.layers.markets && !marketsLoaded) {
        marketsLoaded = true;
        void api.marketsSummary(s.shipment.crop).then((j) => (m.getSource("markets") as GeoJSONSource).setData(
          FC(j.markets.map((x: any) => point([x.lon, x.lat], { name: x.market, approx: x.geocode_method === "district_centroid" ? 1 : 0 })))));
      }
      if (s.focus && s.focus !== lastFocus) {
        lastFocus = s.focus;
        m.fitBounds([[s.focus[0], s.focus[1]], [s.focus[2], s.focus[3]]], { padding: { top: 70, bottom: 50, left: 50, right: 50 }, duration: 600, maxZoom: 11 });
      }
      m.getCanvas().style.cursor = s.pickRoad ? "crosshair" : "";
    }
    const unsub = useStore.subscribe(sync);
    return () => { unsub(); m.remove(); mapRef.current = null; };
  }, [interactive]);

  return <div ref={el} className="map" />;
}
