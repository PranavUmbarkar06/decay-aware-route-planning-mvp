"""`make graph`: build the road graph and generate data/processed/nodes.csv + edges.csv (brief §9, §9A).

Inputs: data/cache/osm_road_ways.parquet, data/cache/osm_places.parquet, data/processed/osm_pois.csv
(from pipelines.osm_extract), agmarknet_markets.csv, agmarknet_arrivals_daily.csv, division boundary.
If the OSM extract is unavailable, a SYNTHETIC_DEMO grid network is generated instead and every output
is flagged "Synthetic network: not real roads" (§9 step 9); never silently.
"""
from __future__ import annotations

import difflib
import hashlib
import json
import math
import re
import sys
import unicodedata
from dataclasses import dataclass, field

import geopandas as gpd
import networkx as nx
import numpy as np
import osmnx as ox
import pandas as pd
from app.core.config import geography, speeds, thresholds
from shapely.geometry import LineString, Point, mapping
from sklearn.neighbors import BallTree

from pipelines.common import CACHE, PROCESSED, ROOT, AuditRecord, write_audit, write_csv_deterministic

EARTH_R = 6_371_008.8
GEO_DIR = PROCESSED / "geo"
REPORTS = ROOT / "reports"

NODE_COLS = ["node_id", "node_type", "name", "name_source", "lat", "lon", "district", "osm_id",
             "agmarknet_market_name", "geocode_method", "geocode_confidence", "snapped_graph_node", "snap_distance_m",
             "capacity_kg", "capacity_source", "provenance", "source_manifest_id", "needs_review", "notes"]
EDGE_COLS = ["edge_id", "u", "v", "osm_way_id", "highway_class", "length_m", "maxspeed_kmh", "speed_kmh_used",
             "speed_source", "free_flow_time_s", "oneway", "road_name", "provenance", "source_manifest_id", "speed_flag"]


def haversine_m(lon1, lat1, lon2, lat2):
    lon1, lat1, lon2, lat2 = map(np.radians, (lon1, lat1, lon2, lat2))
    a = np.sin((lat2 - lat1) / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin((lon2 - lon1) / 2) ** 2
    return 2 * EARTH_R * np.arcsin(np.sqrt(a))


def stable_id(prefix: str, *parts: str) -> str:
    return prefix + hashlib.sha1("|".join(parts).encode("utf-8")).hexdigest()[:12]


# ---------------------------------------------------------------- speeds (brief §9 step 3, 9A step 3)
_MAXSPEED_RE = re.compile(r"^\s*(\d+(?:\.\d+)?)\s*(mph|km/h|kmh|kph)?\s*$", re.I)


def parse_maxspeed(v) -> float | None:
    """Numeric OSM maxspeed in km/h; anything non-numeric (e.g. 'IN:urban', 'signals') → None."""
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return None
    first = str(v).split(";")[0]
    m = _MAXSPEED_RE.match(first)
    if not m:
        return None
    val = float(m.group(1))
    return val * 1.609344 if (m.group(2) or "").lower() == "mph" else val


def speed_for(highway: str, maxspeed) -> tuple[float, str, float | None]:
    sp = speeds()
    ms = parse_maxspeed(maxspeed)
    if ms is not None:
        return min(ms, sp.truck_speed_cap_kmh), "osm_maxspeed", ms
    return sp.class_default_kmh.get(highway, sp.class_default_kmh["unclassified"]), "class_default_ASSUMPTION", None


def is_oneway(oneway, junction) -> tuple[bool, bool]:
    """(oneway, reversed_direction) following OSM tagging conventions."""
    o = str(oneway).lower() if oneway is not None else ""
    if o in ("yes", "true", "1"):
        return True, False
    if o == "-1":
        return True, True
    if str(junction).lower() == "roundabout" and o != "no":
        return True, False
    return False, False


# ---------------------------------------------------------------- road graph
@dataclass
class BuildStats:
    counts: dict = field(default_factory=dict)
    drops: list = field(default_factory=list)
    checks: list = field(default_factory=list)
    synthetic: bool = False


def graph_from_ways(ways: pd.DataFrame) -> nx.MultiDiGraph:
    G = nx.MultiDiGraph(crs="epsg:4326")
    for w in ways.itertuples(index=False):
        ids, lons, lats = list(w.node_ids), list(w.lons), list(w.lats)
        for nid, x, y in zip(ids, lons, lats, strict=True):
            if nid not in G:
                G.add_node(int(nid), x=float(x), y=float(y))
        sp, src, ms = speed_for(w.highway, w.maxspeed)
        one, rev = is_oneway(w.oneway, w.junction)
        seq = list(zip(ids, lons, lats, strict=True))
        if rev:
            seq = seq[::-1]
        for (a, ax, ay), (b, bx, by) in zip(seq[:-1], seq[1:], strict=True):
            if a == b:
                continue
            length = float(haversine_m(ax, ay, bx, by))
            attrs = {"osmid": int(w.way_id), "highway": w.highway, "maxspeed_kmh": ms, "speed_kmh_used": sp,
                     "speed_source": src, "length": length, "free_flow_time_s": length / (sp / 3.6),
                     "oneway": one, "name": w.name if isinstance(w.name, str) else None,
                     "reversed": False}
            G.add_edge(int(a), int(b), **attrs)
            if not one:
                G.add_edge(int(b), int(a), **{**attrs, "reversed": True})
    return G


def _first(v):
    return v[0] if isinstance(v, list) else v


def _joined(v):
    if isinstance(v, list):
        vals = sorted({str(x) for x in v if x is not None and not (isinstance(x, float) and math.isnan(x))})
        return ";".join(vals) if vals else None
    return v


def build_road_graph(stats: BuildStats) -> tuple[nx.MultiDiGraph, str]:
    ways = pd.read_parquet(CACHE / "osm_road_ways.parquet")
    mid = str(ways["source_manifest_id"].iloc[0])
    G = graph_from_ways(ways)
    stats.counts["raw_nodes"], stats.counts["raw_edges"] = G.number_of_nodes(), G.number_of_edges()
    stats.counts["ways"] = len(ways)

    G = ox.simplify_graph(G, edge_attr_aggs={"length": sum, "free_flow_time_s": sum})
    stats.counts["simplified_nodes"], stats.counts["simplified_edges"] = G.number_of_nodes(), G.number_of_edges()

    geo = geography().current
    div = gpd.read_file(PROCESSED / "division_boundary.geojson").to_crs(32644)
    poly = div.buffer(geo.boundary_buffer_km * 1000).to_crs(4326).iloc[0]
    n0, e0 = G.number_of_nodes(), G.number_of_edges()
    G = ox.truncate.truncate_graph_polygon(G, poly, truncate_by_edge=True)
    stats.drops.append({"step": f"clip to division polygon + {geo.boundary_buffer_km} km buffer",
                        "nodes_dropped": n0 - G.number_of_nodes(), "edges_dropped": e0 - G.number_of_edges(),
                        "why": "outside pilot geography"})

    loops = [(u, v, k) for u, v, k in G.edges(keys=True) if u == v]
    G.remove_edges_from(loops)
    stats.drops.append({"step": "remove self-loops", "nodes_dropped": 0, "edges_dropped": len(loops),
                        "why": "closed ways (e.g. loops) collapse to self-loops after simplification; not routable"})
    zero = [(u, v, k) for u, v, k, d in G.edges(keys=True, data=True) if d["length"] <= 0]
    G.remove_edges_from(zero)
    stats.drops.append({"step": "remove zero-length edges", "nodes_dropped": 0, "edges_dropped": len(zero),
                        "why": "duplicate coordinates"})

    n0, e0 = G.number_of_nodes(), G.number_of_edges()
    G = ox.truncate.largest_component(G, strongly=True)
    stats.drops.append({"step": "keep largest strongly connected component", "nodes_dropped": n0 - G.number_of_nodes(),
                        "edges_dropped": e0 - G.number_of_edges(),
                        "why": "fragments unreachable in both directions (cut at the extract/state edge, isolated "
                               "service stubs, one-way dead ends)"})
    G = nx.MultiDiGraph(G)
    stats.counts["final_nodes"], stats.counts["final_edges"] = G.number_of_nodes(), G.number_of_edges()
    return G, mid


def edges_frame(G: nx.MultiDiGraph, mid: str, provenance: str = "REAL_DERIVED") -> pd.DataFrame:
    lo, hi = speeds().plausible_range_kmh
    rows = []
    for u, v, k, d in G.edges(keys=True, data=True):
        length = float(d["length"])
        t = float(d["free_flow_time_s"])
        eff = length / t * 3.6 if t > 0 else float("nan")
        src = d["speed_source"]
        src = ("mixed:" + _joined(src)) if isinstance(src, list) and len(set(src)) > 1 else _first(src)
        ms = d.get("maxspeed_kmh")
        ms = None if isinstance(ms, list) else ms
        rows.append({
            "edge_id": f"E{u}_{v}_{k}", "u": u, "v": v, "osm_way_id": _joined(d["osmid"]),
            "highway_class": _first(d["highway"]) if not isinstance(d["highway"], list) else _joined(d["highway"]),
            "length_m": round(length, 3), "maxspeed_kmh": ms, "speed_kmh_used": round(eff, 3),
            "speed_source": src, "free_flow_time_s": round(t, 3), "oneway": bool(_first(d["oneway"])),
            "road_name": _joined(d.get("name")), "provenance": provenance, "source_manifest_id": mid,
            "speed_flag": "" if lo <= eff <= hi else "OUT_OF_PLAUSIBLE_RANGE",
        })
    return pd.DataFrame(rows, columns=EDGE_COLS)


# ---------------------------------------------------------------- business nodes
def norm(s: str | None) -> str:
    if not s:
        return ""
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z]", "", s.lower())


def skeleton(s: str | None) -> str:
    """Transliteration-tolerant key for Marathi place names written in Latin script: w→v, ao/au→av,
    drop 'h', drop vowels, collapse repeats (e.g. Savner/Saoner, Varora/Warora, Pavani/Pauni,
    Brahmpuri/Bramhapuri). Only ever used to *suggest* a location for human review (confidence 0.45)."""
    n = norm(s).replace("w", "v").replace("ao", "av").replace("au", "av").replace("h", "")
    n = re.sub(r"[aeiouy]", "", n)
    return re.sub(r"(.)+", r"", n)


def market_town_token(name: str) -> tuple[str, str]:
    """('town', 'pattern') parsed from an Agmarknet market label. Rules are documented in GRAPH_BUILD.md."""
    n = re.sub(r"\s+", " ", name).strip()
    m = re.match(r"^APMC\s+(.+)$", n, re.I)
    if m:
        return m.group(1).strip(), "APMC <town>"
    m = re.match(r"^([^()]+)\(([^)]+)\)$", n)
    if m:
        return m.group(1).strip(), "<town>(<locality>)"
    if re.search(r"pvt|ltd|m/s|infra|agro|krishi", n, re.I):
        parts = [p.strip() for p in n.split(",") if p.strip()]
        tail = [p for p in parts[1:] if not re.search(r"dist", p, re.I)] or [re.sub(r"(?i)dist\.?\s*", "", parts[-1])]
        return tail[0].strip(), "private market: operator town"
    return n, "plain"


def geocode_markets(markets: pd.DataFrame, places: pd.DataFrame, pois: pd.DataFrame,
                    districts: gpd.GeoDataFrame) -> pd.DataFrame:
    gplaces = gpd.GeoDataFrame(places, geometry=gpd.points_from_xy(places["lon"], places["lat"]), crs=4326)
    gplaces = gpd.sjoin(gplaces, districts[["district", "geometry"]], predicate="within", how="inner")
    gplaces["n_name"] = gplaces["name"].map(norm)
    gplaces["n_en"] = gplaces["name_en"].map(norm)
    mk = pois[pois["category"] == "MarketplaceCandidate"].copy()
    gmk = gpd.GeoDataFrame(mk, geometry=gpd.points_from_xy(mk["lon"], mk["lat"]), crs=4326)
    gmk = gpd.sjoin(gmk, districts[["district", "geometry"]], predicate="within", how="inner") if len(gmk) else gmk
    rank = {"city": 0.65, "town": 0.65, "village": 0.55, "hamlet": 0.45}
    out = []
    for m in markets.itertuples(index=False):
        town, pattern = market_town_token(m.market_name_clean)
        tn = norm(town)
        res = {"lat": None, "lon": None, "osm_id": None, "geocode_method": None, "geocode_confidence": 0.0,
               "notes": f"town token '{town}' via rule '{pattern}'"}
        # A: OSM marketplace/APMC feature in the same district whose name contains the town token
        cand = gmk[(gmk["district"] == m.district) & gmk["name"].map(lambda s, tn=tn: bool(tn) and tn in norm(s))] if len(gmk) else gmk
        if len(cand) == 1:
            c = cand.iloc[0]
            res |= {"lat": c["lat"], "lon": c["lon"], "osm_id": c["osm_id"], "geocode_method": "osm_tag",
                    "geocode_confidence": 0.85, "notes": res["notes"] + f"; matched OSM market feature '{c['name']}'"}
        else:
            sub = gplaces[gplaces["district"] == m.district]
            exact = sub[(sub["n_name"] == tn) | (sub["n_en"] == tn)]
            method_note = "exact"
            if exact.empty and tn:
                names = sorted(set(sub["n_name"]) | set(sub["n_en"]) - {""})
                close = difflib.get_close_matches(tn, names, n=3, cutoff=0.85)
                if close:
                    exact = sub[(sub["n_name"] == close[0]) | (sub["n_en"] == close[0])]
                    method_note = f"fuzzy '{close[0]}'"
            if len(exact):
                best = exact.sort_values("place", key=lambda s: s.map(lambda p: -rank.get(p, 0))).iloc[0]
                conf = rank.get(best["place"], 0.4)
                if method_note != "exact":
                    conf -= 0.1
                if (exact["place"] == best["place"]).sum() > 1:
                    conf -= 0.15
                    method_note += f"; {int((exact['place'] == best['place']).sum())} same-rank candidates"
                if pattern == "private market: operator town":
                    conf = min(conf, 0.45)
                    method_note += "; private market located at its operator's town (site unknown)"
                res |= {"lat": best["lat"], "lon": best["lon"], "osm_id": best["osm_id"],
                        "geocode_method": "agmarknet_name_match", "geocode_confidence": round(conf, 2),
                        "notes": res["notes"] + f"; {method_note} match to OSM place={best['place']} '{best['name']}' "
                                                "(town centroid used as a proxy for the market yard)"}
            elif len(cand) > 1:
                res["notes"] += f"; {len(cand)} ambiguous OSM market features, no unique place match"
            else:
                sk = skeleton(town)
                ph = sub[(sub["n_name"].map(skeleton) == sk) | (sub["n_en"].map(skeleton) == sk)] if sk else sub.iloc[0:0]
                ph = ph[ph["place"].isin(["city", "town", "village"])]
                if len(ph):
                    best = ph.sort_values("place", key=lambda s: s.map(lambda p: -rank.get(p, 0))).iloc[0]
                    res |= {"lat": best["lat"], "lon": best["lon"], "osm_id": best["osm_id"],
                            "geocode_method": "agmarknet_name_match", "geocode_confidence": 0.45,
                            "notes": res["notes"] + f"; transliteration-skeleton match '{sk}' to OSM place={best['place']} "
                                                    f"'{best['name']}' ({len(ph)} candidate(s)): SUGGESTION ONLY, needs review"}
                else:
                    res["notes"] += "; no OSM place or market feature matched (also no transliteration match)"
        out.append(res)
    return pd.concat([markets.reset_index(drop=True), pd.DataFrame(out)], axis=1)


def build_business_nodes(G: nx.MultiDiGraph | None, stats: BuildStats, synthetic: bool) -> pd.DataFrame:
    th = thresholds().graph
    districts = gpd.read_file(PROCESSED / "district_boundaries.geojson")[["district", "geometry"]]
    markets = pd.read_csv(PROCESSED / "agmarknet_markets.csv")
    rows = []
    if not synthetic:
        places = pd.read_parquet(CACHE / "osm_places.parquet")
        pois = pd.read_csv(PROCESSED / "osm_pois.csv")
        place_mid = str(places["source_manifest_id"].iloc[0])
        daily_p = PROCESSED / "agmarknet_arrivals_daily.csv"
        receiving = set()
        if daily_p.exists():
            d = pd.read_csv(daily_p)
            receiving = set(d[d["in_pilot_commodity"]]["market_name_clean"])
        gm = geocode_markets(markets, places, pois, districts)
        for m in gm.itertuples(index=False):
            ntype = "ReceivingMarket" if m.market_name_clean in receiving else "AssemblyMandi"
            rows.append({
                "node_type": ntype, "name": m.market_name_clean, "name_source": "agmarknet_master",
                "lat": m.lat, "lon": m.lon, "district": m.district, "osm_id": m.osm_id,
                "agmarknet_market_name": m.agmarknet_market_name, "geocode_method": m.geocode_method,
                "geocode_confidence": m.geocode_confidence, "capacity_kg": None, "capacity_source": "MISSING (DATA_GAPS)",
                "provenance": "REAL_FETCHED", "source_manifest_id": f"{m.source_manifest_id};{place_mid}",
                "notes": m.notes + ("; role ReceivingMarket because it reports pilot-commodity arrivals in Agmarknet exports"
                                    if ntype == "ReceivingMarket" else "; role AssemblyMandi (no pilot arrivals in exports)"),
                "_src": f"agmarknet:{m.agmarknet_market_id}"})
        # Real OSM POIs
        gp = gpd.GeoDataFrame(pois, geometry=gpd.points_from_xy(pois["lon"], pois["lat"]), crs=4326)
        gp = gpd.sjoin(gp, districts, predicate="within", how="left")
        for p in gp[gp["category"] != "MarketplaceCandidate"].itertuples(index=False):
            named = isinstance(p.name, str) and p.name.strip()
            rows.append({
                "node_type": p.category, "name": p.name if named else f"Unnamed {p.category} ({p.osm_id})",
                "name_source": "osm" if named else "generated_from_osm_id", "lat": p.lat, "lon": p.lon,
                "district": p.district, "osm_id": p.osm_id, "agmarknet_market_name": None, "geocode_method": "osm_tag",
                "geocode_confidence": 0.9, "capacity_kg": None, "capacity_source": "MISSING (DATA_GAPS)",
                "provenance": "REAL_FETCHED", "source_manifest_id": p.source_manifest_id,
                "notes": f"OSM tags: {p.tags}", "_src": p.osm_id})
        # Origin proxies: OSM place=city/town nodes inside the division
        towns = places[places["place"].isin(["city", "town"])]
        gpl = gpd.GeoDataFrame(towns, geometry=gpd.points_from_xy(towns["lon"], towns["lat"]), crs=4326)
        gpl = gpd.sjoin(gpl, districts, predicate="within", how="inner")
        for p in gpl.itertuples(index=False):
            rows.append({
                "node_type": "FarmGatherPoint", "name": f"{p.name_en if isinstance(p.name_en, str) else p.name} (origin proxy)",
                "name_source": "osm_place", "lat": p.lat, "lon": p.lon, "district": p.district, "osm_id": p.osm_id,
                "agmarknet_market_name": None, "geocode_method": "osm_tag", "geocode_confidence": 0.9,
                "capacity_kg": None, "capacity_source": "n/a", "provenance": "ASSUMPTION",
                "source_manifest_id": p.source_manifest_id,
                "notes": f"origin proxy, not an actual collection centre (OSM place={p.place})", "_src": p.osm_id})
    df = pd.DataFrame(rows)
    df = add_demo_nodes(df, G, districts, synthetic)
    df["node_id"] = [stable_id("N", t, s) for t, s in zip(df["node_type"], df["_src"], strict=True)]
    df = snap(df, G)
    df["needs_review"] = (df["geocode_confidence"].astype(float) < th.geocode_confidence_min) | \
        (df["snap_distance_m"].astype(float) > th.snap_distance_review_m) | df["lat"].isna()
    stats.counts["business_nodes"] = df.groupby(["node_type", "provenance"]).size().to_dict()
    stats.counts["needs_review"] = int(df["needs_review"].sum())
    return df.drop(columns="_src")


DEMO_MIN = {"NGOSink": 3, "ProcessingSink": 2, "TransitStorageNode": 3}
DEMO_LABEL = {"NGOSink": "Demo NGO", "ProcessingSink": "Demo Processor", "TransitStorageNode": "Demo Cold Store"}


def add_demo_nodes(df: pd.DataFrame, G, districts: gpd.GeoDataFrame, synthetic: bool) -> pd.DataFrame:
    """Fictional demo nodes only where a category has fewer real nodes than DEMO_MIN. They sit on real
    graph nodes (deterministically: the graph node nearest each district polygon's representative point,
    cycling through districts in name order) and are tagged SYNTHETIC_DEMO."""
    if G is None or not len(G):
        return df
    anchors = []
    for d in districts.sort_values("district").itertuples(index=False):
        rp = d.geometry.representative_point()
        anchors.append((d.district, rp.y, rp.x))
    ids = np.array(list(G.nodes))
    xy = np.radians([[G.nodes[n]["y"], G.nodes[n]["x"]] for n in ids])
    tree = BallTree(xy, metric="haversine")
    extra, i = [], 0
    for cat, need in DEMO_MIN.items():
        have = int(((df["node_type"] == cat) & (df["provenance"] != "SYNTHETIC_DEMO")).sum()) if len(df) else 0
        for j in range(max(0, need - have)):
            dname, lat, lon = anchors[i % len(anchors)]
            i += 1
            _, idx = tree.query(np.radians([[lat, lon]]), k=1)
            gn = ids[idx[0][0]]
            extra.append({"node_type": cat, "name": f"{DEMO_LABEL[cat]} {j + 1} DEMO", "name_source": "fictional_demo",
                          "lat": G.nodes[gn]["y"], "lon": G.nodes[gn]["x"], "district": dname, "osm_id": None,
                          "agmarknet_market_name": None, "geocode_method": "manual_review", "geocode_confidence": 1.0,
                          "capacity_kg": 2000.0 if cat == "NGOSink" else 10000.0,
                          "capacity_source": "SYNTHETIC_DEMO (fictional)", "provenance": "SYNTHETIC_DEMO",
                          "source_manifest_id": "synthetic:demo_nodes",
                          "notes": f"fictional demo node; only {have} real {cat} node(s) in OSM; excluded from real metrics",
                          "_src": f"demo:{cat}:{j + 1}"})
    return pd.concat([df, pd.DataFrame(extra)], ignore_index=True) if extra else df


def snap(df: pd.DataFrame, G) -> pd.DataFrame:
    df = df.copy()
    df["snapped_graph_node"] = None
    df["snap_distance_m"] = np.nan
    ok = df["lat"].notna()
    if G is None or not ok.any():
        return df
    ids = np.array(list(G.nodes))
    tree = BallTree(np.radians([[G.nodes[n]["y"], G.nodes[n]["x"]] for n in ids]), metric="haversine")
    pts = np.radians(df.loc[ok, ["lat", "lon"]].astype(float).values)
    dist, idx = tree.query(pts, k=1)
    df.loc[ok, "snapped_graph_node"] = ids[idx[:, 0]]
    df.loc[ok, "snap_distance_m"] = np.round(dist[:, 0] * EARTH_R, 1)
    return df


# ---------------------------------------------------------------- OD matrix + checks
def od_matrix(G: nx.MultiDiGraph, nodes: pd.DataFrame) -> pd.DataFrame:
    acc = speeds().access_leg
    use = nodes[~nodes["needs_review"]].copy()
    simple = nx.DiGraph()
    for u, v, d in G.edges(data=True):
        if not simple.has_edge(u, v) or d["free_flow_time_s"] < simple[u][v]["t"]:
            simple.add_edge(u, v, t=d["free_flow_time_s"], length=d["length"])
    access_t = use["snap_distance_m"] * acc.detour_factor / (acc.speed_kmh / 3.6)
    access_d = use["snap_distance_m"] * acc.detour_factor
    use = use.assign(access_t=access_t.values, access_d=access_d.values)
    targets = {gn: [] for gn in use["snapped_graph_node"]}
    for r in use.itertuples(index=False):
        targets[r.snapped_graph_node].append(r)
    rows = []
    for o in use.itertuples(index=False):
        lt, paths = nx.single_source_dijkstra(simple, o.snapped_graph_node, weight="t")
        for gn, lst in targets.items():
            if gn not in lt:
                continue
            dist = sum(simple[a][b]["length"] for a, b in zip(paths[gn][:-1], paths[gn][1:], strict=True))
            for dnode in lst:
                if dnode.node_id == o.node_id:
                    continue
                rows.append({"origin": o.node_id, "dest": dnode.node_id,
                             "time_s": round(lt[gn] + o.access_t + dnode.access_t, 1),
                             "dist_m": round(dist + o.access_d + dnode.access_d, 1),
                             "policy": "free_flow_static", "provenance": "REAL_DERIVED"})
    return pd.DataFrame(rows)


def run_checks(G, nodes: pd.DataFrame, edges: pd.DataFrame, od: pd.DataFrame, stats: BuildStats) -> bool:
    def check(name: str, ok: bool, detail: str = "") -> None:
        stats.checks.append({"check": name, "pass": bool(ok), "detail": detail})

    check("graph is one strongly connected component", nx.number_strongly_connected_components(G) == 1)
    check("no isolated graph nodes", nx.number_of_isolates(G) == 0, f"{nx.number_of_isolates(G)} isolates")
    check("no duplicate node_id", not nodes["node_id"].duplicated().any())
    check("no duplicate edge_id", not edges["edge_id"].duplicated().any())
    check("no zero/negative lengths", bool((edges["length_m"] > 0).all()))
    check("no self-loops", bool((edges["u"] != edges["v"]).all()))
    out = int((edges["speed_flag"] != "").sum())
    check("speeds within plausible range (flagged, not clipped)", True, f"{out} edges flagged OUT_OF_PLAUSIBLE_RANGE")
    for df, nm in ((nodes, "nodes"), (edges, "edges")):
        check(f"every {nm} row has provenance + source_manifest_id",
              bool(df["provenance"].notna().all() and df["source_manifest_id"].notna().all()))
    usable = nodes[~nodes["needs_review"]]
    recv = set(usable[usable["node_type"] == "ReceivingMarket"]["node_id"])
    sinks_real = set(usable[usable["node_type"].isin(["NGOSink", "ProcessingSink"]) & (usable["provenance"] != "SYNTHETIC_DEMO")]["node_id"])
    sinks_any = set(usable[usable["node_type"].isin(["NGOSink", "ProcessingSink"])]["node_id"])
    reach = od.groupby("origin")["dest"].apply(set).to_dict() if len(od) else {}
    unreach_m = [n for n in usable["node_id"] if not (reach.get(n, set()) & (recv - {n}))]
    unreach_s = [n for n in usable["node_id"] if not (reach.get(n, set()) & (sinks_any - {n}))]
    check("every reviewed business node reaches ≥1 receiving market", not unreach_m, f"unreachable: {unreach_m[:10]}")
    check("every reviewed business node reaches ≥1 NGO/processing sink", not unreach_s,
          f"unreachable: {unreach_s[:10]}; real (non-demo) sinks available: {len(sinks_real)}")
    return all(c["pass"] for c in stats.checks)


# ---------------------------------------------------------------- exports
def export_geo(G, nodes: pd.DataFrame, edges: pd.DataFrame, synthetic: bool) -> None:
    GEO_DIR.mkdir(parents=True, exist_ok=True)
    feats = []
    seen = set()
    for u, v, k, d in G.edges(keys=True, data=True):
        key = (min(u, v), max(u, v))
        if key in seen:      # one feature per road segment for display (both directions share geometry)
            continue
        seen.add(key)
        geom = d.get("geometry") or LineString([(G.nodes[u]["x"], G.nodes[u]["y"]), (G.nodes[v]["x"], G.nodes[v]["y"])])
        geom = geom.simplify(0.0003, preserve_topology=False)
        hw = d["highway"]
        feats.append({"type": "Feature", "properties": {"edge_id": f"E{u}_{v}_{k}", "hw": _first(hw) if isinstance(hw, list) else hw},
                      "geometry": {"type": "LineString", "coordinates": [[round(x, 5), round(y, 5)] for x, y in geom.coords]}})
    feats.sort(key=lambda f: f["properties"]["edge_id"])
    meta = {"provenance": "SYNTHETIC_DEMO" if synthetic else "REAL_DERIVED",
            "attribution": "© OpenStreetMap contributors (ODbL)" if not synthetic else "Synthetic network: not real roads"}
    (GEO_DIR / "edges_simplified.geojson").write_text(json.dumps({"type": "FeatureCollection", "meta": meta, "features": feats},
                                                                  separators=(",", ":")), encoding="utf-8")
    nf = []
    for r in nodes.sort_values("node_id").itertuples(index=False):
        if pd.isna(r.lat):
            continue
        nf.append({"type": "Feature", "geometry": mapping(Point(round(float(r.lon), 6), round(float(r.lat), 6))),
                   "properties": {"node_id": r.node_id, "node_type": r.node_type, "name": r.name, "district": r.district,
                                  "provenance": r.provenance, "needs_review": bool(r.needs_review),
                                  "geocode_confidence": float(r.geocode_confidence)}})
    (GEO_DIR / "nodes.geojson").write_text(json.dumps({"type": "FeatureCollection", "meta": meta, "features": nf},
                                                      ensure_ascii=False, separators=(",", ":")), encoding="utf-8")


# ---------------------------------------------------------------- synthetic fallback (§9 step 9)
def build_synthetic(stats: BuildStats) -> tuple[nx.MultiDiGraph, str]:
    """Small grid inside the division bbox. Only used when OSM data cannot be obtained."""
    stats.synthetic = True
    div = gpd.read_file(PROCESSED / "division_boundary.geojson")
    minx, miny, maxx, maxy = div.total_bounds
    n = 12
    G = nx.MultiDiGraph(crs="epsg:4326")
    xs, ys = np.linspace(minx, maxx, n), np.linspace(miny, maxy, n)
    for i in range(n):
        for j in range(n):
            G.add_node(i * n + j, x=float(xs[i]), y=float(ys[j]))
    for i in range(n):
        for j in range(n):
            for di, dj in ((1, 0), (0, 1)):
                if i + di < n and j + dj < n:
                    a, b = i * n + j, (i + di) * n + j + dj
                    L = float(haversine_m(xs[i], ys[j], xs[i + di], ys[j + dj]))
                    for s, t in ((a, b), (b, a)):
                        G.add_edge(s, t, osmid=f"synthetic:{s}-{t}", highway="secondary", maxspeed_kmh=None,
                                   speed_kmh_used=35.0, speed_source="class_default_ASSUMPTION", length=L,
                                   free_flow_time_s=L / (35 / 3.6), oneway=False, name="Synthetic road (not real)")
    stats.counts.update({"final_nodes": G.number_of_nodes(), "final_edges": G.number_of_edges()})
    return G, "synthetic:grid"


# ---------------------------------------------------------------- main
def run(force_synthetic: bool = False) -> int:
    stats = BuildStats()
    synthetic = force_synthetic or not (CACHE / "osm_road_ways.parquet").exists()
    if synthetic:
        print("WARNING: OSM road extract not available → SYNTHETIC_DEMO grid network (not real roads)", file=sys.stderr)
        G, mid = build_synthetic(stats)
    else:
        G, mid = build_road_graph(stats)
    edges = edges_frame(G, mid, "SYNTHETIC_DEMO" if synthetic else "REAL_DERIVED")
    nodes = build_business_nodes(G, stats, synthetic)
    nodes = nodes[NODE_COLS]
    od = od_matrix(G, nodes)
    ok = run_checks(G, nodes, edges, od, stats)

    write_csv_deterministic(nodes, PROCESSED / "nodes.csv", ["node_id"])
    write_csv_deterministic(edges, PROCESSED / "edges.csv", ["edge_id"])
    REPORTS.mkdir(exist_ok=True)
    write_csv_deterministic(nodes[nodes["needs_review"]], REPORTS / "nodes_needing_review.csv", ["node_type", "name"])
    CACHE.mkdir(parents=True, exist_ok=True)
    od.sort_values(["origin", "dest"]).reset_index(drop=True).to_parquet(CACHE / "od_matrix.parquet", index=False)
    ox.save_graphml(G, CACHE / "graph.graphml")
    export_geo(G, nodes, edges, synthetic)
    meta = {"synthetic": synthetic, "banner": "Synthetic network: not real roads" if synthetic else None,
            "osmnx_version": ox.__version__, "networkx_version": nx.__version__, "source_manifest_id": mid,
            "counts": {k: (str(v) if isinstance(v, dict) else v) for k, v in stats.counts.items()},
            "drops": stats.drops, "checks": stats.checks,
            "speed_source": edges["speed_source"].value_counts().to_dict(),
            "highway_class": edges["highway_class"].value_counts().to_dict(),
            "od_pairs": len(od)}
    (PROCESSED / "graph_meta.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False, default=str) + "\n", encoding="utf-8")
    from pipelines.graph_report import write_report
    write_report(G, nodes, edges, od, meta)

    write_audit("osm_roads", AuditRecord(
        need="Road network (drivable graph)", source_name="OpenStreetMap (Geofabrik Western Zone extract) → OSMnx",
        status="MISSING" if synthetic else "AVAILABLE",
        access="Bulk .osm.pbf download; pyosmium filter; OSMnx simplify/truncate", auth="none",
        licence="ODbL 1.0: attribution + share-alike for derived databases",
        coverage=f"{stats.counts.get('final_nodes')} nodes / {stats.counts.get('final_edges')} directed edges after cleaning; "
                 f"classes {geography().current.road_classes}",
        tried=["Overpass instances timed out / at capacity (2026-10-25)", "Geofabrik western-zone-latest.osm.pbf"],
        fallback="SYNTHETIC_DEMO grid if the extract is unavailable",
        known_problems="Western Zone extract covers ~95% of the 5 km buffer (edges in MP/Chhattisgarh/Telangana missing); "
                       "most edges use class-default speeds (ASSUMPTION); no traffic.",
        flags=["ATTRIBUTION_REQUIRED", "SHARE_ALIKE_ODbL"] + (["SYNTHETIC"] if synthetic else [])))
    print(json.dumps({k: meta[k] for k in ("synthetic", "counts", "speed_source", "od_pairs")}, indent=1, default=str))
    for c in stats.checks:
        print(("PASS " if c["pass"] else "FAIL ") + c["check"] + (f"  ({c['detail']})" if c["detail"] else ""))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(run(force_synthetic="--synthetic" in sys.argv))
