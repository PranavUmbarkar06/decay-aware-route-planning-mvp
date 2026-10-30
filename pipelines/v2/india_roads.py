"""Build the India routing graph from a Geofabrik OSM extract (plan v2 §3).

Stage A (C++ via pyosmium): keep highway ∈ {motorway, trunk, primary, secondary} + links, plus the nodes they
reference, into data/cache/india_roads.osm.pbf.
Stage B: split ways at shared nodes into edges, compute length, speed, roughness and render rank, keep the largest
connected component, write data/processed/india/{nodes,edges}.parquet.

Routing uses these parquet files. Rendering uses a SEPARATE artefact built from them (render_tiles.py).
Data © OpenStreetMap contributors, ODbL 1.0.

    python -m pipelines.v2.india_roads [path/to/extract.osm.pbf]
"""
from __future__ import annotations

import json
import math
import re
import sys
import time
from array import array
from pathlib import Path

import numpy as np
import osmium
import pandas as pd
import yaml
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "data" / "raw" / "geofabrik_india" / "india-latest.osm.pbf"
CACHE = ROOT / "data" / "cache"
OUT = ROOT / "data" / "processed" / "india"

CLASSES = ["motorway", "motorway_link", "trunk", "trunk_link", "primary", "primary_link",
           "secondary", "secondary_link"]
KEEP_TAGS = ["highway", "ref", "name", "surface", "smoothness", "maxspeed", "oneway", "junction", "hgv", "lanes"]

# Roughness 0 (smooth) … 10 (very poor). ASSUMPTION: illustrative mapping, source recorded per edge.
SMOOTHNESS = {"excellent": 1.0, "good": 2.0, "intermediate": 4.5, "bad": 6.5, "very_bad": 8.0,
              "horrible": 9.0, "very_horrible": 9.5, "impassable": 10.0}
SURFACE = {"concrete": 2.5, "concrete:plates": 3.0, "paving_stones": 5.0, "sett": 6.0, "cobblestone": 7.0,
           "compacted": 6.0, "fine_gravel": 6.5, "gravel": 7.0, "pebblestone": 7.5, "unpaved": 8.0,
           "dirt": 8.5, "earth": 8.5, "ground": 8.5, "mud": 9.5, "sand": 9.0}
CLASS_ROUGH = {"motorway": 1.5, "trunk": 3.0, "primary": 4.0, "secondary": 5.0}

_MAXSPEED_RE = re.compile(r"^\s*(\d+(?:\.\d+)?)\s*(mph|km/h|kmh)?\s*$", re.I)


def speeds() -> dict:
    return yaml.safe_load((ROOT / "config" / "speeds.yaml").read_text(encoding="utf-8"))


def parse_maxspeed(v: str | None) -> float | None:
    if not v:
        return None
    m = _MAXSPEED_RE.match(str(v).split(";")[0])
    if not m:
        return None
    val = float(m.group(1))
    return val * 1.609344 if (m.group(2) or "").lower() == "mph" else val


def roughness(hw: str, smoothness: str | None, surface: str | None) -> tuple[float, str]:
    base = CLASS_ROUGH[hw.replace("_link", "")] + (0.5 if hw.endswith("_link") else 0)
    if smoothness in SMOOTHNESS:
        return SMOOTHNESS[smoothness], "osm_smoothness"
    if surface in SURFACE:
        return max(base, SURFACE[surface]) if SURFACE[surface] > 3 else min(base, SURFACE[surface]), "osm_surface"
    return base, "class_default"


def render_rank(hw: str, ref: str | None) -> int:
    refs = [r.strip().upper().replace(" ", "").replace("-", "") for r in (ref or "").split(";") if r.strip()]
    if hw.endswith("_link"):
        return 3
    if hw == "motorway" or any(r.startswith("NH") or r.startswith("NE") for r in refs):
        return 0
    if hw == "trunk" or any(r.startswith("SH") or r.startswith("MDR") for r in refs):
        return 1
    if hw == "primary":
        return 2
    return 3


def stage_a(src: Path, dst: Path) -> None:
    if dst.exists() and dst.stat().st_mtime > src.stat().st_mtime:
        print(f"stage A cached: {dst.name}")
        return
    t0 = time.time()
    flt = osmium.filter.TagFilter(*[("highway", c) for c in CLASSES])
    n = 0
    with osmium.BackReferenceWriter(str(dst), ref_src=str(src), overwrite=True) as writer:
        for obj in osmium.FileProcessor(str(src), osmium.osm.WAY).with_filter(flt):
            writer.add_way(obj)
            n += 1
    print(f"stage A: {n:,} ways -> {dst.name} ({dst.stat().st_size / 1e6:.0f} MB) in {time.time() - t0:.0f}s")


def hav_m(lon1, lat1, lon2, lat2):
    r = math.pi / 180
    dlat, dlon = (lat2 - lat1) * r, (lon2 - lon1) * r
    a = np.sin(dlat / 2) ** 2 + np.cos(lat1 * r) * np.cos(lat2 * r) * np.sin(dlon / 2) ** 2
    return 2 * 6371000 * np.arcsin(np.sqrt(a))


def stage_b(src: Path) -> None:
    t0 = time.time()
    ways: list[tuple[int, array, array, array, dict]] = []
    for w in osmium.FileProcessor(str(src), osmium.osm.NODE | osmium.osm.WAY).with_locations():
        if not w.is_way():
            continue
        hw = w.tags.get("highway")
        if hw not in CLASSES:
            continue
        ids, xs, ys = array("q"), array("d"), array("d")
        for nd in w.nodes:
            if not nd.location.valid():
                continue
            ids.append(nd.ref)
            xs.append(nd.location.lon)
            ys.append(nd.location.lat)
        if len(ids) < 2:
            continue
        ways.append((w.id, ids, xs, ys, {k: w.tags.get(k) for k in KEEP_TAGS}))
    print(f"stage B: read {len(ways):,} ways in {time.time() - t0:.0f}s")

    # Split points: nodes used by more than one way, or way endpoints.
    all_ids = np.concatenate([np.frombuffer(w[1], dtype=np.int64) for w in ways])
    uniq, counts = np.unique(all_ids, return_counts=True)
    shared = set(uniq[counts > 1].tolist())
    del all_ids

    sp = speeds()
    cap = sp["truck_speed_cap_kmh"]
    cls_kmh = sp["class_default_kmh"]
    node_index: dict[int, int] = {}
    node_xy: list[tuple[float, float]] = []

    def nid(osm_id: int, x: float, y: float) -> int:
        i = node_index.get(osm_id)
        if i is None:
            i = len(node_xy)
            node_index[osm_id] = i
            node_xy.append((x, y))
        return i

    rows = {k: [] for k in ["u", "v", "way_id", "highway", "ref", "name", "len_m", "speed_kmh", "speed_src",
                            "oneway", "hgv_no", "rough", "rough_src", "rank", "geom"]}
    for way_id, ids, xs, ys, tags in ways:
        hw = tags["highway"]
        ms = parse_maxspeed(tags["maxspeed"])
        speed, ssrc = (min(ms, cap), "osm_maxspeed") if ms else (cls_kmh.get(hw, cls_kmh["unclassified"]), "class_default")
        ow = tags["oneway"]
        oneway = 1 if (ow in ("yes", "true", "1") or tags["junction"] == "roundabout" or hw == "motorway") else (-1 if ow == "-1" else 0)
        hgv_no = 1 if tags["hgv"] in ("no", "destination") else 0
        rough, rsrc = roughness(hw, tags["smoothness"], tags["surface"])
        rank = render_rank(hw, tags["ref"])
        x, y = np.frombuffer(xs, dtype=np.float64), np.frombuffer(ys, dtype=np.float64)
        seg_m = hav_m(x[:-1], y[:-1], x[1:], y[1:])
        start = 0
        n = len(ids)
        for j in range(1, n):
            if j == n - 1 or ids[j] in shared:
                u = nid(ids[start], x[start], y[start])
                v = nid(ids[j], x[j], y[j])
                if u != v:
                    rows["u"].append(u); rows["v"].append(v); rows["way_id"].append(way_id)
                    rows["highway"].append(hw); rows["ref"].append(tags["ref"]); rows["name"].append(tags["name"])
                    rows["len_m"].append(float(seg_m[start:j].sum())); rows["speed_kmh"].append(speed)
                    rows["speed_src"].append(ssrc); rows["oneway"].append(oneway); rows["hgv_no"].append(hgv_no)
                    rows["rough"].append(rough); rows["rough_src"].append(rsrc); rows["rank"].append(rank)
                    g = np.empty(2 * (j - start + 1))
                    g[0::2] = np.round(x[start:j + 1], 5)
                    g[1::2] = np.round(y[start:j + 1], 5)
                    rows["geom"].append(g)
                start = j
    del ways
    edges = pd.DataFrame(rows)
    nodes = pd.DataFrame(node_xy, columns=["lon", "lat"])
    print(f"stage B: {len(nodes):,} nodes, {len(edges):,} edges before component filter")

    # Largest weakly connected component.
    m = coo_matrix((np.ones(len(edges)), (edges.u.values, edges.v.values)), shape=(len(nodes), len(nodes)))
    ncomp, labels = connected_components(m, directed=False)
    big = np.bincount(labels).argmax()
    keep_node = labels == big
    edges = edges[keep_node[edges.u.values] & keep_node[edges.v.values]].copy()
    remap = -np.ones(len(nodes), dtype=np.int64)
    remap[keep_node] = np.arange(keep_node.sum())
    nodes = nodes[keep_node].reset_index(drop=True)
    edges["u"] = remap[edges.u.values]
    edges["v"] = remap[edges.v.values]
    edges = edges.reset_index(drop=True)
    edges.insert(0, "edge_id", np.arange(len(edges), dtype=np.int64))

    OUT.mkdir(parents=True, exist_ok=True)
    nodes.to_parquet(OUT / "nodes.parquet", index=False)
    edges.to_parquet(OUT / "edges.parquet", index=False)
    stats = {
        "source": src.name, "built_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "attribution": "© OpenStreetMap contributors (ODbL 1.0)",
        "components_dropped": int(ncomp - 1), "nodes": int(len(nodes)), "edges": int(len(edges)),
        "km_total": round(float(edges.len_m.sum()) / 1000),
        "by_highway_km": {k: round(float(v) / 1000) for k, v in edges.groupby("highway").len_m.sum().items()},
        "by_rank": {int(k): int(v) for k, v in edges["rank"].value_counts().items()},
        "rough_src": {k: int(v) for k, v in edges.rough_src.value_counts().items()},
        "speed_src": {k: int(v) for k, v in edges.speed_src.value_counts().items()},
        "oneway_edges": int((edges.oneway != 0).sum()), "hgv_restricted_edges": int(edges.hgv_no.sum()),
        "seconds": round(time.time() - t0),
    }
    (OUT / "graph_stats.json").write_text(json.dumps(stats, indent=2), encoding="utf-8")
    print(json.dumps(stats, indent=2))


def main() -> None:
    src = Path(sys.argv[1]) if len(sys.argv) > 1 else RAW
    CACHE.mkdir(parents=True, exist_ok=True)
    filtered = CACHE / f"{src.name.split('.')[0]}_roads.osm.pbf"
    stage_a(src, filtered)
    stage_b(filtered)


if __name__ == "__main__":
    main()
