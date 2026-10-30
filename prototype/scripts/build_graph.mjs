// One-off: convert the Nagpur Division road GeoJSON into a compact graph for the browser.
// Input:  ../data/processed/geo/edges_simplified.geojson (OSM, ODbL)
// Output: public/graph.json  { nodes:[lon,lat,...], edges:[u,v,lenM,cls,...], geoms:[[lon,lat,...],...], classes:[...] }
// Only the largest connected component is kept so every snapped point is reachable.
import { readFileSync, writeFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const here = dirname(fileURLToPath(import.meta.url));
const src = join(here, "..", "..", "data", "processed", "geo", "edges_simplified.geojson");
const out = join(here, "..", "public", "graph.json");

const CLASSES = ["motorway", "motorway_link", "trunk", "trunk_link", "primary", "primary_link",
  "secondary", "secondary_link", "tertiary", "tertiary_link"];

const fc = JSON.parse(readFileSync(src, "utf8"));
const R = 6371000;
const hav = (a, b) => {
  const toR = Math.PI / 180;
  const dLat = (b[1] - a[1]) * toR, dLon = (b[0] - a[0]) * toR;
  const s = Math.sin(dLat / 2) ** 2 + Math.cos(a[1] * toR) * Math.cos(b[1] * toR) * Math.sin(dLon / 2) ** 2;
  return 2 * R * Math.asin(Math.sqrt(s));
};

const idIndex = new Map();
const nodeXY = [];
const nodeOf = (osmId, xy) => {
  let i = idIndex.get(osmId);
  if (i === undefined) { i = nodeXY.length; idIndex.set(osmId, i); nodeXY.push(xy); }
  return i;
};

const raw = [];
for (const f of fc.features) {
  const [u, v] = f.properties.edge_id.slice(1).split("_");
  const c = f.geometry.coordinates;
  const a = nodeOf(u, c[0]), b = nodeOf(v, c[c.length - 1]);
  if (a === b) continue;
  let len = 0;
  for (let i = 1; i < c.length; i++) len += hav(c[i - 1], c[i]);
  const cls = Math.max(0, CLASSES.indexOf(f.properties.hw));
  raw.push({ a, b, len, cls, c });
}

// Largest connected component (union-find).
const parent = nodeXY.map((_, i) => i);
const find = (x) => { while (parent[x] !== x) { parent[x] = parent[parent[x]]; x = parent[x]; } return x; };
for (const e of raw) parent[find(e.a)] = find(e.b);
const size = new Map();
for (let i = 0; i < nodeXY.length; i++) { const r = find(i); size.set(r, (size.get(r) || 0) + 1); }
const big = [...size.entries()].sort((x, y) => y[1] - x[1])[0][0];

const remap = new Map();
const nodes = [];
for (let i = 0; i < nodeXY.length; i++) {
  if (find(i) !== big) continue;
  remap.set(i, nodes.length / 2);
  nodes.push(+nodeXY[i][0].toFixed(5), +nodeXY[i][1].toFixed(5));
}
const edges = [], geoms = [];
for (const e of raw) {
  if (find(e.a) !== big) continue;
  edges.push(remap.get(e.a), remap.get(e.b), Math.round(e.len), e.cls);
  geoms.push(e.c.flatMap(([x, y]) => [+x.toFixed(5), +y.toFixed(5)]));
}

writeFileSync(out, JSON.stringify({
  attribution: "© OpenStreetMap contributors (ODbL)",
  classes: CLASSES, nodes, edges, geoms,
}));
console.log(`nodes ${nodes.length / 2}  edges ${edges.length / 4}  (dropped ${raw.length - edges.length / 4} off-component)`);
