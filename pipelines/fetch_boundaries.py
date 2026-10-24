"""District boundaries for the pilot geography from OSM via Nominatim (polygon_geojson=1).

Nominatim usage policy: ≤1 request/s, identifying User-Agent, no bulk geocoding; results cached.
OSM data © OpenStreetMap contributors, ODbL 1.0 (attribution + share-alike for derived databases).
"""
from __future__ import annotations

import json
import sys

import geopandas as gpd
from app.core.config import geography
from shapely.geometry import shape
from shapely.ops import unary_union

from pipelines.common import (
    PROCESSED,
    AuditRecord,
    SourceMeta,
    fetch_cached,
    manifest_id,
    write_audit,
)

META = SourceMeta("osm_nominatim_boundaries", "ODbL 1.0 (OpenStreetMap). Attribution required: '© OpenStreetMap contributors'.",
                  "https://operations.osmfoundation.org/policies/nominatim/",
                  "District polygons via Nominatim search with polygon_geojson=1.")
URL = "https://nominatim.openstreetmap.org/search"


def slug(name: str) -> str:
    return name.lower().replace(" ", "_")


def run(refresh: bool = False) -> gpd.GeoDataFrame | None:
    geo = geography().current
    feats, tried, problems = [], [], []
    for d in geo.districts:
        params = {"q": d.osm_query, "format": "jsonv2", "polygon_geojson": 1, "limit": 3, "addressdetails": 0}
        tried.append(f"GET {URL}?q={d.osm_query}")
        p, status = fetch_cached(META, f"{slug(d.osm_query)}.json", URL, params=params, refresh=refresh, min_interval_s=1.5)
        if p is None:
            problems.append(f"{d.name}: {status}")
            continue
        hits = json.loads(p.read_text(encoding="utf-8"))
        # Only district-level admin relations: Nominatim addresstype 'state_district' (a city relation of the same
        # name was returned for "Gondia District", so the level is checked, never assumed).
        poly = [h for h in hits if h.get("osm_type") == "relation" and h.get("addresstype") == "state_district"
                and h.get("geojson", {}).get("type") in ("Polygon", "MultiPolygon")]
        if not poly:
            problems.append(f"{d.name}: no relation polygon in Nominatim result ({[h.get('type') for h in hits]})")
            continue
        h = poly[0]
        feats.append({"district": d.name, "osm_id": f"relation/{h['osm_id']}", "osm_display_name": h["display_name"],
                      "osm_class": h.get("category", h.get("class")), "osm_addresstype": h.get("addresstype"),
                      "place_rank": h.get("place_rank"),
                      "geometry": shape(h["geojson"]), "provenance": "REAL_FETCHED",
                      "source_manifest_id": manifest_id(META.source, p.name)})
    status = "AVAILABLE" if len(feats) == len(geo.districts) else ("PARTIAL" if feats else "MISSING")
    gdf = None
    if feats:
        gdf = gpd.GeoDataFrame(feats, crs="EPSG:4326").sort_values("district")
        PROCESSED.mkdir(parents=True, exist_ok=True)
        gdf.to_file(PROCESSED / "district_boundaries.geojson", driver="GeoJSON")
        division = gpd.GeoDataFrame({"name": [geo.label], "provenance": ["REAL_DERIVED"],
                                     "derivation": ["unary_union of district polygons"]},
                                    geometry=[unary_union(list(gdf.geometry))], crs="EPSG:4326")
        division.to_file(PROCESSED / "division_boundary.geojson", driver="GeoJSON")
    write_audit("osm_boundaries", AuditRecord(
        need="Pilot geography boundary (Nagpur Division)", source_name="OpenStreetMap admin relations via Nominatim",
        status=status, access="HTTP GET (Nominatim search API)", auth="none (User-Agent required)",
        licence=META.licence, coverage=f"{len(feats)}/{len(geo.districts)} district polygons: "
        + ", ".join(f"{f['district']}={f['osm_id']}" for f in feats),
        tried=tried, why_failed="; ".join(problems), fallback="If missing: no bbox is hand-typed; graph build falls back to the labelled synthetic network (§9 step 9).",
        urls=[URL], rate_limits="Nominatim policy: max 1 req/s; we use 1.5 s", freshness="OSM live data at fetch time",
        known_problems="District boundaries in OSM are community-mapped; not an official survey boundary. "
                       "Division polygon is the union of the six district relations (no 'Nagpur Division' relation used).",
        flags=["ATTRIBUTION_REQUIRED", "SHARE_ALIKE_ODbL"]))
    print(f"boundaries: {status} {len(feats)} districts; problems: {problems}")
    return gdf


if __name__ == "__main__":
    run(refresh="--refresh" in sys.argv)
