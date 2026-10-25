"""Road network for the simulation, loaded from the auditable CSVs (edges.csv / nodes.csv) into scipy sparse
form for fast time-varying shortest paths.

Parallel edges between the same (u, v) are collapsed to the fastest one (free-flow), documented in the report.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache

import geopandas as gpd
import networkx as nx
import numpy as np
import pandas as pd
from scipy.sparse import csr_matrix
from scipy.sparse.csgraph import dijkstra

from app.core.config import ROOT, speeds

PROCESSED = ROOT / "data" / "processed"
CACHE = ROOT / "data" / "cache"
CLASS_ORDER = ["motorway", "trunk", "primary", "secondary", "tertiary", "other"]


def _class_of(hw: str) -> int:
    base = str(hw).split(";")[0].replace("_link", "")
    return CLASS_ORDER.index(base) if base in CLASS_ORDER else CLASS_ORDER.index("other")


@dataclass
class BusinessNode:
    node_id: str
    node_type: str
    name: str
    district: str | None
    gidx: int                 # graph node index
    access_s: float           # access leg time (one way)
    access_m: float
    provenance: str
    capacity_kg: float | None
    lat: float
    lon: float


@dataclass
class Network:
    n: int
    graph_ids: np.ndarray            # osm node id per index
    x: np.ndarray
    y: np.ndarray
    node_district: np.ndarray        # district index per graph node
    districts: list[str]
    eu: np.ndarray                   # deduped edges
    ev: np.ndarray
    ff_s: np.ndarray
    length_m: np.ndarray
    cls: np.ndarray
    edge_index: dict[tuple[int, int], int]
    business: dict[str, BusinessNode]
    notes: list[str] = field(default_factory=list)

    def csr(self, weights: np.ndarray) -> csr_matrix:
        return csr_matrix((weights, (self.eu, self.ev)), shape=(self.n, self.n))

    def sssp(self, weights: np.ndarray, source: int) -> tuple[np.ndarray, np.ndarray]:
        d, p = dijkstra(self.csr(weights), directed=True, indices=source, return_predecessors=True)
        return d, p

    @staticmethod
    def path_from(pred: np.ndarray, source: int, target: int) -> list[int]:
        if source == target:
            return [source]
        if pred[target] < 0:
            return []
        out = [target]
        while out[-1] != source:
            out.append(int(pred[out[-1]]))
        return out[::-1]

    def path_edges(self, nodes: list[int]) -> list[int]:
        return [self.edge_index[(a, b)] for a, b in zip(nodes[:-1], nodes[1:], strict=True)]

    def by_type(self, t: str) -> list[BusinessNode]:
        return [b for b in self.business.values() if b.node_type == t]


@lru_cache(maxsize=2)
def load_network(include_demo: bool = False) -> Network:
    notes: list[str] = []
    e = pd.read_csv(PROCESSED / "edges.csv", usecols=["u", "v", "free_flow_time_s", "length_m", "highway_class"])
    e = e.sort_values(["u", "v", "free_flow_time_s"]).drop_duplicates(["u", "v"], keep="first")
    ids = np.unique(np.concatenate([e["u"].to_numpy(), e["v"].to_numpy()]))
    pos = {int(g): i for i, g in enumerate(ids)}
    eu = np.array([pos[int(u)] for u in e["u"]], dtype=np.int32)
    ev = np.array([pos[int(v)] for v in e["v"]], dtype=np.int32)
    G = nx.read_graphml(CACHE / "graph.graphml") if (CACHE / "graph.graphml").exists() else None
    if G is not None:
        xs = np.array([float(G.nodes[str(g)]["x"]) for g in ids])
        ys = np.array([float(G.nodes[str(g)]["y"]) for g in ids])
    else:  # pragma: no cover - graphml missing: approximate coordinates from nodes are unavailable
        raise RuntimeError("data/cache/graph.graphml missing: run `python tasks.py graph`")
    dist = gpd.read_file(PROCESSED / "district_boundaries.geojson")[["district", "geometry"]].sort_values("district")
    districts = dist["district"].tolist()
    pts = gpd.GeoDataFrame({"i": np.arange(len(ids))}, geometry=gpd.points_from_xy(xs, ys), crs=4326)
    j = gpd.sjoin_nearest(pts.to_crs(32644), dist.to_crs(32644), how="left").drop_duplicates("i").sort_values("i")
    node_district = np.array([districts.index(d) for d in j["district"]], dtype=np.int16)
    acc = speeds().access_leg
    nodes = pd.read_csv(PROCESSED / "nodes.csv", dtype={"snapped_graph_node": str})
    ov_path = PROCESSED / "node_overrides.csv"
    overrides = pd.read_csv(ov_path).set_index("node_id")["decision"].to_dict() if ov_path.exists() else {}
    business: dict[str, BusinessNode] = {}
    excluded = {"needs_review": 0, "demo": 0, "rejected": 0}
    for r in nodes.itertuples(index=False):
        decision = overrides.get(r.node_id)
        if decision == "reject":
            excluded["rejected"] += 1
            continue
        if r.needs_review and decision not in ("accept", "move"):
            excluded["needs_review"] += 1
            continue
        if r.provenance == "SYNTHETIC_DEMO" and not include_demo:
            excluded["demo"] += 1
            continue
        g = int(float(r.snapped_graph_node))
        if g not in pos:
            continue
        business[r.node_id] = BusinessNode(r.node_id, r.node_type, r.name, r.district, pos[g],
                                           float(r.snap_distance_m) * acc.detour_factor / (acc.speed_kmh / 3.6),
                                           float(r.snap_distance_m) * acc.detour_factor, r.provenance,
                                           None if pd.isna(r.capacity_kg) else float(r.capacity_kg), float(r.lat), float(r.lon))
    notes.append(f"business nodes excluded from simulation: {excluded}")
    notes.append(f"parallel edges collapsed to fastest: {len(pd.read_csv(PROCESSED / 'edges.csv', usecols=['u'])) - len(e)}")
    cls = np.array([_class_of(h) for h in e["highway_class"]], dtype=np.int8)
    edge_index = {(int(a), int(b)): i for i, (a, b) in enumerate(zip(eu, ev, strict=True))}
    return Network(len(ids), ids, xs, ys, node_district, districts, eu, ev, e["free_flow_time_s"].to_numpy(float),
                   e["length_m"].to_numpy(float), cls, edge_index, business, notes)
