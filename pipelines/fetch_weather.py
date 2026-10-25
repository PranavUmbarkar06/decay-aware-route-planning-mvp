"""Hourly weather replay from the Open-Meteo historical archive.

Points: one per pilot district, the polygon's representative point (shapely `representative_point`,
guaranteed inside the polygon) computed from the OSM district boundary. No coordinates are hand-typed.
Open-Meteo snaps each request to its model grid; the returned grid point and the snap distance are stored
so the grid-snapping error is documented per point.

Licence: data CC BY 4.0; free API for non-commercial use only (ADR-008: owner confirmed non-commercial
research, 2026-10-25). Attribution: "Weather data by Open-Meteo.com".
"""
from __future__ import annotations

import json
import sys
from datetime import date

import geopandas as gpd
import pandas as pd
from pyproj import Geod

from pipelines.common import (
    PROCESSED,
    AuditRecord,
    SourceMeta,
    fetch_cached,
    manifest_id,
    write_audit,
    write_csv_deterministic,
)

META = SourceMeta("open_meteo_archive", "CC BY 4.0 (data). Free API: non-commercial use only (terms read 2026-10-24).",
                  "https://open-meteo.com/en/terms",
                  "Owner confirmed non-commercial research use on 2026-10-25 (ADR-008). Attribution: 'Weather data by Open-Meteo.com'.")
URL = "https://archive-api.open-meteo.com/v1/archive"
VARS = ["temperature_2m", "relative_humidity_2m", "precipitation"]
# Window aligned with the Agmarknet 2.0 arrivals ('Both' report starts 2025-11-07). The end date is
# pinned (not "today") so reruns are reproducible; it was set 7 days before the first fetch because the
# archive lags real time. Move it forward deliberately, then rerun with --refresh.
START = date(2025, 11, 1)
END = date(2026, 10, 18)
_geod = Geod(ellps="WGS84")


def run(refresh: bool = False, end: date | None = None) -> pd.DataFrame:
    bpath = PROCESSED / "district_boundaries.geojson"
    if not bpath.exists():
        raise RuntimeError("district_boundaries.geojson missing: run pipelines.fetch_boundaries first")
    gdf = gpd.read_file(bpath)
    end = end or END
    frames, points, problems = [], [], []
    for _, row in gdf.sort_values("district").iterrows():
        rp = row.geometry.representative_point()
        lat, lon = round(rp.y, 4), round(rp.x, 4)
        params = {"latitude": lat, "longitude": lon, "start_date": START.isoformat(), "end_date": end.isoformat(),
                  "hourly": ",".join(VARS), "timezone": "UTC"}
        fname = f"{row['district'].lower()}_{START:%Y%m%d}_{end:%Y%m%d}.json"
        p, status = fetch_cached(META, fname, URL, params=params, refresh=refresh, min_interval_s=1.0)
        if p is None:
            problems.append(f"{row['district']}: {status}")
            continue
        js = json.loads(p.read_text(encoding="utf-8"))
        if "hourly" not in js:
            problems.append(f"{row['district']}: no hourly data ({js.get('reason')})")
            continue
        _, _, snap_m = _geod.inv(lon, lat, js["longitude"], js["latitude"])
        mid = manifest_id(META.source, p.name)
        h = pd.DataFrame(js["hourly"])
        h = h.rename(columns={"time": "time_utc"})
        h.insert(0, "district", row["district"])
        h["provenance"] = "REAL_FETCHED"
        h["source_manifest_id"] = mid
        frames.append(h)
        n_missing = {v: int(h[v].isna().sum()) for v in VARS}
        points.append({"district": row["district"], "request_lat": lat, "request_lon": lon,
                       "grid_lat": js["latitude"], "grid_lon": js["longitude"], "grid_snap_m": round(snap_m, 1),
                       "elevation_m": js.get("elevation"), "point_method": "representative_point(OSM district polygon)",
                       "hours": len(h), "missing_values": json.dumps(n_missing, sort_keys=True),
                       "provenance": "REAL_DERIVED", "source_manifest_id": mid})
    weather = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    pts = pd.DataFrame(points)
    if len(weather):
        write_csv_deterministic(weather, PROCESSED / "weather_hourly.csv", ["district", "time_utc"])
        write_csv_deterministic(pts, PROCESSED / "weather_points.csv", ["district"])
    status = "AVAILABLE" if len(points) == len(gdf) else ("PARTIAL" if points else "MISSING")
    write_audit("open_meteo", AuditRecord(
        need="Weather replay (temperature, humidity, precipitation) for decay and delay modelling",
        source_name="Open-Meteo historical weather archive API",
        status=status, access="HTTP GET JSON", auth="none",
        licence=META.licence,
        coverage=f"{len(points)}/{len(gdf)} district points, hourly {START}..{end} UTC, vars {VARS}; "
                 + "; ".join(f"{p['district']}: grid snap {p['grid_snap_m']:.0f} m, missing {p['missing_values']}" for p in points),
        tried=[f"GET {URL} per district point"], why_failed="; ".join(problems),
        fallback="If missing: simulation runs with a constant-temperature ASSUMPTION and every output carries a warning.",
        urls=[URL, META.terms_url], rate_limits="free tier: <10,000/day, 5,000/hour, 600/min",
        freshness=f"archive window {START}..{end} (pinned in pipelines/fetch_weather.py)",
        known_problems="Reanalysis grid values (not station observations). One point per district stands in for the "
                       "whole district; road-level microclimate and in-truck temperature are not observed.",
        flags=["NON_COMMERCIAL_FREE_TIER", "ATTRIBUTION_REQUIRED", "OWNER_CONFIRMED_NON_COMMERCIAL_2026-10-25"]))
    print(f"weather: {status}; {len(weather)} hourly rows; problems: {problems}")
    if len(pts):
        print(pts[["district", "grid_snap_m", "hours", "missing_values"]].to_string(index=False))
    return weather


if __name__ == "__main__":
    run(refresh="--refresh" in sys.argv)
