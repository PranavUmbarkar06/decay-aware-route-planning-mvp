import { useEffect, useRef, useState } from "react";
import type { Map as MLMap, GeoJSONSource } from "maplibre-gl";
import { useSession } from "../lib/session";

export type MapPoint = { id: string; lat: number; lon: number; label: string; kind: string; provenance?: string; review?: boolean };
export type MapLine = { id: string; coords: [number, number][]; color: "series-1" | "series-2" | "brand" | "muted"; width?: number; dashed?: boolean };
export type MapDot = { lat: number; lon: number; color: "series-1" | "series-2"; label?: string };

const KIND_COLOR: Record<string, string> = {
  ReceivingMarket: "#0f8b8d", AssemblyMandi: "#2a78d6", TransitStorageNode: "#6250d6", NGOSink: "#e87ba4",
  ProcessingSink: "#eda100", FarmGatherPoint: "#008300",
};

function cssVar(name: string): string {
  return getComputedStyle(document.documentElement).getPropertyValue(`--${name}`).trim() || "#2a78d6";
}

function webglOk(): boolean {
  try {
    const c = document.createElement("canvas");
    return !!(c.getContext("webgl2") || c.getContext("webgl"));
  } catch {
    return false;
  }
}

export function MapView({ points = [], lines = [], dots = [], height = 360, fitTo, onPick, showRoads = false }: {
  points?: MapPoint[]; lines?: MapLine[]; dots?: MapDot[]; height?: number; fitTo?: [number, number][];
  onPick?: (id: string) => void; showRoads?: boolean;
}) {
  const el = useRef<HTMLDivElement>(null);
  const map = useRef<MLMap | null>(null);
  const [ready, setReady] = useState(false);
  const [ok] = useState(() => typeof window !== "undefined" && webglOk());
  const { meta } = useSession();

  useEffect(() => {
    if (!ok || !el.current || map.current || !meta) return;
    let cancelled = false;
    void import("maplibre-gl").then((mod) => {
      const maplibregl: typeof import("maplibre-gl") = (mod as any).default ?? mod;
      // MapLibre 6 runs its tile parsing in a separate worker module; point it at the bundled copy.
      (maplibregl as any).setWorkerUrl?.(new URL("maplibre-gl/dist/maplibre-gl-worker.mjs", import.meta.url).toString());
      if (cancelled || !el.current) return;
      const m = new maplibregl.Map({
        container: el.current,
        style: {
          version: 8,
          sources: { base: { type: "raster", tiles: [meta.map.tile_url], tileSize: 256, attribution: meta.map.attribution } },
          layers: [{ id: "base", type: "raster", source: "base" }],
        },
        center: [79.09, 21.15],
        zoom: 7,
        attributionControl: { compact: false },
      });
      m.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-right");
      m.on("load", () => {
        if (showRoads) {
          m.addSource("roads", { type: "geojson", data: "/geo/edges_simplified.geojson" });
          m.addLayer({ id: "roads", type: "line", source: "roads", paint: { "line-color": "#8a98a6", "line-opacity": 0.35, "line-width": 0.8 } });
        }
        m.addSource("lines", { type: "geojson", data: { type: "FeatureCollection", features: [] } });
        m.addLayer({ id: "lines", type: "line", source: "lines", layout: { "line-cap": "round", "line-join": "round" },
          paint: { "line-color": ["get", "color"], "line-width": ["get", "width"], "line-dasharray": [1, 0] } });
        m.addSource("points", { type: "geojson", data: { type: "FeatureCollection", features: [] }, cluster: true, clusterRadius: 36, clusterMaxZoom: 9 });
        m.addLayer({ id: "clusters", type: "circle", source: "points", filter: ["has", "point_count"],
          paint: { "circle-color": "#5e6e7e", "circle-radius": 16, "circle-stroke-color": "#fff", "circle-stroke-width": 2 } });
        m.addLayer({ id: "cluster-count", type: "symbol", source: "points", filter: ["has", "point_count"],
          layout: { "text-field": ["get", "point_count_abbreviated"], "text-size": 12 }, paint: { "text-color": "#fff" } });
        m.addLayer({ id: "pts", type: "circle", source: "points", filter: ["!", ["has", "point_count"]],
          paint: { "circle-color": ["get", "color"], "circle-radius": 7, "circle-stroke-color": ["get", "ring"], "circle-stroke-width": 2.5 } });
        m.addSource("dots", { type: "geojson", data: { type: "FeatureCollection", features: [] } });
        m.addLayer({ id: "dots", type: "circle", source: "dots",
          paint: { "circle-color": ["get", "color"], "circle-radius": 4.5, "circle-stroke-color": "#fff", "circle-stroke-width": 1.5 } });
        m.on("click", "pts", (e: any) => {
          const f = e.features?.[0];
          if (!f) return;
          const p = f.properties as any;
          new maplibregl.Popup({ closeButton: true }).setLngLat(e.lngLat)
            .setHTML(`<strong>${escapeHtml(p.label)}</strong><br/>${escapeHtml(p.kind)}${p.provenance ? ` · ${escapeHtml(p.provenance)}` : ""}${p.review === "true" || p.review === true ? "<br/><em>Location needs review: excluded from routing</em>" : ""}`)
            .addTo(m);
          onPick?.(p.id);
        });
        m.on("click", "clusters", (e: any) => m.easeTo({ center: e.lngLat, zoom: m.getZoom() + 2 }));
        setReady(true);
      });
      map.current = m;
    });
    return () => {
      cancelled = true;
      map.current?.remove();
      map.current = null;
    };
  }, [ok, meta, onPick, showRoads]);

  useEffect(() => {
    const m = map.current;
    if (!ready || !m) return;
    (m.getSource("points") as GeoJSONSource).setData({ type: "FeatureCollection", features: points.map((p) => ({
      type: "Feature", geometry: { type: "Point", coordinates: [p.lon, p.lat] },
      properties: { ...p, color: KIND_COLOR[p.kind] ?? "#5e6e7e", ring: p.provenance === "SYNTHETIC_DEMO" ? "#d9a21b" : p.review ? "#b3261e" : "#ffffff" },
    })) });
    (m.getSource("lines") as GeoJSONSource).setData({ type: "FeatureCollection", features: lines.map((l) => ({
      type: "Feature", geometry: { type: "LineString", coordinates: l.coords.map(([lat, lon]) => [lon, lat]) },
      properties: { id: l.id, color: cssVar(l.color), width: l.width ?? 4 },
    })) });
    (m.getSource("dots") as GeoJSONSource).setData({ type: "FeatureCollection", features: dots.map((d) => ({
      type: "Feature", geometry: { type: "Point", coordinates: [d.lon, d.lat] }, properties: { color: cssVar(d.color) },
    })) });
  }, [ready, points, lines, dots]);

  useEffect(() => {
    const m = map.current;
    const pts = fitTo ?? [...points.map((p) => [p.lat, p.lon] as [number, number]), ...lines.flatMap((l) => l.coords)];
    if (!ready || !m || pts.length < 1) return;
    const lats = pts.map((p) => p[0]);
    const lons = pts.map((p) => p[1]);
    m.fitBounds([[Math.min(...lons), Math.min(...lats)], [Math.max(...lons), Math.max(...lats)]], { padding: 40, maxZoom: 12, duration: 0 });
    // fit only when the set of things changes size, not on every live tick
  }, [ready, fitTo, points.length, lines.length]); // eslint-disable-line react-hooks/exhaustive-deps

  if (!ok) {
    return (
      <div className="card flex items-center justify-center p-6 text-center text-sm text-muted" style={{ height }}>
        Map unavailable on this device (no WebGL). The list below shows the same places.
      </div>
    );
  }
  return (
    <div className="overflow-hidden rounded-xl border border-line" style={{ height }}>
      <div ref={el} className="h-full w-full" role="application" aria-label="Map" />
    </div>
  );
}

function escapeHtml(s: string): string {
  return String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c] as string));
}

export const MAP_LEGEND: [string, string][] = Object.entries(KIND_COLOR);
