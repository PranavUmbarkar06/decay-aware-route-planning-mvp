// Road graph loaded from public/graph.json (built by scripts/build_graph.mjs). Edges are treated as two-way.
export interface Graph {
  n: number;
  m: number;
  lon: Float64Array;
  lat: Float64Array;
  eu: Int32Array;
  ev: Int32Array;
  lenKm: Float32Array;
  cls: Uint8Array;
  classes: string[];
  geoms: number[][];          // flat [lon,lat,...] from eu to ev
  midLon: Float32Array;
  midLat: Float32Array;
  adjStart: Int32Array;       // CSR: half-edges of node i are adjStart[i]..adjStart[i+1]
  adjEdge: Int32Array;
  adjTo: Int32Array;
  attribution: string;
}

interface RawGraph { nodes: number[]; edges: number[]; geoms: number[][]; classes: string[]; attribution: string }

export function buildGraph(raw: RawGraph): Graph {
  const n = raw.nodes.length / 2, m = raw.edges.length / 4;
  const lon = new Float64Array(n), lat = new Float64Array(n);
  for (let i = 0; i < n; i++) { lon[i] = raw.nodes[2 * i]; lat[i] = raw.nodes[2 * i + 1]; }
  const eu = new Int32Array(m), ev = new Int32Array(m), lenKm = new Float32Array(m), cls = new Uint8Array(m);
  const midLon = new Float32Array(m), midLat = new Float32Array(m);
  const deg = new Int32Array(n + 1);
  for (let e = 0; e < m; e++) {
    eu[e] = raw.edges[4 * e]; ev[e] = raw.edges[4 * e + 1];
    lenKm[e] = Math.max(0.005, raw.edges[4 * e + 2] / 1000); cls[e] = raw.edges[4 * e + 3];
    const g = raw.geoms[e], k = Math.floor(g.length / 4) * 2;
    midLon[e] = g[k]; midLat[e] = g[k + 1];
    deg[eu[e] + 1]++; deg[ev[e] + 1]++;
  }
  for (let i = 0; i < n; i++) deg[i + 1] += deg[i];
  const adjStart = deg.slice();
  const fill = deg.slice(0, n);
  const adjEdge = new Int32Array(2 * m), adjTo = new Int32Array(2 * m);
  for (let e = 0; e < m; e++) {
    adjEdge[fill[eu[e]]] = e; adjTo[fill[eu[e]]++] = ev[e];
    adjEdge[fill[ev[e]]] = e; adjTo[fill[ev[e]]++] = eu[e];
  }
  return { n, m, lon, lat, eu, ev, lenKm, cls, classes: raw.classes, geoms: raw.geoms, midLon, midLat,
    adjStart, adjEdge, adjTo, attribution: raw.attribution };
}

export async function loadGraph(url = "graph.json"): Promise<Graph> {
  const res = await fetch(url);
  return buildGraph(await res.json());
}

export function kmBetween(lon1: number, lat1: number, lon2: number, lat2: number): number {
  const r = Math.PI / 180;
  const x = (lon2 - lon1) * r * Math.cos(((lat1 + lat2) / 2) * r);
  const y = (lat2 - lat1) * r;
  return 6371 * Math.hypot(x, y);
}

export function nearestNode(g: Graph, lon: number, lat: number): number {
  let best = 0, bd = Infinity;
  for (let i = 0; i < g.n; i++) {
    const d = kmBetween(lon, lat, g.lon[i], g.lat[i]);
    if (d < bd) { bd = d; best = i; }
  }
  return best;
}
