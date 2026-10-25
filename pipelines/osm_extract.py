"""Extract roads and points of interest for the pilot geography from a Geofabrik OSM extract (ADR-021).

Why not Overpass: during Phase 1/2 the public Overpass instances were at capacity or timed out
(see data/audit/osm_roads.json) and the main instance asks automated/high-volume users to use other
means. Geofabrik regional extracts are intended for bulk download. Data © OpenStreetMap contributors, ODbL 1.0.

Outputs
- data/cache/osm_road_ways.parquet: one row per highway way (selected classes) intersecting the
  division bbox + buffer, with node ids and coordinates (REAL_DERIVED from the raw .pbf).
- data/processed/osm_pois.csv: tagged features used as business-node candidates (committed).
- data/cache/osm_places.parquet: place=city/town/village/hamlet nodes for geocoding lookups.

Tag filters (equivalent Overpass QL is written to GRAPH_BUILD.md):
"""
from __future__ import annotations

import re
import sys

import geopandas as gpd
import osmium
import pandas as pd
from app.core.config import geography

from pipelines.common import (
    CACHE,
    PROCESSED,
    RAW,
    AuditRecord,
    SourceMeta,
    fetch_cached,
    manifest_id,
    write_audit,
    write_csv_deterministic,
)

META = SourceMeta("geofabrik_india_western_zone", "ODbL 1.0 (OpenStreetMap). Attribution '© OpenStreetMap contributors'; "
                  "share-alike applies to derived databases (nodes.csv/edges.csv).",
                  "https://download.geofabrik.de/asia/india/western-zone.html",
                  "Geofabrik daily extract of OSM for India Western Zone (Maharashtra, Gujarat, Goa, DNH&DD).")
PBF_URL = "https://download.geofabrik.de/asia/india/western-zone-latest.osm.pbf"
POLY_URL = "https://download.geofabrik.de/asia/india/western-zone.poly"

# Candidate business-node tag filters. key -> (category, predicate on tags dict)
NAME_COLD = re.compile(r"cold\s*stor|cold\s*chain|शीतगृह|शीत\s*गृह", re.I)
NAME_MARKET = re.compile(r"\bapmc\b|krishi\s*utpan|bazar\s*samiti|बाजार\s*समिती|market\s*yard|mandi|मंडी", re.I)
NAME_FOOD_PROC = re.compile(r"food\s*process|agro\s*(industr|process|food)|dal\s*mill|fruit\s*process", re.I)

POI_RULES: list[tuple[str, str]] = [
    ("TransitStorageNode", "industrial=cold_storage | name~cold storage/शीतगृह | building=warehouse | industrial=warehouse"),
    ("NGOSink", "office=ngo | office=charity | social_facility=food_bank|soup_kitchen | amenity=food_bank"),
    ("ProcessingSink", "industrial=food_industry|food | man_made=works + product~food | name~food processing/agro industries"),
    ("MarketplaceCandidate", "amenity=marketplace | name~APMC/Krishi Utpanna/Bazar Samiti/market yard/mandi"),
]


def classify(tags: dict[str, str]) -> str | None:
    name = tags.get("name", "") + " " + tags.get("name:en", "")
    if tags.get("industrial") == "cold_storage" or NAME_COLD.search(name):
        return "TransitStorageNode"
    if tags.get("office") in ("ngo", "charity") or tags.get("social_facility") in ("food_bank", "soup_kitchen") \
            or tags.get("amenity") == "food_bank":
        return "NGOSink"
    if tags.get("industrial") in ("food_industry", "food") or NAME_FOOD_PROC.search(name) \
            or (tags.get("man_made") == "works" and "food" in tags.get("product", "")):
        return "ProcessingSink"
    if tags.get("building") == "warehouse" or tags.get("industrial") == "warehouse":
        return "TransitStorageNode"
    if tags.get("amenity") == "marketplace" or NAME_MARKET.search(name):
        return "MarketplaceCandidate"
    return None


def area_bbox() -> tuple[float, float, float, float]:
    d = gpd.read_file(PROCESSED / "division_boundary.geojson").to_crs(32644)
    buf = geography().current.boundary_buffer_km * 1000
    return tuple(d.buffer(buf).to_crs(4326).total_bounds)  # type: ignore[return-value]


def extract(pbf_path, bbox, road_classes: set[str]):
    """Single pass. Python only sees objects that carry one of the relevant keys (pyosmium KeyFilter);
    way POIs use the centroid of their node locations (no polygon assembly); relations are skipped."""
    minx, miny, maxx, maxy = bbox

    def inside(lon, lat):
        return minx <= lon <= maxx and miny <= lat <= maxy

    ways, pois, places = [], [], []
    keys = ("highway", "place", "amenity", "office", "social_facility", "industrial", "building", "man_made", "name")
    fp = (osmium.FileProcessor(str(pbf_path), osmium.osm.NODE | osmium.osm.WAY)
          .with_locations()
          .with_filter(osmium.filter.KeyFilter(*keys)))
    for o in fp:
        if o.is_node():
            loc = o.location
            if not loc.valid() or not inside(loc.lon, loc.lat):
                continue
            tags = dict(o.tags)
            if tags.get("place") in ("city", "town", "village", "hamlet") and tags.get("name"):
                places.append({"osm_id": f"node/{o.id}", "name": tags["name"], "name_en": tags.get("name:en"),
                               "name_mr": tags.get("name:mr"), "place": tags["place"], "lat": loc.lat, "lon": loc.lon})
            cat = classify(tags)
            if cat:
                pois.append({"osm_id": f"node/{o.id}", "category": cat, "name": tags.get("name"),
                             "tags": ";".join(f"{k}={v}" for k, v in sorted(tags.items()) if k in KEEP_TAGS),
                             "lat": loc.lat, "lon": loc.lon})
            continue
        # ways
        t = o.tags
        hw = t.get("highway")
        bld = t.get("building")
        if hw is None and bld is not None and bld != "warehouse" and "name" not in t and "industrial" not in t:
            continue                                   # plain buildings: by far the most common, skip fast
        try:
            first = o.nodes[0].location
        except (osmium.InvalidLocationError, IndexError):
            continue
        if hw in road_classes:
            try:
                coords = [(n.ref, n.lon, n.lat) for n in o.nodes]
            except osmium.InvalidLocationError:
                continue
            if any(inside(x, y) for _, x, y in coords):
                tags = dict(t)
                ways.append({"way_id": o.id, "highway": hw, "maxspeed": tags.get("maxspeed"),
                             "oneway": tags.get("oneway"), "junction": tags.get("junction"),
                             "name": tags.get("name"), "ref": tags.get("ref"), "bridge": tags.get("bridge"),
                             "route": tags.get("route"),
                             "node_ids": [c[0] for c in coords], "lons": [c[1] for c in coords],
                             "lats": [c[2] for c in coords]})
            continue
        if not first.valid() or not inside(first.lon, first.lat):
            continue
        tags = dict(t)
        cat = classify(tags)
        if cat:
            try:
                xs = [n.lon for n in o.nodes]
                ys = [n.lat for n in o.nodes]
            except osmium.InvalidLocationError:
                continue
            pois.append({"osm_id": f"way/{o.id}", "category": cat, "name": tags.get("name"),
                         "tags": ";".join(f"{k}={v}" for k, v in sorted(tags.items()) if k in KEEP_TAGS),
                         "lat": sum(ys) / len(ys), "lon": sum(xs) / len(xs)})
    return ways, pois, places


KEEP_TAGS = {"name", "name:en", "name:mr", "amenity", "office", "social_facility", "industrial", "building", "landuse",
             "man_made", "product", "shop", "operator", "addr:city", "addr:district"}


def run(refresh: bool = False) -> None:
    geo = geography().current
    fetch_cached(META, "western-zone.poly", POLY_URL, refresh=refresh)
    pbf, status = fetch_cached(META, "western-zone-latest.osm.pbf", PBF_URL, refresh=refresh, timeout=1800)
    if pbf is None:
        raise RuntimeError(f"OSM extract unavailable ({status}); build_graph will use the SYNTHETIC_DEMO fallback")
    mid = manifest_id(META.source, pbf.name)
    bbox = area_bbox()
    ways, pois, places = extract(pbf, bbox, set(geo.road_classes))
    w = pd.DataFrame(ways).sort_values("way_id")
    w["provenance"] = "REAL_DERIVED"
    w["source_manifest_id"] = mid
    CACHE.mkdir(parents=True, exist_ok=True)
    w.to_parquet(CACHE / "osm_road_ways.parquet", index=False)
    pl = pd.DataFrame(places).sort_values("osm_id")
    pl["provenance"] = "REAL_FETCHED"
    pl["source_manifest_id"] = mid
    pl.to_parquet(CACHE / "osm_places.parquet", index=False)
    p = pd.DataFrame(pois).drop_duplicates("osm_id") if pois else pd.DataFrame(
        columns=["osm_id", "category", "name", "tags", "lat", "lon"])
    # Keep only POIs inside the division polygon (not just the bbox)
    div = gpd.read_file(PROCESSED / "division_boundary.geojson").iloc[0].geometry
    if len(p):
        gp = gpd.GeoDataFrame(p, geometry=gpd.points_from_xy(p["lon"], p["lat"]), crs=4326)
        p = pd.DataFrame(gp[gp.within(div)].drop(columns="geometry"))
    p["provenance"] = "REAL_FETCHED"
    p["source_manifest_id"] = mid
    write_csv_deterministic(p, PROCESSED / "osm_pois.csv", ["category", "osm_id"])
    counts = p["category"].value_counts().to_dict() if len(p) else {}
    pbf_ts = (RAW / META.source / "MANIFEST.json").read_text(encoding="utf-8")
    write_audit("osm_pois", AuditRecord(
        need="Warehouse / cold-storage / NGO / processing locations", source_name="OpenStreetMap (Geofabrik Western Zone extract)",
        status="PARTIAL" if counts else "MISSING", access="Bulk .osm.pbf download, filtered locally with pyosmium",
        auth="none", licence=META.licence,
        coverage=f"inside division polygon: {counts}; place nodes for geocoding: {len(pl)}",
        tried=["Overpass instances at capacity / timing out (2026-10-25)", f"GET {PBF_URL}"] + [f"{c}: {r}" for c, r in POI_RULES],
        why_failed="OSM coverage of warehouses/NGOs/processing units in this region is sparse (see counts)",
        fallback="Fictional 'Demo … DEMO' nodes (SYNTHETIC_DEMO) where a category has too few real nodes for the demo; "
                 "excluded from any metric labelled real.",
        urls=[PBF_URL], freshness="extract timestamp in MANIFEST (Geofabrik 'latest' at fetch time)",
        known_problems="Tag-based classification; many warehouses are unnamed; NGO tagging is rare in India OSM.",
        flags=["ATTRIBUTION_REQUIRED", "SHARE_ALIKE_ODbL", "EXPECT_SPARSE_COVERAGE"]))
    print(f"osm_extract: {len(w)} road ways; POIs {counts}; {len(pl)} place nodes; bbox {tuple(round(b, 3) for b in bbox)}")
    del pbf_ts


if __name__ == "__main__":
    run(refresh="--refresh" in sys.argv)
