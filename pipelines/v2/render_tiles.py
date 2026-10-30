"""Render-only vector tiles for the India road map (plan v2 §8b). Zoom-dependent level of detail.

Routing never reads this file: it uses data/processed/india/edges.parquet with every edge. This artefact only
decides what the browser DRAWS at each zoom, so the national view never ships the whole graph.

  rank 0  expressway / NH            from z4
  rank 1  state highway / other trunk from z6
  rank 2  primary                     from z8
  rank 3  secondary                   from z8   (all *_link roads from z11)

Built in Python (mapbox-vector-tile + pmtiles) because tippecanoe needs root to install in WSL here.
Tiles are z4–z11; MapLibre over-zooms z11 tiles for closer views. Features keep `edge_id` from z8 so a click
identifies a routing edge; below z8 same-rank lines are merged per tile for size (clicks then snap via /edge-at).

    python -m pipelines.v2.render_tiles
"""
from __future__ import annotations

import gzip
import json
import math
import time
from pathlib import Path

import mapbox_vector_tile
import numpy as np
import pandas as pd
import shapely
from pmtiles.tile import Compression, TileType, zxy_to_tileid
from pmtiles.writer import Writer

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "data" / "processed" / "india" / "edges.parquet"
OUT = ROOT / "data" / "processed" / "india" / "render" / "roads.pmtiles"
EXTENT = 4096
BUFFER = 64
MINZOOM = {0: 4, 1: 6, 2: 8, 3: 8}
LINK_MINZOOM = 11
ZMIN, ZMAX = 4, 11
MERGE_BELOW = 8
SIMPLIFY_PX = {4: 6, 5: 5, 6: 4, 7: 3, 8: 2, 9: 1.5, 10: 1, 11: 0.5}   # in 1/4096-tile units ×(EXTENT/256)


def world_px(lon: np.ndarray, lat: np.ndarray, z: int) -> tuple[np.ndarray, np.ndarray]:
    n = (2 ** z) * EXTENT
    x = (lon + 180.0) / 360.0 * n
    lr = np.radians(np.clip(lat, -85, 85))
    y = (1 - np.log(np.tan(lr) + 1 / np.cos(lr)) / math.pi) / 2 * n
    return x, y


def main() -> None:
    t0 = time.time()
    e = pd.read_parquet(SRC, columns=["edge_id", "highway", "ref", "rank", "rough", "rough_src", "geom"])
    e["minzoom"] = np.where(e.highway.str.endswith("_link"), LINK_MINZOOM, e["rank"].map(MINZOOM))
    lon_all = np.concatenate([g[0::2] for g in e.geom])
    lat_all = np.concatenate([g[1::2] for g in e.geom])
    bounds = (float(lon_all.min()), float(lat_all.min()), float(lon_all.max()), float(lat_all.max()))
    del lon_all, lat_all
    OUT.parent.mkdir(parents=True, exist_ok=True)
    tiles: dict[int, bytes] = {}
    stats = {}
    for z in range(ZMIN, ZMAX + 1):
        sel = e[e.minzoom <= z]
        geoms = []
        for g in sel.geom:
            x, y = world_px(g[0::2], g[1::2], z)
            geoms.append(shapely.linestrings(np.column_stack([x, y])))
        geoms = shapely.simplify(np.array(geoms, dtype=object), SIMPLIFY_PX[z] * EXTENT / 256 / 4, preserve_topology=False)
        tree = shapely.STRtree(geoms)
        b = shapely.bounds(geoms)
        tx0, ty0 = np.floor(b[:, 0] / EXTENT).astype(int), np.floor(b[:, 1] / EXTENT).astype(int)
        tx1, ty1 = np.floor(b[:, 2] / EXTENT).astype(int), np.floor(b[:, 3] / EXTENT).astype(int)
        keys = set()
        for a, bb, c, d in zip(tx0, ty0, tx1, ty1):
            for tx in range(a, c + 1):
                for ty in range(bb, d + 1):
                    keys.add((tx, ty))
        props = sel[["edge_id", "rank", "ref", "rough", "rough_src", "highway"]].to_dict("records")
        sizes = []
        for tx, ty in sorted(keys):
            x0, y0 = tx * EXTENT - BUFFER, ty * EXTENT - BUFFER
            x1, y1 = (tx + 1) * EXTENT + BUFFER, (ty + 1) * EXTENT + BUFFER
            hits = tree.query(shapely.box(x0, y0, x1, y1))
            if len(hits) == 0:
                continue
            clipped = shapely.clip_by_rect(geoms[hits], x0, y0, x1, y1)
            local = shapely.transform(clipped, lambda c, tx=tx, ty=ty: c - np.array([tx * EXTENT, ty * EXTENT]))
            feats = []
            if z < MERGE_BELOW:
                by_rank: dict[int, list] = {}
                for h, gm in zip(hits, local):
                    if not gm.is_empty:
                        by_rank.setdefault(int(props[h]["rank"]), []).append(gm)
                for r, parts in by_rank.items():
                    merged = shapely.line_merge(shapely.multilinestrings([p for p in parts if p.geom_type == "LineString"] +
                                                                         [q for p in parts if p.geom_type == "MultiLineString" for q in p.geoms]))
                    feats.append({"geometry": merged, "properties": {"rank": r}})
            else:
                for h, gm in zip(hits, local):
                    if gm.is_empty:
                        continue
                    p = props[h]
                    feats.append({"geometry": gm, "properties": {
                        "edge_id": int(p["edge_id"]), "rank": int(p["rank"]), "ref": p["ref"] or "",
                        "rough": round(float(p["rough"]), 1), "rough_src": p["rough_src"], "link": int(p["highway"].endswith("_link"))}})
            if not feats:
                continue
            data = mapbox_vector_tile.encode([{"name": "roads", "features": feats}],
                                             default_options={"extents": EXTENT, "y_coord_down": True})
            gz = gzip.compress(data, 6)
            tiles[zxy_to_tileid(z, tx, ty)] = gz
            sizes.append(len(gz))
        stats[z] = {"edges": int(len(sel)), "tiles": len(sizes), "max_kb": round(max(sizes) / 1024, 1) if sizes else 0,
                    "mean_kb": round(sum(sizes) / len(sizes) / 1024, 1) if sizes else 0}
        print(f"z{z}: {stats[z]}  ({time.time() - t0:.0f}s)", flush=True)

    with open(OUT, "wb") as f:
        w = Writer(f)
        for tid in sorted(tiles):
            w.write_tile(tid, tiles[tid])
        lon0, lat0, lon1, lat1 = bounds
        w.finalize(
            {"tile_type": TileType.MVT, "tile_compression": Compression.GZIP, "min_zoom": ZMIN, "max_zoom": ZMAX,
             "min_lon_e7": int(lon0 * 1e7), "min_lat_e7": int(lat0 * 1e7), "max_lon_e7": int(lon1 * 1e7),
             "max_lat_e7": int(lat1 * 1e7), "center_zoom": 5, "center_lon_e7": int(78.9 * 1e7), "center_lat_e7": int(22.5 * 1e7)},
            {"name": "India roads (render LOD)", "attribution": "© OpenStreetMap contributors (ODbL)",
             "vector_layers": [{"id": "roads", "minzoom": ZMIN, "maxzoom": ZMAX,
                                "fields": {"edge_id": "Number", "rank": "Number", "ref": "String", "rough": "Number",
                                           "rough_src": "String", "link": "Number"}}],
             "lod": {"rank_minzoom": MINZOOM, "link_minzoom": LINK_MINZOOM, "merged_below_zoom": MERGE_BELOW}})
    rep = {"file": str(OUT.relative_to(ROOT)), "bytes": OUT.stat().st_size, "zooms": stats, "seconds": round(time.time() - t0)}
    (OUT.parent / "tiles_report.json").write_text(json.dumps(rep, indent=2), encoding="utf-8")
    print(json.dumps(rep, indent=2))


if __name__ == "__main__":
    main()
