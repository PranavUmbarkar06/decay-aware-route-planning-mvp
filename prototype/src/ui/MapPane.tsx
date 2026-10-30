import { useEffect, useRef, useState } from "react";
import maplibregl from "maplibre-gl";
import type { GeoJSONSource, Map as MLMap, MapLayerMouseEvent, MapMouseEvent, Marker } from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import { CROPS } from "../data/crops";
import { BUYERS, CONSIGNMENTS } from "../data/consignments";
import type { Cell, CellKind } from "../model/env";
import type { Sim } from "../model/sim";

export type Tool = "pan" | CellKind | "close" | "erase";

const CELL_COLOR: Record<CellKind, string> = { heat: "#ff6b3d", storm: "#3da5ff", jam: "#ffd23d" };
const EMPTY = { type: "FeatureCollection" as const, features: [] as GeoJSON.Feature[] };

function circle(c: Cell): GeoJSON.Feature {
  const pts: number[][] = [];
  const dLat = c.radiusKm / 111.32, dLon = c.radiusKm / (111.32 * Math.cos((c.lat * Math.PI) / 180));
  for (let i = 0; i <= 64; i++) {
    const a = (i / 64) * 2 * Math.PI;
    pts.push([c.lon + dLon * Math.cos(a), c.lat + dLat * Math.sin(a)]);
  }
  return { type: "Feature", properties: { id: c.id, kind: c.kind, color: CELL_COLOR[c.kind] }, geometry: { type: "Polygon", coordinates: [pts] } };
}

export function MapPane({ sim, tick, envTick, tool, cellRadius, selected, onSelect, onAddCell, onMoveCell, onEraseCell, onToggleRoad }: {
  sim: Sim; tick: number; envTick: number; tool: Tool; cellRadius: number; selected: string;
  onSelect: (id: string) => void;
  onAddCell: (kind: CellKind, lon: number, lat: number) => void;
  onMoveCell: (id: number, lon: number, lat: number) => void;
  onEraseCell: (id: number) => void;
  onToggleRoad: (edge: number) => void;
}) {
  const el = useRef<HTMLDivElement>(null);
  const map = useRef<MLMap | null>(null);
  const ready = useRef(false);
  const [loaded, setLoaded] = useState(false);
  const truckMarkers = useRef(new Map<string, Marker>());
  const buyerMarkers = useRef(new Map<string, Marker>());
  const toolRef = useRef(tool);
  const cbs = useRef({ onAddCell, onMoveCell, onEraseCell, onToggleRoad, onSelect, cellRadius });
  toolRef.current = tool;
  cbs.current = { onAddCell, onMoveCell, onEraseCell, onToggleRoad, onSelect, cellRadius };

  useEffect(() => {
    if (!el.current || map.current) return;
    const m = new maplibregl.Map({
      container: el.current,
      style: {
        version: 8,
        sources: {
          base: {
            type: "raster", tileSize: 256,
            tiles: ["https://services.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Dark_Gray_Base/MapServer/tile/{z}/{y}/{x}"],
            attribution: "Basemap © Esri · Roads © OpenStreetMap contributors (ODbL)", maxzoom: 16,
          },
        },
        layers: [{ id: "base", type: "raster", source: "base", paint: { "raster-opacity": 1 } }],
      },
      bounds: [[78.45, 20.15], [79.75, 21.5]],
      attributionControl: { compact: true },
    });
    m.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-right");
    map.current = m;
    if (import.meta.env.DEV) { (window as unknown as { __map: MLMap }).__map = m; }

    m.on("load", () => {
      m.resize();
      m.fitBounds([[78.45, 20.15], [79.75, 21.5]], { duration: 0, padding: 20 });
      const g = sim.g;
      const roads: GeoJSON.Feature[] = [];
      for (let e = 0; e < g.m; e++) {
        const c = g.geoms[e], coords: number[][] = [];
        for (let i = 0; i < c.length; i += 2) coords.push([c[i], c[i + 1]]);
        roads.push({ type: "Feature", id: e, properties: { e, major: g.cls[e] <= 5 ? 1 : 0 }, geometry: { type: "LineString", coordinates: coords } });
      }
      m.addSource("roads", { type: "geojson", data: { type: "FeatureCollection", features: roads } });
      m.addLayer({
        id: "roads", type: "line", source: "roads",
        paint: {
          "line-color": ["interpolate", ["linear"], ["coalesce", ["feature-state", "stress"], 0],
            0, "#5d7189", 0.25, "#58a06a", 0.5, "#e0a030", 0.8, "#ff4d4d", 1, "#ff2bd6"],
          "line-width": ["interpolate", ["linear"], ["zoom"], 8, ["case", ["==", ["get", "major"], 1], 1.4, 0.6], 12, ["case", ["==", ["get", "major"], 1], 3, 1.4]],
          "line-opacity": 0.75,
        },
      });
      m.addLayer({
        id: "roads-closed", type: "line", source: "roads",
        filter: ["==", ["get", "e"], -1],
        paint: { "line-color": "#ff2bd6", "line-width": 5, "line-dasharray": [1, 1] },
      });

      m.addSource("cells", { type: "geojson", data: EMPTY });
      m.addLayer({ id: "cells-fill", type: "fill", source: "cells", paint: { "fill-color": ["get", "color"], "fill-opacity": 0.18 } });
      m.addLayer({ id: "cells-line", type: "line", source: "cells", paint: { "line-color": ["get", "color"], "line-width": 2, "line-dasharray": [2, 1] } });

      m.addSource("ghost", { type: "geojson", data: EMPTY });
      m.addLayer({ id: "ghost", type: "line", source: "ghost", layout: { "line-join": "round", "line-cap": "round" },
        paint: { "line-color": ["get", "color"], "line-width": 2.5, "line-opacity": 0.55, "line-dasharray": [2, 2] } });
      m.addSource("fastest", { type: "geojson", data: EMPTY });
      m.addLayer({ id: "fastest", type: "line", source: "fastest", layout: { "line-join": "round", "line-cap": "round" },
        paint: { "line-color": "#ffffff", "line-width": 3, "line-opacity": 0.75, "line-dasharray": [0.5, 1.5] } });
      m.addSource("routes", { type: "geojson", data: EMPTY });
      m.addLayer({ id: "routes-glow", type: "line", source: "routes", layout: { "line-join": "round", "line-cap": "round" },
        paint: { "line-color": ["get", "color"], "line-width": 11, "line-opacity": 0.18, "line-blur": 4 } });
      m.addLayer({ id: "routes", type: "line", source: "routes", layout: { "line-join": "round", "line-cap": "round" },
        paint: { "line-color": ["get", "color"], "line-width": 4.5 } });

      // Origins
      for (const c of CONSIGNMENTS) {
        const d = document.createElement("div");
        d.className = "origin-pin";
        d.style.borderColor = CROPS[c.crop].color;
        d.title = `${c.origin.name} — origin of ${c.label}`;
        new maplibregl.Marker({ element: d }).setLngLat([c.origin.lon, c.origin.lat]).addTo(m);
      }
      // Buyers
      for (const b of Object.values(BUYERS)) {
        const d = document.createElement("div");
        d.className = `buyer-pin ${b.kind}`;
        d.innerHTML = `<span class="dot"></span><span class="lbl">${b.short}</span>`;
        buyerMarkers.current.set(b.id, new maplibregl.Marker({ element: d, anchor: "left", offset: [-6, 0] }).setLngLat([b.lon, b.lat]).addTo(m));
      }
      // Trucks
      for (const t of sim.trucks) {
        const d = document.createElement("div");
        d.className = `truck ${t.smart ? "smart" : "ghost"}`;
        d.style.setProperty("--c", CROPS[t.c.crop].color);
        d.innerHTML = t.smart ? `<span class="body">🚚</span><span class="tag">${t.c.id}</span>` : `<span class="body">🚚</span>`;
        d.title = t.smart ? `${t.c.label} (smart)` : `${t.c.label} (status quo)`;
        d.addEventListener("click", (ev) => { ev.stopPropagation(); cbs.current.onSelect(t.c.id); });
        truckMarkers.current.set(t.id, new maplibregl.Marker({ element: d }).setLngLat([t.lon, t.lat]).addTo(m));
      }

      // Interaction
      let drag: number | null = null;
      m.on("mousedown", "cells-fill", (ev: MapLayerMouseEvent) => {
        if (toolRef.current !== "pan") return;
        ev.preventDefault();
        drag = ev.features?.[0]?.properties?.id ?? null;
        m.getCanvas().style.cursor = "grabbing";
      });
      m.on("mousemove", (ev: MapMouseEvent) => { if (drag !== null) cbs.current.onMoveCell(drag, ev.lngLat.lng, ev.lngLat.lat); });
      m.on("mouseup", () => { if (drag !== null) { drag = null; m.getCanvas().style.cursor = ""; } });
      m.on("mouseenter", "cells-fill", () => { if (toolRef.current === "pan") m.getCanvas().style.cursor = "grab"; });
      m.on("mouseleave", "cells-fill", () => { if (drag === null) m.getCanvas().style.cursor = ""; });
      m.on("click", (ev: MapMouseEvent) => {
        const t = toolRef.current;
        if (t === "heat" || t === "storm" || t === "jam") cbs.current.onAddCell(t, ev.lngLat.lng, ev.lngLat.lat);
        else if (t === "erase") {
          const f = m.queryRenderedFeatures(ev.point, { layers: ["cells-fill"] })[0];
          if (f) cbs.current.onEraseCell(f.properties.id);
        } else if (t === "close") {
          const p = ev.point;
          const f = m.queryRenderedFeatures([[p.x - 6, p.y - 6], [p.x + 6, p.y + 6]], { layers: ["roads"] })[0];
          if (f) cbs.current.onToggleRoad(f.properties.e);
        }
      });
      ready.current = true;
      setLoaded(true);
    });
    return () => { m.remove(); map.current = null; ready.current = false; };
  }, [sim]);

  // Cursor per tool
  useEffect(() => {
    const m = map.current;
    if (m) m.getCanvas().style.cursor = tool === "pan" ? "" : "crosshair";
  }, [tool]);

  // Moving parts every frame tick; environment layers whenever the conditions object changes.
  const appliedCond = useRef<unknown>(null);
  useEffect(() => {
    const m = map.current;
    if (!m || !ready.current) return;
    if (appliedCond.current !== sim.cond) {
      appliedCond.current = sim.cond;
      const stress = sim.cond.stress;
      for (let e = 0; e < sim.g.m; e++) m.setFeatureState({ source: "roads", id: e }, { stress: stress[e] });
      (m.getSource("cells") as GeoJSONSource).setData({ type: "FeatureCollection", features: sim.env.cells.map(circle) });
      m.setFilter("roads-closed", ["in", ["get", "e"], ["literal", sim.env.closed]]);
    }
    const routes: GeoJSON.Feature[] = [], ghosts: GeoJSON.Feature[] = [];
    for (const t of sim.trucks) {
      truckMarkers.current.get(t.id)?.setLngLat([t.lon, t.lat]);
      const el = truckMarkers.current.get(t.id)?.getElement();
      if (el) { el.classList.toggle("selected", t.c.id === selected); el.classList.toggle("done", !!t.done); }
      if (t.done) continue;
      const coords = sim.remainingCoords(t);
      if (coords.length < 2) continue;
      const f: GeoJSON.Feature = { type: "Feature", properties: { color: CROPS[t.c.crop].color }, geometry: { type: "LineString", coordinates: coords } };
      (t.smart ? routes : ghosts).push(f);
    }
    (m.getSource("routes") as GeoJSONSource).setData({ type: "FeatureCollection", features: routes });
    (m.getSource("ghost") as GeoJSONSource).setData({ type: "FeatureCollection", features: ghosts });

    const sel = sim.trucks.find((t) => t.smart && t.c.id === selected);
    const fast: GeoJSON.Feature[] = [];
    if (sel && !sel.done && sel.fastest) {
      const coords = sim.remainingCoords(sel, sel.fastest.steps, 0);
      if (coords.length > 1) fast.push({ type: "Feature", properties: {}, geometry: { type: "LineString", coordinates: coords } });
    }
    (m.getSource("fastest") as GeoJSONSource).setData({ type: "FeatureCollection", features: fast });

    // Highlight the selected consignment's buyers with prices.
    const c = CONSIGNMENTS.find((x) => x.id === selected);
    for (const [id, mk] of buyerMarkers.current) {
      const offer = c?.offers.find((o) => o.buyer === id);
      const lbl = mk.getElement().querySelector(".lbl")!;
      const isDest = sel?.buyer === id;
      mk.getElement().classList.toggle("muted", !offer);
      mk.getElement().classList.toggle("dest", isDest);
      lbl.textContent = offer ? `${BUYERS[id].short} ₹${offer.priceKg.toFixed(0)}/kg` : BUYERS[id].short;
    }
  }, [tick, envTick, selected, sim, loaded]);

  return <div ref={el} className="map" />;
}
