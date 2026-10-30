"""India road graph for routing: directed arcs in numpy arrays + KD-trees for snapping (plan v2 §4).

Completely independent of map rendering: every edge built by pipelines/v2/india_roads.py is kept here.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.spatial import cKDTree

ROOT = Path(__file__).resolve().parents[2]
GRAPH_DIR = ROOT / "data" / "processed" / "india"
HIGHWAYS = ["motorway", "motorway_link", "trunk", "trunk_link", "primary", "primary_link", "secondary", "secondary_link"]


def _xyz(lon: np.ndarray, lat: np.ndarray) -> np.ndarray:
    lo, la = np.radians(lon), np.radians(lat)
    return np.column_stack([np.cos(la) * np.cos(lo), np.cos(la) * np.sin(lo), np.sin(la)])


def hav_km(lon1, lat1, lon2, lat2):
    r = math.pi / 180
    dlat, dlon = (np.asarray(lat2) - lat1) * r, (np.asarray(lon2) - lon1) * r
    a = np.sin(dlat / 2) ** 2 + np.cos(np.asarray(lat1) * r) * np.cos(np.asarray(lat2) * r) * np.sin(dlon / 2) ** 2
    return 2 * 6371 * np.arcsin(np.sqrt(a))


@dataclass
class RoadGraph:
    lon: np.ndarray
    lat: np.ndarray
    # edges (as stored)
    eu: np.ndarray
    ev: np.ndarray
    len_km: np.ndarray
    speed: np.ndarray
    rough: np.ndarray
    rough_src: np.ndarray
    hw: np.ndarray          # index into HIGHWAYS
    rank: np.ndarray
    hgv_no: np.ndarray
    way_id: np.ndarray
    ref: np.ndarray
    name: np.ndarray
    g_flat: np.ndarray      # all edge geometries concatenated [lon, lat, lon, lat, ...]
    g_off: np.ndarray       # edge e's geometry is g_flat[g_off[e]:g_off[e+1]]
    # directed arcs
    a_edge: np.ndarray
    a_from: np.ndarray
    a_to: np.ndarray
    a_fwd: np.ndarray
    node_tree: cKDTree
    _vert: tuple | None = None

    @property
    def n(self) -> int:
        return len(self.lon)

    def geom(self, e: int) -> np.ndarray:
        return self.g_flat[self.g_off[e]:self.g_off[e + 1]]

    @property
    def geoms(self) -> "_Geoms":
        return _Geoms(self)

    def _vertex_index(self) -> tuple[cKDTree, np.ndarray]:
        # Built on first click: every vertex + segment midpoints, mapped back to its edge.
        if self._vert is None:
            x, y = self.g_flat[0::2], self.g_flat[1::2]
            npts = np.diff(self.g_off) // 2
            ve = np.repeat(np.arange(len(npts)), npts)
            same = np.concatenate([ve[1:] == ve[:-1], [False]])
            mx, my, me = (x[:-1] + x[1:])[same[:-1]] / 2, (y[:-1] + y[1:])[same[:-1]] / 2, ve[:-1][same[:-1]]
            self._vert = (cKDTree(_xyz(np.concatenate([x, mx]), np.concatenate([y, my]))), np.concatenate([ve, me]))
        return self._vert

    def nearest_node(self, lon: float, lat: float) -> tuple[int, float]:
        d, i = self.node_tree.query(_xyz(np.array([lon]), np.array([lat]))[0])
        return int(i), float(d * 6371)

    def nearest_edge(self, lon: float, lat: float) -> tuple[int, float]:
        tree, ve = self._vertex_index()
        d, i = tree.query(_xyz(np.array([lon]), np.array([lat]))[0])
        return int(ve[i]), float(d * 6371)

    def edge_coords(self, e: int, fwd: bool = True) -> list[list[float]]:
        pts = self.geom(e).reshape(-1, 2).tolist()
        return pts if fwd else pts[::-1]

    def edge_info(self, e: int) -> dict:
        return {
            "edge_id": int(e), "way_id": int(self.way_id[e]), "highway": HIGHWAYS[self.hw[e]],
            "ref": self.ref[e] or None, "name": self.name[e] or None, "len_km": round(float(self.len_km[e]), 3),
            "speed_kmh": float(self.speed[e]), "roughness": float(self.rough[e]), "roughness_src": self.rough_src[e],
            "hgv_restricted": bool(self.hgv_no[e]), "rank": int(self.rank[e]),
            "coords": self.edge_coords(e),
        }

    def way_edges(self, way_id: int) -> np.ndarray:
        return np.nonzero(self.way_id == way_id)[0]


class _Geoms:
    """Sequence view so callers can still write g.geoms[e]."""
    def __init__(self, g: "RoadGraph"):
        self.g = g

    def __getitem__(self, e: int) -> np.ndarray:
        return self.g.geom(e)

    def __len__(self) -> int:
        return len(self.g.g_off) - 1

    def __iter__(self):
        return (self.g.geom(e) for e in range(len(self)))


def build(nodes: pd.DataFrame, edges: pd.DataFrame, geom_flat: np.ndarray | None = None,
          geom_off: np.ndarray | None = None) -> RoadGraph:
    if geom_flat is None:
        lens = edges.geom.map(len).to_numpy()
        geom_off = np.concatenate([[0], np.cumsum(lens)])
        geom_flat = np.concatenate(edges.geom.to_numpy()) if len(edges) else np.zeros(0)
    g_flat, g_off = geom_flat, geom_off
    eu, ev = edges.u.to_numpy(np.int64), edges.v.to_numpy(np.int64)
    ow = edges.oneway.to_numpy(np.int8)
    fwd = ow >= 0
    bwd = ow <= 0
    eidx = np.arange(len(edges))
    a_edge = np.concatenate([eidx[fwd], eidx[bwd]])
    a_from = np.concatenate([eu[fwd], ev[bwd]])
    a_to = np.concatenate([ev[fwd], eu[bwd]])
    a_fwd = np.concatenate([np.ones(fwd.sum(), bool), np.zeros(bwd.sum(), bool)])
    lon, lat = nodes.lon.to_numpy(), nodes.lat.to_numpy()
    hw_index = {h: i for i, h in enumerate(HIGHWAYS)}
    return RoadGraph(
        lon=lon, lat=lat, eu=eu, ev=ev, len_km=edges.len_m.to_numpy() / 1000, speed=edges.speed_kmh.to_numpy(float),
        rough=edges.rough.to_numpy(float), rough_src=edges.rough_src.to_numpy(), hw=edges.highway.map(hw_index).to_numpy(np.int8),
        rank=edges["rank"].to_numpy(np.int8), hgv_no=edges.hgv_no.to_numpy(bool), way_id=edges.way_id.to_numpy(np.int64),
        ref=edges.ref.fillna("").to_numpy(), name=edges.name.fillna("").to_numpy(), g_flat=g_flat, g_off=g_off,
        a_edge=a_edge, a_from=a_from, a_to=a_to, a_fwd=a_fwd,
        node_tree=cKDTree(_xyz(lon, lat)),
    )


@lru_cache(maxsize=1)
def load_graph(directory: str | None = None) -> RoadGraph:
    import pyarrow.parquet as pq
    d = Path(directory) if directory else GRAPH_DIR
    t = pq.read_table(d / "edges.parquet")
    geom = t.column("geom").combine_chunks()
    flat = geom.flatten().to_numpy()
    off = geom.offsets.to_numpy().astype(np.int64)
    off = off - off[0]
    edges = t.drop(["geom"]).to_pandas()
    return build(pd.read_parquet(d / "nodes.parquet"), edges, flat, off)
